"""
Player Profile Action Tables
==============================
Defines per-opponent-profile strategy adjustments for flop play.

Two systems:

1. CHECK-RAISE TABLES
   Per hand type, per board texture, per player profile:
   - How often to check-raise (frequency)
   - Minimum equity required to do it profitably
   - Whether it's for value or as a bluff/semi-bluff

2. OPPONENT PROFILE FLOP ADJUSTMENTS
   How to adjust cbet frequency, sizing, and aggression
   based on the opponent's classified profile (fish, nit,
   calling station, maniac, TAG, unknown).

3. PREFLOP HISTORY INTEGRATION
   Uses opponent's showdown hands to estimate how loose their
   opening range actually is. If we've seen them open 98s UTG,
   their "UTG range" is clearly wider than standard — this
   affects our range advantage calculation and flop decisions.
"""

from typing import Optional, List, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from src.bots.lomaan_bot.stats import OpponentStats

RANK_ORDER = '23456789TJQKA'
RANK_VALUE  = {r: i for i, r in enumerate(RANK_ORDER, 2)}


# ---------------------------------------------------------------------------
# Check-raise frequency tables
# ---------------------------------------------------------------------------
# Format: (hand_rank_min, hand_rank_max) -> {profile -> (freq, min_equity)}
# hand_rank: 0=high_card, 1=pair, 2=two_pair, 3=trips, 4=str, 5=flush, 6=FH+
# freq:      how often to check-raise (0.0-1.0)
# min_equity: minimum equity required before applying freq

@dataclass
class CheckRaiseProfile:
    """Defines check-raise behaviour for a hand type against a specific opponent profile."""
    freq: float          # Base check-raise frequency
    min_equity: float    # Must have at least this equity to check-raise
    is_bluff: bool       # True = primarily a bluff/semi-bluff, False = value
    notes: str = ''

# Check-raise tables: hand_rank -> profile -> CheckRaiseProfile
# Profiles: fish, calling_station, nit, maniac, tag, unknown

