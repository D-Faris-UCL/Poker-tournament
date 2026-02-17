import signal
import functools
from typing import Callable

def timeout(func: Callable, seconds: int=5, default: any=None, *args, **kwargs) -> any:
    """Runs a function. If the function exceeds the time limit, a default value is returned.

    Args:
        func (Callable): The function to call.
        seconds (int): The time limit.
        default (any): Default return value.

    Returns:
        any: The function result or the default return value.
    """

    def handle_timeout(signum, frame):
        raise TimeoutError()

    
    try:
        signal.signal(signal.SIGALRM, handle_timeout)
        signal.alarm(seconds)

        result = func(*args, **kwargs)

        signal.alarm(0)
    except TimeoutError:
        return default

    return result




if __name__ == "__main__":
    import time
    def long():
        time.sleep(10)
        return 100
    
    print(timeout(long, seconds=1, default={"action": "call", "amount": 0}))