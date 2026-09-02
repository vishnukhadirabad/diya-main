import serial
import struct
import time

from camera_utils import get_ld2410_port
from ld2410_config import LD2410Config, mm_to_gate, GATE_SIZE_MM

# ============ CONFIG ============
COM_PORT = get_ld2410_port()    # auto-detected via camera_utils.py (CP2102 by-id / VID:PID)
BAUD_RATE = 256000              # LD2410C default baud rate

SEAT_DISTANCE_MM = 850          # distance from kiosk (sensor) to the seat
                                 # UPDATED with seat geometry:
                                 #   sensor height  = 770mm off the floor
                                 #   seat height    = 450mm
                                 #   horizontal gap = 800-900mm (midpoint 850mm)
                                 # The LD2410 reports slant (line-of-sight) range,
                                 # not horizontal distance. For a SEATED person,
                                 # the torso/chest reflection point sits roughly
                                 # 350-450mm above the seat surface -> ~800-900mm
                                 # above the floor, which is within ~30-130mm of
                                 # the sensor's own 770mm height. Pythagoras with
                                 # that small a vertical offset adds well under
                                 # 10mm to the horizontal distance at this range,
                                 # so for a seated person slant range ~= horizontal
                                 # range -- 850mm is used directly as the sensor
                                 # target, no separate slant correction needed.
                                 #
                                 # CAVEAT: the earlier field log (STANDING person)
                                 # showed the sensor under-reporting relative to
                                 # true horizontal distance, which is the opposite
                                 # of what pure slant geometry would predict for a
                                 # much-higher standing torso. That points to some
                                 # sensor-side undershoot behavior independent of
                                 # geometry. The tolerance below is kept generous
                                 # to absorb that; re-tune SEAT_DISTANCE_MM/
                                 # SEAT_TOLERANCE_MM from real seated-test log
                                 # values once available, rather than trusting the
                                 # geometry alone.
SEAT_TOLERANCE_MM = 200         # +/- tolerance band around seat distance (band: 650-1050mm)
CONFIRM_SECONDS = 5             # continuous seconds required to confirm "sat down"
# =================================

SEAT_MIN_MM = SEAT_DISTANCE_MM - SEAT_TOLERANCE_MM
SEAT_MAX_MM = SEAT_DISTANCE_MM + SEAT_TOLERANCE_MM

# ---- ADD: sensor-side range capping (Option 4) ----
# This uses the LD2410's own configuration protocol (separate from the
# data-frame protocol above) to cap the RADAR's max reporting gate just
# past the seat. Once set, the module itself never reports a target
# beyond that range -- it's a hard cutoff enforced in the sensor's
# firmware, not a filter applied afterwards in this script.
#
# IMPORTANT CAVEAT: this does NOT fix someone standing beside the sensor
# at the SAME distance as the seat -- the LD2410 has a ~120 deg field of
# view and reports distance only, never angle, so lateral position is
# fundamentally invisible to it. This only stops people/objects FARTHER
# away (beyond the seat) from ever registering, and lets the seat's own
# gate be tuned independently of farther-out gates. Fixing the lateral
# case requires physically narrowing the sensor's field of view (a
# radome/tube in front of the antenna, RF shielding on the sides, etc).
ENABLE_RANGE_CAPPING = True

# Cap this far PAST SEAT_MAX_MM (not exactly at it), so normal tolerance
# jitter near the edge of the seat band doesn't get clipped by the
# module's own hard cutoff.
RANGE_CAP_MARGIN_MM = 200

# How long (seconds) the radar itself waits with nothing detected before
# it settles into a stable "no target" report. This is a module-side
# debounce, separate from EXIT_DEBOUNCE_FRAMES below (which debounces on
# our own frame-by-frame reads).
NO_ONE_DURATION_S = 2

# Optional per-gate sensitivity overrides, applied AFTER range capping.
# Key = gate index (0 to MAX_GATE_INDEX), value = (motion_sensitivity,
# static_sensitivity), each 0-100 (higher = triggers on weaker signals).
# Leave a gate out to keep its existing/factory sensitivity.
#
# Practical starting point: raise static sensitivity a little on the
# gate that covers SEAT_DISTANCE_MM if a seated, mostly-still person is
# being missed (static reflections from a seated body are weaker than a
# standing/moving one); lower sensitivity on gates closer than the seat
# if people just walking up to the kiosk keep triggering false detects.
#
# NOTE: the captured log showed frequent moving_energy dropouts to 0
# even while a person stood in front of the sensor (see the ambiguous-
# frame handling below). If that persists after the debounce fix, raise
# motion sensitivity on the gate covering SEAT_DISTANCE_MM here, e.g.:
#   mm_to_gate(SEAT_DISTANCE_MM): (60, 40),
GATE_SENSITIVITY_OVERRIDES = {
    # mm_to_gate(SEAT_DISTANCE_MM): (50, 40),
}

