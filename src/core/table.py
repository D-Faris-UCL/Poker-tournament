"""Main Table class that hosts players and manages the game"""

from typing import List, Dict, Tuple, Optional
from .player import Player
from .data_classes import PlayerPublicInfo, SidePot, Action
from .gamestate import PublicGamestate
from .deck_manager import DeckManager


class Table:
    """Table that hosts players and manages the poker game

    This is the main orchestrator for the poker tournament, managing
    all game state, dealing cards, collecting bets, and coordinating
    between players and helper objects.

    Attributes:
        max_rounds: Maximum number of tournament rounds
        round_number: Current round number
        players: List of player objects
        player_hole_cards: Each player's hole cards
        player_public_infos: Public information for each player
        button_position: Current dealer button position
        community_cards: Community cards on the board
        total_pot: Total chips in all pots
        side_pots: List of side pots
        blinds: Current (small_blind, big_blind)
        blinds_schedule: Schedule of blind increases by round
        actor_index: Index of player whose turn it is
        minimum_raise_amount: Minimum valid raise amount
        current_hand_history: Actions in current hand by street
        previous_hand_histories: History from previous hands
        deck_manager: Deck manager for dealing cards
    """

    def __init__(
        self,
        players: List[Player],
        starting_stack: int,
        blinds_schedule: Dict[int, Tuple[int, int]],
        max_rounds: Optional[int] = None,
        seed: Optional[int] = None
    ):
        """Initialize poker table

        Args:
            players: List of player objects
            starting_stack: Starting chip stack for each player
            blinds_schedule: Dictionary mapping round number to (SB, BB) tuples
            max_rounds: Maximum rounds (None for unlimited)
            seed: Random seed for deck shuffling
        """
        if len(players) < 2:
            raise ValueError("Need at least 2 players")

        self.max_rounds = max_rounds
        self.round_number = 1
        self.players = players
        self.player_hole_cards: List[Optional[Tuple[str, str]]] = [None] * len(players)
        self.player_public_infos = [
            PlayerPublicInfo(
                stack=starting_stack,
                current_bet=0,
                active=True,
                busted=False
            )
            for _ in players
        ]
        self.button_position = 0
        self.community_cards: List[str] = []
        self.total_pot = 0
        self.side_pots: List[SidePot] = []
        self.blinds = blinds_schedule.get(1, (10, 20))
        self.blinds_schedule = blinds_schedule
        self.actor_index = 0
        self.minimum_raise_amount = self.blinds[1]  # BB to start
        self.current_hand_history: Dict[str, List[Action]] = {
            "preflop": [],
            "flop": [],
            "turn": [],
            "river": []
        }
        self.previous_hand_histories: List[Dict[str, List[Action]]] = []

        self.deck_manager = DeckManager(seed=seed)

    def get_public_gamestate(self) -> PublicGamestate:
        """Create public gamestate object for players

        Returns:
            PublicGamestate object with visible information only
        """
        return PublicGamestate(
            round_number=self.round_number,
            player_public_infos=self.player_public_infos.copy(),
            button_position=self.button_position,
            community_cards=self.community_cards.copy(),
            total_pot=self.total_pot,
            side_pots=self.side_pots.copy(),
            blinds=self.blinds,
            blinds_schedule=self.blinds_schedule.copy(),
            minimum_raise_amount=self.minimum_raise_amount,
            current_hand_history={k: v.copy() for k, v in self.current_hand_history.items()},
            previous_hand_histories=self.previous_hand_histories.copy()
        )

    def get_next_player_index(self, current_index: int) -> int:
        """Get next non-busted player index

        Args:
            current_index: Current player index

        Returns:
            Next valid player index
        """
        num_players = len(self.players)
        next_index = (current_index + 1) % num_players

        # Skip busted players
        while self.player_public_infos[next_index].busted:
            next_index = (next_index + 1) % num_players
            if next_index == current_index:
                raise ValueError("All players are busted")

        return next_index

    def advance_button(self) -> None:
        """Move button to next non-busted player"""
        self.button_position = self.get_next_player_index(self.button_position)

    def update_blinds(self) -> None:
        """Update blinds based on current round and schedule"""
        if self.round_number in self.blinds_schedule:
            self.blinds = self.blinds_schedule[self.round_number]

    def reset_hand_state(self) -> None:
        """Reset state for a new hand"""
        self.player_hole_cards = [None] * len(self.players)
        self.community_cards = []
        self.total_pot = 0
        self.side_pots = []
        self.minimum_raise_amount = self.blinds[1]

        # Save previous hand history
        if any(len(v) > 0 for v in self.current_hand_history.values()):
            self.previous_hand_histories.append(self.current_hand_history)

        # Reset current hand history
        self.current_hand_history = {
            "preflop": [],
            "flop": [],
            "turn": [],
            "river": []
        }

        # Reset player states
        for i, info in enumerate(self.player_public_infos):
            if not info.busted:
                info.active = True
                info.current_bet = 0

        # Reset and shuffle deck
        self.deck_manager.reset_deck()
        self.deck_manager.shuffle_deck()

    def deal_hole_cards(self) -> None:
        """Deal two hole cards to each active player"""
        for i, info in enumerate(self.player_public_infos):
            if not info.busted:
                card1 = self.deck_manager.deal_card()
                card2 = self.deck_manager.deal_card()
                self.player_hole_cards[i] = (card1, card2)

    def deal_flop(self) -> None:
        """Deal the flop (3 community cards)"""
        self.deck_manager.burn_card()
        self.community_cards = self.deck_manager.deal_multiple(3)

    def deal_turn(self) -> None:
        """Deal the turn (4th community card)"""
        self.deck_manager.burn_card()
        self.community_cards.append(self.deck_manager.deal_card())

    def deal_river(self) -> None:
        """Deal the river (5th community card)"""
        self.deck_manager.burn_card()
        self.community_cards.append(self.deck_manager.deal_card())

    def collect_blinds(self) -> None:
        """Collect small and big blinds at start of hand"""
        small_blind_pos = self.get_next_player_index(self.button_position)
        big_blind_pos = self.get_next_player_index(small_blind_pos)

        # Post small blind
        sb_info = self.player_public_infos[small_blind_pos]
        sb_amount = min(self.blinds[0], sb_info.stack)
        sb_info.stack -= sb_amount
        sb_info.current_bet = sb_amount
        self.total_pot += sb_amount

        # Post big blind
        bb_info = self.player_public_infos[big_blind_pos]
        bb_amount = min(self.blinds[1], bb_info.stack)
        bb_info.stack -= bb_amount
        bb_info.current_bet = bb_amount
        self.total_pot += bb_amount

        # Record blind actions
        self.current_hand_history["preflop"].append(
            Action(small_blind_pos, "small_blind", sb_amount)
        )
        self.current_hand_history["preflop"].append(
            Action(big_blind_pos, "big_blind", bb_amount)
        )

        # Set first actor (UTG position)
        self.actor_index = self.get_next_player_index(big_blind_pos)

    def __repr__(self) -> str:
        active_players = sum(1 for p in self.player_public_infos if not p.busted)
        return (
            f"Table(round={self.round_number}, players={active_players}/{len(self.players)}, "
            f"pot={self.total_pot}, blinds={self.blinds})"
        )
