# Poker Tournament Framework

A comprehensive No-Limit Texas Hold'em tournament simulator designed for AI bot development and competitive play. Perfect for university poker competitions, research projects, and learning poker strategy through programming.

## Features

- Complete Texas Hold'em implementation with all hand rankings
- Automatic side pot calculation for complex all-in scenarios
- Information security (bots only see public information)
- Action validation (invalid moves automatically corrected)
- Blind schedule support with automatic level increases
- Deterministic mode for reproducible games
- Zero external dependencies (pure Python)
- Comprehensive test suite ensuring correctness

## Quick Start

### Installation

No dependencies required! Just clone and run:

```bash
git clone <repository-url>
cd "Poker tournament"
```

### Run Your First Game

```python
from src.core.table import Table
from src.bots.exploiter_bot import ExploiterBot
from src.bots.call_bot import CallBot

# Create 4 players
players = [
    ExploiterBot(0),
    CallBot(1),
    ExploiterBot(2),
    CallBot(3)
]

# Define blind schedule
blinds_schedule = {
    1: (10, 20),      # Rounds 1-49: 10/20 blinds
    50: (25, 50),     # Rounds 50+: 25/50 blinds
}

# Create table
table = Table(
    players=players,
    starting_stack=2000,
    blinds_schedule=blinds_schedule,
    seed=42  # For reproducibility
)

# Run tournament until one winner
hand_num = 1
while sum(1 for p in table.player_public_infos if not p.busted) > 1:
    result = table.simulate_hand()
    print(f"Hand {hand_num}: {result}")
    hand_num += 1

# Find winner
winner_idx = [i for i, p in enumerate(table.player_public_infos) if not p.busted][0]
print(f"\nWinner: Player {winner_idx}")
```

## Writing Your First Bot

### Step 1: Extend the Player Class

Create a new file `src/bots/my_bot.py`:

```python
from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate

class MyBot(Player):
    """My custom poker bot"""

    def get_action(
        self,
        gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """
        Decide what action to take.

        Args:
            gamestate: Current public game state
            hole_cards: Your two hole cards (e.g., ('Ah', 'Kd'))

        Returns:
            Tuple of (action_type, amount)
            - action_type: 'fold', 'check', 'call', 'bet', 'raise', 'all-in'
            - amount: Chip amount for the action (0 for fold/check)
        """
        # Your strategy here!
        pass
```

### Step 2: Understand the Gamestate

The `PublicGamestate` object contains everything you need to know:

```python
def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
    # Your position and stack
    my_position = self.player_index
    my_info = gamestate.player_public_infos[my_position]
    my_stack = my_info.stack
    my_current_bet = my_info.current_bet

    # Community cards and pot
    community_cards = gamestate.community_cards  # List of 0-5 cards
    total_pot = gamestate.total_pot

    # Current betting situation
    current_street = gamestate.get_current_street()  # 'preflop', 'flop', 'turn', 'river'
    bet_to_call = gamestate.get_bet_to_call()  # How much to call
    amount_to_call = bet_to_call - my_current_bet  # Additional chips needed

    # Other players
    for i, player_info in enumerate(gamestate.player_public_infos):
        if i == my_position:
            continue
        print(f"Player {i}: Stack={player_info.stack}, Bet={player_info.current_bet}, "
              f"Active={player_info.active}, All-in={player_info.is_all_in}")

    # Betting history (each street is a StreetHistory with .community_cards and .actions)
    preflop_street = gamestate.current_hand_history['preflop']
    preflop_actions = preflop_street.actions  # list of Action(player_index, action_type, amount)
    # preflop_street.community_cards is [] for preflop; flop/turn/river have the board at that street
```

### Step 3: Implement Simple Strategy

Here's a basic tight-aggressive bot:

