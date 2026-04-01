"""RLBot — tournament-facing poker bot that loads a fixed submission checkpoint.

Drop this directory into src/bots/ and the tournament loader will pick it up.
The model is trained offline via pretrain.py (supervised) then train.py (PPO).

The submission path is explicit so the tournament entry is stable even if
training produces weaker later checkpoints.
"""

from pathlib import Path
from typing import Tuple

import torch

try:
    from ...core.player import Player
    from ...core.gamestate import PublicGamestate
    from ...helpers.player_judge import PlayerJudge
except ImportError:
    import sys, os
    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from src.core.player import Player
    from src.core.gamestate import PublicGamestate
    from src.helpers.player_judge import PlayerJudge

from .encoder import GamestateEncoder
from .model import ActorCritic, build_action_mask, decode_action_with_player


class RLBot(Player):
    """Poker bot backed by a trained ActorCritic network.

    Inference is greedy (argmax over legal actions) for maximum expected value
    during the tournament.  During training (train.py) the TrainingBot wrapper
    samples stochastically from the distribution instead.
    """

    MODEL_CANDIDATES = (
        Path(__file__).parent / 'submission_model.pt',
        Path(__file__).parent / 'model_checkpoint.pt',
    )
    _model_cache = {}

    def __init__(self, player_index: int):
        super().__init__(player_index)
        self.encoder = GamestateEncoder()
        self.model = None
        self._loaded = False

    @classmethod
    def _get_model(cls, model_path: Path):
        model = cls._model_cache.get(model_path)
        if model is not None:
            return model

        model = ActorCritic()
        try:
            ckpt = torch.load(model_path, map_location='cpu',
                              weights_only=True)
            model.load_state_dict(ckpt['model_state_dict'])
            model.eval()
            cls._model_cache[model_path] = model
            return model
        except Exception as e:
            print(f"[RLBot] Warning: could not load model from {model_path.name}: {e}. "
                  "Falling back to check/call heuristic.")
            return None

    def _ensure_model(self) -> None:
        if self._loaded:
            return
        for model_path in self.MODEL_CANDIDATES:
            if not model_path.exists():
                continue
            self.model = self._get_model(model_path)
            self._loaded = self.model is not None
            if self._loaded:
                return

    # ── Tournament interface ──────────────────────────────────────────────────

    def get_action(
        self,
        gamestate: 'PublicGamestate',
        hole_cards: Tuple[str, str],
    ) -> Tuple[str, int]:
        self._ensure_model()
        if not self._loaded:
            return self._heuristic(gamestate)

        current_bet = gamestate.get_bet_to_call()
        legal = PlayerJudge.get_legal_actions(
            self.player_index,
            gamestate.player_public_infos,
            current_bet,
            gamestate.minimum_raise_amount,
        )
        mask = build_action_mask(legal).unsqueeze(0)  # (1, 7)

        x = self.encoder.encode(gamestate, hole_cards, self.player_index)
        x = x.unsqueeze(0)  # (1, 192)

        with torch.no_grad():
            log_probs, _ = self.model(x, mask)

        action_idx = log_probs.argmax(dim=-1).item()
        return decode_action_with_player(action_idx, gamestate, legal,
                                         self.player_index)

    # ── Heuristic fallback (no trained model) ─────────────────────────────────

    def _heuristic(self, gamestate: 'PublicGamestate') -> Tuple[str, int]:
        """Always check or call — always legal, never loses to validation."""
        bet_to_call = gamestate.get_bet_to_call()
        my_bet = gamestate.player_public_infos[self.player_index].current_bet
        return ('check', 0) if bet_to_call == my_bet else ('call', 0)

    def close(self) -> None:
        """Called by the table runner after the tournament ends."""
        pass
