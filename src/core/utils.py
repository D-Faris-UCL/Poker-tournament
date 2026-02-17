import signal
import functools

def timeout(func, seconds=5, default=None, *args, **kwargs):

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