"""Public game state visible to all players"""

from typing import List, Dict, Tuple, Optional
from copy import deepcopy
from .data_classes import PlayerPublicInfo, Pot, Action, StreetHistory, HandRecord


class PublicGamestate:
    """Visible game information given to players to avoid data leakage

    This object contains only information that would be visible to all
    players at the table, preventing bots from accessing hidden information
    like other players' hole cards.

    Attributes:
        round_number: Current tournament round
        player_public_infos: Public info for each player
        button_position: Index of the dealer button
        community_cards: Visible community cards
        total_pot: Total chips in all pots
        pots: List of pots (index 0 is main pot, 1+ are side pots)
        blinds: Current (small_blind, big_blind) amounts
        blinds_schedule: Schedule of blind increases
        minimum_raise_amount: Minimum valid raise amount
        current_hand_history: Actions taken in current hand by street (Dict[str, StreetHistory])
        previous_hand_histories: History from previous hands (list of HandRecord: per_street + optional showdown_details)
        current_player: Index of player whose turn it is (optional, for display)
    """

    def __init__(
        self,
        round_number: int,
        player_public_infos: List[PlayerPublicInfo],
        button_position: int,
        community_cards: List[str],
        total_pot: int,
        pots: List[Pot],
        blinds: Tuple[int, int],
        blinds_schedule: Dict[int, Tuple[int, int]],
        minimum_raise_amount: int,
        current_hand_history: Dict[str, StreetHistory],
        previous_hand_histories: List[HandRecord],
        current_player: Optional[int] = None
    ):
        """Initialize public gamestate

        Args:
            round_number: Current round number
            player_public_infos: List of player public information
            button_position: Dealer button position
            community_cards: List of community cards
            total_pot: Total pot size
            pots: List of pots (index 0 is main pot, 1+ are side pots)
            blinds: Current blinds tuple
            blinds_schedule: Dictionary mapping round to blinds
            minimum_raise_amount: Minimum raise amount
            current_hand_history: Current hand history by street (StreetHistory per street)
            previous_hand_histories: Previous hands' histories (each a HandRecord with per_street and showdown_details)
            current_player: Index of player whose turn it is (optional).
        """
        self.round_number = round_number
        self.player_public_infos = player_public_infos
        self.button_position = button_position
        self.community_cards = community_cards
        self.total_pot = total_pot
        self.pots = pots
        self.blinds = blinds
        self.blinds_schedule = blinds_schedule
        self.minimum_raise_amount = minimum_raise_amount
        self.current_hand_history = current_hand_history
        self.previous_hand_histories = previous_hand_histories
        self.current_player = current_player

    def get_active_players_count(self) -> int:
        """Count number of active players in current hand

        Returns:
            Number of active players
        """
        return sum(1 for p in self.player_public_infos if p.active)

    def get_non_busted_players_count(self) -> int:
        """Count number of non-busted players in tournament

        Returns:
            Number of non-busted players
        """
        return sum(1 for p in self.player_public_infos if not p.busted)

    def get_current_street(self) -> str:
        """Get current betting street

        Returns:
            Current street name ('preflop', 'flop', 'turn', 'river')
        """
        num_community_cards = len(self.community_cards)
        if num_community_cards == 0:
            return "preflop"
        elif num_community_cards == 3:
            return "flop"
        elif num_community_cards == 4:
            return "turn"
        elif num_community_cards == 5:
            return "river"
        else:
            raise ValueError(f"Invalid number of community cards: {num_community_cards}")

    def get_bet_to_call(self) -> int:
        """Get the current bet amount to call

        Returns:
            Current bet amount
        """
        return max((p.current_bet for p in self.player_public_infos), default=0)

    def __repr__(self) -> str:
        street = self.get_current_street()
        active = self.get_active_players_count()
        return (
            f"PublicGamestate(round={self.round_number}, street={street}, "
            f"active_players={active}, pot={self.total_pot}, "
            f"community={self.community_cards})"
        )
