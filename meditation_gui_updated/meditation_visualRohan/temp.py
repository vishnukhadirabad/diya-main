import cv2 as cv  # Import the OpenCV library
import time  # Import the time library

# Create a VideoCapture object called cap
cap = cv.VideoCapture(3)

# Start the timer
start_time = time.time()

# Initialize the frame counter
frame_counter = 0

# This is an infinite loop that will continue to run until the user presses the `q` key
while True:

    # Increment the frame counter
    frame_counter += 1

    # Read a frame from the webcam
    ret, frame = cap.read()

    # If the frame was not successfully captured, break out of the loop
    if ret is False:
        break

    # Calculate the FPS
    fps = frame_counter / (time.time() - start_time)

    # Display the FPS on the frame
    cv.putText(frame, f"FPS: {fps:.3f}", (30, 30), cv.FONT_HERSHEY_PLAIN, 1.5, (0, 255, 255), 2, cv.LINE_AA)

    # Display the frame on the screen
    cv.imshow("frame", frame)

    # Check if the user has pressed the `q` key, if yes then close the program.
    key = cv.waitKey(1)
    if key == ord("q"):
        break

# Release the VideoCapture object
cap.release()

# Close all open windows
cv.destroyAllWindows()
