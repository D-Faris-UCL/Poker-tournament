"""
ViperBot — A2C neural network poker bot.

Decision pipeline:
  1. Extract 26 features (20 game-state + 6 CFR prior probabilities)
  2. Actor forward pass -> masked softmax over 6 abstract actions
  3. Sample from distribution (stochastic play, not argmax)
  4. Translate abstract action to concrete (action_type, amount)

Run nn_train.py to generate nn_weights.pkl before the tournament.
Falls back to CFR strategy, then to a heuristic if neither is found.
"""
import os
import sys
import numpy as np
from typing import Tuple

_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.normpath(os.path.join(_BOT_DIR, '..', '..', '..'))
if _ROOT    not in sys.path: sys.path.insert(0, _ROOT)
if _BOT_DIR not in sys.path: sys.path.insert(0, _BOT_DIR)

from src.core.player    import Player
from src.core.gamestate import PublicGamestate
from nn_model           import PokerNet, NUM_ACTIONS
from nn_features        import extract_features, N_FEATURES, _cfr_probs
from abstraction        import (
    FOLD, CALL, RAISE_T, RAISE_H, RAISE_P, ALL_IN,
    preflop_bucket,
)

_WEIGHTS_PATH = os.path.join(_BOT_DIR, 'nn_weights.pkl')


class ViperBot(Player):

    def __init__(self, player_index: int) -> None:
        super().__init__(player_index)
        self._net = self._load_net()

    def _load_net(self):
        try:
            net, _val = PokerNet.load(_WEIGHTS_PATH)
            if net.n_features != N_FEATURES:
                print(f"[ViperBot] Weights expect {net.n_features} features "
                      f"(need {N_FEATURES}) — run nn_train.py to retrain.")
                return None
            print(f"[ViperBot] Loaded NN weights (A2C t={net.t:,})")
            return net
        except FileNotFoundError:
            print("[ViperBot] nn_weights.pkl not found — run nn_train.py. "
                  "Using CFR prior as fallback.")
            return None
        except Exception as e:
            print(f"[ViperBot] Could not load weights: {e}. Using CFR prior.")
            return None

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str],
    ) -> Tuple[str, int]:

        my_info        = gamestate.player_public_infos[self.player_index]
        bet_to_call    = gamestate.get_bet_to_call()
        amount_to_call = max(0, bet_to_call - my_info.current_bet)
        legal          = self._legal_actions(gamestate, my_info, amount_to_call)

        legal_mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
        for a in legal: legal_mask[a] = 1.0

        if self._net is not None:
            features = extract_features(gamestate, hole_cards, self.player_index)
            probs    = self._net.get_action_probs(features, legal_mask)
            abstract = int(np.random.choice(NUM_ACTIONS, p=probs))
        else:
            # Fallback: use CFR prior directly (no NN needed)
            cfr = _cfr_probs(gamestate, hole_cards, self.player_index)
            probs = np.array(cfr, dtype=np.float32) * legal_mask
            total = probs.sum()
            if total > 1e-9:
                probs /= total
                abstract = int(np.random.choice(NUM_ACTIONS, p=probs))
            else:
                abstract = _heuristic(hole_cards, gamestate, legal)

        return _to_real(abstract, gamestate, my_info, amount_to_call)

    def _legal_actions(self, gamestate, my_info, amount_to_call: int) -> list:
        legal     = []
        stack     = my_info.stack
        pot       = gamestate.total_pot
        min_raise = gamestate.minimum_raise_amount
        remaining = stack - amount_to_call
        if amount_to_call > 0:  legal.append(FOLD)
        legal.append(CALL)
        if remaining > 0:
            if remaining >= max(min_raise, pot * 0.33): legal.append(RAISE_T)
            if remaining >= max(min_raise, pot * 0.67): legal.append(RAISE_H)
            if remaining >= max(min_raise, pot):        legal.append(RAISE_P)
            legal.append(ALL_IN)
        return legal


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_real(abstract: int, gamestate, my_info, amount_to_call: int) -> Tuple[str, int]:
    stack     = my_info.stack
    pot       = gamestate.total_pot
    min_raise = gamestate.minimum_raise_amount
    if abstract == FOLD:    return ('fold', 0)
    if abstract == CALL:    return ('check', 0) if amount_to_call == 0 else ('call', 0)
    if abstract == RAISE_T:
        amt = max(min_raise, int(pot * 0.33))
        return ('all-in', 0) if my_info.current_bet + amt >= stack else ('raise', amt)
    if abstract == RAISE_H:
        amt = max(min_raise, int(pot * 0.67))
        return ('all-in', 0) if my_info.current_bet + amt >= stack else ('raise', amt)
    if abstract == RAISE_P:
        amt = max(min_raise, pot)
        return ('all-in', 0) if my_info.current_bet + amt >= stack else ('raise', amt)
    if abstract == ALL_IN:  return ('all-in', 0)
    return ('check', 0)


def _heuristic(hole_cards: Tuple[str, str], gamestate, legal: list) -> int:
    if gamestate.get_current_street() == 'preflop':
        b = preflop_bucket(hole_cards)
        if b >= 10 and RAISE_H in legal: return RAISE_H
        if b >=  7 and RAISE_T in legal: return RAISE_T
        if b >=  4 and CALL    in legal: return CALL
        if FOLD in legal:                return FOLD
    return CALL if CALL in legal else legal[-1]