CHECK_RAISE_TABLES = {

    # MONSTERS (full house+, rank 6+): always check-raise for value
    'monster': {
        'fish':             CheckRaiseProfile(freq=0.60, min_equity=0.80, is_bluff=False, notes='fish pays off big raises'),
        'calling_station':  CheckRaiseProfile(freq=0.70, min_equity=0.80, is_bluff=False, notes='they call everything'),
        'nit':              CheckRaiseProfile(freq=0.30, min_equity=0.80, is_bluff=False, notes='nit folds to raises — slowplay more'),
        'maniac':           CheckRaiseProfile(freq=0.80, min_equity=0.80, is_bluff=False, notes='maniac bets so check-raise traps'),
        'tag':              CheckRaiseProfile(freq=0.55, min_equity=0.80, is_bluff=False, notes='balanced vs TAG'),
        'unknown':          CheckRaiseProfile(freq=0.50, min_equity=0.80, is_bluff=False),
    },

    # STRONG MADE HANDS (straight/flush, rank 4-5)
    'strong': {
        'fish':             CheckRaiseProfile(freq=0.45, min_equity=0.65, is_bluff=False, notes='fish calls raises wide'),
        'calling_station':  CheckRaiseProfile(freq=0.60, min_equity=0.65, is_bluff=False, notes='they never fold'),
        'nit':              CheckRaiseProfile(freq=0.20, min_equity=0.65, is_bluff=False, notes='nit folds — slowplay to river'),
        'maniac':           CheckRaiseProfile(freq=0.70, min_equity=0.65, is_bluff=False, notes='trap the bluffer'),
        'tag':              CheckRaiseProfile(freq=0.40, min_equity=0.65, is_bluff=False),
        'unknown':          CheckRaiseProfile(freq=0.35, min_equity=0.65, is_bluff=False),
    },

    # TRIPS (rank 3)
    'trips': {
        'fish':             CheckRaiseProfile(freq=0.40, min_equity=0.60, is_bluff=False),
        'calling_station':  CheckRaiseProfile(freq=0.55, min_equity=0.60, is_bluff=False),
        'nit':              CheckRaiseProfile(freq=0.15, min_equity=0.60, is_bluff=False, notes='slowplay vs nit — they fold to raises'),
        'maniac':           CheckRaiseProfile(freq=0.65, min_equity=0.60, is_bluff=False),
        'tag':              CheckRaiseProfile(freq=0.35, min_equity=0.60, is_bluff=False),
        'unknown':          CheckRaiseProfile(freq=0.30, min_equity=0.60, is_bluff=False),
    },

    # TWO PAIR (rank 2)
    'two_pair': {
        'fish':             CheckRaiseProfile(freq=0.30, min_equity=0.52, is_bluff=False, notes='value raise — fish calls'),
        'calling_station':  CheckRaiseProfile(freq=0.40, min_equity=0.52, is_bluff=False),
        'nit':              CheckRaiseProfile(freq=0.10, min_equity=0.55, is_bluff=False, notes='almost never — nit only has it'),
        'maniac':           CheckRaiseProfile(freq=0.50, min_equity=0.50, is_bluff=False, notes='trap the aggressor'),
        'tag':              CheckRaiseProfile(freq=0.25, min_equity=0.52, is_bluff=False),
        'unknown':          CheckRaiseProfile(freq=0.20, min_equity=0.52, is_bluff=False),
    },

    # ONE PAIR (rank 1) — mostly bluff check-raises here
    'one_pair': {
        'fish':             CheckRaiseProfile(freq=0.08, min_equity=0.42, is_bluff=True,  notes='fish calls too much — avoid bluff raises'),
        'calling_station':  CheckRaiseProfile(freq=0.05, min_equity=0.42, is_bluff=True,  notes='never bluff raise a station'),
        'nit':              CheckRaiseProfile(freq=0.20, min_equity=0.40, is_bluff=True,  notes='nit folds — bluff raise works'),
        'maniac':           CheckRaiseProfile(freq=0.05, min_equity=0.45, is_bluff=True,  notes='maniac calls/re-raises — avoid'),
        'tag':              CheckRaiseProfile(freq=0.12, min_equity=0.42, is_bluff=True),
        'unknown':          CheckRaiseProfile(freq=0.10, min_equity=0.42, is_bluff=True),
    },

    # COMBO DRAW (flush + straight draw) — semi-bluff check-raise
    'combo_draw': {
        'fish':             CheckRaiseProfile(freq=0.30, min_equity=0.45, is_bluff=True,  notes='good equity but fish calls — use carefully'),
        'calling_station':  CheckRaiseProfile(freq=0.20, min_equity=0.48, is_bluff=True,  notes='they call so we need real equity'),
        'nit':              CheckRaiseProfile(freq=0.55, min_equity=0.42, is_bluff=True,  notes='nit folds a lot — great semi-bluff spot'),
        'maniac':           CheckRaiseProfile(freq=0.40, min_equity=0.45, is_bluff=True,  notes='we have equity if called'),
        'tag':              CheckRaiseProfile(freq=0.35, min_equity=0.44, is_bluff=True),
        'unknown':          CheckRaiseProfile(freq=0.30, min_equity=0.44, is_bluff=True),
    },

    # FLUSH DRAW only
    'flush_draw': {
        'fish':             CheckRaiseProfile(freq=0.18, min_equity=0.38, is_bluff=True),
        'calling_station':  CheckRaiseProfile(freq=0.10, min_equity=0.40, is_bluff=True,  notes='station calls — less fold equity'),
        'nit':              CheckRaiseProfile(freq=0.40, min_equity=0.35, is_bluff=True,  notes='nit folds to semi-bluffs'),
        'maniac':           CheckRaiseProfile(freq=0.25, min_equity=0.38, is_bluff=True,  notes='we have outs if called'),
        'tag':              CheckRaiseProfile(freq=0.22, min_equity=0.37, is_bluff=True),
        'unknown':          CheckRaiseProfile(freq=0.18, min_equity=0.37, is_bluff=True),
    },

    # OESD only
    'oesd': {
        'fish':             CheckRaiseProfile(freq=0.15, min_equity=0.38, is_bluff=True),
        'calling_station':  CheckRaiseProfile(freq=0.08, min_equity=0.40, is_bluff=True),
        'nit':              CheckRaiseProfile(freq=0.35, min_equity=0.35, is_bluff=True),
        'maniac':           CheckRaiseProfile(freq=0.20, min_equity=0.38, is_bluff=True),
        'tag':              CheckRaiseProfile(freq=0.18, min_equity=0.37, is_bluff=True),
        'unknown':          CheckRaiseProfile(freq=0.15, min_equity=0.37, is_bluff=True),
    },
}


