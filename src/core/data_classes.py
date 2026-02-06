"""Core data classes for poker game state"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SidePot:
    """Represents a side pot in the game

    Attributes:
        amount: Total chips in this side pot
        eligible_players: List of player indices eligible to win this pot
    """
    amount: int
    eligible_players: List[int]

    def __repr__(self) -> str:
        return f"SidePot(amount={self.amount}, eligible={self.eligible_players})"


@dataclass
class PlayerPublicInfo:
    """Public information about a player visible to all

    Attributes:
        stack: Current chip stack
        current_bet: Amount bet in current betting round
        active: Whether player is still in the hand
        busted: Whether player has been eliminated from tournament
    """
    stack: int
    current_bet: int
    active: bool
    busted: bool

    def __repr__(self) -> str:
        status = "BUSTED" if self.busted else ("ACTIVE" if self.active else "FOLDED")
        return f"PlayerPublicInfo(stack={self.stack}, bet={self.current_bet}, {status})"


@dataclass
class Action:
    """Represents a player action in the game

    Attributes:
        player_index: Index of the player who made the action
        action_type: Type of action ('fold', 'check', 'call', 'bet', 'raise', 'all-in')
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
