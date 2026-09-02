import numpy as np
import cv2
import matplotlib.pyplot as plt
from pandas import read_csv

x = read_csv('Radar_Heart_Output_1.csv')
hr=x.HR #.to_numpy()[0:6000]
hrf=np.max(hr[0:3])
hrl=np.min(hr[-4:-1])
hra=np.nanmean(hr)
score=(hrf-hrl)*100/hra

img = np.zeros((1024,1024))



if score>0:
    score=int(np.clip(score,2,9))
    text="Score: "+str(score)
    a1=350
    
else:
    text="Not Relaxed"
    a1=250

img = cv2.putText(
  img = img,
  text = text,
  org = (a1, 512),
  fontFace = cv2.FONT_HERSHEY_DUPLEX,
  fontScale = 3.0,
  color = (125, 246, 55),
  thickness = 3
)

cv2.imwrite('score.png', img)

#plt.imshow(img)
#plt.show()
