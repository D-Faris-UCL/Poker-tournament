"""
GhostBot — CFR-trained No-Limit Texas Hold'em bot.

Run train.py once before the tournament to generate strategy.pkl.
Falls back to a heuristic if the file is not found.
"""

import os
import sys
import random
from typing import Tuple

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.normpath(os.path.join(_BOT_DIR, '..', '..', '..'))
if _ROOT    not in sys.path: sys.path.insert(0, _ROOT)
if _BOT_DIR not in sys.path: sys.path.insert(0, _BOT_DIR)

from src.core.player import Player
from src.core.gamestate import PublicGamestate
from abstraction import (
    preflop_bucket, postflop_bucket,
    FOLD, CALL, RAISE_T, RAISE_H, RAISE_P, ALL_IN,
)

_STRATEGY_PATH = os.path.join(_BOT_DIR, 'strategy.pkl')
_STREET_CHAR   = {'preflop': 'p', 'flop': 'f', 'turn': 't', 'river': 'r'}


class GhostBot(Player):
    """
    CFR-trained poker bot.

    Decision pipeline:
      1. Compute hand bucket  (MC equity post-flop, lookup table pre-flop).
      2. Rebuild abstract action history from gamestate for the info-set key.
      3. Look up the Nash-approximate strategy for that info-set.
      4. Sample an action proportional to the strategy probabilities.
      5. Translate the abstract action into a concrete (action, amount) pair.
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._strategy = self._load_strategy()

    # ── strategy loading ──────────────────────────────────────────────────────

    def _load_strategy(self):
        try:
            import pickle
            with open(_STRATEGY_PATH, 'rb') as f:
                data = pickle.load(f)
            raw = data['strategy_sum']
            # Normalise cumulative sums into probabilities
            strategy = {}
            for infoset, counts in raw.items():
                total = sum(counts)
                if total > 0:
                    strategy[infoset] = {a: counts[a] / total for a in range(len(counts))}
                else:
                    n = len(counts)
                    strategy[infoset] = {a: 1.0 / n for a in range(n)}
            print(f"[GhostBot] Loaded {len(strategy):,} infosets")
            return strategy
        except FileNotFoundError:
            print("[GhostBot] strategy.pkl not found — using heuristic fallback.")
            return None
        except Exception as e:
            print(f"[GhostBot] Could not load strategy: {e}. Using heuristic fallback.")
            return None

    # ── main decision ─────────────────────────────────────────────────────────

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
    ) -> Tuple[str, int]:

        street         = gamestate.get_current_street()
        my_info        = gamestate.player_public_infos[self.player_index]
        bet_to_call    = gamestate.get_bet_to_call()
        amount_to_call = bet_to_call - my_info.current_bet
        num_opponents  = max(1, gamestate.get_active_players_count() - 1)

        # 1. Hand bucket
        bucket = self._get_bucket(
            hole_cards, gamestate.community_cards, street, num_opponents
        )

        # 2. Abstract action history for this street
        acts_str = self._street_history(gamestate, street)

        # 3. Info-set key  (matches the training encoding)
        n_opp   = min(num_opponents, 5)
        infoset = f"{_STREET_CHAR[street]}|{bucket}|{n_opp}|{acts_str}"

        # 4. Legal abstract actions
        legal = self._legal_abstract_actions(gamestate, my_info, amount_to_call)

        # 5. Sample action from strategy (or heuristic fallback)
        abstract_action = self._pick_action(infoset, legal)

        # 6. Translate to real action
        return self._to_real_action(
            abstract_action, gamestate, my_info, amount_to_call
        )

    # ── hand bucketing ────────────────────────────────────────────────────────

    def _get_bucket(
        self,
        hole_cards: Tuple[str, str],
        community_cards: list,
        street: str,
        num_opponents: int,
    ) -> int:
        if street == 'preflop':
            b = preflop_bucket(hole_cards)
            # More opponents → weaker effective equity; reduce bucket
            return max(0, b - min(num_opponents - 1, 4))

        # Postflop: use the same bucketing as training (hand rank + draw detection)
        # n_opp is already encoded separately in the infoset key
        return postflop_bucket(hole_cards, tuple(community_cards))

    # ── action history reconstruction ─────────────────────────────────────────

    def _street_history(self, gamestate: PublicGamestate, street: str) -> str:
        """
        Read this street's action log and encode it as a string of abstract
        action indices (e.g. "121").  Blinds are ignored; capped at 4 actions.
        """
        try:
            history = gamestate.current_hand_history
            if street not in history:
                return ""
            abstract = [
                str(_map_action_type(act.action_type))
                for act in history[street].actions
                if act.action_type not in ('small_blind', 'big_blind')
            ]
            return ''.join(abstract[-4:])
        except Exception:
            return ""

    # ── legal abstract actions ────────────────────────────────────────────────

    def _legal_abstract_actions(self, gamestate, my_info, amount_to_call) -> list:
        legal     = []
        stack     = my_info.stack
        pot       = gamestate.total_pot
        min_raise = gamestate.minimum_raise_amount

        if amount_to_call > 0:
            legal.append(FOLD)
        legal.append(CALL)

        remaining = stack - amount_to_call
        if remaining > 0:
            if remaining >= max(min_raise, pot * 0.33):
                legal.append(RAISE_T)
            if remaining >= max(min_raise, pot * 0.67):
                legal.append(RAISE_H)
            if remaining >= max(min_raise, pot):
                legal.append(RAISE_P)
            legal.append(ALL_IN)

        return legal

    # ── strategy lookup ───────────────────────────────────────────────────────

    def _pick_action(self, infoset: str, legal: list) -> int:
        if self._strategy is None:
            return _heuristic(legal)

        ss    = self._strategy.get(infoset)
        if ss is None:
            return _heuristic(legal)

        total = sum(ss[a] for a in legal)
        if total <= 0:
            return _heuristic(legal)

        # Weighted random sample from strategy probabilities
        r          = random.random() * total
        cumulative = 0.0
        for a in legal:
            cumulative += ss[a]
            if r <= cumulative:
                return a
        return legal[-1]

    # ── abstract → real action ────────────────────────────────────────────────

    def _to_real_action(
        self,
        abstract_action: int,
        gamestate,
        my_info,
        amount_to_call: int,
    ) -> Tuple[str, int]:

        stack     = my_info.stack
        pot       = gamestate.total_pot
        min_raise = gamestate.minimum_raise_amount

        if abstract_action == FOLD:
            return ('fold', 0)

        if abstract_action == CALL:
            return ('check', 0) if amount_to_call == 0 else ('call', 0)

        if abstract_action == RAISE_T:
            amount = max(min_raise, int(pot * 0.33))
            if my_info.current_bet + amount >= stack:
                return ('all-in', 0)
            return ('raise', amount)

        if abstract_action == RAISE_H:
            amount = max(min_raise, int(pot * 0.67))
            if my_info.current_bet + amount >= stack:
                return ('all-in', 0)
            return ('raise', amount)

        if abstract_action == RAISE_P:
            amount = max(min_raise, pot)
            if my_info.current_bet + amount >= stack:
                return ('all-in', 0)
            return ('raise', amount)

        if abstract_action == ALL_IN:
            return ('all-in', 0)

        return ('check', 0)


# ── module-level helpers ──────────────────────────────────────────────────────

def _map_action_type(action_type: str) -> int:
    """Map a real action type string to the nearest abstract action index."""
    return {
        'fold':   FOLD,
        'check':  CALL,
        'call':   CALL,
        'raise':  RAISE_H,   # approximate — we don't reconstruct exact sizing
        'all-in': ALL_IN,
    }.get(action_type, CALL)


def _heuristic(legal: list) -> int:
    """Simple fallback when the CFR table has no entry for this info-set."""
    if RAISE_H in legal:
        return RAISE_H
    if CALL in legal:
        return CALL
    return legal[0]