# ---------------------------------------------------------------------------
# Flop adjustment per player profile
# ---------------------------------------------------------------------------

@dataclass
class FlopProfileAdjustment:
    """
    How to adjust flop strategy against a specific opponent type.
    All values are multipliers or additive shifts on base frequencies.
    """
    cbet_freq_mult: float       = 1.0   # Multiply base cbet frequency
    bet_size_mult: float        = 1.0   # Multiply bet sizing
    bluff_freq_mult: float      = 1.0   # Multiply bluff/semi-bluff frequency
    fold_to_raise_threshold: float = 0.08  # Extra equity needed to continue vs raise
    probe_freq_mult: float      = 1.0   # Multiply IP caller probe frequency
    call_wider: float           = 0.0   # Shift pot odds threshold for calling (neg = call wider)
    notes: str                  = ''

FLOP_PROFILE_ADJUSTMENTS = {
    'fish': FlopProfileAdjustment(
        cbet_freq_mult=1.15,        # Cbet more vs fish — they call too much
        bet_size_mult=1.30,         # Bet bigger for value
        bluff_freq_mult=0.25,       # Almost no bluffing — they call everything
        fold_to_raise_threshold=0.04,  # When fish raises they actually have it
        probe_freq_mult=1.20,
        call_wider=-0.06,           # Call wider vs fish (they bluff less)
        notes='pure value mode — fish never fold',
    ),
    'calling_station': FlopProfileAdjustment(
        cbet_freq_mult=1.10,
        bet_size_mult=1.25,
        bluff_freq_mult=0.10,       # Zero bluffing vs station
        fold_to_raise_threshold=0.05,
        probe_freq_mult=1.15,
        call_wider=-0.05,
        notes='never bluff — always bet value bigger',
    ),
    'nit': FlopProfileAdjustment(
        cbet_freq_mult=1.25,        # Cbet much more — nit folds a lot
        bet_size_mult=0.80,         # Smaller bets work — nit folds to any pressure
        bluff_freq_mult=2.00,       # Double bluff frequency — they fold
        fold_to_raise_threshold=0.18,  # Nit raises = strong hand — fold more
        probe_freq_mult=1.40,
        call_wider=0.08,            # When nit bets, need more equity
        notes='steal relentlessly — respect their bets',
    ),
    'maniac': FlopProfileAdjustment(
        cbet_freq_mult=0.80,        # Cbet less — let them bet into us
        bet_size_mult=0.90,         # Smaller to induce raises
        bluff_freq_mult=0.30,       # Rarely bluff — they call or raise
        fold_to_raise_threshold=0.02,  # Maniac raises = often bluff — call wider
        probe_freq_mult=0.60,       # Check to them more — let them bluff
        call_wider=-0.12,           # Call very wide — they bluff too much
        notes='trap mode — let them hang themselves',
    ),
    'tag': FlopProfileAdjustment(
        cbet_freq_mult=0.95,        # Near baseline vs TAG
        bet_size_mult=1.00,
        bluff_freq_mult=0.85,       # Slightly less bluffing — they defend well
        fold_to_raise_threshold=0.10,  # Respect TAG raises more
        probe_freq_mult=0.90,
        call_wider=0.03,
        notes='near GTO — avoid big deviations',
    ),
    'unknown': FlopProfileAdjustment(
        notes='baseline strategy — no adjustments',
    ),
}


