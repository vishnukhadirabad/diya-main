import serial
import serial.tools.list_ports
import time
import os
import queue
import threading
import cv2
import numpy as np
import subprocess
import sys
import signal

# -------------------------------------------------------
#  Config
# -------------------------------------------------------
BAUD_RATE   = 115200
TIMEOUT     = 30
PAUSE_IMAGE = "pause.png"
WINDOW_NAME = "Paused — release switch to continue"
ALERT_WINDOW = "Hardware Fault"

# Exit code used when the run is stopped by a hardware fault (limit switch
# missing/shorted, or a prox sensor that needs replacing), as opposed to a
# normal completion (0). Set this to 0 if run1.sh does not check the exit
# status and you don't want the pipeline to abort here.
HARDWARE_FAULT_EXIT_CODE = 2

# send_command_and_wait() outcomes. RETRY is returned when the operator
# pressed the manual stop mid-move: the firmware aborts the pass and the
# command is simply re-issued once the switch is released, rather than
# treating an intentional pause as a failure.
RESULT_DONE  = "DONE"
RESULT_RETRY = "RETRY"
RESULT_FAIL  = "FAIL"
MAX_HOME_RETRIES = 2

# ======================================================================
# HARDWARE POLICY (matches the current Arduino firmware)
#
#   HOME LIMIT SWITCHES = critical and provable. Wired NO+NC, so a
#       healthy switch can never read the same level on both pins. If
#       either is NOT INTERFACED or MALFUNCTIONING, the firmware latches
#       all motion off and this script halts before commanding any move,
#       naming which switch needs replacement.
#
#   PROXIMITY SENSORS   = early warning only, and not provable (an
#       unplugged wire and an idle sensor read identically). The limit
#       switch is the detector for a failed prox: if the switch caught
#       the lever and the prox did not fire, the firmware sends
#       FAULT:PROXn_REPLACE and this script reports
#       "PROX n NOT DETECTED — REPLACEMENT REQUIRED".
#
#   That FAULT:PROXn_REPLACE line is also how this script answers the
#   question "was homing stopped by the prox or by the limit switch?":
#       DONE:HOMEn with no FAULT:PROXn_REPLACE -> the prox stopped it
#                                                 (normal, prox healthy)
#       DONE:HOMEn with FAULT:PROXn_REPLACE    -> the LIMIT SWITCH
#                                                 stopped it, prox dead
#   See report_home_source() below.
#
#   COLLISION PROX (A0) = early warning for an incoming obstruction,
#       independent of which axis is currently homing. Firmware sends
#       EARLY:COLLISION_PROX_A0 followed by ERROR:HOMINGn_COLLISION_PROX
#       when it trips mid-homing pass; both motors are stopped in
#       firmware immediately (emergencyStop()).
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
    "MOTION_BLOCKED": "MOTION REFUSED — CONTROLLER SELF-TEST HAS FAILED",
}

# ---- write-rate limiter ----
_last_write_time = 0.0
_MIN_WRITE_GAP   = 0.025   # 25 ms hard floor between any two serial writes

# ---- watchdog bookkeeping ----
_watchdog_reply_received = threading.Event()

WATCHDOG_INTERVAL      = 5.0   # seconds between pings
WATCHDOG_REPLY_TIMEOUT = 3.0   # seconds to wait for any reply after ping

# ---- fast-disconnect detection ----
_port_lost = threading.Event()
_device_path = None

# ------------------------------------------------------------------
#  Hardware-state bookkeeping, filled in by serial_reader().
#
#  Kept in module-level dicts (under _hw_lock) rather than only in the
#  message queue, because these have to survive the queue drains that
#  wait_for_switch_released() and check_home_state() perform — a switch
#  fault must not be thrown away just because it arrived at the wrong
#  moment.
# ------------------------------------------------------------------
_hw_lock          = threading.Lock()
_selftest_results = {}                    # "M1_SWITCH" -> "OK"/"ABSENT"/"SHORT"
_switch_faults    = {}                    # "M1_SWITCH" -> "ABSENT"/"SHORT"
_prox_fault       = {1: False, 2: False}  # prox n fired? False = healthy so far
_selftest_done    = threading.Event()
_selftest_pass    = threading.Event()
_selftest_fail    = threading.Event()

# ------------------------------------------------------------------
# COLLISION (pin 3) — a real hardware safety signal, not a limit-switch
# fault. The firmware already stops both motors in firmware the instant
# it fires, but this script previously only re-queued the ACTIVE/CLEAR
# lines during the READY wait and never actually acted on them anywhere
# else — a collision mid-run would silently sit unhandled while Python
# kept waiting on a DONE:/ERROR: that firmware will never send while
# collisionFlag is latched. _collision_event mirrors the pattern already
# used for switch faults / self-test above.
# ------------------------------------------------------------------
_collision_event            = threading.Event()
_collision_status_received  = threading.Event()

# -------------------------------------------------------
#  Global references for cleanup (needed by signal handler)
# -------------------------------------------------------
_ser        = None
_stop_event = None
_reader     = None
_serial_lock = threading.Lock()   # guards all serial writes


# -------------------------------------------------------
#  Guarded write — rate-limited, write-timeout-bounded, never raises.
#
#  reset_input_buffer() is NOT called here. Calling it from the writer
#  while serial_reader's readline() loop is running discards bytes already
#  in the kernel buffer, corrupting the next decoded line. The only safe
#  callers are startup (before the reader thread starts) and the reader
#  itself on reconnect (under the lock).
# -------------------------------------------------------
def guarded_write(data: bytes, label: str = "") -> bool:
    """Write `data` to the serial port safely. Returns True on success."""
    global _ser, _last_write_time

    now = time.monotonic()
    gap = now - _last_write_time
    if gap < _MIN_WRITE_GAP:
        time.sleep(_MIN_WRITE_GAP - gap)

    tag = f"[{label}] " if label else ""
    try:
        with _serial_lock:
            if _ser is None or not _ser.is_open:
                print(f"{tag}Port closed — skipping write of {data!r}")
                return False
            ret = _ser.write(data)
        _last_write_time = time.monotonic()
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


# -------------------------------------------------------
#  Cleanup & Emergency Stop
# -------------------------------------------------------
def emergency_stop(reason="Interrupted", exit_code=0):
    """Send STOP to Arduino, close serial, destroy windows, exit."""
    print(f"\n[Python] {reason} — sending emergency stop to Arduino...")

    if _stop_event:
        _stop_event.set()

    guarded_write(b"STOP\n", "emergency_stop")
    time.sleep(0.3)   # give Arduino time to halt motors

    with _serial_lock:
        if _ser and _ser.is_open:
            try:
                _ser.close()
            except Exception:
                pass
            print("[Python] Serial port closed.")

    if _reader and _reader.is_alive():
        _reader.join(timeout=2)

    cv2.destroyAllWindows()
    print("[Python] Exited cleanly.")
    sys.exit(exit_code)


