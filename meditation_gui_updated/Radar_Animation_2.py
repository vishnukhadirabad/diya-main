import pandas as pd
from pandas import read_csv
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

# --- Read data from CSV files ---

# Read heart output CSV and extract Time_HR, HR, and Mean_RR (HRV)
heart_df = read_csv('Radar_Heart_Output_1.csv')
t = heart_df.Time_HR.to_numpy()[0:17]      # Time values
hr = heart_df.HR.to_numpy()[0:17]            # Heart Rate (bpm)
hrv = heart_df.Mean_RR.to_numpy()[0:17]       # HRV metric (Mean_RR)

# Read breath output CSV and extract Time_BR and BR
breath_df = read_csv('Radar_Breath_Output_1.csv')
yt = breath_df.Time_BR.to_numpy()[0:17]      # Time values for breath rate
br = breath_df.BR.to_numpy()[0:17]           # Breath Rate (breaths/min)

# --- Set up the figure with three subplots ---
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(20, 15))
fig.subplots_adjust(hspace=0.5)

# Create a timer to automatically close the window after 20 seconds (20000 ms)
timer = fig.canvas.new_timer(interval=20000)
timer.add_callback(plt.close)

# Lists to accumulate data points for the animation
t_list = []
hr_list = []
br_list = []
hrv_list = []

def animate(i):
    # Append the i-th value from each series
    t_list.append(t[i])
    hr_list.append(hr[i])
    br_list.append(br[i])
    hrv_list.append(hrv[i])
    
    # --- Plot Heart Rate ---
    ax1.clear()
    ax1.plot(t_list, hr_list, marker='o', linestyle='-')
    ax1.set_xlim([min(t), max(t)])
    ax1.set_ylim([0, 150])  # Adjusted y-axis for HR as needed
    ax1.set_title("Heart Rate")
    ax1.set_xlabel("Time")
    ax1.set_ylabel("HR (bpm)")
    ax1.grid(True)
    
    # --- Plot Breath Rate ---
    ax2.clear()
    ax2.plot(t_list, br_list, marker='o', linestyle='-')
    # Use the time values from the breath CSV (yt) for the x-axis limits
    ax2.set_xlim([min(yt), max(yt)])
    ax2.set_ylim([0, 40])
    ax2.set_title("Breath Rate")
    ax2.set_xlabel("Time")
    ax2.set_ylabel("BR (breaths/min)")
    ax2.grid(True)
    
    # --- Plot HRV (Mean_RR) ---
    ax3.clear()
    ax3.plot(t_list, hrv_list, marker='o', linestyle='-')
    ax3.set_xlim([min(t), max(t)])
    ax3.set_ylim([0, 2000])  # y-limit set to 2000 as requested
    ax3.set_title("HRV (Mean_RR)")
    ax3.set_xlabel("Time")
    ax3.set_ylabel("HRV (Mean_RR)")
    ax3.grid(True)
    
    # If this is the final frame, save the figure as a PNG file
    if i == len(t) - 1:
        fig.savefig("RADAR_OUTPUT.png")

# Create the animation: each new frame is displayed for 500 ms
ani = FuncAnimation(fig, animate, frames=len(t), interval=500, repeat=False)

# Start the timer and display the animation window
timer.start()
plt.show()

