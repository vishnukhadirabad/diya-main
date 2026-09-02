#_____CHEST_ALIGNMENT______________________
#-----robust for serial communication-------
#-----No abrupt loss of serial communication--
#
# HARDWARE POLICY (this version):
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

import cv2
import mediapipe as mp
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

# ======== MediaPipe Pose Setup ========
mp_pose = mp.solutions.pose
pose    = mp_pose.Pose()

# ======================================================================
# HARDWARE GATE CONFIG
#
# Only the home limit switches gate startup. Drop an entry here only if
# that axis genuinely is not populated on the machine.
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
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        hwid = (port.hwid or "").lower()
        if (
            "ttyACM" in port.device
            or "arduino" in desc
            or "2341" in hwid
        ):
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

# ======== Arduino Setup ========
arduino = serial.Serial(
    SERIAL_PORT,
    115200,
    timeout=2,
    write_timeout=1.0,
)
arduino.dtr = False
time.sleep(0.1)
arduino.dtr = True
arduino.reset_input_buffer()
time.sleep(0.1)

# ======== Camera Setup ========
_cam_src      = get_camera_index("arducam")
capture_chest = cv2.VideoCapture(_cam_src)
capture_chest.set(cv2.CAP_PROP_BUFFERSIZE, 1)

# ======== Shared Events ========
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
m1_home_early_event              = threading.Event()
m2_home_early_event              = threading.Event()

# ------------------------------------------------------------------
# EARLY collision warning from the A0 collision prox — fires from the
# firmware's normal loop() path (the one this alignment script actually
# runs through, since it only ever sends E:/F: PID commands, never
# home/shoot). Unlike the mechanical collision switch, this is
# non-latching on the firmware side: EARLY:COLLISION soft-stops both
# motors for that instant only, and nothing in firmware prevents the
# very next E: command from immediately driving them again. Without a
# Python-side handler, this line was previously dropped silently — the
# firmware stopped the motors for a moment and the operator never found
# out. Treated the same as a mechanical collision here: halt and require
# a restart, rather than letting PID resume driving toward an object
# that was just detected close to the sensor.
# ------------------------------------------------------------------
collision_prox_early_event       = threading.Event()

# ------------------------------------------------------------------
# PROX FAILURE (not fatal to the machine, fatal to this run):
#   Set when the limit switch caught the lever but its paired prox
#   never fired — i.e. the prox is not interfaced, dead, misaligned or
#   wired with the wrong polarity. The screen names it and asks for
#   replacement.
# ------------------------------------------------------------------
prox1_fault_event   = threading.Event()
prox2_fault_event   = threading.Event()

# Legacy generic switch-wire line, kept because the other scripts in the
# pipeline still emit/consume it.
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

reconnect_pending_event          = threading.Event()

# ------------------------------------------------------------------
# STARTUP "already at home" check (M1 / chest) — home limit switch
# reply (HSTATUS1?) and prox-1 reply (PSTATUS1?). Queried once, right
# before the camera loop is entered.
# ------------------------------------------------------------------
hstatus1_result_event = threading.Event()
pstatus1_result_event = threading.Event()
hstatus1_value = {"v": None}   # "AT_HOME" / "AWAY" / "FAULT"
pstatus1_value = {"v": None}   # "TRIGGERED" / "CLEAR"

# ------------------------------------------------------------------
# STARTUP collision-prox (A0) check — mirrors the M1 "already at home"
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
           prox1_fault_event, prox2_fault_event,
           m1_wire_fault_event, m2_wire_fault_event,
           m1_home_early_event, m2_home_early_event,
           collision_prox_early_event,
           selftest_done_event, selftest_pass_event, selftest_fail_event,
           hstatus1_result_event, pstatus1_result_event,
           pstatusC_result_event):
    _e.clear()

# ---- write-rate limiter ----
_last_write_time = 0.0
_MIN_WRITE_GAP   = 0.025   # 25 ms hard floor between any two serial writes

# ---- watchdog bookkeeping ----
_watchdog_reply_received = threading.Event()

