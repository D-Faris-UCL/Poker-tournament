"""Hand evaluation and winner determination"""

from typing import List, Tuple, Dict, Optional
from collections import Counter


class HandJudge:
    """Evaluates poker hands and determines winners

    Determines hand rankings based on community cards and hole cards,
    then distributes pots to winners including side pots.
    """

    # Hand rankings (higher is better)
    HAND_RANKINGS = {
        "high_card": 1,
        "one_pair": 2,
        "two_pair": 3,
        "three_of_a_kind": 4,
        "straight": 5,
        "flush": 6,
        "full_house": 7,
        "four_of_a_kind": 8,
        "straight_flush": 9,
        "royal_flush": 10
    }

    # Card rank values for comparison
    RANK_VALUES = {
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
        '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14
    }

    @staticmethod
    def parse_card(card: str) -> Tuple[str, str]:
        """Parse card string into rank and suit

        Args:
            card: Card string like 'Ah' (Ace of hearts)

        Returns:
            Tuple of (rank, suit)
        """
        return card[0], card[1]

    @classmethod
    def evaluate_hand(
        cls,
        hole_cards: Tuple[str, str],
        community_cards: List[str]
    ) -> Tuple[str, List[int]]:
        """Evaluate best 5-card hand from 7 cards

        Args:
            hole_cards: Player's two hole cards
            community_cards: Five community cards

        Returns:
            Tuple of (hand_name, sorted_card_values) for comparison
            sorted_card_values: list of card values in descending order
        """
        all_cards = list(hole_cards) + community_cards

        # Parse all cards
        parsed_cards = [cls.parse_card(card) for card in all_cards]
        ranks = [rank for rank, _ in parsed_cards]
        suits = [suit for _, suit in parsed_cards]

        # Count ranks and suits
        rank_counts = Counter(ranks)
        suit_counts = Counter(suits)
        rank_values = [cls.RANK_VALUES[r] for r in ranks]

        # Check for flush
        is_flush = any(count >= 5 for count in suit_counts.values())
        flush_suit = None
        if is_flush:
            flush_suit = [suit for suit, count in suit_counts.items() if count >= 5][0]

        # Check for straight
        unique_values = sorted(set(rank_values), reverse=True)
        is_straight, straight_high = cls._check_straight(unique_values)

        # Determine hand type
        counts_sorted = sorted(rank_counts.values(), reverse=True)

        # Check for straight flush and royal flush
        if is_flush and flush_suit:
            # Get cards of flush suit
            flush_ranks = [cls.RANK_VALUES[r] for r, s in parsed_cards if s == flush_suit]
            flush_unique_values = sorted(set(flush_ranks), reverse=True)
            is_straight_flush, sf_high = cls._check_straight(flush_unique_values)

            if is_straight_flush:
                # Royal Flush check
                if set([14, 13, 12, 11, 10]).issubset(set(flush_unique_values)):
                    return "royal_flush", [14, 13, 12, 11, 10]
                # Straight Flush
                return "straight_flush", [sf_high]

        # Four of a Kind
        if counts_sorted[0] == 4:
            quad_rank = [r for r, c in rank_counts.items() if c == 4][0]
            kicker = max([cls.RANK_VALUES[r] for r, c in rank_counts.items() if c != 4])
            return "four_of_a_kind", [cls.RANK_VALUES[quad_rank], kicker]

        # Full House
        if counts_sorted[0] == 3 and counts_sorted[1] >= 2:
            trips_rank = [r for r, c in rank_counts.items() if c == 3][0]
            pair_rank = max([cls.RANK_VALUES[r] for r, c in rank_counts.items() if c >= 2 and r != trips_rank])
            return "full_house", [cls.RANK_VALUES[trips_rank], pair_rank]

        # Flush
        if is_flush:
            flush_suit = [suit for suit, count in suit_counts.items() if count >= 5][0]
            flush_values = sorted(
                [cls.RANK_VALUES[r] for r, s in parsed_cards if s == flush_suit],
                reverse=True
            )[:5]
            return "flush", flush_values

        # Straight
        if is_straight:
            return "straight", [straight_high]

        # Three of a Kind
        if counts_sorted[0] == 3:
            trips_rank = [r for r, c in rank_counts.items() if c == 3][0]
            kickers = sorted(
                [cls.RANK_VALUES[r] for r, c in rank_counts.items() if c != 3],
                reverse=True
            )[:2]
            return "three_of_a_kind", [cls.RANK_VALUES[trips_rank]] + kickers

        # Two Pair
        if counts_sorted[0] == 2 and counts_sorted[1] == 2:
            pairs = sorted([cls.RANK_VALUES[r] for r, c in rank_counts.items() if c == 2], reverse=True)
            kicker = max([cls.RANK_VALUES[r] for r, c in rank_counts.items() if c == 1])
            return "two_pair", pairs + [kicker]

        # One Pair
        if counts_sorted[0] == 2:
            pair_rank = [r for r, c in rank_counts.items() if c == 2][0]
            kickers = sorted(
                [cls.RANK_VALUES[r] for r, c in rank_counts.items() if c == 1],
                reverse=True
            )[:3]
            return "one_pair", [cls.RANK_VALUES[pair_rank]] + kickers

        # High Card
        high_cards = sorted(rank_values, reverse=True)[:5]
        return "high_card", high_cards

    @staticmethod
    def _check_straight(sorted_unique_values: List[int]) -> Tuple[bool, int]:
        """Check for straight in sorted unique card values

        Args:
            sorted_unique_values: Sorted unique card values (descending)

        Returns:
            Tuple of (is_straight, high_card_value)
        """
        # Check for regular straights
        for i in range(len(sorted_unique_values) - 4):
            if sorted_unique_values[i] - sorted_unique_values[i + 4] == 4:
                return True, sorted_unique_values[i]

        # Check for wheel (A-2-3-4-5)
        if set([14, 5, 4, 3, 2]).issubset(set(sorted_unique_values)):
            return True, 5  # In wheel, 5 is high card

        return False, 0

    @classmethod
    def compare_hands(
        cls,
        hand1: Tuple[str, List[int]],
        hand2: Tuple[str, List[int]]
    ) -> int:
        """Compare two hands

        Args:
            hand1: First hand (name, values)
            hand2: Second hand (name, values)

        Returns:
            1 if hand1 wins, -1 if hand2 wins, 0 if tie
        """
        rank1 = cls.HAND_RANKINGS[hand1[0]]
        rank2 = cls.HAND_RANKINGS[hand2[0]]

        if rank1 > rank2:
            return 1
        elif rank1 < rank2:
            return -1
        else:
            # Same hand type, compare values
            for v1, v2 in zip(hand1[1], hand2[1]):
                if v1 > v2:
                    return 1
                elif v1 < v2:
                    return -1
            return 0  # Exact tie

    @classmethod
    def determine_winners(
        cls,
        player_hole_cards: List[Optional[Tuple[str, str]]],
        community_cards: List[str],
        eligible_players: List[int]
    ) -> List[int]:
        """Determine winners from eligible players

        Args:
            player_hole_cards: All players' hole cards
            community_cards: Community cards
            eligible_players: Indices of players eligible for this pot

        Returns:
            List of winning player indices (multiple if tie)
        """
        if not eligible_players:
            return []

        # Evaluate hands for eligible players
        hands: Dict[int, Tuple[str, List[int]]] = {}
        for player_idx in eligible_players:
            if player_hole_cards[player_idx] is not None:
                hands[player_idx] = cls.evaluate_hand(
                    player_hole_cards[player_idx],
                    community_cards
                )

        if not hands:
            return []

        # Find best hand(s)
        best_hand = None
        winners = []

        for player_idx, hand in hands.items():
            if best_hand is None:
                best_hand = hand
                winners = [player_idx]
            else:
                comparison = cls.compare_hands(hand, best_hand)
                if comparison > 0:
                    best_hand = hand
                    winners = [player_idx]
                elif comparison == 0:
                    winners.append(player_idx)

        return winners

    @staticmethod
    def distribute_pot(
        pot_amount: int,
        winners: List[int],
        player_stacks: List[int]
    ) -> None:
        """Distribute pot to winners

        Args:
            pot_amount: Amount to distribute
            winners: List of winning player indices
            player_stacks: List of player stacks (modified in place)
        """
        if not winners:
            return

        share = pot_amount // len(winners)
        remainder = pot_amount % len(winners)

        for winner_idx in winners:
            player_stacks[winner_idx] += share

        # Give remainder to first winner (or could use button position logic)
        if remainder > 0:
            player_stacks[winners[0]] += remainder
