import cv2
import numpy as np
import glob

# Define the chessboard size
chessboard_size = (9, 6)
square_size = 2.5  # centimeters

# Prepare object points
objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
objp *= square_size

# Arrays to store object points and image points
objpoints = []
imgpoints = []

# Load calibration images
images = glob.glob('captured_images/*.jpg')

for fname in images:
    img = cv2.imread(fname)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ret, corners = cv2.findChessboardCorners(gray, chessboard_size, None)
    if ret:
        objpoints.append(objp)
        imgpoints.append(corners)

# Perform camera calibration
ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
# These camera_matrix and dist_coeffs value are used for calibrating the pixel values.
print(camera_matrix)
print(dist_coeffs)
# Load the test image
img = cv2.imread('test_image.jpg')
h, w = img.shape[:2]

# Compute new camera matrix
new_camera_matrix, roi = cv2.getOptimalNewCameraMatrix(camera_matrix, dist_coeffs, (w, h), 1, (w, h))

# Undistort the image
undistorted_img = cv2.undistort(img, camera_matrix, dist_coeffs, None, new_camera_matrix)

# Select some random pixel positions
pixel_positions = [(100, 100), (200, 300), (400, 400)]  # (x, y) coordinates

# Annotate the original and undistorted images
for (x, y) in pixel_positions:
    orig_pixel = img[y, x]
    undist_pixel = undistorted_img[y, x]

    text_orig = f"{orig_pixel[0]}, {orig_pixel[1]}, {orig_pixel[2]}"
    text_undist = f"{undist_pixel[0]}, {undist_pixel[1]}, {undist_pixel[2]}"

    cv2.putText(img, text_orig, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    cv2.putText(undistorted_img, text_undist, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

# Show the images
cv2.imshow("Original Image", img)
cv2.imshow("Undistorted Image", undistorted_img)

# Save the images
cv2.imwrite('annotated_original.jpg', img)
cv2.imwrite('annotated_undistorted.jpg', undistorted_img)

cv2.waitKey(0)
cv2.destroyAllWindows()
