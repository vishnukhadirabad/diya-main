# ======================================================================
# shoot_hardened.py — robust shoot sequencer (Uno R3 build)
#
# Works with the Arduino sketch that:
#   • sends READY every 500 ms until "OK\n" is received, then confirms
#     with SYSTEM:READY
#   • runs a limit-switch self-test at boot AND on demand via SELFTEST?
#     (M1 switch / M2 switch / collision switch, each OK|ABSENT|SHORT)
#   • sets shootUnlocked on OK, then accepts "shoot m1" / "shoot m2"
#   • refuses "shoot m1"/"shoot m2" with ERROR:SELFTEST_FAILED if the
#     boot self-test failed OR the collision switch wiring is faulted
#   • replies "shoot success" on completion
#   • may send SWITCH:PRESSED / COLLISION:ACTIVE / FAULT:* / ERROR:* at
#     any time
#
# This build resets the board via a DTR bounce (FIX-1), which works
# because the Uno R3's onboard USB-serial bridge chip wires DTR through
# a capacitor straight to the reset pin — toggling DTR from pyserial
# forces a clean hardware reset before every run, and the serial handle
# survives that reset (unlike native-USB boards, where the USB device
# itself disconnects/reconnects on reset).
#
# All FIX-N comments map to the risk analysis below.
# ======================================================================

import serial
import serial.tools.list_ports
import time
import sys

# ── tunables ────────────────────────────────────────────────────────────
BAUD             = 115200
READY_TIMEOUT_S  = 15.0    # FIX-8: give up if READY never arrives
SELFTEST_TIMEOUT_S = 5.0   # FIX-9: give up if SELFTEST:END never arrives
SHOOT_TIMEOUT_S  = 60.0    # FIX-2: max time to wait for "shoot success"
DTR_SETTLE_S     = 0.6     # FIX-1: long enough for Uno's USB-serial re-enum
POST_DTR_SETTLE  = 0.25    # FIX-1: extra settle after reset_input_buffer
WRITE_TIMEOUT_S  = 1.0     # FIX-7: ser.write() never blocks forever
# ────────────────────────────────────────────────────────────────────────


# ======================================================================
# Human-readable text for the firmware's named FAULT: lines.
# FIX-9: the firmware's home/collision switches report WHICH switch and
#         WHICH failure mode (ABSENT vs SHORT) so the operator can be
#         told exactly what to replace — surface that instead of just
#         echoing the raw token.
# ======================================================================
FAULT_MESSAGES = {
    "FAULT:M1_SWITCH_ABSENT":        "M1 home limit switch not detected (wiring/COM issue).",
    "FAULT:M1_SWITCH_SHORT":         "M1 home limit switch wiring is shorted.",
    "FAULT:M2_SWITCH_ABSENT":        "M2 home limit switch not detected (wiring/COM issue).",
    "FAULT:M2_SWITCH_SHORT":         "M2 home limit switch wiring is shorted.",
    "FAULT:COLLISION_SWITCH_ABSENT": "Collision switch not detected (wiring/COM issue).",
    "FAULT:COLLISION_SWITCH_SHORT":  "Collision switch wiring is shorted.",
    "FAULT:PROX1_REPLACE":           "PROX 1 sensor did not trip before the M1 limit switch — replacement required.",
    "FAULT:PROX2_REPLACE":           "PROX 2 sensor did not trip before the M2 limit switch — replacement required.",
}


def describe_fault(line: str) -> str:
    """Return a human-readable description for a FAULT: line, or the raw line."""
    for token, msg in FAULT_MESSAGES.items():
        if line.startswith(token):
            return msg
    return line


# ======================================================================
# Arduino auto-detection
# ======================================================================
def find_arduino():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        hwid = (port.hwid  or "").lower()
        if "ttyACM" in port.device or "arduino" in desc or "2341" in hwid:
            return port.device
    for port in ports:
        if "ttyACM" in port.device:
            return port.device
    return None


PORT = find_arduino()
if PORT is None:
    print("[ERROR] Arduino not found. Check USB connection and try again.")
    sys.exit(1)
print(f"[INFO] Auto-detected Arduino on {PORT}")


