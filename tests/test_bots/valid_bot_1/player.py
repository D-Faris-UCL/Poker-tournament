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
        if legal['bet']:
            possible_actions.append('bet')
        if legal['raise']:
            possible_actions.append('raise')

        # Can always fold
        possible_actions.append('fold')

        # Choose random action
        action = random.choice(possible_actions)

        # Determine amount
        if action == 'bet':
            min_bet = legal['min_bet']
            max_bet = min(legal['max_bet'], player_info.stack)
            if max_bet >= min_bet:
                amount = random.randint(min_bet, max_bet)
            else:
                amount = player_info.stack
            return (action, amount)

        elif action == 'raise':
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
            return (action, 0)

        else:
            return (action, 0)
