import pygame
from pygame.math import Vector2

class Tools:
    SPAWN_Z = 2000
    # screen size
    SWIDTH = 920
    SHEIGHT = 920

    @staticmethod
    def projectTo(t_x, t_y, p_z = SPAWN_Z):
        screen_w = Tools.SWIDTH
        screen_h = Tools.SHEIGHT
        if screen_w + p_z == 0:
            p_x = 0
            p_cx = 0
        else:
            p_x = (screen_w * ((t_x) / (screen_w + p_z)))
            p_cx = (screen_w * ((screen_w / 2) / (screen_w + p_z)))

        if screen_h + p_z == 0:
            p_y = 0
            p_cy = 0
        else:
            p_y = (screen_h * ((t_y) / (screen_h + p_z)))
            p_cy = (screen_h * ((screen_h / 2) / (screen_h + p_z)))
        
        
        center = [screen_w / 2, screen_h / 2]
        offset = [center[0] - p_cx, center[1] - p_cy]
        p_x += offset[0]
        p_y += offset[1]
        return Vector2(p_x, p_y)

