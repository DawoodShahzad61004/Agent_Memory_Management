"""Pydantic schemas for every memory type, plus the shared store-managed base.

Chroma metadata values must be scalars; the list fields below are flattened by
the store layer (chroma_store._encode), never at call sites.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Track = Literal["documents", "learned_qa"]
EvidenceType = Literal["animal_model", "observational", "rct", "meta_analysis", "unspecified"]
Verdict = Literal["DUPLICATE", "CONTRADICTS", "REFINES", "UNRELATED"]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryBase(BaseModel):
    """Fields the store manages. The LLM never sets these."""

    hit_count: int = 0
    last_hit_at: str = ""
    active: bool = True
    superseded_by: str | None = None
    contradiction_strikes: int = 0
    memory_type: str = "episodic"
    created_at: str = Field(default_factory=utcnow)

    def to_text(self) -> str:  # pragma: no cover - overridden by every subclass
        raise NotImplementedError

    def to_value(self) -> dict:
        value = self.model_dump()
        value["text"] = self.to_text()
        return value


class EpisodicMemory(MemoryBase):
    """A lesson distilled from a successful interaction."""

    question: str
    answer: str
    track: Track = "learned_qa"
    evidence_type: EvidenceType = "unspecified"
    source_paths: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    memory_type: str = "episodic"

    def to_text(self) -> str:
        return f"Q: {self.question}\nA: {self.answer}"


class FailureMemory(MemoryBase):
    """A consolidated thumbdown. `missing_information`, not the raw feedback,
    is what feeds prompt injection — raw feedback is the wrong shape for
    redirecting retrieval."""

    original_query: str
    bad_answer: str = ""
    user_feedback: str = ""
    missing_information: str
    failed_variants: list[str] = Field(default_factory=list)
    memory_type: str = "episodic_negative"

    def to_text(self) -> str:
        return f"Failed query: {self.original_query}\nMissing: {self.missing_information}"


class SemanticFact(MemoryBase):
    """A domain fact or disambiguation rule (e.g. an acronym with two meanings)."""

    subject: str
    fact: str
    disambiguates: list[str] | None = None
    memory_type: str = "semantic"

    def to_text(self) -> str:
        return f"{self.subject}: {self.fact}"


class PromptRevision(MemoryBase):
    """A proposed prompt revision. Stored, never auto-applied."""

    target_prompt: str
    proposed_text: str
    rationale: str = ""
    approved: bool = False
    memory_type: str = "procedural"

    def to_text(self) -> str:
        return f"Revision for {self.target_prompt}: {self.proposed_text}"


class ClassificationVerdict(BaseModel):
    verdict: Verdict


SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {
    "EpisodicMemory": EpisodicMemory,
    "FailureMemory": FailureMemory,
    "SemanticFact": SemanticFact,
    "PromptRevision": PromptRevision,
    "ClassificationVerdict": ClassificationVerdict,
}
