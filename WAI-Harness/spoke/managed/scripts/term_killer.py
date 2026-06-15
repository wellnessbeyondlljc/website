#!/usr/bin/env python3
"""
term_killer.py - Robust Terminal/Process Cleanup Helper

A standalone utility to terminate stubborn processes using a cascade strategy:
1. Polite Request (SIGTERM)
2. Firm Request (SIGTERM again)
3. Nuclear Option (SIGKILL)

Logs detailed timing to term_killer.log.
"""

import sys
import os
import time
import signal
import subprocess
import argparse
import logging
from datetime import datetime
from typing import List, Optional

# Setup logging
LOG_FILE = "term_killer.log"
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

def find_pids(pattern: str) -> List[int]:
    """Find PIDs matching a substring pattern."""
    pids = []
    try:
        # Use pgrep to find PIDs
        cmd = ["pgrep", "-f", pattern]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    try:
                        pid = int(line)
                        # Exclude self
                        if pid != os.getpid():
                            pids.append(pid)
                    except ValueError:
                        pass
    except Exception as e:
        logging.error(f"Error finding PIDs for pattern '{pattern}': {e}")
    
    return pids

def check_alive(pid: int) -> bool:
    """Check if a process is still alive."""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def kill_pid_cascade(pid: int):
    """Attempt to kill a PID with escalating force."""
    start_time = time.time()
    logging.info(f"Targeting PID {pid}...")
    
    if not check_alive(pid):
        logging.info(f"PID {pid} is already dead.")
        return

    # Phase 1: Polite SIGTERM
    logging.info(f"[{time.time() - start_time:.2f}s] Level 1: Sending SIGTERM to {pid}")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        logging.error(f"Failed to send SIGTERM to {pid}: {e}")
        return

    # Wait 1s
    for _ in range(10):
        time.sleep(0.1)
        if not check_alive(pid):
            logging.info(f"[{time.time() - start_time:.2f}s] Success: PID {pid} terminated gracefully.")
            return

    # Phase 2: Double Tap SIGTERM
    logging.info(f"[{time.time() - start_time:.2f}s] Level 2: Resending SIGTERM to {pid}")
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass

    # Wait 2s
    for _ in range(20):
        time.sleep(0.1)
        if not check_alive(pid):
            logging.info(f"[{time.time() - start_time:.2f}s] Success: PID {pid} terminated after retry.")
            return

    # Phase 3: Nuclear SIGKILL
    logging.warning(f"[{time.time() - start_time:.2f}s] Level 3: Sending SIGKILL to {pid}")
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError as e:
        logging.error(f"Failed to send SIGKILL to {pid}: {e}")
        return

    # Final check
    time.sleep(0.5)
    if check_alive(pid):
        logging.error(f"[{time.time() - start_time:.2f}s] FAILURE: PID {pid} is still alive after SIGKILL!")
    else:
        logging.info(f"[{time.time() - start_time:.2f}s] Success: PID {pid} nuked.")

def main():
    parser = argparse.ArgumentParser(description="Robust Process Killer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", help="Substring to match in process name")
    group.add_argument("--pid", type=int, help="Specific PID to kill")
    
    args = parser.parse_args()
    
    targets = []
    
    if args.pid:
        targets.append(args.pid)
    elif args.name:
        logging.info(f"Searching for processes matching '{args.name}'...")
        targets = find_pids(args.name)
        logging.info(f"Found {len(targets)} matching processes.")
    
    if not targets:
        logging.info("No targets found.")
        sys.exit(0)
        
    for pid in targets:
        kill_pid_cascade(pid)

if __name__ == "__main__":
    main()
