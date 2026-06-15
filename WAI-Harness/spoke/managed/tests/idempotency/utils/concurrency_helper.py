#!/usr/bin/env python3
"""
Concurrency Test Helpers

Utilities for testing concurrent operations, race conditions, and
multi-process scenarios in Wheelwright idempotency tests.
"""

import multiprocessing as mp
import threading
import time
import queue
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional, Tuple
import tempfile
import os


class ProcessBarrier:
    """Synchronization barrier for coordinating multiple processes."""

    def __init__(self, num_processes: int):
        self.num_processes = num_processes
        self.manager = mp.Manager()
        self.counter = self.manager.Value("i", 0)
        self.lock = self.manager.Lock()
        self.ready_event = self.manager.Event()

    def wait(self, timeout: Optional[float] = None):
        """Wait for all processes to reach the barrier."""
        with self.lock:
            self.counter.value += 1
            if self.counter.value == self.num_processes:
                self.ready_event.set()

        # Wait for all processes to be ready
        return self.ready_event.wait(timeout)


def spawn_closeout_process(
    spoke_dir: Path,
    agent_name: str,
    results_queue: mp.Queue,
    barrier: Optional[ProcessBarrier] = None,
    delay: float = 0.0,
) -> mp.Process:
    """
    Spawn a process that attempts a closeout operation.

    Args:
        spoke_dir: Spoke directory to operate on
        agent_name: Name of the agent performing closeout
        results_queue: Queue to put results in
        barrier: Optional barrier for synchronization
        delay: Delay before starting operation

    Returns:
        Started process
    """

    def worker():
        try:
            if delay > 0:
                time.sleep(delay)

            if barrier:
                barrier.wait(timeout=10)

            # Attempt closeout operation
            result = attempt_closeout_operation(spoke_dir, agent_name)
            results_queue.put(
                {
                    "agent": agent_name,
                    "success": result["success"],
                    "message": result.get("message", ""),
                    "error": result.get("error", ""),
                }
            )

        except Exception as e:
            results_queue.put(
                {
                    "agent": agent_name,
                    "success": False,
                    "error": f"Process exception: {str(e)}",
                }
            )

    process = mp.Process(target=worker)
    process.start()
    return process


def attempt_closeout_operation(spoke_dir: Path, agent_name: str) -> Dict[str, Any]:
    """
    Attempt a closeout operation with proper locking.

    Args:
        spoke_dir: Spoke directory
        agent_name: Agent performing the operation

    Returns:
        Operation result dictionary
    """
    lock_file = spoke_dir / "WAI-Spoke" / ".closeout.lock"

    try:
        # Try to acquire lock atomically
        try:
            # Use exclusive creation to ensure atomicity
            with open(lock_file, "x") as f:
                f.write(f"{agent_name}\n{time.time()}")
        except FileExistsError:
            return {
                "success": False,
                "error": f"Concurrent closeout operation detected by {agent_name}",
                "agent": agent_name,
            }

        # Simulate closeout work
        time.sleep(0.5)  # Simulate processing time

        # TODO: Call actual closeout implementation here
        # For now, simulate successful completion

        return {
            "success": True,
            "message": f"Closeout completed by {agent_name}",
            "agent": agent_name,
        }

    finally:
        # Always clean up lock
        if lock_file.exists():
            lock_file.unlink()


def wait_for_completion(processes: List[mp.Process], timeout: float = 30.0) -> bool:
    """
    Wait for all processes to complete.

    Args:
        processes: List of processes to wait for
        timeout: Maximum time to wait

    Returns:
        True if all completed within timeout, False otherwise
    """
    start_time = time.time()

    for process in processes:
        remaining_time = max(0, timeout - (time.time() - start_time))
        process.join(timeout=remaining_time)

        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
            if process.is_alive():
                process.kill()
            return False

    return True


