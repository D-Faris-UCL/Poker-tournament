"""Pygame example: human plays poker with bots. Hole cards bottom-left, betting panel bottom-right."""

import os
import sys
import threading
import queue
import time
from pathlib import Path
from typing import Tuple, List, Optional

# Add parent directory to path and ensure assets load from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

import pygame

from src.core.table import Table
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.player_loader import get_player_by_name
from src.helpers.player_judge import PlayerJudge
from src.visualiser.scene import GameScene, COLOURS

# Human player index (seated at table position 0)
HUMAN_INDEX = 0
MAX_HANDS = 150
FPS = 60

# Raise multiplier options (e.g. 0.5x, 1x, 1.5x, 2x pot)
RAISE_MULTIPLIERS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]


class HumanPlayer(Player):
    """Player that blocks on a queue until the UI provides an action."""

    def __init__(
        self,
        player_index: int,
        pending_action_queue: queue.Queue,
        latest_gamestate: list,
    ):
        super().__init__(player_index)
        self.pending_action_queue = pending_action_queue
        self.latest_gamestate = latest_gamestate

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
    ) -> Tuple[str, int]:
        # Expose only this player's hole cards for the UI
        n = len(gamestate.player_public_infos)
        gamestate.player_hole_cards = [None] * n
        gamestate.player_hole_cards[self.player_index] = hole_cards
        self.latest_gamestate[0] = gamestate

        action_type, amount = self.pending_action_queue.get()
        if action_type == "call" and amount == 0:
            amount = gamestate.get_bet_to_call() - gamestate.player_public_infos[
                self.player_index
            ].current_bet
        if action_type == "all-in" and amount == 0:
            amount = gamestate.player_public_infos[self.player_index].stack
        return (action_type, amount)


def run_game_thread(table: Table, latest_gamestate: list) -> None:
    """Run hands in a loop, updating latest_gamestate[0] after each hand and after each action."""
    for _ in range(1, MAX_HANDS + 1):
        if table.get_public_gamestate().get_non_busted_players_count() <= 1:
            break

        result = table.simulate_hand()
        gamestate = table.get_public_gamestate()
        gamestate.last_hand_winners = {
            idx: amount for idx, (_, amount) in result["winners"].items()
        }
        # Expose only human's hole cards
        n = len(table.players)
        gamestate.player_hole_cards = [None] * n
        gamestate.player_hole_cards[HUMAN_INDEX] = table.player_hole_cards[HUMAN_INDEX]

        if result.get("showdown"):
            gamestate.last_hand_revealed_cards = {
                i: table.player_hole_cards[i]
                for i in range(len(table.players))
                if table.player_hole_cards[i] is not None
                and table.player_public_infos[i].active
            }
        else:
            gamestate.last_hand_revealed_cards = None

        latest_gamestate[0] = gamestate
        time.sleep(2.0)


def _ensure_gamestate(gamestate: Optional[PublicGamestate]) -> Optional[PublicGamestate]:
    """Return gamestate if it has required attributes for drawing."""
    if gamestate is None:
        return None
    if not hasattr(gamestate, "player_public_infos") or not gamestate.player_public_infos:
        return None
    return gamestate


def draw_hole_cards_bottom_left(
    screen: pygame.Surface,
    scene: GameScene,
    gamestate: Optional[PublicGamestate],
) -> None:
    """Draw the human player's hole cards at bottom-left of the screen."""
    gamestate = _ensure_gamestate(gamestate)
    if gamestate is None:
        return
    hole_cards = getattr(gamestate, "player_hole_cards", None)
    if hole_cards is None or HUMAN_INDEX >= len(hole_cards):
        return
    cards = hole_cards[HUMAN_INDEX]
    if cards is None:
        return

    scene._update_scale()
    # Same scale as scene's small cards (CARD_SIZE_MULTIPLIER * 0.75)
    card_scale = scene.pixel_scale_factor * 2 * 0.75
    card_w = int(scene.card_kernel_x * card_scale)
    card_h = int(scene.card_kernel_y * card_scale)
    gap = 10
    margin_left = 30
    margin_bottom = 30
    w, h = screen.get_width(), screen.get_height()
    y = h - margin_bottom - card_h
    x1 = margin_left
    x2 = margin_left + card_w + gap
    scene.draw_card_face_up(cards[0], x1, y, small=True)
    scene.draw_card_face_up(cards[1], x2, y, small=True)


def _total_pot(gamestate: PublicGamestate) -> int:
    return gamestate.total_pot + sum(
        info.current_bet for info in gamestate.player_public_infos
    )