# ======================================================================
# Guarded write helper
# FIX-5: wrap every ser.write() so a SerialException / WriteTimeout
#         is caught and surfaced cleanly rather than crashing the script.
# ======================================================================
def safe_write(ser: serial.Serial, data: bytes, tag: str = "") -> bool:
    """Write *data* to *ser*.  Returns True on success, False on any error."""
    try:
        n = ser.write(data)
        if n != len(data):
            print(f"[WARN]{' ' + tag if tag else ''} partial write ({n}/{len(data)} bytes)")
        return True
    except serial.SerialTimeoutException:
        print(f"[ERROR]{' ' + tag if tag else ''} write timeout — Arduino not consuming data")
        return False
    except serial.SerialException as e:
        print(f"[ERROR]{' ' + tag if tag else ''} SerialException on write: {e}")
        return False
    except Exception as e:
        print(f"[ERROR]{' ' + tag if tag else ''} unexpected write error: {e}")
        return False


# ======================================================================
# READY handshake
# FIX-8: hard deadline so we never hang if the Arduino never sends READY
#         (wrong firmware, stuck in homing, port wrong, etc.).
# ======================================================================
def wait_for_ready(ser: serial.Serial) -> bool:
    """
    Block until READY is received (then ACK with OK) or READY_TIMEOUT_S elapses.
    Returns True on success, False on timeout or port error.

    Any FAULT: line seen here (e.g. from the firmware's boot self-test,
    which runs before the READY loop starts) is surfaced immediately —
    it does not block the handshake itself (the firmware still sends
    READY regardless), but the operator should see it right away rather
    than only after a later shoot command is rejected.
    """
    print("Waiting for Arduino READY ...")
    deadline = time.monotonic() + READY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            raw  = ser.readline()
            line = raw.decode("utf-8", errors="replace").strip()
        except serial.SerialException as e:
            print(f"[ERROR] Serial lost while waiting for READY: {e}")
            return False

        if line:
            print(f"[Arduino] {line}")

        if line.startswith("FAULT:"):
            print(f"[WARN] {describe_fault(line)}")

        if "READY" in line:
            # FIX-5: use safe_write for the OK ACK
            if not safe_write(ser, b"OK\n", "handshake"):
                return False

            # FIX-9: confirm the firmware actually processed OK. This is
            # a short best-effort read, not another hard gate — if it
            # doesn't arrive we still proceed, since shootUnlocked was
            # already set server-side the moment OK was parsed.
            ack_deadline = time.monotonic() + 2.0
            while time.monotonic() < ack_deadline:
                raw  = ser.readline()
                ack  = raw.decode("utf-8", errors="replace").strip()
                if ack:
                    print(f"[Arduino] {ack}")
                if ack == "SYSTEM:READY":
                    break

            print("[INFO] Handshake complete.")
            return True

        # Inform but don't abort on other startup messages
        if "SWITCH:PRESSED" in line:
            print("[WARN] Emergency switch is pressed at startup — aborting.")
            return False
        if "COLLISION:ACTIVE" in line:
            print("[WARN] Collision active at startup — aborting.")
            return False

    print(f"[ERROR] Timed out after {READY_TIMEOUT_S:.0f}s waiting for READY.")
    return False


# ======================================================================
# Explicit self-test
# FIX-9: the firmware gates every "shoot m1"/"shoot m2" on
#         (selftestFailed || collisionSwitchFaultBlock) and answers with
#         ERROR:SELFTEST_FAILED if either is set — but the boot self-test
#         output races the DTR reset and can be lost before wait_for_ready
#         starts reading. Query SELFTEST? explicitly, after the handshake,
#         for a deterministic result instead of relying on catching the
#         boot-time run.
# ======================================================================
def run_selftest(ser: serial.Serial) -> bool:
    """
    Send SELFTEST? and parse the SELFTEST:BEGIN ... SELFTEST:END block.
    Returns True only on SELFTEST:PASS. Prints a human-readable reason
    for every failing switch on SELFTEST:FAIL.
    """
    print("\n[INFO] Running limit-switch self-test ...")
    if not safe_write(ser, b"SELFTEST?\n", "selftest"):
        return False

    deadline = time.monotonic() + SELFTEST_TIMEOUT_S
    saw_begin = False
    passed = None
    failures = []

    while time.monotonic() < deadline:
        try:
            raw  = ser.readline()
            line = raw.decode("utf-8", errors="replace").strip()
        except serial.SerialException as e:
            print(f"[ERROR] Serial lost during self-test: {e}")
            return False

        if not line:
            continue

        print(f"[Arduino] {line}")

        if line == "SELFTEST:BEGIN":
            saw_begin = True
            continue

        if line.startswith("TEST:") and ("ABSENT" in line or "SHORT" in line):
            failures.append(line)
            continue

        if line == "SELFTEST:PASS":
            passed = True
            continue

        if line == "SELFTEST:FAIL":
            passed = False
            continue

        if line == "SELFTEST:END":
            break

    if not saw_begin or passed is None:
        print(f"[ERROR] Self-test did not complete within {SELFTEST_TIMEOUT_S:.0f}s.")
        return False

    if not passed:
        print("[ERROR] Self-test FAILED — refusing to shoot:")
        for f in failures:
            # e.g. "TEST:M1_SWITCH=ABSENT" -> readable name
            switch, _, mode = f.partition("=")
            print(f"  - {switch.replace('TEST:', '').replace('_', ' ')}: {mode}")
        return False

    print("[INFO] Self-test passed.")
    return True


