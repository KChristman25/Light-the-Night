import cv2
import numpy as np
import serial
import time
import pygame
import sys

# Connect to Arduino (update your port as needed)
arduino = serial.Serial('/dev/tty.usbmodem70041DD330E42', 9600)  # Replace this!
time.sleep(2)  # Let Arduino reset

# Define alien hitboxes
aliens = [
    {"name": "Alien 1", "hitbox": (300, 100, 150, 150)},
    {"name": "Alien 2", "hitbox": (200, 300, 150, 150)},
    {"name": "Alien 3", "hitbox": (500, 500, 150, 150)},
]

cap = cv2.VideoCapture(0)

pygame.init()
screen = pygame.display.set_mode([1280,720])
alienimage = pygame.image.load("UFO1.jpg")
alienimage = pygame.transform.scale(alienimage,[150,150])
background = pygame.image.load("Background.jpg")
#background = pygame.transform.scale(background,[1280,720])
isrunning = True

while isrunning:
    ret, frame = cap.read()
    if not ret:
        break

    screen.fill([0,0,0])

    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)

    # Red laser detection range (adjust if using green/other laser)
    lower_red = np.array([0, 100, 100])
    upper_red = np.array([10, 255, 255])
    mask = cv2.inRange(hsv, lower_red, upper_red)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    hit = False

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 5:
            x, y, w, h = cv2.boundingRect(cnt)
            cx, cy = x + w // 2, y + h // 2
            cv2.circle(frame, (cx, cy), 10, (0, 255, 0), 2)

            # Check for alien hits
            for alien in aliens:
                ax, ay, aw, ah = alien["hitbox"]
                if ax <= cx <= ax + aw and ay <= cy <= ay + ah:
                    hit = True
                    print(f"{alien['name']} HIT!")
                    arduino.write(b'ALIEN_HIT\n')  # Communicate with Arduino

    # Draw alien hitboxes
    for alien in aliens:
        ax, ay, aw, ah = alien["hitbox"]
        cv2.rectangle(frame, (ax, ay), (ax + aw, ay + ah), (255, 0, 0), 2)
        cv2.putText(frame, alien["name"], (ax, ay - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

    if hit:
        cv2.putText(frame, "ALIEN HIT!", (50, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    #cv2.imshow("Laser Detection", frame)

    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame = np.rot90(frame)
    frame = pygame.surfarray.make_surface(frame)
    framesize = frame.get_size()
    background = pygame.transform.scale(background,framesize)
    frame.blit(background,[0,0])
    for alien in aliens:
    	ax,ay,aw,ah = alien["hitbox"]
    	x = framesize[0]-ax
    	frame.blit(alienimage,alienimage.get_rect(topright = [x,ay]))
    frame = pygame.transform.scale(frame,[1280,720])
    frame = pygame.transform.flip(frame,True,False)
    screen.blit(frame, (0,0))
    for event in pygame.event.get():
    	if event.type == pygame.QUIT:
    		isrunning = False
    pygame.display.update() 


    if cv2.waitKey(1) & 0xFF == ord("q"):
        sys.exit(0)

cap.release()
pygame.quit()
cv2.destroyAllWindows()
