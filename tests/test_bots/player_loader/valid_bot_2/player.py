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
        player_info = gamestate.player_public_infos[self.player_index]
        bet_to_call = gamestate.get_bet_to_call()
        amount_to_call = bet_to_call - player_info.current_bet

        if amount_to_call == 0:
            return ('check', 0)
        else:
            return ('call', 0)
