import cv2
import mediapipe as mp
import numpy as np
import math
import time
import pyautogui
import pyrealsense2 as rs

# --- Screen and window setup ---
screen_width, screen_height = pyautogui.size()
half_width = screen_width // 2
half_height = screen_height // 2

# --- Pose estimation setup ---
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# --- Load static reference image (top left) ---
static_img = cv2.imread("Screenshot from 2025-05-07 10-45-22.png")
if static_img is None:
    static_img = np.zeros((half_height, half_width, 3), dtype=np.uint8)
else:
    static_img = cv2.resize(static_img, (half_width, half_height))

# --- Reference images for pose comparison (from your paste.txt) ---
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

# --- Load reference angles for similarity calculation ---
reference_angles_list = []
for path in reference_image_paths:
    angles, _ = processImage(path)
    if angles:
        reference_angles_list.append(angles)
    else:
        reference_angles_list.append({k:0 for k in [
            'right_arm','left_arm','right_forearm','left_forearm',
            'left_shoulder_right_shoulder_right_hip','right_shoulder_left_shoulder_left_hip',
            'left_shoulder_left_hip_right_hip','right_shoulder_right_hip_left_hip'
        ]})

pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
pipeline.start(config)
align = rs.align(rs.stream.color)

# --- Main loop ---
with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
    cap = cv2.VideoCapture(0)
    while True:
        # --- Top right: Pose analysis with red lines ---
        ret, frame = cap.read()
        if not ret:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        analysis_frame = frame.copy()
        frame_height, frame_width, _ = frame.shape

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
            # Draw landmarks and connections
            mp_drawing.draw_landmarks(
                analysis_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
            )
            # Similarity score
            scores = []
            for ref_angles in reference_angles_list:
                score = 100 - np.mean([abs(current_angles[key] - ref_angles[key]) for key in current_angles])
                scores.append(score)
            get_score = max(scores)
            score_text = f"Similarity Score: {get_score:.2f}%"
            cv2.putText(analysis_frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
            
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

        resized_analysis = cv2.resize(analysis_frame, (half_width, half_height))

        
        frames = pipeline.wait_for_frames()
        aligned_frames = align.process(frames)
        depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        if not depth_frame or not color_frame:
            annotated_resized = np.zeros((half_height, half_width, 3), dtype=np.uint8)
            depth_resized = np.zeros((half_height, half_width, 3), dtype=np.uint8)
        else:
            depth_image = np.asanyarray(depth_frame.get_data())
            color_image = np.asanyarray(color_frame.get_data())
            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.03),
                cv2.COLORMAP_JET
            )
            
            annotated_image = cv2.addWeighted(color_image, 0.6, depth_colormap, 0.4, 0)
            annotated_resized = cv2.resize(annotated_image, (half_width, half_height))
            depth_resized = cv2.resize(depth_colormap, (half_width, half_height))

        # --- Compose the 2x2 grid ---
        top_row = np.hstack((static_img, resized_analysis))
        bottom_row = np.hstack((annotated_resized, depth_resized))
        combined = np.vstack((top_row, bottom_row))

        cv2.imshow('Combined Analysis', combined)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    pipeline.stop()
    cv2.destroyAllWindows()