# ---- fast-disconnect detection ----
_port_lost = threading.Event()

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
    try:
        output = subprocess.check_output("xrandr | grep ' connected'", shell=True).decode()
        match = re.search(r'(\d+)x(\d+)\+', output)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    try:
        output = subprocess.check_output("xdpyinfo | grep dimensions", shell=True).decode()
        match = re.search(r'(\d+)x(\d+)', output)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    try:
        output = subprocess.check_output("wmctrl -d", shell=True).decode()
        match = re.search(r'(\d+)x(\d+)', output)
        if match:
            return int(match.group(1)), int(match.group(2))
    except Exception:
        pass
    print("[Python] Could not detect screen resolution; defaulting to 1920x1080.")
    return 1920, 1080


# ======== Screen & panel dimensions (computed once) ========
screen_w, screen_h = get_screen_resolution()
print(f"Detected screen resolution: {screen_w}x{screen_h}")

panel_w = screen_w // 2
panel_h = screen_h
print(f"Each panel size: {panel_w}x{panel_h}")

# ======== Load & resize reference image once ========
_ref_path = os.path.join(_BASE, "chest_reference_left.png")
_ref_raw  = cv2.imread(_ref_path)
if _ref_raw is None:
    print(f"[STARTUP WARNING] Reference image not found at '{_ref_path}'. "
          "Left panel will be blank.")
    reference_resized = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
else:
    reference_resized = cv2.resize(_ref_raw, (panel_w, panel_h),
                                   interpolation=cv2.INTER_LINEAR)

# ======== Single display window (created once, auto-fills monitor) ========
WIN = "Chest_Check"
cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
_win_sized = False


def _apply_win_size():
    """On Linux the WM ignores resize hints until the window is mapped.
    Call this once after the first cv2.imshow."""
    global _win_sized
    if not _win_sized:
        cv2.moveWindow(WIN, 0, 0)
        cv2.resizeWindow(WIN, screen_w, screen_h)
        _win_sized = True


def make_combined(camera_frame):
    """Resize camera frame to panel size and stitch with reference side-by-side."""
    cam_panel = cv2.resize(camera_frame, (panel_w, panel_h),
                           interpolation=cv2.INTER_LINEAR)
    return cv2.hconcat([reference_resized, cam_panel])


# ======================================================================
# GUARDED RAW SEND
# ======================================================================
def guarded_raw_write(data: bytes, label: str = "") -> bool:
    """Write raw bytes to the serial port safely. Returns True on success.
    Respects the rate limiter and serial_lock; never raises."""
    global _last_write_time

    now = time.monotonic()
    gap = now - _last_write_time
    if gap < _MIN_WRITE_GAP:
        time.sleep(_MIN_WRITE_GAP - gap)

    tag = f"[{label}] " if label else ""
    try:
        with serial_lock:
            if not arduino.is_open:
                print(f"{tag}Port closed — skipping write of {data!r}")
                return False
            ret = arduino.write(data)
        _last_write_time = time.monotonic()
        if ret != len(data):
            print(f"{tag}Partial write for {data!r} ({ret}/{len(data)} bytes)")
        return ret == len(data)
    except serial.SerialTimeoutException:
        print(f"{tag}WriteTimeout sending {data!r} — Arduino may be busy")
        return False
    except serial.SerialException as e:
        print(f"{tag}SerialException sending {data!r}: {e}")
        return False
    except Exception as e:
        print(f"{tag}Unexpected error sending {data!r}: {e}")
        return False


def _record_component_fault(component: str, status: str):
    """Record a limit-switch fault reported by the firmware. Stored in a
    dict so the firmware's 1 Hz repeats of the same fault don't pile up."""
    with component_fault_lock:
        component_faults[component] = status


