import cv2
import mediapipe as mp
import numpy as np
import math

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

def analyzeVideo(video_path, reference_angles, reference_landmarks):
    with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(video_path)

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec
        out = cv2.VideoWriter('output_analyzed.mp4', fourcc, 20.0, (int(cap.get(3)), int(cap.get(4))))  # Output file setup

        while cap.isOpened():
            success, frame = cap.read()
            if not success:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)
            frame_height, frame_width, _ = frame.shape

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
                mp_drawing.draw_landmarks(frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                          mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                                          mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2))

                # Calculate similarity score
                score = 100 - np.mean([abs(current_angles[key] - reference_angles[key]) for key in current_angles])
                score_text = f"Similarity Score: {score:.2f}%"

                # Display the similarity score on the frame
                cv2.putText(frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                # Draw red lines where angles differ significantly (set your own threshold)
                threshold = 10  # Define your threshold for angle difference
                for key in current_angles:
                    if abs(current_angles[key] - reference_angles[key]) > threshold:
                        # Draw red lines between corresponding landmark points
                        # Define landmark pairs for each angle
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

                        # Draw the line on the frame
                        cv2.line(frame, start_point[:2], end_point[:2], (0, 0, 255), 2)

            # Write the frame into the output video file
            out.write(frame)

            # Display the frame
            cv2.imshow('Video Analysis', frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        out.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    reference_image_path = "Screenshot from 2024-10-30 11-45-14.png"  # Path to your reference image
    video_path = "BK_1_FIVE_MINS(1).mp4"  # Path to your input video

    # Process the reference image to extract angles
    reference_angles, reference_landmarks = processImage(reference_image_path)
    if reference_angles is not None:
        print("Reference angles processed successfully.")
        analyzeVideo(video_path, reference_angles, reference_landmarks)
    else:
        print("Failed to process the reference image.")