def simulate_race_condition(
    operation_func: Callable[[Path, str], Dict[str, Any]],
    spoke_dir: Path,
    num_competitors: int = 2,
    delay_spread: float = 0.1,
) -> List[Dict[str, Any]]:
    """
    Simulate race condition between multiple operations.

    Args:
        operation_func: Function to execute concurrently
        spoke_dir: Spoke directory to operate on
        num_competitors: Number of concurrent operations
        delay_spread: Random delay spread to increase race probability

    Returns:
        List of operation results
    """
    import random

    processes = []
    results_queue = mp.Queue()

    # Create barrier for synchronization
    barrier = ProcessBarrier(num_competitors)

    def worker(agent_id: int):
        try:
            # Small random delay to increase race probability
            delay = random.uniform(0, delay_spread)
            time.sleep(delay)

            # Wait for all processes to be ready
            barrier.wait(timeout=10)

            # Execute operation
            result = operation_func(spoke_dir, f"agent-{agent_id}")
            results_queue.put(result)

        except Exception as e:
            results_queue.put(
                {
                    "success": False,
                    "error": f"Worker {agent_id} exception: {str(e)}",
                    "agent": f"agent-{agent_id}",
                }
            )

    # Spawn workers
    for i in range(num_competitors):
        p = mp.Process(target=worker, args=(i,))
        processes.append(p)
        p.start()

    # Wait for completion
    all_completed = wait_for_completion(processes)
    if not all_completed:
        raise RuntimeError("Some processes did not complete within timeout")

    # Collect results
    results = []
    while not results_queue.empty():
        results.append(results_queue.get())

    return results


def test_file_locking(
    file_path: Path, num_writers: int = 3, writes_per_writer: int = 5
) -> Dict[str, Any]:
    """
    Test file locking behavior with multiple writers.

    Args:
        file_path: File to write to
        num_writers: Number of concurrent writers
        writes_per_writer: Number of writes each writer performs

    Returns:
        Test results including corruption detection
    """

    def writer_worker(writer_id: int, results_queue: mp.Queue):
        try:
            for write_num in range(writes_per_writer):
                # Simulate work before write
                time.sleep(0.01)

                # Write to file
                line = f"Writer-{writer_id}-Write-{write_num}-{time.time()}\n"

                with open(file_path, "a") as f:
                    f.write(line)
                    f.flush()  # Force write

            results_queue.put(
                {
                    "writer_id": writer_id,
                    "success": True,
                    "writes_completed": writes_per_writer,
                }
            )

        except Exception as e:
            results_queue.put(
                {"writer_id": writer_id, "success": False, "error": str(e)}
            )

    # Ensure clean slate
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if file_path.exists():
        file_path.unlink()

    processes = []
    results_queue = mp.Queue()

    # Spawn writers
    for i in range(num_writers):
        p = mp.Process(target=writer_worker, args=(i, results_queue))
        processes.append(p)
        p.start()

    # Wait for completion
    all_completed = wait_for_completion(processes)

    # Collect results
    worker_results = []
    while not results_queue.empty():
        worker_results.append(results_queue.get())

    # Analyze file for corruption
    lines_written = 0
    corruption_detected = False

    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                lines = f.readlines()
                lines_written = len(lines)

                # Check for malformed lines
                for line in lines:
                    if not line.startswith("Writer-"):
                        corruption_detected = True
                        break

        except Exception:
            corruption_detected = True

    return {
        "all_completed": all_completed,
        "worker_results": worker_results,
        "lines_written": lines_written,
        "expected_lines": num_writers * writes_per_writer,
        "corruption_detected": corruption_detected,
    }


def simulate_network_interruption(
    operation_func: Callable,
    interruption_after: float = 1.0,
    interruption_duration: float = 2.0,
) -> Dict[str, Any]:
    """
    Simulate network interruption during operation.

    Args:
        operation_func: Function to execute with interruption
        interruption_after: Seconds after which to interrupt
        interruption_duration: Duration of interruption

    Returns:
        Operation result with interruption info
    """
    # This is a simplified simulation
    # In real implementation, would mock network calls

    import signal

    result = {"interrupted": False, "completed": False}

    def interrupt_handler(signum, frame):
        result["interrupted"] = True
        raise InterruptedError("Network interruption simulated")

    try:
        # Set up interruption
        signal.signal(signal.SIGALRM, interrupt_handler)
        signal.alarm(int(interruption_after))

        # Execute operation
        operation_result = operation_func()
        result["completed"] = True
        result["operation_result"] = operation_result

    except InterruptedError as e:
        result["error"] = str(e)

        # Simulate recovery after interruption
        time.sleep(interruption_duration)

        # Attempt to continue
        try:
            recovery_result = operation_func()
            result["recovered"] = True
            result["recovery_result"] = recovery_result
        except Exception as recovery_error:
            result["recovery_failed"] = True
            result["recovery_error"] = str(recovery_error)

    finally:
        signal.alarm(0)  # Cancel alarm

    return result


