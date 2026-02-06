# Quick Start Guide

Get started with the Poker Tournament Environment in 5 minutes!

## Installation

```bash
# No dependencies needed - pure Python!
git clone <your-repo>
cd poker-tournament

# Verify Python version (3.7+ required)
python --version
```

## Run the Example

```bash
# Run the simple example
python examples/simple_game.py

# Run tests to verify everything works
python tests/test_components.py
```

## Create Your First Bot

### Step 1: Create a new bot file

Create `src/bots/my_bot.py`:

```python
from typing import Tuple
from ..core.player import Player
from ..core.gamestate import PublicGamestate

class MyBot(Player):
    """My first poker bot"""

    def make_decision(
        self,
        public_gamestate: PublicGamestate,
        hole_cards: Tuple[str, str]
    ) -> Tuple[str, int]:
        """Make a decision based on game state"""

        # Get useful information
        my_info = public_gamestate.player_public_infos[self.player_index]
        my_stack = my_info.stack
        current_bet = public_gamestate.get_current_bet()
        amount_to_call = current_bet - my_info.current_bet

        # Simple strategy: Always call or check
        if amount_to_call == 0:
            return ('check', 0)
        else:
            return ('call', 0)
```

### Step 2: Test your bot

Create `test_my_bot.py`:

```python
from src.core.table import Table
from src.bots.my_bot import MyBot
from src.bots.random_bot import RandomBot

# Create bots
my_bot = MyBot(player_index=0)
opponent1 = RandomBot(player_index=1)
opponent2 = RandomBot(player_index=2)

# Setup game
blinds_schedule = {1: (10, 20)}
table = Table(
    players=[my_bot, opponent1, opponent2],
    starting_stack=1000,
    blinds_schedule=blinds_schedule,
    seed=42
)

# Play a hand (basic setup)
table.reset_hand_state()
table.deal_hole_cards()
table.collect_blinds()

print(f"My hole cards: {table.player_hole_cards[0]}")
print(f"My stack: {table.player_public_infos[0].stack}")

# Get decision
gamestate = table.get_public_gamestate()
action, amount = my_bot.make_decision(gamestate, table.player_hole_cards[0])
print(f"My decision: {action} {amount}")
```

## Understanding Game State

### What your bot receives:

```python
public_gamestate = PublicGamestate(
    round_number=1,                    # Current round
    player_public_infos=[...],         # All players' info
    button_position=0,                 # Dealer button
    community_cards=['Ah', 'Kd', 'Qc'], # Board
    total_pot=150,                     # Pot size
    side_pots=[],                      # Side pots
    blinds=(10, 20),                   # Current blinds
    minimum_raise_amount=20,           # Min raise
    current_hand_history={...},        # Action history
)
```

### Accessing player information:

```python
# Your information
my_idx = self.player_index
my_info = public_gamestate.player_public_infos[my_idx]
print(f"My stack: {my_info.stack}")
print(f"My current bet: {my_info.current_bet}")
print(f"Am I active: {my_info.active}")

# Opponent information
for i, info in enumerate(public_gamestate.player_public_infos):
    if i != my_idx and info.active:
        print(f"Player {i}: stack={info.stack}, bet={info.current_bet}")
```

### Understanding the board:

```python
community = public_gamestate.community_cards
street = public_gamestate.get_current_street()  # 'preflop', 'flop', 'turn', 'river'

if street == 'preflop':
    print("No community cards yet")
elif street == 'flop':
    print(f"Flop: {community}")  # 3 cards
elif street == 'turn':
    print(f"Turn: {community}")  # 4 cards
elif street == 'river':
    print(f"River: {community}") # 5 cards
```

## Valid Actions

Your bot must return `(action_type, amount)`:

### Fold
```python
return ('fold', 0)  # Give up hand
```

### Check
```python
return ('check', 0)  # Only when no bet to call
```

### Call
```python
return ('call', 0)  # Match current bet (amount ignored)
```

### Bet
```python
return ('bet', 100)  # When no bet exists, start betting
```

