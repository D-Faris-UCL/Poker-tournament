# Poker Tournament Environment - Architecture Document

## System Overview

This is a complete poker tournament environment designed for AI bot competitions. The architecture follows a clean separation between game logic, player bots, and helper utilities.

## Component Hierarchy

```
Tournament
    └── Table (Game Orchestrator)
        ├── Players (Bot implementations)
        ├── DeckManager (Card management)
        ├── PublicGamestate (Visible information)
        ├── PlayerJudge (Action validation)
        └── HandJudge (Hand evaluation & pot distribution)
```

## Core Components

### 1. Table ([src/core/table.py](src/core/table.py))

**Purpose**: Main game orchestrator that manages all game state and coordinates between components.

**Key Responsibilities**:
- Manage tournament rounds and blinds schedule
- Track player stacks and game state
- Deal cards through DeckManager
- Collect bets and manage pots
- Track hand history
- Generate PublicGamestate for players

**Key Methods**:
- `get_public_gamestate()`: Create safe view for players
- `reset_hand_state()`: Prepare for new hand
- `deal_hole_cards()`: Deal cards to players
- `deal_flop/turn/river()`: Deal community cards
- `collect_blinds()`: Post small and big blinds
- `advance_button()`: Move dealer button

**State Management**:
```python
- round_number: Current tournament round
- players: List of Player objects
- player_hole_cards: Hidden hole cards (List[Tuple[str, str]])
- player_public_infos: Public player information
- button_position: Dealer button index
- community_cards: Board cards
- total_pot: Current pot size
- side_pots: Side pots for all-in situations
- blinds: Current (SB, BB) tuple
- blinds_schedule: Mapping of round -> blinds
- current_hand_history: Actions by street
- previous_hand_histories: Historical hand data
```

### 2. PublicGamestate ([src/core/gamestate.py](src/core/gamestate.py))

**Purpose**: Sanitized view of game state given to players to prevent information leakage.

**Security Design**:
- Contains ONLY information visible at a real poker table
- No access to other players' hole cards
- No access to remaining deck cards
- Immutable snapshot of current game state

**Available Information**:
- Round number and blinds
- All players' public information (stacks, bets, active status)
- Community cards
- Pot sizes
- Hand history (all past actions)
- Minimum raise amount

**Utility Methods**:
- `get_active_players_count()`: Count active players
- `get_current_street()`: Determine current betting round
- `get_current_bet()`: Get amount to call
- `copy()`: Deep copy for safety

### 3. Player ([src/core/player.py](src/core/player.py))

**Purpose**: Abstract base class for all bot implementations.

**Interface**:
```python
def make_decision(
    self,
    public_gamestate: PublicGamestate,
    hole_cards: Tuple[str, str]
) -> Tuple[str, int]:
    """
    Args:
        public_gamestate: Current visible game state
        hole_cards: This player's two hole cards

    Returns:
        (action_type, amount) where:
        - action_type: 'fold', 'check', 'call', 'bet', 'raise'
        - amount: chips for bet/raise (0 for fold/check/call)
    """
```

**Bot Implementation Requirements**:
1. Inherit from Player class
2. Implement make_decision() method
3. Return valid action tuple
4. Handle all game states gracefully
5. Stay within resource limits (enforced externally)

### 4. DeckManager ([src/core/deck_manager.py](src/core/deck_manager.py))

**Purpose**: Manages 52-card deck with shuffling and dealing.

**Card Representation**:
- Format: `<rank><suit>` (e.g., 'Ah' = Ace of hearts)
- Ranks: 2-9, T(10), J, Q, K, A
- Suits: h(hearts), d(diamonds), c(clubs), s(spades)

**Key Methods**:
- `reset_deck()`: Reset to full 52 cards
- `shuffle_deck(seed)`: Shuffle with optional seed for reproducibility
- `deal_card()`: Deal one card
- `burn_card()`: Burn a card (not dealt to players)
- `deal_multiple(n)`: Deal n cards at once

**Features**:
- Deterministic shuffling with seed support
- Tracks remaining and burned cards
- Raises errors on invalid operations

### 5. HandJudge ([src/helpers/hand_judge.py](src/helpers/hand_judge.py))

**Purpose**: Evaluates poker hands and determines winners.

**Hand Rankings** (lowest to highest):
1. High Card
2. One Pair
3. Two Pair
4. Three of a Kind
5. Straight
6. Flush
7. Full House
8. Four of a Kind
9. Straight Flush
10. Royal Flush

**Key Methods**:
- `evaluate_hand(hole_cards, community_cards)`: Evaluate best 5-card hand
- `compare_hands(hand1, hand2)`: Compare two hands (returns 1, 0, -1)
- `determine_winners(hole_cards, community, eligible)`: Find winner(s) from eligible players
- `distribute_pot(amount, winners, stacks)`: Split pot among winners

**Algorithm**:
- Evaluates best 5-card combination from 7 cards
- Returns hand type and kickers for tiebreaking
- Handles all edge cases (wheel straight, flush tiebreakers, etc.)

### 6. PlayerJudge ([src/helpers/player_judge.py](src/helpers/player_judge.py))

**Purpose**: Validates player actions and ensures legal play.

