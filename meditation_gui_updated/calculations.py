import cv2
import mediapipe as mp
import numpy as np
import csv
import time

# Initialize MediaPipe Pose model for pose estimation
mp_pose = mp.solutions.pose
pose = mp_pose.Pose()

# Camera Calibration Parameters (Modify based on calibration)
# K is the camera intrinsic matrix (focal length and optical center)
K = np.array([[334.57061656, 0, 299.5606889],
              [0, 334.87557247, 256.56460557],
              [0, 0, 1]])  # Camera matrix (Intrinsic matrix)

# Distortion coefficients for the camera lens (for undistortion of the image)
dist_coeffs = np.array([-3.2513905e-01, 1.29654852e-01,
                        1.68325779e-04, 2.77664819e-05,
                        -2.66250070e-02])  # Radial and tangential distortion coefficients


# Function to undistort points using camera calibration parameters
def undistort_points(points, K, dist_coeffs):
    """
    Undistorts a set of points using the camera matrix (K) and distortion coefficients.

    Args:
        points: Points to be undistorted, passed as a list of coordinates.
        K: Camera intrinsic matrix.
        dist_coeffs: Camera distortion coefficients.

    Returns:
        Undistorted points as numpy array.
    """
    points = np.array(points, dtype=np.float32).reshape(-1, 1, 2)  # Reshape to appropriate format for undistortion
    undistorted_points = cv2.undistortPoints(points, K, dist_coeffs, None, K)  # Apply undistortion
    return undistorted_points.reshape(-1, 2)  # Return undistorted points reshaped


def pixel_values():
    """
    Capture frames from the camera, process the pose landmarks,
    and return the undistorted pixel coordinates of the nose and right shoulder.

    Returns:
        Tuple: (undistorted nose x, undistorted nose y, undistorted right shoulder y, face length)
    """
    # Start video capture from the first available camera (0 by default)
    cap = cv2.VideoCapture(0)
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break  # If the frame is not read properly, break the loop

        # Convert the captured frame to RGB for MediaPipe Pose model processing
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb_frame)  # Process the frame for pose landmarks

        if results.pose_landmarks:
            # Extract the nose and right shoulder landmarks
            h, w, _ = frame.shape  # Get the height and width of the frame
            nose = results.pose_landmarks.landmark[mp_pose.PoseLandmark.NOSE]  # Nose landmark
            right_shoulder = results.pose_landmarks.landmark[
                mp_pose.PoseLandmark.RIGHT_SHOULDER]  # Right shoulder landmark

            # Convert the normalized (x, y) coordinates of the landmarks to pixel values
            nose_coords = (int(nose.x * w), int(nose.y * h))  # Nose pixel coordinates
            right_shoulder_coords = (
            int(right_shoulder.x * w), int(right_shoulder.y * h))  # Right shoulder pixel coordinates

            # Prepare points for undistortion (pass them as a numpy array)
            distorted_points = np.array([[nose_coords, right_shoulder_coords]], dtype=np.float32)

            # Undistort the points to correct for lens distortion
            undistorted = cv2.undistortPoints(distorted_points, K, dist_coeffs, P=K)

            # Extract the undistorted coordinates of the nose and right shoulder
            undistorted_nose_x = int(undistorted[0][0][0])
            undistorted_nose_y = int(undistorted[0][0][1])
            undistorted_right_shoulder_y = int(undistorted[1][0][1])

            # Calculate the face length (distance between undistorted nose and right shoulder)
            dx = undistorted[0][0][0] - undistorted[1][0][0]
            dy = undistorted[0][0][1] - undistorted[1][0][1]
            face_length = int(np.sqrt(dx ** 2 + dy ** 2))  # Face length in pixels

            cap.release()
            return undistorted_nose_x, undistorted_nose_y, undistorted_right_shoulder_y, face_length


