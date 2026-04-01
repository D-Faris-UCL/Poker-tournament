"""
OmegaBot - Competitive NLHE Tournament Bot
==========================================
Tuned for UCL Poker AI Tournament:
  - 9-handed tables (qualifying + final)
  - 3-second decision time limit (generous MC budget)
  - Stage 1: fish bots present → exploit aggressively, accumulate chips
  - Stage 2: humans only, stacks normalised → tighter, ICM-aware survival play
  - Opponent stats persist from qualifying into the final table

Architecture:
  1. State parser       - reads all gamestate fields cleanly
  2. Position engine    - accurate 9-handed position (UTG/MP/HJ/CO/BTN/SB/BB)
  3. Opponent tracker   - mines hand histories + showdown reveals incrementally
  4. Equity engine      - Monte Carlo vs active opponents (uses 3s budget fully)
  5. Preflop ranges     - position-stratified 9-handed GTO chart
  6. Postflop engine    - equity + pot odds + SPR + stage mode
  7. Exploit layer      - per-opponent adjustments (fish / nit / station / maniac / TAG)
"""

import random
from collections import defaultdict
from typing import Tuple, Dict, List, Optional

from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.hand_judge import HandJudge
from src.helpers.player_judge import PlayerJudge
from src.bots.lomaan_bot.equity_calc import EquityCalculator
from src.bots.lomaan_bot.exploit import ExploitEngine
from src.bots.lomaan_bot.stats import OpponentStats
from src.bots.lomaan_bot.preflop import PreflopEngine, hand_key as preflop_hand_key
from src.bots.lomaan_bot.flop import FlopEngine
from src.bots.lomaan_bot.turn_river import TurnRiverEngine


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
HAND_RANK = {
    'high_card': 0, 'one_pair': 1, 'two_pair': 2, 'three_of_a_kind': 3,
    'straight': 4, 'flush': 5, 'full_house': 6, 'four_of_a_kind': 7,
    'straight_flush': 8, 'royal_flush': 9,
}

RANK_ORDER = '23456789TJQKA'
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, 2)}


# ---------------------------------------------------------------------------
# 9-Handed Preflop Ranges  (position-stratified)
#
# Positions by steps from button (9 players):
#   0 = BTN, 1 = CO, 2 = HJ, 3 = LJ, 4 = MP,
#   5 = UTG+2, 6 = UTG+1, 7 = UTG, 8 = BB, (n-1) = SB
#
# Range tiers:
#   EP  = UTG / UTG+1 / UTG+2  (very tight, 7+ players behind)
#   MP  = LJ / MP               (medium tight, 4-6 behind)
#   LP  = HJ / CO / BTN         (wide opens, steal pressure)
#   BB  = big blind defense      (pot-odds discount, wider call)
# ---------------------------------------------------------------------------

# EP: Premiums only. 7-8 players still to act.
EP_RAISE = {
    'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88',
    'AKs', 'AQs', 'AJs', 'ATs',
    'KQs', 'KJs',
    'AKo', 'AQo',
}
EP_CALL = set()  # No cold-calling UTG at 9-handed — raise or fold

# MP: Add medium pairs, suited broadways, AJo
MP_RAISE = EP_RAISE | {
    '77', '66',
    'A9s', 'A8s', 'KTs', 'QJs', 'QTs', 'JTs',
    'AJo', 'KQo',
}
MP_CALL = {'55', '44', '33', '22', 'T9s', '98s'}

# LP (HJ / CO / BTN): Wide opens, steal freely
LP_RAISE = MP_RAISE | {
    '55', '44', '33', '22',
    'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s',
    'T9s', '98s', '87s', '76s', '65s', '54s',
    'ATo', 'A9o', 'KJo', 'KTo', 'QJo', 'QTo', 'JTo',
}
LP_CALL = {'T8s', '97s', '86s', '75s', 'J9s'}

