"""
Flop Engine
============
Handles all flop decisions with full situational awareness.

Layers (executed in order):
  1. Board texture classification
  2. Range advantage estimation
  3. Situation detection (IP aggressor / OOP aggressor / IP caller / multiway)
  4. Cbet / check decision with frequencies
  5. Bet sizing by texture
  6. Draw overlay — adjusts frequencies and sizing when we have equity

Board texture categories (intermediate, as specified):
  DRY        — rainbow, disconnected, no flush/straight draws possible
  WET        — two-tone or suited, connected cards, many draws possible
  PAIRED     — one rank appears twice on the flop
  MONOTONE   — all three cards same suit
  CONNECTED  — two or more cards within 2 ranks of each other
  HIGH       — two or more of A/K/Q on board
  LOW        — board top card is 8 or below

Range advantage:
  We estimate whether our preflop range connects better with the board
  than villain's likely range. This is the single biggest driver of
  cbet frequency — high range advantage = bet more, bet wider.
  Low range advantage = check more, use mixed strategies.

Situation types:
  IP_AGGRESSOR   — we raised preflop, we're in position (best spot)
  OOP_AGGRESSOR  — we raised preflop, we're out of position (hardest spot)
  IP_CALLER      — we called preflop, we're in position (float + raise game)
  MULTIWAY       — 3+ players (tighten everything, less bluffing)

Draw types (detected from hole cards + board):
  FLUSH_DRAW    — 4 to a flush (roughly 35% equity)
  OESD          — open-ended straight draw (roughly 32% equity)
  COMBO_DRAW    — flush draw + straight draw (roughly 50%+ equity)
  GUTSHOT       — 4 to a straight with one gap (roughly 17% equity)
  BACKDOOR_FD   — 2 to a flush (roughly 4% extra equity)
  BACKDOOR_SD   — 2 to a straight (roughly 3% extra equity)
"""

import random
from typing import Tuple, List, Optional, Dict, TYPE_CHECKING
from src.helpers.hand_judge import HandJudge

if TYPE_CHECKING:
    from src.bots.lomaan_bot.stats import OpponentStats

from src.bots.lomaan_bot.profiles import (
    should_check_raise, get_profile_adjustment,
    PreflopHistoryAnalyser, FLOP_PROFILE_ADJUSTMENTS
)

_preflop_analyser = PreflopHistoryAnalyser()

RANK_ORDER = '23456789TJQKA'
RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER, 2)}

# ---------------------------------------------------------------------------
# Hand strength constants
# ---------------------------------------------------------------------------
HAND_RANK = {
    'high_card': 0, 'one_pair': 1, 'two_pair': 2, 'three_of_a_kind': 3,
    'straight': 4, 'flush': 5, 'full_house': 6, 'four_of_a_kind': 7,
    'straight_flush': 8, 'royal_flush': 9,
}

# ---------------------------------------------------------------------------
# Situation constants
# ---------------------------------------------------------------------------
IP_AGGRESSOR  = 'ip_aggressor'
OOP_AGGRESSOR = 'oop_aggressor'
IP_CALLER     = 'ip_caller'
MULTIWAY      = 'multiway'

# ---------------------------------------------------------------------------
# Bet sizing options as fraction of pot
# ---------------------------------------------------------------------------
SIZE_TINY   = 0.25   # 25% pot — probe / blocker
SIZE_SMALL  = 0.33   # 33% pot — dry board wide cbet
SIZE_MEDIUM = 0.50   # 50% pot — standard
SIZE_LARGE  = 0.67   # 67% pot — wet board, draws
SIZE_BIG    = 0.80   # 80% pot — very wet / semi-bluff
SIZE_POT    = 1.00   # pot bet — polarised / monotone


# ---------------------------------------------------------------------------
# Board texture classifier
# ---------------------------------------------------------------------------