# ======================================================================
# ROBUST SERIAL READER — reconnects up to MAX_RETRIES times on failure.
# ======================================================================
def serial_reader():
    global arduino
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0

    while True:

        if shutdown_event.is_set():
            print("[serial_reader] Shutdown signalled — exiting thread.")
            return

        try:
            raw = arduino.readline()

            if shutdown_event.is_set():
                print("[serial_reader] Shutdown signalled after readline — exiting thread.")
                return

            if raw is None:
                time.sleep(0.05)
                continue

            if not raw:
                if SERIAL_PORT and not os.path.exists(SERIAL_PORT):
                    print(f"[serial_reader] Device node {SERIAL_PORT} vanished "
                          "— port physically disconnected.")
                    _port_lost.set()
                    raise serial.SerialException(
                        f"Device node {SERIAL_PORT} no longer exists")
                continue

            line = raw.decode('utf-8', errors='ignore').strip()
            if not line:
                continue

            print(f"[Arduino] {line}")

            _watchdog_reply_received.set()

            if line == "READY":
                arduino_ready_event.set()
                reconnect_pending_event.clear()
            elif line == "SWITCH:PRESSED":
                switch_event.set()
                switch_status_received_event.set()
            elif line == "SWITCH:RELEASED":
                switch_event.clear()
                switch_status_received_event.set()
            elif line == "COLLISION:ACTIVE":
                collision_event.set()
                collision_status_received_event.set()
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
                # loop()-level (EARLY:COLLISION) is what actually fires
                # during alignment; EARLY:COLLISION_PROX_A0 is the
                # homing/shoot-loop variant, included for completeness
                # in case this script is ever extended to send those
                # commands too.
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

            # ---- on-demand M1 home-switch / prox-1 status replies ----
            # (used only by the startup "already at home" check)
            elif line == "HOME1:AT_HOME":
                hstatus1_value["v"] = "AT_HOME"
                hstatus1_result_event.set()
            elif line == "HOME1:AWAY":
                hstatus1_value["v"] = "AWAY"
                hstatus1_result_event.set()
            elif line == "HOME1:FAULT":
                hstatus1_value["v"] = "FAULT"
                hstatus1_result_event.set()
            elif line == "PROX1:TRIGGERED":
                pstatus1_value["v"] = "TRIGGERED"
                pstatus1_result_event.set()
            elif line == "PROX1:CLEAR":
                pstatus1_value["v"] = "CLEAR"
                pstatus1_result_event.set()

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
                print("[serial_reader] SerialException during shutdown — exiting thread.")
                return

            print(f"[serial_reader] SerialException: {e}")
            print(f"[serial_reader] Attempting reconnect (up to {MAX_RETRIES} tries)...")

            reconnected = False
            for attempt in range(1, MAX_RETRIES + 1):
                if shutdown_event.is_set():
                    print("[serial_reader] Shutdown during reconnect — exiting thread.")
                    return
                time.sleep(RETRY_DELAY)
                try:
                    with serial_lock:
                        try:
                            if arduino.is_open:
                                arduino.close()
                        except Exception:
                            pass
                        time.sleep(0.3)
                        arduino = serial.Serial(
                            SERIAL_PORT, 115200,
                            timeout=2,
                            write_timeout=1.0,
                        )
                        arduino.reset_input_buffer()
                    print(f"[serial_reader] Reconnected successfully on attempt {attempt}.")
                    reconnected = True
                    break
                except Exception as re_err:
                    print(f"[serial_reader] Reconnect attempt {attempt}/{MAX_RETRIES} failed: {re_err}")

            if not reconnected:
                print("[serial_reader] All reconnect attempts exhausted. Marking serial dead.")
                serial_dead_event.set()
                return

            print("[serial_reader] Reconnected — Arduino likely reset. "
                  "Clearing handshake state; re-handshake required.")
            _port_lost.clear()
            arduino_ready_event.clear()
            switch_status_received_event.clear()
            collision_status_received_event.clear()
            selftest_done_event.clear()
            selftest_pass_event.clear()
            selftest_fail_event.clear()
            reconnect_pending_event.set()

        except TypeError as e:
            if shutdown_event.is_set():
                print("[serial_reader] TypeError during shutdown — exiting thread.")
                return
            print(f"[serial_reader] TypeError (None from readline — transient): {e}")
            time.sleep(0.1)

        except Exception as e:
            if shutdown_event.is_set():
                print("[serial_reader] Exception during shutdown — exiting thread.")
                return
            print(f"[serial_reader] Unexpected fatal error: {e}")
            serial_dead_event.set()
            return


