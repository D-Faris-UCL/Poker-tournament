import pygame
import math
import numpy as np
import random

# Following the AAP-64 colour palette: https://lospec.com/palette-list/aap-64

# Reference resolution (16:9) for scale calculations
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
CHECKERBOARD_SQUARES_HORIZONTAL = 40
# At reference: square_size = REFERENCE_WIDTH / 40 = 48
REFERENCE_SQUARE_SIZE = REFERENCE_WIDTH / CHECKERBOARD_SQUARES_HORIZONTAL
# Multiplier for card size relative to the scaled size (2 = twice as big)
CARD_SIZE_MULTIPLIER = 2

COLOURS = {
    "table_mat": (26, 122, 62),
    "table_card_position": (36, 82, 59),
    "background_navy": (58, 68, 98),  # less saturated navy blue
    "wood": (66, 57, 52),
    "wood_highlight": (90, 78, 68),
    "wood_dark": (50, 43, 40),
}


class GameScene():
    def __init__(self, screen: pygame.Surface):
        self.screen = screen

        self.mouse_x = 0
        self.mouse_y = 0
        
        self.pixel_scale_factor = 1.0
        self.square_size = REFERENCE_SQUARE_SIZE

        self.card_kernel = pygame.image.load("assets/textures/cards/card_kernel.png")
        self.card_kernel_x = 56
        self.card_kernel_y = 80

        self.font_size = 14
        self.font = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", self.font_size)
        self.font_small = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", max(11, self.font_size - 2))

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events:
            if hasattr(event, "pos"):
                self.mouse_x, self.mouse_y = event.pos


    def update(self):
        pass

    def _update_scale(self):
        """Compute pixel scale and checker square size from screen size (16:9)."""
        width = self.screen.get_width()
        height = self.screen.get_height()
        # Enforce 16:9: use width as reference, derive height
        self.square_size = width / CHECKERBOARD_SQUARES_HORIZONTAL
        self.pixel_scale_factor = self.square_size / REFERENCE_SQUARE_SIZE

    def draw(self):
        self._update_scale()
        self.draw_background()
        self.draw_table()
        self.draw_table_cards()
        self.draw_ui()

    def draw_background(self):
        self.screen.fill(COLOURS["background_navy"])

    def draw_table(self):
        """Rectangular table ~60% of screen: wood frame, 4px darker squeeze, green checkerboard interior, light highlight."""
        w = self.screen.get_width()
        h = self.screen.get_height()
        
        # Table size ~60% of screen, centered
        table_w = int(w * 0.6)
        table_h = int(h * 0.6)
        table_x = (w - table_w) // 2
        table_y = (h - table_h) // 2
        
        table_rect = pygame.Rect(table_x, table_y, table_w, table_h)
        squeeze = 4  # pixels for darker inner band
        
        # Solid wood frame
        pygame.draw.rect(self.screen, COLOURS["wood"], table_rect)
        
        # Lighter highlight on top and left
        highlight_w = 2
        pygame.draw.rect(self.screen, COLOURS["wood_highlight"], (table_rect.left, table_rect.top, table_rect.width, highlight_w))
        pygame.draw.rect(self.screen, COLOURS["wood_highlight"], (table_rect.left, table_rect.top, highlight_w, table_rect.height))
        
        # Darker 4px squeeze
        inner_rect = table_rect.inflate(-2 * squeeze, -2 * squeeze)
        pygame.draw.rect(self.screen, COLOURS["wood_dark"], inner_rect)
        
        # Playing surface inset by 4px
        play_rect = inner_rect.inflate(-2 * squeeze, -2 * squeeze)
        play_x, play_y = play_rect.x, play_rect.y
        play_w, play_h = play_rect.width, play_rect.height
        
        pygame.draw.rect(self.screen, COLOURS["table_mat"], (play_x, play_y, play_w, play_h))
        
        # Draw rounded rectangle for 5 cards
        card_spacing = 10
        card_radius = 10
        community_card_x = play_x + play_w / 2 - 2.5 * (card_spacing + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)
        community_card_y = play_y + play_h / 2 - 0.5 * (card_spacing + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)
        
        pygame.draw.rect(
            self.screen, COLOURS["table_card_position"],
            (community_card_x, community_card_y,
            5 * (card_spacing + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER),
            (card_spacing + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)),
            border_radius=card_radius,
        )

    
    def draw_table_cards(self):
        # Positions in reference space; scale to screen
        base_y = 100
        for idx, card in enumerate(["Ah", "Ks", "Qd", "Jc", "Td", "9s", "8h", "7s"]):
            base_x = 100 + idx * 100
            x = int(base_x * self.pixel_scale_factor)
            y = int(base_y * self.pixel_scale_factor)
            self.draw_card_face_up(card, x, y)
        self.draw_card_face_down(
            int(900 * self.pixel_scale_factor),
            int(base_y * self.pixel_scale_factor),
        )
    
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
        card_scale = self.pixel_scale_factor * CARD_SIZE_MULTIPLIER
        card_scaled = pygame.transform.scale(card_image, (int(self.card_kernel_x * card_scale), int(self.card_kernel_y * card_scale)))
            
        self.screen.blit(card_scaled, (x, y))
        
    def draw_card_face_down(self, x:int, y:int):
        card = self.card_kernel.subsurface((0, 2 * self.card_kernel_y, self.card_kernel_x, self.card_kernel_y))
        card_scale = self.pixel_scale_factor * CARD_SIZE_MULTIPLIER
        card_scaled = pygame.transform.scale(card,(int(self.card_kernel_x * card_scale), int(self.card_kernel_y * card_scale)))
        
        self.screen.blit(card_scaled, (x, y))
        

    def draw_ui(self):
        pass

    def draw_hover_effects(self, mouse_x: int, mouse_y: int):
        pass