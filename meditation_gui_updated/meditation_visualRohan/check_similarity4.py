import cv2
import mediapipe as mp
import numpy as np
import math
import time

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Function to calculate angle
def calculateAngle(landmark1, landmark2, landmark3):
    x1, y1, _ = landmark1
    x2, y2, _ = landmark2
    x3, y3, _ = landmark3
    if x1 == x2 == x3 == y1 == y2 == y3 == 0:
        return 0
    angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2))
    if angle < 0:
        angle1 = -1 * angle
        return min(angle1, 360 + angle)
    return angle

# Function to process an image and extract angles
def processImage(image_path):
    with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5, model_complexity=2) as pose:
        image = cv2.imread(image_path)
        image_height, image_width, _ = image.shape
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = pose.process(image_rgb)

        if results.pose_landmarks:
            landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width) for lm in results.pose_landmarks.landmark]
            angles = {
                'right_arm': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value],
                                            landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                            landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'left_arm': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value],
                                           landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                           landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
                'right_forearm': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value],
                                                landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]),
                'left_forearm': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                               landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value],
                                               landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]),
                'left_shoulder_right_shoulder_right_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                         landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                         landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'right_shoulder_left_shoulder_left_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                        landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                        landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
                'left_shoulder_left_hip_right_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                   landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                                   landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'right_shoulder_right_hip_left_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                    landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                                    landmarks[mp_pose.PoseLandmark.LEFT_HIP.value])
            }
            return angles, landmarks  # Return both angles and landmarks
        else:
            return None, None

