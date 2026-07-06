"""Lightweight RAG over the mock prescribing information (PI) document.

For the demo we keep this deliberately simple: chunk the PI by section heading,
then score sections against the patient utterance with TF-IDF-style keyword
overlap. No vector DB, no embeddings — fast and good enough to make retrieval
look credible. The top-N sections are injected into the LLM context as
[PI REFERENCE] blocks.

In production you'd swap `PIRetriever` for pgvector + Supabase embeddings; the
interface (`retrieve` -> list of (section_title, text)) stays the same.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_SECTION_RE = re.compile(r"^---\s*(.+?)\s*---$", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z0-9]+")

# Common words that carry no retrieval signal.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are",
    "be", "with", "do", "does", "i", "you", "my", "me", "it", "this", "that",
    "what", "how", "when", "should", "can", "if", "have", "has", "about", "at",
}


def _tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class Section:
    title: str
    text: str
    tokens: Counter  # term frequencies within this section


@dataclass
class Span:
    """A citable unit — one sentence of the PI, with a stable id like 'S1'."""
    id: str
    section: str
    text: str
    tokens: Counter


class PIRetriever:
    def __init__(self, pi_path: str | Path):
        raw = Path(pi_path).read_text(encoding="utf-8")
        self.sections = self._chunk(raw)
        self._idf = self._compute_idf(self.sections)
        # Span-level index for citation-grounded retrieval.
        self.spans = self._chunk_spans(self.sections)
        self._span_idf = self._compute_span_idf(self.spans)
        self._span_by_id = {s.id: s for s in self.spans}

    @staticmethod
    def _chunk(raw: str) -> list[Section]:
        """Split the PI into sections keyed by '--- HEADING ---' markers."""
        matches = list(_SECTION_RE.finditer(raw))
        sections: list[Section] = []
        for i, m in enumerate(matches):
            title = m.group(1).title()
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
            body = raw[start:end].strip()
            if body:
                sections.append(Section(title, body, Counter(_tokenize(body))))
        return sections

    @staticmethod
    def _compute_idf(sections: list[Section]) -> dict[str, float]:
        n = len(sections)
        df: Counter = Counter()
        for s in sections:
            for term in s.tokens:
                df[term] += 1
        return {term: math.log((1 + n) / (1 + d)) + 1 for term, d in df.items()}

    def retrieve(self, query: str, top_k: int = 2) -> list[tuple[str, str]]:
        """Return the top_k (section_title, section_text) pairs for a query."""
        q_terms = _tokenize(query)
        if not q_terms:
            return []

        scored: list[tuple[float, Section]] = []
        for s in self.sections:
            score = sum(s.tokens.get(t, 0) * self._idf.get(t, 0.0) for t in q_terms)
            if score > 0:
                scored.append((score, s))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [(s.title, s.text) for _, s in scored[:top_k]]

    @staticmethod
    def format_context(sections: list[tuple[str, str]]) -> str:
        """Render retrieved sections as the [PI REFERENCE] block for the LLM."""
        if not sections:
            return ""
        blocks = [f"[PI REFERENCE — {title}]:\n{text}" for title, text in sections]
        return "\n\n".join(blocks)

    # ----------------------------------------------------------------- #
    # Span-level (citation-grounded) retrieval
    # ----------------------------------------------------------------- #
    @staticmethod
    def _chunk_spans(sections: list[Section]) -> list[Span]:
        """Split each section into sentence-level, citable spans."""
        spans: list[Span] = []
        n = 0
        for sec in sections:
            for sent in _SENTENCE_SPLIT.split(sec.text):
                sent = sent.strip()
                if len(sent) < 15:  # skip fragments / headers
                    continue
                n += 1
                spans.append(Span(f"S{n}", sec.title, sent, Counter(_tokenize(sent))))
        return spans

    @staticmethod
    def _compute_span_idf(spans: list[Span]) -> dict[str, float]:
        n = len(spans)
        df: Counter = Counter()
        for s in spans:
            for term in s.tokens:
                df[term] += 1
        return {term: math.log((1 + n) / (1 + d)) + 1 for term, d in df.items()}

    def retrieve_spans(self, query: str, top_k: int = 4) -> list[Span]:
        """Return the top_k most relevant citable spans for a query."""
        q_terms = _tokenize(query)
        if not q_terms:
            return []
        scored: list[tuple[float, Span]] = []
        for s in self.spans:
            score = sum(s.tokens.get(t, 0) * self._span_idf.get(t, 0.0) for t in q_terms)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:top_k]]

    def span_text(self, span_id: str) -> str | None:
        """Look up a span's text by id (for auditor verification)."""
        s = self._span_by_id.get(span_id)
        return s.text if s else None

    @staticmethod
    def format_spans(spans: list[Span]) -> str:
        """Render spans as a citable [PI SPANS] block for the grounded prompt."""
        if not spans:
            return ""
        lines = [f"[{s.id}] ({s.section}) {s.text}" for s in spans]
        return "[PI SPANS — cite these by id]\n" + "\n".join(lines)