# ======================================================================
# Collision-prox (A0) startup check
# FIX-11: check A0's raw state BEFORE issuing any shoot command, the same
#         "already at home" pattern the alignment scripts use for M1/M2 —
#         applied here to the collision prox instead. Without this, an
#         obstruction already sitting in the collision zone at startup
#         would only be caught once a shoot pass actually begins (via
#         checkForCollisionProxEarly() inside shootMotor1()/shootMotor2()),
#         rather than before any motion is attempted at all.
# ======================================================================
def check_collision_prox(ser: serial.Serial) -> bool:
    """
    Send PSTATUSC? and confirm the A0 collision prox is CLEAR before
    proceeding. Returns True if clear, False if triggered, unreachable,
    or timed out (any of which should abort the run).
    """
    print("\n[INFO] Checking collision prox (A0) before shooting ...")
    if not safe_write(ser, b"PSTATUSC?\n", "pstatusC"):
        return False

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            raw  = ser.readline()
            line = raw.decode("utf-8", errors="replace").strip()
        except serial.SerialException as e:
            print(f"[ERROR] Serial lost during collision-prox check: {e}")
            return False

        if not line:
            continue

        print(f"[Arduino] {line}")

        if line == "PROXC:CLEAR":
            print("[INFO] Collision prox (A0) is clear.")
            return True
        if line == "PROXC:TRIGGERED":
            print("[ERROR] Collision prox (A0) is already triggered — "
                  "obstruction present. Clear it before shooting.")
            return False

    print("[ERROR] No reply to PSTATUSC? within 3s.")
    return False


# ======================================================================
# send_shoot()
# FIX-2: hard deadline (SHOOT_TIMEOUT_S) so we never loop forever.
# FIX-3: SerialException caught and re-raised as a clean return value.
# FIX-4: Arduino error/abort/event messages are acted on, not just printed.
# FIX-10: ERROR:SELFTEST_FAILED means the command was rejected outright
#         (selftestFailed or collisionSwitchFaultBlock latched on the
#         firmware side) — the shoot never started, so fail fast instead
#         of waiting out the full SHOOT_TIMEOUT_S for a "shoot success"
#         that will never arrive.
# ======================================================================
def send_shoot(ser: serial.Serial, motor: str) -> bool:
    """
    Send "shoot <motor>" and wait for "shoot success".

    Returns True on success.
    Returns False on timeout, port error, or any Arduino-reported abort.

    Motor must be "m1" or "m2".
    """
    cmd = f"shoot {motor}\n"
    print(f"\n[INFO] Sending: shoot {motor}")

    # FIX-5: guard the command write
    if not safe_write(ser, cmd.encode("utf-8"), f"shoot {motor}"):
        return False

    deadline = time.monotonic() + SHOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            raw  = ser.readline()
            line = raw.decode("utf-8", errors="replace").strip()
        except serial.SerialException as e:
            # FIX-3: port died mid-shoot — surface cleanly
            print(f"[ERROR] Serial lost during shoot {motor}: {e}")
            return False

        if not line:
            # readline() timed out (ser.timeout=5) — check our deadline
            continue

        print(f"[Arduino] {line}")

        # ── success ────────────────────────────────────────────────
        if "shoot success" in line:
            print(f"[INFO] ✓ shoot {motor} complete")
            return True

        # ── FIX-10: command was rejected outright, nothing is running ──
        if "ERROR:SELFTEST_FAILED" in line:
            print(f"[ERROR] shoot {motor} rejected — self-test failed or "
                  f"collision switch faulted. Run the self-test to see which.")
            return False

        # ── FIX-4: hard abort conditions ───────────────────────────
        if "SWITCH:PRESSED" in line:
            print(f"[ERROR] Emergency switch pressed during shoot {motor} — aborting.")
            return False

        if "COLLISION:ACTIVE" in line or "collision:occured" in line.lower():
            print(f"[ERROR] Collision detected during shoot {motor}: mechanical switch — aborting.")
            return False

        # FIX-11: distinguish the A0 early-warning prox abort from the
        # generic "ERROR:SHOOT" catch below — same underlying cause as
        # ERROR:HOMINGn_COLLISION_PROX, just reachable from shootMotorN()
        # now too. Caught before the generic prefix match so the operator
        # sees which sensor actually fired.
        if "ERROR:SHOOT" in line and "COLLISION_PROX" in line:
            print(f"[ERROR] Collision detected during shoot {motor}: proximity sensor (A0) "
                  f"— obstruction caught before mechanical contact.")
            return False

        # FIX-9: named switch/collision wiring faults — decode for the operator
        if line.startswith("FAULT:"):
            print(f"[WARN] {describe_fault(line)}")

        # FIX-4: Arduino itself aborted the shoot (STOP received, collision, etc.)
        if line.startswith("ERROR:SHOOT"):
            print(f"[ERROR] Arduino aborted shoot {motor}: {line}")
            return False

        # General Arduino error — log but keep waiting
        # (Arduino may still complete and send "shoot success")
        if line.startswith("ERROR:"):
            print(f"[WARN] Arduino error during shoot {motor}: {line}")

        # FIX-4: if shoot was attempted while locked the Arduino replies
        # immediately with ERROR:SHOOT_LOCKED — no point waiting further
        if "SHOOT_LOCKED" in line:
            print(f"[ERROR] Arduino reports SHOOT_LOCKED — handshake may have failed.")
            return False

    print(f"[ERROR] Timed out after {SHOOT_TIMEOUT_S:.0f}s waiting for shoot {motor} to complete.")
    return False


