# AI Poker Bot Tournament

A No-Limit Texas Hold'em tournament simulator designed for AI bot development and competitive play. Built for university AI competitions with automatic action validation, side pot calculation, and sandboxed bot execution.

## Table of Contents

- [Features](#features)
- [Quickstart](#quickstart)
- [Bot Development Guide](#bot-development-guide)
  - [Directory Structure](#directory-structure)
  - [Player Interface](#player-interface)
  - [Understanding the Game State](#understanding-the-game-state)
  - [Betting History](#betting-history)
  - [Showdown Details](#showdown-details)
- [Testing Your Bot](#testing-your-bot)
- [Helper Utilities](#helper-utilities)
- [Competition Guidelines](#competition-guidelines)
- [Example Bots](#example-bots)
- [Important Notes](#important-notes)

## Features

- **Complete Texas Hold'em Implementation**: All hand rankings, betting rounds, and game mechanics
- **Automatic Side Pot Calculation**: Complex all-in scenarios handled automatically
- **Action Validation**: Invalid moves are automatically corrected (logged for debugging)
- **Sandboxed Execution**: Each bot runs in an isolated process with strict resource limits
- **Information Security**: Bots only receive publicly visible information
- **Blind Schedule Support**: Configurable blind increases throughout the tournament
- **Deterministic Mode**: Reproducible games for testing and debugging
- **ML-Ready**: Support for PyTorch, TensorFlow, scikit-learn, and other popular ML libraries

## Quickstart

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd poker-tournament

# Install dependencies (only psutil for sandboxing)
pip install psutil==7.2.2
```

### Run a Simple Game

```bash
# Run the example game with existing bots
python examples/simple_game.py

# Run component tests
python tests/test_components.py
```

## Bot Development Guide

### Directory Structure

Each bot **must** be in its own directory under `src/bots/`:

```
src/bots/
├── your_bot_name/
│   ├── player.py          # Required: Contains your bot class
│   └── [other files...]   # Optional: Helper modules, data files, etc.
```

**Important**: The main bot class must be in `player.py`. You can include additional Python files or data files in your bot's folder.

### Player Interface

All bots must inherit from `Player` and implement the `get_action` method:

```python
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from typing import Tuple

class YourBot(Player):
    """Your bot description"""

    def __init__(self, player_index: int):
        super().__init__(player_index)
        # Your initialization here (optional)
        # You can initialize strategies, load data, etc.

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """
        Make a poker decision based on current game state.

        Args:
            gamestate: Current public game state (see below for details)
            hole_cards: Your two hole cards, e.g., ('Ah', 'Kd')

        Returns:
            Tuple of (action_type, amount) where:
                - action_type: 'fold', 'check', 'call', 'raise', or 'all-in'
                - amount: Chips for raise (0 for fold/check/call)

        Example returns:
            ('fold', 0)           # Fold your hand
            ('check', 0)          # Check (when no one has raised)
            ('call', 0)           # Call the current raise
            ('raise', 100)        # Raise by 100 chips
            ('all-in', 0)         # Go all-in with your stack
        """
        # Your strategy here
        return ('call', 0)
```

**Card Notation:**
- Ranks: `2-9`, `T` (ten), `J`, `Q`, `K`, `A`
- Suits: `h` (hearts), `d` (diamonds), `c` (clubs), `s` (spades)
- Example: `'Ah'` = Ace of hearts, `'Ts'` = Ten of spades

### Understanding the Game State

The `PublicGamestate` object contains all publicly visible information:

```python
def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]):
    # Access your player's information
    my_info = gamestate.player_public_infos[self.player_index]

    # Key game state attributes:
    gamestate.round_number              # Current tournament round
    gamestate.button_position           # Dealer button index
    gamestate.community_cards           # List of community cards (0-5 cards)
    gamestate.total_pot                 # Total chips in all pots at the start of the betting round
    gamestate.pots                      # List of Pot objects (main pot + side pots)
    gamestate.blinds                    # Current (small_blind, big_blind)
    gamestate.blinds_schedule           # Full blind schedule
    gamestate.minimum_raise_amount      # Minimum valid raise amount

    # Useful helper methods:
    current_bet = gamestate.get_bet_to_call()           # Current amount to call
    street = gamestate.get_current_street()             # 'preflop', 'flop', 'turn', 'river'
    active_count = gamestate.get_active_players_count() # Number of active players
    alive_count = gamestate.get_non_busted_players_count() # Non-eliminated players
```

#### PlayerPublicInfo

Each player's public information is available in `gamestate.player_public_infos`:

```python
# Access any player's public info
player_info = gamestate.player_public_infos[player_index]

# Available attributes:
player_info.stack           # Current chip stack
player_info.current_bet     # Amount committed in current betting round
player_info.active          # True if still in the hand (not folded)
player_info.busted          # True if eliminated from tournament
player_info.is_all_in       # True if player is all-in
```

**Example - Check if you can afford to call:**

```python
my_info = gamestate.player_public_infos[self.player_index]
bet_to_call = gamestate.get_bet_to_call()
amount_to_call = bet_to_call - my_info.current_bet

if my_info.stack >= amount_to_call:
    return ('call', 0)
else:
    return ('fold', 0)
```

#### Pot Structure

The `pots` list contains the main pot and any side pots:

```python
for i, pot in enumerate(gamestate.pots):
    print(f"Pot {i}: {pot.amount} chips")
    print(f"Eligible players: {pot.eligible_players}")

# pot.amount           -> Total chips in this pot
# pot.eligible_players -> List of player indices eligible to win
```

### Betting History

The gamestate tracks betting history in two ways:

#### 1. Current Hand History

`gamestate.current_hand_history` is a dictionary mapping street names to `StreetHistory` objects:

```python
# Access current hand's betting history
current_hand = gamestate.current_hand_history

# Available streets: 'preflop', 'flop', 'turn', 'river'
if 'preflop' in current_hand:
    preflop = current_hand['preflop']
    print(f"Community cards: {preflop.community_cards}")  # [] for preflop

    for action in preflop.actions:
        print(f"Player {action.player_index}: {action.action_type} {action.amount}")
        # action.player_index -> Who made the action
        # action.action_type  -> 'fold', 'check', 'call', 'raise', 'all-in',
        #                        'small_blind', 'big_blind'
        # action.amount       -> Chips involved (0 for fold/check)
```

**Example - Analyze opponent aggression:**

```python
def count_raises(self, gamestate, opponent_idx):
    """Count how many times an opponent has raised"""
    raises = 0
    for street_name, street_history in gamestate.current_hand_history.items():
        for action in street_history.actions:
            if action.player_index == opponent_idx and action.action_type == 'raise':
                raises += 1
    return raises
```

#### 2. Previous Hand Histories

`gamestate.previous_hand_histories` is a list of `HandRecord` objects from previous hands:

```python
# Access previous hands
for hand_record in gamestate.previous_hand_histories:
    # hand_record.per_street -> Dict[str, StreetHistory] (same as current_hand_history)
    # hand_record.showdown_details -> Optional dict with showdown info

    if hand_record.showdown_details:
        details = hand_record.showdown_details
        # details['players']    -> List of player indices at showdown
        # details['hands']      -> Dict mapping player_idx to hand name
        # details['hole_cards'] -> Dict mapping player_idx to (card1, card2)
```

### Showdown Details

**Important**: In this tournament, **ALL active players** at showdown reveal their hole cards (not just winners). This information is available in the showdown details.

```python
# Access previous showdowns to learn opponent tendencies
for hand_record in gamestate.previous_hand_histories:
    if hand_record.showdown_details:
        details = hand_record.showdown_details

        for player_idx in details['players']:
            hole_cards = details['hole_cards'][player_idx]    # e.g., ('Ah', 'Kd')
            hand_name = details['hands'][player_idx]          # e.g., 'one_pair'

            print(f"Player {player_idx} showed {hole_cards} ({hand_name})")
```

**Hand names** (returned by hand evaluator):
- `'high_card'`
- `'one_pair'`
- `'two_pair'`
- `'three_of_a_kind'`
- `'straight'`
- `'flush'`
- `'full_house'`
- `'four_of_a_kind'`
- `'straight_flush'`
- `'royal_flush'`

### Complete Example: Building a Simple Bot

Let's build a complete bot with a simple, easy-to-understand strategy. This "SimpleBot" will give you a working starting point:

**Strategy:**
- **Preflop**: Only play strong hands (pairs 9+, AK, AQ) - fold everything else
- **Postflop**:
  - Raise full pot with three of a kind or better
  - Check/call with pairs or two pair
  - Fold with nothing
- **Safety rules**: Only raise once per betting round, check for all-ins

```python
from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from src.helpers.hand_judge import HandJudge

class SimpleBot(Player):
    """A bare-bones bot that plays safe, basic poker."""

    def __init__(self, player_index: int):
        super().__init__(player_index)
        # Track raises to avoid raising wars
        self.raised_this_street = {}

    def get_action(
        self, 
        gamestate: PublicGamestate, 
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        
        my_info = gamestate.player_public_infos[self.player_index]
        amount_to_call = gamestate.get_bet_to_call() - my_info.current_bet
        current_street = gamestate.get_current_street()

        # Reset raise tracker for new streets
        if current_street not in self.raised_this_street:
            self.raised_this_street[current_street] = False

        # 1. PREFLOP STRATEGY
        if current_street == 'preflop':
            card1, card2 = hole_cards[0][0], hole_cards[1][0]
            high_cards = ['A', 'K', 'Q', 'J', 'T']
            
            # Play pairs or high cards, fold everything else
            if card1 == card2 or card1 in high_cards or card2 in high_cards:
                return ('call', 0) if amount_to_call > 0 else ('check', 0)
            return ('fold', 0) if amount_to_call > 0 else ('check', 0)

        # 2. POSTFLOP STRATEGY
        hand_name, _ = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
        strong_hands = ['three_of_a_kind', 'straight', 'flush', 'full_house', 
                        'four_of_a_kind', 'straight_flush', 'royal_flush']

        # Strong hands: Raise (once per street)
        if hand_name in strong_hands:
            if not self.raised_this_street[current_street]:
                self.raised_this_street[current_street] = True
                amt = gamestate.total_pot # Raise potsize
                amt = max(amt, gamestate.minimum_raise_amount)
                if my_info.current_bet + amt > my_info.stack:
                    return ('all-in', 0)
                else:
                    return ('raise', amt)

            # If we already raised this street, just call to avoid a war
            return ('call', 0)

        # Medium hands: Just check or call
        if hand_name in ['one_pair', 'two_pair']:
            return ('call', 0) if amount_to_call > 0 else ('check', 0)

        # Weak hands: Fold to any raise
        return ('fold', 0) if amount_to_call > 0 else ('check', 0)
```

**How this bot works:**

1. **Preflop decisions**: Only continues with pocket pairs 9+ or Ace with King/Queen. This is very tight, but safe.

2. **Postflop decisions**: Uses `HandJudge.evaluate_hand()` to categorize hand strength:
   - **Strong** (trips+): Raise pot size
   - **Medium** (pairs, two pair): Just check/call
   - **Weak** (high card): Fold to raises, check otherwise

3. **Safety features**:
   - **One raise per street**: Tracks raises with `raised_this_street` dictionary to avoid raising wars
   - **Stack protection**: Ensures we never try to raise more than our stack

**Try modifying this bot:**
- Add more starting hands (suited connectors, lower pairs)
- Add more raise sizing depending on hand strength and board texture
- Track opponent behavior and adjust strategy
- Use pot odds to make better call/fold decisions

## Testing Your Bot

Use the provided `examples/simple_game.py` to test your bot:

```python
from src.core.table import Table
from src.helpers.player_loader import load_players

# Load all bots from src/bots/
player_classes = load_players('src/bots')
bots = [player_class(i) for i, player_class in enumerate(player_classes)]

# Define blind schedule
blinds_schedule = {
    1: (10, 20),      # Round 1: 10/20 blinds
    50: (20, 50),     # Round 50: 20/50 blinds
    100: (50, 100)    # Round 100: 50/100 blinds
}

# Create table
table = Table(
    players=bots,
    starting_stack=2000,
    blinds_schedule=blinds_schedule,
)

# Simulate hands
for hand_num in range(1, 150):
    result = table.simulate_hand()

    # Check for eliminations
    if result['eliminated']:
        print(f"Players eliminated: {result['eliminated']}")

    # Check if only one player remains
    remaining = sum(1 for p in table.get_public_gamestate().player_public_infos if not p.busted)
    if remaining == 1:
        break

# Print final stacks
print("Final stacks:")
for i, player_info in enumerate(table.get_public_gamestate().player_public_infos):
    print(f"Player {i}: {player_info.stack} chips")

# Clean up
for player in table.players:
    player.close()
```

## Helper Utilities

### PlayerJudge - Legal Actions

Check what actions are legal before making a decision:

```python
from src.helpers.player_judge import PlayerJudge

# Get legal actions
legal = PlayerJudge.get_legal_actions(
    player_idx=self.player_index,
    player_infos=gamestate.player_public_infos,
    current_bet=gamestate.get_bet_to_call(),
    minimum_raise=gamestate.minimum_raise_amount
)

# Check what's legal:
if legal['check']:
    # Can check
    pass
if legal['call']:
    # Can call (amount_to_call = legal['call_amount'])
    pass
if legal['raise']:
    # Can raise (min: legal['min_raise'], max: legal['max_raise'])
    # legal['min_raise'] - Minimum raise to amount
    # legal['max_raise'] - Maximum raise to amount (Your stack for All-in)
    pass
```

### HandJudge - Evaluate Hand Strength

Evaluate your hand strength at any point:

```python
from src.helpers.hand_judge import HandJudge

# Works with ANY number of cards (2-7 cards)
hand_name, hand_values = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)

# hand_name: String like 'one_pair', 'flush', etc.
# hand_values: List of card values for tie-breaking [14, 13, ...] (Ace high = 14)

# Example usage:
if gamestate.get_current_street() == 'preflop':
    # Evaluate just your hole cards
    hand_name, values = HandJudge.evaluate_hand(hole_cards, [])
    print(f"Preflop hand: {hand_name}")

elif gamestate.get_current_street() == 'flop':
    # Evaluate with 5 cards (2 hole + 3 community)
    hand_name, values = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
    print(f"Current hand: {hand_name}")
```

## Competition Guidelines

### Submission Requirements

1. **Directory Structure**: Submit a folder named `your_bot_name` containing:
   - `player.py` - **Required**: Contains your bot class that extends `Player`
   - Additional Python files (optional)
   - Data files (optional)

2. **Class Requirements**:
   - Must inherit from `src.core.player.Player`
   - Must implement `get_action(gamestate, hole_cards)` method
   - Must call `super().__init__(player_index)` in `__init__`

3. **Resource Limits**:
   - **Time limit**: 1 second per decision
   - **Memory limit**: 500MB RAM
   - Exceeding limits results in automatic fold

4. **Allowed Libraries**:
   - **Python standard library** - All built-in modules
   - **Machine Learning**: PyTorch, TensorFlow/Keras, scikit-learn
   - **Scientific Computing**: NumPy, SciPy, Pandas
   - **Performance**: Numba, CuPy
   - **Your own modules** - Include any additional files in your bot folder

5. **Allowed Operations**:
   - Store state between hands (in memory or files within your bot directory)
   - Load pre-trained models or data files
   - Perform computations using the allowed libraries
   - Import your own helper modules from your bot folder

6. **Prohibited**:
   - Accessing other bots' files or code
   - Network requests
   - System calls that could interfere with the tournament
   - Attempting to access hidden game information

### Tournament Format

- Multiple bots compete in a single tournament
- Starting stack: TBD by organizer
- Blind schedule: TBD by organizer
- Last bot standing wins

### How Invalid Actions Are Handled

**Don't worry about making illegal moves** - they are automatically corrected:

- Invalid action types default to check (if possible) or fold
- Raise below minimum becomes check/call
- Raise exceeds stack becomes all-in
- All corrections are logged to `illegal_moves.log` for debugging

This ensures the game never crashes due to bot errors.

## Performance Mode: Unrestricted Execution

By default, the tournament runs in **restricted mode** (`restricted=True`) where all bots are sandboxed for safety and fairness. However, for certain use cases like training or simulation, you can enable **unrestricted mode** for significant performance improvements.

### Restricted Mode (Default)

When `restricted=True` (the default), bots run with the following safety measures:

- **Time limit**: 1 second per decision (configurable)
- **Memory limit**: 500MB RAM (configurable)
- **Crash protection**: Exceptions are caught and converted to folds
- **Isolated gamestate**: Each bot receives a deep copy of the gamestate (preventing accidental or malicious modifications)
- **Sandboxed execution**: Bots run in separate processes with resource monitoring

This mode ensures fair play and protects against:
- Bots that run too slowly or get stuck
- Memory leaks or excessive RAM usage
- Crashes that would disrupt the tournament
- Cheating by modifying the gamestate

### Unrestricted Mode

When `restricted=False`, sandboxing is completely disabled:

- **No time limit**: Bots can take as long as they need
- **No memory limit**: Bots can use as much RAM as available
- **No crash protection**: Exceptions will crash the game
- **Real gamestate**: Bots receive the actual gamestate object (not a copy)

**Performance improvement**: Unrestricted mode runs approximately **1320% faster** than restricted mode.

### When to Use Unrestricted Mode

Unrestricted mode is ideal for:

- **Monte Carlo simulations**: Running thousands of games quickly for statistical analysis
- **Reinforcement Learning**: Training bots that need to play millions of hands
- **Development**: Testing your own bot when you trust it won't cheat or crash
- **Benchmarking**: Measuring bot performance without sandboxing overhead

**Important**: Unrestricted mode assumes the bot is **honest and well-behaved**. It provides no protection against:
- Bots that modify the gamestate to cheat
- Infinite loops or excessive memory usage
- Crashes that terminate the entire tournament

### Example Usage

```python
from src.core.table import Table
from src.helpers.player_loader import load_players

# Load players
player_classes = load_players('src/bots')
bots = [player_class(i) for i, player_class in enumerate(player_classes)]

# Restricted mode (default - safe for competitions)
table_safe = Table(
    players=bots,
    starting_stack=2000,
    blinds_schedule=blinds_schedule,
    restricted=True  # Sandboxed execution (default)
)

# Unrestricted mode (fast - for training/simulation)
table_fast = Table(
    players=bots,
    starting_stack=2000,
    blinds_schedule=blinds_schedule,
    restricted=False  # No sandboxing, 1320% faster!
)

# Run simulation
for hand_num in range(1000):
    result = table_fast.simulate_hand()
    # Process results...
```

### Security Warning

Only use `restricted=False` with bots you trust. In unrestricted mode:
- Bots can access and modify the real gamestate object
- There's no protection against resource abuse
- One misbehaving bot can crash the entire simulation

For competitions or when running untrusted code, always use `restricted=True`.

## Example Bots

Three example bots are provided in `src/bots/`:

### 1. CallBot - Passive Baseline
[src/bots/call_bot/player.py](src/bots/call_bot/player.py)

Simple bot that always calls or checks (never folds, never raises). Good baseline for testing.

```python
def get_action(self, gamestate, hole_cards):
    player_info = gamestate.player_public_infos[self.player_index]
    bet_to_call = gamestate.get_bet_to_call()
    amount_to_call = bet_to_call - player_info.current_bet

    if amount_to_call == 0:
        return ('check', 0)
    else:
        return ('call', 0)
```

### 2. RandomBot - Random Legal Actions
[src/bots/random_bot/player.py](src/bots/random_bot/player.py)

Makes random legal decisions. Uses `PlayerJudge.get_legal_actions()` to find valid actions, then randomly selects one.

### 3. ExploiterBot - Strategic Bot
[src/bots/exploiter_bot/player.py](src/bots/exploiter_bot/player.py)

More sophisticated bot designed to exploit weak opponents. Features:
- Tight preflop hand selection
- Position-aware play
- Hand strength evaluation
- Pot-sized value raises

Study this bot to understand advanced concepts like hand evaluation and strategic play.

## Important Notes

### Resource Limits

Each bot runs in a **sandboxed process** with strict limits:
- **1 second** per decision (default, configurable)
- **500MB RAM** (default, configurable)
- Violations result in automatic fold and process restart

### Debugging Tips

1. **Invalid moves**: Check `illegal_moves.log` for action corrections
2. **Bot crashes**: Exceptions are caught and converted to folds
3. **Slow decisions**: If your bot times out, optimize your logic
4. **Print statements**: Use logging or file writes (prints go to separate process)

### State Persistence

You can store state between hands:

```python
class MyBot(Player):
    def __init__(self, player_index: int):
        super().__init__(player_index)
        self.opponent_stats = {}  # Persists across hands

    def get_action(self, gamestate, hole_cards):
        # Update opponent stats based on gamestate.previous_hand_histories
        # Make decisions based on accumulated stats
        pass
```

### Deterministic Testing

For reproducible testing, pass a `seed` parameter:

```python
table = Table(
    players=bots,
    starting_stack=1000,
    blinds_schedule=blinds_schedule,
    seed=42  # Same seed = same card order
)
```

## Questions?

For questions about the tournament or technical issues, contact the tournament organizers.

Good luck and may the best bot win!
