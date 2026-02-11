"""Test bot 1 - Always folds"""

from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate


class ValidBot1(Player):
    """Simple test bot that always folds"""

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Always fold"""
        return ('fold', 0)
