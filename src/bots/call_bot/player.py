from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.hand_judge import HandJudge

class CallingStationBot(Player):
    """
    A Loose-Passive 'Calling Station' Poker Bot.
    Plays approx 50% of starting hands. Seldom raises, rarely folds.
    Loves to "see the flop" and will stubbornly call down with bottom pair.
    """

    def __init__(self, player_index: int):
        super().__init__(player_index)

    def get_action(
        self, 
        gamestate: PublicGamestate, 
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        
        my_info = gamestate.player_public_infos[self.player_index]
        current_street = gamestate.get_current_street()
        amount_to_call = gamestate.get_bet_to_call() - my_info.current_bet

        # --- 1. Preflop Strategy (Loose-Passive) ---
        if current_street == 'preflop':
            if self._is_top_50_percent(hole_cards):
                # If we like it, we just call (limp in or call a raise)
                return ('call', 0) if amount_to_call > 0 else ('check', 0)
            else:
                # Trash hand, finally we fold
                return ('fold', 0) if amount_to_call > 0 else ('check', 0)

        # --- 2. Postflop Strategy (Sticky / Refuses to Fold) ---
        hand_name, _ = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
        
        # If no one bet, we just check. Calling stations rarely initiate betting.
        if amount_to_call == 0:
            return ('check', 0)

        # Facing a bet: The Calling Station logic
        
        # If we have ANY made hand (even a pair of 2s on a board of Aces), we call.
        if hand_name != 'high_card':
            return ('call', 0)
            
        # If we only have high card, check our pot odds and overcards
        pot_total = gamestate.total_pot + amount_to_call
        pot_odds = amount_to_call / pot_total if pot_total > 0 else 0
        
        # We stubbornly float the flop if it's cheap, or if we have an Ace/King
        if current_street == 'flop' and (pot_odds < 0.25 or self._has_overcard(hole_cards)):
            return ('call', 0)

        # If it's the turn/river, the bet is big, and we truly have nothing, we sigh and fold.
        return ('fold', 0)

    # ==========================================
    #             HELPER UTILITIES
    # ==========================================

    def _is_top_50_percent(self, hole_cards: Tuple[str, str]) -> bool:
        """
        Approximates the top ~50% of starting hands.
        Includes any pair, any Ace, any King, any suited cards, or any two cards 8+.
        """
        rank_map = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        
        def get_val(card):
            return rank_map.get(card[0], int(card[0]) if card[0].isdigit() else 0)

        v1 = get_val(hole_cards[0])
        v2 = get_val(hole_cards[1])
        is_suited = hole_cards[0][1] == hole_cards[1][1]

        if v1 == v2: return True                  # Any pocket pair
        if v1 >= 13 or v2 >= 13: return True      # Any Ace or King
        if is_suited: return True                 # Any suited cards (loves flushes)
        if v1 >= 8 and v2 >= 8: return True       # Any two cards 8 or higher
        
        return False

    def _has_overcard(self, hole_cards: Tuple[str, str]) -> bool:
        """Checks if the bot holds an Ace or a King to justify stubborn calls."""
        rank_map = {'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        v1 = rank_map.get(hole_cards[0][0], 0)
        v2 = rank_map.get(hole_cards[1][0], 0)
        return v1 >= 13 or v2 >= 13