```python
from typing import Tuple
from src.core.player import Player
from src.core.gamestate import PublicGamestate

class TightAggressiveBot(Player):
    """Plays only strong hands, bets aggressively when playing"""

    def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
        my_info = gamestate.player_public_infos[self.player_index]
        bet_to_call = gamestate.get_bet_to_call()
        amount_to_call = bet_to_call - my_info.current_bet
        street = gamestate.get_current_street()

        # Evaluate hand strength
        hand_strength = self._evaluate_preflop_hand(hole_cards)

        # Preflop strategy
        if street == 'preflop':
            if hand_strength >= 8:  # Premium hands (AA, KK, QQ, AK)
                # Raise 3x big blind
                raise_amount = gamestate.blinds[1] * 3
                if bet_to_call > 0:
                    # Someone already bet, re-raise
                    additional = raise_amount - my_info.current_bet
                    return ('raise', additional)
                else:
                    return ('bet', raise_amount)

            elif hand_strength >= 6:  # Strong hands (JJ, TT, AQ, AJs)
                if amount_to_call == 0:
                    return ('check', 0)
                elif amount_to_call <= gamestate.blinds[1] * 2:
                    return ('call', amount_to_call)
                else:
                    return ('fold', 0)

            else:  # Weak hands
                if amount_to_call == 0:
                    return ('check', 0)
                else:
                    return ('fold', 0)

        # Postflop: simplified strategy
        else:
            if amount_to_call == 0:
                # No bet to us, bet half pot with good preflop hand
                if hand_strength >= 7:
                    bet_size = gamestate.total_pot // 2
                    return ('bet', min(bet_size, my_info.stack))
                else:
                    return ('check', 0)
            else:
                # Someone bet, call if we had a good starting hand
                if hand_strength >= 7 and amount_to_call <= my_info.stack:
                    return ('call', amount_to_call)
                else:
                    return ('fold', 0)

    def _evaluate_preflop_hand(self, hole_cards: Tuple[str, str]) -> int:
        """Rate hand strength 0-10"""
        card1, card2 = hole_cards

        # Parse cards
        rank1, suit1 = card1[0], card1[1]
        rank2, suit2 = card2[0], card2[1]

        # Convert ranks to values
        rank_values = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
                       '8': 8, '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        val1 = rank_values[rank1]
        val2 = rank_values[rank2]
        high_card = max(val1, val2)
        low_card = min(val1, val2)
        is_pair = (val1 == val2)
        is_suited = (suit1 == suit2)

        # Premium pairs
        if is_pair and high_card >= 12:  # QQ, KK, AA
            return 10
        if is_pair and high_card >= 10:  # TT, JJ
            return 8

        # Premium non-pairs
        if high_card == 14 and low_card >= 12:  # AK, AQ
            return 9 if is_suited else 8
        if high_card == 14 and low_card >= 10:  # AJ, AT
            return 7 if is_suited else 6

        # Medium pairs
        if is_pair and high_card >= 7:  # 77-99
            return 6

        # Other broadway
        if high_card >= 11 and low_card >= 10:  # KQ, KJ, QJ, etc.
            return 6 if is_suited else 5

        # Weak pairs
        if is_pair:
            return 5

        # High card only
        if high_card >= 12:
            return 4

        # Trash
        return 2
```

### Step 4: Test Your Bot

```python
from src.core.table import Table
from src.bots.my_bot import TightAggressiveBot
from src.bots.call_bot import CallBot

# Pit your bot against calling stations
players = [TightAggressiveBot(i) for i in range(3)] + [CallBot(3)]

blinds_schedule = {1: (10, 20)}

table = Table(players, starting_stack=1000, blinds_schedule=blinds_schedule, seed=123)

# Run 50 hands
for hand in range(50):
    result = table.simulate_hand()
    print(f"Hand {hand+1}: Winners = {result['winners']}")

    # Check if someone won
    remaining = sum(1 for p in table.player_public_infos if not p.busted)
    if remaining == 1:
        break

# Print final stacks
for i, info in enumerate(table.player_public_infos):
    print(f"Player {i}: {info.stack} chips (Busted: {info.busted})")
```

## Understanding the Gamestate

### Card Notation

Cards are represented as 2-character strings:
- **Rank:** `2, 3, 4, 5, 6, 7, 8, 9, T, J, Q, K, A`
- **Suit:** `h` (hearts), `d` (diamonds), `c` (clubs), `s` (spades)

