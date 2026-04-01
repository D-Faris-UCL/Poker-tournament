from typing import List, Tuple


class OpponentStats:
    """Per-opponent statistics accumulated across all hands."""

    def __init__(self):
        self.hands_seen: int = 0
        self.vpip: int = 0
        self.pfr: int = 0
        self.fold_to_cbet: int = 0
        self.cbet_faced: int = 0
        self.showdown_hands: List[Tuple[str, str]] = []
        self.aggression_count: int = 0
        self.passive_count: int = 0
        self.is_fish: bool = False

    @property
    def vpip_pct(self) -> float:
        return self.vpip / self.hands_seen if self.hands_seen else 0.25

    @property
    def pfr_pct(self) -> float:
        return self.pfr / self.hands_seen if self.hands_seen else 0.15

    @property
    def fold_to_cbet_pct(self) -> float:
        return self.fold_to_cbet / self.cbet_faced if self.cbet_faced else 0.5

    @property
    def aggression_factor(self) -> float:
        total = self.aggression_count + self.passive_count
        return self.aggression_count / total if total else 1.0

    def player_type(self) -> str:
        """Classify opponent. Fish detection runs first."""
        if self.is_fish:
            return 'fish'
        if self.hands_seen < 8:
            return 'unknown'
        v, p = self.vpip_pct, self.pfr_pct
        if v > 0.55 and p < 0.12:
            self.is_fish = True
            return 'fish'
        if v < 0.18 and p < 0.10:
            return 'nit'
        if v > 0.40 and p < 0.18:
            return 'calling_station'
        if v > 0.35 and p > 0.25:
            return 'maniac'
        if v < 0.28 and p > 0.18:
            return 'tag'
        return 'unknown'
