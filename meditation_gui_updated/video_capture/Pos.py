import cv2
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from paths import project_path

# Path to the videos
video1_path = str(project_path('video_capture', 'postureanalysis.mp4'))
video2_path = str(project_path('video_capture', 'output1_video.avi'))

# Open the video files
cap1 = cv2.VideoCapture(video1_path)
cap2 = cv2.VideoCapture(video2_path)

# Check if videos opened successfully
if not cap1.isOpened() or not cap2.isOpened():
    print("Error: Could not open one of the video files.")
    exit()

# Get the width and height of the first video
width1 = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
height1 = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Get the width and height of the second video
width2 = int(cap2.get(cv2.CAP_PROP_FRAME_WIDTH))
height2 = int(cap2.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Make sure both videos have the same height
height = max(height1, height2)

# Loop through the frames of the videos
while True:
    # Read frames from both videos
    ret1, frame1 = cap1.read()
    ret2, frame2 = cap2.read()

    # If one of the videos ends, break the loop
    if not ret1 or not ret2:
        break

    # Resize frames to the same height
    if height1 != height:
        frame1 = cv2.resize(frame1, (width1, height))
    if height2 != height:
        frame2 = cv2.resize(frame2, (width2, height))

    # Stack the frames horizontally
    combined_frame = np.hstack((frame1, frame2))

    # Display the combined frame
    cv2.imshow('Video Side by Side', combined_frame)

    # Press 'q' to exit the video window
    if cv2.waitKey(25) & 0xFF == ord('q'):
        break

# Release the video captures and close windows
cap1.release()
cap2.release()
cv2.destroyAllWindows()
