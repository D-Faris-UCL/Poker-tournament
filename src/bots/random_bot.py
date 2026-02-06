"""Example bot that makes random legal decisions"""

import random
from typing import Tuple
from ..core.player import Player
from ..core.gamestate import PublicGamestate
from ..helpers.player_judge import PlayerJudge


class RandomBot(Player):
    """Simple bot that makes random legal actions

    This is a baseline bot for testing the environment.
    Real competition bots should use strategy!
    """

    def make_decision(
        self,
        public_gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Make a random legal decision

        Args:
            public_gamestate: Current public game state
            hole_cards: This player's hole cards

        Returns:
            Tuple of (action_type, amount)
        """
        player_info = public_gamestate.player_public_infos[self.player_index]
        current_bet = public_gamestate.get_current_bet()

        # Get legal actions
        legal = PlayerJudge.get_legal_actions(
            self.player_index,
            public_gamestate.player_public_infos,
            current_bet,
            public_gamestate.minimum_raise_amount
        )

        # Build list of legal action types
        possible_actions = []

        if legal['check']:
            possible_actions.append('check')
        if legal['call']:
            possible_actions.append('call')
        if legal['bet']:
            possible_actions.append('bet')
        if legal['raise']:
            possible_actions.append('raise')

        # Always can fold (though usually suboptimal)
        possible_actions.append('fold')

        # Choose random action
        action = random.choice(possible_actions)

        # Determine amount
        if action == 'bet':
            # Random bet between min and max
            min_bet = legal['min_bet']
            max_bet = min(legal['max_bet'], player_info.stack)
            if max_bet >= min_bet:
                amount = random.randint(min_bet, max_bet)
            else:
                amount = player_info.stack
            return (action, amount)

        elif action == 'raise':
            # Random raise between min and max
            amount_to_call = legal['call_amount']
            min_raise_total = legal['min_raise']
            max_raise = player_info.stack
            current_player_bet = player_info.current_bet

            min_raise_amount = min_raise_total - current_player_bet
            max_raise_amount = max_raise

            if max_raise_amount >= min_raise_amount:
                amount = random.randint(min_raise_amount, max_raise_amount)
            else:
                amount = max_raise

            return (action, amount)

        elif action == 'call':
            return (action, 0)  # Amount will be determined by validator

        else:
            return (action, 0)
