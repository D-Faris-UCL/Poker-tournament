"""Test bot 2 - Always calls"""

from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate


class ValidBot2(Player):
    """Simple test bot that always calls"""

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Always call"""
        return ('call', 0)
