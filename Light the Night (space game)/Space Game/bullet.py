import pygame
import math
import random
from Tools import Tools
from pygame.math import Vector2, Vector3

class Bullet:
    def __init__(self, pos, speed, radius, color):
        self.pos = Vector3(pos)
        self.new_pos = Vector2(pos[0], pos[1])
        self.speed = speed
        self.t_radius = radius
        self.radius = self.t_radius
        self.r_scale = 0.5
        self.color = color
        self.destroy = False

    def render(self, screen):
        if self.pos[2] != 0 and self.radius > 1:
            self.radius -= self.r_scale
        elif self.pos[2] == 0:
            self.radius = self.t_radius
        else:
            self.radius = 1

        pygame.draw.circle(screen, self.color, self.new_pos, int(self.radius))

    def move(self):
        self.pos[2] += self.speed
        self.new_pos = Tools.projectTo(self.pos[0], self.pos[1], self.pos[2])

    def update(self):
        self.move()
        if self.pos[2] >= Tools.SPAWN_Z:
            self.destroy = True
