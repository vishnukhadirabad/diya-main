import cv2
import mediapipe as mp
import numpy as np
import math
import pyautogui
import time

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

screen_width, screen_height = pyautogui.size()
# Load the reference image
ref_image = cv2.imread("Screenshot from 2025-05-07 10-45-22.png")
# Function to calculate angle
def calculateAngle(landmark1, landmark2, landmark3):
    x1, y1, _ = landmark1
    x2, y2, _ = landmark2
    x3, y3, _ = landmark3
    if x1==x2==x3==y1==y2==y3==0:
        return 0
    angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y1 - y2, x1 - x2))
    if angle < 0:
        angle1=-1*angle
        return min(angle1, 360+angle)
    return angle

# Function to process an image and extract angles
def processImage(image_path):
    with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5,model_complexity=2) as pose:
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
            return angles
        else:
            return None





def compareWithWebcam(reference_angles):
    with mp.solutions.pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(0)

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec
        out = cv2.VideoWriter('output.mp4', fourcc, 20.0, (640, 480))  # Output file setup
        # Start timer
        start_time = time.time()
        duration = 15  # seconds
        # Set up full-screen window
        cv2.namedWindow("Live Pose", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("Live Pose", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        while cap.isOpened():
            success, image = cap.read()
            if not success:
                continue

            image = cv2.flip(image, 1)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = pose.process(image_rgb)
            image_height, image_width, _ = image.shape

            if results.pose_landmarks:
                landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width) for lm in results.pose_landmarks.landmark]
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
                mp.solutions.drawing_utils.draw_landmarks(image, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
                                          mp.solutions.drawing_utils.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                                          mp.solutions.drawing_utils.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))

                # Calculate similarity score
                score = 100 - np.mean([abs(current_angles[key] - reference_angles[key]) for key in current_angles])
                score_text = f"Similarity Score: {score:.2f}%"

                # Display the similarity score on the image
                cv2.putText(image, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                # Write the frame into the file 'output.mp4'
                out.write(image)
                 # Resize both images to half screen width, full screen height
                half_width = screen_width // 2

                resized_ref = cv2.resize(ref_image, (half_width, screen_height))
                resized_image = cv2.resize(image, (half_width, screen_height))

                # Combine side by side
                combined = np.hstack((resized_ref, resized_image))
                # Display
                cv2.imshow('Live Pose', combined)
                if cv2.waitKey(5) & 0xFF == 27:
                    break
                # Check for 15-second timeout
                if time.time() - start_time > duration:
                    break
        # Release everything when job is finished
        cap.release()
        out.release()
        cv2.destroyAllWindows()


# Main script
if __name__ == "__main__":
    input_image_path = 'Puspendu_P1.jpg'
    angles_from_image = processImage(input_image_path)
    if angles_from_image:
        compareWithWebcam(angles_from_image)
    else:
        print("No landmarks detected in the input image.")
