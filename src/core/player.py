"""Base Player class for poker bots"""

from abc import ABC, abstractmethod
from typing import Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .gamestate import PublicGamestate


class Player(ABC):
    """Abstract base class for poker bot players

    Each bot implementation should inherit from this class and implement
    the make_decision method. External utilities will measure and restrict
    resource usage (CPU time, memory) during decision making.

    Attributes:
        player_index: Unique index identifying this player at the table
    """

    def __init__(self, player_index: int):
        """Initialize player

        Args:
            player_index: Unique index for this player (0-based)
        """
        self.player_index = player_index

    @abstractmethod
    def make_decision(
        self,
        public_gamestate: 'PublicGamestate',
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Make a decision given current game state

        Args:
            public_gamestate: Current public game state visible to all players
            hole_cards: This player's two hole cards (e.g., ('Ah', 'Kd'))

        Returns:
            Tuple of (action_type, amount) where:
                - action_type: One of 'fold', 'check', 'call', 'bet', 'raise'
                - amount: Bet/raise amount (0 for fold/check/call)

        Note:
            Invalid actions will be corrected by PlayerJudge:
            - Invalid bets/raises will be converted to check/fold
            - Invalid action types will default to fold
        """
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(index={self.player_index})"
