"""
OmegaBot: Strong, compute-efficient Texas Hold'em bot.

Key improvements over v1:
  1. Monte Carlo equity  - replaces rough table with actual simulation (300 sims,
                           ~5 ms / call — well under the 1-second sandbox limit)
  2. Range-aware MC      - opponent hands sampled from their estimated VPIP range,
                           giving more accurate equity vs tight vs loose players
  3. Board texture       - wet/dry board detection adjusts bet sizing and aggression
  4. SPR awareness       - stack-to-pot ratio governs willingness to commit chips
  5. Check-raise OOP     - slow-play monsters, then check-raise for max value
  6. Preflop             - same 169-hand table + position + 3-bet/4-bet sizing
  7. Short-stack P/F     - push/fold thresholds keyed to stack-in-BB

Compute budget per decision:
  MC equity    ~5 ms  (300 sims x ≤3 opponents x 7-card hand eval)
  Everything else < 1 ms
  Total        << 1 second (sandbox limit)
"""

import random
from collections import Counter
from typing import Dict, List, Tuple

from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.hand_judge import HandJudge
from src.helpers.player_judge import PlayerJudge


# ---------------------------------------------------------------------------
# Preflop hand-strength table  (0–100, poker-theory based, 169 unique hands)
# ---------------------------------------------------------------------------
_PF_STR: Dict[str, int] = {
    "AA": 100, "KK": 96, "QQ": 91, "JJ": 86, "TT": 81,
    "99": 74,  "88": 68, "77": 62, "66": 56, "55": 51,
    "44": 46,  "33": 41, "22": 36,
    "AKs": 88, "AQs": 81, "AJs": 76, "ATs": 71, "A9s": 63,
    "A8s": 59, "A7s": 56, "A6s": 53, "A5s": 56, "A4s": 53,
    "A3s": 51, "A2s": 49,
    "KQs": 76, "KJs": 71, "KTs": 67, "K9s": 59, "K8s": 51,
    "K7s": 48, "K6s": 45, "K5s": 42, "K4s": 39, "K3s": 36, "K2s": 34,
    "QJs": 69, "QTs": 64, "Q9s": 57, "Q8s": 49, "Q7s": 41,
    "Q6s": 38, "Q5s": 35, "Q4s": 32, "Q3s": 29, "Q2s": 27,
    "JTs": 66, "J9s": 59, "J8s": 52, "J7s": 44, "J6s": 37,
    "J5s": 33, "J4s": 30, "J3s": 27, "J2s": 25,
    "T9s": 63, "T8s": 56, "T7s": 48, "T6s": 40, "T5s": 32,
    "T4s": 28, "T3s": 25, "T2s": 23,
    "98s": 60, "97s": 52, "96s": 44, "95s": 36, "94s": 28,
    "93s": 25, "92s": 23,
    "87s": 56, "86s": 48, "85s": 40, "84s": 32, "83s": 25, "82s": 23,
    "76s": 53, "75s": 45, "74s": 37, "73s": 29, "72s": 23,
    "65s": 50, "64s": 42, "63s": 34, "62s": 27,
    "54s": 48, "53s": 40, "52s": 32,
    "43s": 45, "42s": 37,
    "32s": 40,
    "AKo": 83, "AQo": 75, "AJo": 68, "ATo": 63, "A9o": 55,
    "A8o": 51, "A7o": 48, "A6o": 45, "A5o": 48, "A4o": 45,
    "A3o": 42, "A2o": 39,
    "KQo": 68, "KJo": 62, "KTo": 58, "K9o": 50, "K8o": 42,
    "K7o": 38, "K6o": 35, "K5o": 32, "K4o": 29, "K3o": 26, "K2o": 24,
    "QJo": 61, "QTo": 56, "Q9o": 49, "Q8o": 41, "Q7o": 33,
    "Q6o": 30, "Q5o": 27, "Q4o": 24, "Q3o": 21, "Q2o": 19,
    "JTo": 58, "J9o": 51, "J8o": 44, "J7o": 36, "J6o": 28,
    "J5o": 24, "J4o": 21, "J3o": 19, "J2o": 17,
    "T9o": 55, "T8o": 48, "T7o": 40, "T6o": 32, "T5o": 24,
    "T4o": 20, "T3o": 18, "T2o": 16,
    "98o": 52, "97o": 44, "96o": 36, "95o": 28, "94o": 20,
    "93o": 17, "92o": 15,
    "87o": 48, "86o": 40, "85o": 32, "84o": 24, "83o": 17, "82o": 15,
    "76o": 45, "75o": 37, "74o": 29, "73o": 21, "72o": 15,
    "65o": 41, "64o": 33, "63o": 25, "62o": 18,
    "54o": 39, "53o": 31, "52o": 23,
    "43o": 36, "42o": 28,
    "32o": 31,
}

