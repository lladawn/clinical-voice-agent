"""LiveKit agent entrypoint.

Run the worker with:
    python -m agent.main dev        # local dev (hot reload)
    python -m agent.main start      # production

The worker connects to the LiveKit room, spins up the ClinicalAgent ("Aria"),
greets the patient, and runs the compliance voice pipeline defined in
pipeline.py. Every turn is audited via audit.py.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from livekit.agents import JobContext, WorkerOptions, cli

from .audit import AuditLogger
from .pipeline import PI_PATH, ClinicalAgent, build_session
from .rag import PIRetriever
from .semantic_guardrail import build_semantic_guardrail

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")

# Built once per worker process and reused across jobs.
_retriever = PIRetriever(PI_PATH)
_audit = AuditLogger()
_semantic = build_semantic_guardrail()  # None unless SEMANTIC_GUARDRAIL=1
_grounded = os.getenv("GROUNDED_MODE", "").strip().lower() in ("1", "true", "yes")


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    logger.info("Agent connected to room %s", ctx.room.name)

    session = build_session()
    agent = ClinicalAgent(
        session_id=ctx.room.name,
        retriever=_retriever,
        audit=_audit,
        semantic=_semantic,
        grounded=_grounded,
    )

    await session.start(agent=agent, room=ctx.room)

    await session.say(
        "Hi, this is Aria, your Veralix patient support assistant. "
        "How can I help you today?"
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
