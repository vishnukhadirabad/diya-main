import cv2
import time
from gaze_tracking import GazeTracking
import numpy as np

gaze = GazeTracking()
# Define the camera index (0 is usually the default camera)
camera_index = 8

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

count = 0
score = 0

print("Recording started...")

# Capture frames and write them to the output file without displaying them
while True:
    ret, frame = cap.read()
    gaze.refresh(frame)
    if ret:
        count = count + 1

        if(count>3880 and count<5579):

            # We send this frame to GazeTracking to analyze it
#            gaze.refresh(frame)
            # image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
            image_height, image_width, _ = frame.shape
            # count = count +1

            # results = pose.process(image_rgb)
            # landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width) for lm in results.pose_landmarks.landmark]

            # x_wrist,y_wrist,_ = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]


            frame = gaze.annotated_frame()
            text = ""

            # print(gaze.horizontal_ratio_le(),gaze.horizontal_ratio_re())

            if gaze.is_blinking():
                text = "Looking"
                score = score +1 #a human will blink!
            # elif gaze.is_right():
            #     text = "Looking right"
            elif gaze.is_left_le() and gaze.is_center_re():
                text = "Looking"
                score = score +1
            # elif gaze.is_center():
            #     text = "Looking center"
            else:
                text = "Not Looking"
            

            cv2.putText(frame, text, (90, 60), cv2.FONT_HERSHEY_DUPLEX, 1.6, (147, 58, 31), 2)

            left_pupil = gaze.pupil_left_coords()
            right_pupil = gaze.pupil_right_coords()
 #           cv2.putText(frame, "Left pupil:  " + str(left_pupil), (90, 130), cv2.FONT_HERSHEY_DUPLEX, 0.9, (147, 58, 31), 1)
 #           cv2.putText(frame, "Right pupil: " + str(right_pupil), (90, 165), cv2.FONT_HERSHEY_DUPLEX, 0.9, (147, 58, 31), 1)

            # cv2.putText(frame, "Wrist: " + str(x_wrist)+","+ str(y_wrist), (90, 200), cv2.FONT_HERSHEY_DUPLEX, 0.9, (147, 58, 31), 1)
            print(count)
            # cv2.imshow("Demo", frame)

            # if cv2.waitKey(1) == 27:
            #     break

            # If a frame is read successfully
            
                # Write the frame to the output video
            out.write(frame)

    # Break the loop if the recording time is up
    if (time.time() - start_time) > recording_time:
        break

# Release the camera and writer resources
cap.release()
out.release()
print("Final score:",score*100/1700,"%")
print(f"Recording completed. Video saved as {output_file}")