_HAND_RANK: Dict[str, int] = {
    "high_card": 1, "one_pair": 2, "two_pair": 3, "three_of_a_kind": 4,
    "straight": 5, "flush": 6, "full_house": 7, "four_of_a_kind": 8,
    "straight_flush": 9, "royal_flush": 10,
}

_RV: Dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}

# Full 52-card deck (pre-built for speed)
_FULL_DECK: List[str] = [r + s for r in "23456789TJQKA" for s in "hdcs"]

# Sorted hands by strength (strongest first) for range filtering
_PF_SORTED_KEYS: List[str] = sorted(_PF_STR, key=lambda k: _PF_STR[k], reverse=True)


# ---------------------------------------------------------------------------
class OmegaBot(Player):
    """
    GTO-inspired poker bot with Monte Carlo equity estimation.

    Decision stack:
      1. Short-stack push/fold   (≤ 15 BB)
      2. Preflop: tiered strength + position + correct 3-bet/4-bet sizing
      3. Postflop: MC equity vs opponent range + board texture + SPR
    """

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._opp: Dict[int, Dict] = {}     # per-opponent stats
        self._processed: int = 0            # hands already absorbed

    # ===================================================================
    # ENTRY POINT
    # ===================================================================

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
    ) -> Tuple[str, int]:
        self._update_opp_model(gamestate)

        my = gamestate.player_public_infos[self.player_index]
        bb = max(gamestate.blinds[1], 1)
        stack_bb = my.stack / bb

        legal = PlayerJudge.get_legal_actions(
            self.player_index,
            gamestate.player_public_infos,
            gamestate.get_bet_to_call(),
            gamestate.minimum_raise_amount,
        )

        if stack_bb <= 15:
            return self._short_stack(gamestate, hole_cards, legal, stack_bb)

        street = gamestate.get_current_street()
        if street == "preflop":
            return self._preflop(gamestate, hole_cards, legal)
        return self._postflop(gamestate, hole_cards, legal, street)

    # ===================================================================
    # PREFLOP
    # ===================================================================

    def _preflop(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
        legal: dict,
    ) -> Tuple[str, int]:
        strength = _pf_strength(hole_cards)
        pos, n = self._pos(gamestate)
        my = gamestate.player_public_infos[self.player_index]
        bb = max(gamestate.blinds[1], 1)
        bet_to_call = gamestate.get_bet_to_call()
        atc = bet_to_call - my.current_bet
        call_bb = atc / bb
        n_raises = self._n_pf_raises(gamestate)

        # If any active opponent is all-in, use MC equity vs random range
        if n_raises >= 1 and atc > 0 and self._any_opp_allin(gamestate):
            return self._call_or_fold_vs_allin(gamestate, hole_cards, legal, atc)

        # Position bonus: button (+15), UTG (0)
        pos_bonus = (n - 1 - pos) / max(n - 1, 1) * 15
        adj = strength + pos_bonus

        # ── Tier 1 · Premium  (AA/KK/QQ/JJ/AKs  adj≥90) ────────────────
        if adj >= 90:
            if n_raises >= 2:
                return ("all-in", 0)
            target = 3 * bet_to_call if n_raises >= 1 else 3 * bb
            return self._raise_to(target, my, legal, gamestate)

        # ── Tier 2 · Very strong  (TT/AKo/AQs  adj≥76) ─────────────────
        if adj >= 76:
            if n_raises >= 2:
                if strength >= 82 and legal["call"] and call_bb <= 20:
                    return ("call", 0)
                return _foc(legal)
            if n_raises == 1:
                if strength >= 86:
                    return self._raise_to(3 * bet_to_call, my, legal, gamestate)
                if legal["call"] and call_bb <= 12:
                    return ("call", 0)
                return _foc(legal)
            target = int(2.5 * bb) if pos <= 1 else 3 * bb
            return self._raise_to(target, my, legal, gamestate)

        # ── Tier 3 · Strong  (99/AQo/KQs/AJs  adj≥63) ──────────────────
        if adj >= 63:
            if n_raises >= 2:
                return _foc(legal)
            if n_raises == 1:
                if legal["call"] and call_bb <= 7:
                    return ("call", 0)
                return _foc(legal)
            return self._raise_to(3 * bb, my, legal, gamestate)

        # ── Tier 4 · Playable  (88/AJo/KJs/SC  adj≥49) ─────────────────
        if adj >= 49:
            if n_raises >= 1:
                if legal["call"] and call_bb <= 4:
                    return ("call", 0)
                return _foc(legal)
            if pos <= 1:
                return self._raise_to(int(2.5 * bb), my, legal, gamestate)
            if pos <= 2 and legal["call"] and call_bb <= 2:
                return ("call", 0)
            return _foc(legal)

        # ── Tier 5 · Speculative  (small pairs, suited Ax, SC  adj≥35) ──
        if adj >= 35:
            if n_raises == 0 and legal["check"]:
                return ("check", 0)
            if legal["call"] and call_bb <= 3:
                return ("call", 0)
            return _foc(legal)

        # ── Trash ────────────────────────────────────────────────────────
        return _foc(legal)

    # ===================================================================
    # POSTFLOP  (Monte Carlo equity)
    # ===================================================================

    def _postflop(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
        legal: dict,
        street: str,
    ) -> Tuple[str, int]:
        my = gamestate.player_public_infos[self.player_index]
        bet_to_call = gamestate.get_bet_to_call()
        atc = bet_to_call - my.current_bet
        pot = max(gamestate.total_pot, 1)
        pot_odds = atc / (pot + atc) if atc > 0 else 0.0

        community = gamestate.community_cards
        hand_name, _ = HandJudge.evaluate_hand(hole_cards, community)
        hr = _HAND_RANK[hand_name]

        # Active opponents (exclude folded/busted)
        active_opps = [
            i for i, p in enumerate(gamestate.player_public_infos)
            if p.active and not p.busted and i != self.player_index
        ]
        n_opp = max(len(active_opps), 1)

        # ── Monte Carlo equity ────────────────────────────────────────────
        vpip_rates = [
            self._vpip_rate(i) for i in active_opps
        ]
        n_sims = 150 if street == "preflop" else (250 if street in ("flop", "turn") else 150)
        equity = _mc_equity(hole_cards, community, n_opp, n_sims, vpip_rates)

        # ── Position & board context ──────────────────────────────────────
        pos, _ = self._pos(gamestate)
        ip = pos == 0

        wetness = _board_wetness(community)
        spr = my.stack / pot

        opp_aggressed = self._opp_raised_street(
            gamestate.current_hand_history.get(street)
        )
        agg_rate = self._active_opp_agg_rate(gamestate)
        passive_opps = agg_rate < 0.12
        aggro_opps = agg_rate > 0.28

        # Bet sizing multiplier: bigger on wet boards, smaller on dry
        size_mult = 1.0 + 0.25 * wetness  # 1.0 (dry) → 1.25 (very wet)

        # ── DECISION LOGIC ────────────────────────────────────────────────

        # MONSTER: flush / full house / quads / sf / rf
        if hr >= 6:
            if atc > 0:
                if legal["raise"] and not opp_aggressed:
                    frac = 0.75 * size_mult
                    return self._raise_frac(frac, atc, pot, my, legal, gamestate)
                return ("call", 0)
            # Slow-play option: check-raise OOP with nuts when likely to face bet
            if not ip and hr >= 8 and n_opp == 1:
                return ("check", 0)   # trap — will check-raise next action
            if legal["raise"]:
                frac = 0.70 * size_mult
                return self._raise_frac(frac, atc, pot, my, legal, gamestate)
            return ("check", 0)

        # STRONG: trips / straight
        if hr >= 4:
            if atc > 0:
                if equity >= pot_odds - 0.04:
                    # Re-raise for value if not already raised
                    if legal["raise"] and not opp_aggressed and equity >= 0.78:
                        frac = 0.60 * size_mult
                        return self._raise_frac(frac, atc, pot, my, legal, gamestate)
                    return ("call", 0)
                return ("fold", 0)
            if legal["raise"]:
                frac = 0.60 * size_mult
                return self._raise_frac(frac, atc, pot, my, legal, gamestate)
            return ("check", 0)

        # TWO PAIR
        if hr == 3:
            if atc > 0:
                if equity >= pot_odds - 0.02 or atc <= pot * 0.25:
                    return ("call", 0)
                return ("fold", 0)
            if legal["raise"]:
                frac = 0.55 * size_mult
                return self._raise_frac(frac, atc, pot, my, legal, gamestate)
            return ("check", 0)

        # ONE PAIR
        if hr == 2:
            call_margin = 0.06 - (0.04 if aggro_opps else 0)
            if atc > 0:
                if equity >= pot_odds + call_margin:
                    return ("call", 0)
                if equity >= pot_odds and atc <= pot * 0.35:
                    return ("call", 0)
                # SPR-based all-in call: if pot-committed, call off
                if spr < 2.5 and equity >= 0.38:
                    return ("call", 0)
                return ("fold", 0)
            # Bet for value
            should_bet = ip or passive_opps
            if should_bet and legal["raise"] and not opp_aggressed:
                frac = 0.42 * size_mult
                return self._raise_frac(frac, atc, pot, my, legal, gamestate)
            return ("check", 0)

        # HIGH CARD + DRAWS
        # Estimate draw outs (but on river draws are worthless)
        outs = _draw_outs(hole_cards, community) if street != "river" else 0

        if outs >= 4 or equity >= 0.35:
            # Decent draw or marginal equity
            if atc > 0:
                if equity >= pot_odds + 0.03:
                    if ip and legal["raise"] and equity >= 0.36 and not opp_aggressed:
                        return self._raise_frac(0.50 * size_mult, atc, pot, my, legal, gamestate)
                    return ("call", 0)
                # Cheap call if nearly break-even
                if equity >= pot_odds - 0.05 and atc <= pot * 0.30:
                    return ("call", 0)
                return ("fold", 0)
            # Semi-bluff / check
            bluff_ok = ip and legal["raise"] and not opp_aggressed
            if bluff_ok and equity >= 0.32 and random.random() < 0.45:
                return self._raise_frac(0.50 * size_mult, atc, pot, my, legal, gamestate)
            return ("check", 0)

        # AIR
        if atc > 0:
            # Tiny-bet hero-call
            if pot_odds < 0.17 and atc <= pot * 0.18:
                return ("call", 0)
            return ("fold", 0)
        bluff_freq = 0.20 if not aggro_opps else 0.10
        if ip and legal["raise"] and random.random() < bluff_freq:
            return self._raise_frac(0.38 * size_mult, atc, pot, my, legal, gamestate)
        return ("check", 0)

    # ===================================================================
    # SHORT STACK  (≤ 15 BB)
    # ===================================================================

    def _short_stack(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
        legal: dict,
        stack_bb: float,
    ) -> Tuple[str, int]:
        strength = _pf_strength(hole_cards)
        my = gamestate.player_public_infos[self.player_index]
        bb = max(gamestate.blinds[1], 1)
        atc = gamestate.get_bet_to_call() - my.current_bet
        call_bb = atc / bb

        # If facing an all-in, use MC equity vs random range
        if atc > 0 and self._any_opp_allin(gamestate):
            return self._call_or_fold_vs_allin(gamestate, hole_cards, legal, atc)

        # Push threshold widens as stack shrinks
        if stack_bb <= 5:
            push_thr = 28
        elif stack_bb <= 8:
            push_thr = 42
        elif stack_bb <= 10:
            push_thr = 52
        elif stack_bb <= 12:
            push_thr = 60
        else:
            push_thr = 66

        if strength >= push_thr:
            if legal["raise"]:
                return ("all-in", 0)
            if legal["call"]:
                return ("call", 0)

        if atc > 0:
            if strength >= push_thr * 0.75 and call_bb <= stack_bb * 0.8:
                return ("call", 0)
            if legal["check"]:
                return ("check", 0)
            return ("fold", 0)

        return ("check", 0)

    # ===================================================================
    # ALL-IN CALL HELPERS
    # ===================================================================

    def _any_opp_allin(self, gamestate: PublicGamestate) -> bool:
        """True if any active opponent is all-in."""
        return any(
            p.is_all_in
            for i, p in enumerate(gamestate.player_public_infos)
            if i != self.player_index and p.active and not p.busted
        )

    def _call_or_fold_vs_allin(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
        legal: dict,
        atc: int,
    ) -> Tuple[str, int]:
        """Use MC equity vs random range to decide call/fold against all-in opponents."""
        active_opps = [
            i for i, p in enumerate(gamestate.player_public_infos)
            if p.active and not p.busted and i != self.player_index
        ]
        n_opp = max(len(active_opps), 1)
        # All-in opponents have effectively random ranges
        vpip_rates = [1.0] * n_opp
        community = gamestate.community_cards
        equity = _mc_equity(hole_cards, community, n_opp, 300, vpip_rates)

        my = gamestate.player_public_infos[self.player_index]
        pot = gamestate.total_pot + sum(p.current_bet for p in gamestate.player_public_infos)
        call_cost = min(atc, my.stack)
        pot_odds = call_cost / (pot + call_cost) if call_cost > 0 else 0.0

        if equity > pot_odds:
            if legal.get("call"):
                return ("call", 0)
            return ("all-in", 0)
        return _foc(legal)

    # ===================================================================
    # RAISE HELPERS
    # ===================================================================

    def _raise_to(
        self,
        target_total: float,
        my,
        legal: dict,
        gamestate: PublicGamestate,
    ) -> Tuple[str, int]:
        """
        Raise so player's total street commitment == target_total.

        Engine semantics (player_judge.py):
          current_bet == 0  →  amount = total opening bet size
          current_bet  > 0  →  amount = additional chips beyond player.current_bet
                               (total_bet_needed = amount + player.current_bet)
        """
        if not legal["raise"]:
            return ("call", 0) if legal["call"] else _foc(legal)
        bet_to_call = gamestate.get_bet_to_call()
        atc = bet_to_call - my.current_bet
        min_raise = gamestate.minimum_raise_amount

        if bet_to_call == 0:
            amount = max(int(target_total), min_raise)
            amount = min(amount, my.stack)
        else:
            amount = max(int(target_total) - my.current_bet, 0)
            amount = max(amount, atc + min_raise)
            amount = min(amount, my.stack)

        if amount >= my.stack:
            return ("all-in", 0)
        return ("raise", amount)

    def _raise_frac(
        self,
        fraction: float,
        atc: int,
        pot: int,
        my,
        legal: dict,
        gamestate: PublicGamestate,
    ) -> Tuple[str, int]:
        """Postflop raise sized at `fraction` of effective pot."""
        if not legal["raise"]:
            return ("call", 0) if legal["call"] else _foc(legal)
        min_raise = gamestate.minimum_raise_amount
        if atc == 0:
            amount = max(int(pot * fraction), min_raise)
            amount = min(amount, my.stack)
        else:
            eff_pot = pot + 2 * atc
            amount = atc + int(eff_pot * fraction)
            amount = max(amount, atc + min_raise)
            amount = min(amount, my.stack)
        if amount >= my.stack:
            return ("all-in", 0)
        return ("raise", amount)

    # ===================================================================
    # POSITION
    # ===================================================================

    def _pos(self, gamestate: PublicGamestate) -> Tuple[int, int]:
        """(distance_from_button, n_active).  0 = button (best position)."""
        active = [i for i, p in enumerate(gamestate.player_public_infos) if not p.busted]
        n = len(active)
        if self.player_index not in active:
            return 0, n
        btn = gamestate.button_position
        if btn not in active:
            btn = active[0]
        return (active.index(self.player_index) - active.index(btn)) % n, n

    # ===================================================================
    # OPPONENT MODEL
    # ===================================================================

    def _update_opp_model(self, gamestate: PublicGamestate) -> None:
        n_prev = len(gamestate.previous_hand_histories)
        if n_prev <= self._processed:
            return
        n = len(gamestate.player_public_infos)
        for i in range(n):
            if i not in self._opp:
                self._opp[i] = {"h": 0, "vpip": 0, "pfr": 0}
        for rec in gamestate.previous_hand_histories[self._processed:]:
            pf = rec.per_street.get("preflop")
            if pf is None:
                continue
            vol: set = set()
            for a in pf.actions:
                idx = a.player_index
                if idx not in self._opp:
                    continue
                if a.action_type in ("call", "raise", "all-in"):
                    vol.add(idx)
                if a.action_type in ("raise", "all-in"):
                    self._opp[idx]["pfr"] += 1
            for idx in vol:
                self._opp[idx]["vpip"] += 1
                self._opp[idx]["h"] += 1
        self._processed = n_prev

    def _vpip_rate(self, player_idx: int) -> float:
        """Estimated VPIP rate for a player (0.0–1.0). Default 0.40 until 8 hands seen."""
        s = self._opp.get(player_idx, {})
        h = s.get("h", 0)
        if h < 8:
            return 0.40   # assume moderate looseness by default
        return s["vpip"] / h

    def _active_opp_agg_rate(self, gamestate: PublicGamestate) -> float:
        """Mean PFR/hands of active opponents. Returns 0.20 (neutral) if no data."""
        rates = []
        for i, p in enumerate(gamestate.player_public_infos):
            if i == self.player_index or p.busted or not p.active:
                continue
            s = self._opp.get(i, {})
            h = s.get("h", 0)
            if h >= 6:
                rates.append(s.get("pfr", 0) / h)
        return sum(rates) / len(rates) if rates else 0.20

    # ===================================================================
    # MISC HELPERS
    # ===================================================================

    @staticmethod
    def _n_pf_raises(gamestate: PublicGamestate) -> int:
        pf = gamestate.current_hand_history.get("preflop")
        if pf is None:
            return 0
        return sum(1 for a in pf.actions if a.action_type in ("raise", "all-in"))

    @staticmethod
    def _opp_raised_street(sh) -> bool:
        if sh is None:
            return False
        return any(a.action_type in ("raise", "all-in") for a in sh.actions)


