import pygame
import math
import numpy as np
import random

from src.core.gamestate import PublicGamestate
from src.visualiser.visual_util import calculate_chip_denominations
from src.core.data_classes import Pot

# Following the AAP-64 colour palette: https://lospec.com/palette-list/aap-64

# Reference resolution (16:9) for scale calculations
REFERENCE_WIDTH = 1920
REFERENCE_HEIGHT = 1080
CHECKERBOARD_SQUARES_HORIZONTAL = 40
# At reference: square_size = REFERENCE_WIDTH / 40 = 48
REFERENCE_SQUARE_SIZE = REFERENCE_WIDTH / CHECKERBOARD_SQUARES_HORIZONTAL
# Multiplier for card size relative to the scaled size (2 = twice as big)
CARD_SIZE_MULTIPLIER = 2
CHIP_SIZE_MULTIPLIER = 1.5

COLOURS = {
    "table_mat": (26, 122, 62),
    "table_card_position": (36, 82, 59),
    "background_navy": (58, 68, 98),
    "wood": (66, 57, 52),
    "wood_highlight": (90, 78, 68),
    "wood_dark": (50, 43, 40),
    "button": (254, 243, 192),
    "text": (255, 255, 255),
    "current_player": (255, 215, 0),
    "button_text": (20, 16, 19),
}


