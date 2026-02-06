"""Test basic functionality of poker components"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.deck_manager import DeckManager
from src.core.data_classes import SidePot, PlayerPublicInfo, Action
from src.helpers.hand_judge import HandJudge
from src.helpers.player_judge import PlayerJudge


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

    print("  [PASS] PlayerJudge tests passed")


def test_data_classes():
    """Test data classes"""
    print("Testing data classes...")

    # Test SidePot
    side_pot = SidePot(amount=100, eligible_players=[0, 1, 2])
    assert side_pot.amount == 100
    assert len(side_pot.eligible_players) == 3

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


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("Running Component Tests")
    print("="*60 + "\n")

    test_deck_manager()
    test_hand_evaluation()
    test_hand_comparison()
    test_player_judge()
    test_data_classes()

    print("\n" + "="*60)
    print("All tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
