"""Core data classes for poker game state"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Pot:
    """Represents a pot in the game

    Pots are organized as a list where:
    - pots[0] is the main pot (all active players eligible)
    - pots[1+] are side pots created when players go all-in

    When a player goes all-in for less than other bets, a side pot is created
    for the additional money, and the all-in player is NOT in eligible_players
    for that side pot.

    Attributes:
        amount: Total chips in this pot
        eligible_players: List of player indices eligible to win this pot
    """
    amount: int
    eligible_players: List[int]

    def __repr__(self) -> str:
        return f"Pot(amount={self.amount}, eligible={self.eligible_players})"


@dataclass
class PlayerPublicInfo:
    """Public information about a player visible to all

    Attributes:
        stack: Current chip stack
        current_bet: Amount bet in current betting round
        active: Whether player is still in the hand
        busted: Whether player has been eliminated from tournament
        is_all_in: Whether player is all-in (has committed all chips)
    """
    stack: int
    current_bet: int
    active: bool
    busted: bool
    is_all_in: bool = False

    def __repr__(self) -> str:
        status = "BUSTED" if self.busted else ("ACTIVE" if self.active else "FOLDED")
        if self.is_all_in:
            status += " (ALL-IN)"
        return f"PlayerPublicInfo(stack={self.stack}, bet={self.current_bet}, {status})"


@dataclass
class Action:
    """Represents a player action in the game

    Attributes:
        player_index: Index of the player who made the action
        action_type: Type of action ('small_blind', 'big_blind', 'fold', 'check', 'call', 'raise', 'all-in')
        amount: Amount of chips involved (0 for fold/check)
    """
    player_index: int
    action_type: str
    amount: int

    def __repr__(self) -> str:
        if self.amount > 0:
            return f"Player {self.player_index}: {self.action_type.upper()} {self.amount}"
        return f"Player {self.player_index}: {self.action_type.upper()}"

    def to_dict(self) -> dict:
        """Convert action to dictionary for serialization"""
        return {
            "player_index": self.player_index,
            "action_type": self.action_type,
            "amount": self.amount
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Action':
        """Create action from dictionary"""
        return cls(
            player_index=data["player_index"],
            action_type=data["action_type"],
            amount=data["amount"]
        )


@dataclass
class StreetHistory:
    """Per-street action history with community cards on the board.

    Attributes:
        community_cards: Community cards on the board during this street (0-5 cards).
        actions: List of actions taken on this street.
    """
    community_cards: List[str]
    actions: List[Action]

    def __repr__(self) -> str:
        return f"StreetHistory(community_cards={self.community_cards}, actions={len(self.actions)} items)"


@dataclass
class HandRecord:
    """One hand's stored history: per-street actions and optional showdown.

    Attributes:
        per_street: Action history by street (preflop, flop, turn, river).
        showdown_details: When hand went to showdown, dict with 'players', 'hands', and 'hole_cards'; otherwise None.
    """
    per_street: Dict[str, StreetHistory]
    showdown_details: Optional[dict]
