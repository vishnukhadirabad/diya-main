# ======================================================================
# HARDENED VERSION — all serial-communication risk zones addressed
# Changes are marked with  # FIX-N  where N matches the risk-map above.
#
# HARDWARE POLICY (matches the updated Arduino firmware):
#
#   HOME LIMIT SWITCHES  = critical, and provable. Each is wired NO+NC,
#       so a healthy switch can never read the same level on both pins.
#       If either switch is NOT INTERFACED or MALFUNCTIONING (absent or
#       shorted), the process is halted immediately — at startup it never
#       enters the camera loop at all — a full-screen message names which
#       switch, and it stays halted until the switch is replaced.
#
#   PROXIMITY SENSORS    = early warning only, and NOT provable (an
#       unplugged wire and an idle sensor are electrically identical).
#       No presence test is attempted. If a prox is not interfaced or has
#       failed, its paired limit switch catches the lever instead, and
#       that is exactly what reveals the failure: the screen then reads
#       "PROX n NOT DETECTED — REPLACEMENT REQUIRED".
# ======================================================================

import cv2
import cvzone
from cvzone.FaceMeshModule import FaceMeshDetector
import numpy as np
import serial
import serial.tools.list_ports
import time
import threading
import sys
import os
import subprocess
import re

from camera_utils import get_camera_index

# ======================================================================
# HARDWARE GATE CONFIG
#
# Only the home limit switches gate startup. Both are listed because a
# single Arduino drives both axes and a missing switch on either one
# means that axis has no verifiable end-of-travel detection. Drop an
# entry only if that axis genuinely is not populated on the machine.
# ======================================================================
REQUIRED_COMPONENTS = ("M1_SWITCH", "M2_SWITCH", "COLLISION_SWITCH")

COMPONENT_LABELS = {
    "M1_SWITCH":        "M1 / CHEST HOME LIMIT SWITCH  (pins 5 & 6)",
    "M2_SWITCH":        "M2 / EYES  HOME LIMIT SWITCH  (pins 7 & 8)",
    "COLLISION_SWITCH": "COLLISION LIMIT SWITCH  (pins 3 & 4)",
    "CONTROLLER":       "ARDUINO CONTROLLER",
}

STATUS_LABELS = {
    "ABSENT":        "NOT INTERFACED  (unplugged, broken wire or COM not grounded)",
    "SHORT":         "MALFUNCTIONING  (short circuit in wiring)",
    "NO_REPLY":      "NO SELF-TEST REPLY FROM CONTROLLER",
    "SELFTEST_FAIL": "CONTROLLER REPORTED SELF-TEST FAILURE",
}


