"""Test bot 1 - Makes random legal actions"""

import random
from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.player_judge import PlayerJudge


class ValidBot1(Player):
    """Simple test bot that makes random legal actions"""

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Make a random legal action"""
        player_info = gamestate.player_public_infos[self.player_index]
        current_bet = gamestate.get_bet_to_call()

        # Get legal actions
        legal = PlayerJudge.get_legal_actions(
            self.player_index,
            gamestate.player_public_infos,
            current_bet,
            gamestate.minimum_raise_amount
        )

        # Build list of legal action types
        possible_actions = []

        if legal['check']:
            possible_actions.append('check')
        if legal['call']:
            possible_actions.append('call')
        if legal['raise']:
            possible_actions.append('raise')

        # Can always fold
        possible_actions.append('fold')

        # Choose random action
        action = random.choice(possible_actions)

        # Determine amount
        if action == 'raise':
            min_raise = legal['min_raise']
            max_raise = legal['max_raise']
            current_player_bet = player_info.current_bet

            # If opening raise (no current bet), amount is total bet size
            # If re-raise, amount is additional chips needed
            if current_bet == 0:
                # Opening raise: amount is total bet
                if max_raise >= min_raise:
                    amount = random.randint(min_raise, max_raise)
                else:
                    amount = max_raise
            else:
                # Re-raise: amount is additional chips from stack
                min_raise_amount = min_raise - current_player_bet
                max_raise_amount = max_raise

                if max_raise_amount >= min_raise_amount:
                    amount = random.randint(min_raise_amount, max_raise_amount)
                else:
                    amount = max_raise_amount

            return (action, amount)

        elif action == 'call':
            return (action, 0)

        else:
            return (action, 0)