Examples: `'Ah'` (Ace of hearts), `'Ks'` (King of spades), `'2c'` (Two of clubs)

### PlayerPublicInfo

Information about each player:

```python
player_info = gamestate.player_public_infos[player_index]

player_info.stack          # Remaining chips
player_info.current_bet    # Amount bet on current street
player_info.active         # Still in current hand (hasn't folded)
player_info.busted         # Eliminated from tournament (0 chips)
player_info.is_all_in      # All chips committed
```

### Pot Structure

```python
# Total pot across all pots
total = gamestate.total_pot

# Individual pots (for side pot scenarios)
for pot in gamestate.pots:
    print(f"Pot amount: {pot.amount}")
    print(f"Eligible players: {pot.eligible_players}")  # List of player indices
```

### Betting History

```python
# Each street is a StreetHistory with .community_cards and .actions
preflop = gamestate.current_hand_history['preflop']
flop = gamestate.current_hand_history['flop']
turn = gamestate.current_hand_history['turn']
river = gamestate.current_hand_history['river']

# Iterate over actions; each action is an Action object
for action in preflop.actions:
    print(f"Player {action.player_index} did {action.action_type} for {action.amount}")
# Board at that street: preflop.community_cards ([]), flop.community_cards (3 cards), etc.
```

### Utility Methods

```python
# Current betting street
street = gamestate.get_current_street()  # 'preflop', 'flop', 'turn', 'river'

# Amount needed to call
bet_to_call = gamestate.get_bet_to_call()

# Active player count
active = gamestate.get_active_players_count()

# Total players remaining in tournament
remaining = gamestate.get_non_busted_players_count()
```

## Action Validation

Your bot doesn't need to worry about illegal moves - the system automatically corrects them:

### Valid Actions

| Action | When Valid | Amount Parameter |
|--------|-----------|------------------|
| `'fold'` | Anytime | `0` |
| `'check'` | No bet to call | `0` |
| `'call'` | Bet to call | Amount needed to match bet |
| `'bet'` | First to bet on street | Bet size (min = big blind) |
| `'raise'` | Someone already bet | Additional chips to add to your current_bet |
| `'all-in'` | Anytime | Your remaining stack |

### Automatic Corrections

- **Fold when you can check** → Converted to check
- **Bet when someone already bet** → Converted to call or fold
- **Raise below minimum** → Adjusted to minimum raise
- **Bet more than you have** → Converted to all-in
- **Invalid amounts** → Corrected to legal values

### Example Actions

```python
# Fold
return ('fold', 0)

# Check (when no bet to call)
return ('check', 0)

# Call a 50 chip bet (assuming you have 50+ current_bet less than 50)
bet_to_call = gamestate.get_bet_to_call()
amount_to_call = bet_to_call - my_info.current_bet
return ('call', amount_to_call)

# Bet 100 chips (when no one has bet)
return ('bet', 100)

# Raise to 200 total (if current bet is 100, you need to add 100 more to your current_bet)
current_bet = gamestate.get_bet_to_call()
my_current_bet = my_info.current_bet
additional_needed = 200 - my_current_bet
return ('raise', additional_needed)

# Go all-in
return ('all-in', my_info.stack)
```

## Advanced Bot Strategies

### Hand Strength Calculation

You can use the HandJudge to evaluate your hand:

```python
from src.helpers.hand_judge import HandJudge

def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
    # Only works postflop (need community cards)
    if len(gamestate.community_cards) >= 3:
        hand_name, hand_values = HandJudge.evaluate_hand(hole_cards, gamestate.community_cards)
        print(f"I have: {hand_name}")  # e.g., "one pair", "flush", etc.
```

### Opponent Modeling

Track opponent actions to build a profile:

```python
class AdaptiveBot(Player):
    def __init__(self, player_index: int):
        super().__init__(player_index)
        self.opponent_fold_frequency = {}  # Track how often opponents fold
        self.opponent_aggression = {}      # Track betting patterns

    def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
        # Update opponent models from hand history
        self._update_opponent_models(gamestate)

        # Use models to inform decisions
        # ...
```

### Position Awareness

