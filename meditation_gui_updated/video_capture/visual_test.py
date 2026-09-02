import cv2
import time
import mediapipe as mp
import numpy as np
import math

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

def similarity(results_ref, results):

	landmarks_ref = [(lm.x, lm.y, lm.z) for lm in results_ref.pose_landmarks.landmark]
	landmarks = [(lm.x, lm.y, lm.z) for lm in results.pose_landmarks.landmark]
	# print(landmarks_ref)
	# print(landmarks) 

	x = np.zeros([2,8]) 

	x[0,0],x[1,0],_ = landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW.value]   
	x[0,1],x[1,1],_ = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
	x[0,2],x[1,2],_ = landmarks[mp_pose.PoseLandmark.RIGHT_HIP.value]
	x[0,3],x[1,3],_ = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST.value]
	x[0,4],x[1,4],_ = landmarks[mp_pose.PoseLandmark.LEFT_ELBOW.value]   
	x[0,5],x[1,5],_ = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
	x[0,6],x[1,6],_ = landmarks[mp_pose.PoseLandmark.LEFT_HIP.value]
	x[0,7],x[1,7],_ = landmarks[mp_pose.PoseLandmark.LEFT_WRIST.value]

	x_ref = np.zeros([2,8]) 

	x_ref[0,0],x_ref[1,0],_ = landmarks_ref[mp_pose.PoseLandmark.RIGHT_ELBOW.value]   
	x_ref[0,1],x_ref[1,1],_ = landmarks_ref[mp_pose.PoseLandmark.RIGHT_SHOULDER.value]
	x_ref[0,2],x_ref[1,2],_ = landmarks_ref[mp_pose.PoseLandmark.RIGHT_HIP.value]
	x_ref[0,3],x_ref[1,3],_ = landmarks_ref[mp_pose.PoseLandmark.RIGHT_WRIST.value]
	x_ref[0,4],x_ref[1,4],_ = landmarks_ref[mp_pose.PoseLandmark.LEFT_ELBOW.value]   
	x_ref[0,5],x_ref[1,5],_ = landmarks_ref[mp_pose.PoseLandmark.LEFT_SHOULDER.value]
	x_ref[0,6],x_ref[1,6],_ = landmarks_ref[mp_pose.PoseLandmark.LEFT_HIP.value]
	x_ref[0,7],x_ref[1,7],_ = landmarks_ref[mp_pose.PoseLandmark.LEFT_WRIST.value]


	x_cent = np.zeros([2,1])
	x_cent_ref = np.zeros([2,1])

	x_cent[0,0] = (x[0,1] + x[0,5])/2
	x_cent_ref[0,0] = (x_ref[0,1] + x_ref[0,5])/2

	x_cent[1,0] = (x[1,1] + x[1,5])/2
	x_cent_ref[1,0] = (x_ref[1,1] + x_ref[1,5])/2


	X_ref = x_ref - x_cent_ref*np.ones([1,8])
	X = (x - x_cent*np.ones([1,8]))

	X_flattened = X.flatten()
	Y_flattened = X_ref.flatten()

	score =  X_flattened@Y_flattened.T/math.sqrt((X_flattened@X_flattened.T)*(Y_flattened@Y_flattened.T))

	return score*100

