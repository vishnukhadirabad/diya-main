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
    if (x1 == y1 == 0) or (x2 == y2 == 0) or (x3 == y3 == 0):
        return None
    angle = math.degrees(math.atan2(y3 - y2, x3 - x2) - math.atan2(y2 - y1, x2 - x1))
    if angle < 0:
        angle += 360
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
            
            # Custom points
            body_center = (
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][0] +
                 landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][0] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][0]) / 4,
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][1] +
                 landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][1] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][1]) /4,
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][2] +
                 landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][2] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][2]) / 4
            )
            
            hip_center = (
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][0]) /2,
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][1]) / 2,
                (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][2]) / 2
            )
            
            shoulder_center = (
                (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][0]) / 2,
                (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][1]) / 2,
                (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][2]) / 2
            )

            # Calculating angles
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
                # Additional angles
                'neck_inclination': calculateAngle(landmarks[mp_pose.PoseLandmark.NOSE.value],
                                                   shoulder_center,
                                                   body_center),
                'torso_inclination': calculateAngle(body_center,
                                                    hip_center,
                                                    landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'right_hip_tilt': calculateAngle(hip_center,
                                                 landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                 landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]),
                'left_hip_tilt': calculateAngle(hip_center,
                                                landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]),
                'right_knee_bend': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                  landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value],
                                                  landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]),
                'left_knee_bend': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                 landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value],
                                                 landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value])
            }
            return angles
        else:
            return None

def compareWithWebcam(reference_angles):
    with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(6)

        # Define the codec and create VideoWriter object
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # Codec
        out = cv2.VideoWriter('output.mp4', fourcc, 20.0, (640, 480))  # Output file setup

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
                
                # Custom points
                body_center = (
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][0] +
                     landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][0] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][0]) / 4,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][1] +
                     landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][1] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][1]) / 4,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][2] +
                     landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][2] + landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][2]) / 4
                )
                
                hip_center = (
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][0]) / 2,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][1]) /2,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_HIP.value][2]) / 2
                )
                
                shoulder_center = (
                    (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][0] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][0]) / 2,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][1] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][1]) / 2,
                    (landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value][2] + landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value][2]) / 2
                )

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
                    # Additional angles
                    'neck_inclination': calculateAngle(landmarks[mp_pose.PoseLandmark.NOSE.value],
                                                       shoulder_center,
                                                       body_center),
                    'torso_inclination': calculateAngle(body_center,
                                                        hip_center,
                                                        landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                    'right_hip_tilt': calculateAngle(hip_center,
                                                     landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                     landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value]),
                    'left_hip_tilt': calculateAngle(hip_center,
                                                    landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                    landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value]),
                    'right_knee_bend': calculateAngle(landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                                                      landmarks[mp_pose.PoseLandmark.RIGHT_KNEE.value],
                                                      landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE.value]),
                    'left_knee_bend': calculateAngle(landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                                                     landmarks[mp_pose.PoseLandmark.LEFT_KNEE.value],
                                                     landmarks[mp_pose.PoseLandmark.LEFT_ANKLE.value])
                }

                # Draw landmarks and connections
                mp_drawing.draw_landmarks(image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                          mp_drawing.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
                                          mp_drawing.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))

                # Filter out None values from angles
                valid_angles = {key: value for key, value in current_angles.items() if value is not None and reference_angles.get(key) is not None}

                # Calculate similarity score
                if valid_angles:
                    score = 100-np.mean([int(abs(valid_angles[key] - reference_angles[key]))%180 for key in valid_angles])
                    score_text = f"Angle Similarity Score: {score:.2f}%"

                    # Display the similarity score on the image
                    cv2.putText(image, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                # Write the frame into the file 'output.mp4'
                out.write(image)

                # Display
                cv2.imshow('Live Pose', image)
                if cv2.waitKey(5) & 0xFF == 27:
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
