import cv2
from tkinter import *
from PIL import Image, ImageTk
import sys
import os

class CCTV:
    def __init__(self, root, camera_indices):
        self.root = root
        self.camera_indices = camera_indices
        self.caps = [cv2.VideoCapture(i) for i in camera_indices]
        self.frames = [None] * len(camera_indices)
        self.labels = [Label(root) for _ in camera_indices]
        self.status_labels = [Label(root, text="", font=("Helvetica", 16), bg="white") for _ in camera_indices]

        for i, label in enumerate(self.labels):
            row, col = divmod(i, 2)
            label.grid(row=row*2, column=col)  # Place camera feed on even rows

        for i, status_label in enumerate(self.status_labels):
            row, col = divmod(i, 2)
            status_label.grid(row=row*2+1, column=col)  # Place status text on odd rows

        self.update_video()

    def update_video(self):
        for i, cap in enumerate(self.caps):
            ret, frame = cap.read()
            if ret:
                frame = cv2.resize(frame, (900, 485))  # Resize to fit the grid
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                self.frames[i] = frame
                self.status_labels[i].config(text="Working", fg="green")
            else:
                self.frames[i] = None
                self.status_labels[i].config(text="Not Working", fg="red")

        for i, frame in enumerate(self.frames):
            if frame is not None:
                img = Image.fromarray(frame)
                imgtk = ImageTk.PhotoImage(image=img)
                self.labels[i].imgtk = imgtk
                self.labels[i].config(image=imgtk)
            else:
                self.labels[i].config(image='')

        self.root.after(10, self.update_video)

    def release(self):
        for cap in self.caps:
            cap.release()

# Initialize the main window
root = Tk()
root.title("Sensors Checking......")
root.attributes('-fullscreen', True)  # Set the window to full screen

# Set the window size to 1920x1080
root.geometry("1920x1080")

# Create CCTV instance with camera indices (0, 1, 2, 3)
cctv = CCTV(root, [0, 1, 2, 3])

# Add a quit button to the screen
def quit_application():
    cctv.release()
    root.destroy()
    # Execute the command to redirect to the sensor checking page
    os.system('curl http://127.0.0.1:5000/sensor_check') 

quit_button = Button(root, text="Quit", command=quit_application, font=("Helvetica", 16), bg="red", fg="white")
quit_button.grid(row=4, columnspan=2, pady=20)

# Run the main loop
root.protocol("WM_DELETE_WINDOW", quit_application)
root.mainloop()