def sigint_handler(sig, frame):
    emergency_stop("Ctrl+C detected")


signal.signal(signal.SIGINT,  sigint_handler)
signal.signal(signal.SIGTERM, sigint_handler)


# -------------------------------------------------------
#  Arduino auto-detection
# -------------------------------------------------------
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


def list_available_ports():
    ports = serial.tools.list_ports.comports()
    if ports:
        print("Available serial ports:")
        for p in ports:
            print(f"  {p.device}  —  {p.description}")
    else:
        print("No serial ports found.")
    print()


def load_pause_image():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    img_path   = os.path.join(script_dir, PAUSE_IMAGE)
    img = cv2.imread(img_path)
    if img is None:
        print(f"[WARNING] Could not load '{img_path}'. Showing placeholder.")
        img = np.zeros((480, 640, 3), dtype="uint8") + 60
        cv2.putText(img, "PAUSED — release switch to resume",
                    (40, 240), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (220, 220, 220), 2, cv2.LINE_AA)
    return img


def get_screen_resolution():
    try:
        output = subprocess.check_output(
            ["xrandr"], stderr=subprocess.DEVNULL
        ).decode("utf-8")
        for line in output.splitlines():
            if "* " in line:
                parts = line.strip().split()
                w, h = parts[0].split("x")
                return int(w), int(h)
    except Exception:
        pass

    try:
        output = subprocess.check_output(
            ["xdpyinfo"], stderr=subprocess.DEVNULL
        ).decode("utf-8")
        for line in output.splitlines():
            if "dimensions:" in line:
                res = line.strip().split()[1]
                w, h = res.split("x")
                return int(w), int(h)
    except Exception:
        pass

    print("[Python] Could not detect screen resolution; defaulting to 1920x1080.")
    return 1920, 1080


