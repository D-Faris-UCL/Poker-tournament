"""Invalid test bot - doesn't inherit from Player"""

from typing import Tuple


class InvalidBot:
    """This bot doesn't inherit from Player and should fail validation"""

    def __init__(self, player_index: int):
        self.player_index = player_index

    def get_action(self, gamestate, hole_cards) -> Tuple[str, int]:
        """Has get_action but doesn't inherit from Player"""
        return ('fold', 0)
