"""Deck management for poker games"""

import random
from typing import List, Optional


class DeckManager:
    """Manages card deck for poker game

    Attributes:
        remaining_cards: Cards still in the deck
        burn_cards: Cards that have been burned
        seed: Random seed for reproducibility
    """

    RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', 'T', 'J', 'Q', 'K', 'A']
    SUITS = ['h', 'd', 'c', 's']  # hearts, diamonds, clubs, spades

    def __init__(self, seed: Optional[int] = None):
        """Initialize deck manager

        Args:
            seed: Random seed for shuffling (None for random)
        """
        self.remaining_cards: List[str] = []
        self.burn_cards: List[str] = []
        self.seed: Optional[int] = seed
        self.reset_deck()

    def reset_deck(self) -> None:
        """Reset deck to full 52 cards"""
        self.remaining_cards = [
            f"{rank}{suit}"
            for suit in self.SUITS
            for rank in self.RANKS
        ]
        self.burn_cards = []

    def shuffle_deck(self, seed: Optional[int] = None) -> None:
        """Shuffle the deck

        Args:
            seed: Random seed for shuffling (uses instance seed if None)
        """
        if seed is not None:
            self.seed = seed

        if self.seed is not None:
            random.seed(self.seed)

        random.shuffle(self.remaining_cards)

    def deal_card(self) -> str:
        """Deal one card from the top of the deck

        Returns:
            Card string (e.g., 'Ah' for Ace of hearts)

        Raises:
            ValueError: If no cards remain in deck
        """
        if not self.remaining_cards:
            raise ValueError("No cards remaining in deck")

        return self.remaining_cards.pop(0)

    def burn_card(self) -> str:
        """Burn one card (remove from play without dealing)

        Returns:
            The burned card

        Raises:
            ValueError: If no cards remain in deck
        """
        if not self.remaining_cards:
            raise ValueError("No cards remaining in deck")

        card = self.remaining_cards.pop(0)
        self.burn_cards.append(card)
        return card

    def deal_multiple(self, count: int) -> List[str]:
        """Deal multiple cards

        Args:
            count: Number of cards to deal

        Returns:
            List of dealt cards

        Raises:
            ValueError: If not enough cards remain
        """
        if len(self.remaining_cards) < count:
            raise ValueError(f"Not enough cards: need {count}, have {len(self.remaining_cards)}")

        return [self.deal_card() for _ in range(count)]

    def cards_remaining(self) -> int:
        """Get number of cards remaining in deck

        Returns:
            Number of cards left
        """
        return len(self.remaining_cards)

    def __repr__(self) -> str:
        return f"DeckManager(remaining={len(self.remaining_cards)}, burned={len(self.burn_cards)})"
