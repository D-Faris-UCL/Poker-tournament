"""
Monte Carlo Equity Calculator
==============================
Calibrated for the UCL tournament's 3-second decision budget.
Targets ~2.2s for equity computation, leaving ~0.8s for history
processing and decision logic.

Usage:
    calc = EquityCalculator()
    equity = calc.equity(hole_cards, community_cards, num_opponents=2, simulations=1500)
"""

import random
import time
from typing import Tuple, List
from src.helpers.hand_judge import HandJudge


RANKS = '23456789TJQKA'
SUITS = 'hdcs'
FULL_DECK = [r + s for r in RANKS for s in SUITS]

# Hand rank lookup — avoids re-parsing string on every comparison
HAND_RANK_INT = {
    'high_card': 0, 'one_pair': 1, 'two_pair': 2, 'three_of_a_kind': 3,
    'straight': 4, 'flush': 5, 'full_house': 6, 'four_of_a_kind': 7,
    'straight_flush': 8, 'royal_flush': 9,
}


class EquityCalculator:
    """
    Fast Monte Carlo equity estimator.

    Accuracy at 3-second budget (approximate):
      Preflop HU  1500 sims → ±1.0%
      Flop 3-way  700 sims  → ±1.5%
      Turn HU     800 sims  → ±1.2%
      River HU    500 sims  → ±1.5% (board complete, fast)

    Early exit: stops simulations if time_budget_ms exceeded mid-loop,
    returning best estimate so far. This prevents timeout on slow hardware.
    """

    def equity(
        self,
        hole_cards: Tuple[str, str],
        community_cards: List[str],
        num_opponents: int = 1,
        simulations: int = 1500,
        time_budget_ms: int = 2200,
    ) -> float:
        """
        Returns our estimated win probability [0.0, 1.0].

        UCL tournament allows 3 seconds per decision. We target ~2.2s for
        equity calculation, leaving ~0.8s for history processing and logic.

        Args:
            hole_cards:      Our two hole cards e.g. ('Ah', 'Kd')
            community_cards: 0-5 board cards
            num_opponents:   Number of active opponents (active_count - 1)
            simulations:     Monte Carlo iterations
            time_budget_ms:  Hard cutoff — returns early if exceeded
        """
        n_community = len(community_cards)
        num_opponents = max(1, num_opponents)

        # River: board complete, skip board-completion step
        if n_community == 5:
            return self._river_equity(hole_cards, community_cards, num_opponents, simulations, time_budget_ms)

        wins = 0
        total = 0
        deadline = time.perf_counter() + time_budget_ms / 1000.0

        known = set(hole_cards) | set(community_cards)
        available = [c for c in FULL_DECK if c not in known]

        for i in range(simulations):
            # Early exit if time budget exceeded
            if i % 50 == 0 and time.perf_counter() > deadline:
                break

            deck = available[:]
            random.shuffle(deck)

            cursor = 0
            opp_hands = []
            valid = True

            for _ in range(num_opponents):
                if cursor + 2 > len(deck):
                    valid = False
                    break
                opp_hands.append((deck[cursor], deck[cursor + 1]))
                cursor += 2

            if not valid:
                continue

            cards_needed = 5 - n_community
            board_completion = deck[cursor:cursor + cards_needed]
            if len(board_completion) < cards_needed:
                continue

            full_board = list(community_cards) + board_completion

            our_rank = self._hand_rank(hole_cards, full_board)
            _, our_vals = HandJudge.evaluate_hand(hole_cards, full_board)

            we_win = True
            for opp in opp_hands:
                opp_rank = self._hand_rank(opp, full_board)
                if opp_rank > our_rank:
                    we_win = False
                    break
                elif opp_rank == our_rank:
                    _, opp_vals = HandJudge.evaluate_hand(opp, full_board)
                    if opp_vals > our_vals:
                        we_win = False
                        break

            if we_win:
                wins += 1
            total += 1

        return wins / total if total > 0 else 0.5

    def _river_equity(
        self,
        hole_cards: Tuple[str, str],
        community_cards: List[str],
        num_opponents: int,
        simulations: int,
        time_budget_ms: int,
    ) -> float:
        """
        River: board is final — only sample opponent hole cards.
        Faster per-sim since no board completion needed.
        """
        known = set(hole_cards) | set(community_cards)
        available = [c for c in FULL_DECK if c not in known]

        our_rank = self._hand_rank(hole_cards, community_cards)
        _, our_vals = HandJudge.evaluate_hand(hole_cards, community_cards)

        wins = total = 0
        deadline = time.perf_counter() + time_budget_ms / 1000.0

        for i in range(simulations):
            if i % 50 == 0 and time.perf_counter() > deadline:
                break

            deck = available[:]
            random.shuffle(deck)
            cursor = 0
            we_win = True
            valid = True

            for _ in range(num_opponents):
                if cursor + 2 > len(deck):
                    valid = False
                    break
                opp = (deck[cursor], deck[cursor + 1])
                cursor += 2

                opp_rank = self._hand_rank(opp, community_cards)
                if opp_rank > our_rank:
                    we_win = False
                    break
                elif opp_rank == our_rank:
                    _, opp_vals = HandJudge.evaluate_hand(opp, community_cards)
                    if opp_vals > our_vals:
                        we_win = False
                        break

            if not valid:
                continue
            if we_win:
                wins += 1
            total += 1

        return wins / total if total > 0 else 0.5

    def _hand_rank(self, hole_cards: Tuple[str, str], board: List[str]) -> int:
        """Integer rank for fast comparison."""
        name, _ = HandJudge.evaluate_hand(hole_cards, board)
        return HAND_RANK_INT.get(name, 0)