# An inanimate object (bag, box, etc.) left on the seat shows pure Static (state 2)
# with moving_energy staying at 0 continuously. A real person will show at least
# occasional Moving+Static (state 3) or brief moving_energy blips even while mostly
# still (breathing, weight shifts, etc). This flag requires at least one such blip
# before confirming presence, to reduce false triggers from left-behind objects.
REQUIRE_MOTION_BLIP = True

# ---- ADD: exit-debounce ----
# Real-world logs show a person standing/sitting still can still produce brief
# out-of-band readings (multipath/ghosting off the kiosk body, walls, or seat --
# e.g. moving_distance suddenly jumping to 1300mm for one frame then snapping
# back). Previously ANY single out-of-band frame reset the whole confirm timer,
# which could repeatedly restart a genuine person's countdown or even prevent
# it from ever completing in a busier environment. Now we only reset the timer
# after EXIT_DEBOUNCE_FRAMES consecutive out-of-band frames, absorbing brief
# excursions without losing real "the person actually left" transitions.
EXIT_DEBOUNCE_FRAMES = 5

# ---- change-gated logging thresholds ----
# Only print a status line when something meaningfully changed, instead of on
# every single incoming frame (LD2410 streams several updates/sec, so raw
# per-frame printing floods the terminal and adds I/O overhead in a
# long-running kiosk process).
DISTANCE_CHANGE_THRESHOLD_MM = 50   # ignore jitter smaller than this
ENERGY_CHANGE_THRESHOLD      = 10   # ignore energy jitter smaller than this
HEARTBEAT_SECONDS            = 30   # print a status line at least this often,
                                     # even if nothing changed, so you know
                                     # the script/sensor is still alive

FRAME_HEADER = b'\xF4\xF3\xF2\xF1'
FRAME_FOOTER = b'\xF8\xF7\xF6\xF5'

STATE_LABELS = {
    0: "No target",
    1: "Moving target",
    2: "Static target",
    3: "Moving + Static",
}


def parse_frame(payload: bytes):
    """Parses the LD2410 basic target-data frame payload."""
    if len(payload) < 11:
        return None
    try:
        target_state = payload[2]
        moving_distance_cm = struct.unpack('<H', payload[3:5])[0]
        moving_energy = payload[5]
        static_distance_cm = struct.unpack('<H', payload[6:8])[0]
        static_energy = payload[8]
        detection_distance_cm = struct.unpack('<H', payload[9:11])[0]
        return {
            "target_state": target_state,
            "moving_distance_mm": moving_distance_cm * 10,
            "moving_energy": moving_energy,
            "static_distance_mm": static_distance_cm * 10,
            "static_energy": static_energy,
            "detection_distance_mm": detection_distance_cm * 10,
        }
    except Exception:
        return None


def in_seat_range(frame):
    """
    Returns a (in_range, ambiguous) tuple:

      in_range  = True if a reliable target reading falls within the
                  seat's distance band (SEAT_MIN_MM to SEAT_MAX_MM).

      ambiguous = True if this frame gave us no reliable distance to
                  judge at all (target_state claims Moving and/or
                  Static but the matching energy reading is 0).

    UPDATED (bug fix): this used to fall back to
    frame["detection_distance_mm"] whenever moving/static energy was 0,
    which is a general "something is out there" distance, NOT
    necessarily where the actual target is. The captured log showed
    target_state == Moving with moving_energy == 0 very frequently
    (an LD2410 quirk -- state and energy aren't always in sync frame to
    frame), and detection_distance_mm sat around 550mm during those
    frames -- outside the seat band -- so those frames were being
    wrongly counted as "person left," repeatedly resetting the confirm
    timer before it could ever reach CONFIRM_SECONDS.

    Now an energy-0 frame is reported as ambiguous instead, and the
    caller treats ambiguous frames as neutral: they neither confirm
    presence nor count toward the exit debounce.
    """
    state = frame["target_state"]
    if state == 0:
        return False, False

    candidates = []
    if state in (1, 3) and frame["moving_energy"] > 0:
        candidates.append(frame["moving_distance_mm"])
    if state in (2, 3) and frame["static_energy"] > 0:
        candidates.append(frame["static_distance_mm"])

    if not candidates:
        return False, True  # ambiguous: no trustworthy distance this frame

    return any(SEAT_MIN_MM <= d <= SEAT_MAX_MM for d in candidates), False


