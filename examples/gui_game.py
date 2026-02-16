"""GUI example: run a poker game with 10 exploiter bots and the visualiser."""

import sys
import threading
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.table import Table
from src.helpers.player_loader import get_player_by_name
from src.visualiser.visualiser import Visualiser

# Number of hands to play (or until one player left)
MAX_HANDS = 150

# Delay bounds seconds for each action type
DELAY_CHECK = 1
DELAY_FOLD = 0.4
DELAY_CALL = 0.7
DELAY_MAX = 3
DELAY_END = 2


def action_delay(action_type: str, amount: int) -> float:
    """Return delay in seconds for the given action (scales by significance)."""
    if action_type == "check":
        return DELAY_CHECK
    if action_type == "fold":
        return DELAY_FOLD
    if action_type in ("small_blind", "big_blind"):
        return 0.25 if action_type == "small_blind" else 0.3
    if action_type == "call":
        return DELAY_CALL
    if action_type == "all-in":
        return DELAY_MAX
    # bet / raise: scale with amount, between 0.45 and 0.9
    if action_type in ("bet", "raise"):
        # Scale by amount (e.g. 2000 stack -> ~0.7s)
        t = min(1.0, 0.45 + (amount / 3000) * 0.45)
        return min(DELAY_MAX, t)
    return DELAY_CHECK


def run_game_thread(table: Table, latest_gamestate: list) -> None:
    """Run hands in a loop, updating latest_gamestate[0] after each hand."""
    for _ in range(1, MAX_HANDS + 1):
        if table.get_public_gamestate().get_non_busted_players_count() <= 1:
            break
        result = table.simulate_hand()
        gs = table.get_public_gamestate()
        gs.last_hand_winners = {idx: amount for idx, (_, amount) in result["winners"].items()}
        latest_gamestate[0] = gs
        time.sleep(DELAY_END)


def main() -> None:
    """Run a GUI poker game with 10 exploiter bots."""
    ExploiterBot = get_player_by_name("src/bots", "exploiter_bot")
    if ExploiterBot is None:
        raise RuntimeError("exploiter_bot not found in src/bots")

    bots = [ExploiterBot(i) for i in range(10)]

    blinds_schedule = {
        1: (10, 20),
        50: (20, 50),
        100: (50, 100),
    }

    # Shared gamestate: use a list so the inner ref can be updated from the thread
    table = Table(
        players=bots,
        starting_stack=2000,
        blinds_schedule=blinds_schedule,
    )
    latest_gamestate = [table.get_public_gamestate()]

    def after_action(action_type: str, amount: int) -> None:
        latest_gamestate[0] = table.get_public_gamestate()
        time.sleep(action_delay(action_type, amount))

    table.on_after_action = after_action

    game_thread = threading.Thread(
        target=run_game_thread,
        args=(table, latest_gamestate),
        daemon=True,
    )
    game_thread.start()

    visualiser = Visualiser()
    visualiser.run_with_gamestate(lambda: latest_gamestate[0])


if __name__ == "__main__":
    main()
