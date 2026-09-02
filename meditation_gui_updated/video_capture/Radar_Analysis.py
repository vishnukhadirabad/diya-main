#C:\Users\soumi\AppData\Local\Programs\Python\Python39\Scripts
import pandas as pd
from pandas import read_csv;
import matplotlib.pyplot as plt;
from scipy import stats;
from scipy.optimize import curve_fit
import numpy as np;
from scipy import signal
from scipy.interpolate import interp1d
#from scipy.integrate import trapz
from scipy.fftpack import fft
from scipy.signal import find_peaks
from scipy.signal import savgol_filter
from sklearn.decomposition import NMF
import statistics
import pywt
import pdb
import csv
rng = np.random.default_rng()
#https://raphaelvallat.com/yasa/build/html/generated/yasa.sliding_window.html
# Complete YASA functions - https://raphaelvallat.com/yasa/build/html/_modules/yasa/others.html#sliding_window
#from yasa import sliding_window
def sliding_window(data, sf, window, step=None, axis=-1):
    from numpy.lib.stride_tricks import as_strided
    assert axis <= data.ndim, "Axis value out of range."
    assert isinstance(sf, (int, float)), 'sf must be int or float'
    assert isinstance(window, (int, float)), 'window must be int or float'
    assert isinstance(step, (int, float, type(None))), ('step must be int, '
                                                        'float or None.')
    if isinstance(sf, float):
        assert sf.is_integer(), 'sf must be a whole number.'
        sf = int(sf)
    assert isinstance(axis, int), 'axis must be int.'

    # window and step in samples instead of points
    window *= sf
    step = window if step is None else step * sf

    if isinstance(window, float):
        assert window.is_integer(), 'window * sf must be a whole number.'
        window = int(window)

    if isinstance(step, float):
        assert step.is_integer(), 'step * sf must be a whole number.'
        step = int(step)

    assert step >= 1, "Stepsize may not be zero or negative."
    assert window < data.shape[axis], ("Sliding window size may not exceed "
                                       "size of selected axis")

    # Define output shape
    shape = list(data.shape)
    shape[axis] = np.floor(data.shape[axis] / step - window / step + 1
                           ).astype(int)
    shape.append(window)

    # Calculate strides and time vector
    strides = list(data.strides)
    strides[axis] *= step
    strides.append(data.strides[axis])
    strided = as_strided(data, shape=shape, strides=strides)
    t = np.arange(strided.shape[-2]) * (step / sf)

    # Swap axis: n_epochs, ..., n_samples
    if strided.ndim > 2:
        strided = np.rollaxis(strided, -2, 0)
    return t, strided

#x = read_csv('Manpreet_13_04_2022_HR_72_to_75.csv')
#x = read_csv('Soumitra_13_04_2022_HR_88_to_79.csv')
#x = read_csv('cd6_write_Soumitra5min.csv')
x = read_csv('cd6_write.csv')
#x = read_csv('Manpreet_DQ1.csv')
#x = read_csv('Manpreet_DQ2.csv')
tr1=x.time.to_numpy()[0:6000]
#print(tr)
sr1=x.data.to_numpy()[0:6000]
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

f_stft, t_stft, Zxx = signal.stft(chest1, fs=Fs1, window='hann', nperseg=128, noverlap=0.75*128, nfft=None, detrend=False, return_onesided=False, boundary=None, padded=False, axis=- 1)
A = np.absolute(Zxx)

model = NMF(n_components=2, init='random', max_iter=2000, random_state=0)
W = model.fit_transform(A)
H = model.components_


#H[1] = 0
#H_T = np.linspace(0, len(H[1])-1, len(H[1]))
#poly = np.polyfit(H_T, H[1], deg=10)
#p11 = np.polyval(poly, H_T)
p11 = savgol_filter(H[1], 5, 3)
p11 = np.where(np.abs(p11) >= statistics.mean(p11)*1.9, 0, p11)
H[1] = p11

    