# -------------------------------------------------------
#  Full-screen alert helpers
# -------------------------------------------------------
def _centered_text(frame, text, y, scale, color, thickness=2):
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    (tw, _), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max(20, (w - tw) // 2)
    cv2.putText(frame, text, (x, y), font, scale, color, thickness, cv2.LINE_AA)


def _show_alert(frame, seconds=8.0):
    screen_w, screen_h = frame.shape[1], frame.shape[0]
    cv2.namedWindow(ALERT_WINDOW, cv2.WINDOW_NORMAL)
    cv2.imshow(ALERT_WINDOW, frame)
    for _ in range(5):
        cv2.waitKey(30)
        cv2.moveWindow(ALERT_WINDOW, 0, 0)
        cv2.resizeWindow(ALERT_WINDOW, screen_w, screen_h)
    deadline = time.time() + seconds
    while time.time() < deadline:
        if cv2.waitKey(50) & 0xFF == 27:
            break


# ======================================================================
#  LIMIT SWITCH NOT INTERFACED / MALFUNCTIONING  ->  HALT
#
#  This is the only halt-until-replaced condition. The firmware has
#  already latched motion off on the affected axis by the time we get
#  here, so nothing can move regardless of what this script does next.
#
#  failures: list of (component_key, status_key) tuples.
# ======================================================================
def show_limit_switch_fault_and_exit(failures):
    print("=" * 72)
    print("!!!! LIMIT SWITCH CHECK FAILED — RETURN-TO-HOME WILL NOT RUN !!!!")
    for comp, status in failures:
        label  = COMPONENT_LABELS.get(comp, comp)
        detail = STATUS_LABELS.get(status, status)
        print(f"  * {label}")
        print(f"      -> {detail}")
    print("!!!! REPLACEMENT REQUIRED. Fit/repair the switch, then restart. !!!!")
    print("=" * 72)

    screen_w, screen_h = get_screen_resolution()
    frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    y = int(screen_h * 0.15)
    _centered_text(frame, "SYSTEM HALTED", y, 2.0, (0, 0, 255), 4)
    y += int(screen_h * 0.075)
    _centered_text(frame, "LIMIT SWITCH FAULT", y, 1.2, (0, 0, 255), 3)

    y += int(screen_h * 0.05)
    cv2.line(frame, (int(screen_w * 0.1), y), (int(screen_w * 0.9), y),
             (0, 0, 180), 2)

    y += int(screen_h * 0.08)
    for comp, status in failures:
        _centered_text(frame, COMPONENT_LABELS.get(comp, comp), y,
                       1.0, (0, 255, 255), 2)
        y += int(screen_h * 0.045)
        _centered_text(frame, STATUS_LABELS.get(status, status), y,
                       0.7, (255, 255, 255), 2)
        y += int(screen_h * 0.07)

    y = int(screen_h * 0.84)
    _centered_text(frame, "REPLACEMENT REQUIRED", y, 1.1, (0, 165, 255), 3)
    _centered_text(frame, "Fit or repair the switch above, then restart the system.",
                   y + int(screen_h * 0.06), 0.8, (255, 255, 255), 2)

    _show_alert(frame, 8.0)

    emergency_stop("Home limit switch not interfaced or malfunctioning",
                   exit_code=HARDWARE_FAULT_EXIT_CODE)


# ======================================================================
#  PROX SENSOR DID NOT DETECT  ->  "REPLACEMENT REQUIRED"
#
#  Homing completed safely — the LIMIT SWITCH caught the lever — but the
#  paired prox never fired, so the prox is not interfaced, dead,
#  misaligned, or wired with the wrong polarity.
# ======================================================================
# ======================================================================
#  HOMING RAN OUT OF TRAVEL  ->  HALT
#
#  ERROR:HOMINGn_NO_HOME_FOUND. The firmware stepped the full configured
#  axis travel (HOME_MAX_TRAVEL_MM) or hit HOME_TIMEOUT_MS without either
#  the prox OR the limit switch triggering. The axis is stopped where it
#  ran out, which is NOT home, so nothing downstream can be trusted.
#
#  Note this is a different failure from a switch wiring fault: the
#  switch is electrically healthy (it passed the self-test), it just was
#  never reached.
# ======================================================================
def show_collision_and_exit(source: str = ""):
    print("=" * 72)
    print(f"!!!! {source or 'COLLISION DETECTED'} — stopping system !!!!")
    print("!!!! Pin 3 (collision switch) is ACTIVE. Firmware has already "
          "stopped both motors. !!!!")
    print("=" * 72)

    screen_w, screen_h = get_screen_resolution()
    frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
    frame[:] = (0, 0, 180)
    _centered_text(frame, "!! COLLISION DETECTED !!",
                   screen_h // 2 - 20, 1.2, (0, 0, 255), 3)
    _centered_text(frame, "Check limit switch / obstruction — terminating...",
                   screen_h // 2 + 40, 0.8, (255, 255, 255), 2)

    _show_alert(frame, 4.0)

    emergency_stop("Collision detected")


def show_home_not_found_and_exit(motor_num):
    axis = "CHEST" if motor_num == 1 else "EYES"

    causes = [
        f"Wrong homing direction (M{motor_num}_HOME_DIR)",
        "Motor not stepping — driver disabled, stalled or unpowered",
        "Coupling or belt slipped",
        "Axis obstructed before reaching the lever",
        f"BOTH prox {motor_num} and the M{motor_num} limit switch failed to trigger",
        "HOME_MAX_TRAVEL_MM set shorter than the real axis travel",
    ]

    print("=" * 72)
    print(f"!!!! M{motor_num} ({axis}) HOME NOT FOUND — HOMING ABORTED !!!!")
    print("!!!! The axis travelled its full configured range without "
          "reaching home. !!!!")
    print("!!!! It is stopped where it ran out — this is NOT the home "
          "position. !!!!")
    print("     Possible causes:")
    for c in causes:
        print(f"       - {c}")
    print("=" * 72)

    screen_w, screen_h = get_screen_resolution()
    frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    y = int(screen_h * 0.13)
    _centered_text(frame, "HOME NOT FOUND", y, 1.9, (0, 0, 255), 4)
    y += int(screen_h * 0.07)
    _centered_text(frame, f"M{motor_num} / {axis} — HOMING ABORTED",
                   y, 1.1, (0, 165, 255), 3)

    y += int(screen_h * 0.05)
    cv2.line(frame, (int(screen_w * 0.1), y), (int(screen_w * 0.9), y),
             (0, 0, 180), 2)

    y += int(screen_h * 0.06)
    _centered_text(frame, "The axis travelled its full range without "
                          "reaching home.", y, 0.8, (255, 255, 255), 2)
    y += int(screen_h * 0.042)
    _centered_text(frame, "It is NOT at the home position.",
                   y, 0.8, (255, 255, 255), 2)

    y += int(screen_h * 0.06)
    _centered_text(frame, "CHECK:", y, 0.85, (0, 255, 255), 2)
    for c in causes:
        y += int(screen_h * 0.04)
        _centered_text(frame, c, y, 0.62, (200, 200, 200), 1)

    y = int(screen_h * 0.9)
    _centered_text(frame, "Fix the cause above, then restart the system.",
                   y, 0.8, (255, 255, 255), 2)

    _show_alert(frame, 10.0)

    emergency_stop(f"Motor {motor_num} home not found within configured travel",
                   exit_code=HARDWARE_FAULT_EXIT_CODE)


def show_prox_replacement_and_exit(motor_num, homing_completed=True):
    axis = "CHEST" if motor_num == 1 else "EYES"

    print("=" * 72)
    print(f"!!!! PROX {motor_num} NOT DETECTED — REPLACEMENT REQUIRED !!!!")
    print(f"!!!! M{motor_num} ({axis}) HOME LIMIT SWITCH *WAS* TRIGGERED — "
          f"it stopped the axis in place of the prox sensor. !!!!")
    if homing_completed:
        print(f"!!!! Homing of motor {motor_num} did complete safely on the "
              f"switch, so the axis IS at true home. !!!!")
    print("=" * 72)

    screen_w, screen_h = get_screen_resolution()
    frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    y = int(screen_h * 0.15)
    _centered_text(frame, f"PROX {motor_num} NOT DETECTED", y, 1.9, (0, 0, 255), 4)
    y += int(screen_h * 0.085)
    _centered_text(frame, "REPLACEMENT REQUIRED", y, 1.4, (0, 165, 255), 3)

    y += int(screen_h * 0.055)
    cv2.line(frame, (int(screen_w * 0.1), y), (int(screen_w * 0.9), y),
             (0, 0, 180), 2)

    y += int(screen_h * 0.085)
    _centered_text(frame, f"M{motor_num} / {axis} PROXIMITY SENSOR "
                          f"(pin A{motor_num})",
                   y, 1.0, (0, 255, 255), 2)
    y += int(screen_h * 0.048)
    _centered_text(frame, "did not detect the metal lever.",
                   y, 0.8, (255, 255, 255), 2)

    y += int(screen_h * 0.07)
    _centered_text(frame, f"M{motor_num} HOME LIMIT SWITCH: TRIGGERED  (OK)",
                   y, 0.9, (0, 255, 0), 2)
    y += int(screen_h * 0.045)
    _centered_text(frame, "The limit switch stopped the axis correctly.",
                   y, 0.75, (255, 255, 255), 2)

    y = int(screen_h * 0.87)
    _centered_text(frame, "Replace the proximity sensor, then restart the system.",
                   y, 0.8, (255, 255, 255), 2)

    _show_alert(frame, 8.0)

    emergency_stop(f"Prox {motor_num} not detected — replacement required",
                   exit_code=HARDWARE_FAULT_EXIT_CODE)


# ======================================================================
#  NEW — A0 COLLISION PROX EARLY WARNING DURING HOMING
#
#  Firmware sends EARLY:COLLISION_PROX_A0 followed by
#  ERROR:HOMINGn_COLLISION_PROX when the A0 collision prox trips mid
#  homing pass (see checkForCollisionProxEarly() in the firmware). Both
#  motors are already stopped by the firmware's emergencyStop() by the
#  time this fires. This just gives it its own full-screen alert instead
#  of falling through to the generic collision or generic-error screens.
# ======================================================================
def show_collision_prox_early_and_exit(motor_num):
    axis = "CHEST" if motor_num == 1 else "EYES"

    print("=" * 72)
    print(f"!!!! EARLY COLLISION DETECTED AT PROX (A0) during M{motor_num} "
          f"({axis}) homing !!!!")
    print("!!!! The A0 collision proximity sensor detected an incoming "
          "obstruction before the mechanical collision switch was "
          "reached. Both motors have been stopped. !!!!")
    print("=" * 72)

    screen_w, screen_h = get_screen_resolution()
    frame = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)
    frame[:] = (0, 90, 180)   # amber-ish — early warning, not a hard fault
    _centered_text(frame, "!! EARLY COLLISION DETECTED AT PROX (A0) !!",
                   screen_h // 2 - 20, 1.1, (0, 0, 255), 3)
    _centered_text(frame, f"Detected during M{motor_num} ({axis}) homing — both motors stopped.",
                   screen_h // 2 + 40, 0.8, (255, 255, 255), 2)

    _show_alert(frame, 5.0)

    emergency_stop(f"Early collision detected at prox (A0) during motor "
                   f"{motor_num} homing")


# -------------------------------------------------------
#  Serial reader thread
#
#  Blocking readline() with a 2 s timeout (set on the Serial object).
#  _watchdog_reply_received is set on every decoded line so the watchdog
#  can confirm the Arduino is alive without a dedicated reply type.
#
#  Recognizes the current firmware's diagnostic lines and records them in
#  the module-level hardware-state dicts as well as queueing them, so a
#  fault can't be lost to a queue drain:
#     SELFTEST:BEGIN / TEST:x=y / SELFTEST:PASS|FAIL / SELFTEST:END
#     FAULT:Mn_SWITCH_ABSENT | FAULT:Mn_SWITCH_SHORT   (halt condition)
#     FAULT:PROXn_REPLACE                              (prox replacement)
#     EARLY:Mn_HOME                                    (prox caught it early)
#     EARLY:COLLISION_PROX_A0                          (NEW: A0 prox during homing)
#     LIMIT:Mn_HOME                                    (switch engaged)
# -------------------------------------------------------
def serial_reader(ser, msg_queue, stop_event):
    """Daemon thread — reads every line from serial and puts it in the queue."""
    while not stop_event.is_set():
        try:
            raw = ser.readline()

            if stop_event.is_set():
                break

            if not raw:
                # Timeout with no data. Some platforms leave is_open True
                # and readline() returning b"" forever after a USB-serial
                # adapter is unplugged, so check the device node directly.
                if _device_path and not os.path.exists(_device_path):
                    print(f"[serial_reader] Device node {_device_path} "
                          f"vanished — port physically disconnected.")
                    _port_lost.set()
                    break
                continue

            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            print(f"[Arduino] {line}")
            _watchdog_reply_received.set()

            # ---- limit-switch self-test report ----
            if line == "SELFTEST:BEGIN":
                with _hw_lock:
                    _selftest_results.clear()
                _selftest_done.clear()
                _selftest_pass.clear()
                _selftest_fail.clear()
            elif line.startswith("TEST:") and "=" in line:
                key, _, val = line[len("TEST:"):].partition("=")
                with _hw_lock:
                    _selftest_results[key.strip()] = val.strip()
            elif line == "SELFTEST:PASS":
                _selftest_pass.set()
            elif line == "SELFTEST:FAIL":
                _selftest_fail.set()
            elif line == "SELFTEST:END":
                _selftest_done.set()

            # ---- limit switch not interfaced / malfunctioning ----
            elif line in ("FAULT:M1_SWITCH_ABSENT", "FAULT:M1_SWITCH_SHORT",
                          "FAULT:M2_SWITCH_ABSENT", "FAULT:M2_SWITCH_SHORT",
                          "FAULT:COLLISION_SWITCH_ABSENT", "FAULT:COLLISION_SWITCH_SHORT"):
                if "M1" in line:
                    comp = "M1_SWITCH"
                elif "M2" in line:
                    comp = "M2_SWITCH"
                else:
                    comp = "COLLISION_SWITCH"
                status = "ABSENT" if line.endswith("ABSENT") else "SHORT"
                with _hw_lock:
                    _switch_faults[comp] = status
                print(f"[HALT] {line} — {COMPONENT_LABELS[comp]} is "
                      f"{STATUS_LABELS[status]}. Motion is latched off in "
                      f"firmware; this switch must be replaced.")

            # ---- prox failed to detect; the switch caught the lever ----
            elif line == "FAULT:PROX1_REPLACE":
                with _hw_lock:
                    _prox_fault[1] = True
                print("[REPLACE] FAULT:PROX1_REPLACE — the M1 HOME LIMIT "
                      "SWITCH WAS TRIGGERED but prox 1 never fired. The "
                      "switch did its job; prox 1 needs replacing.")
            elif line == "FAULT:PROX2_REPLACE":
                with _hw_lock:
                    _prox_fault[2] = True
                print("[REPLACE] FAULT:PROX2_REPLACE — the M2 HOME LIMIT "
                      "SWITCH WAS TRIGGERED but prox 2 never fired. The "
                      "switch did its job; prox 2 needs replacing.")

            # ---- legacy generic switch-wire line ----
            elif line.startswith("FAULT:M") and line.endswith("_SWITCH_WIRE"):
                comp = "M1_SWITCH" if "M1" in line else "M2_SWITCH"
                with _hw_lock:
                    _switch_faults.setdefault(comp, "SHORT")

            # ---- NEW: A0 collision prox early warning during homing ----
            # Specific branch BEFORE the generic "EARLY:" catch-all below,
            # since that generic wording ("proximity sensor detected the
            # lever... mechanical switch") is written for the M1/M2 lever
            # prox and would be misleading for the A0 collision prox.
            elif line == "EARLY:COLLISION_PROX_A0":
                print("[SAFETY] EARLY:COLLISION_PROX_A0 — the A0 collision "
                      "proximity sensor detected an incoming obstruction "
                      "before the mechanical collision switch was reached. "
                      "Both motors were stopped by the firmware.")

            elif line.startswith("EARLY:"):
                print(f"[SAFETY] {line} — proximity sensor detected the "
                      f"lever and the axis was halted by the firmware "
                      f"before the mechanical switch was ever reached.")
            elif line.startswith("LIMIT:"):
                print(f"[WARNING] {line} — home limit switch physically "
                      f"engaged outside of a commanded homing pass.")

            # ---- collision (pin 3) ----
            elif line == "COLLISION:ACTIVE":
                _collision_event.set()
                _collision_status_received.set()
            elif line == "COLLISION:CLEAR":
                _collision_event.clear()
                _collision_status_received.set()

            msg_queue.put(line)

        except serial.SerialException as e:
            if not stop_event.is_set():
                print(f"[serial_reader] SerialException — port lost: {e}")
                _port_lost.set()
            break
        except Exception as e:
            if not stop_event.is_set():
                print(f"[serial_reader] Unexpected error: {e}")
                _port_lost.set()
            break


def check_quit_key():
    """Non-blocking OpenCV key check. True if 'q', 'Q', or ESC pressed."""
    key = cv2.waitKey(1) & 0xFF
    return key in (ord('q'), ord('Q'), 27)   # 27 = ESC


def check_port_lost():
    """True if serial_reader has flagged the port as physically gone."""
    return _port_lost.is_set()


def check_switch_faults():
    """Non-blocking. If any home limit switch has been reported absent or
    shorted at any point, halt with the named replacement screen. Called
    from every wait loop so a switch that fails mid-run is caught within
    one poll rather than at the next command timeout."""
    with _hw_lock:
        failures = sorted(_switch_faults.items())
    if failures:
        show_limit_switch_fault_and_exit(failures)


def check_collision():
    """Non-blocking. If the collision switch (pin 3) is currently active,
    halt. Called from every wait loop for the same reason as
    check_switch_faults(): the firmware will not send DONE:/ERROR: for a
    command sent while collisionFlag is latched, so a script that only
    polls the queue for those two prefixes would otherwise wait out the
    full 30 s command timeout instead of reporting what actually
    happened."""
    if _collision_event.is_set():
        show_collision_and_exit("Collision switch active")


def report_home_source(motor_num, command):
    """Report WHICH sensor stopped the homing pass, which is the whole
    point of the prox/switch pairing:

        prox fired    -> normal; the switch was never reached
        switch fired  -> the firmware sent FAULT:PROXn_REPLACE, so the
                         LIMIT SWITCH was triggered and the prox is dead

    Returns True if everything is healthy, and does not return at all if
    the prox needs replacing (it shows the alert and exits)."""
    if not command.startswith("home"):
        # gohomeN performs no motion — the firmware only re-verifies the
        # switch, so there is no prox/switch race to report.
        print(f"[Python] Motor {motor_num}: confirm-only return "
              f"({command}) — no homing pass, nothing to diagnose.")
        return True

    with _hw_lock:
        prox_failed = _prox_fault[motor_num]

    if prox_failed:
        print(f"[Python] Motor {motor_num} homing was stopped by the "
              f"LIMIT SWITCH, not the prox sensor.")
        show_prox_replacement_and_exit(motor_num, homing_completed=True)
        return False   # unreachable — show_...() exits

    print(f"[Python] Motor {motor_num} homing was stopped by the "
          f"PROXIMITY SENSOR (normal). Limit switch was not reached — "
          f"both sensors healthy.")
    return True


def handle_switch_pressed(msg_queue, pause_img):
    print("[Python] Switch is pressed — showing pause image. "
          "Release the switch to resume.")

    screen_w, screen_h = get_screen_resolution()

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.moveWindow(WINDOW_NAME, 0, 0)
    cv2.resizeWindow(WINDOW_NAME, screen_w, screen_h)
    cv2.imshow(WINDOW_NAME, pause_img)
    cv2.waitKey(1)

    while True:
        if check_quit_key():
            emergency_stop("'q' / ESC pressed during pause")

        if check_port_lost():
            emergency_stop("Serial port disconnected during pause")

        check_switch_faults()
        check_collision()

        try:
            line = msg_queue.get_nowait()
        except queue.Empty:
            continue

        if line == "SWITCH:RELEASED":
            print("[Python] Switch released — resuming.")
            cv2.destroyWindow(WINDOW_NAME)
            cv2.waitKey(1)
            return

        if line.startswith("DONE:") or line.startswith("ERROR:"):
            msg_queue.put(line)


# ======================================================================
#  STARTUP LIMIT-SWITCH GATE
#
#  Sends SELFTEST? and waits for the report. Both home limit switches
#  must come back OK. Anything else — including no reply — names the
#  switch on screen and exits BEFORE any motion command is sent.
#
#  This replaces the old behaviour where HOME{n}:FAULT was treated as a
#  soft "AWAY" and fell back to homeN: the current firmware aborts homing
#  on a switch fault and latches motion off, so that fallback could never
#  succeed and would only waste the 30 s command timeout.
# ======================================================================
def run_limit_switch_selftest(msg_queue):
    REPLY_TIMEOUT = 5.0

    print("[Python] Checking home limit switches (SELFTEST?) ...")

    _selftest_done.clear()
    _selftest_pass.clear()
    _selftest_fail.clear()
    with _hw_lock:
        _selftest_results.clear()

    if not guarded_write(b"SELFTEST?\n", "selftest"):
        emergency_stop("Failed to send SELFTEST?",
                       exit_code=HARDWARE_FAULT_EXIT_CODE)

    deadline = time.time() + REPLY_TIMEOUT
    while not _selftest_done.is_set():
        if check_port_lost():
            emergency_stop("Serial port disconnected during self-test",
                           exit_code=HARDWARE_FAULT_EXIT_CODE)
        if time.time() > deadline:
            show_limit_switch_fault_and_exit([("CONTROLLER", "NO_REPLY")])
        time.sleep(0.02)

    with _hw_lock:
        results = dict(_selftest_results)

    failures = []
    for comp in REQUIRED_COMPONENTS:
        status = results.get(comp)
        if status is None:
            failures.append((comp, "NO_REPLY"))
        elif status != "OK":
            failures.append((comp, status))

    if failures:
        show_limit_switch_fault_and_exit(failures)

    if _selftest_fail.is_set() or not _selftest_pass.is_set():
        show_limit_switch_fault_and_exit([("CONTROLLER", "SELFTEST_FAIL")])

    print("[Python] Limit switches OK: "
          + ", ".join(f"{k}={v}" for k, v in sorted(results.items())))
    print("[Python] Both home limit switches are interfaced and healthy — "
          "no replacement needed.\n")


def check_initial_collision(msg_queue):
    """Send CSTATUS? and halt immediately if the collision switch is
    already active at startup — mirrors wait_for_switch_released()'s
    STATUS? check, but for pin 3 instead of pin 2. Uses the event set
    directly by serial_reader rather than draining the queue, since
    _collision_event is authoritative regardless of queue timing."""
    REPLY_TIMEOUT = 3.0

    print("[Python] Checking collision switch via CSTATUS? ...")
    _collision_status_received.clear()

    if not guarded_write(b"CSTATUS?\n", "startup-cstatus"):
        emergency_stop("Failed to send CSTATUS?",
                       exit_code=HARDWARE_FAULT_EXIT_CODE)

    deadline = time.time() + REPLY_TIMEOUT
    while not _collision_status_received.is_set():
        if check_port_lost():
            emergency_stop("Serial port disconnected while querying CSTATUS?")
        if time.time() > deadline:
            print("[Python] WARNING: no reply to CSTATUS? within 3s — "
                  "assuming clear.")
            return
        time.sleep(0.02)

    if _collision_event.is_set():
        print("[Python] Collision switch is ACTIVE at startup.")
        show_collision_and_exit("Collision active at boot")
    else:
        print("[Python] Collision switch is CLEAR. Continuing.")


def check_home_state(motor_num, msg_queue):
    """
    Query the Arduino's PHYSICAL home-limit-switch state for motor
    `motor_num` (1 or 2), via HSTATUS1?/HSTATUS2?, and return one of
    "AT_HOME", "AWAY", or "FAULT".

    This exists because the firmware's position reference is only "how
    far have I moved since setup() ran". Since this script resets the
    Arduino (DTR toggle) on every connect, that reference is re-zeroed
    wherever the motor happened to be sitting — which is only true home
    if the motor was actually left there. The physical limit switch is
    the ground truth that distinguishes those two cases.

    CHANGED: "HOME{n}:FAULT" is no longer treated as a soft fallback to
    homeN. It means that switch's NO/NC contacts read an impossible
    state, and the firmware has latched motion off on that axis — homing
    cannot succeed. It now goes straight to the named replacement screen.
    """
    query = f"HSTATUS{motor_num}?"
    expect_prefix = f"HOME{motor_num}:"
    comp = f"M{motor_num}_SWITCH"

    # Drain stale queue messages BEFORE sending the query, so the reply
    # can't land in the queue and then be discarded as "stale".
    while not msg_queue.empty():
        try:
            msg_queue.get_nowait()
        except queue.Empty:
            break

    guarded_write((query + "\n").encode("utf-8"), label=query)

    deadline = time.time() + 3.0
    while time.time() < deadline:
        if check_port_lost():
            emergency_stop(f"Serial port disconnected while querying {query}")

        check_switch_faults()
        check_collision()

        try:
            line = msg_queue.get(timeout=0.05)
        except queue.Empty:
            continue

        if line.startswith(expect_prefix):
            state = line.split(":", 1)[1]   # "AT_HOME" / "AWAY" / "FAULT"
            if state == "FAULT":
                # The reply itself doesn't say ABSENT vs SHORT; if the
                # firmware's own FAULT line already told us, use that,
                # otherwise report the generic wiring fault.
                with _hw_lock:
                    status = _switch_faults.get(comp, "SHORT")
                print(f"[Python] Motor {motor_num} home limit switch "
                      f"reports a wiring fault (NO/NC mismatch). Motion is "
                      f"latched off on this axis — homing cannot run.")
                show_limit_switch_fault_and_exit([(comp, status)])
            return state

    print(f"[Python] WARNING: no reply to {query} within 3s — "
          f"assuming motor {motor_num} position is unverified.")
    return "AWAY"


def send_command_and_wait(command, msg_queue, pause_img):
    """
    Send a command via guarded_write and wait for DONE:/ERROR: response.

    Works unchanged for the blocking limit-switch commands (home1/home2
    -> DONE:HOME1/DONE:HOME2) and the fast confirm-only commands
    (gohome1/gohome2 -> DONE:GOHOME1/DONE:GOHOME2).

    Error paths from the current firmware, handled explicitly rather than
    as a generic ERROR: failure, so the operator is told what to replace
    or what happened:
        ERROR:SELFTEST_FAILED        -> motion refused; a limit switch is
                                        absent or shorted
        ERROR:HOMINGn_SWITCH_FAULT   -> the switch failed DURING the pass;
                                        homing aborted mid-move
        ERROR:HOMINGn_COLLISION_PROX -> NEW: the A0 collision prox tripped
                                        during this homing pass (early
                                        warning, unrelated to the axis's
                                        own home lever)

    Note: while home1/home2 run, the firmware sets homingActive and its
    main loop() — including the EARLY:/LIMIT:/FAULT: polling — does not
    run, so those lines cannot appear mid-homeN. The homing routine does
    emit FAULT:PROXn_REPLACE just before DONE:HOMEn if the switch caught
    the lever and the prox didn't; serial_reader records that in
    _prox_fault, and report_home_source() acts on it after this returns.
    """
    print(f"\n[Python] Sending: '{command}'")
    ok = guarded_write((command + "\n").encode("utf-8"), label=command)
    if not ok:
        print(f"[Python] Failed to send '{command}' — port may be dead.")
        return RESULT_FAIL

    deadline = time.time() + TIMEOUT

    while time.time() < deadline:
        if check_quit_key():
            emergency_stop("'q' / ESC pressed")

        if check_port_lost():
            emergency_stop(f"Serial port disconnected while waiting on '{command}'")

        # A switch reported absent/shorted at any point is fatal, and the
        # firmware will not finish this command anyway.
        check_switch_faults()
        check_collision()

        try:
            line = msg_queue.get(timeout=0.05)
        except queue.Empty:
            continue

        if line == "SWITCH:PRESSED":
            handle_switch_pressed(msg_queue, pause_img)
            deadline = time.time() + TIMEOUT
            continue

        if line.startswith("DONE:"):
            print(f"[Python] Confirmed: {line}")
            return RESULT_DONE

        # ---- homing ran out of travel / time without finding home ----
        if line in ("ERROR:HOMING1_NO_HOME_FOUND",
                    "ERROR:HOMING2_NO_HOME_FOUND"):
            n = 1 if "HOMING1" in line else 2
            show_home_not_found_and_exit(n)

        # ---- NEW: A0 collision prox early warning during homing ----
        if line in ("ERROR:HOMING1_COLLISION_PROX", "ERROR:HOMING2_COLLISION_PROX"):
            n = 1 if "HOMING1" in line else 2
            show_collision_prox_early_and_exit(n)

        # ---- operator pressed the manual stop mid-move ----
        # The firmware sends SWITCH:PRESSED first, so handle_switch_pressed()
        # above has usually already shown the pause image and waited for the
        # release by the time this line is read. Either way, re-issue the
        # command rather than treating a deliberate pause as a failure.
        if line in ("ERROR:HOMING1_MANUAL_STOP", "ERROR:HOMING2_MANUAL_STOP",
                    "ERROR:SHOOT1_MANUAL_STOP",  "ERROR:SHOOT2_MANUAL_STOP"):
            print(f"[Python] {line} — move aborted by the manual stop. "
                  f"Will retry once the switch is released.")
            return RESULT_RETRY

        # ---- motion refused because the boot self-test failed ----
        if line == "ERROR:SELFTEST_FAILED":
            with _hw_lock:
                failures = sorted(_switch_faults.items())
            if not failures:
                failures = [("CONTROLLER", "MOTION_BLOCKED")]
            show_limit_switch_fault_and_exit(failures)

        # ---- switch failed DURING the homing pass ----
        if line in ("ERROR:HOMING1_SWITCH_FAULT", "ERROR:HOMING2_SWITCH_FAULT"):
            n = 1 if "HOMING1" in line else 2
            comp = f"M{n}_SWITCH"
            with _hw_lock:
                status = _switch_faults.get(comp, "SHORT")
            print(f"[Python] Motor {n} homing aborted — its home limit "
                  f"switch failed mid-pass.")
            show_limit_switch_fault_and_exit([(comp, status)])

        if line.startswith("ERROR:"):
            print(f"[Python] Error received: {line}")
            return RESULT_FAIL

    print(f"[Python] TIMEOUT — no response within {TIMEOUT}s for '{command}'.")
    return RESULT_FAIL


def send_command_with_retry(command, msg_queue, pause_img):
    """Wrapper around send_command_and_wait() that re-issues the command
    if it was aborted by the manual stop. Returns True only on DONE.

    Before each retry we confirm the manual stop has actually been
    released — otherwise the firmware would abort the retry instantly and
    burn through the retry budget in a few milliseconds."""
    for attempt in range(1, MAX_HOME_RETRIES + 1):
        result = send_command_and_wait(command, msg_queue, pause_img)

        if result == RESULT_DONE:
            return True
        if result == RESULT_FAIL:
            return False

        # RESULT_RETRY — manual stop. Make sure it is released first.
        if attempt >= MAX_HOME_RETRIES:
            print(f"[Python] '{command}' aborted by the manual stop "
                  f"{attempt} times — giving up.")
            return False

        print(f"[Python] Confirming the manual stop is released before "
              f"retrying '{command}' (attempt {attempt + 1}"
              f"/{MAX_HOME_RETRIES}) ...")
        wait_for_switch_released(msg_queue, pause_img)

    return False


def wait_for_switch_released(msg_queue, pause_img):
    """
    Block until the Arduino confirms the switch is released, querying via
    STATUS? if needed. Called once at startup after READY handshake.

    The pause window is only created if a SWITCH:PRESSED message actually
    arrives, so it doesn't flash on every startup.

    STATUS? is sent AFTER draining stale queue messages, otherwise a fast
    reply could land in the queue and then be discarded by the drain loop
    itself, leaving this function waiting for a reply already thrown away.
    """
    while not msg_queue.empty():
        try:
            msg_queue.get_nowait()
        except queue.Empty:
            break

    print("[Python] Querying switch state via STATUS? ...")
    guarded_write(b"STATUS?\n", "startup")

    screen_w, screen_h = get_screen_resolution()
    window_shown = False

    while True:
        if check_quit_key():
            emergency_stop("'q' / ESC pressed during startup")

        if check_port_lost():
            emergency_stop("Serial port disconnected during startup")

        check_switch_faults()
        check_collision()

        try:
            line = msg_queue.get(timeout=0.05)
        except queue.Empty:
            continue

        if line == "SWITCH:RELEASED":
            print("[Python] Switch is open — proceeding.")
            if window_shown:
                cv2.destroyWindow(WINDOW_NAME)
                cv2.waitKey(1)
            return

        if line == "SWITCH:PRESSED":
            print("[Python] Switch is PRESSED — waiting for release ...")
            if not window_shown:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
                cv2.moveWindow(WINDOW_NAME, 0, 0)
                cv2.resizeWindow(WINDOW_NAME, screen_w, screen_h)
                cv2.imshow(WINDOW_NAME, pause_img)
                cv2.waitKey(1)
                window_shown = True


# -------------------------------------------------------
#  Watchdog — detects silent Arduino resets and cable pulls
# -------------------------------------------------------
def watchdog(stop_event):
    missed        = 0
    MAX_MISSED    = 2
    POLL_INTERVAL = 0.5
    elapsed = 0.0

    while not stop_event.is_set():
        # --- fast path: poll _port_lost in small increments ---
        if elapsed < WATCHDOG_INTERVAL:
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            if check_port_lost():
                print("[watchdog] Port-lost flag detected — triggering emergency stop.")
                emergency_stop("Watchdog: serial port disconnected")
            check_collision()
            continue

        elapsed = 0.0
        if stop_event.is_set():
            break

        # --- slow path: STATUS? ping/reply check ---
        _watchdog_reply_received.clear()

        sent = guarded_write(b"STATUS?\n", "watchdog")
        if not sent:
            missed += 1
            print(f"[watchdog] Failed to send ping (missed={missed}/{MAX_MISSED})")
        else:
            got_reply = _watchdog_reply_received.wait(timeout=WATCHDOG_REPLY_TIMEOUT)
            if got_reply:
                missed = 0
                continue
            else:
                missed += 1
                print(f"[watchdog] No reply to STATUS? ping (missed={missed}/{MAX_MISSED})")

        if check_port_lost():
            print("[watchdog] Port-lost flag detected — triggering emergency stop.")
            emergency_stop("Watchdog: serial port disconnected")

        check_collision()

        if missed >= MAX_MISSED:
            print("[watchdog] Arduino appears silent — triggering emergency stop.")
            emergency_stop("Watchdog: Arduino not responding")


def print_final_report(results):
    """results: {motor_num: (command, switch_status)} — a plain-text
    summary of what each sensor did, so the operator can see at a glance
    whether anything needs replacing."""
    print("\n" + "=" * 72)
    print("HARDWARE REPORT")
    print("=" * 72)
    with _hw_lock:
        selftest = dict(_selftest_results)
        prox     = dict(_prox_fault)

    for n in (1, 2):
        comp = f"M{n}_SWITCH"
        axis = "CHEST" if n == 1 else "EYES"
        sw   = selftest.get(comp, "UNKNOWN")
        cmd  = results.get(n, ("?", ""))[0]

        print(f"  Motor {n} ({axis}):")
        print(f"    Home limit switch : {sw}"
              + ("   [interfaced, healthy — no replacement needed]"
                 if sw == "OK" else "   [REPLACEMENT REQUIRED]"))
        if cmd.startswith("home"):
            if prox.get(n):
                print(f"    Limit switch      : TRIGGERED during homing")
                print(f"    Prox sensor {n}     : NOT DETECTED — "
                      f"REPLACEMENT REQUIRED")
            else:
                print(f"    Limit switch      : not reached (prox stopped "
                      f"the axis first — correct)")
                print(f"    Prox sensor {n}     : working")
        else:
            print(f"    Homing            : skipped ({cmd}) — already at home")
    print("=" * 72 + "\n")


def main():
    global _ser, _stop_event, _reader, _device_path

    list_available_ports()

    SERIAL_PORT = find_arduino()
    if SERIAL_PORT is None:
        print("[ERROR] Arduino not found. Check USB connection and try again.")
        sys.exit(1)

    print(f"[INFO] Auto-detected Arduino on {SERIAL_PORT}")
    print(f"Connecting to Arduino on {SERIAL_PORT} at {BAUD_RATE} baud...")

    try:
        _ser = serial.Serial(
            SERIAL_PORT,
            BAUD_RATE,
            timeout=2,           # read timeout — keeps serial_reader responsive
            write_timeout=1.0,   # bounded write instead of hanging
        )
    except serial.SerialException as e:
        print(f"\n[ERROR] Could not open port: {e}")
        return

    _device_path = SERIAL_PORT

    # DTR toggle: force Arduino reset so Python never misses boot messages.
    # reset_input_buffer() is safe here — serial_reader has not started yet.
    _ser.dtr = False
    time.sleep(0.1)
    _ser.dtr = True
    _ser.reset_input_buffer()
    time.sleep(0.1)

    pause_img   = load_pause_image()
    msg_queue   = queue.Queue()
    _stop_event = threading.Event()

    _reader = threading.Thread(
        target=serial_reader,
        args=(_ser, msg_queue, _stop_event),
        daemon=True,
        name="SerialReader",
    )
    _reader.start()
    print("[Python] Serial reader thread started.")
    print("[Python] Press Ctrl+C or 'q' / ESC at any time to stop safely.\n")

    # ── Wait for READY (Arduino sends it every 500 ms until OK received) ──
    print("[Python] Waiting for Arduino READY ...")
    ready_deadline = time.time() + 10.0
    while True:
        if time.time() > ready_deadline:
            print("[ERROR] Timed out waiting for Arduino READY. Exiting.")
            emergency_stop("READY timeout")

        if check_port_lost():
            emergency_stop("Serial port disconnected while waiting for READY")

        # CHANGED: a switch fault reported during boot is no longer just
        # logged and ignored. The firmware's boot self-test has already
        # latched motion off, so there is nothing to wait for — halt now
        # with the named replacement message.
        check_switch_faults()
        check_collision()

        try:
            line = msg_queue.get(timeout=0.1)
        except queue.Empty:
            continue

        if line == "READY":
            guarded_write(b"OK\n", "handshake")
            print("[Python] Handshake complete — sent OK to Arduino.\n")
            break

        if line in ("SWITCH:PRESSED", "SWITCH:RELEASED"):
            msg_queue.put(line)   # re-queue for startup check
        # COLLISION:ACTIVE / COLLISION:CLEAR are no longer re-queued here:
        # serial_reader already records them in _collision_event directly,
        # which check_initial_collision() reads after the handshake completes.

    # ── HARDWARE GATE: both limit switches must be healthy ──
    run_limit_switch_selftest(msg_queue)

    # ── Block until switch is confirmed released (sends its own STATUS?) ──
    print("[Python] Checking initial switch state...")
    wait_for_switch_released(msg_queue, pause_img)

    # ── Collision switch (pin 3) must also be clear before homing starts ──
    check_initial_collision(msg_queue)

    # ── Start watchdog AFTER handshake so it doesn't race with READY/OK ──
    _watchdog_thread = threading.Thread(
        target=watchdog,
        args=(_stop_event,),
        daemon=True,
        name="Watchdog",
    )
    _watchdog_thread.start()
    print("[Python] Watchdog thread started.\n")

    # ------------------------------------------------------------------
    # Startup return-to-home checks PHYSICAL ground truth (the limit
    # switch, via HSTATUS1?/HSTATUS2?) before deciding how to get each
    # motor home:
    #
    #   AT_HOME -> the position reference set at boot already corresponds
    #              to true home, so the fast confirm-only gohomeN is safe.
    #
    #   AWAY    -> the motor was left somewhere other than true home, so
    #              the reference is not trustworthy. Fall back to the
    #              physical homeN, which drives to the real end of travel
    #              (prox-primary, switch-backup) and resyncs there.
    #
    #   FAULT   -> CHANGED: no longer falls back to homeN. The switch's
    #              NO/NC contacts read an impossible state, the firmware
    #              has latched motion off on that axis, and homing cannot
    #              succeed. check_home_state() halts with the named
    #              replacement screen instead.
    # ------------------------------------------------------------------
    print("[Python] Checking physical home-limit state for each motor...\n")

    home1_state = check_home_state(1, msg_queue)
    print(f"[Python] Motor 1 physical state: {home1_state}")
    command1 = "gohome1" if home1_state == "AT_HOME" else "home1"

    home2_state = check_home_state(2, msg_queue)
    print(f"[Python] Motor 2 physical state: {home2_state}")
    command2 = "gohome2" if home2_state == "AT_HOME" else "home2"

    print("\n[Python] Returning motors to home position...\n")
    results = {}

    # --- Step 1: Return Motor 1 (chest) to home ---
    success = send_command_with_retry(command1, msg_queue, pause_img)
    if not success:
        print("[Python] Motor 1 return-to-home failed. Aborting.")
        emergency_stop("Motor 1 return-to-home failed",
                       exit_code=HARDWARE_FAULT_EXIT_CODE)

    print("[Python] Motor 1 returned to home position.")
    results[1] = (command1, home1_state)
    # Did the prox stop it, or did the limit switch have to? If the switch
    # did, prox 1 needs replacing and this exits with the alert.
    report_home_source(1, command1)

    # --- Step 2: Return Motor 2 (eyes) to home ---
    success = send_command_with_retry(command2, msg_queue, pause_img)
    if not success:
        print("[Python] Motor 2 return-to-home failed.")
        emergency_stop("Motor 2 return-to-home failed",
                       exit_code=HARDWARE_FAULT_EXIT_CODE)

    print("[Python] Motor 2 returned to home position.")
    results[2] = (command2, home2_state)
    report_home_source(2, command2)

    # --- Done ---
    print("\n[Python] Both motors are back at their home positions.")
    print_final_report(results)

    _stop_event.set()
    _reader.join(timeout=2)
    with _serial_lock:
        if _ser.is_open:
            _ser.close()
    cv2.destroyAllWindows()
    print("[Python] Serial port closed. Exiting.")


if __name__ == "__main__":
    main()
