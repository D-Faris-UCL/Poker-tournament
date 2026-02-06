"""Example bot that always calls or checks"""

from typing import Tuple
from ..core.player import Player
from ..core.gamestate import PublicGamestate


class CallBot(Player):
    """Simple bot that always calls/checks (never folds, never raises)

    This is a passive baseline bot for testing.
    """

    def make_decision(
        self,
        public_gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Always call or check

        Args:
            public_gamestate: Current public game state
            hole_cards: This player's hole cards

        Returns:
            Tuple of (action_type, amount)
        """
        player_info = public_gamestate.player_public_infos[self.player_index]
        current_bet = public_gamestate.get_current_bet()
        amount_to_call = current_bet - player_info.current_bet

        if amount_to_call == 0:
            return ('check', 0)
        else:
            return ('call', 0)