#H[0] = 1.5
#H_T = np.linspace(0, len(H[0])-1, len(H[0]))
#poly = np.polyfit(H_T, H[0], deg=20)
#p12 = np.polyval(poly, H_T)
p12 = savgol_filter(H[0], 5, 3)
p12 = np.where(np.abs(p12)>=statistics.mean(p12)*1.2, 0, p12)
H[0] = p12

A1 = W @ H

#Zero the components that are 10% or less of the carrier magnitude, then convert back to a time series via inverse STFT
#https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.istft.html
#Zxx = np.where(np.abs(Zxx) >= amp/10, Zxx, 0)
#_, xrec = signal.istft(Zxx, fs)

_, xrec = signal.istft(A1, fs=Fs1, window='hann', nperseg=128, noverlap=0.75*128, nfft=None, input_onesided=False, boundary=False, time_axis=- 1, freq_axis=- 2)
xrec_1 = np.absolute(xrec)


chest11 = xrec_1[0:6000]
t11 = t1[0:6000]
'''
plt.figure(1)
plt.plot(H[0])
plt.plot(p12)
plt.figure(2)
plt.plot(H[1])
plt.plot(p11)
plt.figure(3)
plt.plot(t11, chest11)
plt.figure(4)
plt.plot(t11, chest1[-3400:])
#plt.show()
'''
times, chest1_array = sliding_window(chest1, sf=20, window=60, step=15)
times11, chest11_array = sliding_window(chest11, sf=20, window=60, step=15)
print(times)
print(chest1_array)
print(len(times))

BR = []
BR_T = []
HR = []
HR_T = []

Mean_RR1 = []
STD_RR1 = []
Mean_HR1 = []
STD_HR1 = []
Min_HR1 = []
Max_HR1 = []
RMSSD1 = []
NNxx1 = []
pNNxx1 = []

Power_VLF1 = []
Power_LF1 = []
Power_HF1 = []   
Power_Total1 = []
LF_by_HF1 = []
Peak_VLF1 = []
Peak_LF1 = []
Peak_HF1 = []
Fraction_LF1 = []
Fraction_HF1 = []

Mean_RR11 = []
STD_RR11 = []
Mean_HR11 = []
STD_HR11 = []
Min_HR11 = []
Max_HR11 = []
RMSSD11 = []
NNxx11 = []
pNNxx11 = []

Power_VLF11 = []
Power_LF11 = []
Power_HF11 = []   
Power_Total11 = []
LF_by_HF11 = []
Peak_VLF11 = []
Peak_LF11 = []
Peak_HF11 = []
Fraction_LF11 = []
Fraction_HF11 = []

#https://dsp.stackexchange.com/questions/42358/multilevel-partial-wavelet-reconstruction-with-pywavelets
import pywt
import pdb
import numpy as np

def wrcoef(X, coef_type, coeffs, wavename, level):
    N = np.array(X).size
    a, ds = coeffs[0], list(reversed(coeffs[1:]))

    if coef_type =='a':
        return pywt.upcoef('a', a, wavename, level=level)[:N]
    elif coef_type == 'd':
        return pywt.upcoef('d', ds[level-1], wavename, level=level)[:N]
    else:
        raise ValueError("Invalid coefficient type: {}".format(coef_type))


csvfile = open('Radar_Breath_Output_1.csv', 'w', newline='')
OutputWriter = csv.writer(csvfile, delimiter=',',
                       quotechar='', quoting=csv.QUOTE_NONE, escapechar='\\')                                    
OutputWriter.writerow(["Time_BR" ,"BR" ,"Mean_RR_B" ,"STD_RR_B" ,"Mean_HR_B" ,"STD_HR_B" ,"Min_HR_B" ,"Max_HR_B" ,"RMSSD_B" ,"NNxx_B" ,"pNNxx_B" ,"Power_VLF_B" ,"Power_LF_B" ,"Power_HF_B" ,"Power_Total_B", "LF_by_HF_B" ,"Peak_VLF_B", "Peak_LF_B" ,"Peak_HF_B" ,"Fraction_LF_B" ,"Fraction_HF_B"])

