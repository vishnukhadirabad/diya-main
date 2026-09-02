import cv2
import mediapipe as mp
import numpy as np
import math
import time
import pyautogui

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
screen_width, screen_height = pyautogui.size()

# List of reference image paths
reference_image_paths = [
    'Screenshot from 2024-10-30 11-45-14.png',
    'Screenshot 2024-11-08 122356.png',
    'Screenshot 2024-11-08 122257.png',
    'Screenshot 2024-11-08 122008.png',
    'Screenshot 2024-11-08 121728.png',
    'Screenshot 2024-11-08 121652.png',
    'Screenshot 2024-11-08 121631.png',
    'Screenshot 2024-11-08 121523.png',
    'Screenshot 2024-11-08 121407.png'
]

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
        if image is None:
            return None, None
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
            return angles, landmarks
        else:
            return None, None

def create_reference_grid(image_paths, grid_shape=(3,3), size=(320, 240)):
    """
    Combines images into a grid.
    image_paths: list of image file paths.
    grid_shape: (rows, cols)
    size: (width, height) for each image in the grid.
    Returns a single image with all images in a grid.
    """
    images = []
    for path in image_paths:
        img = cv2.imread(path)
        if img is None:
            img = np.zeros((size[1], size[0], 3), dtype=np.uint8)  # Black placeholder
        else:
            img = cv2.resize(img, size)
        images.append(img)
    # Fill up the grid if not enough images
    while len(images) < grid_shape[0] * grid_shape[1]:
        images.append(np.zeros((size[1], size[0], 3), dtype=np.uint8))
    # Stack images in grid
    rows = []
    for i in range(grid_shape[0]):
        row = np.hstack(images[i*grid_shape[1]:(i+1)*grid_shape[1]])
        rows.append(row)
    grid = np.vstack(rows)
    return grid

def analyzeVideo(reference_angles_list):
    with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(0)
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        out = cv2.VideoWriter('visual1_video.avi', fourcc, 20.0, (640, 480))
        start_time = time.time()

        # Create the reference grid image once
        grid_rows, grid_cols = 3, 3  # For 9 reference images
        ref_grid_width = screen_width // 2
        ref_grid_height = screen_height
        ref_grid = create_reference_grid(reference_image_paths, grid_shape=(grid_rows, grid_cols),
                                         size=(ref_grid_width // grid_cols, ref_grid_height // grid_rows))

        while cap.isOpened():
            elapsed_time = time.time() - start_time
            if elapsed_time > 15:
                break

            success, frame = cap.read()
            if not success:
                print("Error: Failed to read frame(s). Exiting...")
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(frame_rgb)
            frame_height, frame_width, _ = frame.shape

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

                mp_drawing.draw_landmarks(analysis_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                                          mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                                          mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2))

                # Calculate similarity scores for all references
                scores = []
                for ref_angles in reference_angles_list:
                    score = 100 - np.mean([abs(current_angles[key] - ref_angles[key]) for key in current_angles])
                    scores.append(score)
                get_score = max(scores)
                score_text = f"Similarity Score: {get_score:.2f}%"
                cv2.putText(analysis_frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

                # Draw red lines for significant angle differences (using first reference as example)
                threshold = 10
                ref_angles = reference_angles_list[0]
                for key in current_angles:
                    if abs(current_angles[key] - ref_angles[key]) > threshold:
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

            # Resize analysis frame to half screen width, full screen height
            half_width = screen_width // 2
            resized_frame = cv2.resize(analysis_frame, (half_width, screen_height))

            # Write the output to the video file
            out.write(analysis_frame)
            # Combine reference grid and analysis frame side by side
            combined = np.hstack((ref_grid, resized_frame))
            cv2.imshow('Front', combined)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        out.release()
        cv2.destroyAllWindows()

# Process all reference images
reference_angles_list = []
for path in reference_image_paths:
    angles, _ = processImage(path)
    if angles:
        reference_angles_list.append(angles)
    else:
        # If image can't be processed, use zeros for all angles
        reference_angles_list.append({k:0 for k in [
            'right_arm','left_arm','right_forearm','left_forearm',
            'left_shoulder_right_shoulder_right_hip','right_shoulder_left_shoulder_left_hip',
            'left_shoulder_left_hip_right_hip','right_shoulder_right_hip_left_hip'
        ]})

if reference_angles_list:
    analyzeVideo(reference_angles_list)
else:
    print("No valid reference images found.")