```python
def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
    button = gamestate.button_position
    my_pos = self.player_index
    num_players = len(gamestate.player_public_infos)

    # Calculate position relative to button
    # Button acts last postflop (best position)
    position_offset = (my_pos - button) % num_players

    if position_offset <= 2:
        print("Early position - play tight")
    elif position_offset <= 4:
        print("Middle position - moderate range")
    else:
        print("Late position - play loose")
```

### Pot Odds Calculation

```python
def should_call_draw(self, gamestate: PublicGamestate, outs: int) -> bool:
    """
    Determine if calling with a draw is profitable.

    Args:
        gamestate: Current game state
        outs: Number of cards that improve your hand

    Returns:
        True if pot odds justify calling
    """
    my_info = gamestate.player_public_infos[self.player_index]
    bet_to_call = gamestate.get_bet_to_call()
    amount_to_call = bet_to_call - my_info.current_bet

    # Calculate pot odds
    pot_after_call = gamestate.total_pot + amount_to_call
    pot_odds = amount_to_call / pot_after_call

    # Calculate equity (approximate)
    # Outs * 2 = rough equity percentage on next card
    # Outs * 4 = rough equity to river (from flop)
    street = gamestate.get_current_street()
    if street == 'flop':
        equity = outs * 4 / 100
    else:
        equity = outs * 2 / 100

    return equity > pot_odds
```

## Running Tournaments

### Head-to-Head Match

```python
from src.core.table import Table
from src.bots.my_bot import MyBot
from src.bots.exploiter_bot import ExploiterBot

# 1v1 match
players = [MyBot(0), ExploiterBot(1)]
blinds_schedule = {1: (10, 20), 50: (25, 50), 100: (50, 100)}

table = Table(players, starting_stack=1500, blinds_schedule=blinds_schedule)

hand_num = 1
while sum(1 for p in table.player_public_infos if not p.busted) > 1:
    result = table.simulate_hand()
    hand_num += 1

winner = [i for i, p in enumerate(table.player_public_infos) if not p.busted][0]
print(f"Winner: Player {winner} after {hand_num} hands")
```

### Multi-Table Tournament

```python
# Run multiple independent tables
winners = []

for table_num in range(4):
    players = [MyBot(i) for i in range(8)]
    blinds_schedule = {1: (10, 20), 20: (25, 50), 40: (50, 100)}

    table = Table(players, starting_stack=1000, blinds_schedule=blinds_schedule, seed=table_num)

    # Play until one winner
    while sum(1 for p in table.player_public_infos if not p.busted) > 1:
        table.simulate_hand()

    winner = [i for i, p in enumerate(table.player_public_infos) if not p.busted][0]
    winners.append(players[winner])

print(f"Table winners: {len(winners)}")

# Finals table with winners
final_table = Table(winners, starting_stack=5000, blinds_schedule=blinds_schedule)
# ... play finals
```

### Statistical Analysis

```python
# Run many games for statistical significance
from collections import Counter

results = Counter()

for game in range(100):
    players = [MyBot(0), ExploiterBot(1), CallBot(2), RandomBot(3)]
    table = Table(players, starting_stack=1000, blinds_schedule={1: (10, 20)}, seed=game)

    while sum(1 for p in table.player_public_infos if not p.busted) > 1:
        table.simulate_hand()

    winner = [i for i, p in enumerate(table.player_public_infos) if not p.busted][0]
    results[type(players[winner]).__name__] += 1

print("Win rates:")
for bot_name, wins in results.most_common():
    print(f"{bot_name}: {wins}% ({wins}/100)")
```

## Example Bots

### CallBot (`src/bots/call_bot.py`)
- Always calls or checks
- Never folds or raises
- Baseline "calling station" strategy

### RandomBot (`src/bots/random_bot.py`)
- Makes random legal actions
- Good for testing edge cases