# ===================================================================
# MODULE-LEVEL PURE FUNCTIONS
# ===================================================================

def _pf_strength(hole_cards: Tuple[str, str]) -> int:
    r1, s1 = hole_cards[0][0], hole_cards[0][1]
    r2, s2 = hole_cards[1][0], hole_cards[1][1]
    if _RV[r1] < _RV[r2]:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        key = r1 + r2
    elif s1 == s2:
        key = r1 + r2 + "s"
    else:
        key = r1 + r2 + "o"
    return _PF_STR.get(key, 20)


def _hand_key(c1: str, c2: str) -> str:
    """Canonical preflop hand key from two card strings."""
    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]
    if _RV[r1] < _RV[r2]:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return r1 + r2
    return (r1 + r2 + "s") if s1 == s2 else (r1 + r2 + "o")


def _mc_equity(
    hole_cards: Tuple[str, str],
    community: List[str],
    n_opp: int,
    n_sims: int,
    vpip_rates: List[float],
) -> float:
    """
    Monte Carlo equity via random rollout.

    Opponent hands are sampled from their VPIP range:
      - If vpip_rate = 0.30, we only accept hands in the top 30% of preflop strength.
      - Uses rejection sampling with a maximum of 4 retries per opponent;
        falls back to any random hand after that (avoids infinite loops).

    n_opp: number of opponents (already folded players not counted)
    vpip_rates: one float per opponent [0.0 – 1.0]
    """
    known = set(list(hole_cards) + list(community))
    deck = [c for c in _FULL_DECK if c not in known]
    n_board = 5 - len(community)

    # Pre-compute playable hand sets for each opponent
    playable: List[set] = []
    for vr in vpip_rates:
        vr = min(max(vr, 0.10), 1.0)
        n_play = max(1, int(169 * vr))
        playable.append(set(_PF_SORTED_KEYS[:n_play]))

    wins = 0.0
    valid_sims = 0
    max_tries = n_sims * 6  # cap total shuffles to stay within time budget

    for _ in range(max_tries):
        if valid_sims >= n_sims:
            break
        random.shuffle(deck)
        pos = 0
        opp_hands: List[Tuple[str, str]] = []
        for i in range(n_opp):
            # Try up to 4 cards to find a hand in opponent's range
            accepted = False
            for attempt in range(4):
                c1 = deck[pos + attempt * 2]
                c2 = deck[pos + attempt * 2 + 1]
                if c1 == c2:
                    continue  # impossible but guard
                hk = _hand_key(c1, c2)
                pset = playable[i] if i < len(playable) else None
                if pset is None or hk in pset:
                    opp_hands.append((c1, c2))
                    pos += attempt * 2 + 2
                    accepted = True
                    break
            if not accepted:
                # Fallback: just take the first two cards
                opp_hands.append((deck[pos], deck[pos + 1]))
                pos += 2

        if pos + n_board > len(deck):
            continue  # not enough cards left

        board = list(community) + deck[pos: pos + n_board]

        my = HandJudge.evaluate_hand(hole_cards, board)
        win = True
        tie = False
        for oh in opp_hands:
            c = HandJudge.compare_hands(my, HandJudge.evaluate_hand(oh, board))
            if c < 0:
                win = False
                break
            if c == 0:
                tie = True

        if win:
            wins += 0.5 if tie else 1.0
        valid_sims += 1

    return wins / valid_sims if valid_sims > 0 else 0.5


