import cv2
import mediapipe as mp
import numpy as np
import math
import time
import pyautogui
import pyrealsense2 as rs
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import posecache
import stage_runtime
from paths import (FRONT_CAM_INDEX, configure_depth_streams, fullscreen_window,
                   project_path, upright)

# --- Screen and window setup ---
screen_width, screen_height = pyautogui.size()
half_width = screen_width // 2
half_height = screen_height // 2

# --- Pose estimation setup ---
mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# --- Reference images for pose comparison ---
reference_image_paths = [
    project_path('depth', 'Screenshot from 2024-10-30 11-45-14.png'),
    project_path('depth', 'Screenshot 2024-11-08 122356.png'),
    project_path('depth', 'Screenshot 2024-11-08 122257.png'),
    project_path('depth', 'Screenshot 2024-11-08 122008.png'),
    project_path('depth', 'Screenshot 2024-11-08 121728.png'),
    project_path('depth', 'Screenshot 2024-11-08 121652.png'),
    project_path('depth', 'Screenshot 2024-11-08 121631.png'),
    project_path('depth', 'Screenshot 2024-11-08 121523.png'),
    project_path('depth', 'Screenshot 2024-11-08 121407.png')
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

_REF_POSE = None


def _reference_pose():
    """One Pose model reused across the reference stills — see Front.py.

    A fresh model_complexity=2 instance per image cost ~0.9s of stage startup for
    identical results.
    """
    global _REF_POSE
    if _REF_POSE is None:
        _REF_POSE = mp_pose.Pose(static_image_mode=True,
                                 min_detection_confidence=0.5, model_complexity=2)
    return _REF_POSE


def _angles(landmarks):
    return {
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

# --- Load reference angles for similarity calculation ---
reference_angles_list = []
# The inference behind this used to run on every launch and cost ~0.95s of
# stage startup, which the visitor saw as part of the black gap between stages;
# posecache keeps the landmarks on disk instead.
for entry in posecache.landmarks_for(reference_image_paths, 'pose_static_mc2',
                                     _reference_pose):
    if not entry['landmarks']:
        reference_angles_list.append({k: 0 for k in [
            'right_arm', 'left_arm', 'right_forearm', 'left_forearm',
            'left_shoulder_right_shoulder_right_hip', 'right_shoulder_left_shoulder_left_hip',
            'left_shoulder_left_hip_right_hip', 'right_shoulder_right_hip_left_hip'
        ]})
        continue
    width, height = entry['width'], entry['height']
    reference_angles_list.append(_angles(
        [(int(x * width), int(y * height), z * width) for x, y, z in entry['landmarks']]))

# --- RealSense pipeline setup ---
def _configure_realsense(config):
    # This stage has always taken whichever RealSense librealsense picks rather
    # than naming one, so select_device stays off to keep that behaviour.
    configure_depth_streams(config, fps=15, select_device=False)


# Under run_stages.py this is the pipeline the earlier depth stages left
# streaming, so the stage starts on a warm camera. That pipeline was opened at
# 30fps rather than the 15 requested here; this loop is bounded by wall clock
# and simply gets fresher frames, and align works on any frameset.
pipeline = stage_runtime.realsense(_configure_realsense)
align = rs.align(rs.stream.color)

# --- Main loop ---
with mp_pose.Pose(min_detection_confidence=0.35, model_complexity=2) as pose:
    cap = stage_runtime.capture(FRONT_CAM_INDEX)
    # Borderless full screen, no Qt toolbar (see paths.fullscreen_window).
    fullscreen_window('FRONT AND SIDE ADJUSTMENT')
    start_time = time.time()
    while True:
        ret, frame = cap.read()
        frame = upright(frame)   # left panel was sideways: camera mounted 90° rotated
        if not ret:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame_rgb)
        analysis_frame = frame.copy()
        frame_height, frame_width, _ = frame.shape
        if time.time() - start_time >= 30:
            print("30 seconds elapsed. Exiting.")
            break

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

            mp_drawing.draw_landmarks(
                analysis_frame, results.pose_landmarks, mp_pose.POSE_CONNECTIONS,
                mp_drawing.DrawingSpec(color=(245, 117, 66), thickness=2, circle_radius=2),
                mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2)
            )

            # Similarity scoring
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

        resized_analysis = cv2.resize(analysis_frame, (half_width, screen_height))

        # RealSense Frame
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

        # Stack right side vertically
        right_combined = np.vstack((annotated_resized, depth_resized))

        # Combine left and right columns
        combined = np.hstack((resized_analysis, right_combined))

        cv2.imshow('FRONT AND SIDE ADJUSTMENT', combined)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    stage_runtime.release_capture(cap)
    stage_runtime.stop_realsense(pipeline)
    cv2.destroyAllWindows()
