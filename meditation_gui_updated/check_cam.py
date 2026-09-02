from ultralytics import YOLO
model =YOLO("yolov8x-pose.pt")
##model =YOLO("yolov8x-pose.pt").to("cuda")
result=model(source=0,conf=0.5,show=True)