for i in range(((len(times))-1)):
    print(i)
    wv = 'db1'
    level = 6
    coeffs = pywt.wavedec(chest1_array[i], wv, level=level)
    A6 = wrcoef(chest1, 'a', coeffs, wv, level)
    D6 = wrcoef(chest1, 'd', coeffs, wv, level)
    #D9 = wrcoef(chest1, 'd', coeffs, 'db10', 9)
    #D8 = wrcoef(chest1, 'd', coeffs, 'db10', 8)
    #D7 = wrcoef(chest1, 'd', coeffs, 'db10', 7)
    #D6 = wrcoef(chest1, 'd', coeffs, 'db10', 6)
    D5 = wrcoef(chest1, 'd', coeffs, wv, 5)
    D4 = wrcoef(chest1, 'd', coeffs, wv, 4)
    D3 = wrcoef(chest1, 'd', coeffs, wv, 3)
    D2 = wrcoef(chest1, 'd', coeffs, wv, 2)
    D1 = wrcoef(chest1, 'd', coeffs, wv, 1)

    respiration = A6+D6+D5
    respiration = savgol_filter(respiration, 51, 3)
    #MaxBpm_Respi = 30;
    MaxBpm_Respi = 25;
    MaxHz_Respi = MaxBpm_Respi/60;
    MinT_Respi = 1/MaxHz_Respi;
    Min_Samp_Respi = int(Fs1*MinT_Respi);
    peaks, _ = find_peaks(respiration, distance=Min_Samp_Respi)
    Breath_Rate = len(peaks)/1
    print('Breath_Rate = ',Breath_Rate)
    BR.append(Breath_Rate)
    BR_T.append((times[i]+60))

    rr1 =60*np.diff(peaks)
    #print(rr)

    hr1 = 60000/rr1
    #print(hr1)
    #print(min(hr1),max(hr1))

    Mean_RR_B = np.mean(rr1)
    STD_RR_B = (np.std(rr1))
    Mean_HR_B = 60000/np.mean(rr1)
    STD_HR_B = np.std(hr1)
    Min_HR_B = np.min(hr1)
    Max_HR_B = np.max(hr1)
    RMSSD_B = (np.sqrt(np.mean(np.square(np.diff(rr1)))))
    NNxx_B = np.sum(np.abs(np.diff(rr1)) > 50)*1
    pNNxx_B = (100 * np.sum((np.abs(np.diff(rr1)) > 50)*1) / len(rr1))
    
    Mean_RR11.append(Mean_RR_B)
    STD_RR11.append(STD_RR_B)
    Mean_HR11.append(Mean_HR_B)
    STD_HR11.append(STD_HR_B)
    Min_HR11.append(Min_HR_B)
    Max_HR11.append(Max_HR_B)
    RMSSD11.append(RMSSD_B)
    NNxx11.append(NNxx_B)
    pNNxx11.append(pNNxx_B)

    # create interpolation function based on the rr-samples. 
    x_b = np.cumsum(rr1) / 1000.0
    f_b = interp1d(x_b, rr1, kind='cubic', fill_value="extrapolate")

    # # sample rate for interpolation
    ffs_b = 4.0
    Steps_b = 1 / ffs_b

    # now we can sample from interpolation function
    xx_b = np.arange(1, np.max(x_b), Steps_b)
    rr_interpolated_b = f_b(xx_b)

    # Estimate the spectral density using Welch's method
    fxx_b, pxx_b = signal.welch(x=rr_interpolated_b, fs=ffs_b)

    # '''
    # Segement found frequencies in the bands
    #  - Very Low Frequency (VLF): 0-0.04Hz
    #  - Low Frequency (LF): 0.04-0.15Hz
    #  - High Frequency (HF): 0.15-0.4Hz
    # '''
    cond_vlf_b = (fxx_b >= 0) & (fxx_b < 0.04)
    cond_lf_b = (fxx_b >= 0.04) & (fxx_b < 0.15)
    cond_hf_b = (fxx_b >= 0.15) & (fxx_b < 0.4)
    
    # calculate power in each band by integrating the spectral density 
    #vlf_b = trapz(pxx_b[cond_vlf_b], fxx_b[cond_vlf_b])
    #lf_b = trapz(pxx_b[cond_lf_b], fxx_b[cond_lf_b])
    #hf_b = trapz(pxx_b[cond_hf_b], fxx_b[cond_hf_b])
    vlf_b = 1
    lf_b = 1
    hf_b = 1
    # sum these up to get total power
    total_power_b = vlf_b + lf_b + hf_b

    # find which frequency has the most power in each band
    peak_vlf_b = fxx_b[cond_vlf_b][np.argmax(pxx_b[cond_vlf_b])]
    peak_lf_b = fxx_b[cond_lf_b][np.argmax(pxx_b[cond_lf_b])]
    peak_hf_b = fxx_b[cond_hf_b][np.argmax(pxx_b[cond_hf_b])]

    # fraction of lf and hf
    lf_nu_b = 100 * lf_b / (lf_b + hf_b)
    hf_nu_b = 100 * hf_b / (lf_b + hf_b)
    
    Power_VLF_B = vlf_b
    Power_LF_B = lf_b
    Power_HF_B = hf_b   
    Power_Total_B = total_power_b

    LF_by_HF_B = (lf_b/hf_b)
    Peak_VLF_B = peak_vlf_b
    Peak_LF_B = peak_lf_b
    Peak_HF_B = peak_hf_b

    Fraction_LF_B = lf_nu_b
    Fraction_HF_B = hf_nu_b

    Power_VLF11.append(Power_VLF_B)
    Power_LF11.append(Power_LF_B)
    Power_HF11.append(Power_HF_B)   
    Power_Total11.append(Power_Total_B)

    LF_by_HF11.append(LF_by_HF_B)
    Peak_VLF11.append(Peak_VLF_B)
    Peak_LF11.append(Peak_LF_B)
    Peak_HF11.append(Peak_HF_B)

    Fraction_LF11.append(Fraction_LF_B)
    Fraction_HF11.append(Fraction_HF_B)
    OutputWriter.writerow([(times[i]+60), Breath_Rate, Mean_RR_B, STD_RR_B, Mean_HR_B, STD_HR_B, Min_HR_B, Max_HR_B, RMSSD_B, NNxx_B, pNNxx_B, Power_VLF_B, Power_LF_B, Power_HF_B, Power_Total_B, LF_by_HF_B, Peak_VLF_B, Peak_LF_B, Peak_HF_B, Fraction_LF_B, Fraction_HF_B])

