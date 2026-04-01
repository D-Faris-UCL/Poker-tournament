"""GamestateEncoder: converts (PublicGamestate, hole_cards) → 192-dim float32 tensor.

Feature vector layout (192 dims total):
    Block A – Hole cards          (35): rank1 one-hot(13) + rank2 one-hot(13)
                                         + suit1 one-hot(4) + suit2 one-hot(4) + suited(1)
    Block B – Community cards     (85): up to 5 cards × 17 (rank 13 + suit 4), zero-padded
    Block B – Street              ( 4): preflop/flop/turn/river one-hot
    Block C – Hand strength       (11): hand-rank one-hot(10) + normalized scalar(1)
                                        (Chen formula scalar preflop)
    Block D – Self chip info      ( 6): stack, current_bet, total_pot, bet_to_call,
                                        amount_to_call, min_raise  — all ÷ (bb×100)
    Block E – Position+opponents  (22): rel_pos(1) + is_btn(1) + is_sb(1) + is_bb(1)
                                        + active_frac(1) + non_busted_frac(1)
                                        + 8 opponent slots × (stack_norm + is_active)
    Block F – Recent actions      (24): last 4 actions on current street,
                                        each = 5-dim action one-hot + amount_norm
    Block G – Tournament meta     ( 5): round/500, sb/2000, bb/2000,
                                        my_stack/2000, non_busted/9
"""

import torch
from typing import List, Tuple

# ── Lookup tables ─────────────────────────────────────────────────────────────

RANK_TO_IDX: dict = {
    '2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5,
    '8': 6, '9': 7, 'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12,
}
SUIT_TO_IDX: dict = {'h': 0, 'd': 1, 'c': 2, 's': 3}
STREET_TO_IDX: dict = {'preflop': 0, 'flop': 1, 'turn': 2, 'river': 3}
HAND_RANK_NAMES: List[str] = [
    'high_card', 'one_pair', 'two_pair', 'three_of_a_kind',
    'straight', 'flush', 'full_house', 'four_of_a_kind',
    'straight_flush', 'royal_flush',
]
CHEN_RANK: dict = {
    14: 10, 13: 8, 12: 7, 11: 6, 10: 5,
    9: 4.5, 8: 4, 7: 3.5, 6: 3, 5: 2.5, 4: 2, 3: 1.5, 2: 1,
}
RANK_VALUES: dict = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
}
# Action type → 0-4 index for Block F one-hot
ACTION_TYPE_TO_IDX: dict = {
    'fold': 0, 'check': 1, 'call': 2, 'raise': 3, 'all-in': 4,
    'small_blind': 2, 'big_blind': 3,
}

FEATURE_DIM = 192


# ── Lazy HandJudge import ─────────────────────────────────────────────────────
# Supports both package import (tournament) and script import (training).

def _get_hand_judge():
    try:
        from ...helpers.hand_judge import HandJudge
        return HandJudge
    except ImportError:
        import sys
        import os
        _root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        if _root not in sys.path:
            sys.path.insert(0, _root)
        from src.helpers.hand_judge import HandJudge
        return HandJudge


# ── Encoder ───────────────────────────────────────────────────────────────────

