"""
Turn & River Engine
====================
Handles all turn and river decisions with full situational awareness.

Key features:
  1. RUNOUT ANALYSIS
     - Detects when draws complete on turn/river (flush cards, straight cards)
     - Identifies scare cards vs blank cards
     - Tracks board texture evolution from flop → turn → river

  2. BLOCKER DETECTION (river bluffing)
     - Ace of flush suit (blocks nut flush — great bluff candidate)
     - Straight blockers (hold cards that complete straights — villain less likely to have it)
     - Broadway blockers (K/Q/J on paired boards — blocks their calling range)
     - Blocker score combines all active blockers for a single bluff quality metric

  3. OPPONENT BLUFF RATE CALCULATION
     - Estimated from aggression factor, PFR, VPIP, and showdown hand evidence
     - High bluff rate → check-call more, trap more
     - Low bluff rate → bet for value more, fold to raises more

  4. THIN VALUE BETTING
     - Moderate aggression: thin bet vs any passive player with low aggression
     - Sizing up vs fish/stations (they call wide)
     - Sizing down vs aggressive players (induce action)
     - Block bets vs thinking players (TAG) — small bet to control pot and see cheap river

  5. PROFILE-AWARE RIVER SIZING
     - Fish/calling station: size up — they call any reasonable bet
     - If they've shown aggression: size down slightly (induce raise)
     - If they're passive: size up (they won't raise, just call)
     - Nit: small bets only — they fold to large bets
     - Maniac: medium bets — let them raise, don't overbet
     - TAG: polarised — either block bet or pot bet, nothing in between

  6. SECOND BARREL (turn) STRATEGY
     - Standard mix: continue with strong hands, draws, good bluff candidates
     - Check back medium hands that benefit from pot control
     - Frequency scales with hand strength + draw equity + blocker score
"""

import random
from typing import Tuple, List, Optional, Dict, TYPE_CHECKING
from src.helpers.hand_judge import HandJudge
from src.bots.lomaan_bot.profiles import (
    should_check_raise, get_profile_adjustment,
    PreflopHistoryAnalyser
)

if TYPE_CHECKING:
    from src.bots.lomaan_bot.stats import OpponentStats

RANK_ORDER = '23456789TJQKA'
RANK_VALUE  = {r: i for i, r in enumerate(RANK_ORDER, 2)}

HAND_RANK = {
    'high_card': 0, 'one_pair': 1, 'two_pair': 2, 'three_of_a_kind': 3,
    'straight': 4, 'flush': 5, 'full_house': 6, 'four_of_a_kind': 7,
    'straight_flush': 8, 'royal_flush': 9,
}

# Situation constants (same as flop)
IP_AGGRESSOR  = 'ip_aggressor'
OOP_AGGRESSOR = 'oop_aggressor'
IP_CALLER     = 'ip_caller'
MULTIWAY      = 'multiway'

_preflop_analyser = PreflopHistoryAnalyser()


# ---------------------------------------------------------------------------
# Runout analyser
# ---------------------------------------------------------------------------