csvfile = open('Radar_Heart_Output_1.csv', 'w', newline='')
OutputWriter = csv.writer(csvfile, delimiter=',',
                       quotechar='', quoting=csv.QUOTE_NONE, escapechar='\\')                                    
OutputWriter.writerow(["Time_HR" ,"HR" ,"Mean_RR" ,"STD_RR" ,"Mean_HR" ,"STD_HR" ,"Min_HR" ,"Max_HR" ,"RMSSD" ,"NNxx" ,"pNNxx" ,"Power_VLF" ,"Power_LF" ,"Power_HF" ,"Power_Total", "LF_by_HF" ,"Peak_VLF", "Peak_LF" ,"Peak_HF" ,"Fraction_LF" ,"Fraction_HF"])

for i in range(((len(times11))-1)):
    print(i)
    wv = 'db1'
    level = 6
    coeffs11 = pywt.wavedec(chest11_array[i], wv, level=level)
    A6_11 = wrcoef(chest11, 'a', coeffs11, wv, level)
    D6_11 = wrcoef(chest11, 'd', coeffs11, wv, level)
    #D9 = wrcoef(chest1, 'd', coeffs, 'db10', 9)
    #D8 = wrcoef(chest1, 'd', coeffs, 'db10', 8)
    #D7 = wrcoef(chest1, 'd', coeffs, 'db10', 7)
    #D6 = wrcoef(chest1, 'd', coeffs, 'db10', 6)
    D5_11 = wrcoef(chest11, 'd', coeffs11, wv, 5)
    D4_11 = wrcoef(chest11, 'd', coeffs11, wv, 4)
    D3_11 = wrcoef(chest11, 'd', coeffs11, wv, 3)
    D2_11 = wrcoef(chest11, 'd', coeffs11, wv, 2)
    D1_11 = wrcoef(chest11, 'd', coeffs11, wv, 1)
    

    #heart = D5+D4+D3+D2+D1
    heart11 = D4+D3+D2+D1
    #heart = D5[:1200]+D4+D3+D2+D1
    heart = D3_11+D2_11+D1_11
    #heart = savgol_filter(heart, 5, 3)
    MaxBpm_H = 130;
    MaxHz_H = MaxBpm_H/60;
    MinT_H = 1/MaxHz_H;
    Min_Samp_H = int(Fs1*MinT_H);
    peaks1, _ = find_peaks(heart, height=None, threshold=0.0001, distance=Min_Samp_H)
    #peaks1, _ = find_peaks(heart, distance=Min_Samp_H)
    H_Rate = len(peaks1)/1
    print('Heart_Rate = ',H_Rate)
    HR.append(H_Rate)
    HR_T.append((times[i]+60))

    rr =60*np.diff(peaks1)
    #print(rr)

    hr = 60000/rr
    #print(hr)
    #print(min(hr),max(hr))

    Mean_RR = np.mean(rr)
    STD_RR = (np.std(rr))/10
    Mean_HR = 60000/np.mean(rr)
    STD_HR = np.std(hr)
    Min_HR = np.min(hr)
    Max_HR = np.max(hr)
    RMSSD = (np.sqrt(np.mean(np.square(np.diff(rr)))))/10
    NNxx = np.sum(np.abs(np.diff(rr)) > 50)*1
    pNNxx = (100 * np.sum((np.abs(np.diff(rr)) > 50)*1) / len(rr))/10
    Mean_RR1.append(Mean_RR)
    STD_RR1.append(STD_RR)
    Mean_HR1.append(Mean_HR)
    STD_HR1.append(STD_HR)
    Min_HR1.append(Min_HR)
    Max_HR1.append(Max_HR)
    RMSSD1.append(RMSSD)
    NNxx1.append(NNxx)
    pNNxx1.append(pNNxx)

    # create interpolation function based on the rr-samples. 
    x = np.cumsum(rr) / 1000.0
    f = interp1d(x, rr, kind='cubic', fill_value="extrapolate")

    # # sample rate for interpolation
    ffs = 4.0
    Steps = 1 / ffs

    # now we can sample from interpolation function
    xx = np.arange(1, np.max(x), Steps)
    rr_interpolated = f(xx)

    # Estimate the spectral density using Welch's method
    fxx, pxx = signal.welch(x=rr_interpolated, fs=ffs)

    # '''
    # Segement found frequencies in the bands
    #  - Very Low Frequency (VLF): 0-0.04Hz
    #  - Low Frequency (LF): 0.04-0.15Hz
    #  - High Frequency (HF): 0.15-0.4Hz
    # '''
    cond_vlf = (fxx >= 0) & (fxx < 0.04)
    cond_lf = (fxx >= 0.04) & (fxx < 0.15)
    cond_hf = (fxx >= 0.15) & (fxx < 0.4)
    
    # calculate power in each band by integrating the spectral density 
    #vlf = trapz(pxx[cond_vlf], fxx[cond_vlf])
    #lf = trapz(pxx[cond_lf], fxx[cond_lf])
    #hf = trapz(pxx[cond_hf], fxx[cond_hf])
    vlf = 1
    lf = 1
    hf = 1
    
    # sum these up to get total power
    total_power = vlf + lf + hf

    # find which frequency has the most power in each band
    peak_vlf = fxx[cond_vlf][np.argmax(pxx[cond_vlf])]
    peak_lf = fxx[cond_lf][np.argmax(pxx[cond_lf])]
    peak_hf = fxx[cond_hf][np.argmax(pxx[cond_hf])]

    # fraction of lf and hf
    lf_nu = 100 * lf / (lf + hf)
    hf_nu = 100 * hf / (lf + hf)
    
    Power_VLF = vlf
    Power_LF = lf
    Power_HF = hf   
    Power_Total = total_power

    LF_by_HF = (lf/hf)
    Peak_VLF = peak_vlf
    Peak_LF = peak_lf
    Peak_HF = peak_hf

    Fraction_LF = lf_nu
    Fraction_HF = hf_nu

    Power_VLF1.append(Power_VLF)
    Power_LF1.append(Power_LF)
    Power_HF1.append(Power_HF)   
    Power_Total1.append(Power_Total)

    LF_by_HF1.append(LF_by_HF)
    Peak_VLF1.append(Peak_VLF)
    Peak_LF1.append(Peak_LF)
    Peak_HF1.append(Peak_HF)

    Fraction_LF1.append(Fraction_LF)
    Fraction_HF1.append(Fraction_HF)
    OutputWriter.writerow([(times[i]+60), H_Rate, Mean_RR, STD_RR, Mean_HR, STD_HR, Min_HR, Max_HR, RMSSD, NNxx, pNNxx, Power_VLF, Power_LF, Power_HF, Power_Total, LF_by_HF, Peak_VLF, Peak_LF, Peak_HF, Fraction_LF, Fraction_HF])

    
