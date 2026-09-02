# Complete Code Integration

# 1. Setup and Install Dependencies
#!pip install opencv-python moviepy
import os

import cv2
import numpy as np
# `from moviepy import *` is the 2.x layout and imports nothing under 1.x, which
# is the API the rest of this file targets (TextClip(fontsize=...),
# .set_duration/.set_position) — so the names silently resolved to nothing and
# blew up mid-run as NameError. Import them explicitly from moviepy.editor.
from moviepy.editor import CompositeVideoClip, ImageClip, ImageSequenceClip

from paths import project_path

INPUT_VIDEO_PATH = project_path("check_thermal.mp4")
OUTPUT_VIDEO_PATH = project_path("output_morphed_video.mp4")
HAAR_CASCADE_PATH = project_path("haarcascade_frontalface_default.xml")
BLANK_VIDEO_PATH = project_path("blank_video.mp4")

# In-progress name for the morph. ".part" sits before the suffix because ffmpeg
# picks the muxer from the extension and would reject a trailing ".part".
_root, _ext = os.path.splitext(str(OUTPUT_VIDEO_PATH))
PART_VIDEO_PATH = _root + '.part' + _ext


# 2. Upload the Input Video
#uploaded = files.upload()

# Automatically detect the uploaded file's name
#if not uploaded:
    #print("No file uploaded. Please upload your thermal video.")
#else:
input_video_path = str(INPUT_VIDEO_PATH)
print(f"Video '{input_video_path}' uploaded successfully!")

# This now runs alongside 5M.py and is consumed by a playback stage that starts
# a clip as soon as its file exists, so the previous run's morph has to go
# before we begin — otherwise it gets played and reported on as if it were this
# visitor's. The new one lands via an atomic rename at the end.
for _stale in (str(OUTPUT_VIDEO_PATH), PART_VIDEO_PATH):
    try:
        os.remove(_stale)
    except FileNotFoundError:
        pass

# 3. Define Helper Functions
def detect_person(frame, face_cascade):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    return len(faces) > 0

def extract_frames(video_path, start_time, duration, frame_rate=30):
    cap = cv2.VideoCapture(video_path)
    frames = []
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps != frame_rate:
        print(f"Warning: Input video FPS ({fps}) does not match expected FPS ({frame_rate}). Using actual FPS.")
        frame_rate = fps  # Use actual FPS
    
    cap.set(cv2.CAP_PROP_POS_MSEC, start_time * 1000)
    num_frames = int(duration * frame_rate)
    
    for _ in range(num_frames):
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    
    cap.release()
    return frames