def frame_changed(frame, last_logged):
    """
    Returns True if this frame differs meaningfully from the last one we
    printed: a target_state transition always logs; otherwise only log if
    a distance/energy reading moved beyond its noise threshold.
    """
    if last_logged is None:
        return True

    if frame["target_state"] != last_logged["target_state"]:
        return True

    if abs(frame["moving_distance_mm"] - last_logged["moving_distance_mm"]) >= DISTANCE_CHANGE_THRESHOLD_MM:
        return True
    if abs(frame["static_distance_mm"] - last_logged["static_distance_mm"]) >= DISTANCE_CHANGE_THRESHOLD_MM:
        return True
    if abs(frame["detection_distance_mm"] - last_logged["detection_distance_mm"]) >= DISTANCE_CHANGE_THRESHOLD_MM:
        return True

    if abs(frame["moving_energy"] - last_logged["moving_energy"]) >= ENERGY_CHANGE_THRESHOLD:
        return True
    if abs(frame["static_energy"] - last_logged["static_energy"]) >= ENERGY_CHANGE_THRESHOLD:
        return True

    return False


def log_frame(frame, reason=""):
    """Prints one status line for the given frame."""
    state_text = STATE_LABELS.get(frame["target_state"], "Unknown")
    tag = f" ({reason})" if reason else ""
    print(
        f"State: {state_text:<16} | "
        f"Moving: {frame['moving_distance_mm']:>5} mm (energy {frame['moving_energy']:>3}) | "
        f"Static: {frame['static_distance_mm']:>5} mm (energy {frame['static_energy']:>3}) | "
        f"Detection: {frame['detection_distance_mm']:>5} mm{tag}"
    )


def configure_range_capping(ser):
    """
    Applies Option 4: uses the LD2410 config protocol to cap the radar's
    own max detection gate just past the seat, plus any per-gate
    sensitivity overrides in GATE_SENSITIVITY_OVERRIDES.

    Must run BEFORE the normal target-data stream is read -- the radar
    suspends its normal F4F3F2F1...F8F7F6F5 output while in config mode,
    so this has to happen at startup, not interleaved with the main loop.

    Failure here is treated as non-fatal: if configuration doesn't apply
    cleanly, we print a clear warning and continue with the sensor's
    existing configuration rather than aborting the whole kiosk process.
    """
    cfg = LD2410Config(ser)
    entered = False
    try:
        cfg.enter_config_mode()
        entered = True

        cap_gate = mm_to_gate(SEAT_MAX_MM + RANGE_CAP_MARGIN_MM)
        cap_range_mm = (cap_gate + 1) * GATE_SIZE_MM
        print(f"[CONFIG] Capping max moving/static gate to {cap_gate} "
              f"(~{cap_range_mm} mm) ...")
        cfg.set_max_gate(cap_gate, cap_gate, NO_ONE_DURATION_S)

        for gate, (motion_s, static_s) in GATE_SENSITIVITY_OVERRIDES.items():
            print(f"[CONFIG] Gate {gate}: motion sensitivity={motion_s}, "
                  f"static sensitivity={static_s}")
            cfg.set_gate_sensitivity(gate, motion_s, static_s)

        params = cfg.read_parameters()
        print(f"[CONFIG] Radar confirms: max moving gate="
              f"{params['configured_max_moving_gate']}, max static gate="
              f"{params['configured_max_static_gate']}, no-one duration="
              f"{params['no_one_duration_s']}s\n")

    except RuntimeError as e:
        print(f"[WARN] Sensor range-capping configuration failed: {e}")
        print("[WARN] Continuing with the sensor's existing configuration.\n")

    finally:
        if entered:
            try:
                cfg.end_config_mode()
            except RuntimeError as e:
                print(f"[WARN] Could not cleanly exit sensor config mode: {e}")
                print("[WARN] The radar may not resume streaming target data "
                      "until it's power-cycled.\n")


