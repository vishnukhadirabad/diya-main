import pyrealsense2 as rs
import mediapipe as mp
import numpy as np
import cv2
import math
import os
import time
import pyautogui
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import posecache
import stage_runtime
from paths import configure_depth_streams, fullscreen_window, project_path

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_connections = mp_pose.POSE_CONNECTIONS
pose = mp_pose.Pose(static_image_mode=False, model_complexity=2, enable_segmentation=False)

# Start streaming — under run_stages.py the camera was already brought up
# during the stage before this one and stays open for the rest of the sequence,
# instead of being torn down and restarted at each stage boundary.
pipeline = stage_runtime.realsense(configure_depth_streams)

# Get RealSense depth intrinsics for mapping 2D to 3D
profile = pipeline.get_active_profile()
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
color_stream = profile.get_stream(rs.stream.color).as_video_stream_profile()
depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
intrinsics = depth_stream.get_intrinsics()

# Define VideoWriter to save the video
output_filename = project_path("depth", "Depth_output.avi")
fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec for MP4 format
fps = 30  # Frames per second
frame_size = (1280, 480)  # Combined frame size (width x height)
video_writer = cv2.VideoWriter(str(output_filename), fourcc, fps, frame_size)

# Function to load reference images and extract keypoints
def load_reference_images(reference_folder):
    """Reference keypoints for the stills in reference_folder, cached on disk.

    This inference used to run on every launch and cost ~0.95s of stage startup,
    which the visitor saw as part of the black gap between stages. `pose` here is
    the streaming model the main loop also uses, and it carries tracking state
    from one still to the next, so posecache re-infers the whole folder whenever
    any image in it changes — inferring only the changed ones would give
    landmarks a full pass never produces. Sorting makes that pass reproducible;
    os.listdir order depends on the filesystem.
    """
    filenames = sorted(f for f in os.listdir(reference_folder)
                       if f.endswith('.jpg') or f.endswith('.png'))
    entries = posecache.landmarks_for(
        [os.path.join(reference_folder, f) for f in filenames],
        'pose_stream_mc2', lambda: pose, recompute_all=True)
    return [{"name": filename, "keypoints": entry['landmarks']}
            for filename, entry in zip(filenames, entries) if entry['landmarks']]

# Load reference keypoints
reference_folder = project_path("depth", "ref")  # Folder containing reference images
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

# Get screen resolution
screen_width, screen_height = pyautogui.size()
half_width = screen_width // 2
half_height = screen_height // 2

# Load reference image for display
ref_img = cv2.imread(str(project_path("depth", "Screenshot 2024-12-12 111026.png")))

# Start video streaming loop
try:
    while True:
        if time.time() - start_time > 15:
            print("1 minute has passed. Exiting the script.")
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

        # Bound before the branch: the frame is displayed and recorded either
        # way, so leaving this to the pose-detected case crashed the stage with
        # a NameError whenever nobody was in frame — including on the very
        # first frame, before the visitor had settled.
        annotated_image = color_image.copy()

        if results.pose_landmarks:
            h, w, _ = annotated_image.shape

            keypoints_2d = []
            keypoints_3d = []

            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                z = depth_frame.get_distance(x, y) if 0 <= x < depth_frame.width and 0 <= y < depth_frame.height else 0
                keypoints_2d.append((x, y))
                keypoints_3d.append([landmark.x, landmark.y, landmark.z])
                cv2.putText(annotated_image, f"({landmark.x:.2f}, {landmark.y:.2f}, {landmark.z:.2f}) {z:.2f}", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            similarity_scores = [
                calculate_similarity(keypoints_3d, ref["keypoints"]) for ref in reference_poses
            ]
            best_match_index = np.argmax(similarity_scores)
            best_match_score = similarity_scores[best_match_index]

            cv2.putText(annotated_image, f"Similarity: {best_match_score*100:.2f}%", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            for connection in mp_connections:
                start_idx, end_idx = connection
                if start_idx < len(keypoints_3d) and end_idx < len(keypoints_3d):
                    start_point = keypoints_2d[start_idx]
                    end_point = keypoints_2d[end_idx]
                    start_ref = reference_poses[best_match_index]["keypoints"][start_idx]
                    end_ref = reference_poses[best_match_index]["keypoints"][end_idx]
                    detected_vector = np.array(keypoints_3d[end_idx]) - np.array(keypoints_3d[start_idx])
                    reference_vector = np.array(end_ref) - np.array(start_ref)
                    line_similarity = calculate_similarity([detected_vector], [reference_vector])
                    color = (0, 255, 0) if line_similarity > 0.8 else (0, 0, 255)
                    cv2.line(annotated_image, start_point, end_point, color, 2)

        # Process depth image
        depth_colormap = cv2.applyColorMap(cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET)

        # Resize all parts
        ref_resized = cv2.resize(ref_img, (half_width, screen_height))
        annotated_resized = cv2.resize(annotated_image, (half_width, half_height))
        depth_resized = cv2.resize(depth_colormap, (half_width, half_height))

        # Stack right side vertically
        right_combined = np.vstack((annotated_resized, depth_resized))

        # Combine left and right side
        final_output = np.hstack((ref_resized, right_combined))

        # Set full-screen window once
        if 'fullscreen_set' not in globals():
            fullscreen_window("Posture Analysis")
            fullscreen_set = True

        # Write to video
        video_writer.write(final_output)

        # Show full-screen output
        cv2.imshow("Posture Analysis", final_output)

        # Break loop with ESC or the kiosk's hidden exit key, 'q'
        if (cv2.waitKey(1) & 0xFF) in (27, ord('q')):
            break

finally:
    stage_runtime.stop_realsense(pipeline)
    video_writer.release()
    cv2.destroyAllWindows()
