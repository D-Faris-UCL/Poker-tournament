"""
Dynamic Preflop Engine  v3
===========================
New in v3:
  1. LIMP HANDLING
     - Iso-raise over limpers (bigger sizing, wider range)
     - Limp-behind in LP with speculative hands when pot odds justify
     - Never limp from EP/MP — raise or fold

  2. EFFECTIVE STACK / JAM SIZING
     - Tracks effective stack (min of our stack vs villain stack)
     - Short opener (<20bb) changes everything — jamming AQo on BTN vs 13bb HJ is correct
     - SPR-aware: if calling a raise commits >33% of stack, evaluate as a shove/fold decision

  3. STACK DEPTH MODES  (relative to TABLE AVERAGE, only when avg > 30bb)
     - DEEP   (> table average):        loosen significantly, more broadway, speculative hands
     - MIDDLE (= table average ±):      current strategy baseline
     - SHORT  (< avg, >25bb):           tighten slightly
     - DANGER (15-25bb):                tighten meaningfully
     - PUSH_FOLD (<15bb):               push/fold only

  4. WIDER BROADWAY RANGES
     - KQo always raises CO/BTN/SB
     - KQs always raises from MP onwards
     - KTo/QTo/JTo included with full frequency LP
     - QTs full frequency HJ onwards
     - Broadway gaps (KJo, QJo, KTo) opened wider

  5. GAPPED HAND FREQUENCIES INCREASED
     - KJo/QJo now open more freely
     - One-gap suited hands (T8s, J9s, 97s) defended wider

  6. PUSH/FOLD RANGE WITH ACTION AWARENESS
     - All pocket pairs push
     - A6s+ push, A9o+ push
     - KJs+, KQo push
     - Steal jams (LP, limited action): JTs, T9s, 87s, 76s at frequency
     - Facing a raise: tighten to premiums only for call-jam
     - Facing 3bet/squeeze: even tighter
"""

import random
from typing import Tuple, Dict, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.bots.lomaan_bot.stats import OpponentStats

RANK_ORDER = '23456789TJQKA'
RANK_VALUE  = {r: i for i, r in enumerate(RANK_ORDER, 2)}

# ---------------------------------------------------------------------------
# Frequency constants
# ---------------------------------------------------------------------------
ALWAYS    = 1.00
OFTEN     = 0.75
MIXED     = 0.50
SOMETIMES = 0.35
RARELY    = 0.20
NEVER     = 0.00

# ---------------------------------------------------------------------------
# Stack depth thresholds
# ---------------------------------------------------------------------------
DEEP_THRESHOLD   = 1.20   # > 120% of table average → deep
SHORT_THRESHOLD  = 0.85   # < 85% of table average → short
DANGER_BB_LOW    = 15
DANGER_BB_HIGH   = 25
PUSH_FOLD_BB     = 15
MIN_AVG_FOR_DEPTH_ADJUST = 30  # Only adjust when table avg > 30bb

# ---------------------------------------------------------------------------
# Open-raise ranges  (hand -> frequency)
# ---------------------------------------------------------------------------

UTG_OPEN = {
    'AA':1.0,'KK':1.0,'QQ':1.0,'JJ':1.0,'TT':1.0,'99':1.0,'88':1.0,
    'AKs':1.0,'AQs':1.0,'AJs':1.0,'ATs':1.0,'KQs':1.0,'KJs':1.0,
    'AKo':1.0,'AQo':1.0,
    '77':OFTEN,'AJo':SOMETIMES,'KTs':OFTEN,'QJs':OFTEN,'QTs':SOMETIMES,
}

UTG1_OPEN = {**UTG_OPEN,
    '77':1.0,'66':OFTEN,'KTs':1.0,'QJs':1.0,'QTs':OFTEN,'JTs':OFTEN,
    'AJo':OFTEN,'KQo':OFTEN,'A9s':SOMETIMES,
}

UTG2_OPEN = {**UTG1_OPEN,
    '66':1.0,'55':SOMETIMES,'QTs':1.0,'JTs':1.0,'T9s':SOMETIMES,
    'A9s':OFTEN,'A8s':SOMETIMES,'AJo':1.0,'KQo':1.0,'KJo':SOMETIMES,
}

LJ_OPEN = {**UTG2_OPEN,
    '55':OFTEN,'44':SOMETIMES,'T9s':OFTEN,'98s':SOMETIMES,
    'A8s':OFTEN,'A7s':SOMETIMES,'KJo':OFTEN,'QJo':SOMETIMES,'KTo':SOMETIMES,
}

MP_OPEN = {**LJ_OPEN,
    '44':OFTEN,'33':SOMETIMES,'98s':OFTEN,'87s':SOMETIMES,
    'A7s':OFTEN,'A6s':SOMETIMES,'KJo':1.0,'QJo':OFTEN,
    'QTo':SOMETIMES,'JTo':SOMETIMES,'KTo':OFTEN,
}

HJ_OPEN = {**MP_OPEN,
    '33':OFTEN,'22':SOMETIMES,'87s':OFTEN,'76s':OFTEN,'65s':SOMETIMES,'54s':SOMETIMES,
    'A6s':OFTEN,'A5s':OFTEN,'A4s':SOMETIMES,'A3s':SOMETIMES,'A2s':SOMETIMES,
    'K9s':OFTEN,'Q9s':SOMETIMES,'J9s':SOMETIMES,
    'QJo':1.0,'QTo':OFTEN,'JTo':OFTEN,'KTo':1.0,'KQo':1.0,
    'A8o':SOMETIMES,'A7o':SOMETIMES,'T9s':1.0,'98s':1.0,
}

