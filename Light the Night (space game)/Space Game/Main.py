import pygame
import Tools
import Stars
import random
from player import Player
from bullet import Bullet
import serial
import time
import io
from asteroid import Asteroid



# === SERIAL SETUP ===
# ser = serial.Serial('/dev/cu.usbmodem70041DD330E42', 115200, timeout=1)
ser = None
# sio = io.TextIOWrapper(io.BufferedRWPair(ser, ser))
# time.sleep(2)
# ser.reset_input_buffer()

# === PYGAME SETUP ===
pygame.init()
WIDTH = Tools.Tools.SWIDTH
HEIGHT = Tools.Tools.SHEIGHT
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Waiting for button press...")

clock = pygame.time.Clock()
fps = 60
dt = 0

# === ROCKET SETUP ===
rocket = Player([WIDTH / 2, HEIGHT / 2], 0.5)

# === STARFIELD SETUP ===
allstars = []
for i in range(600):
    position = [random.randint(-4000, 4000), random.randint(-4000, 4000)]
    star = Stars.Star(position, 1, 5)
    allstars.append(star)

asteroids = []
for i in range(100):
    position = [random.randint(-800, 800), random.randint(-600, 600), 2000]
    asteroids.append(Asteroid(position,10,5))

def update(dt):
    for star in allstars:
        star.move()
    rocket.update(ser)
    for a in asteroids:
        a.update(screen)
    print(asteroids[0].pos)

def draw(screen):
    screen.fill([0, 0, 0])
    for star in allstars:
        star.draw(screen)
    rocket.draw(screen)

# === MAIN LOOP ===
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    update(dt)
    draw(screen)
    dt = clock.tick(fps) / 1000
    pygame.display.update()
    

pygame.quit()
ser.close()
