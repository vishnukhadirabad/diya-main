import cv2
import time
import numpy as np
import argparse
import io

# Open the video source (could be webcam or a file)
cap = cv2.VideoCapture(6)  # 0 is typically the default webcam

# Ensure the video capture is open
if not cap.isOpened():
    print("Error: Could not open camera.")
    exit()

# Define the frame width and height
newWidth = 640
newHeight = 480
'''
ret, frame = cap.read()
imdata,thdata = np.array_split(frame, 2)
bgr = cv2.cvtColor(imdata,  cv2.COLOR_YUV2BGR_YUYV)
bgr = cv2.resize(bgr,(newWidth,newHeight),interpolation=cv2.INTER_CUBIC)#Scale up!
heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_HOT)
'''

# Create a VideoWriter object to save the video
videoOut = cv2.VideoWriter('seek1.avi', cv2.VideoWriter_fourcc(*'XVID'), 25, (newWidth, newHeight))

# Create a window to display the video feed
cv2.namedWindow('Thermal', cv2.WINDOW_NORMAL)

# Counter for naming consecutive CSV files
file_counter = 0

# Get the start time
start_time = time.time()

while True:
    ret, frame = cap.read()
    imdata,thdata = np.array_split(frame, 2)
    # Split the frame into two parts: imdata and thdata
    #imdata, thdata = np.array_split(frame, 2, axis=1)  # Split along the columns
    # thdata is temperature
    # Save thdata as a CSV file
    # Create a unique filename based on the file_counter and timestamp
    #filename = f"thdata_{file_counter}.csv"
    #np.savetxt(filename, thdata.reshape(-1, thdata.shape[-1]), delimiter=",")
    
    # Increment the file counter for the next CSV file
    #file_counter += 1
    #bgr = cv2.cvtColor(imdata,  cv2.COLOR_YUV2BGR_YUYV)
    bgr = cv2.resize(imdata,(newWidth,newHeight),interpolation=cv2.INTER_CUBIC)#Scale up!
    heatmap = cv2.applyColorMap(bgr, cv2.COLORMAP_HOT)
    
    if not ret:
        print("Error: Failed to capture image.")
        break

    # Resize the frame to the desired resolution
    #frame_resized = cv2.resize(frame, (newWidth, newHeight))

    # Show the frame in the window
    #cv2.imshow('Thermal', frame_resized)
    cv2.imshow('Thermal', heatmap)

    # Write the frame to the output video
    videoOut.write(heatmap)

    # Get the current elapsed time
    elapsed_time = time.time() - start_time

    # Check if 60 seconds have passed (or 'q' key is pressed)
    if elapsed_time >= 10 or cv2.waitKey(1) & 0xFF == ord('q'):
        print(f"Video recording stopped. Elapsed time: {elapsed_time:.2f} seconds.")
        break

# Release everything when done
cap.release()
videoOut.release()
cv2.destroyAllWindows()