# Open a CSV file to store the data (for logging measurements)
with open('calculation.csv', 'w', newline='') as csvfile:
    writer = csv.writer(csvfile)  # Create a CSV writer object
    writer.writerow(['description', 'nose.x', 'nose.y', 'chest'])  # Write the header row

    # Extract pixel values from the first position
    nose_px_x1, nose_px_y1, right_shoulder_px1, face_length = pixel_values()
    writer.writerow(['pixel values of 1st position', nose_px_x1, nose_px_y1, right_shoulder_px1, face_length])
    chest_px1 = right_shoulder_px1 + face_length  # Calculate the chest pixel coordinate

    print(nose_px_x1, nose_px_y1, chest_px1)  # Print the pixel coordinates

    # Measure the centimeter values at the first position (update these values with actual measurements)
    nose_cm_x1 = 15
    nose_cm_y1 = 2
    chest_cm1 = 7
    writer.writerow(['centimeter values of 1st position', nose_cm_x1, nose_cm_y1, chest_cm1])

    print('Move to second position after measuring the centimeter values in 50 seconds')
    time.sleep(50)  # Wait for 50 seconds before taking the second measurement

    # Extract pixel values from the second position
    nose_px_x2, nose_px_y2, right_shoulder_px2, face_length = pixel_values()
    writer.writerow(['pixel values of 2nd position', nose_px_x2, nose_px_y2, right_shoulder_px2, face_length])
    chest_px2 = right_shoulder_px2 + face_length  # Calculate the chest pixel coordinate for second position

    print(nose_px_x2, nose_px_y2, chest_px2)  # Print the pixel coordinates of the second position

    # Measure the centimeter values at the second position (update these values with actual measurements)
    nose_cm_x2 = 40
    nose_cm_y2 = 10
    chest_cm2 = 15
    writer.writerow(['centimeter values of 2nd position', nose_cm_x2, nose_cm_y2, chest_cm2])

    # Calculate the differences in pixel and centimeter values between the two positions
    nose_px_x = nose_px_x2 - nose_px_x1
    nose_px_y = nose_px_y2 - nose_px_y1
    chest_px = chest_px2 - chest_px1
    nose_cm_x = nose_cm_x2 - nose_cm_x1
    nose_cm_y = nose_cm_y2 - nose_cm_y1
    chest_cm = chest_cm2 - chest_cm1

    writer.writerow(['difference of both positions in pixels', nose_px_x, nose_px_y, chest_px])
    writer.writerow(['difference of both positions in centimeters', nose_cm_x, nose_cm_y, chest_cm])

    # Convert the differences from pixels to centimeters based on the measurements
    px_cm_nose_x = nose_cm_x / nose_px_x
    px_cm_nose_y = nose_cm_y / nose_px_y
    px_cm_chest_y = chest_cm / chest_px

    writer.writerow(['pixel to centimeter conversion', px_cm_nose_x, px_cm_nose_y, px_cm_chest_y])

    # Convert the differences from pixels to pulses (assuming 3200 pulses per centimeter)
    px_pulses_nose_x = px_cm_nose_x * 3200
    px_pulses_nose_y = px_cm_nose_y * 3200
    px_pulses_chest_y = px_cm_chest_y * 3200

    writer.writerow(['pixel to pulses conversion', px_pulses_nose_x, px_pulses_nose_y, px_pulses_chest_y])

    # Calculate the homing position in pixels based on real-world measurements
    dx = nose_px_x1 - (nose_cm_x1 * px_cm_nose_x)
    dy = nose_px_y1 - (nose_cm_y1 * px_cm_nose_y)
    dy_chest = chest_px1 - (chest_cm1 * px_cm_chest_y)

    # Verify the calculated homing position by checking against the second position
    writer.writerow(['scaling both real-time and homing position', dx, dy, dy_chest])

    # Calculate the maximum movement distance (in pixels) based on real-world measurements
    end_nose_x = 42 / px_cm_nose_x
    end_nose_y = 7.5 / px_cm_nose_y
    end_chest_y = 15 / px_cm_chest_y
    writer.writerow(['maximum distance to move the rail', end_nose_x, end_nose_y, end_chest_y])

# Release the video capture and close OpenCV windows
cv2.destroyAllWindows()
