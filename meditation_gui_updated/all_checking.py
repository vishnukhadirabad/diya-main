import tkinter as tk
import subprocess
import threading

def close_window():
    root.quit()

# Function to run a shell script and capture the output
def run_script(script_path, text_widget):
    # Run the script in the background
    process = subprocess.Popen(script_path, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Continuously capture the output of the script and update the Tkinter Text widget
    for line in iter(process.stdout.readline, b''):
        text_widget.insert(tk.END, line.decode('utf-8'))
        text_widget.yview(tk.END)  # Scroll to the bottom
    process.stdout.close()
    process.wait()  # Wait for the process to complete
    # If there are any error messages, print them
    for line in iter(process.stderr.readline, b''):
        text_widget.insert(tk.END, line.decode('utf-8'))
        text_widget.yview(tk.END)
    process.stderr.close()

# Create the main window
root = tk.Tk()
root.title("CCTV Layout")
root.geometry("3840x2160")  # Full-screen window size

# Create the main frame that holds all sections
frame = tk.Frame(root)
frame.pack(fill=tk.BOTH, expand=True)

# Left Frame: Create two sections on the left side
left_frame = tk.Frame(frame, width=1920, height=2160)  # Half the width of screen
left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

# Right Frame: Create three sections on the right side
right_frame = tk.Frame(frame, width=1920, height=2160)  # Half the width of screen
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

# Left-side sections
left_section1 = tk.Text(left_frame, width=40, height=10, bg="lightblue", font=("Helvetica", 12))
left_section1.pack(fill=tk.BOTH, expand=True)

left_section2 = tk.Text(left_frame, width=40, height=10, bg="lightblue", font=("Helvetica", 12))
left_section2.pack(fill=tk.BOTH, expand=True)

# Right-side sections
right_section1 = tk.Text(right_frame, width=40, height=10, bg="lightgreen", font=("Helvetica", 12))
right_section1.pack(fill=tk.BOTH, expand=True)

right_section2 = tk.Text(right_frame, width=40, height=10, bg="lightgreen", font=("Helvetica", 12))
right_section2.pack(fill=tk.BOTH, expand=True)

right_section3 = tk.Text(right_frame, width=40, height=10, bg="lightgreen", font=("Helvetica", 12))
right_section3.pack(fill=tk.BOTH, expand=True)

# Add Close button at the bottom
close_button = tk.Button(root, text="Close", command=close_window, font=("Helvetica", 12))
close_button.pack(side=tk.BOTTOM, pady=20)

# Start all the scripts in separate threads
def run_all_scripts():
    # Run each script in a separate thread
    threading.Thread(target=run_script, args=("./check_radar", left_section1)).start()
    threading.Thread(target=run_script, args=("./checkvisual1.sh", right_section1)).start()
    #threading.Thread(target=run_script, args=("./check_thermal", left_section2)).start()
    #threading.Thread(target=run_script, args=("./checkvisual2.sh", right_section2)).start()
    #threading.Thread(target=run_script, args=("./depthstart", right_section3)).start()

# Call the function to run all scripts when the GUI is ready
run_all_scripts()

# Start the main loop
root.mainloop()