_serial_reader_thread = threading.Thread(target=serial_reader, daemon=True)
_serial_reader_thread.start()


# ======================================================================
# GUARDED SEND
# ======================================================================
def send_error(value: int, label: str = ""):
    data = f"E:{value}\n"
    tag  = label if label else f"E:{value}"
    ok = guarded_raw_write(data.encode(), tag)
    if ok:
        print(f"[{tag}] Sent E:{value} to Arduino")


# ======================================================================
# SAFE SHUTDOWN
# ======================================================================
def shutdown(reason: str = ""):
    global arduino

    if reason:
        print(reason)

    shutdown_event.set()
    send_error(0, "shutdown")

    try:
        with serial_lock:
            if arduino.is_open:
                arduino.close()
                print("[shutdown] Serial port closed.")
    except Exception as e:
        print(f"[shutdown] Error closing serial port: {e}")

    _serial_reader_thread.join(timeout=3.0)
    if _serial_reader_thread.is_alive():
        print("[shutdown] WARNING: serial_reader thread did not exit in time.")
    else:
        print("[shutdown] serial_reader thread exited cleanly.")

    capture_chest.release()
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
    cv2.imshow(WIN, frame)
    cv2.moveWindow(WIN, 0, 0)
    cv2.resizeWindow(WIN, screen_w, screen_h)
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cv2.waitKey(50) & 0xFF == 27:
            break


# ======================================================================
# LIMIT SWITCH NOT INTERFACED / MALFUNCTIONING  ->  HALT
#
# The only halt-until-replaced condition. Drawn on a blank canvas rather
# than the camera feed, because at startup the camera is irrelevant here
# and may not even be available yet.
#
# failures: list of (component_key, status_key) tuples.
# ======================================================================
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


# ======================================================================
# PROX SENSOR DID NOT DETECT  ->  "REPLACEMENT REQUIRED"
#
# Reached when the home limit switch caught the lever but the paired
# prox never fired. That means the prox is not interfaced, dead,
# misaligned, or wired with the wrong polarity. The switch did its job,
# so the machine was never in danger — but the primary sensor is gone
# and must be replaced, so this run ends here with the message on screen.
# ======================================================================
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


# ======================================================================
# OTHER ALERTS
# ======================================================================
def show_emergency_and_exit(source: str = ""):
    if source:
        print(f"!!!! {source} — stopping system !!!!")
    send_error(0, "emergency")

    frame = _blank_fullscreen()

    line1 = "Emergency Switch is Pressed"
    line2 = "Please Wait For Reboot"

    font      = cv2.FONT_HERSHEY_SIMPLEX
    scale1    = 1.8
    scale2    = 1.3
    thickness = 3

    (_, th1), _ = cv2.getTextSize(line1, font, scale1, thickness)
    (_, th2), _ = cv2.getTextSize(line2, font, scale2, thickness)

    gap     = 40
    total_h = th1 + gap + th2
    y1      = (screen_h - total_h) // 2 + th1
    y2      = y1 + gap + th2

    _centered_text(frame, line1, y1, scale1, (0, 0, 255), thickness)
    _centered_text(frame, line2, y2, scale2, (255, 255, 255), thickness)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after emergency stop !!!!")


