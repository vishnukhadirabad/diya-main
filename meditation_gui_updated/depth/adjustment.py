import cv2
import mediapipe as mp
import numpy as np
import math
import pyautogui
import pyrealsense2 as rs
import time
import os

# MediaPipe setup
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# Screen size
screen_width, screen_height = pyautogui.size()

# Load reference image
ref_image = cv2.imread("Screenshot from 2025-05-07 10-45-22.png")

# Calculate angle between three points
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

# Process static image to extract angles
def processImage(image_path):
    with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5, model_complexity=2) as pose:
        image = cv2.imread(image_path)
        image_height, image_width, _ = image.shape
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = pose.process(image_rgb)

        if results.pose_landmarks:
            landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width)
                         for lm in results.pose_landmarks.landmark]
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
                'left_shoulder_right_shoulder_right_hip': calculateAngle(
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'right_shoulder_left_shoulder_left_hip': calculateAngle(
                    landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
                'left_shoulder_left_hip_right_hip': calculateAngle(
                    landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
                    landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
                'right_shoulder_right_hip_left_hip': calculateAngle(
                    landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
                    landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
                    landmarks[mp_pose.PoseLandmark.LEFT_HIP.value])
            }
            return angles
        else:
            return None

# Real-time comparison using webcam and RealSense depth
def compareWithWebcam(reference_angles):
    # Start RealSense
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device('243322072083')
    config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    pipeline.start(config)

    with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
        cap = cv2.VideoCapture(0)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter('output.mp4', fourcc, 20.0, (640, 480))
        start_time = time.time()
        duration = 30

        #cv2.namedWindow("Live Pose", cv2.WND_PROP_FULLSCREEN)
        #cv2.setWindowProperty("Live Pose", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        try:
            while cap.isOpened():
                ret, webcam_image = cap.read()
                if not ret:
                    continue

                # Get RealSense depth frame
                frames = pipeline.wait_for_frames()
                depth_frame = frames.get_depth_frame()
                if not depth_frame:
                    continue
                depth_image = np.asanyarray(depth_frame.get_data())
                depth_colormap = cv2.applyColorMap(
                    cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET
                )

                webcam_image = cv2.flip(webcam_image, 1)
                image_rgb = cv2.cvtColor(webcam_image, cv2.COLOR_BGR2RGB)
                results = pose.process(image_rgb)
                image_height, image_width, _ = webcam_image.shape

                if results.pose_landmarks:
                    landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width)
                                 for lm in results.pose_landmarks.landmark]

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
    'left_shoulder_right_shoulder_right_hip': calculateAngle(
        landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
    'right_shoulder_left_shoulder_left_hip': calculateAngle(
        landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]),
    'left_shoulder_left_hip_right_hip': calculateAngle(
        landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.LEFT_HIP.value],
        landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]),
    'right_shoulder_right_hip_left_hip': calculateAngle(
        landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value],
        landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value],
        landmarks[mp_pose.PoseLandmark.LEFT_HIP.value])
}


                    mp_drawing.draw_landmarks(
                        webcam_image, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                        mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                        mp_drawing.DrawingSpec(color=(245, 66, 230), thickness=2, circle_radius=2)
                    )

                    # Score
                    score = 100 - np.mean([abs(current_angles[key] - reference_angles[key]) for key in current_angles])
                    cv2.putText(webcam_image, f"Similarity Score: {score:.2f}%", (50, 50),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                    out.write(webcam_image)

                    # Combine display
                    half_width = screen_width // 2
                    third_height = screen_height // 2

                    resized_ref = cv2.resize(ref_image, (half_width, screen_height))
                    resized_webcam = cv2.resize(webcam_image, (half_width, third_height))
                    resized_depth = cv2.resize(depth_colormap, (half_width, third_height))

                    right_column = np.vstack((resized_webcam, resized_depth))
                    combined = np.hstack((resized_ref, right_column))

                    cv2.imshow('Live Pose', combined)

                if cv2.waitKey(5) & 0xFF == 27 or time.time() - start_time > duration:
                    break
        finally:
            cap.release()
            out.release()
            pipeline.stop()
            cv2.destroyAllWindows()

# Main
if __name__ == "__main__":
    input_image_path = 'Puspendu_P1.jpg'
    angles_from_image = processImage(input_image_path)
    if angles_from_image:
        compareWithWebcam(angles_from_image)
    else:
        print("No landmarks detected in the input image.")

