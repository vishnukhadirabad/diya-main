import functools
import glob
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def project_path(*parts):
    return BASE_DIR.joinpath(*parts)


# ── Camera device configuration ──────────────────────────────────────────────
# Every capture script used to hardcode its own /dev/videoX index and the
# RealSense serial, so a swapped or re-plugged camera broke one stage with an
# unhelpful error ("Could not open camera", "No device connected") while the
# rest of the pipeline still reported success. CAMERA_CONFIG.txt (shipped with
# the packaged build) asks for these to live in one place — they do now.
#
# Each constant resolves in this order:
#   1. the matching environment variable, when set
#   2. the /dev/videoX node whose v4l2 name matches the expected camera
#   3. the historical hardcoded index, as a last resort
#
# Indices shift with USB enumeration order, which is why the name lookup is
# preferred over a fixed number.


def _video_index_by_name(name_prefix, default):
    """Index of the first /dev/videoX whose v4l2 name starts with name_prefix."""
    candidates = []
    for name_path in glob.glob('/sys/class/video4linux/video*/name'):
        try:
            with open(name_path) as fh:
                name = fh.read().strip()
        except OSError:
            continue
        if name.startswith(name_prefix):
            node = os.path.basename(os.path.dirname(name_path))
            candidates.append(int(node[len('video'):]))
    # A camera exposes several nodes (capture + metadata); the lowest is the
    # capture one. Sort numerically — lexicographic order puts video10 first.
    return min(candidates) if candidates else default


def _camera_index(env_var, name_prefix, default):
    value = os.environ.get(env_var)
    if value:
        return int(value)
    return _video_index_by_name(name_prefix, default)


# Wide-angle front camera for posture analysis.
# Used in: Front.py, check_similarity4.py, depth/adjustment_test_updated.py.
# Deliberately NOT a RealSense node: acquisition runs check_similarity4.py at
# the same time as depthacquisition.py, and the two cannot both hold the D435
# (one via V4L2, one via librealsense) — the V4L2 side loses and exits.
FRONT_CAM_INDEX = _camera_index('FRONT_CAM_INDEX', 'Arducam', 8)

# Gaze / eye tracking camera.  Used in: visual_test6.py.
GAZE_CAM_INDEX = _camera_index('GAZE_CAM_INDEX', 'HD Pro Webcam C920', 0)

# Thermal camera (256x192 sensor, frames arrive 256x384: image + data rows).
# Used in: test2_time.py.
THERMAL_CAM_INDEX = _camera_index('THERMAL_CAM_INDEX', 'USB Camera', 10)


# Physical mounting correction for the front camera. The Arducam is mounted 90°
# rotated, so its feed arrives sideways while the RealSense panels beside it are
# upright. Values: 'none', 'cw', 'ccw', '180' — override with FRONT_CAM_ROTATION
# if the camera is ever remounted.
FRONT_CAM_ROTATION = os.environ.get('FRONT_CAM_ROTATION', 'ccw').lower()

def upright(frame):
    """Rotate a front-camera frame to match the other panels' orientation.

    Callers resize to a fixed panel size afterwards, so the swapped width/height
    does not affect any downstream layout.
    """
    if frame is None or FRONT_CAM_ROTATION in ('none', '', 'off'):
        return frame
    import cv2
    codes = {
        'cw': cv2.ROTATE_90_CLOCKWISE,
        'ccw': cv2.ROTATE_90_COUNTERCLOCKWISE,
        '180': cv2.ROTATE_180,
    }
    code = codes.get(FRONT_CAM_ROTATION)
    return frame if code is None else cv2.rotate(frame, code)


def upright_size(width, height):
    """Frame size after upright() — width/height swap on a 90° rotation.

    VideoWriter silently discards frames whose size differs from the one it was
    opened with, so any writer fed upright() frames must be sized through here.
    """
    if FRONT_CAM_ROTATION in ('cw', 'ccw'):
        return (height, width)
    return (width, height)


def fullscreen_window(name):
    """Create a borderless, full-screen OpenCV window.

    The old idiom here was cv2.namedWindow(name, cv2.WND_PROP_FULLSCREEN), but
    WND_PROP_FULLSCREEN is a *property* id whose value is 0 — identical to
    WINDOW_NORMAL — so it never requested full screen. Worse, this OpenCV is a Qt5
    build where flags=0 also means WINDOW_GUI_EXPANDED, which is what drew the
    toolbar of arrow/zoom/save icons over each stage. WINDOW_GUI_NORMAL turns that
    chrome off; the property call below is what actually goes full screen.
    """
    import cv2
    cv2.namedWindow(name, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
    cv2.setWindowProperty(name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setWindowProperty(name, cv2.WND_PROP_TOPMOST, 1)
    return name


def configure_depth_streams(config, fps=30, select_device=True):
    """Enable the 640x480 colour and depth streams the depth stages all use.

    Stated once here so run_stages.py can start the RealSense warming up before
    the first stage that needs it, without having to restate a stage's own
    configuration and risk the two drifting apart.
    """
    import pyrealsense2 as rs
    if select_device:
        serial = realsense_serial()
        if serial:
            config.enable_device(serial)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, fps)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, fps)


@functools.lru_cache(maxsize=1)
def realsense_serial():
    """Serial of the RealSense depth camera.

    Used in: depthacquisition.py, splitGaze.py, depth/splitSide.py. Returns
    REALSENSE_SERIAL when set, otherwise the first connected device. Returns
    None when nothing is attached, so callers can skip enable_device() and let
    librealsense raise its own error. pyrealsense2 is imported lazily — plain
    consumers of project_path() should not need it installed.

    Cached because enumerating the USB bus costs ~0.16s and run_stages.py runs
    several depth stages in one process. The camera cannot be swapped part-way
    through a session, so one lookup per process is enough.
    """
    configured = os.environ.get('REALSENSE_SERIAL')
    if configured:
        return configured
    try:
        import pyrealsense2 as rs
    except ImportError:
        return None
    return next(
        (d.get_info(rs.camera_info.serial_number) for d in rs.context().query_devices()),
        None,
    )