class RunoutAnalyser:
    """
    Analyses what changed between the flop and the current street.
    Detects draw completions, scare cards, and blank turns/rivers.
    """

    def __init__(self, community_cards: List[str]):
        self.cards  = community_cards
        self.n      = len(community_cards)
        self.flop   = community_cards[:3]
        self.turn   = community_cards[3] if self.n >= 4 else None
        self.river  = community_cards[4] if self.n >= 5 else None
        self.new_card = community_cards[-1] if self.n >= 4 else None

        self.flop_suits  = [c[1] for c in self.flop]
        self.flop_values = sorted([RANK_VALUE.get(c[0], 2) for c in self.flop], reverse=True)
        self.all_suits   = [c[1] for c in community_cards]
        self.all_values  = sorted([RANK_VALUE.get(c[0], 2) for c in community_cards], reverse=True)

        self.flush_completed    = self._flush_completed()
        self.straight_completed = self._straight_completed()
        self.board_paired       = self._board_paired()
        self.is_scare_card      = self.flush_completed or self.straight_completed
        self.is_blank           = self._is_blank()
        self.new_card_value     = RANK_VALUE.get(self.new_card[0], 2) if self.new_card else 0
        self.is_high_card       = self.new_card_value >= RANK_VALUE.get('T', 10)
        self.is_ace             = self.new_card_value == 14 if self.new_card else False

    def _flush_completed(self) -> bool:
        """Did a flush draw complete on the new card?"""
        if not self.new_card:
            return False
        from collections import Counter
        # Check if flop had a two-tone possibility (2 of same suit)
        flop_suit_counts = Counter(self.flop_suits)
        max_flop_suit = max(flop_suit_counts.values())
        if max_flop_suit < 2:
            return False
        # Now check if new card completes to 3 of same suit (monotone now)
        all_suit_counts = Counter(self.all_suits)
        return max(all_suit_counts.values()) >= 3

    def _straight_completed(self) -> bool:
        """Did a straight draw complete on the new card?"""
        if not self.new_card:
            return False
        vals = sorted(set(self.all_values))
        # Check for 5 consecutive values
        for i in range(len(vals) - 4):
            if vals[i+4] - vals[i] == 4 and len(vals[i:i+5]) == 5:
                return True
        return False

    def _board_paired(self) -> bool:
        """Did the new card pair the board?"""
        if not self.new_card:
            return False
        new_val = RANK_VALUE.get(self.new_card[0], 2)
        return any(RANK_VALUE.get(c[0], 2) == new_val for c in self.flop)

    def _is_blank(self) -> bool:
        """Is the new card a non-threatening blank?"""
        if not self.new_card:
            return False
        return not self.flush_completed and not self.straight_completed and not self.board_paired

    def texture_shift(self) -> str:
        """How dangerous is the new card?"""
        if self.flush_completed and self.straight_completed:
            return 'very_dangerous'
        if self.flush_completed or self.straight_completed:
            return 'dangerous'
        if self.board_paired:
            return 'slightly_dangerous'
        if self.is_blank:
            return 'blank'
        return 'neutral'


# ---------------------------------------------------------------------------
# Blocker detector
# ---------------------------------------------------------------------------

class BlockerDetector:
    """
    Detects blocking cards in our hole cards relative to the board.

    Blockers are most powerful on the river when we want to bluff —
    holding a card that makes villain's strong hands less likely
    means our bluff has better fold equity.
    """

    def __init__(self, hole_cards: Tuple[str, str], community_cards: List[str]):
        self.hole   = hole_cards
        self.board  = community_cards
        self.h1     = hole_cards[0]
        self.h2     = hole_cards[1]
        self.r1     = self.h1[0]
        self.r2     = self.h2[0]
        self.s1     = self.h1[1]
        self.s2     = self.h2[1]
        self.v1     = RANK_VALUE.get(self.r1, 2)
        self.v2     = RANK_VALUE.get(self.r2, 2)

        board_suits  = [c[1] for c in community_cards]
        board_values = [RANK_VALUE.get(c[0], 2) for c in community_cards]

        from collections import Counter
        self.suit_counts  = Counter(board_suits)
        self.value_counts = Counter(board_values)

        # Dominant flush suit on board
        self.flush_suit = max(self.suit_counts, key=self.suit_counts.get) if self.suit_counts else None
        self.flush_count = self.suit_counts.get(self.flush_suit, 0)

        self.ace_blocker       = self._has_ace_flush_blocker()
        self.straight_blocker  = self._has_straight_blocker()
        self.broadway_blocker  = self._has_broadway_blocker()
        self.top_pair_blocker  = self._has_top_pair_blocker()

        self.blocker_score = self._compute_blocker_score()

    def _has_ace_flush_blocker(self) -> bool:
        """
        Hold the Ace of the dominant flush suit.
        Makes it impossible for villain to have the nut flush.
        Excellent bluff candidate — villain can't have the nuts.
        """
        if self.flush_count < 2:
            return False
        return (self.r1 == 'A' and self.s1 == self.flush_suit) or \
               (self.r2 == 'A' and self.s2 == self.flush_suit)

    def _has_straight_blocker(self) -> bool:
        """
        Hold a card that makes key straights impossible.
        E.g. on a 6-7-8-9 board, holding a T or 5 blocks the straight.
        """
        board_vals = sorted([RANK_VALUE.get(c[0], 2) for c in self.board])
        for hv in (self.v1, self.v2):
            for i in range(len(board_vals) - 2):
                # Does our card complete a straight with 3 board cards?
                window = board_vals[i:i+3] + [hv]
                window = sorted(window)
                if window[-1] - window[0] <= 4 and len(set(window)) == 4:
                    return True
        return False

    def _has_broadway_blocker(self) -> bool:
        """
        Hold K/Q/J on a board where paired broadway completes strong hands.
        Blocks villain's top pair calling range — they're less likely to call
        because we hold one of their 'good' cards.
        """
        broadway = set('AKQJT')
        board_ranks = [c[0] for c in self.board]
        board_broadway = [r for r in board_ranks if r in broadway]
        if len(board_broadway) < 2:
            return False
        return self.r1 in broadway or self.r2 in broadway

    def _has_top_pair_blocker(self) -> bool:
        """
        Hold an Ace on an Ace-high board — blocks villain's Ax hands
        from calling (they can't have top pair if we hold an Ace).
        """
        board_values = [RANK_VALUE.get(c[0], 2) for c in self.board]
        top_board_val = max(board_values) if board_values else 0
        return top_board_val == 14 and (self.v1 == 14 or self.v2 == 14)

    def _compute_blocker_score(self) -> float:
        """
        Combined blocker score 0.0-1.0.
        Higher = better bluff candidate due to blockers.
        """
        score = 0.0
        if self.ace_blocker:      score += 0.45  # Strongest blocker
        if self.straight_blocker: score += 0.30
        if self.broadway_blocker: score += 0.20
        if self.top_pair_blocker: score += 0.15
        return min(1.0, score)

    def best_blocker_description(self) -> str:
        parts = []
        if self.ace_blocker:      parts.append('nut flush blocker')
        if self.straight_blocker: parts.append('straight blocker')
        if self.broadway_blocker: parts.append('broadway blocker')
        return ' + '.join(parts) if parts else 'no blocker'


