import os
from concurrent.futures import ThreadPoolExecutor

import cv2

from paths import project_path


def _part_path(output_video_path):
    """In-progress name for output_video_path, keeping the original suffix."""
    root, ext = os.path.splitext(str(output_video_path))
    return root + '.part' + ext


def convert_to_one_minute(input_video_path, output_video_path):
    # Written to a .part file and renamed on completion. The playback stage
    # starts each clip the moment its file appears, so a half-written file at
    # the final path would be picked up and played as a truncated clip —
    # os.replace is atomic, which makes "the file exists" mean "it is finished".
    input_video_path = str(input_video_path)
    output_video_path = str(output_video_path)
    # .part goes before the suffix, not after: OpenCV picks the container from
    # the extension, and a trailing ".part" leaves it with nothing to match.
    part_path = _part_path(output_video_path)
    cap = cv2.VideoCapture(input_video_path)
    
    # Get the original video's frame rate, width, and height
    fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Calculate the total number of frames and the speed factor
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    speed_factor = total_frames / (60 * fps)  # 60 seconds = 1 minute

    # Create a VideoWriter to save the output video with a standard frame rate
    standard_fps = 30  # Set a standard frame rate
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(part_path, fourcc, standard_fps, (width, height))
    
    # Read and write frames with the adjusted speed
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % speed_factor < 1:
            out.write(frame)
        frame_count += 1
    
    # Release the VideoCapture and VideoWriter objects
    cap.release()
    out.release()

    os.replace(part_path, output_video_path)
    print(f"One-minute video saved as {output_video_path}", flush=True)


CONVERSIONS = [
    (project_path("visual1_video.avi"), project_path("visual1_video_1M.avi")),
    (project_path("Gaze_output.avi"), project_path("Gaze_output_1M.avi")),
    (project_path("Depth_output.avi"), project_path("Depth_output_1M.avi")),
]

# Last run's clips are still on disk, and playback treats an existing file as a
# finished one — so clear them before writing, or the visitor gets served the
# previous visitor's video while this one is still encoding.
for _, output_path in CONVERSIONS:
    for stale in (str(output_path), _part_path(output_path)):
        try:
            os.remove(stale)
        except FileNotFoundError:
            pass

# The posture clip plays first and the other two aren't needed for another
# ~50s, so convert it on its own before starting the rest — that gets playback
# on screen in ~3s instead of after all three finish. The remaining two run
# together; OpenCV releases the GIL during decode/encode, so threads overlap.
convert_to_one_minute(*CONVERSIONS[0])

with ThreadPoolExecutor(max_workers=2) as pool:
    for future in [pool.submit(convert_to_one_minute, *c) for c in CONVERSIONS[1:]]:
        future.result()
