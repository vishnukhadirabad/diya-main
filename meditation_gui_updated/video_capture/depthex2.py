import pyrealsense2 as rs
import mediapipe as mp
import numpy as np
import cv2
import math
import os

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_connections = mp_pose.POSE_CONNECTIONS
pose = mp_pose.Pose(static_image_mode=False, model_complexity=2, enable_segmentation=False)

# Initialize RealSense pipeline
pipeline = rs.pipeline()
config = rs.config()

# Configure depth stream
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)

# Start depth streaming
pipeline.start(config)

# Get RealSense depth intrinsics
profile = pipeline.get_active_profile()
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
intrinsics = depth_stream.get_intrinsics()

# Define VideoWriter to save the video
output_filename = 'rgb_depth_video.avi'
fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec for MP4 format
fps = 30  # Frames per second
frame_size = (1280, 480)  # Combined frame size (width x height)
video_writer = cv2.VideoWriter(output_filename, fourcc, fps, frame_size)

# Open RGB camera using OpenCV
cap = cv2.VideoCapture(4)  # Replace 8 with your RGB camera index

if not cap.isOpened():
    print("Error: Unable to open RGB camera.")
    exit()

# Function to calculate similarity (cosine similarity for simplicity)
def calculate_similarity(kp1, kp2):
    kp1 = np.array(kp1)
    kp2 = np.array(kp2)
    dot_product = np.sum(kp1 * kp2, axis=1)
    norm1 = np.linalg.norm(kp1, axis=1)
    norm2 = np.linalg.norm(kp2, axis=1)
    similarity = np.mean(dot_product / (norm1 * norm2 + 1e-6))  # Avoid division by zero
    return similarity

try:
    while True:
        # Capture RGB frame
        ret, rgb_frame = cap.read()
        if not ret:
            print("Error: Unable to read from RGB camera.")
            break

        # Wait for depth frame
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()

        if not depth_frame:
            continue

        # Convert depth frame to numpy array
        depth_image = np.asanyarray(depth_frame.get_data())

        # Convert BGR image to RGB for MediaPipe
        rgb_image = cv2.cvtColor(rgb_frame, cv2.COLOR_BGR2RGB)

        # Run MediaPipe Pose
        results = pose.process(rgb_image)

        if results.pose_landmarks:
            annotated_image = rgb_frame.copy()
            h, w, _ = annotated_image.shape

            # Extract 2D keypoints and 3D keypoints
            keypoints_2d = []
            keypoints_3d = []

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
                keypoints_3d.append([landmark.x, landmark.y, landmark.z])

                # Display 3D coordinates and distance on the image
                text = f"({landmark.x:.2f}, {landmark.y:.2f}, {landmark.z:.2f}) {z:.2f}"
                cv2.putText(annotated_image, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        # Apply colormap to depth data for visualization
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)
        annotated_image_resized = cv2.resize(annotated_image, (depth_colormap.shape[1], depth_colormap.shape[0]))

        # Stack RGB and depth images side by side
        side_by_side = np.hstack((annotated_image_resized, depth_colormap))

        # Write frame to video
        video_writer.write(side_by_side)

        # Display the combined frame
        cv2.imshow("RGB and Depth", side_by_side)

        # Break loop with ESC key
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    # Release resources
    cap.release()
    pipeline.stop()
    video_writer.release()
    cv2.destroyAllWindows()