class BoardTexture:
    """
    Classifies the flop into intermediate texture categories.
    Multiple categories can be true simultaneously (e.g. PAIRED + WET).
    """

    def __init__(self, community_cards: List[str]):
        assert len(community_cards) == 3, "BoardTexture requires exactly 3 cards"
        self.cards = community_cards
        self.ranks  = [c[0] for c in community_cards]
        self.suits  = [c[1] for c in community_cards]
        self.values = sorted([RANK_VALUE.get(r, 2) for r in self.ranks], reverse=True)

        # Compute all texture flags
        self.is_paired    = self._is_paired()
        self.is_monotone  = self._is_monotone()
        self.is_two_tone  = self._is_two_tone()
        self.is_connected = self._is_connected()
        self.is_high      = self._is_high()
        self.is_low       = self._is_low()
        self.is_wet       = self._is_wet()
        self.is_dry       = self._is_dry()

        # Specific draw possibilities
        self.has_flush_draw_possible   = self.is_two_tone or self.is_monotone
        self.has_straight_draw_possible = self.is_connected

    def _is_paired(self) -> bool:
        return len(set(self.ranks)) < 3

    def _is_monotone(self) -> bool:
        return len(set(self.suits)) == 1

    def _is_two_tone(self) -> bool:
        return len(set(self.suits)) == 2

    def _is_connected(self) -> bool:
        """Two or more cards within 2 ranks of each other."""
        vals = sorted([RANK_VALUE.get(r, 2) for r in self.ranks])
        return (vals[1] - vals[0] <= 2) or (vals[2] - vals[1] <= 2)

    def _is_high(self) -> bool:
        """Two or more of A/K/Q on board."""
        high_cards = sum(1 for r in self.ranks if r in ('A', 'K', 'Q'))
        return high_cards >= 2

    def _is_low(self) -> bool:
        """Top card is 8 or below."""
        return self.values[0] <= RANK_VALUE.get('8', 8)

    def _is_wet(self) -> bool:
        return self.is_two_tone or self.is_monotone or self.is_connected

    def _is_dry(self) -> bool:
        return not self.is_wet and not self.is_paired

    def danger_level(self) -> int:
        """
        0 = completely dry, 3 = maximally dangerous.
        Used to scale cbet frequency and sizing.
        """
        score = 0
        if self.is_two_tone:   score += 1
        if self.is_monotone:   score += 2
        if self.is_connected:  score += 1
        if self.is_wet:        score += 1
        return min(3, score)

    def summary(self) -> str:
        parts = []
        if self.is_paired:   parts.append('paired')
        if self.is_monotone: parts.append('monotone')
        elif self.is_two_tone: parts.append('two-tone')
        if self.is_connected: parts.append('connected')
        if self.is_high:     parts.append('high')
        if self.is_low:      parts.append('low')
        if self.is_dry:      parts.append('dry')
        return ' '.join(parts) if parts else 'unknown'


# ---------------------------------------------------------------------------
# Draw detector
# ---------------------------------------------------------------------------