def show_collision_and_exit(source: str = ""):
    if source:
        print(f"!!!! {source} — stopping system !!!!")
    else:
        print("!!!! COLLISION DETECTED — stopping system !!!!")
    send_error(0, "collision-handler")

    if COLLISION_IMG is not None:
        frame = cv2.resize(COLLISION_IMG, (screen_w, screen_h))
    else:
        frame = _blank_fullscreen()
        frame[:] = (0, 0, 180)
        _centered_text(frame, "!! COLLISION OCCURRED !!",
                       screen_h // 2 - 20, 1.2, (0, 0, 255), 3)
        _centered_text(frame, "Check limit switch — terminating...",
                       screen_h // 2 + 40, 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after collision !!!!")


# ======================================================================
# EARLY COLLISION WARNING (A0 prox)  ->  HALT
#
# The A0 collision prox trips before the mechanical collision switch
# makes contact — firmware already soft-stopped both motors by the time
# this line arrives, but that stop is NOT latched, so the very next E:
# command from this script would otherwise resume driving straight
# toward whatever tripped the prox. Halting here (same as the mechanical
# collision path) is the safe choice: an obstruction was detected close
# to the machine, and resuming automatically without a human checking
# it first is the wrong default.
# ======================================================================
def show_collision_prox_and_exit(source: str = ""):
    print(f"!!!! {source or 'EARLY COLLISION (PROX A0) DETECTED'} "
          "— stopping system !!!!")
    send_error(0, "collision-prox-early")

    if COLLISION_IMG is not None:
        frame = cv2.resize(COLLISION_IMG, (screen_w, screen_h))
    else:
        frame = _blank_fullscreen()
        frame[:] = (0, 90, 180)

    _centered_text(frame, "!! EARLY COLLISION WARNING !!",
                   screen_h // 2 - 20, 1.2, (0, 165, 255), 3)
    _centered_text(frame, "Obstruction detected by proximity sensor (A0) — terminating...",
                   screen_h // 2 + 40, 0.8, (255, 255, 255), 2)

    _hold_screen(frame, 4.0)

    shutdown("!!!! Terminating after early collision warning (A0 prox) !!!!")


def show_wrong_indices_and_exit(motor_num: int = 1, early: bool = False):
    """Home limit reached (either now, or already true at startup) with
    the prox sensor working correctly (either the prox caught it early,
    or both fired). A prox that FAILED to fire is handled by
    show_prox_replacement_and_exit() instead, which is checked first."""
    tag = "EARLY " if early else ""
    print(f"!!!! {tag}M{motor_num} HOME LIMIT TRIGGERED — WRONG INDICES !!!!")
    if early:
        print(f"!!!! Caught by Proximity Sensor {motor_num} — axis stopped before mechanical contact !!!!")
    send_error(0, f"m{motor_num}-home-limit" + ("-early" if early else ""))

    start = time.time()
    while time.time() - start < 5:
        ret, frame = capture_chest.read()
        if not ret or frame is None:
            print("[show_wrong_indices_and_exit] WARNING: could not read camera frame.")
            break
        h, w, _ = frame.shape
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h // 2 - 60), (w, h // 2 + 60), (0, 0, 200), -1)
        cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)
        header = f"!! {'EARLY ' if early else ''}WRONG INDICES !!"
        cv2.putText(frame, header,
                    (w // 2 - 220, h // 2 - 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
        sub = f"M{motor_num} HOME LIMIT TRIGGERED" + (" (PROX)" if early else "")
        cv2.putText(frame, sub,
                    (w // 2 - 215, h // 2 + 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2)
        cv2.putText(frame, "Terminating...",
                    (w // 2 - 110, h // 2 + 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        cv2.imshow(WIN, make_combined(frame))
        _apply_win_size()
        if cv2.waitKey(1) & 0xFF == 27:
            break
    shutdown(f"!!!! Terminating after {'early ' if early else ''}wrong indices (M{motor_num}) !!!!")


# ======================================================================
# HARDWARE FAULT SENTINEL — call from every wait/poll loop.
#
# Order matters and is deliberate:
#   1. Limit switch absent/shorted  -> halt, name the switch, exit.
#   2. Prox failed to detect        -> "PROX n NOT DETECTED,
#                                       REPLACEMENT REQUIRED", exit.
#
# Checking the prox message BEFORE the plain LIMIT:Mn_HOME handler also
# removes an old race: the firmware sends FAULT:PROXn_REPLACE
# immediately before LIMIT:Mn_HOME, and previously whichever the main
# loop happened to observe first decided the message. Now both paths
# lead to the prox message when the prox failed.
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

    if not guarded_raw_write(b"SELFTEST?\n", context.lower()):
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
# STARTUP collision-prox (A0) CHECK
#
# Mirrors check_m1_home_at_startup() below, applied to the collision
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
    if not guarded_raw_write(b"PSTATUSC?\n", f"{context.lower()}-pstatusC"):
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
# STARTUP "ALREADY AT HOME" CHECK  (M1 / CHEST)
#
# Runs once, right before the camera loop is entered. Queries the
# firmware directly for:
#   - the M1 home limit switch state  (HSTATUS1? -> HOME1:AT_HOME/AWAY/FAULT)
#   - prox sensor 1's raw state       (PSTATUS1? -> PROX1:TRIGGERED/CLEAR)
#
# If EITHER is already triggered, the chest is already sitting at (or
# past) the home position, which is the same "wrong indices" condition
# handled mid-run — so it's reported and the run ends here rather than
# starting an alignment pass from the wrong starting point.
#
# FAULT on HSTATUS1? would mean the switch went bad in the instant
# between the self-test passing and this query — treated the same as
# any other switch fault (halt, name it, wait for replacement).
# ======================================================================
def check_m1_home_at_startup():
    REPLY_TIMEOUT = 3.0

    print("[STARTUP] Checking M1 home switch / prox-1 state before starting...")

    hstatus1_result_event.clear()
    hstatus1_value["v"] = None
    if not guarded_raw_write(b"HSTATUS1?\n", "startup-hstatus1"):
        shutdown("[STARTUP] Failed to send HSTATUS1? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not hstatus1_result_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for HSTATUS1? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to HSTATUS1? — terminating.")
        time.sleep(0.02)
    home1_state = hstatus1_value["v"]

    pstatus1_result_event.clear()
    pstatus1_value["v"] = None
    if not guarded_raw_write(b"PSTATUS1?\n", "startup-pstatus1"):
        shutdown("[STARTUP] Failed to send PSTATUS1? — terminating.")

    deadline = time.time() + REPLY_TIMEOUT
    while not pstatus1_result_event.is_set():
        if serial_dead_event.is_set():
            shutdown("[STARTUP] Serial lost while waiting for PSTATUS1? reply.")
        if time.time() > deadline:
            shutdown("[STARTUP] No reply to PSTATUS1? — terminating.")
        time.sleep(0.02)
    prox1_state = pstatus1_value["v"]

    print(f"[STARTUP] M1 home switch = {home1_state}, Prox1 = {prox1_state}")

    if home1_state == "FAULT":
        show_limit_switch_fault_and_exit([("M1_SWITCH", "SHORT")])

    at_home_switch = (home1_state == "AT_HOME")
    at_home_prox   = (prox1_state == "TRIGGERED")

    if at_home_switch or at_home_prox:
        print("[STARTUP] M1 is already at the home position — wrong indices.")
        # Prefer flagging it as an "early" (prox) catch only when the
        # switch itself isn't ALSO triggered, matching the mid-run logic.
        show_wrong_indices_and_exit(1, early=(at_home_prox and not at_home_switch))


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

    print("[STARTUP] Arduino READY. Sending STATUS? ...")
    if not guarded_raw_write(b"STATUS?\n", "startup"):
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

    print("[STARTUP] Sending CSTATUS? ...")
    if not guarded_raw_write(b"CSTATUS?\n", "startup"):
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

    # NEW: M1 (chest) home switch / prox-1 already-at-home check, right
    # before the camera loop is entered.
    check_m1_home_at_startup()


check_startup_switch()


# ======================================================================
# POST-RECONNECT RE-HANDSHAKE
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

    # The Arduino reset, so re-verify the switches. One unplugged during
    # the outage must not slip through.
    run_limit_switch_selftest("RECONNECT")

    print("[RECONNECT] Arduino READY. Re-sending STATUS? ...")
    switch_status_received_event.clear()
    if not guarded_raw_write(b"STATUS?\n", "reconnect"):
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
    if not guarded_raw_write(b"CSTATUS?\n", "reconnect"):
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
    check_m1_home_at_startup()

    reconnect_pending_event.clear()
    print("[RECONNECT] Re-handshake complete — resuming normal operation.")


# ======================================================================
# WATCHDOG
# ======================================================================
WATCHDOG_INTERVAL      = 5.0
WATCHDOG_REPLY_TIMEOUT = 3.0
_WATCHDOG_POLL_INTERVAL = 0.5

def watchdog():
    missed = 0
    MAX_MISSED = 2
    elapsed = 0.0

    while not shutdown_event.is_set() and not serial_dead_event.is_set():

        if elapsed < WATCHDOG_INTERVAL:
            time.sleep(_WATCHDOG_POLL_INTERVAL)
            elapsed += _WATCHDOG_POLL_INTERVAL
            if _port_lost.is_set():
                print("[watchdog] Port-lost flag detected — marking serial dead.")
                serial_dead_event.set()
                return
            continue

        elapsed = 0.0
        if shutdown_event.is_set() or serial_dead_event.is_set():
            break

        _watchdog_reply_received.clear()

        try:
            with serial_lock:
                if not arduino.is_open:
                    print("[watchdog] Port is closed — skipping ping.")
                    missed += 1
                    if missed >= MAX_MISSED:
                        print(f"[watchdog] {missed} consecutive misses — marking serial dead.")
                        serial_dead_event.set()
                        return
                    continue
                arduino.write(b"STATUS?\n")
        except Exception as e:
            print(f"[watchdog] Send failed: {e}")
            missed += 1
            if missed >= MAX_MISSED:
                print(f"[watchdog] {missed} consecutive ping failures — marking serial dead.")
                serial_dead_event.set()
                return
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
                return

threading.Thread(target=watchdog, daemon=True).start()


# ======== Main Loop Variables ========
error_chest    = 0
last_sent_time = 0
send_interval  = 0.03
image_captured = False

no_person_start    = None
NO_PERSON_TIMEOUT  = 5.0


# ======================================================================
# MAIN LOOP
# ======================================================================
while True:

    if serial_dead_event.is_set():
        shutdown("!!!! Serial connection lost — terminating !!!!")

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

    if m1_home_early_event.is_set():
        m1_home_early_event.clear()
        show_wrong_indices_and_exit(1, early=True)

    if m2_home_early_event.is_set():
        m2_home_early_event.clear()
        show_wrong_indices_and_exit(2, early=True)

    if m1_home_event.is_set():
        show_wrong_indices_and_exit(1)

    if m2_home_event.is_set():
        show_wrong_indices_and_exit(2)

    ret, frame1 = capture_chest.read()
    if not ret or frame1 is None:
        print("--------Failed to grab frame----------")
        shutdown("Frame grab failed — terminating.")

    h1, w1, _ = frame1.shape
    center_y1  = h1 // 2

    cv2.line(frame1, (0, center_y1), (w1, center_y1), (0, 0, 255), 2)
    cv2.circle(frame1, (w1 // 2, center_y1), 5, (255, 255, 255), -1)

    rgb1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2RGB)
    res1 = pose.process(rgb1)

    if res1.pose_landmarks:
        no_person_start = None

        lm          = res1.pose_landmarks.landmark
        shoulder_y  = int((lm[11].y + lm[12].y) / 2 * h1)

        x1 = int(lm[11].x * w1);  y1_lm = int(lm[11].y * h1)
        x2 = int(lm[12].x * w1);  y2_lm = int(lm[12].y * h1)
        x3 = (x1 + x2) // 2;      y3    = (y1_lm + y2_lm) // 2

        x4 = int(lm[23].x * w1);  y4_lm = int(lm[23].y * h1)
        x5 = int(lm[24].x * w1);  y5_lm = int(lm[24].y * h1)
        x6 = (x4 + x5) // 2;      y6    = (y4_lm + y5_lm) // 2

        x7 = (x3 + x6) // 2;      y7    = (y3 + y6) // 2

        error_chest = center_y1 - y7

        cv2.circle(frame1, (x3, y3),    5, (203, 192, 255), -1)
        cv2.circle(frame1, (x1, y1_lm), 5, (203, 192, 255), -1)
        cv2.circle(frame1, (x2, y2_lm), 5, (203, 192, 255), -1)

        cv2.circle(frame1, (x6, y6),    5, (203, 192, 255), -1)
        cv2.circle(frame1, (x4, y4_lm), 5, (203, 192, 255), -1)
        cv2.circle(frame1, (x5, y5_lm), 5, (203, 192, 255), -1)

        cv2.circle(frame1, (x7, y7), 5, (144, 238, 144), -1)

        cv2.line(frame1, (x1, y1_lm), (x2, y2_lm), (255, 0, 0), 2)
        cv2.line(frame1, (x4, y4_lm), (x5, y5_lm), (255, 0, 0), 2)
        cv2.line(frame1, (x1, y1_lm), (x4, y4_lm), (255, 0, 0), 2)
        cv2.line(frame1, (x5, y5_lm), (x2, y2_lm), (255, 0, 0), 2)
        cv2.line(frame1, (w1 // 2, center_y1), (x7, y7), (255, 255, 0), 2)
        cv2.rectangle(frame1, (10, 10), (200, 60), (0, 0, 0), -1)
        cv2.putText(frame1, f"Moving : {error_chest}", (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

        if -8 <= error_chest <= 8 and not image_captured:
            filename = f"Alined_CHEST_.jpg"
            cv2.putText(frame1, "ALIGNED", (w1 - 130, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imwrite(filename, frame1)
            print(f"-----Image captured: '{filename}'-----")
            image_captured = True
        else:
            cv2.putText(frame1, "NOT ALIGNED", (w1 - 220, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    else:
        error_chest = 0

        if no_person_start is None:
            no_person_start = time.time()

        elapsed_no_person = time.time() - no_person_start
        cv2.rectangle(frame1, (10, 10), (260, 60), (0, 0, 0), -1)
        cv2.putText(frame1, f"No person: {elapsed_no_person:4.1f}s",
                    (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        if elapsed_no_person >= NO_PERSON_TIMEOUT:
            send_error(0, "no-person-timeout")
            shutdown(f"No person detected in front of the camera for "
                     f"{NO_PERSON_TIMEOUT:.0f} seconds — terminating.")

    if time.time() - last_sent_time > send_interval:
        send_error(error_chest)
        print(f"Sent -> Chest err: {error_chest:+4d}")
        last_sent_time = time.time()

    cv2.imshow(WIN, make_combined(frame1))
    _apply_win_size()

    if image_captured:
        send_error(0, "post-capture")
        print("*****Alignment achieved. Displaying for 3 seconds*****")
        captured_display = cv2.imread(filename)
        display_start    = time.time()

        while time.time() - display_start < 3:

            if serial_dead_event.is_set():
                shutdown("!!!! Serial lost during display !!!!")

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

            if m1_home_early_event.is_set():
                m1_home_early_event.clear()
                show_wrong_indices_and_exit(1, early=True)

            if m2_home_early_event.is_set():
                m2_home_early_event.clear()
                show_wrong_indices_and_exit(2, early=True)

            if m1_home_event.is_set():
                show_wrong_indices_and_exit(1)

            if m2_home_event.is_set():
                show_wrong_indices_and_exit(2)

            ret, frame1 = capture_chest.read()
            if not ret or frame1 is None:
                print("*****Failed to grab frame during display*****")
                break

            cv2.line(frame1, (0, center_y1), (w1, center_y1), (0, 0, 255), 2)
            cv2.putText(frame1, "ALIGNED", (w1 - 130, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            cap_panel  = cv2.resize(captured_display, (panel_w, panel_h),
                                    interpolation=cv2.INTER_LINEAR)
            live_panel = cv2.resize(frame1, (panel_w, panel_h),
                                    interpolation=cv2.INTER_LINEAR)
            cv2.imshow(WIN, cv2.hconcat([cap_panel, live_panel]))

            if cv2.waitKey(1) & 0xFF == 27:
                break

        print("*****Exiting display loop*****")
        break

    if cv2.waitKey(1) & 0xFF == 27:
        break


# ======== Cleanup (normal exit path) ========
shutdown("Normal exit.")
