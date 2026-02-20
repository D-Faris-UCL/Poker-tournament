"""Example bot that takes time to make random legal decisions"""

import random
import time
from typing import Tuple
from ..random_bot.player import RandomBot
from ...core.player import Player
from ...core.gamestate import PublicGamestate
from ...helpers.player_judge import PlayerJudge


class SlowBot(RandomBot):
    """Simple bot that makes takes time to make random legal actions

    This is a baseline bot for testing the environment.
    Real competition bots should use strategy!
    """
    def __init__(self, player_index):
        super().__init__(player_index)

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Make a random legal decision

        Args:
            gamestate: Current public game state
            hole_cards: This player's hole cards

        Returns:
            Tuple of (action_type, amount)
        """
        time.sleep(5)
        return super().get_action(gamestate, hole_cards)
