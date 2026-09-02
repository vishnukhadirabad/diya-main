import cv2
import time

# Define the camera index (0 is usually the default camera)
camera_index = 0

# Open the video capture using the camera index
cap = cv2.VideoCapture(camera_index)

# Check if the camera opened successfully
if not cap.isOpened():
    print("Error: Unable to access the camera")
    exit()

# Get the default frame width and height of the camera
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

# Define the codec and create a VideoWriter object to save the video
output_file = 'output2_video.avi'
fourcc = cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter(output_file, fourcc, 20.0, (frame_width, frame_height))

# Define the recording time in seconds (5 minutes = 300 seconds)
recording_time = 5 * 60
start_time = time.time()

print("Recording started...")

# Capture frames and write them to the output file without displaying them
while True:
    ret, frame = cap.read()

    if not ret:
        print("Failed to grab frame")
        break

    # Write the frame to the output file
    out.write(frame)

    # Break the loop if the recording time is up
    if (time.time() - start_time) > recording_time:
        break

# Release the camera and writer resources
cap.release()
out.release()

print(f"Recording completed. Video saved as {output_file}")

