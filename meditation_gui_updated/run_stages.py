"""Run the four camera stages of frontback1 back to back in one process.

frontback1 used to launch each stage as its own `python3 <script>`. Measured on
this machine, that cost 1.5-2.4s per stage before the stage's first frame
reached the screen — interpreter startup, ~1s of imports, MediaPipe model
construction, a cold camera open, and for the depth stages ~0.9s of
librealsense teardown left over from the stage before. That dead time is the
black gap between stages, and none of it is work the visitor benefits from.

Running the stages here instead pays all of it once. The imports below are the
union of what the stages import, so by the time the first one runs everything
is already loaded; stage_runtime keeps each camera open across the boundaries;
and posecache keeps the reference-image landmarks on disk.

Each stage is still its own script, run exactly as `python3 <script>` would run
it — same `__main__` name, its own fresh globals — so the stages remain usable
on their own and stay the place to edit stage behaviour.
"""

import os
import runpy
import sys
import time
import traceback

import cv2

import stage_runtime
from paths import FRONT_CAM_INDEX, configure_depth_streams, project_path

# Kept in the order frontback1 ran them; the names are what shows in the log.
STAGES = [
    ("Front.py", ("Front.py",)),
    ("splitSide.py", ("depth", "splitSide.py")),
    ("splitGaze.py", ("splitGaze.py",)),
    ("adjustment_test_updated.py", ("depth", "adjustment_test_updated.py")),
]


def _preload():
    """Import what the stages import, before the first stage is on screen.

    Doing this here means the cost is paid once during the meditation video
    that precedes the sequence, rather than four times between stages.
    """
    import mediapipe            # noqa: F401
    import numpy                # noqa: F401
    import pyautogui            # noqa: F401
    import pyrealsense2         # noqa: F401


def _wait_for_exit(pid):
    """Block until `pid` has exited.

    frontback1 starts this runner alongside the meditation video, so the
    imports and the camera warm-up happen while the visitor is still watching
    rather than as a gap once the video ends. The first stage must not draw
    over the player, so it waits here until the player is gone. A pid that has
    already exited — or was never ours to signal — returns straight away.
    """
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.05)


def _clear_windows():
    """Tear down the finished stage's window before the next one opens.

    destroyAllWindows only queues the request with the GUI backend; without a
    waitKey to pump the event loop the old full-screen window can linger over
    the incoming stage.
    """
    cv2.destroyAllWindows()
    cv2.waitKey(1)


def main(after_pid=None):
    stage_runtime.enable()
    # Started before the imports so the cameras come up while MediaPipe and the
    # rest are still loading, rather than after.
    stage_runtime.prewarm(configure_depth_streams,
                          capture_indexes=(FRONT_CAM_INDEX,))
    _preload()
    if after_pid:
        _wait_for_exit(after_pid)

    started = time.time()
    previous_finished = started
    for name, parts in STAGES:
        gap = time.time() - previous_finished
        print("[run_stages] %s starting (%.2fs after the previous stage)"
              % (name, gap), flush=True)
        stage_started = time.time()
        try:
            runpy.run_path(str(project_path(*parts)), run_name="__main__")
        except SystemExit as exit_request:
            if exit_request.code:
                print("[run_stages] %s exited with %s" % (name, exit_request.code),
                      file=sys.stderr, flush=True)
                stage_runtime.shutdown()
                return exit_request.code
        except Exception:
            traceback.print_exc()
            print("[run_stages] %s failed." % name, file=sys.stderr, flush=True)
            stage_runtime.shutdown()
            return 1
        print("[run_stages] %s done in %.2fs" % (name, time.time() - stage_started),
              flush=True)
        _clear_windows()
        previous_finished = time.time()

    # acquisition reopens these same devices in its own processes next.
    stage_runtime.shutdown()
    print("[run_stages] all stages completed in %.2fs" % (time.time() - started),
          flush=True)
    return 0


if __name__ == "__main__":
    # --after-pid <pid>: finish loading, then hold the first stage back until
    # that process (the meditation video player) has exited.
    _after = None
    if "--after-pid" in sys.argv:
        _after = int(sys.argv[sys.argv.index("--after-pid") + 1])
    sys.exit(main(_after))
