# Poker Tournament AI Bot Competition

A complete poker tournament environment for hosting AI bot competitions at your university.

## Architecture Overview

The system consists of several key components:

### Core Objects

- **[Table](src/core/table.py)**: Main orchestrator that hosts players and manages the game
- **[PublicGamestate](src/core/gamestate.py)**: Visible information given to players (prevents cheating)
- **[Player](src/core/player.py)**: Abstract base class for bot implementations
- **[DeckManager](src/core/deck_manager.py)**: Manages card dealing and shuffling
- **[Data Classes](src/core/data_classes.py)**: SidePot, PlayerPublicInfo, Action

### Helper Objects

- **[HandJudge](src/helpers/hand_judge.py)**: Evaluates poker hands and determines winners
- **[PlayerJudge](src/helpers/player_judge.py)**: Validates actions and ensures legal play

### Example Bots

- **[RandomBot](src/bots/random_bot.py)**: Makes random legal actions
- **[CallBot](src/bots/call_bot.py)**: Always calls or checks (passive player)

## Project Structure

```
poker-tournament/
├── src/
│   ├── core/              # Core game objects
│   │   ├── table.py
│   │   ├── gamestate.py
│   │   ├── player.py
│   │   ├── deck_manager.py
│   │   └── data_classes.py
│   ├── helpers/           # Helper utilities
│   │   ├── hand_judge.py
│   │   └── player_judge.py
│   └── bots/              # Bot implementations
│       ├── random_bot.py
│       └── call_bot.py
├── examples/              # Example usage
├── tests/                 # Unit tests
└── README.md
```

## Getting Started

### Installation

```bash
# No external dependencies required - uses Python standard library only!
python --version  # Requires Python 3.7+
```

### Creating Your Bot

Create a new bot by inheriting from the `Player` class:

```python
from src.core.player import Player
from src.core.gamestate import PublicGamestate
from typing import Tuple

class MyBot(Player):
    def make_decision(
        self,
        public_gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        # Your bot logic here
        # Return (action_type, amount)
        # action_type: 'fold', 'check', 'call', 'bet', 'raise'
        # amount: bet/raise amount (0 for fold/check/call)

        return ('call', 0)
```

### Game State Information

Your bot receives a `PublicGamestate` object with:

- `round_number`: Current tournament round
- `player_public_infos`: List of player info (stack, current_bet, active, busted)
- `button_position`: Dealer button position
- `community_cards`: Visible community cards
- `total_pot`: Total chips in pot
- `side_pots`: Side pots information
- `blinds`: Current (small_blind, big_blind)
- `minimum_raise_amount`: Minimum valid raise
- `current_hand_history`: Actions taken this hand
- `previous_hand_histories`: Previous hands' histories

### Card Representation

- Cards: `'Ah'` = Ace of hearts, `'Kd'` = King of diamonds, etc.
- Ranks: `'2'` through `'9'`, `'T'` (10), `'J'`, `'Q'`, `'K'`, `'A'`
- Suits: `'h'` (hearts), `'d'` (diamonds), `'c'` (clubs), `'s'` (spades)

### Action Validation

The `PlayerJudge` automatically validates and corrects invalid actions:

- Invalid action types default to fold or check
- Bets/raises below minimum are converted to check/call
- Bets/raises above stack are converted to all-in
- Folding when check is available is converted to check

## Tournament Configuration

### Blinds Schedule

Define increasing blinds by round:

```python
blinds_schedule = {
    1: (10, 20),      # Rounds 1-9: 10/20
    10: (25, 50),     # Rounds 10-19: 25/50
    20: (50, 100),    # Rounds 20-29: 50/100
    30: (100, 200),   # Rounds 30+: 100/200
}
```

### Starting Configuration

```python
from src.core.table import Table

table = Table(
    players=[bot1, bot2, bot3, bot4],
    starting_stack=1000,
    blinds_schedule=blinds_schedule,
    max_rounds=100,
    seed=42  # For reproducibility
)
```

## Resource Management

External utilities should be used to:

- **CPU Time Limits**: Enforce time limits per decision (e.g., 1 second)
- **Memory Limits**: Restrict bot memory usage
- **Process Isolation**: Run bots in separate processes for security

## Development Roadmap

- [ ] Game engine integration (run full hands/tournaments)
- [ ] Tournament runner with statistics
- [ ] Visualization tools
- [ ] Resource monitoring utilities
- [ ] Test suite for validation
- [ ] Example advanced bots
- [ ] Tournament bracket system

## Competition Rules

1. Bots must inherit from `Player` class
2. Bots receive only `PublicGamestate` (no cheating)
3. Invalid actions are auto-corrected (penalties may apply)
4. Time/memory limits enforced externally
5. No external communication allowed

## Contributing

Students can contribute:

- New bot strategies
- Test cases
- Documentation improvements
- Performance optimizations
- Visualization tools

## License

Designed for educational use at [Your University Name]