def analyzeVideo(video_path, reference_angles1, reference_landmarks1,reference_angles2, reference_landmarks2,reference_angles3, reference_landmarks3,reference_angles4, reference_landmarks4,reference_angles5, reference_landmarks5,reference_angles6, reference_landmarks6,reference_angles7, reference_landmarks7,reference_angles8, reference_landmarks8,reference_angles9, reference_landmarks9):
    with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(10)
        cap2 = cv2.VideoCapture(video_path)

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec
        out = cv2.VideoWriter('visual1_video.avi', fourcc,20.0, (640, 480))  # Output file setup
        start_time = time.time()
        while cap.isOpened() and cap2.isOpened():
            if time.time() - start_time > 60:  # Check if 5 minutes (300 seconds) have passed
                print("5 minutes reached. Exiting...")
                break
            success, frame = cap.read()  # Webcam feed (right side)
            success1, frame2 = cap2.read()  # Existing video feed (left side)

            if not success or not success1:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)
            frame_height, frame_width, _ = frame.shape
            frame2_height, frame2_width, _ = frame2.shape

            # Resize both frames to the same height before combining
            if frame_height != frame2_height:
                scale_factor = frame_height / frame2_height
                new_width_frame2 = int(frame2_width * scale_factor)
                frame2_resized = cv2.resize(frame2, (new_width_frame2, frame_height))
            else:
                frame2_resized = frame2

            analysis_frame = frame.copy()
            
            if results.pose_landmarks:
                landmarks = [(int(lm.x * frame_width), int(lm.y * frame_height), lm.z * frame_width) for lm in results.pose_landmarks.landmark]
                current_angles = {
                    'right_arm': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value],
                                                landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                    'left_arm': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value],
                                               landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                               landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
                    'right_forearm': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                    landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value],
                                                    landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]),
                    'left_forearm': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                   landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value],
                                                   landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]),
                    'left_shoulder_right_shoulder_right_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                             landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                             landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                    'right_shoulder_left_shoulder_left_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                            landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                            landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
                    'left_shoulder_left_hip_right_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                                                                       landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                                       landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                    'right_shoulder_right_hip_left_hip': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                                                                        landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                                        landmarks[mp_pose.PoseLandmark.LEFT_HIP.value])
                }

                # Draw landmarks and connections
                mp_drawing.draw_landmarks(analysis_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                          mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                                          mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2))

                # Calculate similarity score
                score1 = 100 - np.mean([abs(current_angles[key] - reference_angles1[key]) for key in current_angles])
                score2 = 100 - np.mean([abs(current_angles[key] - reference_angles2[key]) for key in current_angles])
                score3 = 100 - np.mean([abs(current_angles[key] - reference_angles3[key]) for key in current_angles])
                score4 = 100 - np.mean([abs(current_angles[key] - reference_angles4[key]) for key in current_angles])
                score5 = 100 - np.mean([abs(current_angles[key] - reference_angles5[key]) for key in current_angles])
                score6 = 100 - np.mean([abs(current_angles[key] - reference_angles6[key]) for key in current_angles])
                score7 = 100 - np.mean([abs(current_angles[key] - reference_angles7[key]) for key in current_angles])
                score8 = 100 - np.mean([abs(current_angles[key] - reference_angles8[key]) for key in current_angles])
                score9 = 100 - np.mean([abs(current_angles[key] - reference_angles9[key]) for key in current_angles])
                get_score=max(score1,score2,score3,score4,score5,score6,score7,score8,score9)
                score_text = f"Similarity Score: {get_score:.2f}%"

                # Display the similarity score on the frame
                cv2.putText(analysis_frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                # Draw red lines where angles differ significantly (set your own threshold)
                threshold = 10 # Define your threshold for angle difference
                for key in current_angles:
                    if abs(current_angles[key] - reference_angles1[key]) > threshold:
                        # Draw red lines between corresponding landmark points
                        if key == 'right_arm':
                            start_point = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
                        elif key == 'left_arm':
                            start_point = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
                        elif key == 'right_forearm':
                            start_point = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]
                            end_point = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
                        elif key == 'left_forearm':
                            start_point = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]
                            end_point = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]
                        elif key == 'left_shoulder_right_shoulder_right_hip':
                            start_point = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
                        elif key == 'right_shoulder_left_shoulder_left_hip':
                            start_point = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
                        elif key == 'left_shoulder_left_hip_right_hip':
                            start_point = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
                        elif key == 'right_shoulder_right_hip_left_hip':
                            start_point = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
                            end_point = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]

                        cv2.line(analysis_frame, start_point[:2], end_point[:2], (0, 0, 255), 2)

            # Combine the resized frames side by side (existing video on left, analysis on right)
            combined_frame = np.hstack((frame2_resized, analysis_frame))

            # Resize the combined frame for display
            combined_frame_resized = cv2.resize(combined_frame, (0, 0), fx=0.6, fy=0.9)

            # Write the output to the video file
            out.write(analysis_frame)

            # Display the combined frame
            cv2.imshow('Original vs Analyzed Video', analysis_frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break


        cap.release()
        out.release()
        cv2.destroyAllWindows()

# Replace with the path to your input image for reference and video
reference_image_path1 = 'Screenshot from 2024-10-30 11-45-14.png'
reference_image_path2 = 'Screenshot 2024-11-08 122356.png'
reference_image_path3 = 'Screenshot 2024-11-08 122257.png'
reference_image_path4 = 'Screenshot 2024-11-08 122008.png'
reference_image_path5 = 'Screenshot 2024-11-08 121728.png'
reference_image_path6 = 'Screenshot 2024-11-08 121652.png'
reference_image_path7 = 'Screenshot 2024-11-08 121631.png'
reference_image_path8 = 'Screenshot 2024-11-08 121523.png'
reference_image_path9 = 'Screenshot 2024-11-08 121407.png'

video_path = 'BK_1_FIVE_MINS(1).mp4'

# Get the reference angles
reference_angles1, reference_landmarks1 = processImage(reference_image_path1)
reference_angles2, reference_landmarks2 = processImage(reference_image_path2)
reference_angles3, reference_landmarks3 = processImage(reference_image_path3)
reference_angles4, reference_landmarks4 = processImage(reference_image_path4)
reference_angles5, reference_landmarks5 = processImage(reference_image_path5)
reference_angles6, reference_landmarks6 = processImage(reference_image_path6)
reference_angles7, reference_landmarks7 = processImage(reference_image_path7)
reference_angles8, reference_landmarks8 = processImage(reference_image_path8)
reference_angles9, reference_landmarks9 = processImage(reference_image_path9)
if reference_angles1:
    print("Reference angles:", reference_angles1)
    analyzeVideo(video_path, reference_angles1, reference_landmarks1,reference_angles2, reference_landmarks2,reference_angles3, reference_landmarks3,reference_angles4, reference_landmarks4,reference_angles5, reference_landmarks5,reference_angles6, reference_landmarks6,reference_angles7, reference_landmarks7,reference_angles8, reference_landmarks8,reference_angles9, reference_landmarks9)
else:
    print("Pose landmarks not detected in the reference image.")

