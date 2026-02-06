"""Simple example of running a poker game"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.table import Table
from src.bots.random_bot import RandomBot
from src.bots.call_bot import CallBot


def print_game_state(table: Table, street: str = ""):
    """Print current game state"""
    print(f"\n{'='*60}")
    if street:
        print(f"STREET: {street.upper()}")
    print(f"Round: {table.round_number} | Pot: {table.total_pot} | Blinds: {table.blinds}")
    print(f"Community Cards: {table.community_cards if table.community_cards else 'None'}")
    print(f"\nPlayers:")
    for i, (player, info) in enumerate(zip(table.players, table.player_public_infos)):
        status = "BUSTED" if info.busted else ("ACTIVE" if info.active else "FOLDED")
        button = " [BTN]" if i == table.button_position else ""
        hole = table.player_hole_cards[i] if table.player_hole_cards[i] else "???"
        print(f"  Player {i}{button}: {player.__class__.__name__:12} | "
              f"Stack: {info.stack:4} | Bet: {info.current_bet:3} | "
              f"Cards: {hole} | {status}")
    print('='*60)


def main():
    """Run a simple poker game"""
    print("Poker Tournament Environment - Simple Example")
    print("=" * 60)

    # Create bots
    bot1 = RandomBot(player_index=0)
    bot2 = CallBot(player_index=1)
    bot3 = RandomBot(player_index=2)
    bot4 = CallBot(player_index=3)

    # Define blinds schedule
    blinds_schedule = {
        1: (10, 20),
        5: (25, 50),
        10: (50, 100),
    }

    # Create table
    table = Table(
        players=[bot1, bot2, bot3, bot4],
        starting_stack=1000,
        blinds_schedule=blinds_schedule,
        max_rounds=15,
        seed=42
    )

    print(f"\nStarting game with {len(table.players)} players")
    print(f"Starting stack: 1000 chips")
    print(f"Starting blinds: {table.blinds}")

    # Initialize first hand
    table.reset_hand_state()
    table.deal_hole_cards()
    table.collect_blinds()

    print_game_state(table, "PREFLOP")

    print("\nThis is a skeleton implementation!")
    print("Next steps:")
    print("  1. Implement betting round logic")
    print("  2. Integrate HandJudge for showdown")
    print("  3. Integrate PlayerJudge for action validation")
    print("  4. Add street progression (flop, turn, river)")
    print("  5. Add pot distribution")
    print("  6. Add tournament progression")
    print("\nThe framework is ready for you to build the game engine!")


if __name__ == "__main__":
    main()
