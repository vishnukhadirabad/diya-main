import cv2
import os
import csv
import numpy as np
import pandas as pd
from datetime import datetime
from PIL import Image

# ========== Setup Folders ========== #
def ensure_dirs():
    os.makedirs("TrainingImage", exist_ok=True)
    os.makedirs("TrainData", exist_ok=True)
    os.makedirs("UnknownFaces", exist_ok=True)

# ========== Profile Management ========== #
def read_profiles():
    if not os.path.exists("Profile.csv"):
        with open("Profile.csv", "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['Name', 'Ids'])
            writer.writeheader()
    return pd.read_csv("Profile.csv")

def save_profile(name, new_id):
    with open("Profile.csv", "a", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Name', 'Ids'])
        writer.writerow({'Name': name, 'Ids': new_id})

def get_next_id(df):
    return int(df['Ids'].max()) + 1 if not df.empty else 1

# ========== Capture Images ========== #
def capture_images(name, Id):
    cam = cv2.VideoCapture(10)
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    sample_num = 0
    print("📸 Capturing images for new user. Look at the camera...")

    while True:
        ret, img = cam.read()
        if not ret:
            print("❌ Failed to access camera.")
            break

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = detector.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            sample_num += 1
            cv2.imwrite(f"TrainingImage/{name}.{Id}.{sample_num}.jpg", gray[y:y+h, x:x+w])
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)

        cv2.imshow('Registering...', img)
        if cv2.waitKey(100) & 0xFF == ord('q') or sample_num >= 30:
            break

    cam.release()
    cv2.destroyAllWindows()
    print("✅ Image capture complete.")

# ========== Train Model ========== #
def train_model():
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    faces, Ids = [], []

    for filename in os.listdir("TrainingImage"):
        if filename.endswith(".jpg"):
            path = os.path.join("TrainingImage", filename)
            img = Image.open(path).convert('L')
            np_img = np.array(img, 'uint8')
            Id = int(filename.split(".")[1])
            faces.append(np_img)
            Ids.append(Id)

    recognizer.train(faces, np.array(Ids))
    recognizer.save("TrainData/Trainner.yml")
    print("✅ Model trained and saved.")

# ========== Handle New Face ========== #
def handle_new_face(unknown_face):
    print("\n👤 Unknown face detected.")
    ans = input("Do you want to register this face? (y/n): ").strip().lower()
    if ans == 'y':
        name = input("Enter your name: ").strip()
        df = read_profiles()
        new_id = get_next_id(df)
        save_profile(name, new_id)
        capture_images(name, new_id)
        train_model()
        print("🎯 Registration complete! Please run again to log in.")
    else:
        print("🚫 Face not registered.")

# ========== Main Face Detection and Login ========== #
def detect_and_login():
    df = read_profiles()
    names_dict = {int(row['Ids']): row['Name'] for _, row in df.iterrows()}
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read("TrainData/Trainner.yml")

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cam = cv2.VideoCapture(10)
    font = cv2.FONT_HERSHEY_SIMPLEX

    unknown_counter = 0
    unknown_face = None

    print("🟢 Face login started. Press 'q' to quit.")

    while True:
        ret, frame = cam.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)

        for (x, y, w, h) in faces:
            face = gray[y:y+h, x:x+w]
            Id, confidence = recognizer.predict(face)

            if confidence < 70 and Id in names_dict:
                name = names_dict[Id]
                cv2.putText(frame, name, (x, y + h + 30), font, 1, (0, 255, 0), 2)
                print(f"\n✅ Detected as {name}")
                print("🎉 Login Successful")
                print(f"👋 Welcome {name}")
                cam.release()
                cv2.destroyAllWindows()
                return
            else:
                unknown_counter += 1
                unknown_face = face
                cv2.putText(frame, "Unknown", (x, y + h + 30), font, 1, (0, 0, 255), 2)
                if unknown_counter >= 5:
                    cam.release()
                    cv2.destroyAllWindows()
                    handle_new_face(unknown_face)
                    return

        cv2.imshow("Face Login", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cam.release()
    cv2.destroyAllWindows()

# ========== Entry Point ========== #
if __name__ == "__main__":
    ensure_dirs()
    detect_and_login()

