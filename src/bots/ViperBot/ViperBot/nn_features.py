"""Feature extraction for the neural network poker bot.

Produces a 26-element float vector:
  - 20 game-state features  (hand strength, SPR, pot odds, position, …)
  -  6 CFR prior features   (Allways-in strategy probs for current infoset)

The CFR prior gives the network a near-Nash starting point so it only needs to
learn *when* to deviate (better sizing, exploiting tendencies), not basic strategy.
"""
import os
import sys
from typing import Tuple, List, Optional

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.normpath(os.path.join(_BOT_DIR, '..', '..', '..'))
if _ROOT    not in sys.path: sys.path.insert(0, _ROOT)
if _BOT_DIR not in sys.path: sys.path.insert(0, _BOT_DIR)

from abstraction import preflop_bucket, postflop_bucket

N_FEATURES   = 26
_STREET_CHAR = {'preflop': 'p', 'flop': 'f', 'turn': 't', 'river': 'r'}

# ── Lazy CFR strategy loader ──────────────────────────────────────────────────

_CFR_STRATEGY = None
_CFR_LOADED   = False


def _get_cfr_strategy() -> dict:
    global _CFR_STRATEGY, _CFR_LOADED
    if _CFR_LOADED:
        return _CFR_STRATEGY or {}
    _CFR_LOADED = True
    try:
        cfr_dir  = os.path.normpath(os.path.join(_BOT_DIR, '..', 'Allways-in'))
        cfr_path = os.path.join(cfr_dir, 'strategy.pkl')
        if cfr_dir not in sys.path:
            sys.path.insert(0, cfr_dir)
        from cfr_trainer import CFRTrainer
        _CFR_STRATEGY = CFRTrainer.load_strategy(cfr_path)
        print(f"[ViperBot] Loaded CFR prior ({len(_CFR_STRATEGY):,} infosets)")
    except Exception as e:
        print(f"[ViperBot] CFR prior unavailable ({e}), using uniform prior")
        _CFR_STRATEGY = {}
    return _CFR_STRATEGY


def _cfr_probs(gamestate, hole_cards: Tuple[str, str], player_index: int) -> List[float]:
    """6-dim strategy vector from CFR table for the current infoset.

    Returns uniform [1/6, …] when the infoset is not in the table.
    """
    strategy = _get_cfr_strategy()
    if not strategy:
        return [1 / 6] * 6

    street    = gamestate.get_current_street()
    community = gamestate.community_cards
    n_opp     = min(max(gamestate.get_active_players_count() - 1, 1), 5)

    bucket = (preflop_bucket(hole_cards)
              if street == 'preflop'
              else postflop_bucket(hole_cards, tuple(community)))

    # Rebuild abstract action history (same encoding as CFR training)
    acts_str = ''
    try:
        _MAP = {'fold': 0, 'check': 1, 'call': 1, 'raise': 3, 'all-in': 5}
        if street in gamestate.current_hand_history:
            acts = [
                str(_MAP.get(a.action_type, 1))
                for a in gamestate.current_hand_history[street].actions
                if a.action_type not in ('small_blind', 'big_blind')
            ]
            acts_str = ''.join(acts[-4:])
    except Exception:
        pass

    infoset = f"{_STREET_CHAR[street]}|{bucket}|{n_opp}|{acts_str}"
    ss      = strategy.get(infoset)          # list[float] of length 6, or None
    if ss is None:
        return [1 / 6] * 6
    total = sum(ss)
    return [p / total for p in ss] if total > 0 else [1 / 6] * 6


# ── Main feature extractor ────────────────────────────────────────────────────