### ExploiterBot (`src/bots/exploiter_bot.py`)
- Designed to beat calling stations
- Plays premium hands aggressively
- Folds weak hands
- Never bluffs (opponent won't fold)

## Testing and Debugging

### Run Unit Tests

```bash
python -m pytest tests/test_components.py -v
```

### Run Integration Tests

```bash
python -m pytest tests/test_integration.py -v
```

### Verify Chip Conservation

```python
table = Table(players, starting_stack=1000, blinds_schedule=blinds_schedule)

for _ in range(100):
    table.simulate_hand()

    is_valid, expected, actual = table.verify_chip_count()
    if not is_valid:
        print(f"CHIP LEAK! Expected {expected}, got {actual}")
        break
```

### Debug Bot Decisions

```python
class DebugBot(Player):
    def get_action(self, gamestate: PublicGamestate, hole_cards: Tuple[str, str]) -> Tuple[str, int]:
        print(f"\n--- Player {self.player_index} Decision ---")
        print(f"Hole cards: {hole_cards}")
        print(f"Community: {gamestate.community_cards}")
        print(f"Pot: {gamestate.total_pot}")
        print(f"My stack: {gamestate.player_public_infos[self.player_index].stack}")
        print(f"Bet to call: {gamestate.get_bet_to_call()}")

        # Your decision logic here
        action = ('call', 0)
        print(f"Action: {action}")
        return action
```

## Competition Guidelines

### For Participants

1. **Create one bot class** extending `Player`
2. **No external dependencies** - pure Python only
3. **No file I/O** or network access during games
4. **Stateless between games** - reset state in `__init__`
5. **Time limit:** Return action within reasonable time (suggest <100ms)

### For Organizers

```python
# Tournament structure
from src.core.table import Table
import importlib

# Load bot submissions dynamically
bot_files = ['bot1.py', 'bot2.py', 'bot3.py', ...]
bots = []

for i, bot_file in enumerate(bot_files):
    module = importlib.import_module(bot_file.replace('.py', ''))
    BotClass = module.Bot  # Assume each file has a Bot class
    bots.append(BotClass(i))

# Run tournament
blinds_schedule = {
    1: (10, 20),
    30: (25, 50),
    60: (50, 100),
    90: (100, 200),
}

table = Table(bots, starting_stack=10000, blinds_schedule=blinds_schedule, seed=42)

hand_num = 1
while sum(1 for p in table.player_public_infos if not p.busted) > 1:
    print(f"\n=== Hand {hand_num} ===")
    result = table.simulate_hand()

    # Print results
    for player_idx, (hand_name, amount) in result['winners'].items():
        print(f"Winner: Player {player_idx} ({hand_name}) wins {amount} chips")

    if result['eliminated']:
        for player_idx in result['eliminated']:
            print(f"ELIMINATED: Player {player_idx}")

    # When result['showdown'] is True, result['showdown_details'] has 'players' and 'hands' (player_idx -> hand name)
    hand_num += 1

# Final standings
print("\n=== FINAL STANDINGS ===")
winner_idx = [i for i, p in enumerate(table.player_public_infos) if not p.busted][0]
print(f"Champion: {type(bots[winner_idx]).__name__}")
```

## Troubleshooting

### Bot keeps getting folded automatically
- You're trying to fold when you can check (0 bet to call)
- System auto-corrects this to check

### Bot's raises aren't working
- Make sure you're returning the **additional** chips needed
- Not the total bet size
- Example: If bet is 50 and you want to raise to 150:
  - Current bet to you: 50
  - Your current_bet might be 0
  - Return `('raise', 150)` to add 150 to your current bet

### All-in isn't registering
- Return `('all-in', remaining_stack)`
- Where `remaining_stack = gamestate.player_public_infos[self.player_index].stack`

### Can't see community cards preflop
- `gamestate.community_cards` is empty before the flop
- Check `len(gamestate.community_cards)` before accessing

## Additional Resources

- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed system architecture
- [tests/](tests/) - Example usage and edge cases
- [examples/simple_game.py](examples/simple_game.py) - Complete game example

## Contributing

To add features or fix bugs:

1. Write tests first (`tests/`)
2. Implement changes
3. Verify chip conservation
4. Run full test suite
5. Submit pull request

## License

[Add your license here]

## Support

For questions or issues:
- Open GitHub issue
- Contact tournament organizers
- Check existing bot implementations in `src/bots/`

---

Good luck with your poker bot! May the best algorithm win!