# ======================================================================
# Main — FIX-6: entire serial lifecycle inside try/finally so the port
#         is always closed cleanly even if an exception escapes.
# ======================================================================
ser = None
try:
    print(f"[INFO] Connecting to {PORT} at {BAUD} baud ...")

    # FIX-7: write_timeout prevents ser.write() from blocking indefinitely
    ser = serial.Serial(
        PORT,
        BAUD,
        timeout=5,               # readline() returns after 5 s of silence
        write_timeout=WRITE_TIMEOUT_S,
    )

    # FIX-1: proper DTR bounce — forces a clean Arduino reset. This works
    # on the Uno R3 because its USB-serial bridge chip wires DTR through
    # a capacitor to the reset pin, and (unlike native-USB boards) the
    # serial connection itself survives the reset.
    ser.dtr = False
    time.sleep(DTR_SETTLE_S)
    ser.dtr = True
    ser.reset_input_buffer()
    time.sleep(POST_DTR_SETTLE)

    # ── Handshake ───────────────────────────────────────────────────────
    if not wait_for_ready(ser):
        print("[ERROR] Could not establish handshake. Exiting.")
        sys.exit(1)

    # ── Self-test ──────────────────────────────────────────────────────
    # FIX-9: gate the whole run on this, exactly like the firmware gates
    # "shoot m1"/"shoot m2" on selftestFailed / collisionSwitchFaultBlock.
    if not run_selftest(ser):
        print("[ERROR] Self-test failed. Replace the named switch(es) and retry.")
        sys.exit(1)

    # ── Collision-prox check ──────────────────────────────────────────
    # FIX-11: confirm A0 is clear BEFORE issuing "shoot m1", not just
    # reactively while a shoot pass is already underway.
    if not check_collision_prox(ser):
        print("[ERROR] Collision prox (A0) check failed. Clear the obstruction and retry.")
        sys.exit(1)

    # ── Shoot sequence ──────────────────────────────────────────────────
    if not send_shoot(ser, "m1"):
        print("[ERROR] shoot m1 failed. Sending STOP and exiting.")
        safe_write(ser, b"STOP\n", "abort")
        sys.exit(1)

    if not send_shoot(ser, "m2"):
        print("[ERROR] shoot m2 failed. Sending STOP and exiting.")
        safe_write(ser, b"STOP\n", "abort")
        sys.exit(1)

    print("\n[INFO] All done.")

except serial.SerialException as e:
    # FIX-3: top-level port error (e.g. device unplugged before open)
    print(f"[FATAL] Serial port error: {e}")
    sys.exit(1)

except KeyboardInterrupt:
    print("\n[INFO] Interrupted by user — sending STOP.")
    if ser and ser.is_open:
        safe_write(ser, b"STOP\n", "KeyboardInterrupt")

finally:
    # FIX-6: always close the port, even on exception or sys.exit()
    # (sys.exit() raises SystemExit which is caught by finally)
    if ser and ser.is_open:
        try:
            ser.close()
            print("[INFO] Serial port closed.")
        except Exception as e:
            print(f"[WARN] Error closing serial port: {e}")