### Raise
```python
# Raise by 50 chips (total bet = current + 50)
return ('raise', 50)
```

### All-in
```python
return ('all-in', 0)  # Bet everything (amount ignored)
```

**Note**: Invalid actions are automatically corrected by PlayerJudge!

## Strategy Tips

### 1. Calculate Pot Odds
```python
pot = public_gamestate.total_pot
to_call = current_bet - my_info.current_bet
pot_odds = to_call / (pot + to_call)
```

### 2. Count Active Players
```python
active = public_gamestate.get_active_players_count()
```

### 3. Track Opponent Behavior
```python
history = public_gamestate.current_hand_history
for street, actions in history.items():
    for action in actions:
        if action.player_index != self.player_index:
            print(f"Opponent action: {action}")
```

### 4. Evaluate Your Hand (basic)
```python
from src.helpers.hand_judge import HandJudge

hand = HandJudge.evaluate_hand(hole_cards, public_gamestate.community_cards)
hand_name, values = hand
print(f"I have: {hand_name}")
```

### 5. Position Awareness
```python
button = public_gamestate.button_position
my_position = (self.player_index - button) % len(public_gamestate.player_public_infos)
```

## Common Patterns

### Aggressive Bot
```python
if amount_to_call == 0:
    return ('bet', my_stack // 2)  # Bet half stack
else:
    return ('raise', current_bet)   # Raise
```

### Tight Bot
```python
# Only play strong hands
if self._is_strong_hand(hole_cards):
    if amount_to_call == 0:
        return ('check', 0)
    else:
        return ('call', 0)
else:
    return ('fold', 0)
```

### Positional Bot
```python
if my_position >= num_players - 2:  # Late position
    # More aggressive
    return ('raise', 50)
else:  # Early position
    # More conservative
    return ('call', 0)
```

## Debugging Your Bot

### Print game state
```python
def make_decision(self, public_gamestate, hole_cards):
    print(f"\n=== Player {self.player_index} Decision ===")
    print(f"Hole cards: {hole_cards}")
    print(f"Community: {public_gamestate.community_cards}")
    print(f"Pot: {public_gamestate.total_pot}")
    print(f"Stack: {public_gamestate.player_public_infos[self.player_index].stack}")

    # Your logic here
    return ('call', 0)
```

### Test specific scenarios
```python
# Create specific game state for testing
from src.core.data_classes import PlayerPublicInfo

player_infos = [
    PlayerPublicInfo(stack=1000, current_bet=0, active=True, busted=False),
    PlayerPublicInfo(stack=500, current_bet=50, active=True, busted=False),
]
# ... create gamestate and test
```

## Next Steps

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design
2. Study [src/bots/random_bot.py](src/bots/random_bot.py) for a complete example
3. Look at [src/helpers/hand_judge.py](src/helpers/hand_judge.py) for hand evaluation
4. Check [tests/test_components.py](tests/test_components.py) for usage examples

## Common Issues

### "Invalid action" errors
- **Solution**: PlayerJudge auto-corrects these, but log warnings to debug

### Bot too slow
- **Solution**: Optimize calculations, avoid expensive operations in tight loops

### Can't access other players' cards
- **Solution**: This is intentional! You only get public information

### Confused about betting amounts
- **Solution**: For 'bet' and 'raise', amount is ADDITIONAL chips, not total

## Resources

- **Poker Hand Rankings**: See HandJudge.HAND_RANKINGS in hand_judge.py
- **Card Notation**: Rank (2-9, T, J, Q, K, A) + Suit (h, d, c, s)
- **Action Types**: fold, check, call, bet, raise, all-in

## Competition Tips

1. **Start Simple**: Get a working bot first, optimize later
2. **Test Thoroughly**: Play against RandomBot to verify logic
3. **Learn Game Theory**: Study pot odds, position, and ranges
4. **Track History**: Use previous hands to model opponents
5. **Manage Risk**: Balance aggression with survival

Good luck building your bot!
