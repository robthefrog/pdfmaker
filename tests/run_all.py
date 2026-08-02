#!/usr/bin/env python3
"""Run every pdfmaker test suite; exit nonzero if any check fails.

Usage:  python3 tests/run_all.py
Each suite finds the project's .venv by itself, so this works with plain
system Python as long as a launcher has been run once (or the three
packages are installed for the interpreter used).
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ("test_recursive.py", "test_launcher.py")


def main() -> None:
    failed = []
    for suite in SUITES:
        print(f"===== {suite} =====")
        r = subprocess.run([sys.executable, os.path.join(HERE, suite)])
        if r.returncode != 0:
            failed.append(suite)
        print()
    if failed:
        sys.exit("FAILED: " + ", ".join(failed))
    print("all suites passed")


if __name__ == "__main__":
    main()
