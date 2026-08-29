from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List


@dataclass
class StructuredQuery:
    who: str
    what: str
    stage: str
    goal: str = ""
    question_type: str = "how"
    user_profile: Dict[str, Any] = field(default_factory=dict)
    sub_questions: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalQueryBundle:
    who_query: str
    what_query: str
    stage_query: str
    fused_queries: List[str]

    def all_queries(self) -> List[str]:
        ordered = [self.who_query, self.what_query, self.stage_query, *self.fused_queries]
        seen = set()
        result: List[str] = []
        for item in ordered:
            text = item.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result


@dataclass
class RetrievedChunk:
    chunk_id: str
    type: str
    person_id: str
    content: Dict[str, Any]
    score: float
    matched_query: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class FusedEvidence:
    profile: List[str] = field(default_factory=list)
    timeline: List[str] = field(default_factory=list)
    decisions: List[str] = field(default_factory=list)
    advice: List[str] = field(default_factory=list)
    methods: List[str] = field(default_factory=list)
    reflections: List[str] = field(default_factory=list)
    raw_evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    analysis: str
    decision: str
    action_plan: List[str]
    reason: str
    evidence: List[Dict[str, Any]]
    caveats: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