def main():
    print(f"Opening {COM_PORT} at {BAUD_RATE} baud...")
    ser = serial.Serial(COM_PORT, BAUD_RATE, timeout=1)

    if ENABLE_RANGE_CAPPING:
        configure_range_capping(ser)

    print("Listening for sensor data... (Ctrl+C to stop)\n")
    print(f"Seat detection band: {SEAT_MIN_MM}-{SEAT_MAX_MM} mm | Confirm hold: {CONFIRM_SECONDS}s | "
          f"Exit debounce: {EXIT_DEBOUNCE_FRAMES} frames\n")

    buffer = bytearray()
    seat_presence_start = None  # timestamp when continuous seat-range presence began
    motion_blip_seen = False    # whether any moving-energy blip occurred during this presence
    object_warning_printed = False  # avoid spamming the "possible object" message

    # ---- ADD: exit-debounce counter ----
    # Counts consecutive out-of-band frames while presence is currently active.
    # Only resets seat_presence_start once this reaches EXIT_DEBOUNCE_FRAMES.
    # UPDATED: ambiguous frames (see in_seat_range()) no longer touch this
    # counter at all -- only a genuinely out-of-band reading advances it.
    out_of_band_streak = 0

    # ---- change-gated logging state ----
    last_logged_frame = None
    last_log_time = 0.0

    try:
        while True:
            chunk = ser.read(ser.in_waiting or 1)
            if not chunk:
                time.sleep(0.01)
                continue
            buffer.extend(chunk)

            # process all complete frames currently in the buffer
            while True:
                start = buffer.find(FRAME_HEADER)
                if start == -1:
                    buffer = buffer[-3:]  # keep tail in case header is split
                    break

                end = buffer.find(FRAME_FOOTER, start)
                if end == -1:
                    break  # wait for more data (footer not arrived yet)

                payload = buffer[start + 6:end]
                frame = parse_frame(payload)
                buffer = buffer[end + len(FRAME_FOOTER):]

                if not frame:
                    continue

                # ---- only print if meaningfully changed, or heartbeat is due ----
                now = time.time()
                changed = frame_changed(frame, last_logged_frame)
                heartbeat_due = (now - last_log_time) >= HEARTBEAT_SECONDS

                if changed:
                    log_frame(frame)
                    last_logged_frame = frame
                    last_log_time = now
                elif heartbeat_due:
                    log_frame(frame, reason="heartbeat, no change")
                    last_logged_frame = frame
                    last_log_time = now

                # --- seat presence-hold logic, now with exit-debounce ---
                # UPDATED: in_seat_range() now returns (in_range, ambiguous).
                # An ambiguous frame (no trustworthy distance reading this
                # frame) is treated as neutral -- it neither confirms
                # presence nor counts toward the exit debounce, instead of
                # being silently misjudged as "out of band" via a bad
                # fallback distance.
                in_range, ambiguous = in_seat_range(frame)

                if in_range:
                    # back in-band -- clear any partial exit streak
                    out_of_band_streak = 0

                    if seat_presence_start is None:
                        seat_presence_start = time.time()
                        motion_blip_seen = False
                        object_warning_printed = False

                    # a "blip" = brief motion signature, typical of a live person
                    if frame["target_state"] == 3 or frame["moving_energy"] > 0:
                        motion_blip_seen = True

                    elapsed = time.time() - seat_presence_start
                    if elapsed >= CONFIRM_SECONDS:
                        if (not REQUIRE_MOTION_BLIP) or motion_blip_seen:
                            print("\nPerson is in front of the KIOSK")
                            ser.close()
                            return  # stop execution
                        else:
                            # something is sitting in the seat band but has shown
                            # zero motion the whole time -- likely an object, not a person.
                            # Keep monitoring (don't reset the clock) in case a motion
                            # blip appears shortly after.
                            if not object_warning_printed:
                                print("\n[Note] Static presence detected in seat but no motion "
                                      "observed yet -- possibly an object, not a person. "
                                      "Still monitoring...")
                                object_warning_printed = True

                elif not ambiguous:
                    # Genuinely out-of-band frame (a real, trustworthy distance
                    # reading that falls outside the seat band). Only these
                    # count toward the exit debounce -- ambiguous frames are
                    # skipped entirely (see the "elif" -- no else branch needed
                    # for ambiguous frames since we do nothing for them).
                    if seat_presence_start is not None:
                        out_of_band_streak += 1
                        if out_of_band_streak >= EXIT_DEBOUNCE_FRAMES:
                            seat_presence_start = None
                            motion_blip_seen = False
                            object_warning_printed = False
                            out_of_band_streak = 0
                    else:
                        out_of_band_streak = 0
                # else: ambiguous frame while not in range -- do nothing,
                # wait for a clearer reading on the next frame.

    except KeyboardInterrupt:
        print("\nStopped by user.")
    except serial.SerialException as e:
        print(f"\nSerial error: {e}")
        print("Check that the COM port number is correct and no other program is using it.")
    finally:
        if ser.is_open:
            ser.close()


if __name__ == "__main__":
    main()
