# Poker Tournament Architecture

## Overview

This is a complete No-Limit Texas Hold'em tournament simulator designed for AI bot development and competitive play. The architecture emphasizes clean separation of concerns, information security, and extensibility.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tournament Framework                      │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
         ┌────▼────┐                    ┌─────▼─────┐
         │  Table  │◄───────────────────┤  Players  │
         │ (Core)  │                    │  (Bots)   │
         └────┬────┘                    └───────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼────┐ ┌──▼──┐ ┌───▼──────┐
│ Deck   │ │Pots │ │ Gamestate│
│Manager │ │     │ │ (Public) │
└────────┘ └─────┘ └──────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
┌───▼────┐ ┌──▼────────┐
│  Hand  │ │  Player   │
│ Judge  │ │  Judge    │
└────────┘ └───────────┘
```

## Core Components

### 1. Table (`src/core/table.py`)

**Role:** Main game orchestrator and state manager

**Key Responsibilities:**
- Manages the full tournament lifecycle
- Coordinates betting rounds across all streets
- Handles pot distribution and side pot creation
- Tracks chip counts and verifies conservation
- Enforces blind schedules and button rotation

**Critical Methods:**

| Method | Purpose |
|--------|---------|
| `simulate_hand()` | Orchestrates a complete hand from deal to showdown |
| `run_betting_round(street)` | Executes betting logic for a single street |
| `_reconcile_bets_to_pots()` | Creates side pots for all-in scenarios |
| `end_hand()` | Evaluates hands and distributes winnings |
| `collect_blinds()` | Posts small and big blinds |
| `check_eliminations()` | Identifies and marks busted players |

**State Tracking:**
- `players`: List of Player instances
- `player_hole_cards`: Private cards (List[Optional[Tuple[str, str]]])
- `player_public_infos`: Public information for each player
- `community_cards`: Board cards
- `pots`: List of Pot objects (index 0 = main pot, 1+ = side pots)
- `total_pot`: Aggregate chip total across all pots
- `blinds_schedule`: Dict mapping round number to (SB, BB)
- `current_hand_history`: Actions by street
- `hand_contributions`: Cumulative bets per player for pot calculation

**Betting Round Algorithm:**
1. Reset street-specific state (bets, actor position)
2. Track last aggressor (player who bet/raised)
3. Loop through players collecting actions
4. Validate actions via PlayerJudge
5. Execute actions and update state
6. Continue until all active players match bet or are all-in
7. Reconcile bets into appropriate pots

**Side Pot Creation:**
When players are all-in with different stack sizes, the system creates multiple pots:
- Finds all unique bet levels
- Creates a pot for each level with eligible players
- Only players who contributed at that level can win that pot
- Handles complex multi-way all-in scenarios automatically

### 2. Player (`src/core/player.py`)

**Role:** Abstract base class for all bot implementations

**Interface:**
```python
@abstractmethod
def get_action(
    self,
    gamestate: PublicGamestate,
    hole_cards: Tuple[str, str]
) -> Tuple[str, int]:
    """Return (action_type, amount)"""
    pass
