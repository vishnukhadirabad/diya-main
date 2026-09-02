import pyrealsense2 as rs
import mediapipe as mp
import numpy as np
import cv2
import math
import os
import time

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_connections = mp_pose.POSE_CONNECTIONS
pose = mp_pose.Pose(static_image_mode=False, model_complexity=2, enable_segmentation=False)

# Initialize RealSense pipeline
pipeline = rs.pipeline()
config = rs.config()

# Set the correct device serial number
config.enable_device('239222301020')

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

# Define VideoWriter to save the video
output_filename = 'Depth_output.avi'
fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec for MP4 format
fps = 30  # Frames per second
frame_size = (1280, 480)  # Combined frame size (width x height)
video_writer = cv2.VideoWriter(output_filename, fourcc, fps, frame_size)

# Function to load reference images and extract keypoints
def load_reference_images(reference_folder):
    reference_poses = []
    for filename in os.listdir(reference_folder):
        if filename.endswith('.jpg') or filename.endswith('.png'):
            img_path = os.path.join(reference_folder, filename)
            img = cv2.imread(img_path)

            # Convert BGR image to RGB for MediaPipe
            rgb_image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Process image with MediaPipe Pose
            results = pose.process(rgb_image)

            if results.pose_landmarks:
                keypoints_3d = []
                for landmark in results.pose_landmarks.landmark:
                    keypoints_3d.append([landmark.x, landmark.y, landmark.z])
                reference_poses.append({"name": filename, "keypoints": keypoints_3d})
    return reference_poses

# Load reference keypoints
reference_folder = "ref"  # Folder containing reference images
reference_poses = load_reference_images(reference_folder)

# Function to calculate similarity (cosine similarity for simplicity)
def calculate_similarity(kp1, kp2):
    kp1 = np.array(kp1)
    kp2 = np.array(kp2)
    dot_product = np.sum(kp1 * kp2, axis=1)
    norm1 = np.linalg.norm(kp1, axis=1)
    norm2 = np.linalg.norm(kp2, axis=1)
    similarity = np.mean(dot_product / (norm1 * norm2 + 1e-6))  # Avoid division by zero
    return similarity

# Function to calculate Euclidean distance
def calculate_distance(point1, point2):
    return math.sqrt(sum((p1 - p2) ** 2 for p1, p2 in zip(point1, point2)))
# Track the start time
start_time = time.time()

try:
    while True:
    
        if time.time() - start_time > 60:
            print("5 minutes have passed. Exiting the script.")
            break
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

            # Compare detected keypoints with reference poses
            similarity_scores = [
                calculate_similarity(keypoints_3d, ref["keypoints"]) for ref in reference_poses
            ]
            best_match_index = np.argmax(similarity_scores)
            best_match_score = similarity_scores[best_match_index]

            # Display similarity percentage
            cv2.putText(annotated_image, f"Similarity: {best_match_score*100:.2f}%", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            # Highlight posture correctness for body parts only (remove facial landmarks)
            for connection in mp_connections:
                start_idx, end_idx = connection
                if start_idx < len(keypoints_3d) and end_idx < len(keypoints_3d):
                    start_point = keypoints_2d[start_idx]
                    end_point = keypoints_2d[end_idx]
                    start_ref = reference_poses[best_match_index]["keypoints"][start_idx]
                    end_ref = reference_poses[best_match_index]["keypoints"][end_idx]

                    # Compare detected line with reference line
                    detected_vector = np.array(keypoints_3d[end_idx]) - np.array(keypoints_3d[start_idx])
                    reference_vector = np.array(end_ref) - np.array(start_ref)
                    line_similarity = calculate_similarity([detected_vector], [reference_vector])

                    # Green for correct, red for incorrect
                    color = (0, 255, 0) if line_similarity > 0.8 else (0, 0, 255)
                    cv2.line(annotated_image, start_point, end_point, color, 2)

        # Ensure both images have the same size before stacking
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)
        annotated_image_resized = cv2.resize(annotated_image, (depth_colormap.shape[1], depth_colormap.shape[0]))

        # Stack images side by side
        side_by_side = np.hstack((annotated_image_resized, depth_colormap))

        # Write frame to video
        video_writer.write(side_by_side)

        # Display the combined frame
        cv2.imshow("Annotated Image and Depth Image", side_by_side)

        # Break loop with ESC key
        if cv2.waitKey(1) & 0xFF == 27:
            break

finally:
    pipeline.stop()
    video_writer.release()
    cv2.destroyAllWindows()
    

