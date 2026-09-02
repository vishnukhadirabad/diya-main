"""Cameras shared across the frontback1 stages.

Each stage used to run as its own python3 process, so every one of them paid
interpreter startup, ~1s of imports, a fresh camera open, and — for the three
RealSense stages — ~0.9s of librealsense teardown before the next stage could
even begin. Measured at 1.5-2.4s per stage, and that is exactly the black gap
the visitor sees between stages.

run_stages.py runs all four stages inside a single process instead. The helpers
below hand out one long-lived RealSense pipeline and one long-lived capture per
device, so each camera is opened once for the whole sequence and stays warm and
streaming across every stage boundary.

None of this is imposed on a stage run on its own: when run_stages.py is not
driving, every helper does the plain thing, so `python3 Front.py` still opens
and closes its own camera exactly as it always did. That matters because the
acquisition stage afterwards needs the cameras free.
"""

import threading

_shared = False
_realsense_pipeline = None
_captures = {}

# Separate locks so a stage asking for its webcam is never held up behind the
# RealSense still coming up on the prewarm thread.
_realsense_lock = threading.Lock()
_captures_lock = threading.Lock()

# A capture left streaming across a stage boundary has frames from the previous
# stage sitting in its buffer. Dropping a few means the new stage's first
# displayed frame is live rather than seconds stale.
_STALE_FRAMES = 5


def enable():
    """Share cameras between stages. Called by run_stages.py only."""
    global _shared
    _shared = True


def realsense(configure):
    """A started RealSense pipeline. `configure(config)` enables the streams.

    Under run_stages.py the first stage to ask for the camera starts it and
    every later stage gets that same running pipeline, which skips both the
    ~0.9s stop and the ~0.6s restart at each boundary. All three RealSense
    stages ask for 640x480 colour and depth, so one pipeline serves them all;
    the frame rate is whichever the first caller requested.
    """
    global _realsense_pipeline
    if not _shared:
        return _start_realsense(configure)

    with _realsense_lock:
        if _realsense_pipeline is None:
            _realsense_pipeline = _start_realsense(configure)
        return _realsense_pipeline


def _start_realsense(configure):
    import pyrealsense2 as rs
    pipeline = rs.pipeline()
    config = rs.config()
    configure(config)
    pipeline.start(config)
    return pipeline


def stop_realsense(pipeline):
    """Release the RealSense unless a later stage still needs it."""
    if not _shared:
        pipeline.stop()


def capture(index):
    """An open cv2.VideoCapture for /dev/video<index>."""
    import cv2

    if not _shared:
        return cv2.VideoCapture(index)

    with _captures_lock:
        existing = _captures.get(index)
        if existing is None:
            _captures[index] = cv2.VideoCapture(index)
            return _captures[index]

    for _ in range(_STALE_FRAMES):
        existing.grab()
    return existing


def release_capture(cap):
    """Release a capture unless a later stage still needs it."""
    if not _shared:
        cap.release()


def prewarm(configure, capture_indexes=()):
    """Bring the cameras up in the background, ahead of the stage that needs them.

    Front.py runs on the webcam alone, so the RealSense the three depth stages
    want can be started during it — which is where the last visible gap in the
    sequence used to be. Both can also be opened while the stage imports are
    still loading, since neither is waiting on the CPU.

    Failures are left to the stage: whichever one asks for the camera next
    tries again through the normal path and reports the error where the
    operator will see it, rather than having it disappear on this thread.
    """
    if not _shared:
        return

    def warm():
        for index in capture_indexes:
            try:
                capture(index)
            except Exception:
                pass
        try:
            realsense(configure)
        except Exception:
            pass

    threading.Thread(target=warm, daemon=True).start()


def shutdown():
    """Close every shared camera.

    run_stages.py calls this once the last stage is done, because acquisition
    reopens the same devices in its own processes straight afterwards. Both
    locks are taken so a prewarm thread that is somehow still opening a camera
    cannot have it left behind, still held, after this returns.
    """
    global _realsense_pipeline
    with _captures_lock:
        for cap in _captures.values():
            cap.release()
        _captures.clear()
    with _realsense_lock:
        if _realsense_pipeline is not None:
            _realsense_pipeline.stop()
            _realsense_pipeline = None
