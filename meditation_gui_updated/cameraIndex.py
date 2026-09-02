import cv2
for i in range(20):
    cap = cv2.VideoCapture(i)
    if cap.isOpened():
        ret, frame = cap.read()
        print(f"Camera {i}: {'Frame OK' if ret else 'No frame'}")
        cap.release()
    else:
        print(f"Camera {i}: Not available")

