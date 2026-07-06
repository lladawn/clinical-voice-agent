"""Structured per-turn audit logging.

Every completed conversational turn produces an AuditRecord and is written to
Supabase (Postgres). This table is the artifact an MLR / regulatory reviewer
actually cares about: every patient utterance, what the guardrail decided, which
PI sections were used, the full agent response, the compliance tag, and latency.

Writes are async and best-effort — a logging failure must never break the voice
pipeline. If Supabase isn't configured, we fall back to stdout so the demo still
shows structured records.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger("audit")

TABLE_NAME = "audit_log"

# Hash chaining: the first record in a session links to this sentinel.
GENESIS_HASH = "0" * 64

# Integrity fields are excluded from the hashed payload (record_hash IS the hash;
# it can't hash itself). Everything else — including seq and prev_hash — is hashed.
_HASH_EXCLUDE = {"record_hash"}


@dataclass
class AuditRecord:
    session_id: str
    turn_id: str
    patient_utterance: str
    guardrail_result: str          # PASS / BLOCK / EMERGENCY
    pi_sections_used: list[str]
    agent_response: str            # full LLM response, pre-TTS (tag stripped)
    compliance_tag: str            # ON_LABEL | OFF_LABEL_REFUSED | EMERGENCY_ESCALATED | OUT_OF_SCOPE
    latency_ms: int                # headline: STT final -> first token / canned reply
    latency_breakdown: dict = field(default_factory=dict)  # cumulative ms per stage
    retrieved_spans: list = field(default_factory=list)    # PI span ids offered (grounded mode)
    cited_spans: list = field(default_factory=list)        # PI span ids the answer cited
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    # Tamper-evidence (assigned by AuditLogger at write time).
    seq: int = -1                  # per-session monotonic sequence, starting at 0
    prev_hash: str = ""            # record_hash of the previous record in the session
    record_hash: str = ""          # SHA-256 over the canonical payload below

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def compute_record_hash(record_dict: dict) -> str:
    """SHA-256 over a canonical (sorted-key) serialization of everything but the hash."""
    payload = {k: v for k, v in record_dict.items() if k not in _HASH_EXCLUDE}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class ChainVerification:
    ok: bool
    checked: int
    issues: list[str]


def verify_chain(records: list[dict]) -> ChainVerification:
    """Walk a single session's records (any order) and prove integrity.

    Detects: content tampering (recomputed hash != stored), deletion/reordering
    (broken prev_hash link or non-contiguous seq).
    """
    issues: list[str] = []
    ordered = sorted(records, key=lambda r: r.get("seq", -1))
    expected_prev = GENESIS_HASH

    for i, rec in enumerate(ordered):
        seq = rec.get("seq")
        if seq != i:
            issues.append(f"seq gap: expected {i}, found {seq} (deletion/reorder?)")
        recomputed = compute_record_hash(rec)
        if recomputed != rec.get("record_hash"):
            issues.append(f"seq {seq}: record_hash mismatch (content tampered)")
        if rec.get("prev_hash") != expected_prev:
            issues.append(f"seq {seq}: prev_hash does not link to previous record")
        expected_prev = rec.get("record_hash")

    return ChainVerification(ok=not issues, checked=len(ordered), issues=issues)


class AuditLogger:
    def __init__(self) -> None:
        self._client = self._init_supabase()
        # Per-session chain tip: session_id -> (last_seq, last_record_hash).
        self._chain: dict[str, tuple[int, str]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _init_supabase():
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        if not (url and key):
            logger.warning("Supabase not configured — audit records go to stdout only.")
            return None
        try:
            from supabase import create_client

            return create_client(url, key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to init Supabase (%s) — falling back to stdout.", exc)
            return None

    async def write(self, record: AuditRecord) -> None:
        """Seal the record into the session's hash chain, then persist."""
        # Sealing mutates chain state, so serialize it (turns are sequential per
        # session anyway, but the lock keeps the chain correct under any interleave).
        async with self._lock:
            self._seal(record)

        # Always emit to stdout so the demo is observable even without Supabase.
        logger.info("AUDIT %s", json.dumps(record.to_dict()))

        if self._client is None:
            return

        # supabase-py is sync; push the insert to a thread so we never block the
        # event loop / voice pipeline.
        try:
            await asyncio.to_thread(self._insert, record)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Audit write failed: %s", exc)

    def _seal(self, record: AuditRecord) -> None:
        """Assign seq + prev_hash + record_hash, linking into the session chain."""
        last_seq, last_hash = self._chain.get(record.session_id, (-1, GENESIS_HASH))
        record.seq = last_seq + 1
        record.prev_hash = last_hash
        record.record_hash = ""  # excluded from the hash anyway; keep explicit
        record.record_hash = compute_record_hash(record.to_dict())
        self._chain[record.session_id] = (record.seq, record.record_hash)

    def _insert(self, record: AuditRecord) -> None:
        self._client.table(TABLE_NAME).insert(record.to_dict()).execute()
