import pygame
import random
from Tools import Tools
from pygame.math import Vector2, Vector3

SWIDTH = Tools.SWIDTH
SHEIGHT = Tools.SHEIGHT

# class Asteroid:
#     def __init__(self,pos,minSize,mazSize):
#         self.pos = pos
#         self.minSize = minSize
#         self.maxSize = mazSize
#         self.size = self.minSize
#         self.speed = 75
#         self.distance = SWIDTH + random.randint(1000, 10000)
#         self.x = SWIDTH / 2 + self.pos[0] * SWIDTH / self.distance
#         self.y = SHEIGHT / 2 + self.pos[1] * SHEIGHT / self.distance

#     def update(self,screen):
#         self.draw(screen)
#         self.move()

#     def move(self):
#             if self.distance > SWIDTH:
#                 self.distance -= self.speed
#                 self.x = SWIDTH / 2 + self.pos[0] * SWIDTH / self.distance
#                 self.y = SHEIGHT / 2 + self.pos[1] * SHEIGHT / self.distance
#                 self.size = min(self.size + 0.05, self.maxSize)
#             else:
#                 self.distance = SWIDTH + random.randint(1000, 10000)
#                 self.pos[0] = random.randint(-4000, 4000)
#                 self.pos[1] = random.randint(-4000, 4000)
#                 self.size = self.minSize
    
#     def draw(self,screen):
#         pos = pygame.math.Vector2(self.pos[0],self.pos[1])
#         image = pygame.Surface([self.size,self.size])
#         image.fill("gray")
#         rect = image.get_rect(center = pos)
#         screen.blit(image,rect)



class Asteroid:
    def __init__(self,pos,speed,radius):
        self.pos = Vector3(pos)
        self.new_pos = Vector2(pos[0],pos[1])
        self.speed = speed
        self.t_radius = radius
        self.radius = self.t_radius
        self.r_scale = .5
        self.color = "blue"
        self.destroyed = False

    def render(self,screen):
        if self.pos[2] != 0 and self.radius > 1:
            self.r_scale = .5
            self.radius = self.radius - self.r_scale
        elif self.pos[2] == 0:
            self.radius = self.t_radius
        else:
            self.radius = 1
        pygame.draw.circle(screen,self.color,self.new_pos,10)

    def move(self):
        if self.pos[2] > 0:
            self.pos[2] -= self.speed
            self.new_pos = Tools.projectTo(self.pos[0],self.pos[1],self.pos[2])
        else:
            self.destroyed = True

    def destroy(self):
        if self.pos[2] >= Tools.SPAWN_Z:
            self.destroyed = True

    def update(self,screen):
        self.render(screen)
        self.move()