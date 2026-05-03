import pygame
from Tools import Tools
from bullet import Bullet
from pygame.math import Vector2, Vector3

SWIDTH = Tools.SWIDTH
SHEIGHT = Tools.SHEIGHT

class Player:
    def __init__(self, startPos, scale, maxSpeed=7):
        self.pos = Vector3(startPos[0], startPos[1], 0)
        self.vel = Vector3(0)
        self.baseImage = pygame.image.load("rocket.png").convert_alpha()
        self.image = pygame.transform.scale_by(self.baseImage, scale)
        self.rect = self.image.get_rect(center=self.pos.xy)
        self.maxSpeed = maxSpeed
        self.acc = 0.5
        self.bullets = []
        self.bulletColor = "red"
        self.shootCooldown = 7
        self.shootTimer = self.shootCooldown

    def draw(self, screen):
        for bullet in self.bullets:
            bullet.render(screen)
        screen.blit(self.image, self.rect)

    def update(self, ser):
        # ActionString = self.decodeSerial(ser)
        # pygame.display.set_caption(ActionString)
        direction = self.getInput(ser)
        direction = Vector3(direction.x,direction.y,0)
        self.move(direction)
        self.getFireInput(ser)
        self.rect.center = self.pos.xy
        for bullet in self.bullets:
            bullet.update()
            if bullet.destroy:
                self.bullets.remove(bullet)
        self.checkBoundary()
        if self.shootTimer < self.shootCooldown:
            self.shootTimer += 1
            
    def getInput(self, ser):
        direction = Vector2(0)
        keys = pygame.key.get_pressed()
        if keys[pygame.K_w]:
            direction.y = -1
        if keys[pygame.K_s]:
            direction.y = 1
        if keys[pygame.K_a]:
            direction.x = -1
        if keys[pygame.K_d]:
            direction.x = 1

        # if ser.in_waiting > 0:
        #     try:
        #         line = ser.readline().decode("utf-8").strip()
        #         print(f"[Serial] {line}")
        #         #pygame.display.set_caption(f"Arduino: {line}")
        #         if line == "Moving Left":
        #             direction.x = -1
        #         if line == "Moving Right":
        #             direction.x = 1
        #         if line == "Moving Up":
        #             direction.y = -1
        #         if line == "Moving Down":
        #             direction.y = 1

        #     except Exception as e:
        #         print(f"Serial read error: {e}")

        if direction != Vector2(0):
            direction.normalize_ip()
        return direction

    def move(self, direction):
        desiredVel = direction * self.maxSpeed
        self.vel.move_towards_ip(desiredVel, self.acc)
        self.pos += self.vel

    def getFireInput(self, ser):
        keys = pygame.key.get_pressed()
        if keys [pygame.K_SPACE]:
            if self.shootTimer >= self.shootCooldown:
                self.bullets.append(Bullet(self.pos, 100, 8, [255, 0, 0]))
                self.shootTimer = 0
        # if ser.in_waiting > 0:
        #     try:
        #         line = ser.readline().decode("utf-8").strip()
        #         print(f"[Serial] {line}")
        #         pygame.display.set_caption(f"Arduino: {line}")
        #         if line == "F":
        #             self.bullets.append(Bullet(self.pos, 100, 8, [255, 0, 0]))
        #     except Exception as e:
        #         print(f"Serial read error: {e}")

    def checkBoundary(self):
        screenWidth = Tools.SWIDTH
        screenHeight= Tools.SHEIGHT
        if self.rect.top > screenHeight:
            self.rect.bottom = 0
            self.pos.x = self.rect.centerx
            self.pos.y = self.rect.centery
        if self.rect.bottom < 0:
            self.rect.top = screenHeight
            self.pos.x = self.rect.centerx
            self.pos.y = self.rect.centery
        if self.rect.left > screenWidth:
            self.rect.right = 0
            self.pos.x = self.rect.centerx
            self.pos.y = self.rect.centery
        if self.rect.right < 0:
            self.rect.left = screenWidth
            self.pos.x = self.rect.centerx
            self.pos.y = self.rect.centery

    def decodeSerial(self, ser):
        actionString = ""
        if ser.in_waiting > 0:
            print(ser.in_waiting)
            try:
                line = ser.readline()
                print(f"[Serial] {line}")
                actionString = line
            except Exception as e:
                print(f"Serial read error: {e}")
        return actionString