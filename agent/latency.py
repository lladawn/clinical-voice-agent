"""Per-turn latency instrumentation.

Voice UX degrades sharply past ~800ms of response latency, so the numbers that
matter are per-stage timings and their tail (p95), not an average. This module
provides:

  * TurnLatency — marks cumulative milliseconds from STT-final at each pipeline
    stage (guardrail -> rag -> llm_first_token -> end). The headline metric is
    STT-final -> first token (when the patient starts hearing a response).
  * LatencyStats — a rolling p50/p95 aggregator the worker logs periodically.

`time.monotonic()` is used throughout — it's immune to wall-clock adjustments.
"""

from __future__ import annotations

import math
import time


class TurnLatency:
    """Cumulative stage timings (ms from turn start) for one conversational turn."""

    # Ordered stages; not every turn hits every stage (canned turns skip rag/llm).
    STAGES = ("guardrail", "rag", "llm_first_token", "canned_response", "end")

    def __init__(self) -> None:
        self._t0 = time.monotonic()
        self.marks: dict[str, int] = {}

    def mark(self, stage: str) -> None:
        self.marks[stage] = int((time.monotonic() - self._t0) * 1000)

    def response_ms(self) -> int:
        """STT-final -> the patient hears something (first token, or canned reply)."""
        for stage in ("llm_first_token", "canned_response", "end"):
            if stage in self.marks:
                return self.marks[stage]
        return 0

    def breakdown(self) -> dict[str, int]:
        """Cumulative ms-from-start per stage, in canonical order."""
        return {s: self.marks[s] for s in self.STAGES if s in self.marks}


def percentile(values: list[float], p: float) -> float:
    """Linear-interpolated percentile (p in [0, 1]). 0.0 for empty input."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return s[int(k)]
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


class LatencyStats:
    """Rolling response-latency samples with p50/p95 snapshots."""

    def __init__(self, log_every: int = 1) -> None:
        self._samples: list[int] = []
        self._log_every = log_every

    def add(self, response_ms: int) -> None:
        self._samples.append(response_ms)

    def should_log(self) -> bool:
        return self._log_every > 0 and len(self._samples) % self._log_every == 0

    def snapshot(self) -> dict[str, float]:
        return {
            "n": len(self._samples),
            "p50_ms": round(percentile(self._samples, 0.50), 1),
            "p95_ms": round(percentile(self._samples, 0.95), 1),
            "max_ms": max(self._samples) if self._samples else 0,
        }
