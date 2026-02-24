"""This bot should be ignored because directory starts with __"""

from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate


class IgnoredBot(Player):
    """This bot should not be loaded because its directory starts with __"""

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        return ('fold', 0)