class ConcurrencyTestContext:
    """Context manager for concurrency testing with cleanup."""

    def __init__(self, num_processes: int = 2):
        self.num_processes = num_processes
        self.temp_dir = None
        self.processes = []
        self.results_queue = None

    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="wai_concurrency_test_")
        self.results_queue = mp.Queue()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Clean up processes
        for process in self.processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=1.0)
                if process.is_alive():
                    process.kill()

        # Clean up temp directory
        if self.temp_dir:
            import shutil

            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def spawn_worker(
        self, target_func: Callable, args: Tuple = (), kwargs: Dict = None
    ) -> mp.Process:
        """Spawn a worker process."""
        if kwargs is None:
            kwargs = {}

        def worker_wrapper():
            try:
                result = target_func(*args, **kwargs)
                self.results_queue.put(result)
            except Exception as e:
                self.results_queue.put({"success": False, "error": str(e)})

        process = mp.Process(target=worker_wrapper)
        self.processes.append(process)
        process.start()
        return process

    def wait_and_collect_results(self, timeout: float = 30.0) -> List[Dict[str, Any]]:
        """Wait for all processes and collect results."""
        all_completed = wait_for_completion(self.processes, timeout)

        if not all_completed:
            raise RuntimeError("Some processes did not complete within timeout")

        results = []
        while not self.results_queue.empty():
            results.append(self.results_queue.get())

        return results


def measure_contention_overhead(
    single_operation_func: Callable,
    concurrent_operation_func: Callable,
    num_trials: int = 5,
) -> Dict[str, Any]:
    """
    Measure overhead introduced by contention handling.

    Args:
        single_operation_func: Function to execute without contention
        concurrent_operation_func: Function to execute with potential contention
        num_trials: Number of trials to average

    Returns:
        Performance comparison results
    """
    single_times = []
    concurrent_times = []

    # Measure single operation times
    for _ in range(num_trials):
        start_time = time.time()
        single_operation_func()
        end_time = time.time()
        single_times.append(end_time - start_time)

    # Measure concurrent operation times
    for _ in range(num_trials):
        start_time = time.time()
        concurrent_operation_func()
        end_time = time.time()
        concurrent_times.append(end_time - start_time)

    avg_single = sum(single_times) / len(single_times)
    avg_concurrent = sum(concurrent_times) / len(concurrent_times)
    overhead_percent = ((avg_concurrent - avg_single) / avg_single) * 100

    return {
        "single_operation_avg": avg_single,
        "concurrent_operation_avg": avg_concurrent,
        "overhead_seconds": avg_concurrent - avg_single,
        "overhead_percent": overhead_percent,
        "trials": num_trials,
    }


# Process management utilities


def terminate_process_tree(pid: int):
    """Terminate a process and all its children."""
    import psutil

    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)

        for child in children:
            child.terminate()

        parent.terminate()

        # Wait for termination
        gone, alive = psutil.wait_procs([parent] + children, timeout=3)

        # Force kill if still alive
        for p in alive:
            p.kill()

    except psutil.NoSuchProcess:
        pass  # Process already gone


def is_process_responsive(pid: int) -> bool:
    """Check if a process is responsive (not deadlocked)."""
    import psutil

    try:
        process = psutil.Process(pid)

        # Check if process is in a problematic state
        if process.status() in [psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD]:
            return False

        # Basic responsiveness check - CPU usage should be reasonable
        cpu_percent = process.cpu_percent(interval=0.1)
        if cpu_percent > 90:  # Potentially stuck in busy loop
            return False

        return True

    except psutil.NoSuchProcess:
        return False
