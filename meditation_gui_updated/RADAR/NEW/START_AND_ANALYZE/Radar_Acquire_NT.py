import numpy as np
import numpy.matlib 
import serial
from mmWave import vitalsign
import time
import struct
import sys
import os
import csv
import threading
from collections import deque
from threading import Thread
from signal import pause
import datetime
from scipy import signal
from serial import Serial
exit_event= threading.Event()
elapsed = 0
elapsed1 = 0
start_time = time.time()
total=300
global cd6,rp7

csvfile = open('cd6_write.csv', 'w+', newline='')
OutputWriter = csv.writer(csvfile, delimiter=',',
                       quotechar='', quoting=csv.QUOTE_NONE, escapechar='\\')                                    
OutputWriter.writerow(["time" ,"data"])

count = 0

rp7  = np.zeros(23)

try:
    #port = serial.Serial("/dev/ttyS0",baudrate = 921600)
    port = serial.Serial("/dev/ttyUSB0",baudrate = 921600, timeout = 0.5)
    vts = vitalsign.VitalSign(port)

    port.flushInput()
    print("working")
    while True:
        end_time = time.time()
        elapsed = end_time-start_time
        print(elapsed)
        (dck , vd, rangeBuf) = vts.tlvRead(False)
        vs = vts.getHeader()
        if dck:
            rp7 = [np.sqrt(rangeBuf[i*2]*rangeBuf[i*2] + rangeBuf[i*2+1]*rangeBuf[i*2+1]) for i in range(23)]
            end_time = time.time()
            elapsed1 = end_time-start_time
            OutputWriter.writerow([elapsed1, vd.unwrapPhasePeak_mm])
            if int(elapsed) >= total:
                csvfile.close()
                print("Program Stopped")
                port.close()
                exit_event.set()
                os._exit(1)
                break
except:
    pass
