import time
from typing import Tuple
from ..random_bot.player import RandomBot
from ...core.gamestate import PublicGamestate

class MemoryBot(RandomBot):
    """
    A bot designed to gradually leak memory to test the Sandbox limits.
    It adds ~100MB of RAM to itself every time it takes a turn.
    """
    def __init__(self, player_index):
        super().__init__(player_index)
        # We store the memory locally so it persists between turns
        self.secret_memory_stash = []

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        
        # Add ~100MB of distinct strings to our stash
        # We do this in a small loop with a micro-sleep so the parent 
        # process monitor has a chance to catch us crossing the limit!
        for _ in range(10):
            # 10MB chunk
            chunk = [" " * 100_000 for _ in range(100)] 
            self.secret_memory_stash.append(chunk)
            time.sleep(0.01) # Give the psutil monitor a tiny window to check
            
        print(f"MemoryBot {self.player_index} successfully hoarded more RAM!")

        # Return a random legal move
        return super().get_action(gamestate, hole_cards)