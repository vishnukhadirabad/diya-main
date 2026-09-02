# Import required libraries
import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import serial
import csv
import numpy as np
import math
from collections import deque
from sklearn.metrics.pairwise import cosine_similarity

elapsed = 0
start_time = time.time()
total=90

# Initialize MediaPipe Pose and FaceMesh modules
mp_pose = mp.solutions.pose
pose_detector = mp_pose.Pose(min_detection_confidence=0.3, min_tracking_confidence=0.3)
mp_face_mesh = mp.solutions.face_mesh

# Initialize serial communication (replace with appropriate COM port)
com = serial.Serial('/dev/ttyACM0', baudrate=9600, timeout=1)

# Camera calibration parameters (obtained from chessboard calibration of 115° wide-angle camera) 
# These values are updated from camera calibration.py
camera_matrix = np.array([[334.57061656, 0, 299.5606889], [0, 334.87557247, 256.56460557], [0, 0, 1]])
dist_coeffs = np.array([-3.2513905e-01, 1.29654852e-01, 1.68325779e-04, 2.77664819e-05, -2.66250070e-02])

# Variables to store previously updated keypoint values
updated_nose_x, updated_nose_y, updated_chest_y = 0, 0, 0

# Conversion constants (pixel to cm and pulses), and range boundaries (global coordinates)
# These values are updated from calculations.py
px_cm_nose_x = 0.2635 
px_cm_nose_y = 0.08   
px_cm_chest_y = 0.2459
px_pulses_nose_x = 843.294
px_pulses_nose_y = 271.1
px_pulses_chest_y = 786.885
dx = 254.90           #Homing position pixel values in nose_x
dy = 183.2            #Homing position pixel values in nose_y
dy_chest = 225        #Homing position pixel values in chest_y
end_nose_x = 159.375  #The other end of the rail in nose_x pixel 
end_nose_y = 93       #The other end of the rail in nose_y pixel 
end_chest_y = 61      #The other end of the rail in chest_y pixel 

        
		
# Capture undistorted stable nose keypoints and compute average
def detect_stable_nose():
    cap = cv2.VideoCapture(10)
    print("Detecting stable nose position...")

    distorted_nose_positions = deque(maxlen=10)
    undistorted_nose_positions = deque(maxlen=10)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Error: Camera feed not available.")
            break
        frame = cv2.flip(frame, 1)
        #Undistort the frame
        undistorted_frame = cv2.undistort(frame, camera_matrix, dist_coeffs, None)
        rgb_frame = cv2.cvtColor(undistorted_frame, cv2.COLOR_BGR2RGB)
        pose_results = pose_detector.process(rgb_frame)

        if pose_results.pose_landmarks:
            h, w, _ = undistorted_frame.shape

            # Utility to get a landmark
            def get_landmark(landmark_id):
                lm = pose_results.pose_landmarks.landmark[landmark_id]
                return int(lm.x * w), int(lm.y * h)

            # Extract facial keypoints
            nose_x, nose_y = get_landmark(mp_pose.PoseLandmark.NOSE)
            chin_x, chin_y = get_landmark(mp_pose.PoseLandmark.MOUTH_LEFT)
            forehead_x, forehead_y = get_landmark(mp_pose.PoseLandmark.RIGHT_EYE)
            face_height = abs(forehead_y - chin_y)

            # Undistort the nose point pixels 
            nose_undistorted = cv2.undistortPoints(np.array([[nose_x, nose_y]], dtype=np.float32),
                                                   camera_matrix, dist_coeffs, None, camera_matrix)
            nose_x_u, nose_y_u = int(nose_undistorted[0][0][0]), int(nose_undistorted[0][0][1])

            # Append to buffer
            distorted_nose_positions.append((nose_x, nose_y))
            undistorted_nose_positions.append((nose_x_u, nose_y_u))

            # Evaluate stability
            if len(distorted_nose_positions) == 10:
                avg_x_d = sum(p[0] for p in distorted_nose_positions) / 10
                avg_y_d = sum(p[1] for p in distorted_nose_positions) / 10
                avg_x_u = sum(p[0] for p in undistorted_nose_positions) / 10
                avg_y_u = sum(p[1] for p in undistorted_nose_positions) / 10

                if abs(nose_x_u - avg_x_u) < 5 and abs(nose_y_u - avg_y_u) < 5:
                    cap.release()
                    return (avg_x_d, avg_y_d, avg_x_u, avg_y_u, face_height)
                else:
                    print("Nose position is not stable")

    cap.release()
    return None, None, None, None, None