```

**Action Types:**
- `'fold'`: Exit the hand (amount = 0)
- `'check'`: Pass action when no bet to call (amount = 0)
- `'call'`: Match current bet (amount = chips needed to match)
- `'bet'`: Make first bet on a street (amount = bet size)
- `'raise'`: Increase existing bet (amount = additional chips to add)
- `'all-in'`: Bet entire remaining stack (amount = remaining stack)

**Design Principles:**
- Bots receive only PUBLIC information (no other players' hole cards)
- Invalid actions are corrected automatically by PlayerJudge
- Bots don't need to track game state - it's provided each action
- Simple interface enables rapid bot development

**Attributes:**
- `player_index`: Position at table (0 to N-1)

### 3. PublicGamestate (`src/core/gamestate.py`)

**Role:** Information container passed to bots

**Purpose:** Prevents information leakage by exposing only visible game state

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `round_number` | int | Current tournament round |
| `player_public_infos` | List[PlayerPublicInfo] | Public info for all players |
| `button_position` | int | Dealer button index |
| `community_cards` | List[str] | Board cards (0-5 cards) |
| `total_pot` | int | Total chips in all pots |
| `pots` | List[Pot] | Individual pots with eligibility |
| `blinds` | Tuple[int, int] | Current (small_blind, big_blind) |
| `blinds_schedule` | Dict[int, Tuple[int, int]] | Future blind levels |
| `minimum_raise_amount` | int | Minimum valid raise size |
| `current_hand_history` | Dict[str, List[Action]] | Actions by street |
| `previous_hand_histories` | List[Dict[...]] | Past hand histories |

**Utility Methods:**
- `get_current_street()`: Returns 'preflop', 'flop', 'turn', or 'river'
- `get_bet_to_call()`: Current bet amount to match
- `get_active_players_count()`: Number of players still in hand
- `get_non_busted_players_count()`: Players remaining in tournament
- `copy()`: Deep copy for safe manipulation

### 4. Data Classes (`src/core/data_classes.py`)

#### PlayerPublicInfo
```python
@dataclass
class PlayerPublicInfo:
    stack: int           # Remaining chips
    current_bet: int     # Bet on current street
    active: bool         # Still in current hand
    busted: bool         # Eliminated from tournament
    is_all_in: bool      # All chips committed
```

#### Pot
```python
@dataclass
class Pot:
    amount: int                  # Chips in pot
    eligible_players: List[int]  # Player indices who can win
```

#### Action
```python
@dataclass
class Action:
    player_index: int
    action_type: str
    amount: int
```

### 5. DeckManager (`src/core/deck_manager.py`)

**Role:** Card deck management with reproducible shuffling

**Card Notation:**
- Ranks: `2, 3, 4, 5, 6, 7, 8, 9, T, J, Q, K, A`
- Suits: `h` (hearts), `d` (diamonds), `c` (clubs), `s` (spades)
- Example: `'Ah'` = Ace of hearts, `'Ks'` = King of spades

**Features:**
- Seeded random shuffling for deterministic games
- Burn card tracking
- Remaining card counting

**Key Methods:**
- `shuffle_deck()`: Randomize deck order
- `deal_card()`: Draw next card
- `burn_card()`: Remove card without dealing
- `deal_multiple(n)`: Deal N cards at once
- `cards_remaining()`: Check deck status

### 6. HandJudge (`src/helpers/hand_judge.py`)

**Role:** Hand evaluation and winner determination

**Hand Rankings (weakest to strongest):**
1. High Card
2. One Pair
3. Two Pair
4. Three of a Kind
5. Straight (includes wheel: A-2-3-4-5)
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush
10. Royal Flush (A-K-Q-J-T suited)

**Key Methods:**

```python
evaluate_hand(
    hole_cards: Tuple[str, str],
    community_cards: List[str]
) -> Tuple[str, Tuple[int, ...]]
```
Returns hand name and card values for comparison.

```python
compare_hands(
    hand1: Tuple[str, Tuple[int, ...]],
    hand2: Tuple[str, Tuple[int, ...]]
) -> int
```
Returns -1 (hand1 wins), 0 (tie), or 1 (hand2 wins).

```python
determine_winners(
    all_hole_cards: List[Optional[Tuple[str, str]]],
    community_cards: List[str],
    eligible_players: List[int]
) -> List[int]
```
Finds all winners from eligible players (handles ties).

**Tie-Breaking:**
- Compares hand ranks first
- If ranks equal, compares card values (kickers)
- Supports split pots for identical hands

### 7. PlayerJudge (`src/helpers/player_judge.py`)

**Role:** Action validation and rule enforcement

**Purpose:** Don't trust bot actions - validate and correct them

**Key Methods:**

```python
validate_action(
    player_idx: int,
    action_type: str,
    amount: int,
    player_infos: List[PlayerPublicInfo],
    current_bet: int,
    minimum_raise_amount: int
) -> Tuple[str, int]
```
Returns corrected (action_type, amount) tuple.

**Validation Rules:**
- Can't fold when check is available
- Can't bet when someone already bet (must raise/call/fold)
- Can't raise below minimum_raise_amount
- Insufficient chips → forced all-in
- Invalid amounts → corrected to legal values

```python
get_legal_actions(
    player_idx: int,
    player_infos: List[PlayerPublicInfo],
    current_bet: int,
    minimum_raise_amount: int
) -> Dict[str, any]
```
Returns dictionary of legal actions with constraints:
```python
{
    'can_check': bool,
    'can_call': bool,
    'call_amount': int,
    'can_bet': bool,
    'min_bet': int,
    'max_bet': int,
    'can_raise': bool,
    'min_raise': int,
    'max_raise': int,
    'can_fold': bool
}
```

**Other Utilities:**
- `get_next_actor()`: Find next non-busted, non-all-in player
- `is_betting_complete()`: Check if round should end

## Game Flow

### Hand Lifecycle

```
1. SETUP
   ├─ reset_hand_state()
   ├─ deal_hole_cards()
   └─ collect_blinds()

