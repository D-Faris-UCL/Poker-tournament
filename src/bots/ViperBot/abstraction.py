"""
Hand and action abstraction for CFR-based poker bot.

Improvements over v1:
  - 13 hand buckets  (was 8)  — finer-grained hand strength categories
  - 6 abstract actions (was 5) — adds a 1/3-pot raise size
  - n_opponents included in info-set key for multi-player awareness
"""

import os
import sys
import random
import functools
from typing import List, Tuple

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.normpath(os.path.join(_BOT_DIR, '..', '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Card constants ────────────────────────────────────────────────────────────
RANKS    = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
SUITS    = ['h', 'd', 'c', 's']
_RANK_IDX = {r: i for i, r in enumerate(RANKS)}   # '2'->0 … 'A'->12

# ── Abstract action indices ───────────────────────────────────────────────────
FOLD    = 0   # fold
CALL    = 1   # check or call
RAISE_T = 2   # raise ~1/3 pot  (small / "thin value" bet)
RAISE_H = 3   # raise ~2/3 pot  (standard sizing)
RAISE_P = 4   # raise ~1x  pot  (polarised / strong)
ALL_IN  = 5   # shove

NUM_ACTIONS = 6
NUM_BUCKETS = 14   # 0-5: weak made hands × draw status; 6-13: strong made hands

# ── Hand rank map ─────────────────────────────────────────────────────────────
_HAND_RANK = {
    'high_card': 0, 'one_pair': 1, 'two_pair': 2,
    'three_of_a_kind': 3, 'straight': 4, 'flush': 5,
    'full_house': 6, 'four_of_a_kind': 7,
    'straight_flush': 8, 'royal_flush': 9,
}


def full_deck() -> List[str]:
    return [r + s for r in RANKS for s in SUITS]


@functools.lru_cache(maxsize=200_000)
def eval_hand_score(hole_cards: Tuple[str, str], board: tuple) -> int:
    """Comparable integer representing hand strength at showdown.
    board must be a tuple (hashable) for caching."""
    from src.helpers.hand_judge import HandJudge
    name, vals = HandJudge.evaluate_hand(hole_cards, list(board))
    score = _HAND_RANK.get(name, 0) * 10 ** 10
    for i, v in enumerate(vals[:5]):
        score += v * (100 ** (4 - i))
    return score


# ── Preflop bucket (0-12, no simulation needed) ───────────────────────────────

def preflop_bucket(hole_cards: Tuple[str, str]) -> int:
    """
    Map preflop hand to one of 13 buckets.

    Bucket scale (rough):
      0 = trash     4 = weak-speculative    8 = decent
      1 = very weak 5 = speculative         9 = good
      2 = weak      6 = medium              10 = strong
      3 = marginal  7 = medium-strong       11 = premium
                                            12 = elite
    """
    c1, c2 = hole_cards
    r1, r2 = c1[0], c2[0]
    s1, s2 = c1[1], c2[1]
    v1, v2 = _RANK_IDX[r1], _RANK_IDX[r2]
    hi, lo = max(v1, v2), min(v1, v2)
    pair   = r1 == r2
    suited = s1 == s2
    gap    = hi - lo

    # ── Pocket pairs ──────────────────────────────────────────────────────────
    if pair:
        if hi >= 12: return 12   # KK, AA
        if hi == 11: return 11   # QQ
        if hi == 10: return 10   # JJ
        if hi == 9:  return 9    # TT
        if hi == 8:  return 8    # 99
        if hi >= 6:  return 7    # 77-88
        if hi >= 4:  return 6    # 55-66
        if hi >= 2:  return 5    # 33-44
        return 4                 # 22

    # ── Ace-high ──────────────────────────────────────────────────────────────
    if hi == 12:
        if lo == 11: return 12 if suited else 11   # AK
        if lo == 10: return 11 if suited else 10   # AQ
        if lo == 9:  return 10 if suited else 9    # AJ
        if lo == 8:  return 9  if suited else 8    # AT
        if lo >= 5:  return 7  if suited else 5    # A5-A9
        return 6 if suited else 4                  # A2-A4

    # ── King-high ─────────────────────────────────────────────────────────────
    if hi == 11:
        if lo == 10: return 10 if suited else 9    # KQ
        if lo == 9:  return 9  if suited else 8    # KJ
        if lo == 8:  return 8  if suited else 7    # KT
        if lo >= 5:  return 6  if suited else 4    # K5-K9
        return 5 if suited else 3                  # K2-K4

    # ── Queen-high ────────────────────────────────────────────────────────────
    if hi == 10:
        if lo == 9: return 9 if suited else 8      # QJ
        if lo == 8: return 8 if suited else 7      # QT
        if lo >= 6: return 6 if suited else 4      # Q6-Q9
        return 4 if suited else 2                  # Q2-Q5

    # ── Jack-high / suited connectors / broadway ──────────────────────────────
    if hi == 9:
        if lo == 8: return 8 if suited else 6      # JT
        if lo == 7: return 6 if suited else 4      # J9
        return 4 if suited else 2

    if suited:
        if gap <= 1 and lo >= 6: return 6          # T9s, 98s, 87s, 76s
        if gap <= 2 and lo >= 5: return 5          # 86s, 97s etc.
        if gap <= 1 and lo >= 3: return 4          # 65s, 54s
        return 3

    if gap <= 1 and lo >= 7: return 5              # T9o, 98o
    if gap <= 2 and lo >= 6: return 3
    return 1 if lo >= 5 else 0


# ── Draw detection helpers ────────────────────────────────────────────────────

def _has_flush_draw(hole_cards: Tuple[str, str], community_cards: tuple) -> bool:
    """Four cards to a flush (not yet complete) on flop or turn."""
    if len(community_cards) >= 5:
        return False
    from collections import Counter
    suits = Counter(c[1] for c in list(hole_cards) + list(community_cards))
    return any(v == 4 for v in suits.values())


def _has_straight_draw(hole_cards: Tuple[str, str], community_cards: tuple) -> bool:
    """Open-ended or gutshot straight draw on flop or turn."""
    if len(community_cards) >= 5:
        return False
    all_ranks = sorted(set(_RANK_IDX[c[0]] for c in list(hole_cards) + list(community_cards)))
    # Any 4 distinct ranks that span ≤ 4 (fits inside a 5-card straight window)
    n = len(all_ranks)
    for i in range(n - 3):
        if all_ranks[i + 3] - all_ranks[i] <= 4:
            return True
    return False


# ── Postflop bucket (0-13, uses HandJudge + draw detection) ──────────────────

@functools.lru_cache(maxsize=200_000)
def postflop_bucket(hole_cards: Tuple[str, str], community_cards: tuple) -> int:
    """
    Map postflop hand to one of 14 buckets.

    Weak made-hands (high card, one pair) are split by draw potential so the
    bot distinguishes "weak and drawing" from "weak and dead".

    Bucket mapping:
      0   high card,         no draw
      1   high card,         has flush or straight draw
      2   one pair (low 2-6), no draw
      3   one pair (low 2-6), has draw
      4   one pair (mid-high 7+), no draw
      5   one pair (mid-high 7+), has draw
      6   two pair — weak (top pair < T)
      7   two pair — strong (top pair T+)
      8   trips
      9   straight
      10  flush
      11  full house — weak (trips rank < T)
      12  full house — strong / four of a kind
      13  straight flush / royal flush
    """
    from src.helpers.hand_judge import HandJudge
    name, vals = HandJudge.evaluate_hand(hole_cards, list(community_cards))
    rank = _HAND_RANK.get(name, 0)
    top  = vals[0] if vals else 0

    # Strong made hands — draws irrelevant
    if rank == 2:  return 6 if top < 10 else 7    # two pair
    if rank == 3:  return 8                         # trips
    if rank == 4:  return 9                         # straight
    if rank == 5:  return 10                        # flush
    if rank == 6:  return 11 if top < 10 else 12   # full house
    if rank >= 7:  return 13                        # quads / str-flush / royal

    # Weak made hands — split by draw potential
    draw = _has_flush_draw(hole_cards, community_cards) or \
           _has_straight_draw(hole_cards, community_cards)

    if rank == 0:                          # high card
        return 1 if draw else 0
    # rank == 1: one pair
    if top <= 6:   return 3 if draw else 2  # low pair
    return 5 if draw else 4                 # mid-high pair


# ── Monte Carlo equity (used at runtime for accurate multi-opponent eval) ──────

def estimate_equity_mc(
    hole_cards: Tuple[str, str],
    community_cards: List[str],
    num_opponents: int = 1,
    sims: int = 400,
) -> float:
    """Estimate win probability via Monte Carlo simulation."""
    deck    = full_deck()
    blocked = set(hole_cards) | set(community_cards)
    avail   = [c for c in deck if c not in blocked]

    wins = ties = 0
    for _ in range(sims):
        random.shuffle(avail)
        idx  = 0
        opps = []
        for _ in range(num_opponents):
            if idx + 1 >= len(avail):
                break
            opps.append((avail[idx], avail[idx + 1]))
            idx += 2
        if not opps:
            break

        board = list(community_cards)
        board.extend(avail[idx: idx + (5 - len(board))])

        board_t = tuple(board)
        my   = eval_hand_score(hole_cards, board_t)
        best = max(eval_hand_score(o, board_t) for o in opps)

        if my > best:    wins += 1
        elif my == best: ties += 1

    return (wins + 0.5 * ties) / sims if sims > 0 else 0.5


def equity_to_bucket(equity: float) -> int:
    return min(int(equity * NUM_BUCKETS), NUM_BUCKETS - 1)
