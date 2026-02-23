import multiprocessing
import psutil

def sandbox_worker(user_bot_instance, conn):
    """This runs in the background. It holds the user's actual bot object."""
    while True:
        try:
            gamestate, hole_cards = conn.recv()
            action, amount = user_bot_instance.get_action(gamestate, hole_cards)
            conn.send((action, amount))
            
        except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
            # The parent engine closed the pipe, terminated, or restarted.
            # Do NOT try to send data back. Just exit gracefully.
            break
            
        except Exception as e:
            # The USER'S bot code crashed (e.g., KeyError, ZeroDivisionError).
            # Tell the parent table to force a fold.
            try:
                conn.send(("fold", 0))
            except (BrokenPipeError, OSError):
                break # Just in case the pipe broke at the exact same time

class SandboxedPlayer:
    """The Table talks to this, thinking it's the real player."""
    
    def __init__(self, user_bot_instance, max_ram_mb=500, time_limit=1.0):
        self.user_bot = user_bot_instance # The class the user defined
        self.max_ram = max_ram_mb
        self.time_limit = time_limit
        self.process = None
        self.conn = None
        self._boot_sandbox()

    def _boot_sandbox(self):
        if self.process:
            self.process.terminate()
        parent_conn, child_conn = multiprocessing.Pipe()
        self.conn = parent_conn
        
        # We pass the user's initialized class into the isolated process
        self.process = multiprocessing.Process(
            target=sandbox_worker, 
            args=(self.user_bot, child_conn)
        )
        self.process.start()
        self.monitor = psutil.Process(self.process.pid)

    # THIS IS THE MAGIC: It exactly matches the expected interface!
    def get_action(self, gamestate, hole_cards):
        # 1. Check if the user's code ate too much RAM
        try:
            if (self.monitor.memory_info().rss / 1024**2) > self.max_ram:
                print(f"[!] Bot used too much RAM! Forcing fold and restarting.")
                self._boot_sandbox()
                return "fold", 0
        except psutil.NoSuchProcess:
            self._boot_sandbox()

        # 2. Ask the user's code for an action
        self.conn.send((gamestate, hole_cards))
        
        # 3. Apply the strict 1-second timeout
        if self.conn.poll(timeout=self.time_limit):
            return self.conn.recv()
        else:
            print("[!] Bot took too long! Forcing fold and restarting.")
            self._boot_sandbox() # Nuke it to stop the infinite loop
            return "fold", 0
        
    def close(self):
        """Cleanly shut down the process and pipes when the tournament ends."""
        if self.process and self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=1) # Wait up to 1 second for it to die
        if self.conn:
            self.conn.close()

    def __del__(self):
        """Failsafe: If the object is deleted, ensure it cleans up."""
        self.close()