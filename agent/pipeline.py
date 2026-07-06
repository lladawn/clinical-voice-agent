"""The voice pipeline: STT -> guardrail -> (RAG + Claude) -> tag strip -> TTS -> audit.

Built on LiveKit Agents (v1.x). The AgentSession wires together VAD, Deepgram
STT, the Claude LLM, and Cartesia TTS. `ClinicalAgent` layers the compliance
behaviour on top via two hooks:

  * on_user_turn_completed — runs the fast guardrail and injects RAG context
    BEFORE the LLM sees the turn. Emergencies / blocks short-circuit to a canned
    compliant response (no LLM tokens spent).

  * llm_node — wraps the model output to (a) strip the internal [COMPLIANCE: ...]
    tag before it reaches TTS, and (b) capture the tag + full response + latency
    for the per-turn audit record.

Flow:
    Mic (PCM 16kHz) -> LiveKit room (WebRTC)
      -> Deepgram Nova-3 Medical (streaming STT)
        -> guardrail check
          -> PASS:  Claude (claude-sonnet-4-6) + RAG context
          -> BLOCK/EMERGENCY: canned compliant response
        -> strip compliance tag
        -> TTS -> room -> patient speaker
        -> async audit log write
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterable
from pathlib import Path

from livekit.agents import Agent, AgentSession, ChatContext, ChatMessage, llm
from livekit.agents.voice import ModelSettings
from livekit.plugins import anthropic, cartesia, deepgram, silero

from . import guardrails
from .audit import AuditLogger, AuditRecord
from .latency import LatencyStats, TurnLatency
from .prompts import (
    _TAG_OPEN,
    GROUNDED_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    ComplianceTagFilter,
)
from .rag import PIRetriever
from .semantic_guardrail import SemanticGuardrail

logger = logging.getLogger("pipeline")

# Shared across turns/agents in a worker process — session-level p50/p95.
_LATENCY_STATS = LatencyStats(log_every=1)


def _text_chunk(text: str) -> llm.ChatChunk:
    """Build a plain assistant text chunk for the llm_node output stream."""
    return llm.ChatChunk(
        id=str(uuid.uuid4()),
        delta=llm.ChoiceDelta(role="assistant", content=text),
    )

# Pin the LLM here. claude-sonnet-4-6 keeps latency low for real-time voice.
# Swap to "claude-opus-4-8" if you want maximum compliance accuracy at higher cost.
LLM_MODEL = "claude-sonnet-4-6"

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PI_PATH = DATA_DIR / "mock_pi.txt"


class ClinicalAgent(Agent):
    def __init__(
        self,
        session_id: str,
        retriever: PIRetriever,
        audit: AuditLogger,
        semantic: "SemanticGuardrail | None" = None,
        grounded: bool = False,
    ):
        # Grounded mode swaps in the citation-forced prompt (GROUNDED_MODE=1).
        super().__init__(
            instructions=GROUNDED_SYSTEM_PROMPT if grounded else SYSTEM_PROMPT
        )
        self._session_id = session_id
        self._retriever = retriever
        self._audit = audit
        self._semantic = semantic  # Layer 1 classifier, or None (regex-only)
        self._grounded = grounded
        # Per-turn state shared between the user-turn hook and llm_node.
        self._turn_utterance = ""
        self._turn_guardrail = "PASS"
        self._turn_pi_sections: list[str] = []
        self._turn_retrieved_spans: list[str] = []
        self._turn_cited_spans: list[str] = []
        self._lat = TurnLatency()
        self._stats = _LATENCY_STATS
        # Semantic Layer 1 runs concurrently with the LLM; llm_node awaits it
        # before emitting the first token. None when regex-only.
        self._semantic_task: asyncio.Task[str] | None = None

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        """Runs after STT finalizes a turn, before the LLM is invoked."""
        utterance = new_message.text_content or ""
        self._turn_utterance = utterance
        self._turn_retrieved_spans = []
        self._turn_cited_spans = []
        self._lat = TurnLatency()  # t0 = STT final

        # Layer 0: fast regex detector (always on, ~microseconds).
        result = guardrails.check(utterance)
        self._turn_guardrail = result
        self._lat.mark("guardrail")

        if result in guardrails.CANNED_RESPONSES:
            # Regex caught it — speak the pre-approved line, skip the LLM entirely.
            text, tag = guardrails.CANNED_RESPONSES[result]
            self._turn_pi_sections = []
            self._lat.mark("canned_response")
            await self.session.say(text)
            await self._write_audit(agent_response=text, compliance_tag=tag)
            # StopResponse tells the framework not to call the LLM for this turn.
            from livekit.agents import StopResponse

            raise StopResponse()

        # Layer 1: launch the semantic classifier CONCURRENTLY — do not await it
        # here. It runs alongside the LLM; llm_node gates the first token on its
        # verdict, so its ~1.4s cost overlaps the LLM's ~1.5s time-to-first-token
        # instead of stacking in front of it. Safety is preserved: no token
        # reaches TTS until the verdict is in.
        self._semantic_task = None
        if self._semantic is not None and guardrails.should_run_semantic(utterance):
            self._semantic_task = asyncio.create_task(
                self._semantic.classify(utterance)
            )

        # PASS: retrieve PI context and inject into the *user* turn (not as a
        # trailing assistant message — that becomes a prefill, which the
        # claude-sonnet-4-6 / 4.x family rejects with a 400).
        if self._grounded:
            # Span-level: citable sentences the answer must ground its claims in.
            spans = self._retriever.retrieve_spans(utterance, top_k=4)
            self._turn_retrieved_spans = [s.id for s in spans]
            self._turn_pi_sections = sorted({s.section for s in spans})
            context = self._retriever.format_spans(spans)
        else:
            sections = self._retriever.retrieve(utterance, top_k=2)
            self._turn_pi_sections = [title for title, _ in sections]
            context = self._retriever.format_context(sections)
        if context:
            new_message.content.append(f"\n\n{context}")
        self._lat.mark("rag")

    async def llm_node(
        self,
        chat_ctx: ChatContext,
        tools: list,
        model_settings: ModelSettings,
    ) -> AsyncIterable[llm.ChatChunk]:
        """Wrap the default LLM stream: strip the compliance tag, capture for audit.

        The concurrent semantic guardrail is resolved here, before ANY token is
        emitted. If it flags EMERGENCY/BLOCK, the in-flight LLM output is
        discarded and the canned compliant line is spoken instead.
        """
        flt = ComplianceTagFilter(strip_citations=self._grounded)
        safety_checked = False

        async for chunk in Agent.default.llm_node(
            self, chat_ctx, tools, model_settings
        ):
            # Gate: resolve the concurrent safety verdict before emitting anything.
            if not safety_checked:
                verdict = await self._resolve_semantic()
                safety_checked = True
                if verdict in guardrails.CANNED_RESPONSES:
                    text, tag = guardrails.CANNED_RESPONSES[verdict]
                    self._turn_guardrail = verdict
                    self._turn_pi_sections = []
                    self._lat.mark("canned_response")
                    yield _text_chunk(text)
                    await self._write_audit(agent_response=text, compliance_tag=tag)
                    return  # discard the (unsafe) LLM output for this turn

            delta = chunk.delta.content if chunk.delta else None
            if not delta:
                yield chunk
                continue
            visible = flt.feed(delta)
            if visible:
                if "llm_first_token" not in self._lat.marks:
                    self._lat.mark("llm_first_token")  # patient starts hearing a reply
                chunk.delta.content = visible
                yield chunk
            # else: held back (potential tag) — drop this chunk's text

        # Safety net: if the LLM produced no chunks, the gate above never ran —
        # resolve the verdict now so an emergency still escalates.
        if not safety_checked:
            verdict = await self._resolve_semantic()
            if verdict in guardrails.CANNED_RESPONSES:
                text, tag = guardrails.CANNED_RESPONSES[verdict]
                self._turn_guardrail = verdict
                self._turn_pi_sections = []
                self._lat.mark("canned_response")
                yield _text_chunk(text)
                await self._write_audit(agent_response=text, compliance_tag=tag)
                return

        tail = flt.flush()
        if tail:
            yield _text_chunk(tail)

        # Turn complete — write the audit record.
        clean = (flt.raw.split(_TAG_OPEN)[0]).strip()
        self._turn_cited_spans = flt.cited_spans()
        await self._write_audit(
            agent_response=clean,
            compliance_tag=flt.compliance_tag(),
        )

    async def _resolve_semantic(self) -> str:
        """Await the concurrent Layer-1 verdict (or PASS if none / on failure)."""
        if self._semantic_task is None:
            return "PASS"
        try:
            return await self._semantic_task
        except Exception:  # classifier already fails open, but be defensive
            return "PASS"

    async def _write_audit(self, agent_response: str, compliance_tag: str) -> None:
        self._lat.mark("end")
        response_ms = self._lat.response_ms()

        # Roll into session p50/p95 and log the tail periodically.
        self._stats.add(response_ms)
        if self._stats.should_log():
            snap = self._stats.snapshot()
            logger.info(
                "LATENCY response=%dms | p50=%.0fms p95=%.0fms max=%dms (n=%d)",
                response_ms, snap["p50_ms"], snap["p95_ms"], snap["max_ms"], snap["n"],
            )

        record = AuditRecord(
            session_id=self._session_id,
            turn_id=str(uuid.uuid4()),
            patient_utterance=self._turn_utterance,
            guardrail_result=self._turn_guardrail,
            pi_sections_used=self._turn_pi_sections,
            agent_response=agent_response,
            compliance_tag=compliance_tag,
            latency_ms=response_ms,
            latency_breakdown=self._lat.breakdown(),
            retrieved_spans=self._turn_retrieved_spans,
            cited_spans=self._turn_cited_spans,
        )
        await self._audit.write(record)


def build_session() -> AgentSession:
    """Construct the AgentSession with the full STT/LLM/TTS/VAD stack."""
    return AgentSession(
        vad=silero.VAD.load(),
        stt=deepgram.STT(
            model="nova-3-medical",
            language="en-US",
            interim_results=True,   # stream interims for low latency
            punctuate=True,
        ),
        llm=anthropic.LLM(model=LLM_MODEL),
        tts=cartesia.TTS(),
    )