**Validation Rules**:
- Invalid action types → fold or check
- Bets/raises below minimum → check or call
- Bets/raises above stack → all-in
- Fold when check available → check (anti-mistake)

**Key Methods**:
- `get_legal_actions()`: Get all legal actions for player
- `validate_action()`: Validate and correct player action
- `is_betting_complete()`: Check if betting round is done
- `get_next_actor()`: Find next player to act

**Design Philosophy**:
- Graceful error handling (no game crashes from bad bots)
- Conservative corrections (protect players from mistakes)
- Clear action semantics

## Data Classes ([src/core/data_classes.py](src/core/data_classes.py))

### SidePot
```python
@dataclass
class SidePot:
    amount: int
    eligible_players: List[int]
```

### PlayerPublicInfo
```python
@dataclass
class PlayerPublicInfo:
    stack: int           # Current chips
    current_bet: int     # Bet this round
    active: bool         # In current hand
    busted: bool         # Eliminated from tournament
```

### Action
```python
@dataclass
class Action:
    player_index: int
    action_type: str    # 'fold', 'check', 'call', 'bet', 'raise', 'all-in'
    amount: int

    # Serialization methods for logging/replay
    def to_dict() -> dict
    def from_dict(data: dict) -> Action
```

## Information Flow

```
1. Table creates hand
   └── Shuffle deck
   └── Deal hole cards
   └── Post blinds

2. For each betting round:
   └── Table generates PublicGamestate
   └── Table calls Player.make_decision(gamestate, hole_cards)
   └── PlayerJudge validates action
   └── Table updates game state
   └── Repeat until betting complete

3. At showdown:
   └── HandJudge evaluates all hands
   └── HandJudge determines winners
   └── HandJudge distributes pots

4. Next hand:
   └── Update stacks
   └── Check for busted players
   └── Advance button
   └── Repeat from step 1
```

## Security Model

### Data Isolation
- Players receive **only** PublicGamestate
- No access to Table's internal state
- No access to other players' hole cards
- No access to deck state

### Action Validation
- All actions validated by PlayerJudge
- Invalid actions auto-corrected
- No way to cheat through invalid actions

### External Resource Control (TODO)
- CPU time limits per decision
- Memory limits per bot
- Process isolation
- Sandboxed execution

## Extensibility Points

### Custom Bots
Inherit from `Player` and implement strategy:
```python
class MyBot(Player):
    def make_decision(self, gamestate, hole_cards):
        # Your strategy here
        return (action, amount)
```

### Tournament Variations
- Modify blinds schedule
- Add antes
- Change starting stacks
- Implement knockout bounties
- Add rebuys/add-ons

### Logging & Analysis
- Hook into hand history
- Track player statistics
- Replay hands
- Generate visualizations

## Testing Strategy

### Unit Tests ([tests/test_components.py](tests/test_components.py))
- DeckManager: Shuffle, deal, burn
- HandJudge: Hand evaluation, comparison
- PlayerJudge: Action validation
- Data classes: Serialization

### Integration Tests (TODO)
- Full hand simulation
- Multi-round tournaments
- Edge cases (all-ins, side pots)

### Bot Tests (TODO)
- Bot decision making
- Resource usage
- Error handling

## Next Steps for Full Implementation

1. **Game Engine**
   - Betting round loop
   - Street progression
   - Showdown logic
   - Pot distribution with side pots

2. **Tournament Manager**
   - Multi-table support
   - Player elimination
   - Prize structure
   - Statistics tracking

3. **Resource Monitor**
   - CPU time limits
   - Memory limits
   - Process sandboxing

4. **Visualization**
   - Hand replayer
   - Live tournament view
   - Statistics dashboard

5. **Testing Suite**
   - Comprehensive unit tests
   - Integration tests
   - Bot validation tests
   - Stress testing

## Design Principles

1. **Separation of Concerns**: Each component has a single, well-defined responsibility
2. **Security First**: No information leakage to bots
3. **Graceful Degradation**: Invalid actions corrected, not crashed
4. **Testability**: Each component independently testable
5. **Extensibility**: Easy to add new bots and features
6. **Reproducibility**: Seed support for deterministic testing
7. **Clean Interfaces**: Simple, well-documented APIs

## File Structure Summary

```
src/
├── core/
│   ├── table.py           - Main game orchestrator
│   ├── gamestate.py       - Public game state
│   ├── player.py          - Bot base class
│   ├── deck_manager.py    - Card management
│   └── data_classes.py    - Data structures
├── helpers/
│   ├── hand_judge.py      - Hand evaluation
│   └── player_judge.py    - Action validation
└── bots/
    ├── random_bot.py      - Random action bot
    └── call_bot.py        - Always-call bot

examples/
└── simple_game.py         - Basic usage example

tests/
└── test_components.py     - Unit tests
```

## Performance Considerations

- **Deck Operations**: O(1) for dealing
- **Hand Evaluation**: O(1) for 7-card evaluation
- **Action Validation**: O(1) per action
- **Winner Determination**: O(n) where n = active players

## License & Usage

Designed for educational use in university AI competitions.
Students encouraged to:
- Build creative bot strategies
- Contribute improvements
- Share ideas and approaches
- Learn game theory and AI concepts
