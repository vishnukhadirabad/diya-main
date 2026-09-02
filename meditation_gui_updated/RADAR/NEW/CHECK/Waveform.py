#C:\Users\soumi\AppData\Local\Programs\Python\Python39\Scripts
import pandas as pd
from pandas import read_csv;
import matplotlib.pyplot as plt;
from scipy import stats;
import numpy as np;
from scipy import signal
from scipy.interpolate import interp1d
from scipy.fftpack import fft
from scipy.signal import find_peaks
from scipy.signal import savgol_filter
import statistics
#import pywt
#import pdb
#https://raphaelvallat.com/yasa/build/html/generated/yasa.sliding_window.html
#from yasa import sliding_window
from scipy.interpolate import interp1d

#x = read_csv('cd6_write_Soumitra5min.csv')
x = read_csv('cd6_write_check.csv')
#tr1=x.time.to_numpy()[0:6000]
tr1=x.time.to_numpy()[-190:-1]
#print(tr)
#sr1=x.data.to_numpy()[0:6000]
sr1=x.data.to_numpy()[-190:-1]
#print(sr)
to1=min(tr1);
tf1=max(tr1);
Ts1=stats.mode(np.diff(tr1))[0];
Fs1=1/Ts1;
t1=np.arange(to1,tf1,Ts1);
f1 = interp1d(tr1, sr1)
chest1=f1(t1)
print(chest1)
print(len(chest1))

# plotting the points
#plt.plot(t1, chest1)
#plt.plot(t1, respiration)
#plt.plot(t1[peaks],respiration[peaks],'*')
#plt.plot(t1, heart)
#plt.plot(t1[peaks1],heart[peaks1],'*')
#plt.subplot(1, 2, 1)
#plt.plot(BR_T,BR)
# naming the x axis
#plt.xlabel('x - axis Time in Sec')
# naming the y axis
#plt.ylabel('y - axis BR (Breaths)') 
# giving a title to my graph
#plt.title('Breath_Rate')
#plt.ylim([0, 30])
#plt.grid()
#plt.subplot(1, 2, 2)
#plt.plot(HR_T,HR)
# naming the x axis
#plt.xlabel('x - axis Time in Sec')
# naming the y axis
#plt.ylabel('y - axis HR (Heart_Rate)') 
# giving a title to my graph
#plt.title('Heart_Rate') 
# function to show the plot
#plt.ylim([0, 150])
#plt.grid()
#plt.savefig('HR_BR.png')
#plt.show()


#https://pywavelets.readthedocs.io/en/latest/regression/multilevel.html
#db10 = pywt.Wavelet('db10')
#cA10, cD10, cD9, cD8, cD7, cD6, cD5, cD4, cD3, cD2, cD1 = pywt.wavedec(chest1, db10, level=10)
#coeffs = pywt.wavedec(chest1, db10)
#print(pywt.waverec(coeffs, db10))
    
       

#fig.tight_layout(h_pad=1)
plt.plot(t1, chest1)


#fig.set_size_inches(12.6,7)
plt.savefig('Chest_Display.png')
