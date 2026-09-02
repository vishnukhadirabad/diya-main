import cv2
import numpy as np
import time
import mediapipe as mp
import math
import pyrealsense2 as rs
import os
import threading

import posecache
import stage_runtime
from paths import (GAZE_CAM_INDEX, configure_depth_streams, fullscreen_window,
                   project_path)

# ======================== GAZE ANALYSIS SETUP ========================
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)

# ======================== DEPTH ANALYSIS SETUP ========================
mp_pose = mp.solutions.pose
pose = mp_pose.Pose(static_image_mode=False, model_complexity=2, enable_segmentation=False)

# ======================== REALSENSE SETUP ========================
# Under run_stages.py this is the pipeline splitSide already left streaming,
# so the stage starts on a warm camera instead of restarting it.
pipeline = stage_runtime.realsense(configure_depth_streams)

profile = pipeline.get_active_profile()
depth_sensor = profile.get_device().first_depth_sensor()
depth_scale = depth_sensor.get_depth_scale()
depth_stream = profile.get_stream(rs.stream.depth).as_video_stream_profile()
intrinsics = depth_stream.get_intrinsics()

# ======================== VIDEO OUTPUT SETUP ========================
output_video = project_path("Combined_Output.avi")

video_writer = cv2.VideoWriter(
    str(output_video),
    cv2.VideoWriter_fourcc(*'XVID'),
    20.0,
    (1280, 480)
)

# ======================== GLOBAL SHARED FRAMES ========================
gaze_frame = np.zeros((480, 640, 3), dtype=np.uint8)
depth_frame_out = np.zeros((480, 640, 3), dtype=np.uint8)
exit_flag = False