class GamestateEncoder:
    """Stateless encoder. Thread-safe; no mutable state after construction."""

    FEATURE_DIM = FEATURE_DIM

    # ── Public API ────────────────────────────────────────────────────────────

    def encode(
        self,
        gamestate,
        hole_cards: Tuple[str, str],
        player_index: int,
    ) -> torch.Tensor:
        """Encode a game state into a 192-dim float32 tensor.

        Args:
            gamestate:    PublicGamestate object from the table.
            hole_cards:   Two-card tuple for the acting player, e.g. ('Ah', 'Kd').
            player_index: Index of the acting player.

        Returns:
            Tensor of shape (192,) dtype float32.
        """
        f: List[float] = []

        # A: Hole cards (35)
        f.extend(self._encode_hole_cards(hole_cards))

        # B: Community cards (85) + street (4)
        f.extend(self._encode_community_cards(gamestate.community_cards))
        f.extend(self._encode_street(gamestate.get_current_street()))

        # C: Hand strength (11)
        f.extend(self._encode_hand_strength(hole_cards, gamestate.community_cards))

        # D: Self chip info (6)
        f.extend(self._encode_self_info(gamestate, player_index))

        # E: Position + opponents (22)
        f.extend(self._encode_position_and_opponents(gamestate, player_index))

        # F: Recent actions (24)
        f.extend(self._encode_recent_actions(gamestate))

        # G: Tournament meta (5)
        f.extend(self._encode_tournament_meta(gamestate, player_index))

        assert len(f) == FEATURE_DIM, f"Feature dim mismatch: {len(f)} != {FEATURE_DIM}"
        return torch.tensor(f, dtype=torch.float32)

    # ── Block A: Hole cards ───────────────────────────────────────────────────

    def _encode_hole_cards(self, hole_cards: Tuple[str, str]) -> List[float]:
        """35 features: rank1(13) + rank2(13) + suit1(4) + suit2(4) + suited(1)."""
        c1, c2 = hole_cards
        r1 = [0.0] * 13; r1[RANK_TO_IDX[c1[0]]] = 1.0
        r2 = [0.0] * 13; r2[RANK_TO_IDX[c2[0]]] = 1.0
        s1 = [0.0] * 4;  s1[SUIT_TO_IDX[c1[1]]] = 1.0
        s2 = [0.0] * 4;  s2[SUIT_TO_IDX[c2[1]]] = 1.0
        suited = [1.0 if c1[1] == c2[1] else 0.0]
        return r1 + r2 + s1 + s2 + suited  # 35

    # ── Block B: Community cards + street ─────────────────────────────────────

    def _encode_card(self, card: str) -> List[float]:
        """17 features per card: rank one-hot(13) + suit one-hot(4)."""
        r = [0.0] * 13; r[RANK_TO_IDX[card[0]]] = 1.0
        s = [0.0] * 4;  s[SUIT_TO_IDX[card[1]]] = 1.0
        return r + s  # 17

    def _encode_community_cards(self, community_cards: List[str]) -> List[float]:
        """85 features: 5 card slots × 17, zero-padded for un-dealt cards."""
        result: List[float] = []
        for i in range(5):
            result.extend(self._encode_card(community_cards[i])
                          if i < len(community_cards) else [0.0] * 17)
        return result  # 85

    def _encode_street(self, street: str) -> List[float]:
        """4-dim one-hot: preflop=0, flop=1, turn=2, river=3."""
        oh = [0.0] * 4
        oh[STREET_TO_IDX.get(street, 0)] = 1.0
        return oh  # 4

    # ── Block C: Hand strength ────────────────────────────────────────────────

    def _encode_hand_strength(
        self, hole_cards: Tuple[str, str], community_cards: List[str]
    ) -> List[float]:
        """11 features: hand-rank one-hot(10) + normalized rank scalar(1).

        Preflop (no community cards): one-hot is zeroed; scalar = Chen formula.
        """
        if len(community_cards) >= 3:
            try:
                HandJudge = _get_hand_judge()
                hand_name, _ = HandJudge.evaluate_hand(hole_cards, community_cards)
                rank_idx = HAND_RANK_NAMES.index(hand_name)
            except Exception:
                rank_idx = 0
            oh = [0.0] * 10
            oh[rank_idx] = 1.0
            return oh + [(rank_idx + 1) / 10.0]  # 11
        else:
            chen = self._chen_formula(hole_cards)
            return [0.0] * 10 + [min(max(chen / 20.0, 0.0), 1.0)]  # 11

    def _chen_formula(self, hole_cards: Tuple[str, str]) -> float:
        """Simplified Chen formula — preflop hand strength in [~1, ~20]."""
        c1, c2 = hole_cards
        r1 = RANK_VALUES.get(c1[0], 2)
        r2 = RANK_VALUES.get(c2[0], 2)
        high = max(r1, r2)
        low = min(r1, r2)
        score = float(CHEN_RANK.get(high, 1))
        if r1 == r2:
            return max(score * 2, 5.0)
        if c1[1] == c2[1]:
            score += 2.0
        gap = high - low - 1
        if gap == 0:
            score += 1.0
        elif gap == 1:
            score += 0.5
        elif gap == 3:
            score -= 1.0
        elif gap >= 4:
            score -= 1.5
        if high < 10:
            score -= 1.0
        return score

    # ── Block D: Self chip info ───────────────────────────────────────────────

    def _encode_self_info(self, gamestate, player_index: int) -> List[float]:
        """6 features: stack, current_bet, total_pot, bet_to_call,
        amount_to_call, min_raise — all normalised by (bb × 100)."""
        bb = max(gamestate.blinds[1], 1)
        norm = float(bb * 100)
        p = gamestate.player_public_infos[player_index]
        bet_to_call = gamestate.get_bet_to_call()
        amount_to_call = max(bet_to_call - p.current_bet, 0)
        return [
            p.stack / norm,
            p.current_bet / norm,
            gamestate.total_pot / norm,
            bet_to_call / norm,
            amount_to_call / norm,
            gamestate.minimum_raise_amount / norm,
        ]  # 6

    # ── Block E: Position + opponents ─────────────────────────────────────────

    def _encode_position_and_opponents(
        self, gamestate, player_index: int
    ) -> List[float]:
        """22 features: 6 positional scalars + 8 opponent slots × 2."""
        n = len(gamestate.player_public_infos)
        button = gamestate.button_position
        sb_pos = (button + 1) % n
        bb_pos = (button + 2) % n

        rel_pos = ((player_index - button) % n) / max(n, 1)
        is_btn = 1.0 if player_index == button else 0.0
        is_sb  = 1.0 if player_index == sb_pos  else 0.0
        is_bb  = 1.0 if player_index == bb_pos  else 0.0
        active_frac     = gamestate.get_active_players_count()     / 9.0
        non_busted_frac = gamestate.get_non_busted_players_count() / 9.0

        pos_feats = [rel_pos, is_btn, is_sb, is_bb, active_frac, non_busted_frac]  # 6

        bb = max(gamestate.blinds[1], 1)
        norm = float(bb * 100)

        opp_feats: List[float] = []
        for i in range(1, 9):  # 8 opponent slots
            if i >= n:
                # No player in this seat (table has fewer than 9 players)
                opp_feats.extend([-1.0, 0.0])
            else:
                opp_idx = (player_index + i) % n
                opp = gamestate.player_public_infos[opp_idx]
                if opp.busted:
                    opp_feats.extend([-1.0, 0.0])
                else:
                    opp_feats.extend([opp.stack / norm, 1.0 if opp.active else 0.0])

        return pos_feats + opp_feats  # 6 + 16 = 22

    # ── Block F: Recent actions ────────────────────────────────────────────────

    def _encode_recent_actions(self, gamestate) -> List[float]:
        """24 features: last 4 actions on current street,
        each = 5-dim action one-hot + normalised amount (6 dims × 4 = 24)."""
        street = gamestate.get_current_street()
        street_history = gamestate.current_hand_history.get(street)

        actions = []
        if street_history is not None:
            actions = list(street_history.actions[-4:])

        bb = max(gamestate.blinds[1], 1)
        norm = float(bb * 100)

        result: List[float] = []
        for i in range(4):
            if i < len(actions):
                act = actions[i]
                oh = [0.0] * 5
                oh[ACTION_TYPE_TO_IDX.get(act.action_type, 0)] = 1.0
                result.extend(oh + [act.amount / norm])
            else:
                result.extend([0.0] * 6)

        return result  # 24

    # ── Block G: Tournament meta ──────────────────────────────────────────────

    def _encode_tournament_meta(self, gamestate, player_index: int) -> List[float]:
        """5 features: round/500, sb/2000, bb/2000, my_stack/2000, non_busted/9."""
        p = gamestate.player_public_infos[player_index]
        sb, bb = gamestate.blinds
        starting = 2000.0
        return [
            gamestate.round_number / 500.0,
            sb / starting,
            bb / starting,
            p.stack / starting,
            gamestate.get_non_busted_players_count() / 9.0,
        ]  # 5
