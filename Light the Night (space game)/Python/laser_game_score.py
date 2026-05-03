import os
import cv2
import numpy as np
import serial
import time
import pygame
import sys
from datetime import datetime, timedelta

# Move window to second monitor (adjust if needed)
os.environ['SDL_VIDEO_WINDOW_POS'] = "1920,0"

# Connect to Arduino
arduino = serial.Serial('/dev/tty.usbmodem70041DD330E42', 9600)
time.sleep(2)

# Display and camera resolution
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720

# Initialize camera
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
time.sleep(1)  # Allow camera to adjust

# Check actual resolution
CAM_WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
CAM_HEIGHT = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"Requested: 1280x720 | Got: {CAM_WIDTH}x{CAM_HEIGHT}")
if CAM_WIDTH != 1280 or CAM_HEIGHT != 720:
    print("Warning: Resizing camera frames manually to 1280x720.")

# Alien setup
aliens = [
    {"name": "Alien 1", "pos": [100, 100], "size": [150, 150], "vel": [3, 2]},
    {"name": "Alien 2", "pos": [400, 300], "size": [150, 150], "vel": [4, -2]},
    {"name": "Alien 3", "pos": [800, 500], "size": [150, 150], "vel": [-3, 3]},
]

pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT),pygame.FULLSCREEN)
pygame.display.set_caption("UFO Laser Game")

# Fonts
font_large = pygame.font.SysFont(None, 96)
font_medium = pygame.font.SysFont(None, 60)
font_small = pygame.font.SysFont(None, 40)

# Load images
alienimage = pygame.image.load("UFO1.jpg")
alienimage = pygame.transform.scale(alienimage, [150, 150])
background = pygame.image.load("Background.jpg")

#alienimage = pygame.Surface([150,150])
#alienimage.fill("black")
#background = pygame.Surface([1280,720])

# Game state
isrunning = True
game_active = False
game_timer_end = datetime.now()
score = 0

while isrunning:
    ret, frame = cap.read()
    if not ret:
        break

    if CAM_WIDTH != 1280 or CAM_HEIGHT != 720:
        frame = cv2.resize(frame, (1280, 720))

    screen.fill([0, 0, 0])

    # Arduino motion detection
    if arduino.in_waiting:
        line = arduino.readline().decode().strip()
        if line == "MOTION":
            game_active = True
            game_timer_end = datetime.now() + timedelta(seconds=30)
            score = 0
            print("Game started or restarted.")

    if game_active and datetime.now() > game_timer_end:
        game_active = False
        print("Game ended. Waiting for motion...")

    # Move aliens
    for alien in aliens:
        ax, ay = alien["pos"]
        aw, ah = alien["size"]
        vx, vy = alien["vel"]

        ax += vx
        ay += vy

        if ax <= 0 or ax + aw >= 1280:
            vx *= -1
            ax = max(0, min(ax, 1280 - aw))

        if ay <= 0 or ay + ah >= 720:
            vy *= -1
            ay = max(0, min(ay, 720 - ah))

        alien["pos"] = [ax, ay]
        alien["vel"] = [vx, vy]

    # Detect laser
    blurred = cv2.GaussianBlur(frame, (5, 5), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    lower_red = np.array([300, 0, 75])
    upper_red = np.array([350, 60, 110])
    mask = cv2.inRange(hsv, lower_red, upper_red)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    debug_frame = frame.copy()
    

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 5:
            x, y, w, h = cv2.boundingRect(cnt)
            cx, cy = x + w // 2, y + h // 2
            cv2.circle(debug_frame, (cx, cy), 10, (0, 255, 0), 2)

            for alien in aliens:
                ax, ay = alien["pos"]
                aw, ah = alien["size"]
                if game_active and ax <= cx <= ax + aw and ay <= cy <= ay + ah:
                    print(f"{alien['name']} HIT!")
                    arduino.write(b'ALIEN_HIT\n')
                    score += 1

    # Draw debug
    for alien in aliens:
        ax, ay = alien["pos"]
        aw, ah = alien["size"]
        cv2.rectangle(debug_frame, (int(ax), int(ay)), (int(ax + aw), int(ay + ah)), (255, 0, 0), 2)
        cv2.putText(debug_frame, alien["name"], (int(ax), int(ay - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    cv2.imshow("Debug View", debug_frame)

    # Convert OpenCV to Pygame
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    frame = np.rot90(frame)
    frame = pygame.surfarray.make_surface(frame)
    frame.blit(pygame.transform.scale(background, frame.get_size()), (0, 0))
    frame = pygame.transform.scale(frame, (SCREEN_WIDTH, SCREEN_HEIGHT))
    frame = pygame.transform.flip(frame, True, False)
    screen.blit(frame, (0, 0))

    if game_active:
        scale_x = SCREEN_WIDTH / 1280
        scale_y = SCREEN_HEIGHT / 720

        for alien in aliens:
            ax, ay = alien["pos"]
            screen.blit(alienimage, (int(ax * scale_x), int(ay * scale_y)))

        remaining = int((game_timer_end - datetime.now()).total_seconds())
        timer_text = font_small.render(f"Time: {remaining}s", True, (255, 255, 255))
        score_text = font_small.render(f"Score: {score}", True, (255, 255, 255))
        screen.blit(timer_text, (20, 20))
        screen.blit(score_text, (20, 60))
    else:
        screen.fill((0, 0, 0))
        screen_rect = screen.get_rect()
        game_over_text = font_large.render("GAME OVER", True, (255, 0, 0))
        final_score_text = font_medium.render(f"Final Score: {score}", True, (255, 255, 255))
        exit_text = font_small.render("Please exit for next group", True, (255, 255, 0))
        screen.blit(game_over_text, game_over_text.get_rect(center=(screen_rect.centerx, screen_rect.centery - 60)))
        screen.blit(final_score_text, final_score_text.get_rect(center=(screen_rect.centerx, screen_rect.centery)))
        screen.blit(exit_text, exit_text.get_rect(center=(screen_rect.centerx, screen_rect.centery + 60)))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            isrunning = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            isrunning = False
        

    pygame.display.update()

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
pygame.quit()
cv2.destroyAllWindows()
