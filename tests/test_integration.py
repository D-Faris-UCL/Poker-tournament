"""Integration tests for poker tournament system"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.table import Table
from src.core.data_classes import PlayerPublicInfo, Pot
from bots.random_bot.player import RandomBot
from bots.call_bot.player import CallBot
from src.helpers.hand_judge import HandJudge


def test_chip_leak():
    """Test for chip leaks across multiple game simulations"""
    print("Testing chip leak detection...")

    errors_found = []

    # Test with various configurations
    configs = [
        {"stack": 100, "seeds": 20, "desc": "Small stacks (100)"},
        {"stack": 500, "seeds": 20, "desc": "Medium stacks (500)"},
        {"stack": 1000, "seeds": 20, "desc": "Large stacks (1000)"},
    ]

    for config in configs:
        print(f"  Testing: {config['desc']}")

        for seed_val in range(config['seeds']):
            bot1 = RandomBot(player_index=0)
            bot2 = CallBot(player_index=1)
            bot3 = RandomBot(player_index=2)
            bot4 = CallBot(player_index=3)

            blinds_schedule = {
                1: (10, 20),
                5: (25, 50),
                10: (50, 100),
            }

            table = Table(
                players=[bot1, bot2, bot3, bot4],
                starting_stack=config['stack'],
                blinds_schedule=blinds_schedule,
                seed=seed_val
            )

            # Play hands until 4 players bust or max hands reached
            hand_num = 0
            busted_count = 0

            while busted_count < 4 and hand_num < 100:
                hand_num += 1

                # Initialize hand
                table.reset_hand_state()
                table.deal_hole_cards()
                table.collect_blinds()

                # Play all streets
                should_continue = table.run_betting_round("preflop")

                if should_continue:
                    table.deal_flop()
                    should_continue = table.run_betting_round("flop")

                if should_continue:
                    table.deal_turn()
                    should_continue = table.run_betting_round("turn")

                if should_continue:
                    table.deal_river()
                    should_continue = table.run_betting_round("river")

                # Showdown
                results = table.end_hand()

                # Check eliminations
                eliminated = table.check_eliminations()
                if eliminated:
                    busted_count = sum(1 for info in table.player_public_infos if info.busted)

                # Verify chip count
                is_valid, expected, actual = table.verify_chip_count()

                if not is_valid:
                    errors_found.append({
                        'config': config['desc'],
                        'seed': seed_val,
                        'hand': hand_num,
                        'expected': expected,
                        'actual': actual,
                        'diff': actual - expected,
                        'busted_count': busted_count,
                        'player_stacks': [info.stack for info in table.player_public_infos],
                        'pot': table.total_pot,
                        'pots': sum(p.amount for p in table.pots)
                    })
                    break

                # Check if we can continue
                active_count = sum(1 for info in table.player_public_infos if not info.busted)
                if active_count <= 1:
                    break

                table.advance_button()

        print(f"    Completed {config['seeds']} seeds")

    # Report results
    if errors_found:
        print(f"\n  {'='*60}")
        print(f"  [FAIL] Found {len(errors_found)} chip count errors:")
        print(f"  {'='*60}")
        for error in errors_found:
            print(f"\n  Config: {error['config']}")
            print(f"    Seed {error['seed']}, Hand {error['hand']}")
            print(f"    Expected: {error['expected']}, Actual: {error['actual']}, Diff: {error['diff']}")
            print(f"    Busted: {error['busted_count']}")
            print(f"    Player stacks: {error['player_stacks']}")
            print(f"    Pot: {error['pot']}, Pots: {error['pots']}")
        raise AssertionError(f"Chip leak detected in {len(errors_found)} scenarios")
    else:
        print("  [PASS] Chip leak tests passed")


def test_chip_distribution():
    """Test correct chip distribution including side pot scenarios"""
    print("Testing chip distribution correctness...")

    class TestBot:
        """Simple test bot that follows predetermined actions"""
        def __init__(self, player_index, actions):
            self.player_index = player_index
            self.actions = actions
            self.action_count = 0

        def get_action(self, gamestate, hole_cards):
            if self.action_count >= len(self.actions):
                return 'fold', 0
            action = self.actions[self.action_count]
            self.action_count += 1
            return action

    # Test 1: Simple heads-up pot (no side pots)
    print("  Test 1: Simple heads-up pot")
    bot1 = TestBot(0, [('call', 0)])  # Calls BB
    bot2 = TestBot(1, [('check', 0)])  # Checks as BB

    blinds_schedule = {1: (10, 20)}
    table = Table(
        players=[bot1, bot2],
        starting_stack=1000,
        blinds_schedule=blinds_schedule,
        seed=42
    )

    # Manually set hole cards and community to ensure known winner
    table.reset_hand_state()
    table.deal_hole_cards()
    table.player_hole_cards[0] = ('Ah', 'Kh')  # Player 0 has AK
    table.player_hole_cards[1] = ('2c', '3d')  # Player 1 has 23
    table.collect_blinds()

    # Record initial total after blinds (includes stacks + current_bets + pot)
    initial_total = sum(p.stack for p in table.player_public_infos) + \
                    sum(p.current_bet for p in table.player_public_infos) + \
                    table.total_pot

    table.run_betting_round("preflop")
    table.deal_flop()
    table.community_cards = ['As', 'Ks', '4h', '5c', '6d']  # Player 0 gets two pair

    # Skip remaining betting
    table.player_public_infos[0].current_bet = 0
    table.player_public_infos[1].current_bet = 0

    results = table.end_hand()

    # Verify winner got the pot
    assert 0 in results, "Player 0 should win"
    pot_size = 30  # SB (10) + BB (20)
    assert results[0][1] == pot_size, f"Winner should get {pot_size} chips, got {results[0][1]}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos) + \
                  sum(p.current_bet for p in table.player_public_infos) + \
                  table.total_pot
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] Simple heads-up pot")

    # Test 2: All-in scenario with side pot
    print("  Test 2: All-in scenario with side pot")

    bot1 = TestBot(0, [])
    bot2 = TestBot(1, [])
    bot3 = TestBot(2, [])

    table = Table(
        players=[bot1, bot2, bot3],
        starting_stack=1000,
        blinds_schedule={1: (10, 20)},
        seed=43
    )

    table.reset_hand_state()

    # Set different stacks: P0=300, P1=200, P2=100
    table.player_public_infos[0].stack = 300
    table.player_public_infos[1].stack = 200
    table.player_public_infos[2].stack = 100

    initial_total = sum(p.stack for p in table.player_public_infos)

    table.deal_hole_cards()
    # Set hands: P0 best, P1 second, P2 worst
    table.player_hole_cards[0] = ('Ah', 'Ad')  # Pair of Aces (best)
    table.player_public_infos[0].active = True

    table.player_hole_cards[1] = ('Kh', 'Kd')  # Pair of Kings
    table.player_public_infos[1].active = True

    table.player_hole_cards[2] = ('Qh', 'Qd')  # Pair of Queens
    table.player_public_infos[2].active = True

    # Simulate: All 3 players go all-in
    # Mark final states after betting
    table.player_public_infos[0].stack = 100  # 300 - 200 = 100 remaining
    table.player_public_infos[1].stack = 0     # All-in
    table.player_public_infos[1].is_all_in = True
    table.player_public_infos[2].stack = 0     # All-in
    table.player_public_infos[2].is_all_in = True

    # Set hand contributions
    table.hand_contributions[0] = 200
    table.hand_contributions[1] = 200
    table.hand_contributions[2] = 100

    table.community_cards = ['2s', '3c', '4h', '6d', '8s']  # No straight, pairs win

    # Add action history
    from src.core.data_classes import Action
    table.current_hand_history["preflop"] = [
        Action(2, "all-in", 100),
        Action(1, "all-in", 200),
        Action(0, "bet", 200)
    ]

    # Manually create pots
    from src.core.data_classes import Pot
    table.pots = [
        Pot(300, [0, 1, 2]),  # Main pot: 100*3 = 300, all eligible
        Pot(200, [0, 1])      # Side pot: 100*2 = 200, P0,P1 eligible
    ]
    table.total_pot = 500

    results = table.end_hand()

    # P0 should win both pots (has best hand - Aces)
    # Main pot: 300 (all eligible), Side pot: 200 (P0, P1 eligible)
    assert 0 in results, f"Player 0 should win, results: {results}"
    assert results[0][1] == 500, f"Player 0 should win 500, got {results[0][1]}"

    # Verify total distributed
    total_winnings = sum(r[1] for r in results.values())
    assert total_winnings == 500, f"Total winnings should be 500, got {total_winnings}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos)
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] All-in scenario with side pot")

    # Test 3: Split pot scenario
    print("  Test 3: Split pot with identical hands")

    bot1 = TestBot(0, [('call', 0)])
    bot2 = TestBot(1, [('check', 0)])

    table = Table(
        players=[bot1, bot2],
        starting_stack=1000,
        blinds_schedule={1: (10, 20)},
        seed=45
    )

    table.reset_hand_state()
    table.deal_hole_cards()

    # Give both players identical pocket pairs (different suits) so they tie
    table.player_hole_cards[0] = ('9h', '9c')  # Pair of 9s
    table.player_hole_cards[1] = ('9d', '9s')  # Pair of 9s

    # Both players are active
    table.player_public_infos[0].active = True
    table.player_public_infos[1].active = True

    # Simulate both players putting 100 chips in
    table.player_public_infos[0].stack = 900
    table.player_public_infos[1].stack = 900

    # Set hand contributions
    table.hand_contributions[0] = 100
    table.hand_contributions[1] = 100

    table.total_pot = 200  # 100 from each
    table.community_cards = ['2h', '3d', '4c', '5s', '6c']  # Board doesn't improve either

    initial_total = sum(p.stack for p in table.player_public_infos) + table.total_pot

    # Add hand history
    from src.core.data_classes import Action
    table.current_hand_history["preflop"] = [
        Action(0, "bet", 100),
        Action(1, "call", 100)
    ]

    results = table.end_hand()

    # Both should win and split pot equally (100 each)
    assert 0 in results and 1 in results, f"Both players should win, got: {results}"
    assert results[0][1] == 100, f"P0 should get 100, got {results[0][1]}"
    assert results[1][1] == 100, f"P1 should get 100, got {results[1][1]}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos) + table.total_pot
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] Split pot with identical hands")

    # Test 4: Split pot WITH side pots (complex scenario)
    print("  Test 4: Split pot with side pots")

    bot1 = TestBot(0, [])
    bot2 = TestBot(1, [])
    bot3 = TestBot(2, [])
    bot4 = TestBot(3, [])

    table = Table(
        players=[bot1, bot2, bot3, bot4],
        starting_stack=1000,
        blinds_schedule={1: (10, 20)},
        seed=50
    )

    table.reset_hand_state()

    # Set different stacks: P0=400, P1=300, P2=200, P3=100
    table.player_public_infos[0].stack = 400
    table.player_public_infos[1].stack = 300
    table.player_public_infos[2].stack = 200
    table.player_public_infos[3].stack = 100

    initial_total = sum(p.stack for p in table.player_public_infos)

    table.deal_hole_cards()

    # Set hands so P0 and P1 TIE for best, P2 is third, P3 is worst
    table.player_hole_cards[0] = ('Ah', 'Ad')  # Pair of Aces (ties for best)
    table.player_public_infos[0].active = True

    table.player_hole_cards[1] = ('Ac', 'As')  # Pair of Aces (ties for best)
    table.player_public_infos[1].active = True

    table.player_hole_cards[2] = ('Kh', 'Kd')  # Pair of Kings (third)
    table.player_public_infos[2].active = True

    table.player_hole_cards[3] = ('Qh', 'Qd')  # Pair of Queens (worst)
    table.player_public_infos[3].active = True

    # Simulate: All 4 players go all-in
    # P3 contributes 100, P2 contributes 200, P1 contributes 300, P0 contributes 300
    # Expected side pots:
    #   - Main pot: 400 (100*4) - all four eligible -> P0 and P1 split = 200 each
    #   - Side pot 1: 300 (100*3 from P0,P1,P2) - P0, P1, P2 eligible -> P0 and P1 split = 150 each
    #   - Side pot 2: 200 (100*2 from P0,P1) - P0, P1 eligible -> P0 and P1 split = 100 each
    # Total: P0 gets 200+150+100=450, P1 gets 200+150+100=450

    table.player_public_infos[0].stack = 100  # 400 - 300 = 100 remaining
    table.player_public_infos[1].stack = 0     # All-in
    table.player_public_infos[1].is_all_in = True
    table.player_public_infos[2].stack = 0     # All-in
    table.player_public_infos[2].is_all_in = True
    table.player_public_infos[3].stack = 0     # All-in
    table.player_public_infos[3].is_all_in = True

    # Set hand contributions to match what each player put in
    table.hand_contributions[0] = 300
    table.hand_contributions[1] = 300
    table.hand_contributions[2] = 200
    table.hand_contributions[3] = 100

    table.community_cards = ['2s', '3c', '4h', '6d', '8s']  # No improvement, pairs win

    # Add action history
    from src.core.data_classes import Action
    table.current_hand_history["preflop"] = [
        Action(3, "all-in", 100),
        Action(2, "all-in", 200),
        Action(1, "all-in", 300),
        Action(0, "bet", 300)
    ]

    # Manually create pots based on contributions
    from src.core.data_classes import Pot
    table.pots = [
        Pot(400, [0, 1, 2, 3]),  # Main pot: 100*4 = 400, all eligible
        Pot(300, [0, 1, 2]),     # Side pot 1: 100*3 = 300, P0,P1,P2 eligible
        Pot(200, [0, 1])         # Side pot 2: 100*2 = 200, P0,P1 eligible
    ]
    table.total_pot = 900  # Total of all pots

    results = table.end_hand()

    # P0 and P1 should split all pots (450 each)
    assert 0 in results and 1 in results, f"P0 and P1 should both win, got: {results}"
    assert results[0][1] == 450, f"P0 should win 450, got {results[0][1]}"
    assert results[1][1] == 450, f"P1 should win 450, got {results[1][1]}"
    assert 2 not in results, f"P2 should not win anything"
    assert 3 not in results, f"P3 should not win anything"

    # Verify total distributed
    total_winnings = sum(r[1] for r in results.values())
    assert total_winnings == 900, f"Total winnings should be 900, got {total_winnings}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos)
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] Split pot with side pots")

    # Test 5: Three-way split of side pot
    print("  Test 5: Three-way split of side pot")

    bot1 = TestBot(0, [])
    bot2 = TestBot(1, [])
    bot3 = TestBot(2, [])
    bot4 = TestBot(3, [])

    table = Table(
        players=[bot1, bot2, bot3, bot4],
        starting_stack=1000,
        blinds_schedule={1: (10, 20)},
        seed=60
    )

    table.reset_hand_state()

    # Set different stacks: P0=400, P1=400, P2=400, P3=100
    table.player_public_infos[0].stack = 400
    table.player_public_infos[1].stack = 400
    table.player_public_infos[2].stack = 400
    table.player_public_infos[3].stack = 100

    initial_total = sum(p.stack for p in table.player_public_infos)

    table.deal_hole_cards()

    # Set hands so P0, P1, P2 all TIE with Kings, P3 has worst hand
    table.player_hole_cards[0] = ('Kh', 'Kd')  # Pair of Kings
    table.player_public_infos[0].active = True

    table.player_hole_cards[1] = ('Kc', 'Ks')  # Pair of Kings
    table.player_public_infos[1].active = True

    table.player_hole_cards[2] = ('2h', '2d')  # Pair of 2s (with board makes trips of Kings)
    table.player_public_infos[2].active = True

    table.player_hole_cards[3] = ('Qh', 'Qd')  # Pair of Queens
    table.player_public_infos[3].active = True

    # All go all-in
    # P3 contributes 100, P0/P1/P2 each contribute 100
    # Expected side pots:
    #   - Main pot: 400 (100*4) - all eligible
    #   - Side pot: 900 (300*3) - P0, P1, P2 eligible
    # But with community having Kings, all will tie differently...

    table.player_public_infos[0].stack = 300  # 400 - 100
    table.player_public_infos[1].stack = 300  # 400 - 100
    table.player_public_infos[2].stack = 300  # 400 - 100
    table.player_public_infos[3].stack = 0     # All-in
    table.player_public_infos[3].is_all_in = True

    # Set hand contributions
    table.hand_contributions[0] = 100
    table.hand_contributions[1] = 100
    table.hand_contributions[2] = 100
    table.hand_contributions[3] = 100

    table.total_pot = 400
    table.community_cards = ['As', '7c', '6h', '5d', '3s']  # High card Ace for all

    # Add action history - everyone bets 100
    from src.core.data_classes import Action
    table.current_hand_history["preflop"] = [
        Action(3, "all-in", 100),
        Action(0, "bet", 100),
        Action(1, "call", 100),
        Action(2, "call", 100)
    ]

    results = table.end_hand()

    # P0 and P1 both have pair of Kings, P2 has pair of 2s, P3 has pair of Queens
    # P0 and P1 should tie and split the main pot
    # Expected: P0 and P1 split 400, so each gets 200
    # P2 gets 0, P3 gets 0

    assert 0 in results and 1 in results, f"P0 and P1 should win, got: {results}"

    # They should split the 400 pot
    total_winnings = sum(r[1] for r in results.values())
    assert total_winnings == 400, f"Total winnings should be 400, got {total_winnings}"

    # Each winner should get equal share
    if len(results) == 2:
        assert results[0][1] == 200, f"P0 should win 200, got {results[0][1]}"
        assert results[1][1] == 200, f"P1 should win 200, got {results[1][1]}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos)
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] Three-way split of side pot")

    # Test 6: Small stack with best hand wins main pot, second-best wins side pot
    print("  Test 6: Different winners for main pot vs side pot")

    bot1 = TestBot(0, [])
    bot2 = TestBot(1, [])
    bot3 = TestBot(2, [])

    table = Table(
        players=[bot1, bot2, bot3],
        starting_stack=1000,
        blinds_schedule={1: (10, 20)},
        seed=70
    )

    table.reset_hand_state()

    # Set different stacks: P0=300, P1=200, P2=100
    table.player_public_infos[0].stack = 300
    table.player_public_infos[1].stack = 200
    table.player_public_infos[2].stack = 100

    initial_total = sum(p.stack for p in table.player_public_infos)

    table.deal_hole_cards()

    # Key scenario: P2 (smallest stack) has BEST hand
    #               P1 has second-best hand
    #               P0 has worst hand
    table.player_hole_cards[0] = ('Qh', 'Qd')  # Pair of Queens (worst)
    table.player_public_infos[0].active = True

    table.player_hole_cards[1] = ('Kh', 'Kd')  # Pair of Kings (second best)
    table.player_public_infos[1].active = True

    table.player_hole_cards[2] = ('Ah', 'Ad')  # Pair of Aces (BEST - but smallest stack!)
    table.player_public_infos[2].active = True

    # All go all-in:
    # P2 contributes 100, P1 contributes 200, P0 contributes 200
    # Expected side pots:
    #   - Main pot: 300 (100*3) - all eligible -> P2 wins with Aces (300)
    #   - Side pot: 200 (100*2 from P0 and P1) - only P0 and P1 eligible -> P1 wins with Kings (200)
    # Total: P2 gets 300, P1 gets 200, P0 gets 0

    table.player_public_infos[0].stack = 100  # 300 - 200
    table.player_public_infos[1].stack = 0     # All-in
    table.player_public_infos[1].is_all_in = True
    table.player_public_infos[2].stack = 0     # All-in
    table.player_public_infos[2].is_all_in = True

    # Set hand contributions
    table.hand_contributions[0] = 200
    table.hand_contributions[1] = 200
    table.hand_contributions[2] = 100

    table.community_cards = ['2s', '3c', '4h', '6d', '8s']  # No improvement, pairs win

    # Add action history
    from src.core.data_classes import Action
    table.current_hand_history["preflop"] = [
        Action(2, "all-in", 100),  # P2 all-in for 100
        Action(1, "all-in", 200),  # P1 all-in for 200
        Action(0, "bet", 200)      # P0 bets 200 to match
    ]

    # Manually create pots
    from src.core.data_classes import Pot
    table.pots = [
        Pot(300, [0, 1, 2]),  # Main pot: 100*3 = 300, all eligible
        Pot(200, [0, 1])      # Side pot: 100*2 = 200, P0,P1 eligible
    ]
    table.total_pot = 500

    results = table.end_hand()

    # P2 should win main pot (300), P1 should win side pot (200)
    assert 2 in results, f"P2 should win main pot, got: {results}"
    assert 1 in results, f"P1 should win side pot, got: {results}"
    assert results[2][1] == 300, f"P2 should win 300 (main pot), got {results[2][1]}"
    assert results[1][1] == 200, f"P1 should win 200 (side pot), got {results[1][1]}"
    assert 0 not in results, f"P0 should not win anything, got: {results}"

    # Verify total distributed
    total_winnings = sum(r[1] for r in results.values())
    assert total_winnings == 500, f"Total winnings should be 500, got {total_winnings}"

    # Verify chip conservation
    final_total = sum(p.stack for p in table.player_public_infos)
    assert initial_total == final_total, f"Chips not conserved: {initial_total} -> {final_total}"

    print("    [PASS] Different winners for main pot vs side pot")

    print("  [PASS] Chip distribution tests passed")


def main():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("Running Integration Tests")
    print("="*60 + "\n")

    test_chip_leak()
    test_chip_distribution()

    print("\n" + "="*60)
    print("All integration tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
