from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from edupilot_agent.schemas import FusedEvidence, RetrievedChunk


class InformationFusion:
    """Turn retrieved chunks into compact evidence groups for final reasoning."""

    def fuse(self, chunks: List[RetrievedChunk]) -> FusedEvidence:
        grouped: Dict[str, List[RetrievedChunk]] = defaultdict(list)
        for chunk in chunks:
            grouped[chunk.type].append(chunk)

        profile = self._summaries(grouped.get("profile", []), limit=3)
        timeline = self._summaries(grouped.get("timeline", []), limit=4)
        decisions = self._summaries(grouped.get("decision", []), limit=4)
        advice = self._summaries(grouped.get("advice", []), limit=5)
        methods = self._summaries(grouped.get("method", []), limit=4)
        reflections = self._summaries(grouped.get("reflection", []), limit=3)

        return FusedEvidence(
            profile=profile,
            timeline=timeline,
            decisions=decisions,
            advice=advice,
            methods=methods,
            reflections=reflections,
            raw_evidence=[chunk.to_dict() for chunk in chunks],
        )

    def _summaries(self, chunks: List[RetrievedChunk], limit: int) -> List[str]:
        summaries: List[str] = []
        seen = set()
        for chunk in sorted(chunks, key=lambda item: item.score, reverse=True):
            content = chunk.content
            text = str(content.get("content", "")).strip()
            topic = str(content.get("topic", "")).strip()
            if not text:
                continue
            summary = f"{topic}：{text}" if topic else text
            if summary in seen:
                continue
            seen.add(summary)
            summaries.append(summary)
            if len(summaries) >= limit:
                break
        return summaries