# ---------------------------------------------------------------------------
# Opponent bluff rate calculator
# ---------------------------------------------------------------------------

class BluffRateEstimator:
    """
    Estimates how often an opponent bluffs based on their tracked stats.

    Bluff rate is inferred from:
      - Aggression factor (raise/bet vs check/call ratio)
      - PFR (preflop raise frequency — correlates with postflop aggression)
      - VPIP (loose players bluff more)
      - Showdown hand evidence (if we've seen them show bluffs at showdown)

    Returns bluff_rate: 0.0 (never bluffs) to 1.0 (always bluffs)
    """

    def estimate(self, stats: 'OpponentStats') -> float:
        if stats.hands_seen < 6:
            return 0.35  # Unknown — assume moderate

        pfr  = stats.pfr_pct
        vpip = stats.vpip_pct
        af   = stats.aggression_factor

        # Base bluff rate from aggression factor
        # AF > 2 = aggressive, < 1 = passive
        base = min(0.80, max(0.05, (af - 1.0) * 0.25 + 0.30))

        # PFR adjustment: high PFR = more cbets = more bluffs
        base += (pfr - 0.20) * 0.40

        # VPIP adjustment: very wide players bluff more
        base += (vpip - 0.25) * 0.20

        # Showdown evidence: if we've seen them showdown bluffs
        if stats.showdown_hands:
            bluff_showdowns = self._count_bluff_showdowns(stats.showdown_hands)
            if bluff_showdowns > 0:
                base += bluff_showdowns * 0.05

        return min(0.85, max(0.05, base))

    def _count_bluff_showdowns(self, showdown_hands: List) -> int:
        """Count showdown hands that look like missed draws or air."""
        count = 0
        for (c1, c2) in showdown_hands:
            v1 = RANK_VALUE.get(c1[0], 2)
            v2 = RANK_VALUE.get(c2[0], 2)
            # Low non-paired hands without broadway = likely bluff/semi-bluff
            if max(v1, v2) <= 9 and v1 != v2:
                count += 1
        return count

    def classify(self, bluff_rate: float) -> str:
        if bluff_rate >= 0.55: return 'maniac'
        if bluff_rate >= 0.40: return 'aggressive'
        if bluff_rate >= 0.25: return 'balanced'
        if bluff_rate >= 0.15: return 'passive'
        return 'never_bluffs'


