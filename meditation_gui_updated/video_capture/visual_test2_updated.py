import cv2
from gaze_tracking import GazeTracking
import mediapipe as mp
import numpy as np
import math

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils



def compare_with(x_w,y_w,x_e,y_e):
    # print("In compare width")
    theta = math.degrees(math.atan2(abs(y_w - y_e),abs(x_w - x_e)))

    if(x_w > x_e):
        theta_new = theta/2
    else:
        theta_new = (180 - theta)/2

    return math.cos(theta_new*math.pi/180)


# Main script
if __name__ == "__main__":
    gaze = GazeTracking()
    # Define the camera index (0 is usually the default camera)
    camera_index = 0

    # Open the video capture using the camera index
    cap = cv2.VideoCapture(camera_index)
    # Path to the input video file
    # input_video_path = "output2_video.avi"
    # Path to the output video file
    output_file = 'output2_video.avi'
    fourcc = cv2.VideoWriter_fourcc(*'XVID')

    # Create a VideoCapture object to read the input video
    # cap = cv2.VideoCapture(input_video_path)

    count = 0
    score = 0
    with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5,model_complexity=2) as pose:

        # Check if video opened successfully
        if not cap.isOpened():
            print("Error: Could not open input video file.")
        else:
            # Get the frame width, height, and frames per second (fps) from the input video
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            # Define the codec and create a VideoWriter object to save the video
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 'mp4v' for mp4 files, you can also use 'XVID' for .avi files
            out = cv2.VideoWriter(output_file, fourcc, fps, (frame_width, frame_height))

            

            while cap.isOpened():
                
                # Read frame-by-frame
                ret, frame = cap.read()
                gaze.refresh(frame)
                count = count + 1

                # print(count)

                if ret:     
                    if(count>3880 and count<5579):  #3880

                        # We send this frame to GazeTracking to analyze it
                        # gaze.refresh(frame)
                        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            
                        image_height, image_width, _ = frame.shape
                        # count = count +1

                        results = pose.process(image_rgb)
                        landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width) for lm in results.pose_landmarks.landmark]

                        x_w,y_w,_ = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
                        x_r,y_r,_ = landmarks[mp_pose.PoseLandmark.RIGHT_EYE.value]
                        x_l,y_l,_ = landmarks[mp_pose.PoseLandmark.LEFT_EYE.value]

                        h1 = gaze.horizontal_ratio_re()
                        h2 = gaze.horizontal_ratio_le()

                        comp1 = compare_with(x_w,y_w,x_r,y_r)
                        comp2 = compare_with(x_w,y_w,x_l,y_l)

                        
                        t = 0.2
                        if(h1 != None or h2 != None):
                            print(comp1,comp2)
                            print(h1,h2)

                            print(count, ":",h2 + h2 - (comp1 + comp2))

                            if(abs(h2 + h2 - (comp1 + comp2))<t):
                                condition = 1

                            else:
                                condition = 0

                            if gaze.is_blinking():
                                # print(0)
                                text = "Looking"
                                score = score +1 #a human will blink!
                                # elif gaze.is_right():
                                #     text = "Looking right"
                            elif (y_w <= (y_l + y_r)/2):
                                # print(1)
                                if(gaze.vertical_ratio()>=0.5 and condition==1):
                                    text = "Looking"
                                    score = score +1
                                else:
                                    text = "Not Looking"
                            else:
                                # print(2)
                                if(gaze.vertical_ratio()<0.5 and condition==1):
                                    text = "Looking"
                                    score = score +1
                                else:
                                    text = "Not Looking"

                            frame = gaze.annotated_frame()
                
                            
                            print(text)
                            cv2.putText(frame, text, (90, 60), cv2.FONT_HERSHEY_DUPLEX, 1.6, (147, 58, 31), 2)

                            out.write(frame)

                        else:
                            print(None)
                            text = "Looking"
                            score = score +1


                            frame = gaze.annotated_frame()
                            
                            print(text)
                            cv2.putText(frame, text, (90, 60), cv2.FONT_HERSHEY_DUPLEX, 1.6, (147, 58, 31), 2)

                            out.write(frame)
                        # print('NEXT')
                    
                else:
                    break

        # Release the VideoCapture and VideoWriter objects

        cap.release()
        out.release()
        print("Final score:",score*100/1700,"%")
        print("Video saved successfully as", output_file)