def extract_features(
    gamestate,
    hole_cards: Tuple[str, str],
    player_index: int,
) -> List[float]:
    """Return a 26-element feature vector for the neural network.

    Base features (0-19):
      0  hand_strength       — normalised hand bucket
      1  pot_odds            — call / (pot + call)
      2  spr_feat            — stack / pot, capped at 20, normalised
      3  street_preflop      — one-hot
      4  street_flop         — one-hot
      5  street_turn         — one-hot
      6  street_river        — one-hot
      7  position            — distance from dealer / (n_players-1)
      8  stack_feat          — stack / (100 * BB), capped at 1
      9  call_frac           — amount_to_call / stack
     10  pot_feat            — pot / (10 * BB)
     11  commitment          — my_current_bet / pot
     12  raises_this_street  — count / 4
     13  opp_feat            — active opponents / 5
     14  is_bb               — 1 if in big-blind seat
     15  facing_raise_frac   — amount_to_call / pot, capped at 2 → /2
     16  stack_dom           — my_stack / max_opp_stack, capped at 2 → /2
     17  board_cards_feat    — len(community) / 5
     18  is_dealer           — 1 if on the button
     19  all_in_possible     — 1 if stack > amount_to_call

    CFR prior (20-25):
     20-25  CFR strategy probs for this infoset (6 values, sum = 1)
    """
    my_info        = gamestate.player_public_infos[player_index]
    street         = gamestate.get_current_street()
    community      = gamestate.community_cards
    bet_to_call    = gamestate.get_bet_to_call()
    amount_to_call = max(0, bet_to_call - my_info.current_bet)
    pot            = max(gamestate.total_pot, 1)
    stack          = my_info.stack
    bb             = max(gamestate.blinds[1], 1)
    n_total        = len(gamestate.player_public_infos)
    dealer         = gamestate.button_position

    # 0 — hand strength
    if street == 'preflop':
        hand_strength = preflop_bucket(hole_cards) / 12.0
    else:
        hand_strength = postflop_bucket(hole_cards, tuple(community)) / 13.0

    # 1 — pot odds
    pot_odds = amount_to_call / (pot + amount_to_call) if amount_to_call > 0 else 0.0

    # 2 — SPR
    spr_feat = min(stack / pot, 20.0) / 20.0

    # 3-6 — street one-hot
    street_feats = [
        1.0 if street == 'preflop' else 0.0,
        1.0 if street == 'flop'    else 0.0,
        1.0 if street == 'turn'    else 0.0,
        1.0 if street == 'river'   else 0.0,
    ]

    # 7 — position
    pos = ((player_index - dealer - 1) % n_total) / max(n_total - 1, 1)

    # 8-11
    stack_feat  = min(stack / (100.0 * bb), 1.0)
    call_frac   = min(amount_to_call / max(stack, 1), 1.0)
    pot_feat    = min(pot / (10.0 * bb), 1.0)
    commitment  = my_info.current_bet / pot

    # 12 — raises this street
    raises = 0
    try:
        if street in gamestate.current_hand_history:
            for act in gamestate.current_hand_history[street].actions:
                if act.action_type in ('raise', 'all-in'):
                    raises += 1
    except Exception:
        pass
    raises_feat = min(raises / 4.0, 1.0)

    # 13 — opponents
    n_opp    = max(0, gamestate.get_active_players_count() - 1)
    opp_feat = min(n_opp / 5.0, 1.0)

    # 14 — is big blind
    bb_pos = (dealer + 1) % 2 if n_total == 2 else (dealer + 2) % n_total
    is_bb  = 1.0 if player_index == bb_pos else 0.0

    # 15-16
    facing_raise_frac = min(amount_to_call / pot, 2.0) / 2.0
    opp_stacks = [
        gamestate.player_public_infos[i].stack
        for i in range(n_total)
        if i != player_index and not gamestate.player_public_infos[i].busted
    ]
    max_opp   = max(opp_stacks) if opp_stacks else 1
    stack_dom = min(stack / max(max_opp, 1), 2.0) / 2.0

    # 17-19
    board_cards_feat = len(community) / 5.0
    is_dealer        = 1.0 if player_index == dealer else 0.0
    all_in_possible  = 1.0 if stack > amount_to_call else 0.0

    # 20-25 — CFR prior
    cfr_prior = _cfr_probs(gamestate, hole_cards, player_index)

    features = [
        hand_strength, pot_odds, spr_feat,
        *street_feats,
        pos, stack_feat, call_frac, pot_feat, commitment,
        raises_feat, opp_feat, is_bb,
        facing_raise_frac, stack_dom,
        board_cards_feat, is_dealer, all_in_possible,
        *cfr_prior,
    ]

    assert len(features) == N_FEATURES, f"Got {len(features)}, expected {N_FEATURES}"
    return features
