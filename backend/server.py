"""Thin FastAPI backend.

Two responsibilities:
  1. POST /token  — mint a LiveKit access token so the browser can join a room.
  2. GET  /audit-log — serve the structured audit records for the right-hand
     panel of the UI (polled every ~2s by the frontend).

Run with:
    uvicorn backend.server:app --reload --port 8000
"""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api
from postgrest.exceptions import APIError
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Synthio Clinical Voice Agent — Backend")

# Permissive CORS for the local Next.js dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")

TABLE_NAME = "audit_log"


class TokenResponse(BaseModel):
    token: str
    url: str
    room: str
    identity: str


def _supabase():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return None
    from supabase import create_client

    return create_client(url, key)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/token", response_model=TokenResponse)
def create_token(room: str | None = None) -> TokenResponse:
    """Mint a LiveKit join token for the patient (browser) participant."""
    if not (LIVEKIT_API_KEY and LIVEKIT_API_SECRET and LIVEKIT_URL):
        raise HTTPException(500, "LiveKit credentials not configured")

    room_name = room or f"veralix-{uuid.uuid4().hex[:8]}"
    identity = f"patient-{uuid.uuid4().hex[:6]}"

    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("Patient")
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    return TokenResponse(token=token, url=LIVEKIT_URL, room=room_name, identity=identity)


@app.get("/audit-log")
def audit_log(session_id: str | None = None, limit: int = 50) -> dict:
    """Return recent audit records (optionally filtered to one session)."""
    client = _supabase()
    if client is None:
        # Supabase not configured — return empty so the UI degrades gracefully.
        return {"records": [], "source": "unconfigured"}

    query = client.table(TABLE_NAME).select("*").order("timestamp", desc=True).limit(limit)
    if session_id:
        query = query.eq("session_id", session_id)
    try:
        resp = query.execute()
    except APIError as exc:
        # Most common cause: the audit_log table hasn't been created yet.
        # Degrade gracefully so the UI keeps polling instead of erroring.
        if exc.code == "PGRST205":
            return {
                "records": [],
                "source": "table_missing",
                "hint": "Run data/schema.sql in the Supabase SQL editor to create the audit_log table.",
            }
        raise
    return {"records": resp.data or [], "source": "supabase"}