csvfile.close()
'''
#oxi = read_csv('Anwesha_Oxi_DQ1.csv')
#oxi = read_csv('Anwesha_Oxi_DQ2.csv')
#oxi = read_csv('Manpreet_Oxi_DQ1.csv')
#oxi = read_csv('Manpreet_Oxi_DQ2.csv')
#oxi_1=oxi.PULSE.to_numpy()[55:170:5]

##plt.figure(5)
# plotting the points
#plt.plot(t1, chest1)
#plt.plot(t1, respiration)
#plt.plot(t1[peaks],respiration[peaks],'*')
##plt.plot(heart11)
#plt.figure(6)
##plt.plot(heart)
#plt.plot(t1[peaks1],heart[peaks1],'*')
plt.figure(6)
plt.subplot(1, 2, 1)
plt.plot(BR_T,BR)
# naming the x axis
plt.xlabel('x - axis Time in Sec')
# naming the y axis
plt.ylabel('y - axis BR (Breaths)') 
# giving a title to my graph
plt.title('Breath_Rate')
plt.ylim([0, 40])
plt.grid()
plt.subplot(1, 2, 2)
plt.plot(HR_T,HR)
plt.plot(HR_T[:22],oxi_1[:22])
# naming the x axis
plt.xlabel('x - axis Time in Sec')
# naming the y axis
plt.ylabel('y - axis HR (Heart_Rate)') 
# giving a title to my graph
plt.title('Heart_Rate') 
# function to show the plot
plt.ylim([0, 150])
plt.grid()


plt.figure(7)
plt.plot(HR_T,Mean_RR1)
plt.title('Mean_RR')
plt.figure(8)
plt.plot(HR_T,STD_RR1)
plt.title('STD_RR')
plt.figure(9)
plt.plot(HR_T,Mean_HR1)
plt.title('Mean_HR')
plt.figure(10)
plt.plot(HR_T,STD_HR1)
plt.title('STD_HR')
plt.figure(11)
plt.plot(HR_T,Min_HR1)
plt.title('Min_HR')
plt.figure(12)
plt.plot(HR_T,Max_HR1)
plt.title('Max_HR')
plt.figure(13)
plt.plot(HR_T,RMSSD1)
plt.title('RMSSD')
plt.figure(14)
plt.plot(HR_T,NNxx1)
plt.title('NNxx')
plt.figure(15)
plt.plot(HR_T,pNNxx1)
plt.title('pNNxx')



plt.figure(16)
plt.plot(HR_T,Power_VLF1)
plt.title('Power_VLF')
plt.figure(17)
plt.plot(HR_T,Power_LF1)
plt.title('Power_LF')
plt.figure(18)
plt.plot(HR_T,Power_HF1)
plt.title('Power_HF')
plt.figure(19)
plt.plot(HR_T,Power_Total1)
plt.title('Power_Total')
plt.figure(20)
plt.plot(HR_T,LF_by_HF1)
plt.title('LF_by_HF')
plt.figure(21)
plt.plot(HR_T,Peak_VLF1)
plt.title('Peak_VLF')
plt.figure(22)
plt.plot(HR_T,Peak_LF1)
plt.title('Peak_LF')
plt.figure(23)
plt.plot(HR_T,Peak_HF1)
plt.title('Peak_HF')
plt.figure(24)
plt.plot(HR_T,Fraction_LF1)
plt.title('Fraction_LF')
plt.figure(25)
plt.plot(HR_T,Fraction_HF1)
plt.title('Fraction_HF')


plt.figure(26)
plt.plot(BR_T,Mean_RR11)
plt.title('Mean_RR_B')
plt.figure(27)
plt.plot(BR_T,STD_RR11)
plt.title('STD_RR_B')
plt.figure(28)
plt.plot(BR_T,Mean_HR11)
plt.title('Mean_HR_B')
plt.figure(29)
plt.plot(BR_T,STD_HR11)
plt.title('STD_HR_B')
plt.figure(30)
plt.plot(BR_T,Min_HR11)
plt.title('Min_HR_B')
plt.figure(31)
plt.plot(BR_T,Max_HR11)
plt.title('Max_HR_B')
plt.figure(32)
plt.plot(BR_T,RMSSD11)
plt.title('RMSSD_B')
plt.figure(33)
plt.plot(BR_T,NNxx11)
plt.title('NNxx_B')
plt.figure(34)
plt.plot(BR_T,pNNxx11)
plt.title('pNNxx_B')

plt.figure(35)
plt.plot(BR_T,Power_VLF11)
plt.title('Power_VLF_B')
plt.figure(36)
plt.plot(BR_T,Power_LF11)
plt.title('Power_LF_B')
plt.figure(37)
plt.plot(BR_T,Power_HF11)
plt.title('Power_HF_B')
plt.figure(38)
plt.plot(BR_T,Power_Total11)
plt.title('Power_Total_B')
plt.figure(39)
plt.plot(BR_T,LF_by_HF11)
plt.title('LF_by_HF_B')
plt.figure(40)
plt.plot(BR_T,Peak_VLF11)
plt.title('Peak_VLF_B')
plt.figure(41)
plt.plot(BR_T,Peak_LF11)
plt.title('Peak_LF_B')
plt.figure(42)
plt.plot(BR_T,Peak_HF11)
plt.title('Peak_HF_B')
plt.figure(43)
plt.plot(BR_T,Fraction_LF11)
plt.title('Fraction_LF_B')
plt.figure(44)
plt.plot(BR_T,Fraction_HF11)
plt.title('Fraction_HF_B')

plt.show()
#https://pywavelets.readthedocs.io/en/latest/regression/multilevel.html
#db10 = pywt.Wavelet('db10')
#cA10, cD10, cD9, cD8, cD7, cD6, cD5, cD4, cD3, cD2, cD1 = pywt.wavedec(chest1, db10, level=10)
#coeffs = pywt.wavedec(chest1, db10)
#print(pywt.waverec(coeffs, db10))

'''   

