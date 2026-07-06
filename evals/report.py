"""Tiny terminal reporter for eval runs (no third-party deps)."""

from __future__ import annotations

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def line(passed: bool, label: str, got: str, expected: str | None = None) -> str:
    mark = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    suffix = ""
    if not passed and expected is not None:
        suffix = f" {DIM}(expected {expected}){RESET}"
    return f"  [{mark}] {label:<42} -> {got}{suffix}"


def warn_line(label: str, value: str) -> str:
    return f"  [{YELLOW}WARN{RESET}] {label:<42} -> {value}"


def summary(title: str, passed: int, total: int) -> str:
    pct = (passed / total * 100) if total else 0.0
    color = GREEN if passed == total else (YELLOW if pct >= 75 else RED)
    return f"\n{title}: {color}{passed}/{total} ({pct:.1f}%){RESET}"
