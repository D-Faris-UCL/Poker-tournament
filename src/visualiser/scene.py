import pygame
import math
import numpy as np
import random

#Following the AAP-64 colour palette: https://lospec.com/palette-list/aap-64

COLOURS = {
    "table_light": (26, 122, 62),
    "table_dark": (36, 82, 59),
    "table_wood": (82, 55, 28),
    "table_frame_dark": (61, 41, 20),
    "table_frame_wood": (82, 55, 28),
    "table_frame_light": (120, 82, 42),
    "table_frame_inner_shadow": (18, 16, 14),
    "table_frame_inner_highlight": (255, 255, 255),
    "table_frame_outer_shadow": (18, 16, 14),
    "table_frame_outer_highlight": (255, 255, 255),
}


class GameScene():
    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        self.mouse_x = 0
        self.mouse_y = 0
        
        self.pixel_scale_factor = 1.0
        
        self.card_kernel = pygame.image.load("assets/textures/cards/card_kernel.png")
        self.card_kernel_x = 56
        self.card_kernel_y = 80
        
        
        self.font_size = max(14, int(13 * self.pixel_scale_factor))

        self.font_size = max(14, int(13 * self.pixel_scale_factor))
        self.font = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", self.font_size)
        self.font_small = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", max(11, self.font_size - 2))

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events:
            if hasattr(event, "pos"):
                self.mouse_x, self.mouse_y = event.pos


    def update(self):
        pass

    def draw(self):
        self.draw_background()
        self.draw_table()
        self.draw_table_cards()
        self.draw_ui()

    def draw_background(self):
        self.screen.fill(COLOURS["table_light"])
    
    def draw_table(self):
        pass
    
    def draw_table_cards(self):
        self.draw_card_face_up("Ah", 100, 100)
        self.draw_card_face_up("Ks", 200, 100)
        self.draw_card_face_up("Qd", 300, 100)
        self.draw_card_face_up("Jc", 400, 100)
        self.draw_card_face_up("Td", 500, 100)
        self.draw_card_face_up("9s", 600, 100)
        self.draw_card_face_up("8h", 700, 100)
        self.draw_card_face_up("7s", 800, 100)
        self.draw_card_face_down(900, 100)
    
    def draw_card_face_up(self, card:str, x:int, y:int):
        rank, suit = card[0], card[1]
        
        if rank.isnumeric():
            i = self.card_kernel_x * int(rank)
        elif rank == "A":
            i = self.card_kernel_x
        elif rank == "J":
            i = self.card_kernel_x * 11
        elif rank == "Q":
            i = self.card_kernel_x * 12
        elif rank == "K":
            i = self.card_kernel_x * 13
        elif rank == "T":
            i = self.card_kernel_x * 10
        else:
            i = 0
            
        
        if suit == "h":
            j = 0
        elif suit == "s":
            j = self.card_kernel_y
        elif suit == "d":
            j = self.card_kernel_y * 2
        elif suit == "c":
            j = self.card_kernel_y * 3
            
        #get single card image from card kernel
        card_image = self.card_kernel.subsurface((i, j, self.card_kernel_x, self.card_kernel_y))
        
        #scale card image to pixel scale factor
        card_scaled = pygame.transform.scale(card_image, (self.card_kernel_x * self.pixel_scale_factor, self.card_kernel_y * self.pixel_scale_factor))
            
        self.screen.blit(card_scaled, (x, y))
        
    def draw_card_face_down(self, x:int, y:int):
        card = self.card_kernel.subsurface((0, 2 * self.card_kernel_y, self.card_kernel_x, self.card_kernel_y))
        card_scaled = pygame.transform.scale(card, (self.card_kernel_x * self.pixel_scale_factor, self.card_kernel_y * self.pixel_scale_factor))
        self.screen.blit(card_scaled, (x, y))
        

    def draw_ui(self):
        pass

    def draw_hover_effects(self, mouse_x: int, mouse_y: int):
        pass