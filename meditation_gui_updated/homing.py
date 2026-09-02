import serial
com = serial.Serial('/dev/ttyACM0', baudrate=9600, timeout=1)
com.write(("7").encode('utf-8'))
print("OK")