def compute_bet_amount(
    gamestate: PublicGamestate,
    human_index: int,
    multiplier: float,
) -> int:
    """Compute bet amount (total to put in) when first to act, clamped to legal range."""
    legal = PlayerJudge.get_legal_actions(
        human_index,
        gamestate.player_public_infos,
        gamestate.get_bet_to_call(),
        gamestate.minimum_raise_amount,
    )
    if not legal.get("bet", False):
        return 0
    total_pot = _total_pot(gamestate)
    bet_total = int(multiplier * total_pot)
    bet_total = max(legal["min_bet"], min(legal["max_bet"], bet_total))
    return bet_total


def compute_raise_amount(
    gamestate: PublicGamestate,
    human_index: int,
    multiplier: float,
) -> int:
    """Compute raise amount (additional chips) as multiplier * pot, clamped to legal range."""
    legal = PlayerJudge.get_legal_actions(
        human_index,
        gamestate.player_public_infos,
        gamestate.get_bet_to_call(),
        gamestate.minimum_raise_amount,
    )
    
    if not legal.get("raise", False):
        return 0
    
    total_pot = _total_pot(gamestate)
    player_info = gamestate.player_public_infos[human_index]
    raise_by = int(multiplier * total_pot)
    
    min_raise_extra = (
        legal["min_raise"] - player_info.current_bet
        if legal.get("min_raise")
        else gamestate.minimum_raise_amount
    )
    
    max_extra = player_info.stack
    raise_by = max(min_raise_extra, min(max_extra, raise_by))
    
    return raise_by