# BB defense (facing single open raise — pot odds discount)
BB_DEFEND_CALL = {
    '22', '33', '44', '55', '66', '77', '88', '99',
    'A2s', 'A3s', 'A4s', 'A5s', 'A6s', 'A7s', 'A8s', 'A9s',
    'K9s', 'K8s', 'Q9s', 'J8s', 'T8s', '97s', '86s', '75s', '64s', '54s',
    'AJo', 'ATo', 'A9o', 'KJo', 'QJo', 'JTo', 'KTo',
}

# 3-bet value hands (all positions)
THREEBET_VALUE = {'AA', 'KK', 'QQ', 'AKs', 'AKo'}

# LP light 3-bet bluffs (blocker / suited-ace hands)
THREEBET_BLUFFS_LP = {'A5s', 'A4s', 'A3s', 'A2s', 'KQs'}


# ---------------------------------------------------------------------------
# OpponentStats
# ---------------------------------------------------------------------------


class LomaanBot(Player):
    """
    UCL Poker AI Tournament bot — 9-handed NLHE.

    Qualifying: exploit fish bots heavily, accumulate chips above average.
    Final table: tighten up, respect stack pressure, use qualifying reads.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)

        self.opponent_stats: Dict[int, OpponentStats] = defaultdict(OpponentStats)
        self._raised_this_street: Dict[str, bool] = {}
        self._last_processed_hand: int = 0
        self._current_hole_cards: Optional[Tuple[str, str]] = None
        self._at_final_table: bool = False

        self.equity_calc = EquityCalculator()
        self.exploit_engine = ExploitEngine()
        self.preflop_engine = PreflopEngine()
        self.flop_engine = FlopEngine()
        self.turn_river_engine = TurnRiverEngine()

    # -----------------------------------------------------------------------
    # Entry point
    # -----------------------------------------------------------------------

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:

        self._current_hole_cards = hole_cards
        self._process_new_hand_histories(gamestate)
        self._detect_stage(gamestate)

        state = self._parse_state(gamestate, hole_cards)

        if state['street'] not in self._raised_this_street:
            self._raised_this_street[state['street']] = False

        if state['street'] == 'preflop':
            return self._preflop_action(state, gamestate)
        elif state['street'] == 'flop':
            state['raised_this_street'] = self._raised_this_street.get('flop', False)
            state['was_aggressor'] = self._was_preflop_aggressor(gamestate)
            return self.flop_engine.decide(state, gamestate, hole_cards, self.opponent_stats)
        elif state['street'] in ('turn', 'river'):
            state['raised_this_street'] = self._raised_this_street.get(state['street'], False)
            state['was_aggressor'] = self._was_preflop_aggressor(gamestate)
            return self.turn_river_engine.decide(state, gamestate, hole_cards, self.opponent_stats)
        else:
            return self._postflop_action(state, gamestate)

    # -----------------------------------------------------------------------
    # Stage detection
    # -----------------------------------------------------------------------

    def _detect_stage(self, gamestate: PublicGamestate):
        """
        Flip to final-table mode when fish bots are no longer present.
        Fish bots are loose-passive and get classified quickly.
        Once no fish are active and we have reads on the remaining players,
        we switch to tighter final-table play.
        """
        if self._at_final_table:
            return

        active = [
            i for i, p in enumerate(gamestate.player_public_infos)
            if not p.busted and i != self.player_index
        ]

        fish_present = any(
            self.opponent_stats[i].player_type() == 'fish'
            for i in active if i in self.opponent_stats
        )
        reads = sum(
            1 for i in active if self.opponent_stats[i].hands_seen >= 5
        )

        if not fish_present and reads >= min(3, len(active)):
            self._at_final_table = True

    # -----------------------------------------------------------------------
    # State parsing
    # -----------------------------------------------------------------------

    def _parse_state(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> dict:
        my_info = gamestate.player_public_infos[self.player_index]
        bet_to_call = gamestate.get_bet_to_call()
        amount_to_call = max(0, bet_to_call - my_info.current_bet)
        pot = gamestate.total_pot
        stack = my_info.stack
        street = gamestate.get_current_street()
        active_count = gamestate.get_active_players_count()
        bb = gamestate.blinds[1]
        spr = stack / pot if pot > 0 else 999
        bb_stack = stack / bb if bb > 0 else 100

        position, _ = self._get_position(gamestate)
        is_lp = position in ('btn', 'co', 'hj')
        is_ep = position in ('utg', 'utg1', 'utg2')
        is_mp = position in ('lj', 'mp')
        is_blind = position in ('sb', 'bb')

        legal = PlayerJudge.get_legal_actions(
            player_idx=self.player_index,
            player_infos=gamestate.player_public_infos,
            current_bet=bet_to_call,
            minimum_raise=gamestate.minimum_raise_amount
        )

        pot_odds = amount_to_call / (pot + amount_to_call) if amount_to_call > 0 else 0

        hand_name, hand_values = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
        hand_rank = HAND_RANK.get(hand_name, 0)
        equity = self._estimate_equity(hole_cards, gamestate.community_cards, active_count)

        return {
            'hole_cards': hole_cards,
            'street': street,
            'pot': pot,
            'stack': stack,
            'amount_to_call': amount_to_call,
            'pot_odds': pot_odds,
            'spr': spr,
            'bb': bb,
            'bb_stack': bb_stack,
            'short_stacked': bb_stack < 15,
            'active_count': active_count,
            'position': position,
            'is_lp': is_lp,
            'is_ep': is_ep,
            'is_mp': is_mp,
            'is_blind': is_blind,
            'legal': legal,
            'hand_name': hand_name,
            'hand_rank': hand_rank,
            'hand_values': hand_values,
            'equity': equity,
            'my_info': my_info,
            'min_raise': legal.get('min_raise') or gamestate.minimum_raise_amount,
            'max_raise': legal.get('max_raise') or stack,
            'facing_raise': amount_to_call > 0,
            'final_table': self._at_final_table,
            'depth': 'middle',  # filled in by preflop engine
        }

    # -----------------------------------------------------------------------
    # 9-Handed Position Engine
    # -----------------------------------------------------------------------

    def _get_position(self, gamestate: PublicGamestate) -> Tuple[str, int]:
        """
        Maps player index to a 9-handed position name.

        steps_from_button → position:
          0 → btn, 1 → co, 2 → hj, 3 → lj, 4 → mp,
          5 → utg2, 6 → utg1, 7 → utg, 8 → bb, (n-1) → sb
        """
        n = len(gamestate.player_public_infos)
        btn = gamestate.button_position
        steps = (self.player_index - btn) % n

        if steps == n - 1:
            return 'sb', steps

        pos_map = {
            0: 'btn', 1: 'co', 2: 'hj', 3: 'lj', 4: 'mp',
            5: 'utg2', 6: 'utg1', 7: 'utg', 8: 'bb',
        }
        return pos_map.get(steps, 'utg'), steps

    # -----------------------------------------------------------------------
    # Equity estimation  (3-second budget)
    # -----------------------------------------------------------------------

    def _estimate_equity(
        self,
        hole_cards: Tuple[str, str],
        community_cards: list,
        active_players: int,
    ) -> float:
        """
        Monte Carlo equity. Sim counts calibrated for ~2s compute,
        leaving 1s margin for history processing and decision logic.
        """
        n_opponents = max(1, active_players - 1)
        n_community = len(community_cards)

        # Base sims per street
        base = {0: 1500, 3: 1200, 4: 800, 5: 500}.get(n_community, 1200)

        # Scale down for multiway (each sim deals more cards → slower)
        if n_opponents >= 5:
            base = int(base * 0.45)
        elif n_opponents >= 3:
            base = int(base * 0.60)
        elif n_opponents >= 2:
            base = int(base * 0.78)

        return self.equity_calc.equity(
            hole_cards,
            list(community_cards),
            num_opponents=n_opponents,
            simulations=base,
        )

    # -----------------------------------------------------------------------
    # Preflop strategy  (9-handed, position-stratified)
    # -----------------------------------------------------------------------

    def _was_preflop_aggressor(self, gamestate: PublicGamestate) -> bool:
        """Check if we were the last preflop raiser."""
        if 'preflop' not in gamestate.current_hand_history:
            return False
        last_raiser = None
        for a in gamestate.current_hand_history['preflop'].actions:
            if a.action_type == 'raise':
                last_raiser = a.player_index
        return last_raiser == self.player_index

    def _preflop_action(self, state: dict, gamestate: PublicGamestate) -> Tuple[str, int]:
        """Delegates all preflop decisions to the dynamic PreflopEngine."""
        state['hand_key'] = self._hand_key(state['hole_cards'])
        return self.preflop_engine.decide(state, gamestate, self.opponent_stats)

    # -----------------------------------------------------------------------
    # Postflop strategy
    # -----------------------------------------------------------------------

    def _postflop_action(self, state: dict, gamestate: PublicGamestate) -> Tuple[str, int]:
        equity = state['equity']
        pot_odds = state['pot_odds']
        pot = state['pot']
        street = state['street']
        hand_rank = state['hand_rank']
        spr = state['spr']
        facing_raise = state['facing_raise']
        raised_already = self._raised_this_street.get(street, False)
        is_lp = state['is_lp']
        final_table = state['final_table']
        multiway = state['active_count'] > 2

        # Exploit adjustments
        adjust = self._get_main_exploit(gamestate, facing_raise)
        eff_pot_odds = pot_odds + adjust.equity_threshold_shift
        bluff_mult = adjust.bluff_frequency_mult
        size_mult = adjust.bet_size_multiplier

        # Multiway: much less bluffing
        if multiway:
            bluff_mult *= 0.35

        # Final table: reduce bluff frequency
        if final_table:
            bluff_mult *= 0.65

        # --- MONSTERS (full house+) ---
        if hand_rank >= 6:
            if not facing_raise and not raised_already:
                # Occasionally trap to balance
                if spr > 4 and random.random() < 0.20:
                    return ('check', 0)
                size = int(pot * 1.1 * size_mult)
                return self._make_raise(size, state)
            if facing_raise and not raised_already and spr > 1.5:
                return self._make_raise(int(pot * 2.8), state)
            return ('call', 0)

        # --- STRONG MADE HANDS (straight / flush / trips) ---
        if hand_rank >= 3:
            if not facing_raise and not raised_already:
                size = int(pot * 0.85 * size_mult)
                return self._make_raise(size, state)
            if facing_raise:
                if not raised_already and spr > 2:
                    return self._make_raise(int(pot * 2.5), state)
                return ('call', 0)

        # --- TWO PAIR ---
        if hand_rank == 2:
            if not facing_raise and not raised_already:
                size = int(pot * 0.65 * size_mult)
                return self._make_raise(size, state)
            if facing_raise:
                if multiway and equity < 0.55:
                    return ('fold', 0)
                return ('call', 0)

        # --- ONE PAIR ---
        if hand_rank == 1:
            if not facing_raise:
                bet_freq = 0.50 if is_lp else 0.30
                if not raised_already and random.random() < bet_freq * bluff_mult:
                    size = int(pot * 0.45 * size_mult)
                    return self._make_raise(size, state)
                return ('check', 0)
            else:
                if equity > eff_pot_odds + 0.06:
                    return ('call', 0)
                return ('fold', 0)

        # --- DRAWS (equity > 30%) ---
        if equity > 0.30:
            if not facing_raise:
                if street in ('flop', 'turn') and not raised_already and is_lp:
                    if random.random() < 0.48 * bluff_mult:
                        size = int(pot * 0.55 * size_mult)
                        return self._make_raise(size, state)
                return ('check', 0)
            else:
                if equity > eff_pot_odds + 0.05:
                    return ('call', 0)
                return ('fold', 0)

        # --- PURE POT-ODDS CALL ---
        if equity > eff_pot_odds + 0.04:
            return ('call', 0)

        # --- AIR ---
        if not facing_raise:
            if (street == 'river' and is_lp and not raised_already
                    and not multiway and random.random() < 0.20 * bluff_mult):
                size = int(pot * 0.60 * size_mult)
                return self._make_raise(size, state)
            return ('check', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Exploit layer
    # -----------------------------------------------------------------------

    def _get_main_exploit(self, gamestate: PublicGamestate, facing_bet: bool):
        """Return exploit adjustment for the most-read active opponent."""
        from src.bots.lomaan_bot.exploit import StrategyAdjustment
        best_idx, best_hands = None, 0
        for idx, stats in self.opponent_stats.items():
            info = gamestate.player_public_infos[idx]
            if not info.busted and info.active and stats.hands_seen > best_hands:
                best_hands = stats.hands_seen
                best_idx = idx

        if best_idx is None:
            return StrategyAdjustment()

        return self.exploit_engine.get_adjustment(
            self.opponent_stats[best_idx],
            street='',
            facing_bet=facing_bet,
            we_are_aggressor=not facing_bet,
        )

    # -----------------------------------------------------------------------
    # Opponent tracking
    # -----------------------------------------------------------------------

    def _process_new_hand_histories(self, gamestate: PublicGamestate):
        """Incrementally mine newly completed hands."""
        histories = gamestate.previous_hand_histories
        for record in histories[self._last_processed_hand:]:
            self._process_one_hand(record)
        self._last_processed_hand = len(histories)

    def _process_one_hand(self, hand_record):
        per_street = hand_record.per_street

        if 'preflop' in per_street:
            seen = set()
            for action in per_street['preflop'].actions:
                idx = action.player_index
                if idx == self.player_index:
                    continue
                stats = self.opponent_stats[idx]
                if idx not in seen:
                    stats.hands_seen += 1
                    seen.add(idx)
                if action.action_type in ('call', 'raise'):
                    stats.vpip += 1
                if action.action_type == 'raise':
                    stats.pfr += 1

        for _, street_hist in per_street.items():
            for action in street_hist.actions:
                idx = action.player_index
                if idx == self.player_index:
                    continue
                stats = self.opponent_stats[idx]
                if action.action_type == 'raise':
                    stats.aggression_count += 1
                elif action.action_type in ('call', 'check'):
                    stats.passive_count += 1

        if hand_record.showdown_details:
            details = hand_record.showdown_details
            for pidx in details.get('players', []):
                if pidx == self.player_index:
                    continue
                cards = details['hole_cards'].get(pidx)
                if cards:
                    self.opponent_stats[pidx].showdown_hands.append(cards)

    def get_opponent_type(self, player_idx: int) -> str:
        if player_idx not in self.opponent_stats:
            return 'unknown'
        return self.opponent_stats[player_idx].player_type()

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _make_raise(self, amount: int, state: dict) -> Tuple[str, int]:
        """Safely clamp raise to legal range."""
        street = state['street']
        min_r, max_r = state['min_raise'], state['max_raise']
        stack = state['stack']

        if amount >= stack or amount >= max_r:
            self._raised_this_street[street] = True
            return ('all-in', 0)

        amount = max(amount, min_r)
        amount = min(amount, max_r)
        self._raised_this_street[street] = True
        return ('raise', amount)

    def _hand_key(self, hole_cards: Tuple[str, str]) -> str:
        """
        Canonical 169-bucket hand key.
        ('Ah','Kd') → 'AKo'  |  ('9h','8h') → '98s'  |  ('7h','7c') → '77'
        """
        c1, c2 = hole_cards
        r1, r2, s1, s2 = c1[0], c2[0], c1[1], c2[1]
        v1, v2 = RANK_VALUE.get(r1, 2), RANK_VALUE.get(r2, 2)

        if v1 < v2:
            r1, r2, s1, s2 = r2, r1, s2, s1

        if r1 == r2:
            return f'{r1}{r2}'

        return f'{r1}{r2}{"s" if s1 == s2 else "o"}'