_bluff_estimator = BluffRateEstimator()


# ---------------------------------------------------------------------------
# Profile-aware river sizing
# ---------------------------------------------------------------------------

def river_bet_size(
    hand_rank: int,
    is_thin_value: bool,
    is_bluff: bool,
    opp_profile: str,
    opp_bluff_rate: float,
    opp_stats: Optional['OpponentStats'],
    pot: int,
    spr: float,
) -> float:
    """
    Compute optimal river bet size as a fraction of pot.

    Core philosophy:
      Value bet: size to maximise calling range (not fold equity)
      Bluff:     size for maximum fold equity (usually larger)
      Thin value: size smaller to keep worse hands in

    Profile-aware adjustments:
      Fish/station:   size up (they call wide regardless)
      Aggressive opp: size down slightly (induce raises)
      Passive opp:    size up (they won't raise, maximise value)
      Nit:            size small (large bets fold them out)
      Maniac:         medium (let them raise, don't overbet)
      TAG:            polarised (block bet or pot, nothing in between)
    """
    is_aggressor_type = opp_profile in ('maniac',) or opp_bluff_rate >= 0.45
    is_passive_type   = opp_profile in ('nit', 'calling_station', 'fish') or opp_bluff_rate <= 0.20

    if is_bluff:
        # Bluffs want fold equity — size depends on profile
        if opp_profile == 'nit':
            return 0.55    # Nit folds to moderate bets
        if opp_profile in ('calling_station', 'fish'):
            return 0.35    # They call bluffs too — small bluff or don't bluff
        if opp_profile == 'tag':
            return 0.55    # Block bet size vs thinker
        if is_aggressor_type:
            return 0.65    # Need credibility vs aggressive player
        return 0.60        # Default bluff size

    if is_thin_value:
        # Thin value — keep worse hands in
        if opp_profile in ('fish', 'calling_station'):
            return 0.45    # They call any reasonable bet
        if opp_profile == 'nit':
            return 0.28    # Small bet — nit only calls with strong hands
        if opp_profile == 'maniac':
            return 0.38    # Medium — they might raise, that's ok
        if opp_profile == 'tag':
            return 0.33    # Block bet vs thinker — cheaply gets to showdown
        return 0.38        # Standard thin value

    # Full value bet
    if opp_profile in ('fish', 'calling_station'):
        # Has villain shown postflop aggression? Size down to induce calls
        if opp_stats and opp_stats.aggression_factor > 1.5:
            return 0.65    # They're aggressive — size down, let them raise
        else:
            return 0.80    # Passive fish — size up, they call anything
    if opp_profile == 'nit':
        return 0.45        # Nit won't call big — medium is max
    if opp_profile == 'maniac':
        return 0.60        # Medium — they'll raise, don't need to overbet
    if opp_profile == 'tag':
        # Polarised: either block bet or pot bet
        if hand_rank >= 4:
            return 0.90    # Nutted — pot bet
        return 0.35        # Block bet — control pot size
    # Unknown / balanced
    return 0.65


# ---------------------------------------------------------------------------
# Main turn & river engine
# ---------------------------------------------------------------------------