def draw_betting_panel(
    screen: pygame.Surface,
    scene: GameScene,
    gamestate: Optional[PublicGamestate],
    raise_multiplier_index: int,
    button_rects: dict,
) -> None:
    """
    Draw Fold, Check, Call, Raise buttons and multiplier selector at bottom-right.
    Fill button_rects with name -> pygame.Rect for hit-testing.
    """
    button_rects.clear()
    gamestate = _ensure_gamestate(gamestate)
    
    w, h = screen.get_width(), screen.get_height()
    margin_right = 30
    margin_bottom = 30
    btn_h = 44
    btn_gap = 12
    panel_top = h - margin_bottom - btn_h - 60

    if gamestate is None:
        return
    
    current = getattr(gamestate, "current_player", None)
    
    if current != HUMAN_INDEX:
        return
    
    if HUMAN_INDEX >= len(gamestate.player_public_infos):
        return
    
    info = gamestate.player_public_infos[HUMAN_INDEX]
    
    if not info.active or info.is_all_in:
        return

    scene._update_scale()
    font = scene.font_small
    current_bet = gamestate.get_bet_to_call()
    
    legal = PlayerJudge.get_legal_actions(
        HUMAN_INDEX,
        gamestate.player_public_infos,
        current_bet,
        gamestate.minimum_raise_amount,
    )
    
    mult = RAISE_MULTIPLIERS[raise_multiplier_index]
    bet_amt = compute_bet_amount(gamestate, HUMAN_INDEX, mult)
    raise_amt = compute_raise_amount(gamestate, HUMAN_INDEX, mult)

    # Multiplier selector and amount label (above buttons)
    mult_text = font.render(
        f"{mult}x pot: Bet={bet_amt} Raise={raise_amt}",
        True,
        COLOURS["text"],
    )
    
    screen.blit(mult_text, (w - margin_right - mult_text.get_width(), panel_top - 22))

    # Buttons right-aligned
    labels = []
    if legal.get("fold"):
        labels.append(("Fold", "fold", 0))

    if legal.get("check"):
        labels.append(("Check", "check", 0))

    # Call: show when there's a bet to call and we have chips (full call or call all-in into side pots)
    call_amt = legal.get("call_amount", 0)
    if call_amt > 0 and info.stack > 0:
        if info.stack >= call_amt:
            labels.append((f"Call {call_amt}", "call", 0))
        else:
            labels.append((f"Call All-in {info.stack}", "call", 0))

    if legal.get("bet"):
        labels.append((f"Bet {bet_amt}", "bet", bet_amt))
        
    if legal.get("raise"):
        labels.append((f"Raise {raise_amt}", "raise", raise_amt))

    # All-in: show whenever player has chips (so they can go all-in at any time)
    if info.stack > 0:
        labels.append((f"All-in {info.stack}", "all-in", 0))

    x = w - margin_right
    
    for label_text, action_key, amount in reversed(labels):
        tw = font.render(label_text, True, COLOURS["button_text"]).get_width()
        
        bw = max(80, tw + 20)
        x -= bw + btn_gap
        
        rect = pygame.Rect(x, panel_top, bw, btn_h)
        
        button_rects[action_key] = (rect, amount)
        
        pygame.draw.rect(screen, COLOURS["button"], rect, border_radius=6)
        pygame.draw.rect(screen, COLOURS["wood_dark"], rect, 2, border_radius=6)
        
        text_surf = font.render(label_text, True, COLOURS["button_text"])
        
        screen.blit(
            text_surf,
            (
                rect.centerx - text_surf.get_width() // 2,
                rect.centery - text_surf.get_height() // 2,
            ),
        )

    # Multiplier selector buttons: < 0.5x 1x 1.5x 2x ... >
    sel_y = panel_top + btn_h + 8
    sel_h = 28
    
    for i, m in enumerate(RAISE_MULTIPLIERS):
        mw = 36
        mx = w - margin_right - (len(RAISE_MULTIPLIERS) - i) * (mw + 4)
        
        mrect = pygame.Rect(mx, sel_y, mw, sel_h)
        
        key = f"mult_{i}"
        button_rects[key] = (mrect, None)
        
        col = COLOURS["current_player"] if i == raise_multiplier_index else COLOURS["wood"]
        
        pygame.draw.rect(screen, col, mrect, border_radius=4)
        
        ms = font.render(f"{m}x", True, COLOURS["button_text"])
        
        screen.blit(ms, (mrect.centerx - ms.get_width() // 2, mrect.centery - ms.get_height() // 2))


def main() -> None:
    """Run a poker game with one human (index 0) and exploiter bots."""
    ExploiterBot = get_player_by_name("src/bots", "exploiter_bot")
    
    if ExploiterBot is None:
        raise RuntimeError("exploiter_bot not found in src/bots")

    action_queue: queue.Queue = queue.Queue()
    latest_gamestate: List[Optional[PublicGamestate]] = [None]

    human = HumanPlayer(HUMAN_INDEX, action_queue, latest_gamestate)
    bots = [ExploiterBot(i) for i in range(1, 10)]
    players: List[Player] = [human] + bots

    blinds_schedule = {
        1: (10, 20),
        50: (25, 50),
        100: (50, 100),
    }
    
    table = Table(
        players=players,
        starting_stack=2000,
        blinds_schedule=blinds_schedule,
    )

    gs = table.get_public_gamestate()
    n = len(players)
    gs.player_hole_cards = [None] * n
    latest_gamestate[0] = gs

    def after_action(action_type: str, amount: int) -> None:
        gs = table.get_public_gamestate()
        gs.player_hole_cards = [None] * n
        gs.player_hole_cards[HUMAN_INDEX] = table.player_hole_cards[HUMAN_INDEX]
        latest_gamestate[0] = gs
        time.sleep(0.3)

    table.on_after_action = after_action

    game_thread = threading.Thread(
        target=run_game_thread,
        args=(table, latest_gamestate),
        daemon=True,
    )
    game_thread.start()

    pygame.init()
    screen = pygame.display.set_mode((1080, 720), pygame.RESIZABLE)
    pygame.display.set_caption("Poker – You are Player 0")
    clock = pygame.time.Clock()
    scene = GameScene(screen, cards_exposed=False)

    button_rects: dict = {}
    raise_multiplier_index = 1  # 1x pot default

    while True:
        events = pygame.event.get()
        
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
                
            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
                scene.screen = screen
                
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gs = _ensure_gamestate(latest_gamestate[0])
                
                if gs and getattr(gs, "current_player", None) == HUMAN_INDEX:
                    for key, (rect, amount) in list(button_rects.items()):
                        if rect.collidepoint(event.pos):
                            if key.startswith("mult_"):
                                raise_multiplier_index = int(key.split("_")[1])
                                break
                            
                            if key in ("fold", "check"):
                                action_queue.put((key, 0))
                                break
                            
                            if key == "call":
                                action_queue.put(("call", 0))
                                break
                            
                            if key == "bet":
                                mult = RAISE_MULTIPLIERS[raise_multiplier_index]
                                amt = compute_bet_amount(gs, HUMAN_INDEX, mult)
                                action_queue.put(("bet", amt))
                                break
                            
                            if key == "raise":
                                mult = RAISE_MULTIPLIERS[raise_multiplier_index]
                                amt = compute_raise_amount(gs, HUMAN_INDEX, mult)
                                action_queue.put(("raise", amt))
                                break
                            if key == "all-in":
                                action_queue.put(("all-in", 0))
                                break

        gamestate = latest_gamestate[0]
        
        scene.update(gamestate)
        scene.handle_events(events)
        scene.draw()
        draw_hole_cards_bottom_left(screen, scene, gamestate)
        draw_betting_panel(screen, scene, gamestate, raise_multiplier_index, button_rects)

        pygame.display.flip()
        clock.tick(FPS)


if __name__ == "__main__":
    main()
