import multiprocessing
import psutil
import time

def worker_wrapper(func, args, queue):
    """
    A wrapper that runs the actual function and puts the 
    return value into a queue for the parent to collect.
    """
    try:
        result = func(*args)
        queue.put(result)
    except Exception as e:
        queue.put(f"Error: {e}")

def run_with_limit(func, args, mem_limit_mb, default=None):
    """
    Runs a function sequentially with a hard RAM monitor.
    Returns the function's return value OR the default value if limit hit.
    """
    q = multiprocessing.Queue()
    p = multiprocessing.Process(target=worker_wrapper, args=(func, args, q))
    p.start()
    
    proc_monitor = psutil.Process(p.pid)
    result = default # Initialize with default
    
    try:
        while p.is_alive():
            # Check memory usage
            current_mem = proc_monitor.memory_info().rss / (1024 * 1024)
            
            if current_mem > mem_limit_mb:
                print(f"!!! Limit Hit ({current_mem:.1f}MB). Terminating...")
                p.terminate()
                p.join()
                return default # Return default immediately on limit hit
            
            # Small sleep to prevent high CPU usage from the monitor itself
            time.sleep(0.1) 
            
        # If the process finished naturally, get the result from the queue
        if not q.empty():
            result = q.get()
            
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    finally:
        p.join()
        
    return result

# --- Example Usage ---

def my_heavy_function(n):
    # Simulate work that might grow in RAM
    data = []
    for i in range(n):
        data.append(" " * 10**6) # 1MB chunks
    return f"Success with {len(data)}MB"

if __name__ == "__main__":
    tasks = [10, 800, 20] # The 800MB task will fail our 500MB limit
    
    for val in tasks:
        print(f"Running task with size: {val}...")
        
        # This will return the string or None if it crashes
        final_val = run_with_limit(my_heavy_function, (val,), mem_limit_mb=500, default="FAILED_RAM")
        
        print(f"Result: {final_val}")