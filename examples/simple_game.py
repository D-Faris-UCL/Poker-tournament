"""Simple example of running a poker game"""

import sys
from pathlib import Path
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.table import Table
from src.helpers.player_loader import load_players

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

    # Load all available bots
    player_classes = load_players('src/bots')

    # Create bot instances (using first 3 available bots)
    bots = [player_class(i) for i, player_class in enumerate(player_classes)]

    print(f"Loaded {len(player_classes)} player classes")
    print(f"Playing with: {[bot.__class__.__name__ for bot in bots]}")

    # Define blinds schedule
    blinds_schedule = {
        1: (10, 20),
        50: (20, 50),
        100: (50, 100)
    }

    begin = time.time()

    
    # Create table
    table = Table(
        players=bots,
        starting_stack=2000,
        blinds_schedule=blinds_schedule,
    )

    # Play a few hands
    for hand_num in range(1, 150):
        print(f"\n{'#'*60}")
        print(f"# HAND {hand_num}")
        print(f"{'#'*60}")

        # Play the hand and get results
        result = table.simulate_hand()

        # Display hand results
        print_game_state(table, f"Hand Complete - {result['final_street'].upper()}")

        if result['showdown']:
            print("\n--- SHOWDOWN ---")
            print("\nActive players at showdown:")
            details = result.get('showdown_details')
            if details and 'hands' in details:
                for idx in details.get('players', []):
                    hole = table.player_hole_cards[idx]
                    hand_name = details['hands'].get(idx, '?')
                    hand_display = hand_name.replace('_', ' ').title() if hand_name != '?' else '?'
                    print(f"  Player {idx} ({table.players[idx].__class__.__name__}): "
                          f"{hole} - {hand_display}")
            else:
                from src.helpers.hand_judge import HandJudge
                for winner_idx in result['winners'].keys():
                    hand_eval = HandJudge.evaluate_hand(
                        table.player_hole_cards[winner_idx],
                        table.community_cards
                    )
                    print(f"  Player {winner_idx} ({table.players[winner_idx].__class__.__name__}): "
                          f"{table.player_hole_cards[winner_idx]} - {hand_eval[0].replace('_', ' ').title()}")
        elif result['ended_early']:
            print(f"\n--- Hand ended after {result['final_street']} (all but one folded) ---")
            

        # Display winners
        print("\nWinners:")
        for winner_idx, (hand_name, amount) in result['winners'].items():
            hand_display = hand_name.replace('_', ' ').title() if hand_name != "uncontested" else "Uncontested"
            print(f"  Player {winner_idx} wins {amount} chips with {hand_display}")

        # Check for eliminations
        if result['eliminated']:
            print(f"\nPlayers eliminated: {result['eliminated']}")
            

    print("\n" + "="*60)
    print("DEMO COMPLETE!")
    print("="*60)
    print(time.time()-begin)
    for player in table.players:
        player.close()


if __name__ == "__main__":
    main()
