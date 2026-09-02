import cv2
import time
import mediapipe as mp
import pyrealsense2 as rs
import numpy as np

# Initialize MediaPipe Pose Detection
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
pose = mp_pose.Pose(
    static_image_mode=True, 
    min_detection_confidence=0.5,
    model_complexity=2
)
filtered_connections = [
    (start, end) for start, end in mp_pose.POSE_CONNECTIONS if start > 10 and end > 10
]

# Initialize RealSense pipeline
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)

# Define camera indices
thermal_cam_index = 8
webcam_index = 0

# Open cameras with delay
cap_thermal = cv2.VideoCapture(thermal_cam_index)
time.sleep(1)
cap_webcam = cv2.VideoCapture(webcam_index)  
time.sleep(1)


while True:
    ret1, frame_thermal = cap_thermal.read()
    ret2, frame_webcam = cap_webcam.read()

    if not ret2: 
        print("Webcam (index 0) not returning frames. Restarting...")
        cap_webcam.release()
        time.sleep(1)
        cap_webcam = cv2.VideoCapture(webcam_index)
        continue

    if not ret1:
        print("Error: One or more cameras not working.")
        break

    frames = pipeline.wait_for_frames()
    depth_frame = frames.get_depth_frame()
    color_frame = frames.get_color_frame()
    
    # Resize frames to 640x480
    frame_thermal = cv2.resize(frame_thermal, (640, 480))
    frame_webcam = cv2.resize(frame_webcam, (640, 480))
    frame_thermal = cv2.flip(frame_thermal, 1)
    frame_webcam = cv2.flip(frame_webcam, 1)

    # Convert frames to RGB (required for MediaPipe)
    rgb_webcam = cv2.cvtColor(frame_webcam, cv2.COLOR_BGR2RGB)

    # Process Pose Detection
    results_webcam = pose.process(rgb_webcam)
    
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
            filtered_connections,
            mp.solutions.drawing_utils.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
            mp.solutions.drawing_utils.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))
        
    # Combine all frames horizontally
    combined_frame = cv2.hconcat([frame_thermal, frame_webcam, annotated_image])

    # Display
    cv2.imshow("Multi-Camera Pose Detection", combined_frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cap_thermal.release()
cap_webcam.release()
cv2.destroyAllWindows()