# ---------------------------------------------------------------------------
# Preflop history analyser
# ---------------------------------------------------------------------------

class PreflopHistoryAnalyser:
    """
    Analyses opponent's showdown hands to estimate how wide their
    preflop opening range actually is — separate from VPIP/PFR stats.

    Key use case: if we've seen villain showdown 98s from UTG, their
    UTG opening range is clearly much wider than standard. This means:
      - On low connected boards, they connect more than we'd expect
      - Our range advantage is reduced
      - We should be more cautious about betting into them

    Returns a 'range_width_score' from 0.0 (very tight) to 1.0 (very wide)
    and a 'connects_to_board' score estimating how well their observed
    range hits a given board.
    """

    # Standard opening range widths by position (fraction of 169 combos)
    STANDARD_RANGE_WIDTH = {
        'utg':  0.12, 'utg1': 0.14, 'utg2': 0.16,
        'lj':   0.20, 'mp':   0.22, 'hj':   0.28,
        'co':   0.35, 'btn':  0.45, 'sb':   0.38,
        'bb':   0.70,  # BB defends wide
    }

    def get_range_width_score(
        self,
        stats: 'OpponentStats',
        opener_position: Optional[str],
    ) -> float:
        """
        Estimate how wide the opponent's range is in the given position.

        Returns 0.0-1.0:
          0.0 = very tight (only premiums)
          0.5 = standard for position
          1.0 = very wide / ATC
        """
        if stats.hands_seen < 6:
            return 0.5  # Not enough data — assume standard

        # Base estimate from PFR
        pfr = stats.pfr_pct
        standard = self.STANDARD_RANGE_WIDTH.get(opener_position or 'mp', 0.22)

        # How much wider/tighter than standard?
        ratio = pfr / standard if standard > 0 else 1.0
        score = min(1.0, max(0.0, ratio * 0.5))

        # Adjust from showdown hand data
        if stats.showdown_hands:
            loose_hands = self._count_loose_hands(stats.showdown_hands, opener_position)
            if loose_hands > 0:
                # They've shown down hands outside standard range — they're wider
                score = min(1.0, score + loose_hands * 0.08)

        return score

    def _count_loose_hands(
        self,
        showdown_hands: List[Tuple[str, str]],
        opener_position: Optional[str],
    ) -> int:
        """
        Count showdown hands that would be outside a standard opening range
        for the given position.
        Standard UTG range = EP_RAISE from preflop.py. 
        We approximate: any non-premium hand shown from EP/MP is "loose".
        """
        loose_count = 0
        is_ep = opener_position in ('utg', 'utg1', 'utg2')
        is_mp = opener_position in ('lj', 'mp')

        for (c1, c2) in showdown_hands:
            r1, r2 = c1[0], c2[0]
            s1, s2 = c1[1], c2[1]
            v1 = RANK_VALUE.get(r1, 2)
            v2 = RANK_VALUE.get(r2, 2)
            hi, lo = (v1, v2) if v1 >= v2 else (v2, v1)
            suited = s1 == s2
            paired = r1 == r2

            # Consider it loose if shown from EP/MP
            if is_ep:
                # Standard EP range = pairs 88+, AJs+, AQo+, KQs
                is_premium = (
                    (paired and hi >= 8) or
                    (hi == 14 and lo >= 11 and suited) or  # AJs+
                    (hi == 14 and lo >= 12) or              # AQo+
                    (hi == 13 and lo == 12 and suited)       # KQs
                )
                if not is_premium:
                    loose_count += 1

            elif is_mp:
                # Standard MP range = pairs 66+, suited broadways, AJo+
                is_standard = (
                    (paired and hi >= 6) or
                    (hi >= 11 and lo >= 10 and suited) or   # JTs+
                    (hi == 14 and lo >= 10) or               # ATo+
                    (hi == 13 and lo >= 11)                  # KJo+
                )
                if not is_standard:
                    loose_count += 1

        return loose_count

    def estimate_board_connectivity(
        self,
        stats: 'OpponentStats',
        board_values: List[int],
        opener_position: Optional[str],
    ) -> float:
        """
        Estimate how well the opponent's observed range connects with the board.
        Returns 0.0 (they miss completely) to 1.0 (they hit perfectly).

        Uses actual showdown hands if available, otherwise uses PFR-based estimate.
        """
        if not stats.showdown_hands:
            # Fall back to position-based estimate
            pfr = stats.pfr_pct
            return min(0.8, pfr * 2.5)  # Loose players connect more

        # Check each showdown hand against the board
        board_hits = 0
        for (c1, c2) in stats.showdown_hands[-20:]:  # Use last 20 showdowns
            r1_val = RANK_VALUE.get(c1[0], 2)
            r2_val = RANK_VALUE.get(c2[0], 2)

            # Does either hole card pair the board?
            pairs_board = any(v in (r1_val, r2_val) for v in board_values)
            # Does opponent have a connector with the board?
            near_board  = any(abs(v - r1_val) <= 2 or abs(v - r2_val) <= 2 for v in board_values)

            if pairs_board:
                board_hits += 2
            elif near_board:
                board_hits += 1

        return min(1.0, board_hits / (len(stats.showdown_hands[-20:]) * 2))


