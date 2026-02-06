"""Validates and corrects player actions"""

from typing import Tuple, List
from ..core.data_classes import PlayerPublicInfo


class PlayerJudge:
    """Validates player actions and ensures legal play

    Checks if actions are legal based on game state and corrects
    invalid actions by converting them to legal alternatives.
    Invalid actions default to check (if possible) or fold.
    """

    VALID_ACTIONS = {'fold', 'check', 'call', 'bet', 'raise', 'all-in'}

    @staticmethod
    def get_legal_actions(
        player_idx: int,
        player_infos: List[PlayerPublicInfo],
        current_bet: int,
        minimum_raise: int
    ) -> dict:
        """Get legal actions and valid amounts for a player

        Args:
            player_idx: Player index
            player_infos: List of all player public info
            current_bet: Current bet to match
            minimum_raise: Minimum raise amount

        Returns:
            Dictionary with legal actions and amount ranges
        """
        player_info = player_infos[player_idx]
        player_stack = player_info.stack
        player_current_bet = player_info.current_bet
        amount_to_call = current_bet - player_current_bet

        legal = {
            'fold': True,
            'check': amount_to_call == 0,
            'call': amount_to_call > 0 and player_stack >= amount_to_call,
            'bet': current_bet == 0 and player_stack > 0,
            'raise': current_bet > 0 and player_stack > amount_to_call,
            'all-in': player_stack > 0,
            'min_bet': minimum_raise if current_bet == 0 else 0,
            'min_raise': current_bet + minimum_raise if current_bet > 0 else 0,
            'max_bet': player_stack,
            'call_amount': amount_to_call
        }

        return legal

    @classmethod
    def validate_action(
        cls,
        player_idx: int,
        action_type: str,
        amount: int,
        player_infos: List[PlayerPublicInfo],
        current_bet: int,
        minimum_raise: int
    ) -> Tuple[str, int]:
        """Validate and correct player action

        Args:
            player_idx: Player making the action
            action_type: Requested action type
            amount: Requested amount
            player_infos: List of player public info
            current_bet: Current bet to match
            minimum_raise: Minimum raise amount

        Returns:
            Tuple of (corrected_action, corrected_amount)
        """
        player_info = player_infos[player_idx]
        player_stack = player_info.stack
        player_current_bet = player_info.current_bet
        amount_to_call = current_bet - player_current_bet

        legal = cls.get_legal_actions(player_idx, player_infos, current_bet, minimum_raise)

        # Normalize action type
        action_type = action_type.lower().strip()

        # Invalid action type defaults to fold
        if action_type not in cls.VALID_ACTIONS:
            return ('fold', 0) if not legal['check'] else ('check', 0)

        # FOLD - always valid
        if action_type == 'fold':
            # Don't allow folding when check is available (anti-mistake)
            if legal['check']:
                return ('check', 0)
            return ('fold', 0)

        # CHECK - only valid when no bet to call
        if action_type == 'check':
            if legal['check']:
                return ('check', 0)
            else:
                # Can't check when there's a bet, must fold
                return ('fold', 0)

        # CALL - match current bet
        if action_type == 'call':
            if legal['call']:
                return ('call', amount_to_call)
            elif amount_to_call == 0:
                return ('check', 0)
            elif player_stack < amount_to_call:
                # Not enough to call, go all-in
                return ('all-in', player_stack)
            else:
                return ('fold', 0)

        # BET - when no current bet exists
        if action_type == 'bet':
            if not legal['bet']:
                # Can't bet, check or fold
                return ('check', 0) if legal['check'] else ('fold', 0)

            # Validate bet amount
            if amount < legal['min_bet']:
                # Bet too small, convert to check
                return ('check', 0)
            elif amount > player_stack:
                # Bet too large, go all-in
                return ('all-in', player_stack)
            else:
                return ('bet', amount)

        # RAISE - increase current bet
        if action_type == 'raise':
            if not legal['raise']:
                # Can't raise, try to call or fold
                if legal['call']:
                    return ('call', amount_to_call)
                else:
                    return ('fold', 0)

            total_bet_needed = amount + player_current_bet

            # Check if raise is large enough
            if total_bet_needed < legal['min_raise']:
                # Raise too small, just call
                return ('call', amount_to_call)
            elif amount > player_stack:
                # Raise too large, go all-in
                return ('all-in', player_stack)
            else:
                return ('raise', amount)

        # ALL-IN - bet entire stack
        if action_type == 'all-in':
            if player_stack == 0:
                return ('check', 0) if legal['check'] else ('fold', 0)
            return ('all-in', player_stack)

        # Should never reach here
        return ('fold', 0) if not legal['check'] else ('check', 0)

    @staticmethod
    def is_betting_complete(
        player_infos: List[PlayerPublicInfo],
        last_aggressor_idx: int,
        current_actor_idx: int
    ) -> bool:
        """Check if betting round is complete

        Args:
            player_infos: List of player public info
            last_aggressor_idx: Index of last player to bet/raise
            current_actor_idx: Index of current actor

        Returns:
            True if betting is complete for this street
        """
        # Get active players and their bets
        active_players = [
            (i, info) for i, info in enumerate(player_infos)
            if info.active
        ]

        if len(active_players) <= 1:
            return True

        # Check if all active players have matched the current bet
        current_bet = max((info.current_bet for _, info in active_players), default=0)

        for idx, info in active_players:
            # Skip players who are all-in
            if info.is_all_in:
                continue

            # If player hasn't matched current bet, betting not complete
            if info.current_bet < current_bet:
                return False

        # If we've returned to the last aggressor, betting is complete
        if current_actor_idx == last_aggressor_idx:
            return True

        return True

    @staticmethod
    def get_next_actor(
        current_idx: int,
        player_infos: List[PlayerPublicInfo],
        num_players: int
    ) -> int:
        """Get next player to act

        Args:
            current_idx: Current player index
            player_infos: List of player public info
            num_players: Total number of players

        Returns:
            Index of next player to act
        """
        next_idx = (current_idx + 1) % num_players

        # Skip inactive players and players who are all-in
        attempts = 0
        while (not player_infos[next_idx].active or player_infos[next_idx].is_all_in) and attempts < num_players:
            next_idx = (next_idx + 1) % num_players
            attempts += 1

        if attempts >= num_players:
            # No valid next player (all folded or all-in)
            return current_idx

        return next_idx