CO_OPEN = {**HJ_OPEN,
    '22':OFTEN,'65s':OFTEN,'54s':OFTEN,'43s':SOMETIMES,
    'A4s':OFTEN,'A3s':OFTEN,'A2s':OFTEN,
    'K9s':1.0,'Q9s':OFTEN,'J9s':OFTEN,'T8s':SOMETIMES,
    'A8o':OFTEN,'A7o':OFTEN,'A6o':SOMETIMES,
    'KQo':1.0,'KTo':1.0,'QTo':1.0,'JTo':1.0,
    'K8s':SOMETIMES,'Q8s':SOMETIMES,
}

BTN_OPEN = {**CO_OPEN,
    '22':1.0,'33':1.0,'43s':OFTEN,'32s':SOMETIMES,
    'T8s':OFTEN,'97s':OFTEN,'86s':SOMETIMES,'75s':SOMETIMES,
    'K8s':OFTEN,'K7s':SOMETIMES,'Q8s':OFTEN,'J8s':SOMETIMES,
    'A5o':SOMETIMES,'A6o':OFTEN,'A7o':1.0,'A8o':1.0,'A9o':1.0,
    'K9o':SOMETIMES,'Q9o':SOMETIMES,'KQo':1.0,
}

SB_OPEN = {
    'AA':1.0,'KK':1.0,'QQ':1.0,'JJ':1.0,'TT':1.0,'99':1.0,'88':1.0,'77':1.0,'66':OFTEN,
    'AKs':1.0,'AQs':1.0,'AJs':1.0,'ATs':1.0,'A9s':1.0,'A8s':OFTEN,'A7s':OFTEN,
    'A5s':OFTEN,'A4s':SOMETIMES,'A3s':SOMETIMES,'A2s':SOMETIMES,
    'KQs':1.0,'KJs':1.0,'KTs':1.0,'K9s':OFTEN,
    'QJs':1.0,'QTs':OFTEN,'Q9s':SOMETIMES,
    'JTs':1.0,'J9s':OFTEN,'T9s':OFTEN,'98s':OFTEN,'87s':SOMETIMES,'76s':SOMETIMES,
    'AKo':1.0,'AQo':1.0,'AJo':1.0,'ATo':1.0,'A9o':OFTEN,'A8o':SOMETIMES,
    'KQo':1.0,'KJo':1.0,'KTo':OFTEN,'QJo':OFTEN,'QTo':SOMETIMES,'JTo':SOMETIMES,
    '55':SOMETIMES,'44':SOMETIMES,
}

# Deep stack additions (when we're > 120% of table average)
DEEP_OPEN_EXTRAS = {
    # Extra hands added to LP ranges when deep
    'hj': {'K8s':SOMETIMES,'Q8s':SOMETIMES,'J8s':SOMETIMES,'T8s':OFTEN,'86s':SOMETIMES,'K9o':SOMETIMES},
    'co': {'K7s':SOMETIMES,'97s':OFTEN,'86s':OFTEN,'75s':SOMETIMES,'64s':SOMETIMES,'K9o':OFTEN,'Q9o':SOMETIMES},
    'btn': {'K6s':SOMETIMES,'Q7s':SOMETIMES,'J7s':SOMETIMES,'96s':SOMETIMES,'85s':SOMETIMES,'74s':SOMETIMES,'Q9o':OFTEN,'J9o':SOMETIMES,'T8o':SOMETIMES},
    'sb': {'K8o':SOMETIMES,'J8s':SOMETIMES,'T7s':SOMETIMES},
}

# ---------------------------------------------------------------------------
# Iso-raise sizing over limpers
# ---------------------------------------------------------------------------
# Standard open is 2.2-3x BB. Over limpers: add 1BB per limper

def iso_raise_size(bb: int, n_limpers: int, position: str) -> int:
    """Raise sizing when there are limpers in the pot."""
    base_mult = 3.0 if position in ('utg','utg1','utg2') else 2.5
    return int(bb * (base_mult + n_limpers))

# Hands that iso-raise over limpers (wider than cold open due to dead money)
ISO_RAISE_RANGE = {
    # All standard open hands plus:
    'KQo':1.0,'KJo':OFTEN,'QJo':OFTEN,'KTo':OFTEN,'QTo':SOMETIMES,'JTo':SOMETIMES,
    'A9o':OFTEN,'A8o':SOMETIMES,'A7o':SOMETIMES,
    'T9s':1.0,'98s':1.0,'87s':OFTEN,'76s':OFTEN,'65s':SOMETIMES,
    'K9s':1.0,'Q9s':OFTEN,'J9s':OFTEN,'T8s':OFTEN,
}

# Hands that limp-behind in LP (speculative, want to see cheap flop)
LIMP_BEHIND_LP = {
    '22':OFTEN,'33':OFTEN,'44':OFTEN,  # Set mining
    '54s':OFTEN,'43s':SOMETIMES,        # Low connectors
    'T8s':SOMETIMES,'97s':SOMETIMES,    # One-gappers
}

