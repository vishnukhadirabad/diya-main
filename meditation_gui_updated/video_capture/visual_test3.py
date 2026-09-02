import cv2
import numpy as np
import time
import mediapipe as mp
import math

# Initialize MediaPipe FaceMesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)
mp_draw = mp.solutions.drawing_utils

# Define video codec and create VideoWriter object
fourcc = cv2.VideoWriter_fourcc(*'XVID')  # Codec for MP4
out = cv2.VideoWriter('hand_detection_output.avi', fourcc, 20.0, (640, 480))

# Pupil landmark indices
LEFT_PUPIL_INDEX = 473
RIGHT_PUPIL_INDEX = 468

# Define Eye Boundary Indices
LEFT_EYE_BOUNDARY = [386,263,362,374,257]#, 385, 384, 382, 381] #, 387, 388, 466, 263, 249]//up, outer eye, inner eye, down
RIGHT_EYE_BOUNDARY = [159,33,133,145,27]#, 158, 157, 173, 144] #, 160, 161, 246, 33, 7]


# Initialize Webcam
cap = cv2.VideoCapture(8)
# cap = cv2.VideoCapture(6)

fr = 0.6
svr = 0
cvr = 0
shr = 0
cohr = 0

svl = 0
cvl = 0
shl = 0
chl = 0

total = 0
look = 0

recording_time = 5 * 60
start_time = 2*60 + 10 + time.time()

