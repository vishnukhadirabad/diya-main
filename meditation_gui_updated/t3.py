import cv2
import os
from fpdf import FPDF
from paths import project_path

class ModernPDF(FPDF):
    def header(self):
        if self.page_no() == 1:  # Only show the header on the first page
            self.set_font("Arial", "B", 16)
            self.set_text_color(0, 51, 102)  # Dark blue
            self.cell(200, 10, "Meditation Report", ln=True, align="C")
            self.ln(5)  # Reduce space after the title to avoid a large gap

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 10)
        self.set_text_color(128, 128, 128)  # Gray color
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

def generate_report(video_file, output_video, output_pdf, snapshot_dir, gaze_video_file=None, gaze_snapshot_dir=None, thermal_video_file=None, thermal_snapshot_dir=None, depth_video_file=None, depth_snapshot_dir=None, subject_number=1):
    if not os.path.exists(video_file):
        print(f"Error: File '{video_file}' not found!")
        return

    # Create PDF instance
    pdf = ModernPDF()
    pdf.set_auto_page_break(auto=True, margin=10)

    # Add first page: Meditation Report and Subject Number
    pdf.add_page()

    # Add Subject Number (with a smaller font size to avoid overlap)
    pdf.set_font("Arial", 'B', 12)  # Corrected font size for better visibility
    pdf.cell(200, 10, f"Subject Number: {subject_number}", ln=True, align='C')
    pdf.ln(5)  # Reduced space after Subject Number to avoid large gap

    # Add Posture Analysis Report Title (on the left side)
    pdf.set_font("Arial", 'B', 14)
    pdf.set_x(10)  # Position text at the left margin
    pdf.cell(0, 10, "Posture Analysis Report", ln=True)  # Add text aligned to the left
    pdf.ln(5)  # Reduced space after Posture Analysis Report title

    # Posture Analysis Video Processing
    cap = cv2.VideoCapture(video_file)
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    fps = int(cap.get(cv2.CAP_PROP_FPS))
    out = cv2.VideoWriter(output_video, fourcc, fps, 
                           (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                            int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))

    frames_analysis = []
    frame_count = 0

    if not os.path.exists(snapshot_dir):
        os.makedirs(snapshot_dir)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        frame_count += 1
        hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        green_lower, green_upper = (35, 100, 100), (85, 255, 255)
        red_lower1, red_upper1 = (0, 100, 100), (10, 255, 255)
        red_lower2, red_upper2 = (170, 100, 100), (180, 255, 255)

        green_mask = cv2.inRange(hsv_frame, green_lower, green_upper)
        red_mask1 = cv2.inRange(hsv_frame, red_lower1, red_upper1)
        red_mask2 = cv2.inRange(hsv_frame, red_lower2, red_upper2)
        red_mask = cv2.bitwise_or(red_mask1, red_mask2)

        green_area, red_area = cv2.countNonZero(green_mask), cv2.countNonZero(red_mask)

        frame[green_mask > 0] = [0, 255, 0]
        frame[red_mask > 0] = [0, 0, 255]

        out.write(frame)

        if frame_count % 50 == 0:
            snapshot_path = os.path.join(snapshot_dir, f"frame_{frame_count}.png")
            cv2.imwrite(snapshot_path, frame)

        if green_area > 0 or red_area > 0:
            frames_analysis.append({'Frame': frame_count, 'Correct Area (Green)': green_area, 'Error Area (Red)': red_area})

    cap.release()
    out.release()

    if not frames_analysis:
        print("Error: No valid data collected from the video.")
        return

    # Add Posture Snapshots
    snapshots = [f for f in os.listdir(snapshot_dir) if f.startswith("frame_")]
    snapshots.sort()

    y_offset = 50  # Starting Y position for images
    for i, snapshot in enumerate(snapshots[:12]):  # Limit to 12 images
        if i % 3 == 0 and i != 0:
            y_offset += 60
            pdf.ln(5)  # Adding space for the next row of images
        x_offset = 10 + (i % 3) * 60
        pdf.image(os.path.join(snapshot_dir, snapshot), x=x_offset, y=y_offset, w=50)

    # Add a page break before starting the Gaze Analysis Report
    pdf.add_page()

    # If gaze video file exists, process Gaze Analysis
    if gaze_video_file:
        # Gaze Analysis Video Processing
        gaze_cap = cv2.VideoCapture(gaze_video_file)
        gaze_frame_count = 0
        gaze_analysis_snapshots = []

        if not os.path.exists(gaze_snapshot_dir):
            os.makedirs(gaze_snapshot_dir)

        while gaze_cap.isOpened():
            ret, frame = gaze_cap.read()
            if not ret:
                break
            gaze_frame_count += 1

            # Dummy gaze analysis logic - Example: Detecting a simple point (substitute with your logic)
            gaze_point = (100, 100)  # Example gaze point
            cv2.circle(frame, gaze_point, 10, (0, 0, 255), -1)  # Draw a red circle for the gaze point

            # Save a snapshot for gaze analysis
            if gaze_frame_count % 50 == 0:
                snapshot_path = os.path.join(gaze_snapshot_dir, f"gaze_frame_{gaze_frame_count}.png")
                cv2.imwrite(snapshot_path, frame)
                gaze_analysis_snapshots.append(snapshot_path)

        gaze_cap.release()

        # Add Gaze Analysis Report Title (This is added directly after Posture Analysis)
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, "Gaze Analysis Report", ln=True, align='C')
        pdf.ln(10)  # Add space after Gaze Analysis Report title

        # Add Gaze Snapshots
        y_offset = 30
        for i, gaze_snapshot in enumerate(gaze_analysis_snapshots[:12]):  # Limit to 12 images
            if i % 3 == 0 and i != 0:
                y_offset += 60
                pdf.ln(5)  # Adding space for the next row of images
            x_offset = 10 + (i % 3) * 60
            pdf.image(gaze_snapshot, x=x_offset, y=y_offset, w=50)

    # Add a page break before starting the Thermal Analysis Report
    pdf.add_page()

    # If thermal video file exists, process Thermal Analysis
    if thermal_video_file:
        # Thermal Analysis Video Processing
        thermal_cap = cv2.VideoCapture(thermal_video_file)
        thermal_frame_count = 0
        thermal_analysis_snapshots = []

        if not os.path.exists(thermal_snapshot_dir):
            os.makedirs(thermal_snapshot_dir)

        while thermal_cap.isOpened():
            ret, frame = thermal_cap.read()
            if not ret:
                break
            thermal_frame_count += 1

            # Dummy thermal analysis logic - Example: Detecting a simple point (substitute with your logic)
            thermal_point = (100, 100)  # Example thermal point
            cv2.circle(frame, thermal_point, 10, (0, 255, 0), -1)  # Draw a green circle for the thermal point

            # Save a snapshot for thermal analysis
            if thermal_frame_count % 50 == 0:
                snapshot_path = os.path.join(thermal_snapshot_dir, f"thermal_frame_{thermal_frame_count}.png")
                cv2.imwrite(snapshot_path, frame)
                thermal_analysis_snapshots.append(snapshot_path)

        thermal_cap.release()

        # Add Thermal Analysis Report Title
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, "Thermal Analysis Report", ln=True, align='C')
        pdf.ln(10)  # Add space after Thermal Analysis Report title

        # Add Thermal Snapshots
        y_offset = 30
        for i, thermal_snapshot in enumerate(thermal_analysis_snapshots[:12]):  # Limit to 12 images
            if i % 3 == 0 and i != 0:
                y_offset += 60
                pdf.ln(5)  # Adding space for the next row of images
            x_offset = 10 + (i % 3) * 60
            pdf.image(thermal_snapshot, x=x_offset, y=y_offset, w=50)

    # Add a page break before starting the Depth Analysis Report
    pdf.add_page()

    # If depth video file exists, process Depth Analysis
    if depth_video_file:
        # Depth Analysis Video Processing
        depth_cap = cv2.VideoCapture(depth_video_file)
        depth_frame_count = 0
        depth_analysis_snapshots = []

        if not os.path.exists(depth_snapshot_dir):
            os.makedirs(depth_snapshot_dir)

        while depth_cap.isOpened():
            ret, frame = depth_cap.read()
            if not ret:
                break
            depth_frame_count += 1

            # Dummy depth analysis logic - Example: Detecting a simple point (substitute with your logic)
            depth_point = (100, 100)  # Example depth point
            cv2.circle(frame, depth_point, 10, (255, 0, 0), -1)  # Draw a blue circle for the depth point

            # Save a snapshot for depth analysis
            if depth_frame_count % 50 == 0:
                snapshot_path = os.path.join(depth_snapshot_dir, f"depth_frame_{depth_frame_count}.png")
                cv2.imwrite(snapshot_path, frame)
                depth_analysis_snapshots.append(snapshot_path)

        depth_cap.release()

        # Add Depth Analysis Report Title
        pdf.set_font("Arial", 'B', 14)
        pdf.cell(200, 10, "Depth Analysis Report", ln=True, align='C')
        pdf.ln(10)  # Add space after Depth Analysis Report title

        # Add Depth Snapshots
        y_offset = 30
        for i, depth_snapshot in enumerate(depth_analysis_snapshots[:12]):  # Limit to 12 images
            if i % 3 == 0 and i != 0:
                y_offset += 60
                pdf.ln(5)  # Adding space for the next row of images
            x_offset = 10 + (i % 3) * 60
            pdf.image(depth_snapshot, x=x_offset, y=y_offset, w=50,h=35)

    # Add a page break before starting the Radar Analysis Report
    #pdf.add_page()

    # Add Radar Analysis Report Title
    #pdf.set_font("Arial", 'B', 14)
    #pdf.cell(200, 10, "Radar Analysis Report", ln=True, align='C')
    #pdf.ln(10)  # Add space after Radar Analysis Report title

    # Path to the Radar Analysis image
    #radar_image_path = str(project_path('RADAR_OUTPUT.png'))

    # Add Radar Analysis Image (make sure the image exists at the given path)
    #pdf.image(radar_image_path, x=10, y=30, w=200)

    # Save the final PDF report
    pdf.output(output_pdf)
    print(f"PDF Report Generated: {output_pdf}")

# Paths to video files and output locations
posture_video_file_path = str(project_path('visual1_video_1M.avi'))
output_video_path = str(project_path('annotated_video.avi'))
output_pdf_path = str(project_path('Complete_Report_Sub_2.pdf'))
posture_snapshot_dir_path = str(project_path('snapshots'))

# Gaze video file path and snapshots directory
gaze_video_file_path = str(project_path('Gaze_output_1M.avi'))
gaze_snapshot_dir_path = str(project_path('gaze_snapshots'))

# Thermal video file path and snapshots directory
thermal_video_file_path = str(project_path('output_morphed_video.mp4'))
thermal_snapshot_dir_path = str(project_path('thermal_snapshots'))

# Depth video file path and snapshots directory
depth_video_file_path = str(project_path('Depth_output_1M.avi'))
depth_snapshot_dir_path = str(project_path('depth_snapshots'))

# Subject number (change as needed)
subject_number = 1

# Generate the report
generate_report(posture_video_file_path, output_video_path, output_pdf_path, posture_snapshot_dir_path, gaze_video_file_path, gaze_snapshot_dir_path, thermal_video_file_path, thermal_snapshot_dir_path, depth_video_file_path, depth_snapshot_dir_path, subject_number)
