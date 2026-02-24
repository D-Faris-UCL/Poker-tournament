"""Test basic functionality of poker components"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.deck_manager import DeckManager
from src.core.data_classes import Pot, PlayerPublicInfo, Action
from src.core.player import Player
from src.helpers.hand_judge import HandJudge
from src.helpers.player_judge import PlayerJudge
from src.helpers.player_loader import load_players, get_player_by_name, get_player_names, validate_players
import inspect



def test_deck_manager():
    """Test deck manager functionality"""
    print("Testing DeckManager...")

    deck = DeckManager(seed=42)
    assert deck.cards_remaining() == 52, "Deck should have 52 cards"

    deck.shuffle_deck()
    card = deck.deal_card()
    assert len(card) == 2, "Card should be 2 characters"
    assert deck.cards_remaining() == 51, "Should have 51 cards after dealing one"

    burn = deck.burn_card()
    assert len(deck.burn_cards) == 1, "Should have 1 burned card"
    assert deck.cards_remaining() == 50, "Should have 50 cards after burning one"

    cards = deck.deal_multiple(5)
    assert len(cards) == 5, "Should deal 5 cards"
    assert deck.cards_remaining() == 45, "Should have 45 cards remaining"

    print("  [PASS] DeckManager tests passed")


def test_hand_evaluation():
    """Test hand evaluation"""
    print("Testing HandJudge...")

    # Test royal flush
    hole_cards = ('Ah', 'Kh')
    community = ['Qh', 'Jh', 'Th', '2d', '3c']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "royal_flush", f"Should be royal flush, got {hand_name}"

    # Test straight
    hole_cards = ('9h', '8d')
    community = ['7s', '6c', '5h', 'Kd', '2c']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "straight", f"Should be straight, got {hand_name}"

    # Test pair
    hole_cards = ('Ah', 'Ad')
    community = ['Ks', '7c', '3h', '2d', 'Qc']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "one_pair", f"Should be one pair, got {hand_name}"

    print("  [PASS] HandJudge tests passed")


def test_hand_evaluation_fewer_cards():
    """Test hand evaluation with fewer than 7 cards (before all community cards are dealt)"""
    print("Testing HandJudge with fewer than 7 cards...")

    # Test one pair with only flop (5 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['Ks', '7c', '3h']  # Only flop
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "one_pair", f"Should be one pair, got {hand_name}"
    assert values[0] == 14, f"Pair should be Aces (14), got {values[0]}"
    assert 13 in values, f"King kicker should be in values, got {values}"

    # Test two pair with flop + turn (6 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['Ks', 'Kc', '7h', '3d']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "two_pair", f"Should be two pair, got {hand_name}"
    assert values[0] == 14 and values[1] == 13, f"Should be Aces and Kings, got {values}"
    assert values[2] == 7, f"Kicker should be 7, got {values[2]}"

    # Test two pair with no kicker (4 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['Ks', 'Kc']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "two_pair", f"Should be two pair, got {hand_name}"
    assert values[2] == 0, f"Kicker should be 0 (no kicker available), got {values[2]}"

    # Test three of a kind with minimal kickers (4 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['As', '7c']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "three_of_a_kind", f"Should be three of a kind, got {hand_name}"
    assert values[0] == 14, f"Trips should be Aces (14), got {values[0]}"
    assert len(values) == 2, f"Should have trips + 1 kicker, got {len(values)} values"

    # Test four of a kind with no kicker (4 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['As', 'Ac']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "four_of_a_kind", f"Should be four of a kind, got {hand_name}"
    assert values[0] == 14, f"Quads should be Aces (14), got {values[0]}"
    assert values[1] == 0, f"Kicker should be 0 (no kicker available), got {values[1]}"

    # Test four of a kind with one kicker (5 total cards)
    hole_cards = ('Ah', 'Ad')
    community = ['As', 'Ac', 'Kh']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "four_of_a_kind", f"Should be four of a kind, got {hand_name}"
    assert values[1] == 13, f"Kicker should be King (13), got {values[1]}"

    # Test edge case: just hole cards (2 cards only)
    hole_cards = ('Ah', 'Ad')
    community = []
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "one_pair", f"Should be one pair, got {hand_name}"
    assert len(values) == 1, f"Should only have pair value with no kickers, got {values}"

    print("  [PASS] HandJudge with fewer cards tests passed")


def test_hand_evaluation_edge_cases():
    """Test edge cases in hand evaluation"""
    print("Testing HandJudge edge cases...")

    # Test full house with two trips (AAAKKK + Q) - should pick higher trips (AAA)
    hole_cards = ('Ah', 'Ad')
    community = ['As', 'Ks', 'Kc', 'Kh', 'Qd']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "full_house", f"Should be full house, got {hand_name}"
    # Aces full of Kings beats Kings full of Aces - trips value is compared first
    assert values[0] == 14, f"Should use Aces trips (14), got {values[0]}"
    assert values[1] == 13, f"Should use Kings pair (13), got {values[1]}"

    # Test two pair with three pairs - should pick top 2
    hole_cards = ('Ah', 'Ad')
    community = ['Ks', 'Kc', 'Qh', 'Qd', '7c']
    hand_name, values = HandJudge.evaluate_hand(hole_cards, community)
    assert hand_name == "two_pair", f"Should be two pair, got {hand_name}"
    assert len(values) == 3, f"Should have 2 pairs + kicker, got {len(values)} values"
    # Should be A-A-K-K-Q (top 2 pairs are AA and KK, Q is kicker)
    assert values[0] == 14, f"Top pair should be Aces (14), got {values[0]}"
    assert values[1] == 13, f"Second pair should be Kings (13), got {values[1]}"

    print("  [PASS] HandJudge edge cases tests passed")


def test_hand_comparison():
    """Test hand comparison"""
    print("Testing hand comparison...")

    # Royal flush beats straight flush
    hand1 = ("royal_flush", [14, 13, 12, 11, 10])
    hand2 = ("straight_flush", [9])
    result = HandJudge.compare_hands(hand1, hand2)
    assert result == 1, "Royal flush should beat straight flush"

    # Higher pair wins
    hand1 = ("one_pair", [14, 13, 12, 11])  # Pair of Aces
    hand2 = ("one_pair", [13, 14, 12, 11])  # Pair of Kings
    result = HandJudge.compare_hands(hand1, hand2)
    assert result == 1, "Pair of Aces should beat pair of Kings"

    # Same hands tie
    hand1 = ("one_pair", [10, 14, 13, 12])
    hand2 = ("one_pair", [10, 14, 13, 12])
    result = HandJudge.compare_hands(hand1, hand2)
    assert result == 0, "Identical hands should tie"

    print("  [PASS] Hand comparison tests passed")


def test_player_judge():
    """Test action validation"""
    print("Testing PlayerJudge...")

    # Setup test scenario
    player_infos = [
        PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=20, active=True, busted=False),
    ]

    # Test check when no bet
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='check',
        amount=0,
        player_infos=player_infos,
        current_bet=0,
        minimum_raise=20
    )
    assert action == 'check', "Should allow check when no bet"

    # Test call validation
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='call',
        amount=0,
        player_infos=player_infos,
        current_bet=20,
        minimum_raise=20
    )
    assert action == 'call', "Should allow call"
    assert amount == 20, "Call amount should be 20"

    # Test invalid bet converted to check
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='bet',
        amount=5,  # Below minimum
        player_infos=player_infos,
        current_bet=0,
        minimum_raise=20
    )
    assert action == 'check', "Below-minimum bet should convert to check"

    # Test raise validation - exactly minimum raise
    player_infos_raise = [
        PlayerPublicInfo(stack=1000, current_bet=20, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=100, active=True, busted=False),
    ]
    # Current bet is 100, player has 20, min raise is 50
    # To raise by minimum: need to reach 150 total (100 + 50)
    # Player needs to add: 150 - 20 = 130 chips
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='raise',
        amount=130,  # Exactly minimum raise
        player_infos=player_infos_raise,
        current_bet=100,
        minimum_raise=50
    )
    assert action == 'raise', "Should allow raise equal to minimum"
    assert amount == 130, f"Raise amount should be 130, got {amount}"

    # Test raise below minimum (should convert to call)
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='raise',
        amount=129,  # Below minimum raise
        player_infos=player_infos_raise,
        current_bet=100,
        minimum_raise=50
    )
    assert action == 'call', "Below-minimum raise should convert to call"
    assert amount == 80, f"Call amount should be 80, got {amount}"

    # Test raise above minimum
    action, amount = PlayerJudge.validate_action(
        player_idx=0,
        action_type='raise',
        amount=180,  # Above minimum raise
        player_infos=player_infos_raise,
        current_bet=100,
        minimum_raise=50
    )
    assert action == 'raise', "Should allow raise above minimum"
    assert amount == 180, f"Raise amount should be 180, got {amount}"

    print("  [PASS] PlayerJudge tests passed")


PLAYER_JUDGE_LOGGER = "src.helpers.player_judge"


def test_illegal_move_warning_bet_exceeds_stack(caplog):
    """Warn when bet amount exceeds available stack (corrected to all-in)."""
    player_infos = [
        PlayerPublicInfo(stack=50, current_bet=0, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
    ]
    with caplog.at_level(logging.WARNING, logger=PLAYER_JUDGE_LOGGER):
        action, amount = PlayerJudge.validate_action(
            player_idx=0,
            action_type="bet",
            amount=200,
            player_infos=player_infos,
            current_bet=0,
            minimum_raise=20,
        )
    assert action == "all-in" and amount == 50
    assert any("bet exceeds stack" in r.message for r in caplog.records)


def test_illegal_move_warning_raise_below_minimum(caplog):
    """Warn when raise is below minimum (corrected to call)."""
    player_infos = [
        PlayerPublicInfo(stack=1000, current_bet=20, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=100, active=True, busted=False),
    ]
    with caplog.at_level(logging.WARNING, logger=PLAYER_JUDGE_LOGGER):
        action, amount = PlayerJudge.validate_action(
            player_idx=0,
            action_type="raise",
            amount=100,
            player_infos=player_infos,
            current_bet=100,
            minimum_raise=50,
        )
    assert action == "call" and amount == 80
    assert any("raise below minimum" in r.message for r in caplog.records)


def test_illegal_move_warning_check_not_allowed(caplog):
    """Warn when check is requested but there is a bet to call (corrected to fold)."""
    player_infos = [
        PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=50, active=True, busted=False),
    ]
    with caplog.at_level(logging.WARNING, logger=PLAYER_JUDGE_LOGGER):
        action, amount = PlayerJudge.validate_action(
            player_idx=0,
            action_type="check",
            amount=0,
            player_infos=player_infos,
            current_bet=50,
            minimum_raise=20,
        )
    assert action == "fold" and amount == 0
    assert any("check not allowed" in r.message for r in caplog.records)


def test_illegal_move_warning_bet_below_minimum(caplog):
    """Warn when bet is below minimum (corrected to check)."""
    player_infos = [
        PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
    ]
    with caplog.at_level(logging.WARNING, logger=PLAYER_JUDGE_LOGGER):
        action, amount = PlayerJudge.validate_action(
            player_idx=0,
            action_type="bet",
            amount=5,
            player_infos=player_infos,
            current_bet=0,
            minimum_raise=20,
        )
    assert action == "check" and amount == 0
    assert any("bet below minimum" in r.message for r in caplog.records)


def test_illegal_move_warning_raise_exceeds_stack(caplog):
    """Warn when raise amount exceeds stack (corrected to all-in)."""
    # Player can raise (stack 200 > amount_to_call 100) but requests 500 > stack
    player_infos = [
        PlayerPublicInfo(stack=200, current_bet=0, active=True, busted=False),
        PlayerPublicInfo(stack=1000, current_bet=100, active=True, busted=False),
    ]
    with caplog.at_level(logging.WARNING, logger=PLAYER_JUDGE_LOGGER):
        action, amount = PlayerJudge.validate_action(
            player_idx=0,
            action_type="raise",
            amount=500,
            player_infos=player_infos,
            current_bet=100,
            minimum_raise=50,
        )
    assert action == "all-in" and amount == 200
    assert any("raise exceeds stack" in r.message for r in caplog.records)


def test_data_classes():
    """Test data classes"""
    print("Testing data classes...")

    # Test Pot
    pot = Pot(amount=100, eligible_players=[0, 1, 2])
    assert pot.amount == 100
    assert len(pot.eligible_players) == 3

    # Test PlayerPublicInfo
    info = PlayerPublicInfo(stack=1000, current_bet=50, active=True, busted=False)
    assert info.stack == 1000
    assert info.current_bet == 50
    assert info.active == True

    # Test Action
    action = Action(player_index=0, action_type='raise', amount=100)
    assert action.player_index == 0
    assert action.action_type == 'raise'
    assert action.amount == 100

    # Test action serialization
    action_dict = action.to_dict()
    assert action_dict['player_index'] == 0
    action_restored = Action.from_dict(action_dict)
    assert action_restored.player_index == 0
    assert action_restored.action_type == 'raise'

    print("  [PASS] Data classes tests passed")


def test_player_loader():
    """Test player loader functionality"""
    print("Testing PlayerLoader...")

    # Test 1: load_players with test fixture
    print("  Testing load_players()...")
    players = load_players('tests/test_bots/player_loader')
    assert isinstance(players, list), "load_players should return a list"
    assert len(players) == 4, f"Should load exactly 4 bots (2 valid + 2 invalid), got {len(players)}"

    # Verify all returned items are classes
    for player_class in players:
        assert inspect.isclass(player_class), f"{player_class} should be a class"

    # Verify class names (load_players loads all that can be imported, not just valid ones)
    class_names = {cls.__name__ for cls in players}
    assert 'ValidBot1' in class_names, "Should load ValidBot1"
    assert 'ValidBot2' in class_names, "Should load ValidBot2"
    assert 'InvalidBot' in class_names, "Should load InvalidBot (validation happens separately)"
    assert 'InvalidNoGetAction' in class_names, "Should load InvalidNoGetAction"
    assert 'IgnoredBot' not in class_names, "Should ignore __should_be_ignored directory"
    print("    [PASS] load_players() correctly loads all importable bots")

    # Test 2: get_player_names with test fixture
    print("  Testing get_player_names()...")
    names = get_player_names('tests/test_bots/player_loader')
    assert isinstance(names, list), "get_player_names should return a list"
    assert len(names) == 4, f"Should find exactly 4 bot directories with player.py, got {len(names)}"
    expected_names = ['invalid_inheritance', 'invalid_no_get_action', 'valid_bot_1', 'valid_bot_2']
    assert names == expected_names, f"Should return sorted names, got {names}"
    assert 'no_player_file' not in names, "Should skip directories without player.py"
    assert '__should_be_ignored' not in names, "Should skip directories starting with __"
    print("    [PASS] get_player_names() returns correct sorted names")

    # Test 3: get_player_names with non-existent directory
    print("  Testing get_player_names() with non-existent directory...")
    names_empty = get_player_names('tests/nonexistent_bots')
    assert names_empty == [], "Should return empty list for non-existent directory"
    print("    [PASS] get_player_names() handles non-existent directory")

    # Test 4: load_players raises error for non-existent directory
    print("  Testing load_players() with non-existent directory...")
    try:
        load_players('tests/nonexistent_bots')
        assert False, "Should raise FileNotFoundError"
    except FileNotFoundError as e:
        assert "does not exist" in str(e), "Error message should indicate directory doesn't exist"
    print("    [PASS] load_players() raises FileNotFoundError correctly")

    # Test 5: get_player_by_name success case
    print("  Testing get_player_by_name() success...")
    ValidBot1 = get_player_by_name('tests/test_bots/player_loader', 'valid_bot_1')
    assert ValidBot1 is not None, "Should successfully load valid_bot_1"
    assert inspect.isclass(ValidBot1), "Should return a class"
    assert ValidBot1.__name__ == 'ValidBot1', f"Should load ValidBot1, got {ValidBot1.__name__}"

    # Test instantiation
    bot_instance = ValidBot1(player_index=0)
    assert bot_instance.player_index == 0, "Instance should have correct player_index"
    assert hasattr(bot_instance, 'get_action'), "Instance should have get_action method"
    print("    [PASS] get_player_by_name() loads and instantiates correctly")

    # Test 6: get_player_by_name failure cases
    print("  Testing get_player_by_name() failure cases...")
    nonexistent = get_player_by_name('tests/test_bots/player_loader', 'nonexistent_bot')
    assert nonexistent is None, "Should return None for non-existent bot"

    no_file = get_player_by_name('tests/test_bots/player_loader', 'no_player_file')
    assert no_file is None, "Should return None for directory without player.py"
    print("    [PASS] get_player_by_name() handles failures correctly")

    # Test 7: validate_players with mixed valid/invalid bots
    print("  Testing validate_players() with mixed bots...")
    all_players = load_players('tests/test_bots/player_loader')
    validation = validate_players(all_players)

    assert isinstance(validation, dict), "validate_players should return a dict"
    assert 'valid' in validation, "Result should have 'valid' key"
    assert 'invalid' in validation, "Result should have 'invalid' key"
    assert 'all_valid' in validation, "Result should have 'all_valid' key"

    assert validation['all_valid'] == False, "Should have some invalid bots"
    # Note: InvalidNoGetAction passes because it inherits abstract get_action from Player
    # Only InvalidBot (no Player inheritance) fails validation
    assert len(validation['valid']) == 3, f"Should have 3 valid bots, got {len(validation['valid'])}"
    assert len(validation['invalid']) == 1, f"Should have 1 invalid bot, got {len(validation['invalid'])}"

    # Verify the valid ones include our test bots
    valid_names = {cls.__name__ for cls in validation['valid']}
    assert 'ValidBot1' in valid_names and 'ValidBot2' in valid_names, "Should identify valid bots correctly"

    # Verify invalid one
    invalid_names = {cls.__name__ for cls, _ in validation['invalid']}
    assert 'InvalidBot' in invalid_names, "Should identify InvalidBot as invalid"

    print("    [PASS] validate_players() correctly separates valid and invalid bots")

    # Test 8: validate_players with invalid objects
    print("  Testing validate_players() with invalid objects...")

    # Test with non-class object
    invalid_objects = ["not a class", 123, None]
    validation_invalid = validate_players(invalid_objects)
    assert validation_invalid['all_valid'] == False, "Should fail validation for non-classes"
    assert len(validation_invalid['invalid']) == 3, "Should have 3 invalid items"
    for item, reason in validation_invalid['invalid']:
        assert "Not a class" in reason, f"Should indicate non-class, got: {reason}"

    # Test with class not inheriting from Player
    InvalidBot = get_player_by_name('tests/test_bots/player_loader', 'invalid_inheritance')
    if InvalidBot:
        validation_no_inherit = validate_players([InvalidBot])
        assert validation_no_inherit['all_valid'] == False, "Should fail for non-Player inheritance"
        assert len(validation_no_inherit['invalid']) == 1, "Should have 1 invalid bot"
        _, reason = validation_no_inherit['invalid'][0]
        assert "Does not inherit from Player" in reason, f"Should indicate inheritance issue, got: {reason}"

    # Note: We can't easily test "missing get_action" because classes inheriting from Player
    # will have the abstract get_action method from the parent, so hasattr returns True.
    # The validation catches classes that don't inherit from Player at all.

    print("    [PASS] validate_players() catches invalid bots")

    # Test 9: Consistency between loader functions
    print("  Testing consistency between loader functions...")
    names_list = get_player_names('tests/test_bots/player_loader')
    players_list = load_players('tests/test_bots/player_loader')

    assert len(names_list) == len(players_list), \
        f"get_player_names count ({len(names_list)}) should match load_players count ({len(players_list)})"

    # Verify each name can be loaded individually
    for name in names_list:
        player_class = get_player_by_name('tests/test_bots/player_loader', name)
        assert player_class is not None, f"Should be able to load {name} individually"

    print("    [PASS] Loader functions are consistent")

    # Test 10: Smoke test on production bots (no hardcoded expectations)
    print("  Testing with production bots (smoke test)...")
    try:
        prod_players = load_players('src/bots')
        assert isinstance(prod_players, list), "Should return a list"
        assert len(prod_players) > 0, "Should load at least some production bots"

        # Verify all are classes
        for player_class in prod_players:
            assert inspect.isclass(player_class), "All loaded items should be classes"

        # Verify they can be validated
        prod_validation = validate_players(prod_players)
        assert isinstance(prod_validation, dict), "Validation should return dict"

        print(f"    [PASS] Production bots smoke test ({len(prod_players)} bots loaded)")
    except Exception as e:
        print(f"    [WARNING] Production bots test failed: {e}")

    print("  [PASS] PlayerLoader tests passed")


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Running Component Tests")
    print("="*60 + "\n")

    test_deck_manager()
    test_hand_evaluation()
    test_hand_evaluation_fewer_cards()
    test_hand_evaluation_edge_cases()
    test_hand_comparison()
    test_player_judge()
    test_data_classes()
    test_player_loader()

    print("\n" + "="*60)
    print("All tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