# ---------------------------------------------------------------------------
# 3bet / bluff ranges
# ---------------------------------------------------------------------------
THREEBET_VALUE  = {'AA':1.0,'KK':1.0,'QQ':1.0,'AKs':1.0,'AKo':1.0}
THREEBET_STRONG = {'JJ':OFTEN,'TT':SOMETIMES,'AQs':OFTEN,'AQo':SOMETIMES,'KQs':OFTEN}
THREEBET_BLUFFS = {
    'A5s':MIXED,'A4s':MIXED,'A3s':SOMETIMES,'A2s':SOMETIMES,
    'KQs':SOMETIMES,'JTs':SOMETIMES,'T9s':SOMETIMES,
}

# ---------------------------------------------------------------------------
# Call ranges vs single raise
# ---------------------------------------------------------------------------
EP_CALL_VS_RAISE = {
    'JJ':1.0,'TT':1.0,'99':OFTEN,'88':SOMETIMES,
    'AQs':1.0,'AJs':1.0,'ATs':OFTEN,'A9s':SOMETIMES,
    'KQs':1.0,'KJs':OFTEN,'KTs':SOMETIMES,
    'QJs':SOMETIMES,'JTs':SOMETIMES,
    'AQo':1.0,'AJo':OFTEN,
}

UTG2_CALL_VS_RAISE = {**EP_CALL_VS_RAISE,
    'AJo':1.0,'KQo':OFTEN,
    '77':OFTEN,'66':SOMETIMES,
    'QTs':SOMETIMES,'T9s':SOMETIMES,
}

MP_CALL_VS_RAISE = {**UTG2_CALL_VS_RAISE,
    '77':1.0,'66':OFTEN,'55':SOMETIMES,
    'A8s':SOMETIMES,'KTs':OFTEN,'KQo':1.0,'QJo':SOMETIMES,
}

LP_CALL_VS_RAISE = {**MP_CALL_VS_RAISE,
    '55':OFTEN,'44':SOMETIMES,'33':SOMETIMES,
    'A8s':OFTEN,'A7s':SOMETIMES,'A6s':SOMETIMES,'A5s':OFTEN,
    'K9s':OFTEN,'Q9s':SOMETIMES,'J9s':SOMETIMES,'T8s':SOMETIMES,
    '98s':OFTEN,'87s':OFTEN,'76s':SOMETIMES,'65s':SOMETIMES,
    'ATo':OFTEN,'A9o':SOMETIMES,'KJo':1.0,'KTo':OFTEN,'QJo':1.0,
    'KQo':1.0,'QTo':SOMETIMES,
}

BB_CALL_VS_RAISE = {
    '22':OFTEN,'33':OFTEN,'44':1.0,'55':1.0,'66':1.0,'77':1.0,'88':1.0,'99':1.0,
    'A2s':OFTEN,'A3s':OFTEN,'A4s':1.0,'A5s':1.0,'A6s':1.0,'A7s':1.0,'A8s':1.0,'A9s':1.0,
    'AJs':1.0,'ATs':1.0,'KQs':1.0,'KJs':1.0,'KTs':1.0,'QJs':1.0,'QTs':1.0,
    'JTs':1.0,'T9s':1.0,'J9s':1.0,
    '98s':1.0,'87s':1.0,'76s':1.0,'65s':OFTEN,'54s':OFTEN,
    'T8s':OFTEN,'97s':OFTEN,'86s':OFTEN,'75s':SOMETIMES,'64s':SOMETIMES,
    'K9s':1.0,'K8s':OFTEN,'Q9s':OFTEN,'Q8s':SOMETIMES,'J8s':SOMETIMES,
    'AJo':1.0,'ATo':1.0,'A9o':1.0,'A8o':OFTEN,'A7o':SOMETIMES,
    'KQo':1.0,'KJo':1.0,'KTo':OFTEN,'QJo':1.0,'QTo':OFTEN,'JTo':OFTEN,
}

SB_CALL_VS_RAISE = {
    'JJ':1.0,'TT':1.0,'99':OFTEN,'88':SOMETIMES,
    'AQs':1.0,'AJs':OFTEN,'ATs':OFTEN,'A9s':SOMETIMES,
    'KQs':1.0,'KJs':OFTEN,'QJs':SOMETIMES,'JTs':SOMETIMES,
    'AQo':OFTEN,'AJo':SOMETIMES,'KQo':OFTEN,
    '77':SOMETIMES,'66':SOMETIMES,
}

# vs tight EP opener: fold these even if in your range
FOLD_VS_TIGHT_EP = frozenset({
    '76s','75s','65s','64s','54s','53s','43s',
    'T8s','97s','86s','75s',
    '22','33','44',
    'K8s','Q9s','J8s','Q8s',
    'A6o','A5o','A7o',
})

# vs wide LP opener: add these to BB defence
WIDE_BB_EXTRA = frozenset({
    '43s','53s','63s','32s',
    'K7s','K6s','Q8s','J7s',
    'A6o','A5o','22',
})

