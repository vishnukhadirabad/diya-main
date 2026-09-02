import pyrealsense2 as rs
import numpy as np
import cv2
import mediapipe as mp

# Initialize RealSense pipeline
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)

# Initialize MediaPipe Pose
mp_pose = mp.solutions.pose
pose = mp_pose.Pose()

try:
    while True:
        # Capture frames
        frames = pipeline.wait_for_frames()
        depth_frame = frames.get_depth_frame()
        color_frame = frames.get_color_frame()
        if not depth_frame or not color_frame:
            continue

        # Convert frames to numpy arrays
        depth_image = np.asanyarray(depth_frame.get_data())
        color_image = np.asanyarray(color_frame.get_data())

        # Process the color frame with MediaPipe Pose
        color_image_rgb = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        results = pose.process(color_image_rgb)

        # Draw pose landmarks
        annotated_image = color_image.copy()
        if results.pose_landmarks:
            mp.solutions.drawing_utils.draw_landmarks(
                annotated_image, 
                results.pose_landmarks, 
                mp_pose.POSE_CONNECTIONS
            )

        # Display the output
        cv2.imshow('Skeleton Tracking', annotated_image)

        # Break loop on 'q' key press
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    pipeline.stop()
    cv2.destroyAllWindows()

