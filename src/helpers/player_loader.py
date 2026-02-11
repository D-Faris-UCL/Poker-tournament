"""Dynamic player/bot loader for discovering and importing bot classes"""

import importlib
import inspect
from pathlib import Path
from typing import List, Type, Optional, Dict, Any


def load_players(src: str) -> List[Type]:
    """Dynamically load all player classes from the specified source directory.

    Each player class must be in its own subdirectory with a file named 'player.py'.
    For example: src/bots/random_bot/player.py

    Args:
        src: Path to the players directory (e.g., 'src/bots')

    Returns:
        List of player classes found in the source directory

    Example:
        >>> players = load_players('src/bots')
        >>> for player_class in players:
        ...     print(player_class.__name__)
    """
    player_classes = []
    src_path = Path(src)

    if not src_path.exists():
        raise FileNotFoundError(f"Source directory '{src}' does not exist")

    # Iterate through each subdirectory in the source path
    for player_dir in src_path.iterdir():
        if not player_dir.is_dir():
            continue

        # Skip __pycache__ and other special directories
        if player_dir.name.startswith('__'):
            continue

        # Look for player.py in the directory
        player_file = player_dir / "player.py"

        if not player_file.exists():
            print(f"Warning: Skipping '{player_dir.name}' - no player.py found")
            continue

        try:
            # Convert path to module path (e.g., 'src/bots' -> 'src.bots', 'tests/test_bots' -> 'tests.test_bots')
            module_base = src.replace('/', '.').replace('\\', '.')
            module_path = f"{module_base}.{player_dir.name}.player"
            module = importlib.import_module(module_path)

            # Find all classes in the module
            for _, obj in inspect.getmembers(module, inspect.isclass):
                # Only include classes defined in this module (not imports)
                if obj.__module__ == module_path:
                    player_classes.append(obj)

        except Exception as e:
            print(f"Warning: Failed to load player from {player_file}: {e}")
            continue

    return player_classes


def get_player_by_name(src: str, name: str) -> Optional[Type]:
    """Load a specific player class by its folder name.

    Args:
        src: Path to the players directory (e.g., 'src/bots')
        name: Name of the player folder (e.g., 'random_bot', 'claude')

    Returns:
        The player class if found, None otherwise

    Example:
        >>> RandomBot = get_player_by_name('src/bots', 'random_bot')
        >>> if RandomBot:
        ...     bot = RandomBot(player_index=0)
    """
    src_path = Path(src)
    player_dir = src_path / name

    if not player_dir.exists() or not player_dir.is_dir():
        print(f"Warning: Player directory '{name}' not found in {src}")
        return None

    player_file = player_dir / "player.py"

    if not player_file.exists():
        print(f"Warning: No player.py found in '{name}'")
        return None

    try:
        # Convert path to module path (e.g., 'src/bots' -> 'src.bots', 'tests/test_bots' -> 'tests.test_bots')
        module_base = src.replace('/', '.').replace('\\', '.')
        module_path = f"{module_base}.{name}.player"
        module = importlib.import_module(module_path)

        # Find the first class in the module
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ == module_path:
                return obj

        print(f"Warning: No class found in {player_file}")
        return None

    except Exception as e:
        print(f"Warning: Failed to load player from {player_file}: {e}")
        return None


def get_player_names(src: str) -> List[str]:
    """Get list of available player names (folder names) without loading them.

    Args:
        src: Path to the players directory (e.g., 'src/bots')

    Returns:
        List of player folder names that contain player.py

    Example:
        >>> names = get_player_names('src/bots')
        >>> print(names)
        ['random_bot', 'claude', 'gemini', 'chatgpt']
    """
    src_path = Path(src)
    player_names = []

    if not src_path.exists():
        return player_names

    for player_dir in src_path.iterdir():
        if not player_dir.is_dir() or player_dir.name.startswith('__'):
            continue

        player_file = player_dir / "player.py"
        if player_file.exists():
            player_names.append(player_dir.name)

    return sorted(player_names)


def validate_players(player_classes: List[Type], base_class: Optional[Type] = None) -> Dict[str, Any]:
    """Validate that loaded player classes meet requirements.

    Args:
        player_classes: List of player classes to validate
        base_class: Base class to check inheritance (default: Player from core).
                    If None, loads Player class automatically.

    Returns:
        Dictionary with validation results:
            - 'valid': List of valid player classes
            - 'invalid': List of (class, reason) tuples for invalid classes
            - 'all_valid': Boolean indicating if all classes are valid

    Example:
        >>> players = load_players('src/bots')
        >>> results = validate_players(players)
        >>> if results['all_valid']:
        ...     print("All players are valid!")
        >>> else:
        ...     for cls, reason in results['invalid']:
        ...         print(f"{cls.__name__}: {reason}")
    """
    # Import Player here to avoid circular imports and unused import warnings
    if base_class is None:
        from ..core.player import Player
        base_class = Player

    valid = []
    invalid = []

    for player_class in player_classes:
        # Check if it's a class
        if not inspect.isclass(player_class):
            invalid.append((player_class, "Not a class"))
            continue

        # Check inheritance from base_class
        if not issubclass(player_class, base_class):
            invalid.append((player_class, f"Does not inherit from {base_class.__name__}"))
            continue

        # Check if it has required method (get_action)
        if not hasattr(player_class, 'get_action'):
            invalid.append((player_class, "Missing get_action method"))
            continue

        valid.append(player_class)

    return {
        'valid': valid,
        'invalid': invalid,
        'all_valid': len(invalid) == 0
    }