while cap.isOpened():
    success, frame = cap.read()
    if not success:
        print("Ignoring empty frame.")
        continue

    # Flip and convert the frame
    frame = cv2.flip(frame, 1)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Process the frame
    results = face_mesh.process(rgb_frame)
    result_hands = hands.process(rgb_frame)

    if results.multi_face_landmarks:
        for face_landmarks in results.multi_face_landmarks:
            # Get frame dimensions
            frame_height, frame_width, _ = frame.shape

            # Extract left and right pupil positions
            left_pupil = face_landmarks.landmark[LEFT_PUPIL_INDEX]
            right_pupil = face_landmarks.landmark[RIGHT_PUPIL_INDEX]

            # Convert normalized coordinates to pixel positions
            left_pupil_pos = (int(left_pupil.x * frame_width), int(left_pupil.y * frame_height))
            right_pupil_pos = (int(right_pupil.x * frame_width), int(right_pupil.y * frame_height))

            # Draw pupils on the frame
            cv2.circle(frame, left_pupil_pos, 1, (0, 255, 0), -1)  # Green for left pupil
            cv2.circle(frame, right_pupil_pos, 1, (0,255, 0), -1)  # Red for right pupil


            pos_left = np.zeros((5,2))
            pos_right = np.zeros((5,2))
            # Draw Left Eye(Red)
            i = 0
            for idx in LEFT_EYE_BOUNDARY:
                point = face_landmarks.landmark[idx]
                x, y = int(point.x * frame_width), int(point.y * frame_height)
                # cv2.circle(frame, (x, y), 1, (0, 0, 255), -1)
                pos_left[i,0],pos_left[i,1] = x,y
                i = i+1

            i = 0
            # Draw Right Eye (blue)
            for idx in RIGHT_EYE_BOUNDARY:
                point = face_landmarks.landmark[idx]
                x, y = int(point.x * frame_width), int(point.y * frame_height)
                # cv2.circle(frame, (x, y), 1, (255, 0, 0), -1)
                pos_right[i,0],pos_right[i,1] = x,y
                i = i+1

        if result_hands.multi_hand_landmarks:
            for hand_landmarks in result_hands.multi_hand_landmarks:
                # mp_draw.draw_landmarks(frame, hand_landmarks, mp_hands.HAND_CONNECTIONS)

                X_hand = []
                Y_hand = []
                for idx, landmark in enumerate(hand_landmarks.landmark):

                    X_hand.append( int(landmark.x * frame_width))  # Convert normalized x to pixel coordinates
                    Y_hand.append(int(landmark.y * frame_height))  # Convert normalized y to pixel coordinates
                   
            # print(X_hand)
            x_max = max(X_hand)
            x_min = min(X_hand)
            y_max = max(Y_hand)
            y_min = min(Y_hand)

            x_centre = (X_hand[5] + X_hand[17])/2
            y_centre = (2*Y_hand[0] + Y_hand[9] + Y_hand[13])/4
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), (0, 255, 255), 2)
               

           
            # print("Coordinates:")
            # print(left_pupil_pos)
            # print(right_pupil_pos)
            # for i in range(5):
            #     print(pos_left[i,:])
            # for i in range(5):
            #     print(pos_right[i,:])


            hr = max(0,min(1,(pos_right[1,0]-2- right_pupil_pos[0])/(pos_right[1,0]-2- pos_right[2,0])))
            hl = max(0,min(1,(pos_left[2,0]- left_pupil_pos[0])/(pos_left[2,0]- pos_left[1,0])))

            vr = max(0,min(1,((pos_right[4,1]+8 - right_pupil_pos[1]))/(pos_right[4,1]+8 - pos_right[3,1])))
            vl = max(0,min(1,((pos_left[4,1]+8 - left_pupil_pos[1]))/(pos_left[4,1]+8 - pos_left[3,1])))

            # vr = max(0,min(1,(pos_right[1,1]+pos_right[2,1] - (pos_right[3,1]) - right_pupil_pos[1])/(pos_right[1,1]+pos_right[2,1] - 2*(pos_right[3,1]) )))
            # vl = max(0,min(1,(pos_left[1,1]+pos_left[2,1] - (pos_left[3,1]) - left_pupil_pos[1])/(pos_left[1,1]+pos_left[2,1] - 2*(pos_left[3,1]) )))

            theta_v1 = 2*math.pi*75/180
            theta_v2 = 2*math.pi*60/180
            theta_h1 = 2*math.pi*65/180
            theta_h2 = 2*math.pi*66/180

            sin_vr = (1 - vr)*math.sin(theta_v1) - vr*math.sin(theta_v2)
            cos_vr = math.sqrt(1 - sin_vr*sin_vr)
            sin_hr = (1 - hr*cos_vr)*math.sin(theta_h2) - hr*cos_vr*math.sin(theta_h1)
            cos_hr = math.sqrt(1 - sin_hr*sin_hr)

            sin_vl = (1 - vl)*math.sin(theta_v1) - vr*math.sin(theta_v2)
            cos_vl = math.sqrt(1 - sin_vl*sin_vl)
            sin_hl = (1 - hl*cos_vl)*math.sin(theta_h1) - hl*cos_vl*math.sin(theta_h2)
            cos_hl = math.sqrt(1 - sin_hl*sin_hl)

            svr = sin_vr*(1-fr)+svr*fr
            cvr = cos_vr*(1-fr)+cvr*fr
            shr = sin_hr*(1-fr)+shr*fr
            cohr = cos_hr*(1-fr)+cohr*fr

            svl = sin_vl*(1-fr)+svl*fr
            cvl = cos_vl*(1-fr)+cvl*fr
            shl = sin_hl*(1-fr)+shl*fr
            chl = cos_hl*(1-fr)+chl*fr

            #condition looking
            # cv2.circle(frame, (x_min,y_min), 1, (255, 255, 0), 3)
            # cv2.circle(frame, (x_max,y_min), 1, (0, 255, 0), 3)

            rr1 = math.sqrt((right_pupil_pos[0]-x_min)**2 + (right_pupil_pos[1]-y_min)**2)
            rr2 = math.sqrt((right_pupil_pos[0]-x_max)**2 + (right_pupil_pos[1]-y_min)**2)
            rl1 = math.sqrt((left_pupil_pos[0]-x_min)**2 + (left_pupil_pos[1]-y_min)**2)
            rl2 = math.sqrt((left_pupil_pos[0]-x_max)**2 + (left_pupil_pos[1]-y_min)**2)

            cr = cvr*shr/math.sqrt((cvr*shr)**2 + svr**2)
            cl = cvl*shl/math.sqrt((cvl*shl)**2 + svl**2)

            sr = svr/math.sqrt((cvr*shr)**2 + svr**2)
            sl = svl/math.sqrt((cvl*shl)**2 + svl**2)

            right_looking = (x_min < right_pupil.x * frame_width-rr1*cr)&(x_max > right_pupil.x * frame_width-rr2*cr)#&(right_pupil.y * frame_height-rl2*sr - y_min<0)
            left_looking = (x_min< left_pupil.x * frame_width-rl1*cl)&(x_max> left_pupil.x * frame_width-rl2*cl)#&(left_pupil.y * frame_height-rl2*sl - y_min<0)

            looking = right_looking & left_looking

            print("right:",right_looking,", left:",left_looking,"looking:",looking)
           
            r = 1000
            left_gaze = (int(left_pupil.x * frame_width-r*cvl*shl), int(left_pupil.y * frame_height-r*svl))
            right_gaze = (int(right_pupil.x * frame_width-r*cvr*shr), int(left_pupil.y * frame_height-r*svr))

            # #check!
            left_look = (int(left_pupil.x * frame_width-rl1*cl), int(left_pupil.y * frame_height-rl2*sl))
            right_look = (int(right_pupil.x * frame_width-rr1*cr), int(left_pupil.y * frame_height-rr2*sr))

            #condition occlusion
            occ = (right_pupil_pos[0]<x_max) & (right_pupil_pos[0]>x_min)&(right_pupil_pos[1]<y_max)&(right_pupil_pos[1]>y_min)|(left_pupil_pos[0]<x_max) & (left_pupil_pos[0]>x_min)&(left_pupil_pos[1]<y_max)&(left_pupil_pos[1]>y_min)

            centre = (int(x_centre),int(y_centre))

            #eyes closed
            tc = 0.7
            # print("right",(pos_right[4,1] - pos_right[0,1])/(pos_right[4,1] - pos_right[3,1]))
            # print("left",(pos_left[4,1] - pos_left[0,1])/(pos_left[4,1] - pos_left[3,1]))
            isclosed = ((pos_right[4,1] - pos_right[0,1])/(pos_right[4,1] - pos_right[3,1])>=tc)&((pos_left[4,1] - pos_left[0,1])/(pos_left[4,1] - pos_left[3,1])>=tc)

   
            # # print("Left_gaze:",left_looking)
            # print("x_min:",x_min,", x_max:",x_max)
            # print("Right:",right_pupil.x * frame_width-rr1*cr,",",right_pupil.x * frame_width-rr2*sr)
            # print("Left:",right_pupil.x * frame_width-rl1*cl,",",right_pupil.x * frame_width-rl2*cl)
            # # print(right_pupil_pos)
           
            total = total + 1
            # looking = 1
            looking = looking|occ
            looking = looking|isclosed
            #cv2.line(frame,right_pupil_pos, right_look, (0, 255, 255), 2)
            #cv2.line(frame, left_pupil_pos, left_look, (0, 255, 255), 2)
            if(looking==0):
                cv2.line(frame,right_pupil_pos, right_gaze, (0, 0, 255), 2)
                cv2.line(frame, left_pupil_pos, left_gaze, (0, 0, 255), 2)
            else:
                look = look + 1
                cv2.line(frame,right_pupil_pos, centre, (0, 255, 0), 2)
                cv2.line(frame, left_pupil_pos, centre, (0, 255, 0), 2)


    # Display the result
    cv2.imshow('Pupils', frame)
    if (((time.time() - start_time) < recording_time)&(time.time()>start_time)):
    	out.write(frame)

    #if cv2.waitKey(1) & 0xFF == 27:  # Press 'Esc' to exit
    #print(time.time())
    if (time.time() - start_time) > recording_time:
        break
print("Score:",look*100/total,"%")
# Cleanup
cap.release()
cv2.destroyAllWindows()