if __name__ == "__main__":
# Define the camera index (0 is usually the default camera)
	camera_index = 6

	# Open the video capture using the camera index
	cap = cv2.VideoCapture(camera_index)

	# Check if the camera opened successfully
	if not cap.isOpened():
		print("Error: Unable to access the camera")
		exit()

	# Get the default frame width and height of the camera
	frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
	frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

	# Define the codec and create a VideoWriter object to save the video
	output_file = 'output1_video.avi'
	output_video_path_concat = "output_concat.avi"
	fourcc = cv2.VideoWriter_fourcc(*'XVID')
	out = cv2.VideoWriter(output_file, fourcc, 20.0, (frame_width, frame_height))
	out_concat = cv2.VideoWriter(output_video_path_concat, fourcc, 20.0, (frame_width, frame_height))

	# Define the recording time in seconds (5 minutes = 300 seconds)
	recording_time = 5 * 60
	start_time = time.time()
	
	count = 0
	count_concat = 0
	avg_score = 0
	N = 0

	prev_score = 0
	score = 0
	thr = 1

	print("Recording started...")
	
	with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5,model_complexity=2) as pose:
    
		image_path1 = 'Posture1.png'
		image1 = cv2.imread(image_path1)
		image1_height, image1_width, _ = image1.shape
		image1_rgb = cv2.cvtColor(image1, cv2.COLOR_BGR2RGB)
		results1 = pose.process(image1_rgb)

		landmarks1 = [(int(lm.x * image1_width), int(lm.y * image1_height), lm.z * image1_width) for lm in results1.pose_landmarks.landmark]


		image_path2 = 'Posture2.png'
		image2 = cv2.imread(image_path2)
		image2_height, image2_width, _ = image2.shape
		image2_rgb = cv2.cvtColor(image2, cv2.COLOR_BGR2RGB)
		results2 = pose.process(image2_rgb)


		landmarks2 = [(int(lm.x * image2_width), int(lm.y * image2_height), lm.z * image2_width) for lm in results2.pose_landmarks.landmark]


		# Capture frames and write them to the output file without displaying them

		if not cap.isOpened():
			print("Error: Could not open video file.")

		else:


			while cap.isOpened():
		
				ret, image = cap.read()
				image = cv2.flip(image, 1)
				image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

				image_height, image_width, _ = image.shape
				count = count +1


				if ret:

					
					# Write the frame to the output file
					if(count>400 and count<2579):
						results = pose.process(image_rgb)

						# Write the frame to the output video
						prev_score = score
						score = similarity(results1,results)

						N = N + 1
						avg_score = (avg_score*(N-1) + score)/N
						# score_text = f"Similarity Score: {score:.2f}%"

						# # Display the similarity score on the image
						# cv2.putText(frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
						#     # Draw landmarks and connections

						# score = random.uniform(80, 100)
						print(count,": ",score,", cumulative score:",avg_score)
						score_text = f"Similarity Score: {score:.2f}%"

						# Display the similarity score on the image
						cv2.putText(image, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

						mp.solutions.drawing_utils.draw_landmarks(image, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
													mp.solutions.drawing_utils.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
													mp.solutions.drawing_utils.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))
			
						out.write(image)

						if(prev_score-score > thr):
							count_concat = 1

						if(count_concat != 0):
							out_concat.write(image)
							count_concat = (count_concat + 1)%200

						
					elif(count>2580 and count<4279):
						results = pose.process(image_rgb)
						
						prev_score = score
						# Write the frame to the output video
						score = similarity(results2,results)

						N = N + 1
						avg_score = (avg_score*(N-1) + score)/N

						print(count,": ",score,", cumulative score:",avg_score)
						score_text = f"Similarity Score: {score:.2f}%"

						# Display the similarity score on the image
						cv2.putText(image, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

						mp.solutions.drawing_utils.draw_landmarks(image, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
													mp.solutions.drawing_utils.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
													mp.solutions.drawing_utils.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))
			
						out.write(image)

						if(prev_score-score > thr):
							count_concat = 1

						if(count_concat != 0):
							out_concat.write(image)
							count_concat = (count_concat + 1)%200

					elif(count>4280 and count<6359):
						results = pose.process(image_rgb)
						
						prev_score = score
						# Write the frame to the output video
						score = similarity(results1,results)
						# score_text = f"Similarity Score: {score:.2f}%"
						N = N + 1
						avg_score = (avg_score*(N-1) + score)/N
						# # Display the similarity score on the image
						# cv2.putText(frame, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)
						#     # Draw landmarks and connections

						# score = random.uniform(80, 100)
						print(count,": ",score,", cumulative score:",avg_score)
						score_text = f"Similarity Score: {score:.2f}%"

						# Display the similarity score on the image
						cv2.putText(image, score_text, (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2, cv2.LINE_AA)

						mp.solutions.drawing_utils.draw_landmarks(image, results.pose_landmarks, mp.solutions.pose.POSE_CONNECTIONS,
													mp.solutions.drawing_utils.DrawingSpec(color=(245,117,66), thickness=2, circle_radius=2),
													mp.solutions.drawing_utils.DrawingSpec(color=(245,66,230), thickness=2, circle_radius=2))
			
						out.write(image)

						if(prev_score-score > thr):
							count_concat = 1

						if(count_concat != 0):
							out_concat.write(image)
							count_concat = (count_concat + 1)%200
									
									
					# Break the loop if the recording time is up
					if (time.time() - start_time) > recording_time:
						break

	# Release the camera and writer resources
	cap.release()
	out.release()
	out_concat.release()

	print(f"Recording completed. Video saved as {output_file}")