class DrawDetector:
    """
    Detects what draws we hold on the flop.
    Works with hole cards + 3 community cards.
    """

    def __init__(self, hole_cards: Tuple[str, str], community_cards: List[str]):
        self.hole   = hole_cards
        self.board  = community_cards
        all_cards   = list(hole_cards) + list(community_cards)
        self.all_suits  = [c[1] for c in all_cards]
        self.all_ranks  = [c[0] for c in all_cards]
        self.all_values = sorted([RANK_VALUE.get(r, 2) for r in self.all_ranks])

        self.flush_draw    = self._has_flush_draw()
        self.oesd          = self._has_oesd()
        self.gutshot       = self._has_gutshot()
        self.combo_draw    = self.flush_draw and (self.oesd or self.gutshot)
        self.backdoor_fd   = self._has_backdoor_fd()
        self.backdoor_sd   = self._has_backdoor_sd()

        # Equity boost from draws
        self.draw_equity = self._estimate_draw_equity()

    def _has_flush_draw(self) -> bool:
        """4 cards to a flush (not yet complete)."""
        from collections import Counter
        suit_counts = Counter(self.all_suits)
        # Exactly 4 of a suit (if 5 we already made the flush — hand judge handles that)
        return any(v == 4 for v in suit_counts.values())

    def _has_oesd(self) -> bool:
        """Open-ended straight draw — 4 consecutive cards with outs on both ends."""
        vals = sorted(set(self.all_values))
        for i in range(len(vals) - 3):
            window = vals[i:i+4]
            if window[-1] - window[0] == 3 and len(window) == 4:
                # Check both ends are open (not A-high or A-low wrap)
                low_open  = window[0] > 2
                high_open = window[-1] < 14
                if low_open or high_open:
                    return True
        return False

    def _has_gutshot(self) -> bool:
        """4 to a straight with one gap."""
        vals = sorted(set(self.all_values))
        for i in range(len(vals) - 3):
            span = vals[i+3] - vals[i]
            if span == 4 and len(set(vals[i:i+4])) >= 3:
                # 4-card span of 4 with at least 3 unique cards = gutshot possibility
                return True
        return False

    def _has_backdoor_fd(self) -> bool:
        """3 cards to a flush using our hole cards."""
        from collections import Counter
        suit_counts = Counter(self.all_suits)
        # We need both hole cards to be the same suit, and board has 1 of that suit
        if self.hole[0][1] == self.hole[1][1]:
            suit = self.hole[0][1]
            return suit_counts[suit] == 3
        return False

    def _has_backdoor_sd(self) -> bool:
        """3 consecutive cards including our hole cards."""
        vals = sorted(set(self.all_values))
        for i in range(len(vals) - 2):
            if vals[i+2] - vals[i] == 2:
                return True
        return False

    def _estimate_draw_equity(self) -> float:
        """Rough extra equity from draws (added on top of made hand equity)."""
        extra = 0.0
        if self.combo_draw:   extra += 0.18
        elif self.flush_draw: extra += 0.12
        elif self.oesd:       extra += 0.12
        elif self.gutshot:    extra += 0.06
        if self.backdoor_fd:  extra += 0.03
        if self.backdoor_sd:  extra += 0.02
        return extra

    def has_any_draw(self) -> bool:
        return self.flush_draw or self.oesd or self.gutshot or self.combo_draw

    def strongest_draw(self) -> Optional[str]:
        if self.combo_draw:   return 'combo'
        if self.flush_draw:   return 'flush'
        if self.oesd:         return 'oesd'
        if self.gutshot:      return 'gutshot'
        if self.backdoor_fd:  return 'backdoor_fd'
        if self.backdoor_sd:  return 'backdoor_sd'
        return None


# ---------------------------------------------------------------------------
# Range advantage estimator
# ---------------------------------------------------------------------------

