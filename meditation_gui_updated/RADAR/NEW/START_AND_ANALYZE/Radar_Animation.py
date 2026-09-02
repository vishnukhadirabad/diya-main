#C:\Users\soumi\AppData\Local\Programs\Python\Python39\Scripts
import pandas as pd
from pandas import read_csv;
import matplotlib.pyplot as plt;
from matplotlib.animation import FuncAnimation
import numpy as np;
import time

t1=[]
hr1=[]
t2=[]
br1=[]


x = read_csv('Radar_Heart_Output_1.csv')
t=x.Time_HR.to_numpy()[0:17]
hr=x.HR.to_numpy()[0:17]

y = read_csv('Radar_Breath_Output_1.csv')
yt=y.Time_BR.to_numpy()[0:17]
br=y.BR.to_numpy()[0:17]


# create the figure and axes objects
fig, (ax, axx) = plt.subplots(2,1,figsize=(20, 5))
fig.subplots_adjust(hspace=0.5)

# set the timer interval 5000 milliseconds
timer = fig.canvas.new_timer(interval = 20000)
timer.add_callback(plt.close)

def animate(i):
    t1.append(t[i])
    hr1.append(hr[i])
    t2.append(yt[i])
    br1.append(br[i])
    
    
    ax.clear()
    ax.plot(t1, hr1)
    ax.set_xlim([60,300])
    ax.set_ylim([40,160])
    ax.set_title("HEART_RATE")
    ax.set_xlabel('Time')
    ax.set_ylabel('Heart Rate')
    ax.grid(True)
    
    
    axx.clear()
    axx.plot(t1, br1)
    axx.set_xlim([60,300])
    axx.set_ylim([0,40])
    axx.set_title("BREATH_RATE")
    axx.set_xlabel('Time')
    axx.set_ylabel('Breath Rate')
    axx.grid(True)

# run the animation
ani = FuncAnimation(fig, animate, frames=(len(t)), interval=500, repeat=False)

timer.start()
plt.show()

