"""Main Table class that hosts players and manages the game"""

from typing import List, Dict, Tuple, Optional
from .player import Player
from .data_classes import PlayerPublicInfo, Pot, Action
from .gamestate import PublicGamestate
from .deck_manager import DeckManager
from ..helpers.player_judge import PlayerJudge
from ..helpers.hand_judge import HandJudge


class Table:
    """Table that hosts players and manages the poker game

    This is the main orchestrator for the poker tournament, managing
    all game state, dealing cards, collecting bets, and coordinating
    between players and helper objects.

    Attributes:
        round_number: Current round number
        players: List of player objects
        player_hole_cards: Each player's hole cards
        player_public_infos: Public information for each player
        button_position: Current dealer button position
        community_cards: Community cards on the board
        total_pot: Total chips in all pots
        pots: List of pots (index 0 is main pot, 1+ are side pots)
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
        seed: Optional[int] = None
    ):
        """Initialize poker table

        Args:
            players: List of player objects
            starting_stack: Starting chip stack for each player
            blinds_schedule: Dictionary mapping round number to (SB, BB) tuples
            seed: Random seed for deck shuffling
        """
        if len(players) < 2:
            raise ValueError("Need at least 2 players")

        self.round_number = 1
        self.players = players
        self.player_hole_cards: List[Optional[Tuple[str, str]]] = [None] * len(players)
        self.player_public_infos = [
            PlayerPublicInfo(
                stack=starting_stack,
                current_bet=0,
                active=True,
                busted=False,
                is_all_in=False
            )
            for _ in players
        ]
        self.button_position = 0
        self.community_cards: List[str] = []
        self.total_pot = 0
        self.pots: List[Pot] = []
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

        # Track total chips in play for verification
        self.total_chips_in_play = starting_stack * len(players)

        # Track contributions for each player during the current hand (for side pot calculation)
        self.hand_contributions: List[int] = [0] * len(players)

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
            pots=self.pots.copy(),
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
        self.pots = []
        self.minimum_raise_amount = self.blinds[1]
        self.hand_contributions = [0] * len(self.players)

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
                info.is_all_in = False

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
        self.hand_contributions[small_blind_pos] += sb_amount
        if sb_info.stack == 0:
            sb_info.is_all_in = True

        # Post big blind
        bb_info = self.player_public_infos[big_blind_pos]
        bb_amount = min(self.blinds[1], bb_info.stack)
        bb_info.stack -= bb_amount
        bb_info.current_bet = bb_amount
        self.hand_contributions[big_blind_pos] += bb_amount
        if bb_info.stack == 0:
            bb_info.is_all_in = True

        # Record blind actions
        self.current_hand_history["preflop"].append(
            Action(small_blind_pos, "small_blind", sb_amount)
        )
        self.current_hand_history["preflop"].append(
            Action(big_blind_pos, "big_blind", bb_amount)
        )

        # Set first actor (UTG position)
        self.actor_index = self.get_next_player_index(big_blind_pos)

    def run_betting_round(self, street: str) -> bool:
        """Run a complete betting round for the given street

        Args:
            street: The betting street ('preflop', 'flop', 'turn', 'river')

        Returns:
            True if hand should continue (more than one active player), False otherwise
        """
        # Check if we have enough active players to continue
        active_count = sum(1 for info in self.player_public_infos if info.active)
        if active_count <= 1:
            return False

        # Reset bets for new street (except preflop where blinds are already posted)
        if street != "preflop":
            for info in self.player_public_infos:
                info.current_bet = 0
            # Start action after button
            self.actor_index = self.get_next_player_index(self.button_position)

        # Track the last player to bet/raise (aggressor)
        last_aggressor_idx = -1
        if street == "preflop":
            # Big blind is the last aggressor preflop
            big_blind_pos = self.get_next_player_index(
                self.get_next_player_index(self.button_position)
            )
            last_aggressor_idx = big_blind_pos

        # Get current bet amount (highest current_bet among all players)
        current_bet = max(
            (info.current_bet for info in self.player_public_infos),
            default=0
        )

        # Track if we've gone around the table once
        first_actor = self.actor_index
        first_action = True

        # Betting loop
        while True:
            # Check if betting is complete
            active_players_with_chips = [
                i for i, info in enumerate(self.player_public_infos)
                if info.active and not info.is_all_in
            ]

            # If only one player has chips left, betting is complete
            if len(active_players_with_chips) <= 1:
                break

            # If all active players have matched the bet, check if we're done
            all_matched = all(
                info.current_bet == current_bet or info.is_all_in
                for info in self.player_public_infos
                if info.active
            )

            # If all matched and we've returned to the last aggressor (or no aggressor), done
            if all_matched and not first_action:
                if last_aggressor_idx == -1:
                    break
                # If last aggressor is all-in, we can't return to them - just check if all matched
                if last_aggressor_idx >= 0 and self.player_public_infos[last_aggressor_idx].is_all_in:
                    break
                if self.actor_index == last_aggressor_idx:
                    break
                # If we've gone full circle back to first actor, done
                if self.actor_index == first_actor:
                    break

            current_player_info = self.player_public_infos[self.actor_index]

            # Skip if player is not active or is all-in
            if not current_player_info.active or current_player_info.is_all_in:
                self.actor_index = PlayerJudge.get_next_actor(
                    self.actor_index,
                    self.player_public_infos,
                    len(self.players)
                )
                # If we've cycled back to start with no action taken, and all players matched, we're done
                if self.actor_index == first_actor and not first_action:
                    if all_matched:
                        break
                continue

            # Get action from player
            gamestate = self.get_public_gamestate()
            hole_cards = self.player_hole_cards[self.actor_index]
            action_type, amount = self.players[self.actor_index].get_action(
                gamestate, hole_cards
            )

            # Validate and correct action
            action_type, amount = PlayerJudge.validate_action(
                self.actor_index,
                action_type,
                amount,
                self.player_public_infos,
                current_bet,
                self.minimum_raise_amount
            )

            # Execute the action
            self._execute_action(self.actor_index, action_type, amount, street)

            # Update last aggressor and current bet
            if action_type in ['bet', 'raise', 'all-in']:
                # Only update aggressor if this actually increases the bet
                new_total_bet = current_player_info.current_bet
                if new_total_bet > current_bet:
                    last_aggressor_idx = self.actor_index
                    current_bet = new_total_bet
                    # Update minimum raise
                    raise_amount = current_bet - (current_bet - (new_total_bet - amount))
                    self.minimum_raise_amount = raise_amount

            # Move to next player
            first_action = False
            self.actor_index = PlayerJudge.get_next_actor(
                self.actor_index,
                self.player_public_infos,
                len(self.players)
            )

        # After betting round, reconcile bets into pots (creates side pots as needed)
        self._reconcile_bets_to_pots()

        # Check if hand should continue
        active_count = sum(1 for info in self.player_public_infos if info.active)
        return active_count > 1

    def _execute_action(
        self,
        player_idx: int,
        action_type: str,
        amount: int,
        street: str
    ) -> None:
        """Execute a player action and update game state

        Args:
            player_idx: Player index
            action_type: Type of action
            amount: Amount involved
            street: Current betting street
        """
        player_info = self.player_public_infos[player_idx]

        if action_type == 'fold':
            player_info.active = False

        elif action_type == 'check':
            # No state change needed
            pass

        elif action_type == 'call':
            player_info.stack -= amount
            player_info.current_bet += amount
            self.hand_contributions[player_idx] += amount
            if player_info.stack == 0:
                player_info.is_all_in = True

        elif action_type == 'bet':
            player_info.stack -= amount
            player_info.current_bet = amount
            self.hand_contributions[player_idx] += amount
            if player_info.stack == 0:
                player_info.is_all_in = True

        elif action_type == 'raise':
            # Amount is the additional chips from stack needed for this raise
            player_info.stack -= amount
            player_info.current_bet += amount
            self.hand_contributions[player_idx] += amount
            if player_info.stack == 0:
                player_info.is_all_in = True

        elif action_type == 'all-in':
            player_info.current_bet += amount
            self.hand_contributions[player_idx] += amount
            player_info.stack = 0
            player_info.is_all_in = True

        # Record action in hand history
        self.current_hand_history[street].append(
            Action(player_idx, action_type, amount)
        )

    def end_hand(self) -> Dict[int, Tuple[str, int]]:
        """Conclude hand and distribute pot(s) to winner(s)

        Handles two cases:
        1. Everyone folded: Award entire pot to last active player
        2. Showdown: Evaluate hands and distribute each pot to best hand(s)

        Returns:
            Dictionary mapping player_idx to (hand_name, amount_won)
        """
        # Get active players
        active_players = [
            i for i, info in enumerate(self.player_public_infos)
            if info.active
        ]

        if len(active_players) == 0:
            return {}

        # CASE 1: Only one player active (everyone else folded)
        if len(active_players) == 1:
            winner_idx = active_players[0]
            amount_won = self.total_pot

            # Award entire pot to winner
            self.player_public_infos[winner_idx].stack += amount_won

            # Reset pot and pots
            self.total_pot = 0
            self.pots = []

            return {winner_idx: ("uncontested", amount_won)}

        # CASE 2: Multiple players at showdown
        # Ensure we have pots created (should be done during betting rounds)
        if not self.pots:
            # Failsafe: create main pot if no pots exist
            self.pots = [Pot(self.total_pot, active_players)]

        results: Dict[int, Tuple[str, int]] = {}

        # Distribute each pot (main pot and any side pots)
        for pot in self.pots:
            if pot.amount == 0:
                continue

            # Determine winners for this pot
            winners = HandJudge.determine_winners(
                self.player_hole_cards,
                self.community_cards,
                pot.eligible_players
            )

            if not winners:
                continue

            # Get winning hand name for display
            winning_hand = HandJudge.evaluate_hand(
                self.player_hole_cards[winners[0]],
                self.community_cards
            )

            # Distribute pot equally among winners
            share = pot.amount // len(winners)
            remainder = pot.amount % len(winners)

            for winner_idx in winners:
                self.player_public_infos[winner_idx].stack += share

                # Track total winnings for this player
                if winner_idx in results:
                    results[winner_idx] = (
                        winning_hand[0],
                        results[winner_idx][1] + share
                    )
                else:
                    results[winner_idx] = (winning_hand[0], share)

            # Give any remainder chips to first winner (closest to button)
            if remainder > 0 and winners:
                self.player_public_infos[winners[0]].stack += remainder
                results[winners[0]] = (
                    results[winners[0]][0],
                    results[winners[0]][1] + remainder
                )

        # Reset pot and pots
        self.total_pot = 0
        self.pots = []

        return results

    def _reconcile_bets_to_pots(self) -> None:
        """Move current bets into appropriate pots, creating side pots as needed

        This is called at the end of each betting round to consolidate bets into pots.
        Creates side pots when players have contributed different amounts (all-in situations).
        """
        # Get all players who have bets to add to pot
        players_with_bets = [
            i for i, info in enumerate(self.player_public_infos)
            if info.current_bet > 0
        ]

        if not players_with_bets:
            return

        # Find all unique bet levels
        bet_levels = sorted(set(
            self.player_public_infos[i].current_bet
            for i in players_with_bets
        ))

        # If everyone bet the same amount, just add to main pot
        if len(bet_levels) == 1:
            total_to_add = sum(info.current_bet for info in self.player_public_infos)

            # Determine eligible players (all active players)
            eligible = [
                i for i, info in enumerate(self.player_public_infos)
                if info.active
            ]

            # Add to existing main pot or create new one
            if self.pots and self.pots[-1].eligible_players == eligible:
                # Same eligible players as last pot, just add to it
                self.pots[-1].amount += total_to_add
            else:
                # Different eligible players, create new pot
                self.pots.append(Pot(total_to_add, eligible))

            self.total_pot += total_to_add

            # Reset current bets
            for info in self.player_public_infos:
                info.current_bet = 0
            return

        # Multiple bet levels - need to create side pots
        previous_level = 0

        for level in bet_levels:
            # Calculate amount for this pot level
            pot_amount = sum(
                min(info.current_bet, level) - min(info.current_bet, previous_level)
                for info in self.player_public_infos
                if info.current_bet > 0
            )

            if pot_amount <= 0:
                continue

            # Determine eligible players (those who bet at least to this level in THIS round)
            # Must also still be active in the hand
            # Only check current_bet to exclude players who went all-in in previous streets
            eligible = [
                i for i, info in enumerate(self.player_public_infos)
                if info.active and info.current_bet >= level
            ]

            if not eligible:
                continue

            # Add to existing pot with same eligible players or create new pot
            if self.pots and self.pots[-1].eligible_players == eligible:
                self.pots[-1].amount += pot_amount
            else:
                self.pots.append(Pot(pot_amount, eligible))

            self.total_pot += pot_amount
            previous_level = level

        # Reset current bets
        for info in self.player_public_infos:
            info.current_bet = 0

    def simulate_hand(self) -> Dict[str, any]:
        """Simulate a complete hand from start to finish

        Orchestrates all phases of a poker hand:
        1. Reset and deal
        2. Collect blinds
        3. Run betting rounds (preflop, flop, turn, river)
        4. Showdown and pot distribution
        5. Check eliminations
        6. Update game state (increment round, advance button, update blinds)

        Returns:
            Dictionary with hand results including:
            - winners: Dict mapping player_idx to (hand_name, amount_won)
            - eliminated: List of eliminated player indices
            - total_pot: Final pot size
            - ended_early: Whether hand ended before river
            - showdown: Whether hand went to showdown
        """
        # Initialize hand
        self.reset_hand_state()
        self.deal_hole_cards()
        self.collect_blinds()

        # Track if hand ends early
        ended_early = False
        showdown = False

        # Preflop betting
        should_continue = self.run_betting_round("preflop")
        if not should_continue:
            ended_early = True
            winners = self.end_hand()
            eliminated = self.check_eliminations()
            self._finalize_hand()
            return {
                "winners": winners,
                "eliminated": eliminated,
                "total_pot": sum(w[1] for w in winners.values()),
                "ended_early": ended_early,
                "showdown": showdown,
                "final_street": "preflop"
            }

        # Flop
        self.deal_flop()
        should_continue = self.run_betting_round("flop")
        if not should_continue:
            ended_early = True
            winners = self.end_hand()
            eliminated = self.check_eliminations()
            self._finalize_hand()
            return {
                "winners": winners,
                "eliminated": eliminated,
                "total_pot": sum(w[1] for w in winners.values()),
                "ended_early": ended_early,
                "showdown": showdown,
                "final_street": "flop"
            }

        # Turn
        self.deal_turn()
        should_continue = self.run_betting_round("turn")
        if not should_continue:
            ended_early = True
            winners = self.end_hand()
            eliminated = self.check_eliminations()
            self._finalize_hand()
            return {
                "winners": winners,
                "eliminated": eliminated,
                "total_pot": sum(w[1] for w in winners.values()),
                "ended_early": ended_early,
                "showdown": showdown,
                "final_street": "turn"
            }

        # River
        self.deal_river()
        should_continue = self.run_betting_round("river")

        # Showdown (hand went to completion)
        showdown = should_continue
        winners = self.end_hand()
        eliminated = self.check_eliminations()
        self._finalize_hand()

        return {
            "winners": winners,
            "eliminated": eliminated,
            "total_pot": sum(w[1] for w in winners.values()),
            "ended_early": ended_early,
            "showdown": showdown,
            "final_street": "river"
        }

    def _finalize_hand(self) -> None:
        """Finalize hand state: increment round, advance button, update blinds"""
        self.round_number += 1
        self.advance_button()
        self.update_blinds()

    def check_eliminations(self) -> List[int]:
        """Check for eliminated players (stack = 0)

        Returns:
            List of player indices that were eliminated
        """
        eliminated = []
        for i, info in enumerate(self.player_public_infos):
            if not info.busted and info.stack == 0:
                info.busted = True
                info.active = False
                eliminated.append(i)
        return eliminated

    def verify_chip_count(self) -> Tuple[bool, int, int]:
        """Verify that total chips in play equals starting chips

        Returns:
            Tuple of (is_valid, expected_total, actual_total)
        """
        # Calculate actual total chips
        player_chips = sum(info.stack for info in self.player_public_infos)
        current_bets = sum(info.current_bet for info in self.player_public_infos)
        pot_chips = self.total_pot
        pots_chips = sum(pot.amount for pot in self.pots)

        actual_total = player_chips + current_bets + pot_chips + pots_chips

        is_valid = actual_total == self.total_chips_in_play

        return is_valid, self.total_chips_in_play, actual_total

    def __repr__(self) -> str:
        active_players = sum(1 for p in self.player_public_infos if not p.busted)
        return (
            f"Table(round={self.round_number}, players={active_players}/{len(self.players)}, "
            f"pot={self.total_pot}, blinds={self.blinds})"
        )