# ---------------------------------------------------------------------------
# Facing 3bet / 4bet
# ---------------------------------------------------------------------------
CALL_VS_3BET   = {'AA':1.0,'KK':1.0,'QQ':OFTEN,'JJ':OFTEN,'TT':SOMETIMES,'99':SOMETIMES,'AKs':1.0,'AQs':OFTEN,'AKo':1.0,'AQo':SOMETIMES,'KQs':SOMETIMES}
FOURBET_VS_3BET = {'AA':1.0,'KK':1.0,'QQ':OFTEN,'AKs':1.0,'AKo':1.0}
BLUFF_4BET     = {'A5s':SOMETIMES,'A4s':SOMETIMES}
CALL_VS_4BET   = {'AA':1.0,'KK':1.0,'QQ':SOMETIMES,'AKs':OFTEN,'AKo':SOMETIMES}

# ---------------------------------------------------------------------------
# Push/fold ranges  (< 15bb)
# ---------------------------------------------------------------------------
# Base push range — all situations
PUSH_BASE = {
    # All pairs
    'AA':1.0,'KK':1.0,'QQ':1.0,'JJ':1.0,'TT':1.0,'99':1.0,'88':1.0,'77':1.0,'66':1.0,'55':1.0,'44':1.0,'33':OFTEN,'22':OFTEN,
    # Ax suited A6s+
    'AKs':1.0,'AQs':1.0,'AJs':1.0,'ATs':1.0,'A9s':1.0,'A8s':1.0,'A7s':1.0,'A6s':1.0,
    # Ax offsuit A9o+
    'AKo':1.0,'AQo':1.0,'AJo':1.0,'ATo':1.0,'A9o':1.0,
    # Kx
    'KQs':1.0,'KJs':1.0,'KTs':OFTEN,'KQo':1.0,'KJo':OFTEN,
}

# Extra steal-jam hands in LP with limited action (no raises, 0-1 callers)
STEAL_JAM_LP = {
    'JTs':OFTEN,'T9s':OFTEN,'98s':SOMETIMES,'87s':SOMETIMES,'76s':SOMETIMES,
    'A5s':OFTEN,'A4s':OFTEN,'A3s':SOMETIMES,'A2s':SOMETIMES,
    'KTo':SOMETIMES,'QJo':SOMETIMES,
}

# Facing a raise: tighten push range to premiums
PUSH_VS_RAISE = {
    'AA':1.0,'KK':1.0,'QQ':1.0,'JJ':1.0,'TT':1.0,'99':OFTEN,
    'AKs':1.0,'AQs':1.0,'AJs':OFTEN,'ATs':SOMETIMES,
    'AKo':1.0,'AQo':OFTEN,'AJo':SOMETIMES,
    'KQs':OFTEN,'KQo':SOMETIMES,
}

# Facing 3bet/squeeze: only absolute premiums
PUSH_VS_3BET = {
    'AA':1.0,'KK':1.0,'QQ':OFTEN,'AKs':1.0,'AKo':1.0,'JJ':SOMETIMES,
}

# ---------------------------------------------------------------------------
# Squeeze bluff hands
# ---------------------------------------------------------------------------
SQUEEZE_BLUFF_HANDS = frozenset({
    'A5s','A4s','A3s','A2s','A6s','A7s',
    'KQs','K9s','KTs',
    'JTs','T9s','98s','87s',
})

TRAP_HANDS = frozenset({'AA','KK'})


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

