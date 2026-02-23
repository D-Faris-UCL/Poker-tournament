"""Invalid test bot - inherits Player but missing get_action"""

from src.core.player import Player


class InvalidNoGetAction(Player):
    """This bot inherits from Player but doesn't implement get_action"""

    def __init__(self, player_index: int):
        super().__init__(player_index)

    # Missing get_action method - this should fail validation