# ======================== REFERENCE IMAGES ========================
def load_reference_images(reference_folder):
    """Reference keypoints for the stills in reference_folder, cached on disk.

    This inference used to run on every launch and cost ~0.95s of stage startup,
    which the visitor saw as part of the black gap between stages. `pose` here is
    the streaming model the depth thread also uses, and it carries tracking state
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

def calculate_similarity(kp1, kp2):
    kp1 = np.array(kp1)
    kp2 = np.array(kp2)
    dot_product = np.sum(kp1 * kp2, axis=1)
    norm1 = np.linalg.norm(kp1, axis=1)
    norm2 = np.linalg.norm(kp2, axis=1)
    similarity = np.mean(dot_product / (norm1 * norm2 + 1e-6))
    return similarity

reference_folder = project_path("ref")
reference_poses = load_reference_images(reference_folder)

# ======================== GAZE THREAD ========================
def run_gaze():
    global gaze_frame, exit_flag
    cap = stage_runtime.capture(GAZE_CAM_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    LEFT_PUPIL_INDEX = 473
    RIGHT_PUPIL_INDEX = 468
    NOSE_INDEX = 1
    LEFT_EYE_BOUNDARY = [386, 263, 362, 374, 257]
    RIGHT_EYE_BOUNDARY = [159, 33, 133, 145, 27]

    fr = 0.6
    svr = cvr = shr = cohr = 0
    svl = cvl = shl = chl = 0
    total = look = 0
    recording_time = 60
    start_time = 1 + time.time()
    
    while not exit_flag and cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        if (time.time() - start_time) < 0:
            continue
        elif ((time.time() - start_time) < recording_time):
            results = face_mesh.process(rgb_frame)
            result_hands = hands.process(rgb_frame)
            frame_height, frame_width = rgb_frame.shape[:2]

            if results.multi_face_landmarks:
                face_landmarks = results.multi_face_landmarks[0]
                left_pupil = face_landmarks.landmark[LEFT_PUPIL_INDEX]
                right_pupil = face_landmarks.landmark[RIGHT_PUPIL_INDEX]
                nose = face_landmarks.landmark[NOSE_INDEX]

                left_pupil_pos = (int(left_pupil.x * frame_width), int(left_pupil.y * frame_height))
                right_pupil_pos = (int(right_pupil.x * frame_width), int(right_pupil.y * frame_height))
                nose_pos = (int(nose.x * frame_width), int(nose.y * frame_height))
                
                # ✅ Draw detected pupils as blue circles
                cv2.circle(frame, left_pupil_pos, 2, (0, 255, 0), -1)
                cv2.circle(frame, right_pupil_pos, 2, (0, 255, 0), -1)
                pos_left = np.array([[face_landmarks.landmark[idx].x * frame_width,
                                      face_landmarks.landmark[idx].y * frame_height]
                                     for idx in LEFT_EYE_BOUNDARY])
                pos_right = np.array([[face_landmarks.landmark[idx].x * frame_width,
                                       face_landmarks.landmark[idx].y * frame_height]
                                      for idx in RIGHT_EYE_BOUNDARY])

                if result_hands.multi_hand_landmarks:
                    hand_landmarks = result_hands.multi_hand_landmarks[0]
                    X_hand = [int(lm.x * frame_width) for lm in hand_landmarks.landmark]
                    Y_hand = [int(lm.y * frame_height) for lm in hand_landmarks.landmark]
                    x_min, x_max = min(X_hand), max(X_hand)
                    y_min, y_max = min(Y_hand), max(Y_hand)
                    x_centre = (X_hand[5] + X_hand[17]) / 2
                    y_centre = (2 * Y_hand[0] + Y_hand[9] + Y_hand[13]) / 4
                    centre = (int(x_centre), int(y_centre))

                    # Gaze ratio calculations
                    hr = max(0, min(1, (pos_right[1, 0] - 2 - right_pupil_pos[0]) / (pos_right[1, 0] - 2 - pos_right[2, 0])))
                    hl = max(0, min(1, (pos_left[2, 0] - left_pupil_pos[0]) / (pos_left[2, 0] - pos_left[1, 0])))
                    vr = max(0, min(1, (pos_right[4, 1] + 8 - right_pupil_pos[1]) / (pos_right[4, 1] + 8 - pos_right[3, 1])))
                    vl = max(0, min(1, (pos_left[4, 1] + 8 - left_pupil_pos[1]) / (pos_left[4, 1] + 8 - pos_left[3, 1])))

                    theta_v1 = math.radians(75)
                    theta_v2 = math.radians(60)
                    theta_h1 = math.radians(65)
                    theta_h2 = math.radians(66)

                    sin_vr = (1 - vr) * math.sin(theta_v1) - vr * math.sin(theta_v2)
                    cos_vr = math.sqrt(1 - sin_vr ** 2)
                    sin_hr = (1 - hr * cos_vr) * math.sin(theta_h2) - hr * cos_vr * math.sin(theta_h1)
                    cos_hr = math.sqrt(1 - sin_hr ** 2)

                    sin_vl = (1 - vl) * math.sin(theta_v1) - vl * math.sin(theta_v2)
                    cos_vl = math.sqrt(1 - sin_vl ** 2)
                    sin_hl = (1 - hl * cos_vl) * math.sin(theta_h1) - hl * cos_vl * math.sin(theta_h2)
                    cos_hl = math.sqrt(1 - sin_hl ** 2)

                    svr = sin_vr * (1 - fr) + svr * fr
                    cvr = cos_vr * (1 - fr) + cvr * fr
                    shr = sin_hr * (1 - fr) + shr * fr
                    cohr = cos_hr * (1 - fr) + cohr * fr

                    svl = sin_vl * (1 - fr) + svl * fr
                    cvl = cos_vl * (1 - fr) + cvl * fr
                    shl = sin_hl * (1 - fr) + shl * fr
                    chl = cos_hl * (1 - fr) + chl * fr

                    # Compute gaze direction
                    r = 1000
                    left_gaze = (int(left_pupil.x * frame_width - r * cvl * shl), int(left_pupil.y * frame_height - r * svl))
                    right_gaze = (int(right_pupil.x * frame_width - r * cvr * shr), int(right_pupil.y * frame_height - r * svr))
                    ng = (
                        int((left_gaze[0] + right_gaze[0]) / 2),
                        int((left_gaze[1] + right_gaze[1]) / 2),
                    )

                    occ = ((x_min < right_pupil_pos[0] < x_max and y_min < right_pupil_pos[1] < y_max) or
                           (x_min < left_pupil_pos[0] < x_max and y_min < left_pupil_pos[1] < y_max))
                    tc = 0.7
                    isclosed = ((pos_right[4, 1] - pos_right[0, 1]) / (pos_right[4, 1] - pos_right[3, 1]) >= tc and
                                (pos_left[4, 1] - pos_left[0, 1]) / (pos_left[4, 1] - pos_left[3, 1]) >= tc)

                    rr1 = math.dist([right_pupil_pos[0], right_pupil_pos[1]], [x_min, y_min])
                    rr2 = math.dist([right_pupil_pos[0], right_pupil_pos[1]], [x_max, y_min])
                    rl1 = math.dist([left_pupil_pos[0], left_pupil_pos[1]], [x_min, y_min])
                    rl2 = math.dist([left_pupil_pos[0], left_pupil_pos[1]], [x_max, y_min])
                    cr = cvr * shr / math.sqrt((cvr * shr) ** 2 + svr ** 2)
                    cl = cvl * shl / math.sqrt((cvl * shl) ** 2 + svl ** 2)
                    right_looking = (x_min < right_pupil.x * frame_width - rr1 * cr) and (x_max > right_pupil.x * frame_width - rr2 * cr)
                    left_looking = (x_min < left_pupil.x * frame_width - rl1 * cl) and (x_max > left_pupil.x * frame_width - rl2 * cl)

                    gaze_match = right_looking and left_looking
                    focused = gaze_match and not occ and not isclosed

                    total += 1

                    if not focused:
                        cv2.line(frame, right_pupil_pos, right_gaze, (0, 0, 255), 2)
                        cv2.line(frame, left_pupil_pos, left_gaze, (0, 0, 255), 2)
                        cv2.line(frame, nose_pos, ng, (0, 0, 255), 2)
                    else:
                        look += 1
                        cv2.line(frame, right_pupil_pos, centre, (0, 255, 0), 2)
                        cv2.line(frame, left_pupil_pos, centre, (0, 255, 0), 2)
                        cv2.line(frame, nose_pos, centre, (0, 255, 0), 2)

                    score = look * 100 / total
                    #cv2.putText(frame, f"Attention: {score:.1f}%", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        gaze_frame = frame.copy()
    else:
        exit_flag = True
    stage_runtime.release_capture(cap)

# ======================== DEPTH THREAD ========================
def run_depth():
    global depth_frame_out, exit_flag
    start_time = time.time()
    while not exit_flag:
        frames = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        depth_frame = frames.get_depth_frame()
        if not color_frame or not depth_frame:
            continue

        color_image = np.asanyarray(color_frame.get_data())
        depth_image = np.asanyarray(depth_frame.get_data())
        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_image)
        annotated_image = color_image.copy()

        if results.pose_landmarks:
            h, w, _ = annotated_image.shape
            keypoints_2d = []
            keypoints_3d = []

            for idx, landmark in enumerate(results.pose_landmarks.landmark):
                x = int(landmark.x * w)
                y = int(landmark.y * h)
                z = depth_frame.get_distance(x, y) if 0 <= x < w and 0 <= y < h else 0
                keypoints_2d.append((x, y))
                keypoints_3d.append([landmark.x, landmark.y, landmark.z])
                text = f"({landmark.x:.2f}, {landmark.y:.2f}, {landmark.z:.2f}) {z:.2f}"
                cv2.putText(annotated_image, text, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            similarity_scores = [calculate_similarity(keypoints_3d, ref["keypoints"]) for ref in reference_poses]
            best_match_index = np.argmax(similarity_scores)
            best_match_score = similarity_scores[best_match_index]

            cv2.putText(annotated_image, f"Similarity: {best_match_score*100:.2f}%", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            for connection in mp_pose.POSE_CONNECTIONS:
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

        depth_frame_out = cv2.resize(annotated_image, (640, 480))
        if time.time() - start_time > 15:
            exit_flag = True
    stage_runtime.stop_realsense(pipeline)

# ======================== MAIN ========================
thread_gaze = threading.Thread(target=run_gaze)
thread_depth = threading.Thread(target=run_depth)
thread_gaze.start()
thread_depth.start()

screen_width = 1920
screen_height = 1080

while not exit_flag:
    combined = np.hstack((gaze_frame, depth_frame_out))
    
    # Resize combined frame to fill the screen
    fullscreen_frame = cv2.resize(combined, (screen_width, screen_height))
    
    fullscreen_window("Combined Output")
    cv2.imshow("Combined Output", fullscreen_frame)
    
    video_writer.write(cv2.resize(combined, (1280, 480)))  # Save original size to video
    # ESC or the kiosk's hidden exit key, 'q'
    if (cv2.waitKey(1) & 0xFF) in (27, ord('q')):
        exit_flag = True
        break


thread_gaze.join()
thread_depth.join()
video_writer.release()
cv2.destroyAllWindows()