def _text_clip(text, fontsize=70, color=(255, 255, 255)):
    """Caption clip rendered with Pillow instead of moviepy's TextClip.

    TextClip shells out to ImageMagick, which isn't installed here, so the
    "no subject found" path died with an OSError instead of writing its blank
    video. Pillow is already a dependency (via moviepy), so render the text to
    an array and wrap it in an ImageClip — same .set_position/.set_duration
    interface the caller expects.
    """
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype(
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', fontsize)
    except OSError:
        font = ImageFont.load_default()
    dummy = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    left, top, right, bottom = dummy.textbbox((0, 0), text, font=font)
    img = Image.new('RGB', (right - left + 20, bottom - top + 20), (0, 0, 0))
    ImageDraw.Draw(img).text((10 - left, 10 - top), text, font=font, fill=color)
    return ImageClip(np.array(img))


def create_blank_video(duration_sec, frame_size, frame_rate=30, text='No Subject Found'):
    width, height = frame_size
    black_frame = np.zeros((height, width, 3), dtype=np.uint8)
    num_frames = duration_sec * frame_rate
    frames = [black_frame] * num_frames
    clip = ImageSequenceClip(frames, fps=frame_rate)
    txt_clip = _text_clip(text, fontsize=70, color=(255, 255, 255))
    txt_clip = txt_clip.set_position('center').set_duration(duration_sec)
    final_clip = CompositeVideoClip([clip, txt_clip])
    return final_clip

def check_person_presence(frames, face_cascade):
    for idx, frame in enumerate(frames):
        if detect_person(frame, face_cascade):
            print(f"Person detected in frame {idx + 1}")
            return True
    return False

# 4. Load Haar Cascade for Person Detection
#!wget -O haarcascade_frontalface_default.xml https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml

face_cascade = cv2.CascadeClassifier(str(HAAR_CASCADE_PATH))
if face_cascade.empty():
    print("Error loading Haar Cascade. Please check the file path.")
else:
    print("Haar Cascade loaded successfully!")

# 5. Detect Person Presence
default_frame_rate = 30  # FPS
total_duration_sec = 300  # 5 minutes

def get_video_properties(video_path):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if fps else 0
    cap.release()
    return fps, duration

# Get actual video properties
actual_fps, actual_duration = get_video_properties(input_video_path)
print(f"Actual FPS: {actual_fps}")
print(f"Actual Duration: {actual_duration} seconds")

# Update frame_rate if different
frame_rate = default_frame_rate
if actual_fps != default_frame_rate and actual_fps > 0:
    print(f"Updating frame rate to actual FPS: {actual_fps}")
    frame_rate = actual_fps

# Extract frames from the last 1 minute
print("Extracting frames from the last 1 minute...")
start_time_last = max(actual_duration - 60, 0)  # Ensure start_time is non-negative
last_1min_frames = extract_frames(
    video_path=input_video_path,
    start_time=start_time_last,
    duration=60,
    frame_rate=frame_rate
)

# Check for person in the last 1 minute
print("Checking for person in the last 1 minute...")
person_in_last = check_person_presence(last_1min_frames, face_cascade)

if person_in_last:
    selected_frames = last_1min_frames
    print("Person detected in the last 1 minute.")
else:
    # If not found, check the middle segment
    print("Person not found in the last 1 minute. Checking the middle segment...")
    middle_start = max((actual_duration / 2) - 30, 0)  # Start 30 seconds before the midpoint
    middle_frames = extract_frames(
        video_path=input_video_path,
        start_time=middle_start,
        duration=60,
        frame_rate=frame_rate
    )
    person_in_middle = check_person_presence(middle_frames, face_cascade)
    
    if person_in_middle:
        selected_frames = middle_frames
        print("Person detected in the middle segment.")
    else:
        # If still not found, create a blank video
        print("Person not found in any segment. Creating a blank video.")
        # Get frame size from any available frame
        cap = cv2.VideoCapture(input_video_path)
        ret, frame = cap.read()
        if not ret:
            print("Error reading the video for frame size. Using default size 1920x1080.")
            frame_size = (1920, 1080)  # Default size
        else:
            height, width, _ = frame.shape
            frame_size = (width, height)
        cap.release()
        
        blank_clip = create_blank_video(duration_sec=30, frame_size=frame_size)
        blank_clip.write_videofile(str(BLANK_VIDEO_PATH), codec='libx264', fps=frame_rate)
        
        # Exit the script as no further processing is needed
        import sys
        sys.exit("No person detected. Blank video created.")

# 6. Extract and Select Frames for Morphing
print("Extracting frames from the first 2 minutes...")
first_2min_frames = extract_frames(
    video_path=input_video_path,
    start_time=0,  # Start from the beginning
    duration=120,  # 2 minutes
    frame_rate=frame_rate
)

print("Extracting frames from the last 1 minute...")
last_1min_frames = extract_frames(
    video_path=input_video_path,
    start_time=start_time_last,
    duration=60,
    frame_rate=frame_rate
)

# Define desired output duration and total frames
output_duration_sec = 30  # 30 seconds
desired_total_frames = int(output_duration_sec * frame_rate)  # Total frames required (e.g., 900 frames)

# Calculate frames to extract from each segment
# Allocate approximately 20 seconds from the first 2 minutes and 10 seconds from the last 1 minute
frames_from_first = int(desired_total_frames * (2/3))  # 20 seconds worth
frames_from_last = desired_total_frames - frames_from_first  # 10 seconds worth

# Ensure we have enough frames
frames_from_first = min(frames_from_first, len(first_2min_frames))
frames_from_last = min(frames_from_last, len(last_1min_frames))

# Select frames
selected_frames_first = first_2min_frames[:frames_from_first]
selected_frames_last = last_1min_frames[:frames_from_last]

# Combine selected frames
selected_frames = selected_frames_first + selected_frames_last

# If selected_frames are less than desired_total_frames, loop frames to fill the gap
if len(selected_frames) < desired_total_frames:
    additional_frames_needed = desired_total_frames - len(selected_frames)
    selected_frames += selected_frames[:additional_frames_needed]

# Ensure we have exactly desired_total_frames
selected_frames = selected_frames[:desired_total_frames]

print(f"Total selected frames for morphing: {len(selected_frames)}")

# 7. Perform Morphing
print("Applying morphing to frames...")

morphed_frames = []

# Define number of morphed frames between each pair
num_morphs = 2  # Adjusted to maintain total frames within 900

for i in range(len(selected_frames) - 1):
    current_frame = selected_frames[i]
    next_frame = selected_frames[i + 1]
    
    # Generate intermediate frames for smooth transition
    for j in range(1, num_morphs + 1):
        alpha = j / (num_morphs + 1)
        morphed = cv2.addWeighted(current_frame, 1 - alpha, next_frame, alpha, 0)
        morphed_frames.append(morphed)

# Append the last frame
morphed_frames.append(selected_frames[-1])

print(f"Total morphed frames: {len(morphed_frames)}")

# 8. Compile Morphed Frames into Output Video
print("Converting frames to RGB format...")
morphed_frames_rgb = [cv2.cvtColor(frame, cv2.COLOR_BGR2RGB) for frame in morphed_frames]

print("Creating the final video clip...")
output_clip = ImageSequenceClip(morphed_frames_rgb, fps=frame_rate)

# Optionally, add a title or text overlay
# For example, adding "Calmness Enhanced" at the beginning
# Uncomment the following lines to add text

"""
txt_clip = TextClip("Calmness Enhanced", fontsize=70, color='white')
txt_clip = txt_clip.set_position('center').set_duration(5)  # Display for first 5 seconds
final_clip = CompositeVideoClip([output_clip, txt_clip])
final_clip.write_videofile('output_with_text.mp4', codec='libx264', fps=frame_rate)
"""

# Save the output video
output_video_path = str(OUTPUT_VIDEO_PATH)
# ultrafast trades file size for encode time. This clip is played once on the
# kiosk and then thrown away, so the size does not matter and the visitor was
# waiting on a black screen for the encode.
output_clip.write_videofile(
    PART_VIDEO_PATH, codec='libx264', fps=frame_rate,
    preset='ultrafast', ffmpeg_params=['-crf', '28'])
os.replace(PART_VIDEO_PATH, output_video_path)


# Provide the output video for download
#files.download(output_video_path)
