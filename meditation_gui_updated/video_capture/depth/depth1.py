import pyrealsense2 as rs
import mediapipe as mp
import numpy as np
import cv2
import math

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_connections = mp_pose.POSE_CONNECTIONS
pose = mp_pose.Pose(static_image_mode=False, model_complexity=2, enable_segmentation=False)

# Initialize RealSense pipeline
pipeline = rs.pipeline()
config = rs.config()

# Configure depth and color streams
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

# Start streaming
pipeline.start(config)

# Get RealSense depth intrinsics for mapping 2D to 3D
profile = pipeline.get_active_profile()
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
intrinsics = depth_stream.get_intrinsics()

# Function to calculate Euclidean distance
def calculate_distance(point1, point2):
    return math.sqrt(sum((p1 - p2) ** 2 for p1, p2 in zip(point1, point2)))

try:
    while True:
        # Wait for frames
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()

        if not color_frame or not depth_frame:
            continue

        # Convert frames to numpy arrays
        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())

        # Convert BGR image to RGB for MediaPipe
        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)

        # Run MediaPipe Pose
        results = pose.process(rgb_image)

        if results.pose_landmarks:
            annotated_image = color_image.copy()
            h, w, _ = annotated_image.shape

            # Extract 2D keypoints
            keypoints_2d = []
            keypoints_3d = {}

            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                
                # Ensure coordinates are within the depth frame bounds
                if 0 <= x < depth_frame.width and 0 <= y < depth_frame.height:
                    z = depth_frame.get_distance(x, y)
                else:
                    z = 0  # Set to 0 if out of bounds

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
            cv2.imshow("Pose Detection with 3D", annotated_image)

        # Display depth image
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)
        cv2.imshow("Depth Image", depth_colormap)

        # Break loop with ESC key
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    pipeline.stop()
    cv2.destroyAllWindows()