2. PREFLOP
   ├─ run_betting_round('preflop')
   └─ Check if hand continues

3. FLOP (if multiple players active)
   ├─ deal_flop() [3 cards]
   ├─ run_betting_round('flop')
   └─ Check if hand continues

4. TURN (if multiple players active)
   ├─ deal_turn() [1 card]
   ├─ run_betting_round('turn')
   └─ Check if hand continues

5. RIVER (if multiple players active)
   ├─ deal_river() [1 card]
   └─ run_betting_round('river')

6. SHOWDOWN
   ├─ end_hand() [evaluate & distribute]
   ├─ check_eliminations()
   └─ _finalize_hand() [advance button, update blinds]
```

### Betting Round Flow

```
START
  │
  ├─ Reset street bets to 0 (except preflop)
  ├─ Set first actor (UTG or SB)
  └─ Track last aggressor
  │
LOOP for each player:
  │
  ├─ Skip if not active or all-in
  ├─ Get action from bot (get_action)
  ├─ Validate action (PlayerJudge)
  ├─ Execute action (update state)
  ├─ Update aggressor if bet/raise
  └─ Move to next player
  │
CHECK end conditions:
  │
  ├─ Only one player with chips? → END
  ├─ All matched current bet? → Check if returned to aggressor
  └─ Returned to aggressor? → END
  │
END
  │
  └─ Reconcile bets into pots
```

## Information Security

### What Bots CAN See:
- Their own hole cards
- Community cards
- All players' stack sizes
- All players' current bets
- Who is active/folded/all-in/busted
- Pot sizes and side pot structure
- Betting history (actions and amounts)
- Blind schedule and current blinds

### What Bots CANNOT See:
- Other players' hole cards
- Cards remaining in deck
- Future cards to be dealt
- Internal table state (e.g., `hand_contributions`)

### How Security is Enforced:
1. Bots receive `PublicGamestate` object (no private data)
2. Hole cards passed separately for current player only
3. Table maintains private state inaccessible to bots
4. No direct access to Table object from Player methods

## Chip Conservation

The system guarantees no chips are created or destroyed:

**Tracking:**
```python
total_chips = (player_stacks) + (current_bets) + (total_pot) + (sum of pots)
```

**Verification:**
```python
table.verify_chip_count()  # Returns (is_valid, expected, actual)
```

**Tested Scenarios:**
- Simple heads-up pots
- All-in with side pots
- Split pots (ties)
- Multiple side pots with different winners
- Complex multi-way all-ins

## Side Pot Algorithm

When players go all-in with different stack sizes, multiple pots are created:

### Example Scenario:
- Player A: 100 chips (all-in)
- Player B: 300 chips (all-in)
- Player C: 500 chips (call)

### Pot Creation:
1. **Main Pot:** 300 chips (100 × 3 players)
   - Eligible: A, B, C

2. **Side Pot 1:** 400 chips (200 × 2 players)
   - Eligible: B, C

3. **Side Pot 2:** 200 chips (200 × 1 player)
   - Eligible: C

### Distribution:
- Player C wins all pots: Gets 900 chips
- Player B wins with A folded: Gets Side Pot 1 + Side Pot 2 (600), A gets Main Pot (300)
- Player A wins all: Gets Main Pot (300), remaining distributed among B/C

**Implementation:**
The `_reconcile_bets_to_pots()` method automatically handles this by:
1. Sorting bet levels
2. Creating a pot for each level
3. Tracking eligibility based on contribution

## Blind Schedule

Blinds increase over time to force action:

```python
blinds_schedule = {
    1: (10, 20),       # Rounds 1-49: 10/20 blinds
    50: (25, 50),      # Rounds 50-99: 25/50 blinds
    100: (50, 100),    # Rounds 100+: 50/100 blinds
}
```

**Implementation:**
- Table checks `round_number` after each hand
- If new blind level exists in schedule, updates `self.blinds`
- Blinds automatically apply at start of next hand

## Tournament Lifecycle

```
INITIALIZATION
  ├─ Create Player instances (bots)
  ├─ Define blinds schedule
  └─ Create Table with starting stacks

