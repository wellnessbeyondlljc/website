#!/usr/bin/env python3
"""
Idempotency Test Suite Runner

Orchestrates the execution of all idempotency tests with proper environment setup,
parallel execution options, and comprehensive reporting.
"""

import argparse
import sys
import time
import unittest
from pathlib import Path
from typing import List, Dict, Any

# Add current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))


def discover_tests(test_dir: Path) -> unittest.TestSuite:
    """Discover all test files in the test directory."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Find all test_*.py files
    test_files = list(test_dir.glob("test_*.py"))

    for test_file in test_files:
        try:
            # Import module dynamically
            module_name = test_file.stem
            spec = unittest.util.spec_from_file_location(module_name, test_file)
            if spec and spec.loader:
                module = unittest.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Add tests from module
                module_tests = loader.loadTestsFromModule(module)
                suite.addTest(module_tests)

        except Exception as e:
            print(f"Warning: Could not load tests from {test_file}: {e}")

    return suite


def run_test_category(category: str) -> Dict[str, Any]:
    """Run tests for a specific category."""
    test_dir = Path(__file__).parent

    category_map = {
        "closeout": "test_closeout_replay.py",
        "concurrent": "test_concurrent_closeout.py",
        "signals": "test_signal_deduplication.py",
        "migration": "test_migration_resume.py",
    }

    if category not in category_map:
        return {"success": False, "error": f"Unknown category: {category}"}

    test_file = test_dir / category_map[category]

    if not test_file.exists():
        return {"success": False, "error": f"Test file not found: {test_file}"}

    # Run specific test file
    loader = unittest.TestLoader()
    suite = loader.discover(str(test_dir), pattern=category_map[category])

    # Custom test result to capture details
    class DetailedTestResult(unittest.TestResult):
        def __init__(self):
            super().__init__()
            self.test_details = []

        def addSuccess(self, test):
            super().addSuccess(test)
            self.test_details.append({"test": str(test), "status": "PASS", "time": 0})

        def addError(self, test, err):
            super().addError(test, err)
            self.test_details.append(
                {"test": str(test), "status": "ERROR", "error": str(err[1]), "time": 0}
            )

        def addFailure(self, test, err):
            super().addFailure(test, err)
            self.test_details.append(
                {"test": str(test), "status": "FAIL", "error": str(err[1]), "time": 0}
            )

    result = DetailedTestResult()
    start_time = time.time()
    suite.run(result)
    end_time = time.time()

    return {
        "success": result.wasSuccessful(),
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "time": end_time - start_time,
        "details": result.test_details,
    }


def main():
    """Main test runner."""
    parser = argparse.ArgumentParser(description="Run Wheelwright idempotency tests")
    parser.add_argument(
        "--category",
        choices=["closeout", "concurrent", "signals", "migration", "all"],
        default="all",
        help="Test category to run",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast tests (skip slow concurrency tests)",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Wheelwright Idempotency Test Suite")
    print("=" * 60)

    # Check if we can import required modules
    try:
        import multiprocessing

        print(f"✓ Multiprocessing support available")
    except ImportError:
        print("✗ Warning: Multiprocessing not available, concurrent tests may fail")

    # Set up environment
    test_dir = Path(__file__).parent
    print(f"Test directory: {test_dir}")

    if args.category == "all":
        categories = ["closeout", "concurrent", "signals", "migration"]
        if args.quick:
            categories = ["closeout", "signals", "migration"]  # Skip concurrent tests
    else:
        categories = [args.category]

    overall_success = True
    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_time = 0

    for category in categories:
        print(f"\n{'─' * 40}")
        print(f"Running {category} tests...")
        print(f"{'─' * 40}")

        result = run_test_category(category)

        if result.get("success"):
            print(f"✓ {category}: All tests passed")
        else:
            print(f"✗ {category}: Tests failed")
            overall_success = False

        # Print details
        tests_run = result.get("tests_run", 0)
        failures = result.get("failures", 0)
        errors = result.get("errors", 0)
        test_time = result.get("time", 0)

        print(f"  Tests run: {tests_run}")
        print(f"  Failures: {failures}")
        print(f"  Errors: {errors}")
        print(f"  Time: {test_time:.2f}s")

        if args.verbose and "details" in result:
            for detail in result["details"]:
                status_icon = "✓" if detail["status"] == "PASS" else "✗"
                print(f"    {status_icon} {detail['test']}")
                if detail["status"] != "PASS" and "error" in detail:
                    print(f"      Error: {detail['error']}")

        total_tests += tests_run
        total_failures += failures
        total_errors += errors
        total_time += test_time

    # Summary
    print(f"\n{'=' * 60}")
    print("Test Summary")
    print(f"{'=' * 60}")
    print(f"Overall result: {'PASS' if overall_success else 'FAIL'}")
    print(f"Total tests: {total_tests}")
    print(f"Failures: {total_failures}")
    print(f"Errors: {total_errors}")
    print(f"Total time: {total_time:.2f}s")

    if not overall_success:
        print("\nSome tests failed. See details above.")
        sys.exit(1)
    else:
        print("\nAll tests passed successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