# ======== Arduino auto-detection ========
def find_arduino():
    """Return the device path of the first Arduino-like port, or None."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        hwid  = (port.hwid  or "").lower()
        if "ttyACM" in port.device or "arduino" in desc or "2341" in hwid:
            return port.device
    for port in ports:
        if "ttyACM" in port.device:
            return port.device
    return None

SERIAL_PORT = find_arduino()
if SERIAL_PORT is None:
    print("[ERROR] Arduino not found. Check USB connection and try again.")
    sys.exit(1)

print(f"[STARTUP] Auto-detected Arduino on {SERIAL_PORT}")

# ======== Arduino setup ========
arduino = serial.Serial(
    SERIAL_PORT,
    115200,
    timeout=2,
    write_timeout=1.0,
)
arduino.dtr = False
# FIX-1: extend DTR bounce delay — 100 ms was too short on slow USB hubs
time.sleep(0.5)
arduino.dtr = True
arduino.reset_input_buffer()
time.sleep(0.2)

# ======== Camera setup ========
_cam_src = get_camera_index("logitech")
cap = cv2.VideoCapture(_cam_src, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
cap.set(cv2.CAP_PROP_FPS,          15)
cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

detector = FaceMeshDetector(maxFaces=1)

# ======== Shared state ========
collision_event                  = threading.Event()
m1_home_event                    = threading.Event()
m2_home_event                    = threading.Event()
switch_event                     = threading.Event()
serial_dead_event                = threading.Event()
arduino_ready_event              = threading.Event()
switch_status_received_event     = threading.Event()
collision_status_received_event  = threading.Event()
shutdown_event                   = threading.Event()

# ---- prox-based EARLY stop events ----
# Set when the firmware's prox sensor alone caught the home lever during
# normal run, BEFORE the mechanical switch made contact. The firmware has
# already stopped that axis by the time the line arrives.
m1_home_early_event              = threading.Event()
m2_home_early_event              = threading.Event()

# ------------------------------------------------------------------
# EARLY collision warning from the A0 collision prox. This script only
# ever sends F: PID commands (never home/shoot), so the line that
# actually fires here is the firmware's loop()-level EARLY:COLLISION —
# non-latching on the firmware side, so without a handler here the
# motors get soft-stopped for an instant and the very next F: command
# would resume driving with no operator ever finding out. Treated the
# same as a mechanical collision: halt and require a restart.
# ------------------------------------------------------------------
collision_prox_early_event       = threading.Event()

# ------------------------------------------------------------------
# PROX FAILURE (not fatal to the machine, fatal to this run):
#   Set when the limit switch caught the lever but its paired prox never
#   fired — the prox is not interfaced, dead, misaligned, or wired with
#   the wrong polarity. The screen names it and asks for replacement.
# ------------------------------------------------------------------
prox1_fault_event   = threading.Event()
prox2_fault_event   = threading.Event()

# Legacy generic switch-wire line, still emitted by the firmware for the
# older scripts in the pipeline.
m1_wire_fault_event = threading.Event()
m2_wire_fault_event = threading.Event()

# ------------------------------------------------------------------
# LIMIT SWITCH ABSENT / SHORTED — the halt-until-replaced condition.
# ------------------------------------------------------------------
component_fault_lock = threading.Lock()
component_faults     = {}   # component key -> status string

selftest_lock        = threading.Lock()
selftest_results     = {}   # component key -> "OK" / "ABSENT" / "SHORT"
selftest_done_event  = threading.Event()
selftest_pass_event  = threading.Event()
selftest_fail_event  = threading.Event()

# Set by serial_reader the instant a reconnect succeeds. The Arduino
# almost certainly reset (opening the port toggles DTR), so the READY
# handshake, the switch/collision status AND the limit-switch self-test
# all have to be redone before any further motion command is sent.
reconnect_pending_event          = threading.Event()

# ------------------------------------------------------------------
# STARTUP "already at home" check (M2 / eyes) — home limit switch
# reply (HSTATUS2?) and prox-2 reply (PSTATUS2?). Queried once, right
# before the camera loop is entered.
# ------------------------------------------------------------------
hstatus2_result_event = threading.Event()
pstatus2_result_event = threading.Event()
hstatus2_value = {"v": None}   # "AT_HOME" / "AWAY" / "FAULT"
pstatus2_value = {"v": None}   # "TRIGGERED" / "CLEAR"

# ------------------------------------------------------------------
# STARTUP collision-prox (A0) check — mirrors the M2 "already at home"
# pattern above, applied to the collision prox instead. Queried once,
# right before the camera loop is entered, so an obstruction already
# sitting in the collision zone is caught before any motion command is
# sent rather than only once alignment is already moving.
# ------------------------------------------------------------------
pstatusC_result_event = threading.Event()
pstatusC_value = {"v": None}   # "TRIGGERED" / "CLEAR"

for _e in (collision_event, m1_home_event, m2_home_event, switch_event,
           serial_dead_event, arduino_ready_event,
           switch_status_received_event, collision_status_received_event,
           shutdown_event, reconnect_pending_event,
           m1_home_early_event, m2_home_early_event,
           collision_prox_early_event,
           prox1_fault_event, prox2_fault_event,
           m1_wire_fault_event, m2_wire_fault_event,
           selftest_done_event, selftest_pass_event, selftest_fail_event,
           hstatus2_result_event, pstatus2_result_event,
           pstatusC_result_event):
    _e.clear()

# ---- write-rate limiter (state shared between send_error and watchdog) ----
_last_write_time = 0.0
_MIN_WRITE_GAP   = 0.025   # 25 ms hard floor between any two serial writes

# ---- watchdog bookkeeping ----
_watchdog_reply_received = threading.Event()

serial_lock = threading.Lock()

# ======== Pre-load alert images once at startup ========
_BASE = os.path.dirname(os.path.abspath(__file__))

COLLISION_IMG_PATH = os.path.join(_BASE, "collision_img.png")
COLLISION_IMG = cv2.imread(COLLISION_IMG_PATH)
if COLLISION_IMG is None:
    print(f"[STARTUP WARNING] Collision image not found at '{COLLISION_IMG_PATH}'. "
          "Red overlay fallback will be used.")

# ======== Screen resolution helper ========
def get_screen_resolution():
    for cmd, pat in [
        ("xrandr | grep ' connected'",   r'(\d+)x(\d+)\+'),
        ("xdpyinfo | grep dimensions",   r'(\d+)x(\d+)'),
        ("wmctrl -d",                    r'(\d+)x(\d+)'),
    ]:
        try:
            out   = subprocess.check_output(cmd, shell=True).decode()
            match = re.search(pat, out)
            if match:
                return int(match.group(1)), int(match.group(2))
        except Exception:
            pass
    print("[Python] Could not detect screen resolution; defaulting to 1920x1080.")
    return 1920, 1080

screen_w, screen_h = get_screen_resolution()
print(f"Detected screen resolution: {screen_w}x{screen_h}")

panel_w = screen_w // 2
panel_h = screen_h
print(f"Each panel size: {panel_w}x{panel_h}")

# ======== Load & resize reference image once ========
_ref_path = os.path.join(_BASE, "eye_reference_left.png")
_ref_raw  = cv2.imread(_ref_path)
if _ref_raw is None:
    print(f"[STARTUP WARNING] Reference image not found at '{_ref_path}'. "
          "Left panel will be blank.")
    reference_resized = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
else:
    reference_resized = cv2.resize(_ref_raw, (panel_w, panel_h),
                                   interpolation=cv2.INTER_LINEAR)

# ======== Single display window ========
WIN = "Eye_Check"
cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
_win_sized = False

def _apply_win_size():
    global _win_sized
    if not _win_sized:
        cv2.moveWindow(WIN, 0, 0)
        cv2.resizeWindow(WIN, screen_w, screen_h)
        _win_sized = True

def _force_fullscreen(frame):
    cv2.imshow(WIN, frame)
    for _ in range(5):
        cv2.waitKey(30)
        cv2.moveWindow(WIN, 0, 0)
        cv2.resizeWindow(WIN, screen_w, screen_h)

def make_combined(camera_frame):
    cam_panel = cv2.resize(camera_frame, (panel_w, panel_h),
                           interpolation=cv2.INTER_LINEAR)
    return cv2.hconcat([reference_resized, cam_panel])


def _record_component_fault(component: str, status: str):
    """Record a limit-switch fault reported by the firmware. Stored in a
    dict so the firmware's 1 Hz repeats of the same fault don't pile up."""
    with component_fault_lock:
        component_faults[component] = status


# ======================================================================
# ROBUST SERIAL READER
# ======================================================================
def serial_reader():
    global arduino, SERIAL_PORT
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    while True:
        if shutdown_event.is_set():
            print("[serial_reader] Shutdown signalled — exiting thread.")
            return

        try:
            raw = arduino.readline()

            if shutdown_event.is_set():
                return

            if raw is None:
                time.sleep(0.05)
                continue

            line = raw.decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            print(f"[Arduino] {line}")
            _watchdog_reply_received.set()

            if   line == "READY":
                arduino_ready_event.set()
            elif line == "SWITCH:PRESSED":
                switch_event.set();   switch_status_received_event.set()
            elif line == "SWITCH:RELEASED":
                switch_event.clear(); switch_status_received_event.set()
            elif line == "COLLISION:ACTIVE":
                collision_event.set(); collision_status_received_event.set()
            elif line == "COLLISION:CLEAR":
                collision_status_received_event.set()
            elif line.lower() == "collision:occured":
                collision_event.set()
            elif line == "LIMIT:M1_HOME":
                m1_home_event.set()
            elif line == "LIMIT:M2_HOME":
                m2_home_event.set()

            # ---- prox-based EARLY stop lines ----
            elif line == "EARLY:M1_HOME":
                m1_home_early_event.set()
            elif line == "EARLY:M2_HOME":
                m2_home_early_event.set()
            elif line == "EARLY:COLLISION" or line == "EARLY:COLLISION_PROX_A0":
                collision_prox_early_event.set()

            # ---- LIMIT-SWITCH SELF-TEST REPORT ----
            elif line == "SELFTEST:BEGIN":
                with selftest_lock:
                    selftest_results.clear()
                selftest_done_event.clear()
                selftest_pass_event.clear()
                selftest_fail_event.clear()
            elif line.startswith("TEST:") and "=" in line:
                key, _, val = line[len("TEST:"):].partition("=")
                with selftest_lock:
                    selftest_results[key.strip()] = val.strip()
            elif line == "SELFTEST:PASS":
                selftest_pass_event.set()
            elif line == "SELFTEST:FAIL":
                selftest_fail_event.set()
            elif line == "SELFTEST:END":
                selftest_done_event.set()
            elif line == "ERROR:SELFTEST_FAILED":
                _record_component_fault("CONTROLLER", "SELFTEST_FAIL")

            # ---- LIMIT SWITCH NOT INTERFACED / MALFUNCTIONING ----
            elif line == "FAULT:M1_SWITCH_ABSENT":
                _record_component_fault("M1_SWITCH", "ABSENT")
            elif line == "FAULT:M2_SWITCH_ABSENT":
                _record_component_fault("M2_SWITCH", "ABSENT")
            elif line == "FAULT:M1_SWITCH_SHORT":
                _record_component_fault("M1_SWITCH", "SHORT")
            elif line == "FAULT:M2_SWITCH_SHORT":
                _record_component_fault("M2_SWITCH", "SHORT")
            elif line == "FAULT:COLLISION_SWITCH_ABSENT":
                _record_component_fault("COLLISION_SWITCH", "ABSENT")
            elif line == "FAULT:COLLISION_SWITCH_SHORT":
                _record_component_fault("COLLISION_SWITCH", "SHORT")

            # ---- PROX FAILED TO DETECT (switch caught it instead) ----
            elif line == "FAULT:PROX1_REPLACE":
                prox1_fault_event.set()
            elif line == "FAULT:PROX2_REPLACE":
                prox2_fault_event.set()

            # ---- legacy generic switch-wire line ----
            elif line == "FAULT:M1_SWITCH_WIRE":
                m1_wire_fault_event.set()
            elif line == "FAULT:M2_SWITCH_WIRE":
                m2_wire_fault_event.set()

            # ---- on-demand M2 home-switch / prox-2 status replies ----
            # (used only by the startup "already at home" check)
            elif line == "HOME2:AT_HOME":
                hstatus2_value["v"] = "AT_HOME"
                hstatus2_result_event.set()
            elif line == "HOME2:AWAY":
                hstatus2_value["v"] = "AWAY"
                hstatus2_result_event.set()
            elif line == "HOME2:FAULT":
                hstatus2_value["v"] = "FAULT"
                hstatus2_result_event.set()
            elif line == "PROX2:TRIGGERED":
                pstatus2_value["v"] = "TRIGGERED"
                pstatus2_result_event.set()
            elif line == "PROX2:CLEAR":
                pstatus2_value["v"] = "CLEAR"
                pstatus2_result_event.set()

            # ---- on-demand collision-prox (A0) status reply ----
            # (used only by the startup "obstruction already present" check)
            elif line == "PROXC:TRIGGERED":
                pstatusC_value["v"] = "TRIGGERED"
                pstatusC_result_event.set()
            elif line == "PROXC:CLEAR":
                pstatusC_value["v"] = "CLEAR"
                pstatusC_result_event.set()

        except serial.SerialException as e:
            if shutdown_event.is_set():
                return

            print(f"[serial_reader] SerialException: {e}")
            print(f"[serial_reader] Attempting reconnect (up to {MAX_RETRIES} tries)...")

            reconnected = False
            for attempt in range(1, MAX_RETRIES + 1):
                if shutdown_event.is_set():
                    return
                time.sleep(RETRY_DELAY)
                try:
                    # FIX-8: re-scan for the Arduino port — it may re-enumerate
                    # to a different /dev/ttyACMn after a disconnect/reconnect.
                    new_port = find_arduino() or SERIAL_PORT
                    if new_port != SERIAL_PORT:
                        print(f"[serial_reader] Port re-enumerated: {SERIAL_PORT} → {new_port}")

                    with serial_lock:
                        try:
                            if arduino.is_open:
                                arduino.close()
                        except Exception:
                            pass
                        time.sleep(0.3)
                        arduino = serial.Serial(
                            new_port, 115200,
                            timeout=2,
                            write_timeout=1.0,
                        )
                        arduino.reset_input_buffer()

                    SERIAL_PORT = new_port
                    print(f"[serial_reader] Reconnected on {new_port}, attempt {attempt}.")
                    reconnected = True
                    break
                except Exception as re_err:
                    print(f"[serial_reader] Reconnect attempt {attempt}/{MAX_RETRIES} failed: {re_err}")

            if not reconnected:
                print("[serial_reader] All reconnect attempts exhausted. Marking serial dead.")
                serial_dead_event.set()
                return

            # Reconnected at the OS level, but opening the port toggles DTR
            # and resets the board, so every piece of application state is
            # now stale — including the limit-switch self-test result.
            print("[serial_reader] Reconnected — Arduino likely reset. "
                  "Clearing handshake state; re-handshake required.")
            arduino_ready_event.clear()
            switch_status_received_event.clear()
            collision_status_received_event.clear()
            selftest_done_event.clear()
            selftest_pass_event.clear()
            selftest_fail_event.clear()
            reconnect_pending_event.set()

        except TypeError as e:
            if shutdown_event.is_set():
                return
            print(f"[serial_reader] TypeError (None from readline — transient): {e}")
            time.sleep(0.1)

        except Exception as e:
            if shutdown_event.is_set():
                return
            print(f"[serial_reader] Unexpected fatal error: {e}")
            serial_dead_event.set()
            return


_serial_reader_thread = threading.Thread(target=serial_reader, daemon=True)
_serial_reader_thread.start()


# ======================================================================
# GUARDED SEND — rate-limited inside the lock, never raises
#
# FIX-5: The rate-limiter sleep is now performed INSIDE serial_lock so
#         two concurrent callers cannot interleave their writes in the
#         gap between sleep() and write().  The sleep is still bounded
#         to _MIN_WRITE_GAP so the lock is not held for long.
# ======================================================================
def send_error(value: int, label: str = ""):
    global arduino, _last_write_time

    data = f"F:{value}\n"
    tag  = f"[{label}] " if label else ""
    try:
        with serial_lock:
            if not arduino.is_open:
                print(f"{tag}Port closed — skipping send of F:{value}")
                return

            # FIX-5: enforce rate limit INSIDE the lock so no two callers
            # can simultaneously pass the gap check and both proceed.
            now = time.monotonic()
            gap = now - _last_write_time
            if gap < _MIN_WRITE_GAP:
                time.sleep(_MIN_WRITE_GAP - gap)

            ret = arduino.write(data.encode())
            _last_write_time = time.monotonic()

        if ret == len(data):
            print(f"{tag}Sent F:{value} to Arduino")
        else:
            print(f"{tag}Partial/failed write for F:{value} ({ret}/{len(data)} bytes)")

    except serial.SerialTimeoutException:
        print(f"{tag}WriteTimeout for F:{value} — Arduino may be busy")
    except serial.SerialException as e:
        print(f"{tag}SerialException during send F:{value}: {e}")
    except Exception as e:
        print(f"{tag}Unexpected error during send F:{value}: {e}")


# ======================================================================
# SAFE SERIAL WRITE HELPER  (used by startup checks, self-test & watchdog)
#
# FIX-2 / FIX-3 / FIX-4: All raw arduino.write() calls that previously
# bypassed serial_lock are replaced with this helper, which:
#   • acquires serial_lock
#   • checks is_open before writing
#   • honours the same rate limit as send_error()
# ======================================================================
def _locked_write(data_bytes: bytes, tag: str = ""):
    """Write raw bytes under serial_lock with is_open guard. Returns True on success."""
    global _last_write_time
    try:
        with serial_lock:
            if not arduino.is_open:
                print(f"[{tag}] Port closed — skipping write")
                return False
            now = time.monotonic()
            gap = now - _last_write_time
            if gap < _MIN_WRITE_GAP:
                time.sleep(_MIN_WRITE_GAP - gap)
            arduino.write(data_bytes)
            _last_write_time = time.monotonic()
        return True
    except serial.SerialTimeoutException:
        print(f"[{tag}] WriteTimeout")
        return False
    except serial.SerialException as e:
        print(f"[{tag}] SerialException: {e}")
        return False
    except Exception as e:
        print(f"[{tag}] Unexpected write error: {e}")
        return False


# ======================================================================
# SAFE SHUTDOWN
#
# FIX-6: shutdown() now signals shutdown_event and waits for
#         serial_reader to exit BEFORE closing the port.  This prevents
#         the reader from calling readline() on a fd that we are in the
#         process of closing, which can raise a confusing OSError and
#         also masks the intended clean-exit message.
# ======================================================================
def shutdown(reason: str = ""):
    global arduino

    if reason:
        print(reason)

    shutdown_event.set()

    # FIX-6: wait for reader to notice shutdown_event and exit
    # (it will break out of readline() at the next timeout, ≤2 s)
    _serial_reader_thread.join(timeout=3.0)
    if _serial_reader_thread.is_alive():
        print("[shutdown] WARNING: serial_reader thread did not exit in time.")
    else:
        print("[shutdown] serial_reader thread exited cleanly.")

    # Now it is safe to write and close — reader is no longer running
    send_error(0, "shutdown")

    try:
        with serial_lock:
            if arduino.is_open:
                arduino.close()
                print("[shutdown] Serial port closed.")
    except Exception as e:
        print(f"[shutdown] Error closing serial port: {e}")

    devnull    = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    os.dup2(devnull, 2)
    cap.release()
    os.dup2(old_stderr, 2)
    os.close(devnull)
    os.close(old_stderr)

    cv2.destroyAllWindows()
    sys.exit(0)


# ======================================================================
# FULL-SCREEN TEXT HELPERS
# ======================================================================
def _blank_fullscreen():
    return np.zeros((screen_h, screen_w, 3), dtype=np.uint8)


def _centered_text(frame, text, y, scale, color, thickness=2):
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, _), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max(20, (screen_w - tw) // 2)
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def _hold_screen(frame, seconds: float):
    _force_fullscreen(frame)
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cv2.waitKey(50) & 0xFF == 27:
            break


# ======================================================================
# ALERT HELPERS
# ======================================================================

# ----------------------------------------------------------------------
# LIMIT SWITCH NOT INTERFACED / MALFUNCTIONING  ->  HALT
#
# The only halt-until-replaced condition. Drawn on a blank canvas rather
# than the camera feed, because at startup the camera is irrelevant here
# and may not even be available yet.
#
# failures: list of (component_key, status_key) tuples.
# ----------------------------------------------------------------------
def show_limit_switch_fault_and_exit(failures):
    print("=" * 70)
    print("!!!! LIMIT SWITCH CHECK FAILED — SYSTEM WILL NOT RUN !!!!")
    for comp, status in failures:
        label  = COMPONENT_LABELS.get(comp, comp)
        detail = STATUS_LABELS.get(status, status)
        print(f"  * {label}  ->  {detail}")
    print("!!!! REPLACEMENT REQUIRED. Fit/repair the switch, then restart. !!!!")
    print("=" * 70)

    send_error(0, "limit-switch-fault")

    frame = _blank_fullscreen()

    y = int(screen_h * 0.15)
    _centered_text(frame, "SYSTEM HALTED", y, 2.0, (0, 0, 255), 4)
    y += int(screen_h * 0.075)
    _centered_text(frame, "LIMIT SWITCH FAULT", y, 1.2, (0, 0, 255), 3)

    y += int(screen_h * 0.05)
    cv2.line(frame, (int(screen_w * 0.1), y), (int(screen_w * 0.9), y),
             (0, 0, 180), 2)

    y += int(screen_h * 0.08)
    for comp, status in failures:
        label  = COMPONENT_LABELS.get(comp, comp)
        detail = STATUS_LABELS.get(status, status)
        _centered_text(frame, label, y, 1.0, (0, 255, 255), 2)
        y += int(screen_h * 0.045)
        _centered_text(frame, detail, y, 0.7, (255, 255, 255), 2)
        y += int(screen_h * 0.07)

    y = int(screen_h * 0.84)
    _centered_text(frame, "REPLACEMENT REQUIRED", y, 1.1, (0, 165, 255), 3)
    _centered_text(frame, "Fit or repair the switch above, then restart the system.",
                   y + int(screen_h * 0.06), 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 8.0)

    shutdown("!!!! Terminating — home limit switch not interfaced or malfunctioning !!!!")


# ----------------------------------------------------------------------
# PROX SENSOR DID NOT DETECT  ->  "REPLACEMENT REQUIRED"
#
# Reached when the home limit switch caught the lever but the paired
# prox never fired. That means the prox is not interfaced, dead,
# misaligned, or wired with the wrong polarity. The switch did its job,
# so the machine was never in danger — but the primary sensor is gone
# and must be replaced, so this run ends here with the message on screen.
# ----------------------------------------------------------------------
def show_prox_replacement_and_exit(motor_num: int, limit_triggered: bool):
    axis = "CHEST" if motor_num == 1 else "EYES"

    print("=" * 70)
    print(f"!!!! PROX {motor_num} NOT DETECTED — REPLACEMENT REQUIRED !!!!")
    print(f"!!!! M{motor_num} ({axis}) home limit switch caught the lever instead. !!!!")
    if limit_triggered:
        print(f"!!!! M{motor_num} HOME LIMIT TRIGGERED — WRONG INDICES !!!!")
    print("=" * 70)

    send_error(0, f"prox{motor_num}-not-detected")

    frame = _blank_fullscreen()

    y = int(screen_h * 0.17)
    _centered_text(frame, f"PROX {motor_num} NOT DETECTED", y, 1.9, (0, 0, 255), 4)
    y += int(screen_h * 0.085)
    _centered_text(frame, "REPLACEMENT REQUIRED", y, 1.4, (0, 165, 255), 3)

    y += int(screen_h * 0.06)
    cv2.line(frame, (int(screen_w * 0.1), y), (int(screen_w * 0.9), y),
             (0, 0, 180), 2)

    y += int(screen_h * 0.09)
    _centered_text(frame, f"M{motor_num} / {axis} PROXIMITY SENSOR "
                          f"(pin A{motor_num})",
                   y, 1.0, (0, 255, 255), 2)
    y += int(screen_h * 0.05)
    _centered_text(frame, "did not detect the metal lever.",
                   y, 0.8, (255, 255, 255), 2)
    y += int(screen_h * 0.045)
    _centered_text(frame, f"The M{motor_num} home limit switch stopped the axis instead.",
                   y, 0.8, (255, 255, 255), 2)

    if limit_triggered:
        y += int(screen_h * 0.075)
        _centered_text(frame, f"M{motor_num} HOME LIMIT TRIGGERED — WRONG INDICES",
                       y, 0.85, (0, 255, 255), 2)

    y = int(screen_h * 0.87)
    _centered_text(frame, "Replace the proximity sensor, then restart the system.",
                   y, 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 8.0)

    shutdown(f"!!!! Terminating — prox {motor_num} not detected, replacement required !!!!")


def show_emergency_and_exit(source: str = ""):
    if source:
        print(f"!!!! {source} — stopping system !!!!")
    send_error(0, "emergency")

    frame     = _blank_fullscreen()
    font      = cv2.FONT_HERSHEY_SIMPLEX
    scale1, scale2, thickness = 1.8, 1.3, 3
    line1, line2 = "Emergency Switch is Pressed", "Please Wait For Reboot"

    (tw1, th1), _ = cv2.getTextSize(line1, font, scale1, thickness)
    (tw2, th2), _ = cv2.getTextSize(line2, font, scale2, thickness)
    gap  = 40
    y1   = (screen_h - th1 - gap - th2) // 2 + th1
    y2   = y1 + gap + th2
    cv2.putText(frame, line1, ((screen_w - tw1) // 2, y1), font, scale1, (0,   0, 255), thickness, cv2.LINE_AA)
    cv2.putText(frame, line2, ((screen_w - tw2) // 2, y2), font, scale2, (255, 255, 255), thickness, cv2.LINE_AA)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after emergency stop !!!!")


def show_collision_and_exit(source: str = ""):
    print(f"!!!! {source or 'COLLISION DETECTED'} — stopping system !!!!")
    send_error(0, "collision-handler")

    if COLLISION_IMG is not None:
        frame = cv2.resize(COLLISION_IMG, (screen_w, screen_h))
    else:
        frame = _blank_fullscreen()
        frame[:] = (0, 0, 180)
        cv2.putText(frame, "!! COLLISION OCCURRED !!",
                    (screen_w // 2 - 260, screen_h // 2 - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)
        cv2.putText(frame, "Check limit switch — terminating...",
                    (screen_w // 2 - 270, screen_h // 2 + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after collision !!!!")


# ----------------------------------------------------------------------
# EARLY COLLISION WARNING (A0 prox)  ->  HALT
#
# Same reasoning as chest_alignment.py: firmware's EARLY:COLLISION is
# non-latching, so without this handler the motors get soft-stopped for
# an instant and the very next F: command resumes driving with no
# operator ever finding out. Halting is the safe default here.
# ----------------------------------------------------------------------
def show_collision_prox_and_exit(source: str = ""):
    print(f"!!!! {source or 'EARLY COLLISION (PROX A0) DETECTED'} "
          "— stopping system !!!!")
    send_error(0, "collision-prox-early")

    if COLLISION_IMG is not None:
        frame = cv2.resize(COLLISION_IMG, (screen_w, screen_h))
    else:
        frame = _blank_fullscreen()
        frame[:] = (0, 90, 180)

    cv2.putText(frame, "!! EARLY COLLISION WARNING !!",
                (screen_w // 2 - 300, screen_h // 2 - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 165, 255), 3)
    cv2.putText(frame, "Obstruction detected by proximity sensor (A0) — terminating...",
                (screen_w // 2 - 330, screen_h // 2 + 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after early collision warning (A0 prox) !!!!")


def show_wrong_indices_and_exit(motor_num: int = 2, early: bool = False):
    """Home limit reached (either now, or already true at startup) with
    the prox sensor working correctly (either the prox caught it early,
    or both fired). A prox that FAILED to fire is handled by
    show_prox_replacement_and_exit() instead, which is checked first."""
    tag = "EARLY " if early else ""
    print(f"!!!! {tag}M{motor_num} HOME LIMIT TRIGGERED — WRONG INDICES !!!!")
    if early:
        print(f"!!!! Caught by Proximity Sensor {motor_num} — "
              "axis stopped before mechanical contact !!!!")
    send_error(0, f"m{motor_num}-home-limit" + ("-early" if early else ""))

    # FIX-9: guard cap usage — if shutdown is already in progress the
    # camera may have been released; skip the live-camera loop in that case.
    if shutdown_event.is_set():
        shutdown(f"!!!! Terminating after wrong indices (M{motor_num}, no camera) !!!!")
        return

    start = time.time()
    while time.time() - start < 5:
        if shutdown_event.is_set():
            break
        cap.grab()
        ret, frame = cap.retrieve()
        if not ret or frame is None:
            print("[show_wrong_indices_and_exit] WARNING: could not read camera frame.")
            break
        h, w, _ = frame.shape
        overlay  = frame.copy()
        cv2.rectangle(overlay, (0, h // 2 - 60), (w, h // 2 + 60), (0, 0, 200), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        header = f"!! {'EARLY ' if early else ''}WRONG INDICES !!"
        cv2.putText(frame, header,
                    (w // 2 - 220, h // 2 - 15), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
        sub = f"M{motor_num} HOME LIMIT TRIGGERED" + (" (PROX)" if early else "")
        cv2.putText(frame, sub,
                    (w // 2 - 215, h // 2 + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
        cv2.putText(frame, "Terminating...",
                    (w // 2 - 110, h // 2 + 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.imshow(WIN, make_combined(frame))
        _apply_win_size()
        if cv2.waitKey(1) & 0xFF == 27:
            break

    shutdown(f"!!!! Terminating after {'early ' if early else ''}"
             f"wrong indices (M{motor_num}) !!!!")


# ======================================================================
# HARDWARE FAULT SENTINEL — call from every wait/poll loop.
#
# Order matters and is deliberate:
#   1. Limit switch absent/shorted  -> halt, name the switch, exit.
#   2. Prox failed to detect        -> "PROX n NOT DETECTED,
#                                       REPLACEMENT REQUIRED", exit.
#
# Checking the prox message BEFORE the plain LIMIT:Mn_HOME handler also
# removes a race: the firmware sends FAULT:PROXn_REPLACE immediately
# before LIMIT:Mn_HOME, so whichever the main loop happened to observe
# first would otherwise decide the message. Now both paths lead to the
# prox message when the prox failed.
# ======================================================================
def check_hardware_faults():
    with component_fault_lock:
        failures = sorted(component_faults.items())
        if failures:
            component_faults.clear()
    if failures:
        # The named failure supersedes the generic legacy wire line.
        m1_wire_fault_event.clear()
        m2_wire_fault_event.clear()
        show_limit_switch_fault_and_exit(failures)

    # Legacy generic line with no specific ABSENT/SHORT companion.
    if m1_wire_fault_event.is_set():
        m1_wire_fault_event.clear()
        show_limit_switch_fault_and_exit([("M1_SWITCH", "SHORT")])
    if m2_wire_fault_event.is_set():
        m2_wire_fault_event.clear()
        show_limit_switch_fault_and_exit([("M2_SWITCH", "SHORT")])

    if prox1_fault_event.is_set():
        prox1_fault_event.clear()
        limit_hit = m1_home_event.is_set()
        m1_home_event.clear()
        show_prox_replacement_and_exit(1, limit_hit)

    if prox2_fault_event.is_set():
        prox2_fault_event.clear()
        limit_hit = m2_home_event.is_set()
        m2_home_event.clear()
        show_prox_replacement_and_exit(2, limit_hit)


# ======================================================================
# STARTUP LIMIT-SWITCH GATE
#
# Sends SELFTEST? and waits for the report. Both home limit switches
# must come back OK. Anything else — including no reply at all — names
# the switch on screen and terminates BEFORE the camera loop or any
# motion command is reached.
# ======================================================================
def run_limit_switch_selftest(context: str = "STARTUP"):
    REPLY_TIMEOUT = 5.0

    print(f"[{context}] Checking home limit switches ...")

    selftest_done_event.clear()
    selftest_pass_event.clear()
    selftest_fail_event.clear()
    with selftest_lock:
        selftest_results.clear()
    with component_fault_lock:
        component_faults.clear()

    if not _locked_write(b"SELFTEST?\n", f"{context.lower()}-SELFTEST?"):
        shutdown(f"[{context}] Failed to send SELFTEST? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not selftest_done_event.is_set():
        if serial_dead_event.is_set():
            shutdown(f"[{context}] Serial lost while waiting for self-test reply.")
        if time.time() > deadline:
            show_limit_switch_fault_and_exit([("CONTROLLER", "NO_REPLY")])
        time.sleep(0.02)

    with selftest_lock:
        results = dict(selftest_results)

    failures = []
    for comp in REQUIRED_COMPONENTS:
        status = results.get(comp)
        if status is None:
            failures.append((comp, "NO_REPLY"))
        elif status != "OK":
            failures.append((comp, status))

    if failures:
        show_limit_switch_fault_and_exit(failures)

    if selftest_fail_event.is_set() or not selftest_pass_event.is_set():
        show_limit_switch_fault_and_exit([("CONTROLLER", "SELFTEST_FAIL")])

    print(f"[{context}] Limit switches OK: "
          + ", ".join(f"{k}={v}" for k, v in sorted(results.items())))


# ======================================================================
# ======================================================================
# STARTUP collision-prox (A0) CHECK
#
# Mirrors check_m2_home_at_startup() below, applied to the collision
# prox instead of the home switches. Sends PSTATUSC? and, if it's
# already TRIGGERED, treats it exactly like a live collision (same
# screen, same shutdown) rather than letting alignment start with an
# obstruction already sitting in the collision zone.
# ======================================================================
def check_collision_prox_at_startup(context: str = "STARTUP"):
    REPLY_TIMEOUT = 3.0

    print(f"[{context}] Checking collision prox (A0) state before starting...")

    pstatusC_result_event.clear()
    pstatusC_value["v"] = None
    if not _locked_write(b"PSTATUSC?\n", f"{context.lower()}-pstatusC"):
        shutdown(f"[{context}] Failed to send PSTATUSC? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not pstatusC_result_event.is_set():
        if serial_dead_event.is_set():
            shutdown(f"[{context}] Serial lost while waiting for PSTATUSC? reply.")
        if time.time() > deadline:
            shutdown(f"[{context}] No reply to PSTATUSC? — terminating.")
        time.sleep(0.02)

    print(f"[{context}] Collision prox (A0) = {pstatusC_value['v']}")

    if pstatusC_value["v"] == "TRIGGERED":
        show_collision_and_exit(f"{context}: collision prox (A0) already "
                                 "triggered — obstruction present")


# ======================================================================
# STARTUP "ALREADY AT HOME" CHECK  (M2 / EYES)
#
# Runs once, right before the camera loop is entered. Queries the
# firmware directly for:
#   - the M2 home limit switch state  (HSTATUS2? -> HOME2:AT_HOME/AWAY/FAULT)
#   - prox sensor 2's raw state       (PSTATUS2? -> PROX2:TRIGGERED/CLEAR)
#
# If EITHER is already triggered, the eyes axis is already sitting at
# (or past) the home position, which is the same "wrong indices"
# condition handled mid-run — so it's reported and the run ends here
# rather than starting an alignment pass from the wrong starting point.
#
# FAULT on HSTATUS2? would mean the switch went bad in the instant
# between the self-test passing and this query — treated the same as
# any other switch fault (halt, name it, wait for replacement).
# ======================================================================
def check_m2_home_at_startup():
    REPLY_TIMEOUT = 3.0

    print("[STARTUP] Checking M2 home switch / prox-2 state before starting...")

    hstatus2_result_event.clear()
    hstatus2_value["v"] = None
    if not _locked_write(b"HSTATUS2?\n", "startup-hstatus2"):
        shutdown("[STARTUP] Failed to send HSTATUS2? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not hstatus2_result_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for HSTATUS2? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to HSTATUS2? — terminating.")
        time.sleep(0.02)
    home2_state = hstatus2_value["v"]

    pstatus2_result_event.clear()
    pstatus2_value["v"] = None
    if not _locked_write(b"PSTATUS2?\n", "startup-pstatus2"):
        shutdown("[STARTUP] Failed to send PSTATUS2? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not pstatus2_result_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for PSTATUS2? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to PSTATUS2? — terminating.")
        time.sleep(0.02)
    prox2_state = pstatus2_value["v"]

    print(f"[STARTUP] M2 home switch = {home2_state}, Prox2 = {prox2_state}")

    if home2_state == "FAULT":
        show_limit_switch_fault_and_exit([("M2_SWITCH", "SHORT")])

    at_home_switch = (home2_state == "AT_HOME")
    at_home_prox   = (prox2_state == "TRIGGERED")

    if at_home_switch or at_home_prox:
        print("[STARTUP] M2 is already at the home position — wrong indices.")
        # Prefer flagging it as an "early" (prox) catch only when the
        # switch itself isn't ALSO triggered, matching the mid-run logic.
        show_wrong_indices_and_exit(2, early=(at_home_prox and not at_home_switch))


# ======================================================================
# STARTUP CHECKS
# ======================================================================
def check_startup_switch():
    BOOT_TIMEOUT  = 15.0
    REPLY_TIMEOUT =  3.0

    print("[STARTUP] Waiting for Arduino READY ...")
    deadline = time.time() + BOOT_TIMEOUT
    while not arduino_ready_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for READY.")
        if time.time() > deadline:
            shutdown("[STARTUP] Timed out waiting for Arduino READY.")
        time.sleep(0.05)

    # HARDWARE GATE — before anything else moves.
    run_limit_switch_selftest("STARTUP")

    # FIX-2: use _locked_write() instead of bare arduino.write()
    print("[STARTUP] Arduino READY. Sending STATUS? ...")
    if not _locked_write(b"STATUS?\n", "startup-STATUS?"):
        shutdown("[STARTUP] Failed to send STATUS? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not switch_status_received_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for STATUS? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to STATUS? — terminating.")
        time.sleep(0.02)

    if switch_event.is_set():
        print("[STARTUP] Pin 2 is PRESSED at startup.")
        show_emergency_and_exit("STARTUP: switch pressed at boot")
    else:
        print("[STARTUP] Pin 2 is RELEASED. Continuing.")

    # FIX-3: use _locked_write() instead of bare arduino.write()
    print("[STARTUP] Sending CSTATUS? ...")
    if not _locked_write(b"CSTATUS?\n", "startup-CSTATUS?"):
        shutdown("[STARTUP] Failed to send CSTATUS? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not collision_status_received_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for CSTATUS? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to CSTATUS? — terminating.")
        time.sleep(0.02)

    if collision_event.is_set():
        print("[STARTUP] Pin 3 (collision) is ACTIVE at startup.")
        show_collision_and_exit("STARTUP: collision active at boot")
    else:
        print("[STARTUP] Pin 3 (collision) is CLEAR. Continuing.")

    # Collision-prox (A0) check -- right alongside the collision switch
    # check above, since it's checking the same physical danger zone
    # through the other sensor.
    check_collision_prox_at_startup("STARTUP")

    # Anything the firmware reported asynchronously during boot.
    check_hardware_faults()

    # NEW: M2 (eyes) home switch / prox-2 already-at-home check, right
    # before the camera loop is entered.
    check_m2_home_at_startup()


check_startup_switch()


# ======================================================================
# POST-RECONNECT RE-HANDSHAKE
#
# A mid-run reconnect resets the Arduino (opening the port toggles DTR),
# so READY, the switch/collision status and the limit-switch self-test
# must all be redone before the main loop trusts anything or resumes
# sending motion commands.
# ======================================================================
def wait_for_post_reconnect_ready():
    BOOT_TIMEOUT  = 15.0
    REPLY_TIMEOUT =  3.0

    print("[RECONNECT] Re-handshake required — waiting for Arduino READY ...")
    deadline = time.time() + BOOT_TIMEOUT
    while not arduino_ready_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[RECONNECT] Serial lost while waiting for post-reconnect READY.")
        if time.time() > deadline:
            shutdown("[RECONNECT] Timed out waiting for post-reconnect READY.")
        time.sleep(0.05)

    # Re-verify the switches: one unplugged during the outage must not
    # slip through.
    run_limit_switch_selftest("RECONNECT")

    print("[RECONNECT] Arduino READY. Re-sending STATUS? ...")
    switch_status_received_event.clear()
    if not _locked_write(b"STATUS?\n", "reconnect-STATUS?"):
        shutdown("[RECONNECT] Failed to send STATUS? after reconnect — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not switch_status_received_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[RECONNECT] Serial lost while waiting for STATUS? reply.")
        if time.time() > deadline:
            shutdown("[RECONNECT] No reply to STATUS? after reconnect — terminating.")
        time.sleep(0.02)

    if switch_event.is_set():
        show_emergency_and_exit("RECONNECT: switch found pressed after re-handshake")

    print("[RECONNECT] Re-sending CSTATUS? ...")
    collision_status_received_event.clear()
    if not _locked_write(b"CSTATUS?\n", "reconnect-CSTATUS?"):
        shutdown("[RECONNECT] Failed to send CSTATUS? after reconnect — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not collision_status_received_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[RECONNECT] Serial lost while waiting for CSTATUS? reply.")
        if time.time() > deadline:
            shutdown("[RECONNECT] No reply to CSTATUS? after reconnect — terminating.")
        time.sleep(0.02)

    if collision_event.is_set():
        show_collision_and_exit("RECONNECT: collision found active after re-handshake")

    # Re-check the collision prox too, same reasoning as the switch checks
    # above: an obstruction could have appeared while the port was down.
    check_collision_prox_at_startup("RECONNECT")

    check_hardware_faults()

    # Firmware reset during the outage, so re-check the "already at home"
    # condition too — a lever that moved onto the switch/prox while the
    # port was down must not slip through.
    check_m2_home_at_startup()

    reconnect_pending_event.clear()
    print("[RECONNECT] Re-handshake complete — resuming normal operation.")


# ======================================================================
# WATCHDOG
# ======================================================================
WATCHDOG_INTERVAL      = 5.0
WATCHDOG_REPLY_TIMEOUT = 3.0

def watchdog():
    missed    = 0
    MAX_MISSED = 2

    while not shutdown_event.is_set() and not serial_dead_event.is_set():
        time.sleep(WATCHDOG_INTERVAL)
        if shutdown_event.is_set() or serial_dead_event.is_set():
            break

        _watchdog_reply_received.clear()

        # FIX-4: use _locked_write() which includes is_open guard
        sent = _locked_write(b"STATUS?\n", "watchdog")
        if not sent:
            missed += 1
            print(f"[watchdog] Ping send failed (missed={missed}/{MAX_MISSED})")
            if missed >= MAX_MISSED:
                print("[watchdog] Too many ping failures — marking serial dead.")
                serial_dead_event.set()
            continue

        got_reply = _watchdog_reply_received.wait(timeout=WATCHDOG_REPLY_TIMEOUT)
        if got_reply:
            missed = 0
        else:
            missed += 1
            print(f"[watchdog] No reply to STATUS? ping (missed={missed}/{MAX_MISSED})")
            if missed >= MAX_MISSED:
                print("[watchdog] Arduino appears silent — marking serial dead.")
                serial_dead_event.set()

threading.Thread(target=watchdog, daemon=True).start()


# ======== Main loop variables ========
error_eye      = 0
last_sent_time = 0
send_interval  = 0.03
image_captured = False

# ======================================================================
# MAIN LOOP
# ======================================================================
while True:

    if serial_dead_event.is_set():
        shutdown("!!!! Serial connection lost — terminating !!!!")

    # A mid-run reconnect leaves every piece of application state stale,
    # including the limit-switch self-test. Block here until a fresh
    # handshake completes before trusting anything below.
    if reconnect_pending_event.is_set():
        wait_for_post_reconnect_ready()

    if switch_event.is_set():
        show_emergency_and_exit("SWITCH PRESSED mid-execution")

    if collision_event.is_set():
        show_collision_and_exit("COLLISION mid-execution")

    if collision_prox_early_event.is_set():
        collision_prox_early_event.clear()
        show_collision_prox_and_exit("EARLY COLLISION mid-execution")

    # Limit-switch faults and prox-not-detected are checked BEFORE the
    # plain home-limit handlers, so the operator gets the actionable
    # message rather than a bare "wrong indices".
    check_hardware_faults()

    if m2_home_early_event.is_set():
        m2_home_early_event.clear()
        show_wrong_indices_and_exit(2, early=True)

    if m1_home_early_event.is_set():
        m1_home_early_event.clear()
        show_wrong_indices_and_exit(1, early=True)

    if m2_home_event.is_set():
        show_wrong_indices_and_exit(2)

    if m1_home_event.is_set():
        show_wrong_indices_and_exit(1)

    cap.grab()
    success, img = cap.retrieve()
    if not success or img is None:
        print("--------Failed to grab frame----------")
        shutdown("Frame grab failed — terminating.")

    img, faces = detector.findFaceMesh(img, draw=False)
    h1, w1, _ = img.shape
    center_y1  = h1 // 2

    cv2.line(img, (0, center_y1), (w1, center_y1), (255, 0, 255), 2)

    if faces:
        face           = faces[0]
        mid_point_eyes = face[168]
        error_eye      = center_y1 - mid_point_eyes[1]

        cv2.circle(img, mid_point_eyes, 4, (0, 255, 0), -1)
        x = w1 // 2
        cv2.circle(img, (x, center_y1), 5, (125, 249, 255), -1)
        cv2.line(img, mid_point_eyes, (x, center_y1), (255, 192, 203), 2)

        cv2.rectangle(img, (10, 10), (200, 60), (0, 0, 0), -1)
        cv2.putText(img, f"Moving : {error_eye}", (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if -8 <= error_eye <= 8 and not image_captured:
           # timestamp = time.strftime("%Y%m%d_%H%M%S")
           # filename  = f"_EYE_{timestamp}.jpg"
            filename=f"Alined_EYE_.jpg"
            cv2.putText(img, "ALIGNED", (w1 - 130, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imwrite(filename, img)
            print(f"-----Image captured: '{filename}'-----")
            image_captured = True
        else:
            cv2.putText(img, "NOT ALIGNED", (w1 - 220, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    else:
        error_eye = 0

    if time.time() - last_sent_time > send_interval:
        send_error(error_eye)
        print(f"Sent -> Eye err: {error_eye:+4d}")
        last_sent_time = time.time()

    cv2.imshow(WIN, make_combined(img))
    _apply_win_size()

    if image_captured:
        # send_error() already rate-limited; one call here is fine
        send_error(0, "post-capture")
        print("*****Alignment achieved. Displaying for 4 seconds*****")
        captured_display = cv2.imread(filename)
        display_start    = time.time()

        # FIX-7: track last_display_send so the 4 s display loop cannot
        # flood the Arduino with send_error(0) on every frame (~15 fps).
        last_display_send = 0.0

        while time.time() - display_start < 4:

            if serial_dead_event.is_set():
                shutdown("!!!! Serial connection lost during display !!!!")

            if switch_event.is_set():
                show_emergency_and_exit("SWITCH PRESSED during display")

            if collision_event.is_set():
                show_collision_and_exit("COLLISION during display")

            if collision_prox_early_event.is_set():
                collision_prox_early_event.clear()
                show_collision_prox_and_exit("EARLY COLLISION during display")

            # Keep enforcing limit-switch faults and prox-not-detected
            # during the post-capture display window.
            check_hardware_faults()

            if m2_home_early_event.is_set():
                m2_home_early_event.clear()
                show_wrong_indices_and_exit(2, early=True)

            if m1_home_early_event.is_set():
                m1_home_early_event.clear()
                show_wrong_indices_and_exit(1, early=True)

            if m2_home_event.is_set():
                show_wrong_indices_and_exit(2)

            if m1_home_event.is_set():
                show_wrong_indices_and_exit(1)

            cap.grab()
            ret, frame = cap.retrieve()
            if not ret or frame is None:
                print("*****Failed to grab frame during display*****")
                break

            cv2.line(frame, (0, center_y1), (w1, center_y1), (0, 0, 255), 2)
            cv2.putText(frame, "ALIGNED", (w1 - 130, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            cap_panel  = cv2.resize(captured_display, (panel_w, panel_h),
                                    interpolation=cv2.INTER_LINEAR)
            live_panel = cv2.resize(frame, (panel_w, panel_h),
                                    interpolation=cv2.INTER_LINEAR)
            cv2.imshow(WIN, cv2.hconcat([cap_panel, live_panel]))

            # FIX-7: only send F:0 at the normal send_interval cadence,
            # not every frame.  send_error() is also guarded internally
            # but this avoids pointless lock contention at 15 fps.
            now = time.time()
            if now - last_display_send > send_interval:
                send_error(0, "display-loop")
                last_display_send = now

            if cv2.waitKey(1) & 0xFF == 27:
                break

        print("*****Exiting display loop*****")
        break

    if cv2.waitKey(1) & 0xFF == 27:
        break

# ======== Cleanup (normal exit path) ========
shutdown("Normal exit.")
