import numpy as np
import cv2
import matplotlib.pyplot as plt

img = np.zeros((1024,1024))

score=5

if score>0:
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

plt.imshow(img)
plt.show()