# ---------------------------------------------------------------------------
# Check-raise decision function
# ---------------------------------------------------------------------------

def should_check_raise(
    hand_rank: int,
    draws,                  # DrawDetector instance
    equity: float,
    texture,                # BoardTexture instance
    opponent_profile: str,
    spr: float,
    raised_already: bool,
) -> Tuple[bool, float]:
    """
    Determine if we should check-raise and at what pot fraction.

    Returns (should_raise: bool, raise_size_fraction: float)

    Check-raise sizing:
      Value:      2.5-3x the bet (represents strength)
      Semi-bluff: 2.0-2.5x the bet (needs fold equity)
    """
    if raised_already or spr < 1.5:
        return False, 0.0

    # Determine which table to use
    if hand_rank >= 6:
        table_key = 'monster'
    elif hand_rank >= 4:
        table_key = 'strong'
    elif hand_rank == 3:
        table_key = 'trips'
    elif hand_rank == 2:
        table_key = 'two_pair'
    elif hand_rank == 1:
        table_key = 'one_pair'
    elif draws.combo_draw:
        table_key = 'combo_draw'
    elif draws.flush_draw:
        table_key = 'flush_draw'
    elif draws.oesd:
        table_key = 'oesd'
    else:
        return False, 0.0  # No check-raise with air/gutshot

    profile_table = CHECK_RAISE_TABLES.get(table_key, {})
    cr_profile = profile_table.get(opponent_profile) or profile_table.get('unknown')

    if cr_profile is None:
        return False, 0.0

    # Apply texture adjustment to frequency
    freq = cr_profile.freq
    if texture.is_wet and not cr_profile.is_bluff:
        freq *= 1.20   # Value raise more on wet boards (deny equity)
    elif texture.is_dry and cr_profile.is_bluff:
        freq *= 0.70   # Bluff raise less on dry boards (less fold equity vs draws)
    elif texture.is_monotone and cr_profile.is_bluff:
        freq *= 1.15   # Monotone: semi-bluffs work well (flush draw scare)

    # Equity check
    if equity < cr_profile.min_equity:
        return False, 0.0

    import random
    if random.random() >= freq:
        return False, 0.0

    # Sizing: value raises bigger, bluff raises smaller
    if not cr_profile.is_bluff:
        size = 2.8   # 2.8x the bet = strong value signal
    else:
        size = 2.2   # 2.2x = semi-bluff, leaves room to fold

    return True, size


# ---------------------------------------------------------------------------
# Convenience accessor
# ---------------------------------------------------------------------------

def get_profile_adjustment(profile: str) -> FlopProfileAdjustment:
    """Get the flop adjustment for a given opponent profile."""
    return FLOP_PROFILE_ADJUSTMENTS.get(profile, FLOP_PROFILE_ADJUSTMENTS['unknown'])