TOURNAMENT LOOP
  │
  FOR each hand:
    │
    ├─ simulate_hand()
    ├─ Check eliminations
    ├─ Increment round
    ├─ Advance button
    └─ Update blinds
    │
    UNTIL only one player remains
  │
END
  │
  └─ Winner is last non-busted player
```

## Testing Strategy

### Unit Tests (`tests/test_components.py`)
- Deck shuffling and dealing
- Hand evaluation (all 10 hand types)
- Hand comparison and tie-breaking
- Action validation
- Data class serialization

### Integration Tests (`tests/test_integration.py`)
- **Chip Conservation:** Run 100+ hands, verify no leaks
- **Pot Distribution:** Test all side pot scenarios
- **Split Pots:** Verify correct splitting with remainders
- **Complex All-Ins:** Multi-way all-ins with different stacks

## Design Patterns

### 1. Strategy Pattern
Players implement the `Player` interface, allowing different bot strategies to be swapped.

### 2. Facade Pattern
`Table` provides a simple interface (`simulate_hand()`) that orchestrates complex subsystems.

### 3. Data Transfer Object (DTO)
`PublicGamestate` packages public information for transfer to bots.

### 4. Validator Pattern
`PlayerJudge` validates and corrects bot actions before execution.

### 5. Judge Pattern
`HandJudge` provides objective evaluation without bias.

## Performance Considerations

**Optimizations:**
- Minimal copying (only when creating PublicGamestate)
- No external dependencies (pure Python)
- Efficient hand evaluation (7-card combinations)

**Scalability:**
- Supports 2-10 players (typical poker table)
- Can simulate thousands of hands quickly
- Deterministic mode (seeded) for reproducible benchmarks

## Extension Points

### Adding New Bot Types:
1. Extend `Player` class
2. Implement `get_action()` method
3. Use `gamestate` and `hole_cards` to make decisions
4. Return valid action tuple

### Adding New Features:
- **Antes:** Modify `collect_blinds()` to collect antes
- **Different Poker Variants:** Extend `HandJudge` with new hand rankings
- **Tournament Payouts:** Add payout structure to Table
- **Hand Logging:** Extend `current_hand_history` tracking
- **Real-time Visualization:** Hook into betting round callbacks

## File Structure

```
src/
├── core/                      # Game engine
│   ├── player.py             # Bot interface
│   ├── table.py              # Game orchestrator
│   ├── gamestate.py          # Public state
│   ├── data_classes.py       # Core data structures
│   └── deck_manager.py       # Card management
├── helpers/                   # Utilities
│   ├── hand_judge.py         # Hand evaluation
│   └── player_judge.py       # Action validation
└── bots/                      # Example implementations
    ├── random_bot.py         # Random strategy
    ├── call_bot.py           # Calling station
    └── exploiter_bot.py      # Anti-calling-station
```

## Key Invariants

1. **Chip Conservation:** Total chips constant throughout game
2. **Information Hiding:** Bots never see private information
3. **Action Validity:** Invalid actions automatically corrected
4. **Pot Eligibility:** Players only eligible for pots they contributed to
5. **Button Advancement:** Button always advances to next non-busted player
6. **Blind Posting:** Blinds always posted before hand starts

## Summary

This architecture provides:
- **Clean separation** between game logic and bot strategy
- **Information security** preventing data leakage
- **Correctness guarantees** through validation and testing
- **Extensibility** via simple bot interface
- **Production quality** with comprehensive test coverage

The design enables rapid bot development while ensuring fair and correct gameplay.