class TurnRiverEngine:
    """
    Complete turn and river decision engine.
    Shares architecture with FlopEngine but adds:
      - Runout analysis (what changed from flop?)
      - Blocker detection
      - Opponent bluff rate
      - Second barrel logic (turn)
      - Thin value betting
      - Profile-aware river sizing
    """

    def decide(
        self,
        state: dict,
        gamestate,
        hole_cards: Tuple[str, str],
        opponent_stats: Dict[int, 'OpponentStats'],
    ) -> Tuple[str, int]:

        community = list(gamestate.community_cards)
        street    = state['street']
        assert street in ('turn', 'river'), f"TurnRiverEngine called on {street}"

        # Build analysis objects
        runout  = RunoutAnalyser(community)
        blockers = BlockerDetector(hole_cards, community)

        # Hand strength
        hand_name, _ = HandJudge.evaluate_hand(hole_cards, community)
        hand_rank     = HAND_RANK.get(hand_name, 0)

        # Equity from state
        equity = state.get('equity', 0.5)

        # Opponent model
        main_opp    = self._get_main_opponent(gamestate, opponent_stats)
        opp_profile = main_opp.player_type() if main_opp else 'unknown'
        prof_adjust = get_profile_adjustment(opp_profile)
        bluff_rate  = _bluff_estimator.estimate(main_opp) if main_opp else 0.35
        bluff_class = _bluff_estimator.classify(bluff_rate)

        # Situation
        situation = self._detect_situation(state)

        # Dispatch to street
        if street == 'turn':
            return self._turn_decision(
                state, runout, blockers, hand_rank, equity,
                opp_profile, prof_adjust, bluff_rate, bluff_class, main_opp, situation
            )
        else:
            return self._river_decision(
                state, runout, blockers, hand_rank, equity,
                opp_profile, prof_adjust, bluff_rate, bluff_class, main_opp, situation
            )

    # -----------------------------------------------------------------------
    # Turn decision
    # -----------------------------------------------------------------------

    def _turn_decision(
        self, state, runout, blockers, hand_rank, equity,
        opp_profile, prof_adjust, bluff_rate, bluff_class, opp_stats, situation
    ) -> Tuple[str, int]:

        pot          = state['pot']
        facing_raise = state['facing_raise']
        raised_yet   = state.get('raised_this_street', False)
        spr          = state['spr']
        pot_odds     = state['pot_odds']

        # ── FACING A BET / RAISE ────────────────────────────────────────────
        if facing_raise:
            return self._facing_bet_turn(
                state, runout, blockers, hand_rank, equity,
                opp_profile, prof_adjust, bluff_rate, raised_yet
            )

        # ── WE ACT FIRST / CHECK BACK ────────────────────────────────────────
        # Draw completed — adjust based on profile
        if runout.is_scare_card:
            return self._scare_card_turn(
                state, runout, hand_rank, equity,
                opp_profile, prof_adjust, bluff_rate, bluff_class, blockers
            )

        # Blank turn — standard second barrel logic
        return self._blank_turn_barrel(
            state, runout, blockers, hand_rank, equity,
            opp_profile, prof_adjust, bluff_rate, situation
        )

    def _scare_card_turn(
        self, state, runout, hand_rank, equity,
        opp_profile, prof_adjust, bluff_rate, bluff_class, blockers
    ) -> Tuple[str, int]:
        """
        Draw completed on turn — flush card or straight card.
        Strategy depends entirely on opponent profile:
          - vs fish/station: bet bigger to deny remaining equity
          - vs nit: check-call (they rarely have the draw, let them bet air)
          - vs maniac: check-call/check-raise trap
          - vs TAG: mixed — bet strong hands, check-call medium
        """
        pot     = state['pot']
        spr     = state['spr']

        # We improved (hit the draw ourselves or made a strong hand)
        if hand_rank >= 4:  # Straight or better
            # Our hand is very strong — bet or trap based on profile
            if opp_profile in ('maniac',) or bluff_rate >= 0.50:
                # Maniac/aggressive: check-call or check-raise to trap
                return ('check', 0)
            else:
                # Standard: bet for value
                size = 0.70 if opp_profile in ('fish', 'calling_station') else 0.55
                return self._make_bet(size, pot, state)

        # Made hand now vulnerable (two pair, trips on a flushing board)
        if hand_rank in (2, 3):
            if opp_profile == 'nit':
                return ('check', 0)  # Nit has it when they bet — check-call cheaply
            elif opp_profile in ('fish', 'calling_station'):
                # Bet bigger — deny equity and they call with worse
                size = 0.75
                return self._make_bet(size, pot, state)
            elif opp_profile == 'maniac':
                # Check-raise trap — let them barrel into us
                return ('check', 0)
            elif opp_profile == 'tag':
                # Mixed — 60% bet to define range, 40% check to balance
                if random.random() < 0.60:
                    size = 0.60
                    return self._make_bet(size, pot, state)
                return ('check', 0)
            else:
                # Unknown — standard bet
                if random.random() < 0.55:
                    size = 0.60
                    return self._make_bet(size, pot, state)
                return ('check', 0)

        # One pair on a completed draw board — dangerous spot
        if hand_rank == 1:
            # Check unless we have a strong read that opponent missed
            if bluff_rate <= 0.20:  # They don't bluff — don't bluff back
                return ('check', 0)
            # Blockers make bluffing viable here
            if blockers.ace_blocker and runout.flush_completed:
                # We hold the nut flush blocker — they can't have the nuts
                if random.random() < 0.45:
                    size = 0.60
                    return self._make_bet(size, pot, state)
            return ('check', 0)

        # Air on scary board — check almost always
        return ('check', 0)

    def _blank_turn_barrel(
        self, state, runout, blockers, hand_rank, equity,
        opp_profile, prof_adjust, bluff_rate, situation
    ) -> Tuple[str, int]:
        """
        Blank turn — second barrel decision (standard mix).
        Continue with: strong hands, strong draws, good bluff candidates.
        Check back: medium hands that benefit from pot control.
        """
        pot = state['pot']
        spr = state['spr']

        # Strong made hands — always barrel
        if hand_rank >= 3:
            size = river_bet_size(hand_rank, False, False, opp_profile, bluff_rate, None, pot, spr)
            return self._make_bet(size, pot, state)

        # Two pair — barrel most of the time, pot control occasionally
        if hand_rank == 2:
            if random.random() < 0.75:
                size = river_bet_size(hand_rank, False, False, opp_profile, bluff_rate, None, pot, spr)
                return self._make_bet(size, pot, state)
            return ('check', 0)

        # One pair — standard mix, pot control
        if hand_rank == 1:
            pair_freq = 0.45  # Base frequency
            if prof_adjust:
                pair_freq *= prof_adjust.cbet_freq_mult
            if random.random() < pair_freq:
                size = river_bet_size(hand_rank, True, False, opp_profile, bluff_rate, None, pot, spr)
                return self._make_bet(size, pot, state)
            return ('check', 0)

        # Air / draw — bluff barrel with quality hands
        bluff_freq = self._turn_bluff_frequency(blockers, equity, opp_profile, bluff_rate, situation)
        if bluff_freq > 0 and random.random() < bluff_freq:
            size = river_bet_size(0, False, True, opp_profile, bluff_rate, None, pot, spr)
            return self._make_bet(size, pot, state)

        return ('check', 0)

    def _turn_bluff_frequency(self, blockers, equity, opp_profile, bluff_rate, situation) -> float:
        """
        How often to bluff the turn based on:
        - Blocker quality (ace blocker = bluff more)
        - Remaining equity (draws = semi-bluff)
        - Position (IP = bluff more)
        - Opponent bluff rate (high bluff rate = they call/raise bluffs — bluff less)
        """
        if opp_profile in ('calling_station', 'fish'):
            return 0.0  # Never bluff stations

        base = 0.20

        # Blocker adjustment
        base += blockers.blocker_score * 0.25

        # Equity — semi-bluffs are better bluffs
        if equity > 0.30:
            base += 0.15
        if equity > 0.40:
            base += 0.10

        # Position
        if situation == IP_AGGRESSOR:
            base += 0.08

        # Opponent profile
        if opp_profile == 'nit':
            base += 0.15   # Nit folds a lot — bluff more
        elif opp_profile == 'maniac':
            base -= 0.15   # They call/raise — bluff less
        elif opp_profile == 'tag':
            base -= 0.05   # TAGs defend well

        return max(0.0, min(0.65, base))

    def _facing_bet_turn(
        self, state, runout, blockers, hand_rank, equity,
        opp_profile, prof_adjust, bluff_rate, raised_yet
    ) -> Tuple[str, int]:
        """
        Facing a bet on the turn — call, raise, or fold.
        Integrates opponent bluff rate to decide how wide to call.
        """
        pot_odds = state['pot_odds']
        pot      = state['pot']
        spr      = state['spr']

        # Raise threshold — lower if villain bluffs a lot
        raise_equity = 0.60 - (bluff_rate * 0.15)

        # Check-raise with strong hands
        cr_raise, cr_size = should_check_raise(
            hand_rank, type('D', (), {'combo_draw': False, 'flush_draw': False,
                                       'oesd': False, 'gutshot': False})(),
            equity, type('T', (), {'is_wet': runout.flush_completed or runout.straight_completed,
                                   'is_dry': runout.is_blank, 'is_monotone': False,
                                   'is_paired': runout.board_paired})(),
            opp_profile, spr, raised_yet
        )
        if cr_raise and equity >= raise_equity:
            return self._make_bet(int(pot * cr_size), pot, state)

        # Call threshold — wider vs high bluff rate opponents
        call_shift = -0.08 if bluff_rate >= 0.50 else (0.06 if bluff_rate <= 0.15 else 0.0)
        if prof_adjust:
            call_shift += prof_adjust.call_wider

        # Scare card hit — be more cautious unless we have a monster
        if runout.is_scare_card and hand_rank <= 2:
            call_shift += 0.08  # Need more equity on scary boards

        if equity > pot_odds + call_shift + 0.03:
            return ('call', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # River decision
    # -----------------------------------------------------------------------

    def _river_decision(
        self, state, runout, blockers, hand_rank, equity,
        opp_profile, prof_adjust, bluff_rate, bluff_class, opp_stats, situation
    ) -> Tuple[str, int]:

        pot          = state['pot']
        facing_raise = state['facing_raise']
        raised_yet   = state.get('raised_this_street', False)
        spr          = state['spr']
        pot_odds     = state['pot_odds']
        is_ip        = situation in (IP_AGGRESSOR, IP_CALLER)

        if facing_raise:
            return self._facing_bet_river(
                state, hand_rank, equity, opp_profile, bluff_rate, raised_yet
            )

        # ── DECIDE: BET OR CHECK ─────────────────────────────────────────────

        # MONSTER VALUE BETS
        if hand_rank >= 5:
            size = river_bet_size(hand_rank, False, False, opp_profile, bluff_rate, opp_stats, pot, spr)
            return self._make_bet(size, pot, state)

        # STRONG VALUE (straight, trips, two pair)
        if hand_rank >= 2:
            # Is this actually thin value or clear value?
            is_thin = hand_rank == 2 and runout.is_scare_card  # Two pair on completed draw board
            size    = river_bet_size(hand_rank, is_thin, False, opp_profile, bluff_rate, opp_stats, pot, spr)

            if is_thin:
                # Thin value — check passive requirement
                if self._should_thin_value_bet(opp_profile, bluff_rate, state):
                    return self._make_bet(size, pot, state)
                return ('check', 0)

            return self._make_bet(size, pot, state)

        # ONE PAIR — thin value or check
        if hand_rank == 1:
            if self._should_thin_value_bet(opp_profile, bluff_rate, state):
                size = river_bet_size(1, True, False, opp_profile, bluff_rate, opp_stats, pot, spr)
                return self._make_bet(size, pot, state)
            # Check back — either check-call (vs high bluff rate) or check-fold
            return ('check', 0)

        # AIR — bluff candidates
        bluff_score = self._river_bluff_score(
            blockers, opp_profile, bluff_rate, is_ip, runout
        )

        if bluff_score >= 0.30 and random.random() < bluff_score:
            size = river_bet_size(0, False, True, opp_profile, bluff_rate, opp_stats, pot, spr)
            return self._make_bet(size, pot, state)

        return ('check', 0)

    def _should_thin_value_bet(self, opp_profile: str, bluff_rate: float, state: dict) -> bool:
        """
        Moderate aggression thin value betting:
        Thin bet vs any passive player with low aggression.
        """
        is_passive = bluff_rate <= 0.30
        is_passive_profile = opp_profile in ('fish', 'calling_station', 'nit')

        if opp_profile in ('fish', 'calling_station'):
            return True   # Always thin value bet vs stations

        if is_passive and is_passive_profile:
            return True   # Low aggression, passive profile

        if is_passive and bluff_rate <= 0.20:
            return True   # Very passive opponent regardless of profile

        return False

    def _river_bluff_score(
        self, blockers: BlockerDetector, opp_profile: str,
        bluff_rate: float, is_ip: bool, runout: RunoutAnalyser
    ) -> float:
        """
        Compute river bluff probability based on blocker quality and opponent profile.

        Key principle: bluff when villain's calling range is weakest.
        Blockers make their strong hands less likely = they call with
        weaker hands = our bluff has higher EV.
        """
        if opp_profile in ('calling_station', 'fish'):
            return 0.0  # Never bluff these players on the river

        # Base bluff probability from blocker score
        base = blockers.blocker_score * 0.55

        # No blockers and no draw completed = rarely bluff
        if blockers.blocker_score < 0.15 and not runout.flush_completed:
            base = 0.08

        # Draw completed = we can represent having hit
        if runout.flush_completed and blockers.ace_blocker:
            base += 0.25  # We hold the nut flush blocker — perfect bluff candidate
        elif runout.flush_completed:
            base += 0.10  # We can still represent the flush

        if runout.straight_completed and blockers.straight_blocker:
            base += 0.15

        # Position
        if is_ip:
            base += 0.08

        # Profile adjustments
        if opp_profile == 'nit':
            base += 0.20   # Nit folds river bets often
        elif opp_profile == 'maniac':
            base -= 0.20   # They call/raise everything
        elif opp_profile == 'tag':
            # TAGs are thinking — only bluff with strong blocker hands
            if blockers.blocker_score < 0.30:
                base *= 0.40
        elif opp_profile == 'unknown':
            base *= 0.75   # Be conservative with unknowns

        # High bluff rate opponent = they don't fold = don't bluff
        if bluff_rate >= 0.55:
            base *= 0.30

        return max(0.0, min(0.80, base))

    def _facing_bet_river(
        self, state, hand_rank, equity, opp_profile, bluff_rate, raised_yet
    ) -> Tuple[str, int]:
        """
        Facing a river bet — call, raise (for value), or fold.
        Integrates bluff rate: high bluff rate = call wider.
        """
        pot_odds = state['pot_odds']
        pot      = state['pot']
        spr      = state['spr']

        # Raise for value with strong hands
        if hand_rank >= 4 and not raised_yet:
            if spr > 1.2:
                size = int(pot * 2.5)
                return self._make_bet(size, pot, state)
            return ('call', 0)

        # Call threshold adjusted by bluff rate
        # High bluff rate opponent = call down to one pair
        bluff_call_adj = -0.12 if bluff_rate >= 0.50 else (0.08 if bluff_rate <= 0.15 else 0.0)

        if hand_rank >= 2:
            return ('call', 0)  # Two pair or better always call river

        if hand_rank == 1:
            # One pair — call only if villain bluffs enough or we have good pot odds
            threshold = pot_odds + 0.04 + bluff_call_adj
            if equity > threshold:
                return ('call', 0)
            # vs known bluffer — call down more aggressively
            if bluff_rate >= 0.55 and pot_odds < 0.40:
                return ('call', 0)
            return ('fold', 0)

        # High card — only call with excellent blockers or vs maniac bluffer
        if bluff_rate >= 0.65 and pot_odds < 0.30:
            return ('call', 0)
        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Shared helpers
    # -----------------------------------------------------------------------

    def _detect_situation(self, state: dict) -> str:
        active  = state.get('active_count', 2)
        if active > 2:
            return MULTIWAY
        was_agg = state.get('was_aggressor', False)
        is_ip   = state.get('is_lp', False)
        if was_agg and is_ip:   return IP_AGGRESSOR
        if was_agg and not is_ip: return OOP_AGGRESSOR
        return IP_CALLER

    def _get_main_opponent(self, gamestate, opponent_stats) -> Optional['OpponentStats']:
        best_idx, best_hands = None, 0
        for idx, stats in opponent_stats.items():
            info = gamestate.player_public_infos[idx]
            if not info.busted and info.active and stats.hands_seen > best_hands:
                best_hands = stats.hands_seen
                best_idx   = idx
        return opponent_stats.get(best_idx) if best_idx is not None else None

    def _make_bet(self, size, pot: int, state: dict) -> Tuple[str, int]:
        if isinstance(size, float):
            amount = int(pot * size)
        else:
            amount = int(size)
        min_r = state.get('min_raise', 1)
        max_r = state.get('max_raise', state['stack'])
        stack = state['stack']
        if amount >= stack or amount >= max_r:
            return ('all-in', 0)
        amount = max(amount, min_r)
        amount = min(amount, max_r)
        return ('raise', amount)