# Capture right shoulder position from live camera feed
def detect_shoulder():
    cap = cv2.VideoCapture(10)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            print("Error: Camera feed not available.")
            break
        frame = cv2.flip(frame, 1)
        # Undistort the frame
        undistorted_frame = cv2.undistort(frame, camera_matrix, dist_coeffs, None)
        rgb_frame = cv2.cvtColor(undistorted_frame, cv2.COLOR_BGR2RGB)
        pose_results = pose_detector.process(rgb_frame)

        if pose_results.pose_landmarks:
            h, w, _ = undistorted_frame.shape
            right_shoulder = pose_results.pose_landmarks.landmark[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            right_shoulder_x = int(right_shoulder.x * w)
            right_shoulder_y = int(right_shoulder.y * h)

            # Convert shoulder to undistorted pixels
            distorted_points = np.array([[[right_shoulder_x, right_shoulder_y]]], dtype=np.float32)
            undistorted_points = cv2.undistortPoints(distorted_points, camera_matrix, dist_coeffs, None, camera_matrix)
            right_shoulder_x_u = int(undistorted_points[0][0][0])
            right_shoulder_y_u = int(undistorted_points[0][0][1])

            cap.release()
            return right_shoulder_x_u, right_shoulder_y_u

    cap.release()
    return None, None


# Process image to extract 3D facial landmarks using MediaPipe FaceMesh
def processImage(image_path):
    with mp_face_mesh.FaceMesh(static_image_mode=True, min_detection_confidence=0.5) as face_mesh:
        image = cv2.imread(image_path)
        image_height, image_width, _ = image.shape
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(image_rgb)
        if results.multi_face_landmarks:
            landmarks = [(int(lm.x * image_width), int(lm.y * image_height), int(lm.z * image_width)) for lm in
                         results.multi_face_landmarks[0].landmark]
            return landmarks
        else:
            return None


# Calculate cosine similarity between two sets of 3D landmarks
def calculate_similarity(landmarks1, landmarks2):
    landmarks1 = np.array(landmarks1).flatten().reshape(1, -1)
    landmarks2 = np.array(landmarks2).flatten().reshape(1, -1)
    return cosine_similarity(landmarks1, landmarks2)[0][0] * 100


# Normalize 3D facial landmarks with respect to image dimensions
def normalize_landmarks(landmarks, img_width, img_height):
    return [(lm[0] / img_width, lm[1] / img_height, lm[2] / img_width) for lm in landmarks]


# Compare webcam feed with stored facial reference image using landmark similarity
def compareWithWebcam(reference_landmarks):
    with mp_face_mesh.FaceMesh(min_detection_confidence=0.35) as face_mesh:
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        while cap.isOpened():
            success, image = cap.read()
            if not success:
                continue
            image = cv2.flip(image, 1)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(image_rgb)
            image_height, image_width, _ = image.shape

            if results.multi_face_landmarks:
                landmarks = [(int(lm.x * image_width), int(lm.y * image_height), lm.z * image_width) for lm in
                             results.multi_face_landmarks[0].landmark]
                landmarks_normalized = normalize_landmarks(landmarks, image_width, image_height) # Landmarks of reference image
                reference_normalized = normalize_landmarks(reference_landmarks, image_width, image_height) #Landmarks of webcam data

                score = calculate_similarity(landmarks_normalized, reference_normalized)
                score_text = f"Face Similarity Score: {score:.2f}%"
                print(score_text)
                csvwriter.writerow(score_text.split(':'))
                break
            if cv2.waitKey(5) & 0xFF == 27:
                break
        cap.release()
        cv2.destroyAllWindows()
        
# Start execution loop and save data to CSV
with open('output_data.csv', 'w', newline='') as csvfile:
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['Source', 'X', 'Y'])  # CSV header
    #global updated_nose_x, updated_nose_y, updated_chest_y
    while True:
        (avg_x_d, avg_y_d, avg_x_u, avg_y_u, face_height) = detect_stable_nose()
        (right_shoulder_x, right_shoulder_y) = detect_shoulder()

        # Step 2: Estimate chest position using face height and shoulder position
        chest_y = face_height + right_shoulder_y

	############################################################################################
	# Mathematical Calculations. 
	# Required calculations of global to local coordinate system, pixels to centimeters, pulses conversion and difference to send to the motor.
        # Step 3: Convert from global (camera) to local coordinate system
        nose_x1 = avg_x_u - dx
        nose_y1 = dy - avg_y_u
        chest_y1 = chest_y - dy_chest

        # Step 4: Bound the transformed coordinates within allowed ranges
        nose_x1 = max(0, min(nose_x1, end_nose_x))
        nose_y1 = max(0, min(nose_y1, end_nose_y))
        chest_y1 = max(0, min(chest_y1, end_chest_y))

        # Calculate differences from previous keypoints
        difference_x, difference_y = nose_x1 - updated_nose_x, nose_y1 - updated_nose_y
        difference_chest = chest_y1 - updated_chest_y
	###########################################################################################

        # Step 5: Only proceed if all coordinates are valid and within bounds
        if 0 <= nose_x1 <= end_nose_x and 0 <= nose_y1 <= end_nose_y and 0 <= chest_y1 <= end_chest_y:
            # Threshold to avoid unnecessary small movements 
            if abs(difference_x) > 15 or abs(difference_y) > 15 or abs(difference_chest) > 10:
                while True:
                    # Wait for controller signal indicating readiness
                    constant_value = com.readline().decode('utf-8').strip()
                    #constant_value = "1"
                    if constant_value == "1":
                        # Update internal keypoint memory
                        updated_nose_x = nose_x1
                        updated_nose_y = nose_y1
                        updated_chest_y = chest_y1

                        # Format the data to be sent (centimeters and pulses), Here 5 is a constant value [can be anything].
                        combined_data1 = f"5,{str((difference_x) * px_cm_nose_x)},{str((difference_y) * px_cm_nose_y)},{str((difference_chest) * px_cm_chest_y)}"
                        print(f"combined_data1:{combined_data1}")
                        combined_data = f"5,{str((difference_x) * px_pulses_nose_x)},{str((difference_y) * px_pulses_nose_y)},{str((difference_chest) * px_pulses_chest_y)}"

                        # Save and send data
                        csvwriter.writerow(combined_data.split(','))
                        com.write((combined_data + "\n").encode('utf-8'))

                        # Wait for motor status confirmation
                        i = 0
                        while i < 27:
                            status = com.readline().decode('utf-8').strip()
                            # To avoid the unnessary garbage values
                            if status in ["1", "0.00", "", "0"]:
                                continue
                            else:
                                csvwriter.writerow(status.split(','))
                                i += 1

                        # Facial similarity verification
                        input_image_path = 'Puspendu_P1_1.jpg'
                        reference_landmarks = processImage(input_image_path)
                        if reference_landmarks:
                            compareWithWebcam(reference_landmarks)
                            print("Waits for 20secs, then next iteration starts.")
                            time.sleep(20)
                            break
                        else:
                            print("No landmarks detected in the input image.")
                            

            else:
                print("No movement in person.")
                end_time = time.time()
                elapsed = end_time-start_time
                print(elapsed)
                if int(elapsed) >= total:          
                    print("Program Stopped")
                    break
                