class PreflopEngine:

    def decide(
        self,
        state: dict,
        gamestate,
        opponent_stats: Dict[int, 'OpponentStats'],
    ) -> Tuple[str, int]:

        hand_key  = state['hand_key']
        bb        = state['bb']
        position  = state['position']

        # Compute stack depth mode
        depth = self._stack_depth_mode(state, gamestate)
        state['depth'] = depth

        # Push/fold territory
        if state['bb_stack'] <= PUSH_FOLD_BB:
            return self._push_fold(hand_key, state, gamestate)

        # Count raises and limpers
        num_raises  = self._count_raises(gamestate)
        num_limpers = self._count_limpers(gamestate)
        situation   = self._analyse_situation(state, gamestate, opponent_stats)
        situation['num_limpers'] = num_limpers

        if num_raises == 0:
            if num_limpers > 0:
                return self._facing_limpers(hand_key, state, situation)
            else:
                return self._no_raise(hand_key, state, situation)
        elif num_raises == 1:
            # Check if calling commits too much stack → treat as jam decision
            if self._should_jam_instead_of_call(state, situation):
                return self._jam_vs_short_opener(hand_key, state, situation)
            return self._vs_single_raise(hand_key, state, situation, opponent_stats)
        elif num_raises == 2:
            return self._vs_threebet(hand_key, state, situation)
        else:
            return self._vs_fourbet_plus(hand_key, state)

    # -----------------------------------------------------------------------
    # Stack depth mode
    # -----------------------------------------------------------------------

    def _stack_depth_mode(self, state: dict, gamestate) -> str:
        """
        Compare our stack to table average.
        Only adjusts when table average > 30bb.
        Returns: 'deep' | 'middle' | 'short' | 'danger' | 'push_fold'
        """
        bb_stack = state['bb_stack']

        if bb_stack <= PUSH_FOLD_BB:
            return 'push_fold'
        if bb_stack <= DANGER_BB_HIGH:
            return 'danger'

        # Calculate table average
        infos = gamestate.player_public_infos
        bb    = state['bb']
        alive = [p.stack for p in infos if not p.busted and p.stack > 0]
        if not alive:
            return 'middle'

        avg_stack = sum(alive) / len(alive)
        avg_bb    = avg_stack / bb if bb > 0 else 100

        # Only adjust if table average is meaningful
        if avg_bb < MIN_AVG_FOR_DEPTH_ADJUST:
            return 'middle'

        ratio = state['stack'] / avg_stack if avg_stack > 0 else 1.0

        if ratio > DEEP_THRESHOLD:
            return 'deep'
        elif ratio < SHORT_THRESHOLD:
            return 'short'
        else:
            return 'middle'

    # -----------------------------------------------------------------------
    # Count raises and limpers
    # -----------------------------------------------------------------------

    def _count_raises(self, gamestate) -> int:
        count = 0
        if 'preflop' not in gamestate.current_hand_history:
            return 0
        for a in gamestate.current_hand_history['preflop'].actions:
            if a.action_type == 'raise':
                count += 1
        return count

    def _count_limpers(self, gamestate) -> int:
        """Count players who called the big blind (limped) without a raise following."""
        if 'preflop' not in gamestate.current_hand_history:
            return 0
        limpers = 0
        raised = False
        for a in gamestate.current_hand_history['preflop'].actions:
            if a.action_type == 'raise':
                raised = True
            elif a.action_type == 'call' and not raised:
                limpers += 1
        return 0 if raised else limpers

    # -----------------------------------------------------------------------
    # Situation analysis
    # -----------------------------------------------------------------------

    def _analyse_situation(self, state, gamestate, opponent_stats) -> dict:
        actions = []
        if 'preflop' in gamestate.current_hand_history:
            actions = gamestate.current_hand_history['preflop'].actions

        opener_idx = None
        callers    = []
        raisers    = []

        for a in actions:
            if a.action_type in ('small_blind','big_blind'):
                continue
            if a.action_type == 'raise':
                if opener_idx is None:
                    opener_idx = a.player_index
                raisers.append(a.player_index)
            elif a.action_type == 'call' and opener_idx is not None:
                callers.append(a.player_index)

        opener_stats    = opponent_stats.get(opener_idx) if opener_idx else None
        opener_pfr      = opener_stats.pfr_pct  if (opener_stats and opener_stats.hands_seen >= 8) else 0.20
        opener_vpip     = opener_stats.vpip_pct if (opener_stats and opener_stats.hands_seen >= 8) else 0.25
        opener_position = self._get_player_position(opener_idx, gamestate) if opener_idx else None

        # Effective stack between us and opener
        eff_stack = self._effective_stack(state, gamestate, opener_idx)

        return {
            'opener_idx':       opener_idx,
            'opener_position':  opener_position,
            'opener_pfr':       opener_pfr,
            'opener_vpip':      opener_vpip,
            'opener_stack_bb':  eff_stack / state['bb'] if state['bb'] > 0 else 100,
            'callers':          callers,
            'num_callers':      len(callers),
            'num_raisers':      len(raisers),
            'is_squeeze':       opener_idx is not None and len(callers) >= 1,
            'opener_is_tight':  opener_pfr < 0.15,
            'opener_is_wide':   opener_pfr > 0.26,
            'opener_is_fish':   opener_vpip > 0.50 and opener_pfr < 0.12,
            'opener_is_lp':     opener_position in ('btn','co','hj') if opener_position else False,
            'opener_is_ep':     opener_position in ('utg','utg1','utg2') if opener_position else False,
            'eff_stack_bb':     eff_stack / state['bb'] if state['bb'] > 0 else 100,
        }

    def _effective_stack(self, state, gamestate, opponent_idx) -> int:
        """Effective stack = min(our stack, opponent stack). Defaults to our stack if unknown."""
        if opponent_idx is None:
            return state['stack']
        try:
            opp_stack = gamestate.player_public_infos[opponent_idx].stack
            return min(state['stack'], opp_stack)
        except (IndexError, AttributeError):
            return state['stack']

    def _get_player_position(self, player_idx, gamestate) -> str:
        n    = len(gamestate.player_public_infos)
        btn  = gamestate.button_position
        steps = (player_idx - btn) % n
        if steps == n - 1:
            return 'sb'
        return {0:'btn',1:'co',2:'hj',3:'lj',4:'mp',5:'utg2',6:'utg1',7:'utg',8:'bb'}.get(steps,'utg')

    # -----------------------------------------------------------------------
    # Jam vs short opener
    # -----------------------------------------------------------------------

    def _should_jam_instead_of_call(self, state: dict, situation: dict) -> bool:
        """
        If calling a raise commits more than 33% of our stack, or if the
        effective stack is short (<20bb), evaluate as shove/fold not call/fold.
        Classic example: BTN with AQo vs 13bb HJ open — just jam.
        """
        eff_bb     = situation.get('eff_stack_bb', 100)
        call_cost  = state['amount_to_call']
        our_stack  = state['stack']

        # Short effective stack
        if eff_bb <= 20:
            return True

        # Calling commits > 33% of stack → treat as commit decision
        if our_stack > 0 and call_cost / our_stack > 0.33:
            return True

        return False

    def _jam_vs_short_opener(self, hand_key: str, state: dict, situation: dict) -> Tuple[str, int]:
        """
        Short effective stack scenario.
        Jam with strong hands, fold the rest. No point calling — either commit or fold.
        The jam range scales with effective stack depth.
        """
        eff_bb       = situation.get('eff_stack_bb', 20)
        is_lp        = state['is_lp']
        is_blind     = state['is_blind']
        opener_is_tight = situation['opener_is_tight']

        # Build jam range for this scenario
        jam = dict(PUSH_VS_RAISE)

        # Wider jam vs short/wide opener
        if not opener_is_tight and eff_bb <= 15:
            jam.update({'88':1.0,'77':OFTEN,'66':SOMETIMES,'A9s':OFTEN,'A8s':SOMETIMES,'KQo':OFTEN})

        # LP/blind can jam slightly wider
        if (is_lp or is_blind) and eff_bb <= 18:
            jam.update({'TT':1.0,'99':1.0,'AJs':1.0,'AQo':1.0})

        freq = jam.get(hand_key, NEVER)
        if random.random() < freq:
            return ('all-in', 0)
        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Facing limpers
    # -----------------------------------------------------------------------

    def _facing_limpers(self, hand_key: str, state: dict, situation: dict) -> Tuple[str, int]:
        """
        When there are limpers:
          - Iso-raise with strong hands + dead money range (wider than cold open)
          - Limp behind in LP with set-mining / speculative hands
          - Never limp from EP/MP — raise or fold
        """
        position    = state['position']
        bb          = state['bb']
        num_limpers = situation['num_limpers']
        is_lp       = state['is_lp']
        is_ep       = state['is_ep']
        is_mp       = position in ('lj','mp')
        depth       = state['depth']

        # Select base open range for position
        open_map = {
            'utg':UTG_OPEN,'utg1':UTG1_OPEN,'utg2':UTG2_OPEN,
            'lj':LJ_OPEN,'mp':MP_OPEN,'hj':HJ_OPEN,
            'co':CO_OPEN,'btn':BTN_OPEN,'sb':SB_OPEN,
        }
        base_range = open_map.get(position, UTG_OPEN)

        # Iso-raise range = base open range + ISO_RAISE_RANGE extras
        iso_range = {**base_range}
        if is_lp or position in ('sb',):
            for h, f in ISO_RAISE_RANGE.items():
                iso_range[h] = max(iso_range.get(h, NEVER), f)

        # Apply depth adjustments
        iso_freq = self._depth_adjust(iso_range.get(hand_key, NEVER), depth, hand_key)

        if random.random() < iso_freq:
            size = iso_raise_size(bb, num_limpers, position)
            return self._make_raise(size, state)

        # LP limp-behind with speculative hands
        if is_lp and hand_key in LIMP_BEHIND_LP:
            limp_freq = LIMP_BEHIND_LP[hand_key]
            if depth == 'deep':
                limp_freq = min(ALWAYS, limp_freq * 1.3)
            if random.random() < limp_freq:
                return ('call', 0)

        # BB checks for free
        if position == 'bb':
            return ('check', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # No raise — opening
    # -----------------------------------------------------------------------

    def _no_raise(self, hand_key: str, state: dict, situation: dict) -> Tuple[str, int]:
        position  = state['position']
        bb        = state['bb']
        final_table = state['final_table']
        depth     = state['depth']

        if position == 'bb':
            return ('check', 0)

        open_map = {
            'utg':UTG_OPEN,'utg1':UTG1_OPEN,'utg2':UTG2_OPEN,
            'lj':LJ_OPEN,'mp':MP_OPEN,'hj':HJ_OPEN,
            'co':CO_OPEN,'btn':BTN_OPEN,'sb':SB_OPEN,
        }
        open_range = open_map.get(position, UTG_OPEN)

        if final_table and position in ('utg','utg1','utg2','lj','mp'):
            open_range = UTG_OPEN

        # Deep: add extra hands
        if depth == 'deep' and position in DEEP_OPEN_EXTRAS:
            open_range = {**open_range, **DEEP_OPEN_EXTRAS[position]}

        freq = self._depth_adjust(open_range.get(hand_key, NEVER), depth, hand_key)

        if random.random() < freq:
            if position in ('utg','utg1','utg2'):
                size = int(bb * 3.0)
            elif position in ('btn','co','hj','sb'):
                size = int(bb * 2.2)
            else:
                size = int(bb * 2.5)
            return self._make_raise(size, state)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Depth adjustment multiplier
    # -----------------------------------------------------------------------

    def _depth_adjust(self, base_freq: float, depth: str, hand_key: str = '') -> float:
        """
        Apply stack depth multiplier to a base frequency.
        Deep → loosen, Short/Danger → tighten.
        IMPORTANT: Never reduce hands that are already ALWAYS (1.0).
        Premium hands play regardless of stack depth — only marginal
        hands should be affected by tightening.
        """
        if depth == 'deep':
            return min(ALWAYS, base_freq * 1.35)
        # Never tighten hands that are unconditional — AA/KK/QQ etc always play
        if base_freq >= ALWAYS:
            return base_freq
        if depth == 'short':
            return base_freq * 0.80
        elif depth == 'danger':
            return base_freq * 0.60
        return base_freq

    # -----------------------------------------------------------------------
    # Facing a single raise
    # -----------------------------------------------------------------------

    def _vs_single_raise(self, hand_key, state, situation, opponent_stats) -> Tuple[str, int]:
        position        = state['position']
        is_lp           = state['is_lp']
        is_ep           = state['is_ep']
        is_blind        = state['is_blind']
        bb              = state['bb']
        pot             = state['pot']
        amount_to_call  = state['amount_to_call']
        final_table     = state['final_table']
        depth           = state['depth']
        is_squeeze      = situation['is_squeeze']
        num_callers     = situation['num_callers']
        opener_is_tight = situation['opener_is_tight']
        opener_is_wide  = situation['opener_is_wide']
        opener_is_fish  = situation['opener_is_fish']
        opener_is_lp    = situation['opener_is_lp']
        opener_is_ep    = situation['opener_is_ep']

        # Squeeze spot
        if is_squeeze and (is_lp or is_blind):
            sq = self._squeeze_decision(hand_key, state, situation)
            if sq is not None:
                return sq

        # Value 3bet
        if hand_key in THREEBET_VALUE:
            freq = THREEBET_VALUE[hand_key]
            if hand_key in TRAP_HANDS and opener_is_lp and opener_is_wide:
                if random.random() < 0.25:
                    if amount_to_call <= bb * 8:
                        return ('call', 0)
            if random.random() < freq:
                return self._make_raise(self._threebet_size(pot, bb, False, 0), state)
            return ('call', 0)

        # Strong 3bet
        if hand_key in THREEBET_STRONG:
            base = THREEBET_STRONG[hand_key]
            freq = min(ALWAYS, base * (1.4 if opener_is_wide else 1.0))
            freq = self._depth_adjust(freq, depth)
            if (is_lp or is_blind) and random.random() < freq:
                return self._make_raise(self._threebet_size(pot, bb, False, 0), state)

        # 3bet bluffs
        if (is_lp or is_blind) and not final_table and hand_key in THREEBET_BLUFFS:
            base = THREEBET_BLUFFS[hand_key]
            mult = 1.5 if opener_is_wide else (0.3 if opener_is_tight else 1.0)
            if depth == 'deep':
                mult *= 1.2
            elif depth in ('short','danger'):
                mult *= 0.5
            if random.random() < base * mult:
                return self._make_raise(self._threebet_size(pot, bb, False, 0), state)

        # Select call range
        if position == 'bb':
            call_range = BB_CALL_VS_RAISE
        elif position == 'sb':
            call_range = SB_CALL_VS_RAISE
        elif position == 'utg2':
            call_range = UTG2_CALL_VS_RAISE
        elif is_ep:
            call_range = EP_CALL_VS_RAISE
        elif position in ('lj','mp'):
            call_range = MP_CALL_VS_RAISE
        else:
            call_range = LP_CALL_VS_RAISE

        call_freq = call_range.get(hand_key, NEVER)

        # Opponent adjustments
        if opener_is_tight and opener_is_ep and hand_key in FOLD_VS_TIGHT_EP:
            call_freq = NEVER
        if position == 'bb' and opener_is_lp and opener_is_wide:
            if hand_key in WIDE_BB_EXTRA:
                call_freq = max(call_freq, SOMETIMES)
        if opener_is_fish and hand_key in {'76s','65s','54s','T8s','97s'}:
            call_freq *= 0.6

        # VPIP/PFR awareness — widen calling range vs loose openers
        opener_stats = opponent_stats.get(situation.get('opener_idx')) if situation.get('opener_idx') else None
        if opener_stats and opener_stats.hands_seen >= 8:
            opener_vpip = opener_stats.vpip_pct
            opener_pfr  = opener_stats.pfr_pct
            opener_type = opener_stats.player_type()

            # Maniac (high VPIP + high PFR) — call much wider, they bluff too much
            if opener_type == 'maniac':
                call_freq = min(ALWAYS, call_freq * 1.60)

            # Loose aggressive — widen moderately
            elif opener_vpip > 0.38 and opener_pfr > 0.22:
                call_freq = min(ALWAYS, call_freq * 1.30)

            # Calling station opening — widen for value, tighten bluffs
            elif opener_type == 'calling_station':
                call_freq = min(ALWAYS, call_freq * 1.15)

            # Nit opening — tighten significantly
            elif opener_type == 'nit':
                call_freq *= 0.65

        # Depth adjustment
        call_freq = self._depth_adjust(call_freq, depth)

        # Price check — but NEVER fold premiums just because of sizing
        # Oversized opens are often a bluff or fish behaviour — widen vs large opens from loose players
        is_oversize = amount_to_call > bb * 9
        if is_oversize:
            # Check if opener is known loose — oversized open from maniac = call wider
            opener_stats2 = opponent_stats.get(situation.get('opener_idx')) if situation.get('opener_idx') else None
            if opener_stats2 and opener_stats2.player_type() in ('maniac', 'fish', 'calling_station'):
                pass  # Don't discount vs known loose openers
            elif position == 'sb' or final_table:
                call_freq *= 0.50
            else:
                call_freq *= 0.65  # Mild discount vs unknown oversized opens

        if random.random() < call_freq:
            return ('call', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Facing 3bet
    # -----------------------------------------------------------------------

    def _vs_threebet(self, hand_key, state, situation) -> Tuple[str, int]:
        is_lp           = state['is_lp']
        pot             = state['pot']
        bb              = state['bb']
        amount_to_call  = state['amount_to_call']
        opener_is_tight = situation['opener_is_tight']
        depth           = state['depth']

        if hand_key in FOURBET_VS_3BET:
            freq = self._depth_adjust(FOURBET_VS_3BET[hand_key], depth)
            if random.random() < freq:
                return self._make_raise(int(pot * 2.2), state)

        if is_lp and not opener_is_tight and hand_key in BLUFF_4BET:
            freq = self._depth_adjust(BLUFF_4BET[hand_key], depth)
            if random.random() < freq:
                return self._make_raise(int(pot * 2.2), state)

        call_freq = CALL_VS_3BET.get(hand_key, NEVER)
        call_freq = self._depth_adjust(call_freq, depth)
        if amount_to_call > bb * 12:
            call_freq *= 0.6

        if random.random() < call_freq:
            return ('call', 0)
        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Facing 4bet+
    # -----------------------------------------------------------------------

    def _vs_fourbet_plus(self, hand_key, state) -> Tuple[str, int]:
        call_freq = CALL_VS_4BET.get(hand_key, NEVER)
        if random.random() < call_freq:
            if state['bb_stack'] < 40:
                return ('all-in', 0)
            return ('call', 0)
        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Squeeze
    # -----------------------------------------------------------------------

    def _squeeze_decision(self, hand_key, state, situation) -> Optional[Tuple[str, int]]:
        pot             = state['pot']
        bb              = state['bb']
        num_callers     = situation['num_callers']
        opener_is_tight = situation['opener_is_tight']
        final_table     = state['final_table']
        depth           = state['depth']

        if hand_key in THREEBET_VALUE:
            return self._make_raise(self._squeeze_size(pot, bb, num_callers), state)

        if hand_key in THREEBET_STRONG:
            freq = self._depth_adjust(THREEBET_STRONG.get(hand_key, SOMETIMES), depth)
            if not opener_is_tight and random.random() < freq:
                return self._make_raise(self._squeeze_size(pot, bb, num_callers), state)

        if not final_table and hand_key in SQUEEZE_BLUFF_HANDS:
            base = SOMETIMES
            freq = min(OFTEN, base + num_callers * 0.12)
            freq = self._depth_adjust(freq, depth)
            if opener_is_tight:
                freq *= 0.25
            if random.random() < freq:
                return self._make_raise(self._squeeze_size(pot, bb, num_callers), state)

        return None

    # -----------------------------------------------------------------------
    # Push / fold  (<= 15bb)
    # -----------------------------------------------------------------------

    def _push_fold(self, hand_key: str, state: dict, gamestate) -> Tuple[str, int]:
        """
        Full push/fold strategy for <= 15bb.
        Accounts for:
          - Number of raises already in the pot
          - Our position (steal jams in LP)
          - Action in front (more action = tighter push range)
        """
        position    = state['position']
        is_lp       = state['is_lp']
        is_blind    = state['is_blind']
        bb_stack    = state['bb_stack']
        facing_raise = state['facing_raise']

        num_raises  = self._count_raises(gamestate)

        # Facing 3bet or more: only absolute premiums
        if num_raises >= 2:
            freq = PUSH_VS_3BET.get(hand_key, NEVER)
            if random.random() < freq:
                return ('all-in', 0)
            return ('fold', 0)

        # Facing a single raise
        if num_raises == 1 or facing_raise:
            freq = PUSH_VS_RAISE.get(hand_key, NEVER)
            # Tighten with a short stack even further
            if bb_stack < 10:
                freq = PUSH_VS_3BET.get(hand_key, freq * 0.5)
            if random.random() < freq:
                return ('all-in', 0)
            return ('fold', 0)

        # No raise: open-jam
        freq = PUSH_BASE.get(hand_key, NEVER)

        # LP steal jams with limited action
        if is_lp and hand_key in STEAL_JAM_LP:
            steal_freq = STEAL_JAM_LP[hand_key]
            # Tighten steal jams as stack gets shorter (less fold equity)
            if bb_stack < 8:
                steal_freq *= 0.5
            freq = max(freq, steal_freq)

        # SB steal jam
        if position == 'sb' and hand_key in STEAL_JAM_LP:
            freq = max(freq, STEAL_JAM_LP[hand_key] * 0.8)

        # BB: fold or shove only
        if position == 'bb':
            freq = max(freq, PUSH_BASE.get(hand_key, NEVER))

        if random.random() < freq:
            return ('all-in', 0)
        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Sizing helpers
    # -----------------------------------------------------------------------

    def _threebet_size(self, pot, bb, is_squeeze, num_callers) -> int:
        base = int(pot * 3.0)
        if is_squeeze:
            base += num_callers * bb
        return max(base, bb * 9)

    def _squeeze_size(self, pot, bb, num_callers) -> int:
        return max(int(pot * 3.0) + num_callers * bb, bb * 10)

    def _make_raise(self, amount: int, state: dict) -> Tuple[str, int]:
        min_r = state['min_raise']
        max_r = state['max_raise']
        stack = state['stack']
        if amount >= stack or amount >= max_r:
            return ('all-in', 0)
        amount = max(amount, min_r)
        amount = min(amount, max_r)
        return ('raise', amount)


# ---------------------------------------------------------------------------
# Shorthand — used in hand key generation

def hand_key(hole_cards: Tuple[str, str]) -> str:
    c1, c2 = hole_cards
    r1, r2, s1, s2 = c1[0], c2[0], c1[1], c2[1]
    v1, v2 = RANK_VALUE.get(r1, 2), RANK_VALUE.get(r2, 2)
    if v1 < v2:
        r1, r2, s1, s2 = r2, r1, s2, s1
    if r1 == r2:
        return f'{r1}{r2}'
    return f'{r1}{r2}{"s" if s1 == s2 else "o"}'