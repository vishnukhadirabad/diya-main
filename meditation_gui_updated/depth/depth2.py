import pyrealsense2 as rs
import mediapipe as mp
import numpy as np
import cv2
import math

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_connections = mp_pose.POSE_CONNECTIONS

# Initialize MediaPipe Pose with desired confidence
pose = mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2)

# Use OpenCV to capture video from camera index 6
cap = cv2.VideoCapture(6)  # Open the camera with index 6

# Function to calculate Euclidean distance
def calculate_distance(point1, point2):
    return math.sqrt(sum((p1 - p2) ** 2 for p1, p2 in zip(point1, point2)))

try:
    while True:
        # Read a frame from the camera
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Convert BGR image to RGB for MediaPipe
        rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Run MediaPipe Pose
        results = pose.process(rgb_image)

        if results.pose_landmarks:
            annotated_image = frame.copy()
            h, w, _ = annotated_image.shape

            # Extract 2D keypoints
            keypoints_2d = []
            keypoints_3d = {}

            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                z = landmark.z  # z value is normalized, not in depth units

                # Add 2D and 3D keypoints
                keypoints_2d.append((x, y))
                keypoints_3d[idx] = [x, y, z]

                # Draw the point and display its coordinates
                cv2.circle(annotated_image, (x, y), 5, (0, 255, 0), -1)
                cv2.putText(annotated_image, f'{idx}: ({x},{y},{z:.2f})', (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # Draw connections and calculate distances
            for connection in mp_connections:
                start_idx, end_idx = connection
                if start_idx in keypoints_3d and end_idx in keypoints_3d:
                    start_point = keypoints_3d[start_idx]
                    end_point = keypoints_3d[end_idx]

                    # Draw line
                    cv2.line(annotated_image, tuple(keypoints_2d[start_idx]), tuple(keypoints_2d[end_idx]), (0, 0, 255), 2)

                    # Calculate distance
                    distance = calculate_distance(start_point, end_point)
                    mid_point = ((keypoints_2d[start_idx][0] + keypoints_2d[end_idx][0]) // 2,
                                 (keypoints_2d[start_idx][1] + keypoints_2d[end_idx][1]) // 2)

                    # Display distance on the line
                    cv2.putText(annotated_image, f'{distance:.2f}', mid_point, cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

            # Display annotated image
            cv2.imshow("Pose Detection", annotated_image)

        # Break loop with ESC key
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    cap.release()  # Release the webcam
    cv2.destroyAllWindows()