class RangeAdvantage:
    """
    Estimates whether our preflop range connects better with the board
    than the opponent's range. Uses position and preflop action as proxies.

    Returns a score from -1.0 (villain has full advantage) to +1.0 (we do).
    """

    def estimate(
        self,
        texture: BoardTexture,
        situation: str,
        opener_position: Optional[str],
        our_position: Optional[str],
        opponent_stats: Optional['OpponentStats'] = None,
    ) -> float:
        """
        Estimate our range advantage on this board.
        Positive = we connect better. Negative = villain connects better.
        """
        score = 0.0

        # HIGH boards favour EP/tight ranges (we have AK, AQ, big pairs)
        if texture.is_high:
            if situation in (IP_AGGRESSOR, OOP_AGGRESSOR):
                # We raised preflop — our range has more AK/AQ/KK/QQ
                score += 0.35
            else:
                # We called — villain's range has more high cards
                score -= 0.20

        # LOW connected boards favour calling ranges (suited connectors, small pairs)
        if texture.is_low and texture.is_connected:
            if situation in (IP_AGGRESSOR, OOP_AGGRESSOR):
                score -= 0.25  # Callers hit these harder
            else:
                score += 0.15  # We called, so we have more connectors

        # PAIRED boards favour the preflop aggressor (pairs in raising range)
        if texture.is_paired:
            if situation in (IP_AGGRESSOR, OOP_AGGRESSOR):
                score += 0.20  # Our raising range has more pocket pairs
            else:
                score -= 0.10

        # MONOTONE boards are more neutral but slightly favour tighter ranges
        if texture.is_monotone:
            score *= 0.7  # Dilute existing advantage — suits equalise things

        # Position bonus: IP aggressor has strongest range advantage signal
        if situation == IP_AGGRESSOR:
            score += 0.10
        elif situation == OOP_AGGRESSOR:
            score -= 0.05   # OOP is harder to realise advantage

        # Opponent tendency adjustment
        if opponent_stats and opponent_stats.hands_seen >= 8:
            vpip = opponent_stats.vpip_pct
            if vpip > 0.45:
                # Wide opponent = they have more garbage = we have more advantage
                score += 0.15
            elif vpip < 0.18:
                # Tight opponent = they also have strong hands = less advantage
                score -= 0.10

        return max(-1.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Main flop engine
# ---------------------------------------------------------------------------

class FlopEngine:
    """
    Complete flop decision engine.

    Called from player.py's _postflop_action when street == 'flop'.
    Returns (action_type, amount).
    """

    def __init__(self):
        self.range_adv = RangeAdvantage()

    def decide(
        self,
        state: dict,
        gamestate,
        hole_cards: Tuple[str, str],
        opponent_stats: Dict[int, 'OpponentStats'],
    ) -> Tuple[str, int]:

        community = gamestate.community_cards
        if len(community) < 3:
            return ('check', 0)

        # Build texture and draw objects
        texture = BoardTexture(community[:3])
        draws   = DrawDetector(hole_cards, community[:3])

        # Get hand strength
        hand_name, hand_values = HandJudge.evaluate_hand(hole_cards, community)
        hand_rank = HAND_RANK.get(hand_name, 0)

        # Detect situation
        situation = self._detect_situation(state, gamestate)

        # Estimate range advantage
        opener_pos = self._get_opener_position(gamestate)
        main_opp   = self._get_main_opponent_stats(gamestate, opponent_stats)
        range_adv  = self.range_adv.estimate(
            texture, situation, opener_pos, state['position'], main_opp
        )

        # Total equity = hand equity + draw equity
        base_equity = state.get('equity', 0.5)
        total_equity = min(0.99, base_equity + draws.draw_equity)

        # Get opponent profile and flop adjustment
        opp_profile  = main_opp.player_type() if main_opp else 'unknown'
        prof_adjust  = get_profile_adjustment(opp_profile)

        # Adjust range advantage using preflop history
        opener_pos   = self._get_opener_position(gamestate)
        if main_opp:
            range_adv = self._adjust_range_adv_from_history(
                range_adv, main_opp, opener_pos, texture
            )

        # Route to correct decision function
        if situation == IP_AGGRESSOR:
            return self._ip_aggressor(state, texture, draws, hand_rank, total_equity, range_adv, main_opp, opp_profile, prof_adjust)
        elif situation == OOP_AGGRESSOR:
            return self._oop_aggressor(state, texture, draws, hand_rank, total_equity, range_adv, main_opp, opp_profile, prof_adjust)
        elif situation == IP_CALLER:
            return self._ip_caller(state, texture, draws, hand_rank, total_equity, range_adv, main_opp, opp_profile, prof_adjust)
        else:
            return self._multiway(state, texture, draws, hand_rank, total_equity, range_adv, opp_profile, prof_adjust)

    # -----------------------------------------------------------------------
    # Situation detection
    # -----------------------------------------------------------------------

    def _detect_situation(self, state: dict, gamestate) -> str:
        """Determine which of the 4 situations we're in."""
        active_count = state['active_count']
        if active_count > 2:
            return MULTIWAY

        was_aggressor = state.get('was_aggressor', False)
        is_ip         = state.get('is_lp', False)

        if was_aggressor and is_ip:
            return IP_AGGRESSOR
        elif was_aggressor and not is_ip:
            return OOP_AGGRESSOR
        else:
            return IP_CALLER

    def _get_opener_position(self, gamestate) -> Optional[str]:
        if 'preflop' not in gamestate.current_hand_history:
            return None
        for a in gamestate.current_hand_history['preflop'].actions:
            if a.action_type == 'raise':
                n   = len(gamestate.player_public_infos)
                btn = gamestate.button_position
                steps = (a.player_index - btn) % n
                if steps == n - 1: return 'sb'
                return {0:'btn',1:'co',2:'hj',3:'lj',4:'mp',5:'utg2',6:'utg1',7:'utg',8:'bb'}.get(steps,'utg')
        return None

    def _get_main_opponent_stats(self, gamestate, opponent_stats) -> Optional['OpponentStats']:
        best_idx, best_hands = None, 0
        for idx, stats in opponent_stats.items():
            info = gamestate.player_public_infos[idx]
            if not info.busted and info.active and stats.hands_seen > best_hands:
                best_hands = stats.hands_seen
                best_idx   = idx
        return opponent_stats.get(best_idx) if best_idx is not None else None

    def _adjust_range_adv_from_history(self, base_adv, opp_stats, opener_pos, texture) -> float:
        """
        Adjust range advantage estimate using opponent showdown history.
        If they have shown down loose hands from early position, their range
        hits more boards than we would expect — reduce our range advantage.
        """
        board_vals = texture.values
        connects   = _preflop_analyser.estimate_board_connectivity(
            opp_stats, board_vals, opener_pos
        )
        range_width = _preflop_analyser.get_range_width_score(opp_stats, opener_pos)

        # Wide range = they connect to more boards = reduce our advantage
        # connects > 0.5 means they hit this board well
        adv_reduction = (connects - 0.4) * 0.4 + (range_width - 0.5) * 0.3
        return max(-1.0, min(1.0, base_adv - adv_reduction))

    # -----------------------------------------------------------------------
    # IP Aggressor — best situation, widest cbet range
    # -----------------------------------------------------------------------

    def _ip_aggressor(self, state, texture, draws, hand_rank, equity, range_adv, opp_stats, opp_profile="unknown", prof_adjust=None) -> Tuple[str, int]:
        pot           = state['pot']
        facing_raise  = state['facing_raise']
        raised_street = state.get('raised_this_street', False)

        # Facing a check-raise — tighten up
        if facing_raise and not raised_street:
            return self._facing_checkraise(state, texture, draws, hand_rank, equity)

        # Already bet this street — we're in a bet-call/fold spot
        if facing_raise:
            return self._call_or_fold(state, equity, draws, texture)

        # ── CBET DECISION ────────────────────────────────────────────────────
        cbet_freq = self._ip_cbet_frequency(texture, range_adv, hand_rank, draws)

        # Apply profile adjustment
        if prof_adjust:
            cbet_freq *= prof_adjust.cbet_freq_mult

        if random.random() < cbet_freq:
            size = self._cbet_size(texture, draws, hand_rank, state)
            if prof_adjust:
                size = min(1.0, size * prof_adjust.bet_size_mult)
            return self._make_bet(size, pot, state)

        # Check — possibly check-raise with strong hands if villain likely to bet
        cr_raise, cr_size = should_check_raise(
            hand_rank, draws, equity, texture, opp_profile, state['spr'], raised_street
        )
        if cr_raise:
            size = int(pot * cr_size)
            return self._make_bet(size, pot, state)

        return ('check', 0)

    def _ip_cbet_frequency(
        self, texture: BoardTexture, range_adv: float,
        hand_rank: int, draws: DrawDetector
    ) -> float:
        """
        IP aggressor cbet frequency.

        Rules:
          - High range advantage + dry board = bet almost any two cards (high freq, small size)
          - Low range advantage + wet board = check most air, bet value + strong draws
          - Strong hands always bet
          - Draws semi-bluff at variable frequency based on draw strength
        """
        # Always bet strong made hands
        if hand_rank >= 3:  # Trips or better
            return 0.95
        if hand_rank == 2:  # Two pair
            return 0.88

        # Wet boards: more selective
        danger = texture.danger_level()

        # Base frequency from range advantage
        if range_adv >= 0.3:
            base = 0.72  # Strong advantage — bet wide
        elif range_adv >= 0.0:
            base = 0.55  # Slight advantage — standard
        elif range_adv >= -0.2:
            base = 0.40  # Slight disadvantage — selective
        else:
            base = 0.28  # Clear disadvantage — value + strong draws only

        # Texture adjustment
        base -= danger * 0.07  # Each danger level reduces frequency

        # Hand strength adjustments
        if hand_rank == 1:  # One pair
            base += 0.10  # Pairs always bet with some frequency
        elif hand_rank == 0:  # Air / high card
            base -= 0.10  # Pure air bets less

        # Draw adjustment
        if draws.combo_draw:
            base += 0.20   # Combo draws always bet
        elif draws.flush_draw:
            base += 0.12   # Flush draw semi-bluff
        elif draws.oesd:
            base += 0.10   # OESD semi-bluff
        elif draws.gutshot:
            base += 0.04

        return max(0.15, min(0.95, base))

    # -----------------------------------------------------------------------
    # OOP Aggressor — hardest spot, need to protect checking range
    # -----------------------------------------------------------------------

    def _oop_aggressor(self, state, texture, draws, hand_rank, equity, range_adv, opp_stats, opp_profile="unknown", prof_adjust=None) -> Tuple[str, int]:
        pot          = state['pot']
        facing_raise = state['facing_raise']

        if facing_raise:
            # Facing a bet after we checked — decide to call/raise/fold
            return self._oop_facing_bet(state, texture, draws, hand_rank, equity, opp_profile, prof_adjust)

        # ── CBET FREQUENCY OOP ───────────────────────────────────────────────
        # OOP cbets should be more selective — we need to check with good hands
        # to protect our checking range and avoid being too predictable
        cbet_freq = self._oop_cbet_frequency(texture, range_adv, hand_rank, draws)
        if prof_adjust:
            cbet_freq *= prof_adjust.cbet_freq_mult

        if random.random() < cbet_freq:
            size = self._cbet_size(texture, draws, hand_rank, state)
            if prof_adjust:
                size = min(1.0, size * prof_adjust.bet_size_mult)
            return self._make_bet(size, pot, state)

        return ('check', 0)

    def _oop_cbet_frequency(self, texture, range_adv, hand_rank, draws) -> float:
        """
        OOP cbet frequency — significantly lower than IP.
        Key insight: OOP we need to check good hands sometimes to have a
        believable checking range. If we only check air and bet value, 
        villain can exploit by raising every time we check.
        """
        danger = texture.danger_level()

        # Strong hands: mostly bet but check-raise sometimes
        if hand_rank >= 3:
            return 0.70  # Leave 30% as check-raise / slow play

        if hand_rank == 2:
            return 0.60  # Two pair — mix of bet and check-raise

        # Range advantage drives base frequency OOP
        if range_adv >= 0.3:
            base = 0.55
        elif range_adv >= 0.0:
            base = 0.40
        else:
            base = 0.25  # No advantage OOP = mostly check

        # Texture: wet boards we check more OOP (less fold equity, more draws)
        base -= danger * 0.08

        if hand_rank == 1:
            base += 0.08
        elif hand_rank == 0:
            base -= 0.08

        # Draws: semi-bluff OOP but less than IP
        if draws.combo_draw:  base += 0.15
        elif draws.flush_draw: base += 0.08
        elif draws.oesd:       base += 0.08

        return max(0.10, min(0.75, base))

    def _oop_facing_bet(self, state, texture, draws, hand_rank, equity, opp_profile='unknown', prof_adjust=None) -> Tuple[str, int]:
        """
        OOP: we checked, villain bet. Decide: check-call, check-raise, or check-fold.
        Uses profile-aware check-raise tables.
        """
        pot_odds   = state['pot_odds']
        pot        = state['pot']
        spr        = state['spr']
        raised_yet = state.get('raised_this_street', False)

        # Use profile-aware check-raise decision
        cr_raise, cr_size_mult = should_check_raise(
            hand_rank, draws, equity, texture, opp_profile, spr, raised_yet
        )
        if cr_raise:
            size = int(pot * cr_size_mult)
            return self._make_bet(size, pot, state)

        # Call threshold adjusted by profile
        call_shift = prof_adjust.call_wider if prof_adjust else 0.0
        if equity > pot_odds + 0.05 + call_shift or hand_rank >= 1:
            return ('call', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # IP Caller — float, raise, or fold
    # -----------------------------------------------------------------------

    def _ip_caller(self, state, texture, draws, hand_rank, equity, range_adv, opp_stats, opp_profile="unknown", prof_adjust=None) -> Tuple[str, int]:
        pot          = state['pot']
        facing_raise = state['facing_raise']
        spr          = state['spr']
        pot_odds     = state['pot_odds']
        raised_yet   = state.get('raised_this_street', False)

        if not facing_raise:
            # Villain checked to us — bet for value or thin bluff
            return self._ip_caller_probe(state, texture, draws, hand_rank, equity)

        # Villain bet into us (cbet) — decide: call, raise, or fold

        # Raise with monsters and semi-bluffs on wet boards
        if hand_rank >= 3 and not raised_yet and spr > 2:
            # Raise for value and to deny equity on draws
            if texture.is_wet or random.random() < 0.45:
                size = int(pot * 2.5)
                return self._make_bet(size, pot, state)
            return ('call', 0)

        # Float / call with equity
        if equity > pot_odds + 0.04:
            return ('call', 0)

        # Semi-bluff raise with strong draws (float-raise)
        if draws.combo_draw and not raised_yet and spr > 3:
            if random.random() < 0.40:
                size = int(pot * 2.2)
                return self._make_bet(size, pot, state)
            return ('call', 0)

        if draws.flush_draw and not raised_yet and spr > 3:
            if random.random() < 0.20:
                size = int(pot * 2.2)
                return self._make_bet(size, pot, state)
            return ('call', 0)

        return ('fold', 0)

    def _ip_caller_probe(self, state, texture, draws, hand_rank, equity) -> Tuple[str, int]:
        """
        Villain checked to us in position (we're IP caller).
        Bet to take the pot or build it with our good hands.
        """
        pot = state['pot']

        # Bet value hands
        if hand_rank >= 2:
            size = self._cbet_size(texture, draws, hand_rank, state)
            return self._make_bet(size, pot, state)

        if hand_rank == 1:
            # Bet pairs in position
            if random.random() < 0.55:
                size = SIZE_SMALL if texture.is_dry else SIZE_MEDIUM
                return self._make_bet(size, pot, state)
            return ('check', 0)

        # Bluff / semi-bluff probes in position
        if draws.combo_draw:
            size = SIZE_MEDIUM
            return self._make_bet(size, pot, state)

        if draws.flush_draw or draws.oesd:
            if random.random() < 0.55:
                size = SIZE_MEDIUM
                return self._make_bet(size, pot, state)

        # Air probe with range advantage
        if equity > 0.35 and random.random() < 0.35:
            size = SIZE_SMALL
            return self._make_bet(size, pot, state)

        return ('check', 0)

    # -----------------------------------------------------------------------
    # Multiway — tighten significantly
    # -----------------------------------------------------------------------

    def _multiway(self, state, texture, draws, hand_rank, equity, range_adv, opp_profile="unknown", prof_adjust=None) -> Tuple[str, int]:
        """
        3+ players: almost never bluff, only bet strong hands,
        be very careful with marginal hands on wet boards.
        """
        pot          = state['pot']
        facing_raise = state['facing_raise']
        pot_odds     = state['pot_odds']
        active_count = state['active_count']

        # Facing a bet multiway
        if facing_raise:
            # Need much stronger hand to continue multiway
            required_equity = pot_odds + 0.08 + (active_count - 3) * 0.04
            if equity > required_equity or hand_rank >= 3:
                return ('call', 0)
            if hand_rank >= 5 and state['spr'] > 2:  # Flush+ raise
                size = int(pot * 2.2)
                return self._make_bet(size, pot, state)
            return ('fold', 0)

        # Bet only strong hands multiway
        if hand_rank >= 3:  # Trips or better
            # Bigger sizing multiway — more people to charge
            size = SIZE_LARGE if texture.is_wet else SIZE_MEDIUM
            return self._make_bet(size, pot, state)

        if hand_rank == 2:  # Two pair — bet but smaller
            if not texture.is_wet or equity > 0.60:
                size = SIZE_MEDIUM
                return self._make_bet(size, pot, state)
            return ('check', 0)

        if hand_rank == 1:  # Pair — mostly check multiway
            if equity > 0.65 and not texture.is_wet:
                size = SIZE_SMALL
                return self._make_bet(size, pot, state)
            return ('check', 0)

        # Combo draws still semi-bluff multiway but less often
        if draws.combo_draw and random.random() < 0.30:
            size = SIZE_MEDIUM
            return self._make_bet(size, pot, state)

        return ('check', 0)

    # -----------------------------------------------------------------------
    # Shared: facing a check-raise
    # -----------------------------------------------------------------------

    def _facing_checkraise(self, state, texture, draws, hand_rank, equity) -> Tuple[str, int]:
        """
        Facing a check-raise is a strong signal — villain has a strong range.
        Only continue with very strong hands or premium draws.
        """
        pot_odds = state['pot_odds']
        spr      = state['spr']

        if hand_rank >= 4:  # Straight or better — usually commit
            return ('call', 0)

        if hand_rank >= 2 and equity > pot_odds + 0.08:
            return ('call', 0)

        # Strong combo draw
        if draws.combo_draw and equity > pot_odds + 0.05:
            return ('call', 0)

        # Flush draw on dry boards — be cautious
        if draws.flush_draw and equity > pot_odds + 0.10:
            return ('call', 0)

        return ('fold', 0)

    def _call_or_fold(self, state, equity, draws, texture) -> Tuple[str, int]:
        """Generic call or fold when facing a bet."""
        pot_odds = state['pot_odds']
        threshold = pot_odds + 0.04

        if equity > threshold:
            return ('call', 0)

        if draws.flush_draw and equity > pot_odds:
            return ('call', 0)

        return ('fold', 0)

    # -----------------------------------------------------------------------
    # Bet sizing by texture
    # -----------------------------------------------------------------------

    def _cbet_size(
        self, texture: BoardTexture, draws: DrawDetector,
        hand_rank: int, state: dict
    ) -> float:
        """
        Select the correct bet size as a fraction of pot.

        Dry board  → small (33%) — betting wide, just need fold equity
        Wet board  → large (67-80%) — charging draws, protecting equity
        Monotone   → polarised pot bet or 80%
        Paired     → medium (50%) — value hands bet medium, bluffs small
        Draw heavy → scale up with draw danger
        """
        danger = texture.danger_level()

        if texture.is_monotone:
            # Polarised on monotone — bet big or small
            if hand_rank >= 2 or draws.flush_draw:
                return SIZE_BIG
            return SIZE_SMALL  # Small bluff or check

        if texture.is_paired:
            if hand_rank >= 3:
                return SIZE_MEDIUM  # Trips+ — medium to keep in bluffs
            if hand_rank >= 1:
                return SIZE_SMALL   # Pair on paired board — small
            return SIZE_SMALL       # Bluff small on paired boards

        # Standard texture sizing
        base_size = SIZE_SMALL + danger * 0.10  # Scale with wetness

        # Strong draws inflate size
        if draws.combo_draw:
            base_size = max(base_size, SIZE_LARGE)
        elif draws.flush_draw and texture.is_wet:
            base_size = max(base_size, SIZE_MEDIUM)

        # Monster hands on wet boards go bigger
        if hand_rank >= 4 and texture.is_wet:
            base_size = max(base_size, SIZE_LARGE)

        return min(SIZE_POT, base_size)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _make_bet(self, size_fraction: float, pot: int, state: dict) -> Tuple[str, int]:
        """Convert a pot fraction to an actual raise action."""
        if isinstance(size_fraction, float):
            amount = int(pot * size_fraction)
        else:
            amount = size_fraction

        min_r = state.get('min_raise', 1)
        max_r = state.get('max_raise', state['stack'])
        stack = state['stack']

        if amount >= stack or amount >= max_r:
            return ('all-in', 0)

        amount = max(amount, min_r)
        amount = min(amount, max_r)
        return ('raise', amount)
