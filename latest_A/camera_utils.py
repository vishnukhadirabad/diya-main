import os
import glob
import subprocess
import re
import serial.tools.list_ports

# ======================================================================
# CAMERAS
# ======================================================================
CAMERA_CONFIG = {
    "logitech": "/dev/v4l/by-id/usb-Logitech_HD_Pro_Webcam_C920_XXXX-video-index0",
    "arducam":  "/dev/v4l/by-id/usb-ArduCam_XXXX-video-index0",
}


def find_cameras_by_name():
    cameras = {}
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'],
            capture_output=True, text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("[WARN] v4l2-ctl not available.")
        return cameras
    current_name = ""
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith('/dev/video'):
            current_name = line.lower()
        else:
            m = re.search(r'/dev/video(\d+)', line)
            if not m:
                continue
            index = int(m.group(1))
            if 'hd pro webcam' in current_name and 'logitech' not in cameras:
                cameras['logitech'] = index
            elif 'arducam' in current_name and 'arducam' not in cameras:
                cameras['arducam'] = index
    return cameras


def resolve_camera(name: str, fallback_index: int | None = None):
    path = CAMERA_CONFIG.get(name)
    if path and os.path.exists(path):
        print(f"[{name}] Using stable path: {path}")
        return path
    print(f"[{name}] Stable path not found, falling back to index {fallback_index}")
    return fallback_index


def get_camera_index(name: str) -> int | str | None:
    """
    Returns the OpenCV-openable path or integer index for `name`.
    Call this once at startup; pass the result to cv2.VideoCapture().
    """
    detected = find_cameras_by_name()
    src = resolve_camera(name, detected.get(name))
    if src is None:
        raise RuntimeError(
            f"[camera_utils] Could not resolve camera '{name}'. "
            "Check the connection or update CAMERA_CONFIG."
        )
    return src


# ======================================================================
# ARDUINO (native USB — ATmega16u2, enumerates as /dev/ttyACM*)
# ======================================================================
def find_arduino():
    """Return the device path of the first Arduino-like port, or None.

    VID 0x2341 is the official Arduino vendor ID. This chip family is
    distinct from the CP2102 used by the LD2410 below, so the two
    devices can never be confused with each other.
    """
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


# ======================================================================
# LD2410C-P (via CP2102 USB-UART bridge, enumerates as /dev/ttyUSB*)
# ======================================================================
# CP2102 is a generic Silicon Labs chip ID, not specific to the LD2410.
# It's fine to identify by VID:PID here because in this setup it's the
# only CP2102 device on the bus, and the Arduino above enumerates as a
# completely different chip family (ttyACM, VID 0x2341) so there's no
# risk of the two being mixed up.
CP2102_VID = 0x10C4
CP2102_PID = 0xEA60


def find_ld2410_port_by_id():
    """
    Preferred method: look for a stable /dev/serial/by-id/ symlink.
    This is the serial-port equivalent of the /dev/v4l/by-id/ camera
    paths above, and survives reboots/replugs/renumbering, unlike
    /dev/ttyUSB0.
    """
    by_id_dir = "/dev/serial/by-id"
    if not os.path.isdir(by_id_dir):
        return None

    candidates = glob.glob(os.path.join(by_id_dir, "*"))
    matches = [
        p for p in candidates
        if "cp2102" in p.lower() or "silicon_labs" in p.lower() or "cp210x" in p.lower()
    ]

    if not matches:
        return None
    if len(matches) > 1:
        print(f"[camera_utils] WARNING: found more than one CP2102 by-id path "
              f"(unexpected with a single LD2410C-P): {matches}. Using the first one.")
    return matches[0]


def find_ld2410_port_by_vidpid():
    """
    Fallback: scan pyserial's port list for a CP2102 by VID:PID.
    Returns the raw /dev/ttyUSBn path (not guaranteed stable across
    replugs — prefer by-id above when available).
    """
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if port.vid == CP2102_VID and port.pid == CP2102_PID:
            return port.device
    return None


def get_ld2410_port() -> str:
    """
    Returns the path to open with serial.Serial() for the LD2410C-P's
    CP2102 UART bridge. Call once at startup, same pattern as
    get_camera_index() above.
    """
    port = find_ld2410_port_by_id()
    if port:
        print(f"[camera_utils] LD2410: using stable by-id path: {port}")
        return port

    port = find_ld2410_port_by_vidpid()
    if port:
        print(f"[camera_utils] LD2410: by-id path not found, falling back to: {port} "
              "(WARNING: not guaranteed stable across replugs)")
        return port

    raise RuntimeError(
        "[camera_utils] Could not find CP2102/LD2410 serial port. "
        "Check the USB connection, or run `ls -l /dev/serial/by-id/` "
        "and `python3 -m serial.tools.list_ports -v` to inspect what's connected."
    )