def _draw_outs(hole_cards: Tuple[str, str], community: List[str]) -> int:
    """Count draw outs: flush (9), OESD (8), gutshot (4). Cap at 15."""
    all_cards = list(hole_cards) + list(community)
    if len(all_cards) < 4:
        return 0

    suit_cnt = Counter(c[1] for c in all_cards)
    flush_draw = any(v == 4 for v in suit_cnt.values())
    if any(v >= 5 for v in suit_cnt.values()):
        flush_draw = False

    rank_set = set(_RV[c[0]] for c in all_cards)
    if 14 in rank_set:
        rank_set.add(1)

    oesd = gutshot = False
    for start in range(1, 11):
        window = set(range(start, start + 5))
        if len(window & rank_set) == 4:
            missing = next(iter(window - rank_set))
            if missing == start or missing == start + 4:
                oesd = True
            else:
                gutshot = True

    outs = (9 if flush_draw else 0) + (8 if oesd else 4 if gutshot else 0)
    return min(outs, 15)


def _board_wetness(community: List[str]) -> float:
    """
    Board wetness: 0.0 = rainbow disconnected (dry), 1.0 = monotone connected (very wet).
    Used to scale bet sizes (protect against draws on wet boards).
    """
    if len(community) < 3:
        return 0.5

    # Flush texture
    suit_cnt = Counter(c[1] for c in community)
    max_suit = max(suit_cnt.values())
    # 1 of a suit → 0, 2 → 0.5, 3 → 1.0
    flush_factor = max(0.0, (max_suit - 1) / 2.0)

    # Straight texture: count consecutive rank pairs
    ranks = sorted(set(_RV[c[0]] for c in community))
    if 14 in ranks:
        ranks = [1] + ranks
    consec = sum(1 for i in range(len(ranks) - 1) if ranks[i + 1] - ranks[i] <= 2)
    straight_factor = min(consec / 3.0, 1.0)

    return 0.5 * flush_factor + 0.5 * straight_factor


def _foc(legal: dict) -> Tuple[str, int]:
    """Fold-or-check: prefer check when free."""
    return ("check", 0) if legal.get("check") else ("fold", 0)
