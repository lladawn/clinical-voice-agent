# Tamper-evident audit

## The problem

The audit log is the artifact an MLR/regulatory reviewer trusts to reconstruct a
conversation. But a plain insert proves nothing: a row could be edited, deleted,
or reordered after the fact and no one would know. For a regulated setting, the
log needs to be **tamper-evident** — any change must be detectable.

## The design: per-session hash chain

Each record carries three integrity fields (`agent/audit.py`):

- **`seq`** — a per-session monotonic sequence number starting at 0. Gaps reveal
  deletions or reordering.
- **`prev_hash`** — the `record_hash` of the previous record in the session. The
  first record links to a genesis sentinel (`"0"*64`).
- **`record_hash`** — `SHA-256` over a canonical (sorted-key) serialization of the
  record's content *plus* `seq` and `prev_hash`.

Because each hash commits to the previous one, the records form a chain: editing
any field changes that record's hash, which breaks the `prev_hash` link of every
record after it. You can't quietly change history without rewriting the whole
tail.

```
rec0: seq=0  prev=GENESIS      hash=H0=sha256(content0 + GENESIS)
rec1: seq=1  prev=H0           hash=H1=sha256(content1 + H0)
rec2: seq=2  prev=H1           hash=H2=sha256(content2 + H1)
              ▲ edit content1 → H1 changes → rec2.prev_hash no longer matches
```

## Where the chain state lives

The `AuditLogger` owns write ordering, so it owns the chain. It keeps a per-session
tip `(last_seq, last_hash)`, and `_seal()` assigns `seq`/`prev_hash`/`record_hash`
under an `asyncio.Lock` before persisting. The pipeline just builds the record;
sealing is centralized so it can't be gotten wrong per call site. A unique index
on `(session_id, seq)` (migration) rejects an injected duplicate seq at the DB.

## Verification

`verify_chain(records)` (`agent/audit.py`) walks a session's records ordered by
`seq` and recomputes each hash, asserting:
1. `seq` is contiguous from 0 (no gaps → no deletions/reorders),
2. the recomputed `record_hash` matches the stored one (no content tampering),
3. each `prev_hash` links to the previous record's `record_hash`.

`make eval-verify` proves it end-to-end, fully offline and deterministic:

```
Verifying tamper-evident audit chain (5 records)...
  [PASS] intact chain verifies          -> checked 5
  [PASS] detects content tampering       -> seq 2: record_hash mismatch (content tampered)
  [PASS] detects deletion                -> seq gap: expected 2, found 3 (deletion/reorder?)
Audit integrity: 3/3 (100.0%)
```

## Limits / production hardening

This detects tampering by anyone who can't recompute the whole chain — it's an
*integrity* proof, not an *authenticity* one. A party who can rewrite every
subsequent record could forge a consistent chain. To close that:

- **Sign the tip** — periodically sign the latest `record_hash` with a key the
  writer doesn't hold, or anchor it to an append-only external store (an object
  lock, a transparency log, or a notary). Then even a full rewrite is detectable.
- **Write-once storage** — enforce append-only at the database (no UPDATE/DELETE
  grants on `audit_log`).

The chain is the mechanism; external anchoring is what makes it trustworthy across
a trust boundary.