class GameScene():
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.gamestate: PublicGamestate = None
        self.mouse_x = 0
        self.mouse_y = 0
        
        self.pixel_scale_factor = 1.0
        self.square_size = REFERENCE_SQUARE_SIZE

        self.card_kernel = pygame.image.load("assets/textures/cards/card_kernel.png")
        self.card_kernel_x = 56
        self.card_kernel_y = 80
        
        self.play_x = 0
        self.play_y = 0
        self.play_w = 0
        self.play_h = 0
        
        self.community_card_x = 0
        self.community_card_y = 0
        self.card_spacing = 10
        self.card_radius = 10

        self.font_size = 50
        self.font_size_small = 25
        self.font = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", self.font_size)
        self.font_small = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", self.font_size_small)
        
        self.chip_500 = pygame.image.load("assets/textures/chips/chip_500.png")
        self.chip_100 = pygame.image.load("assets/textures/chips/chip_100.png")
        self.chip_50 = pygame.image.load("assets/textures/chips/chip_50.png")
        self.chip_25 = pygame.image.load("assets/textures/chips/chip_25.png")
        self.chip_5 = pygame.image.load("assets/textures/chips/chip_5.png")
        self.chip_1 = pygame.image.load("assets/textures/chips/chip_1.png")

    def handle_events(self, events: list[pygame.event.Event]):
        for event in events:
            if hasattr(event, "pos"):
                self.mouse_x, self.mouse_y = event.pos


    def update(self, gamestate: PublicGamestate):
        self.gamestate = gamestate

    def _update_scale(self):
        """Compute pixel scale and checker square size from screen size (16:9)."""
        width = self.screen.get_width()
        height = self.screen.get_height()
        # Enforce 16:9: use width as reference, derive height
        self.square_size = width / CHECKERBOARD_SQUARES_HORIZONTAL
        self.pixel_scale_factor = self.square_size / REFERENCE_SQUARE_SIZE
        
        self.font = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", int(self.font_size * self.pixel_scale_factor))
        self.font_small = pygame.font.Font("assets/fonts/Jersey_10/Jersey10-Regular.ttf", int(self.font_size_small * self.pixel_scale_factor))

    def _get_display_pot_state(self):
        """Include current bets in pot display so chips update after each action."""
        pending_bets = sum(info.current_bet for info in self.gamestate.player_public_infos)
        display_total = self.gamestate.total_pot + pending_bets
        
        if not self.gamestate.pots:
            display_pots = [Pot(pending_bets, [])] if pending_bets > 0 else []
        else:
            first = self.gamestate.pots[0]
            display_pots = [Pot(first.amount + pending_bets, first.eligible_players)] + list(self.gamestate.pots[1:])
            
        return display_total, display_pots

    def draw(self):
        self._update_scale()
        self.draw_background()
        self.draw_table()
        self.draw_table_cards()
        display_total, display_pots = self._get_display_pot_state()
        self.draw_pot_chips(display_pots)
        self.draw_button()
        self.draw_ui(display_total)

    def draw_background(self):
        self.screen.fill(COLOURS["background_navy"])

    def draw_table(self):
        """Rectangular table ~60% of screen: wood frame, 4px darker squeeze, green checkerboard interior, light highlight."""
        w = self.screen.get_width()
        h = self.screen.get_height()
        
        # Table size ~75% of screen, centered
        table_w = int(w * 0.75)
        table_h = int(h * 0.75)
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
        self.play_x, self.play_y = play_rect.x, play_rect.y
        self.play_w, self.play_h = play_rect.width, play_rect.height
        
        pygame.draw.rect(self.screen, COLOURS["table_mat"], (self.play_x, self.play_y, self.play_w, self.play_h))
        
        # Draw rounded rectangle for 5 cards
        
        self.community_card_x = self.play_x + self.play_w / 2 - 2.5 * (self.card_spacing + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)
        self.community_card_y = self.play_y + self.play_h / 2 - 0.5 * (self.card_spacing + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)
        
        pygame.draw.rect(
            self.screen, COLOURS["table_card_position"],
            (self.community_card_x, self.community_card_y,
            5 * (self.card_spacing + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER),
            (self.card_spacing + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER)),
            border_radius=self.card_radius,
        )

    
    def draw_table_cards(self): 
        # Draw community cards
        for i in range(5):
            x = self.community_card_x + i * (self.card_spacing + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER) + self.card_spacing / 2
            y = self.community_card_y + self.card_spacing / 2
            
            if i < len(self.gamestate.community_cards):
                self.draw_card_face_up(self.gamestate.community_cards[i], x, y)
            else:
                self.draw_card_face_down(x, y)
                
        edge_offset = 10 * self.pixel_scale_factor
                
        # Draw player cards face down
        for i in range(len(self.gamestate.player_public_infos)):
            if self.gamestate.player_public_infos[i].active:
                center_x, center_y = self.calculate_player_position(i)
                
                if i == 0:
                    self.draw_card_face_down(center_x + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 2 -2,
                                             center_y + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER/2 + 1, 
                                             rotated=True, 
                                             small=True)
                    
                    self.draw_card_face_down(center_x + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 2 -2, 
                                             center_y - 1, 
                                             rotated=True, 
                                             small=True)
                elif i == 5:
                    self.draw_card_face_down(center_x - edge_offset,
                                             center_y + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER/2 + 1, 
                                             rotated=True, 
                                             small=True)
                    
                    self.draw_card_face_down(center_x - edge_offset, 
                                             center_y - 1, 
                                             rotated=True, 
                                             small=True)
                elif i in range(1, 5):
                    self.draw_card_face_down(center_x + 2,
                                             center_y + edge_offset,
                                             small=True)
                    
                    self.draw_card_face_down(center_x - self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 3 -2,
                                             center_y + edge_offset, 
                                             small=True)
                    
                elif i in range(6, 10):
                    self.draw_card_face_down(center_x + 2,
                                             center_y - self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 3 + 2,
                                             small=True)
                    
                    self.draw_card_face_down(center_x - self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 3 -2,
                                             center_y - self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + edge_offset * 3 + 2,
                                             small=True)
    
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
        
    def draw_card_face_down(self, x:int, y:int, rotated:bool=False, small:bool=False):
        card = self.card_kernel.subsurface((0, 2 * self.card_kernel_y, self.card_kernel_x, self.card_kernel_y))
        card_scale = self.pixel_scale_factor * CARD_SIZE_MULTIPLIER
        
        if small:
            card_scale = card_scale * 0.75
            
        card_scaled = pygame.transform.scale(card,(int(self.card_kernel_x * card_scale), int(self.card_kernel_y * card_scale)))
        
        
        if rotated:
            card_scaled = pygame.transform.rotate(card_scaled, 90)
            x = x - card_scaled.get_width()
            y = y - card_scaled.get_height()
            
        self.screen.blit(card_scaled, (x, y))
        
    def draw_button(self):
        
        button = self.gamestate.button_position
        button_radius = 20 * self.pixel_scale_factor

        play_offset = 50 * self.pixel_scale_factor
        
        center_x, center_y = self.calculate_player_position(button)
        
        if button == 0:
            center_x = center_x + self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER + play_offset
        elif button == 5:
            center_x = center_x - self.card_kernel_x * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER - play_offset
        elif button in range(1, 5):
            center_y = center_y + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER
        elif button in range(6, 10):
            center_y = center_y - self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER


        pygame.draw.circle(self.screen, COLOURS["button"], (int(center_x), int(center_y)), button_radius)
        
        #draw button text
        button_text = self.font_small.render(f"BTN", True, COLOURS["button_text"])
        self.screen.blit(button_text, (int(center_x - button_text.get_width() / 2), int(center_y - button_text.get_height() / 2)))
        
    def calculate_player_position(self, player_index: int):
        """table has max 10 players with 1 at each end and 4 each long side"""
        spacing = self.play_w / 5
        
        if player_index == 0:
            center_x = self.play_x
            center_y = self.play_y + self.play_h / 2
        elif player_index == 5:
            center_x = self.play_x + self.play_w
            center_y = self.play_y + self.play_h / 2
        elif player_index in range(1, 5):
            center_x = self.play_x + spacing * player_index
            center_y = self.play_y
        elif player_index in range(6, 10):
            center_x = self.play_x + self.play_w - spacing * (player_index - 5)
            center_y = self.play_y + self.play_h
        else:
            center_x = self.play_x + self.play_w / 2
            center_y = self.play_y + self.play_h / 2
            
        return center_x, center_y
    
    def draw_pot_chips(self, pots: list[Pot]):
        if not pots:
            return
        
        width_of_chip = self.chip_500.get_width() * self.pixel_scale_factor * CHIP_SIZE_MULTIPLIER
        stack_spacing = 35 * self.pixel_scale_factor * CHIP_SIZE_MULTIPLIER
        pot_stack_gap = 2 * stack_spacing  # gap between separate pot stacks
        
        table_center_x = self.play_x + self.play_w / 2
        pot_y = self.play_y + self.play_h / 2 + self.card_kernel_y * self.pixel_scale_factor * CARD_SIZE_MULTIPLIER * 0.55

        # Width of each pot block
        block_widths = []
        for pot in pots:
            denominations = calculate_chip_denominations(pot.amount)
            num_stacks = len(denominations)
            
            block_width = (num_stacks - 1) * stack_spacing + width_of_chip if num_stacks else width_of_chip
            
            block_widths.append(block_width)

        total_width = sum(block_widths) + (len(pots) - 1) * pot_stack_gap
        left_edge = table_center_x - total_width / 2

        for pot_index, pot in enumerate(pots):
            denominations = calculate_chip_denominations(pot.amount)
            num_stacks = len(denominations)
            
            if num_stacks == 0:
                continue
            
            block_start = left_edge + sum(block_widths[:pot_index]) + pot_index * pot_stack_gap
            first_stack_x = block_start
            
            for i, (denomination, count) in enumerate(denominations.items()):
                for j in range(count):
                    self.draw_chip(denomination, int(first_stack_x + i * stack_spacing), int(pot_y + j * 10 * self.pixel_scale_factor * CHIP_SIZE_MULTIPLIER))
                    
    def draw_chip(self, denomination: int, x: int, y: int):
        if denomination not in [500, 100, 50, 25, 5, 1]:
            return
        
        if denomination == 500:
            chip_image = self.chip_500
        elif denomination == 100:
            chip_image = self.chip_100
        elif denomination == 50:
            chip_image = self.chip_50
        elif denomination == 25:
            chip_image = self.chip_25
        elif denomination == 5:
            chip_image = self.chip_5
        elif denomination == 1:
            chip_image = self.chip_1
            
        chip_scale = self.pixel_scale_factor * CHIP_SIZE_MULTIPLIER
        chip_scaled = pygame.transform.scale(chip_image, (int(chip_image.get_width() * chip_scale), int(chip_image.get_height() * chip_scale)))
        
        self.screen.blit(chip_scaled, (int(x), int(y)))

    def draw_ui(self, display_total_pot: int = None):
        if display_total_pot is None:
            display_total_pot = self.gamestate.total_pot + sum(info.current_bet for info in self.gamestate.player_public_infos)
        ui_length = 10

        #draw current round
        round_text = self.font.render(f"Round: {self.gamestate.round_number}", True, COLOURS["text"])
        self.screen.blit(round_text, (ui_length, 10))

        ui_length += round_text.get_width() + 20

        #draw total pot size (includes current bets so it updates after each action)
        total_pot_text = self.font.render(f"Total Pot: {display_total_pot}", True, COLOURS["text"])
        self.screen.blit(total_pot_text, (ui_length, 10))
        
        #draw player ui
        current_player = getattr(self.gamestate, "current_player", None)
        for i in range(len(self.gamestate.player_public_infos)):
            if not self.gamestate.player_public_infos[i].busted:
                info = self.gamestate.player_public_infos[i]
                center_x, center_y = self.calculate_player_position(i)
                line_spacing = 2 * self.pixel_scale_factor
                player_colour = COLOURS["current_player"] if current_player is not None and i == current_player else COLOURS["text"]

                #player name (show "Folded" for players who folded this hand)
                name = f"Player {i}:" + (" (Folded)" if not info.active else "")
                name_text = self.font_small.render(f"{name}", True, player_colour)

                #player current bet
                current_bet = f"Current Bet - {info.current_bet}"
                current_bet_text = self.font_small.render(f"{current_bet}", True, player_colour)

                #player stack size
                stack_size = f"Stack - {info.stack}"
                stack_text = self.font_small.render(f"{stack_size}", True, player_colour)
                
                text_height = int(sum([name_text.get_height(), current_bet_text.get_height(), stack_text.get_height(), 2 * line_spacing]))
                text_width = int(max(name_text.get_width(), current_bet_text.get_width(), stack_text.get_width()))
                
                
                if i == 0:
                    center_x = center_x - text_width / 2 - 15 * self.pixel_scale_factor
                elif i == 5:
                    center_x = center_x + text_width / 2 + 15 * self.pixel_scale_factor
                elif i in range(1, 5):
                    center_y = center_y - text_height + 30 * self.pixel_scale_factor
                elif i in range(6, 10):
                    center_y = center_y + text_height - 30 * self.pixel_scale_factor
                else:
                    center_x = center_x - text_width / 2
                    center_y = center_y - text_height / 2
                    
                top_x = center_x - text_width / 2
                top_y = center_y - text_height / 2
                    
                self.screen.blit(name_text, (top_x, top_y))
                
                self.screen.blit(current_bet_text, (top_x, top_y + name_text.get_height() + line_spacing))
                
                self.screen.blit(stack_text, (top_x, top_y + name_text.get_height() + current_bet_text.get_height() + 2 * line_spacing))

    def draw_hover_effects(self, mouse_x: int, mouse_y: int):
        pass