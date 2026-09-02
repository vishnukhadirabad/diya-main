# Complete Code Integration

# 1. Setup and Install Dependencies
#!pip install opencv-python moviepy
import cv2
import numpy as np
from moviepy import *
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import project_path


# 2. Upload the Input Video
#uploaded = files.upload()

# Automatically detect the uploaded file's name
#if not uploaded:
    #print("No file uploaded. Please upload your thermal video.")
#else:
input_video_filename = str(project_path("check_thermal.mp4"))
input_video_path = input_video_filename
print(f"Video '{input_video_path}' uploaded successfully!")

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

def create_blank_video(duration_sec, frame_size, frame_rate=30, text='No Subject Found'):
    width, height = frame_size
    black_frame = np.zeros((height, width, 3), dtype=np.uint8)
    num_frames = duration_sec * frame_rate
    frames = [black_frame] * num_frames
    clip = ImageSequenceClip(frames, fps=frame_rate)
    txt_clip = TextClip(text, fontsize=70, color='white')
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

face_cascade = cv2.CascadeClassifier(str(project_path('haarcascade_frontalface_default.xml')))
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
        blank_clip_path = str(project_path('video_capture', 'blank_video.mp4'))
        blank_clip.write_videofile(blank_clip_path, codec='libx264', fps=frame_rate)
        
        # Provide the blank video for download
        files.download(blank_clip_path)
        
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
output_video_path = str(project_path('video_capture', 'output_morphed_video.mp4'))
output_clip.write_videofile(output_video_path, codec='libx264', fps=frame_rate)


# Provide the output video for download
#files.download(output_video_path)
