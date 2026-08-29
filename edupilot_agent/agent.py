from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from edupilot_agent.information_fusion import InformationFusion
from edupilot_agent.llm_client import JsonLLMClient
from edupilot_agent.query_generator import QueryGenerator
from edupilot_agent.query_planner import QueryPlanner
from edupilot_agent.reasoner import ExperienceReasoner
from edupilot_agent.schemas import RetrievedChunk


class Retriever(Protocol):
    """Retriever interface expected by the EduPilot agent."""

    def retrieve(self, queries: List[str], top_k: int = 8) -> List[RetrievedChunk]:
        ...


class MentorExperienceAgent:
    """Main Agent pipeline: plan -> generate -> retrieve -> reason."""

    def __init__(
        self,
        kb_path: str | None = None,
        retriever: Retriever | None = None,
        llm: JsonLLMClient | None = None,
    ):
        self.llm = llm or JsonLLMClient(enabled=False)
        self.query_planner = QueryPlanner(llm=self.llm)
        self.query_generator = QueryGenerator()
        if retriever is None:
            raise ValueError("A retriever must be provided. Use an official LangChain retriever adapter here.")
        self.retriever = retriever
        self.fusion = InformationFusion()
        self.reasoner = ExperienceReasoner(llm=self.llm)

    def run(self, user_input: str, top_k: int = 6, user_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        structured_query = self.query_planner.plan(user_input)

        # 个人资料模块已移除，user_profile 不再注入到 structured_query 中
        # user_profile 仅传给 retriever 做加权排序和 views.py 做卡片匹配度计算
        # reasoner 只能看到用户在问题中明确提及的信息
        
        query_bundle = self.query_generator.generate(structured_query)
        retrieved_chunks = self.retriever.retrieve(query_bundle.all_queries(), top_k=top_k,
                                                    user_profile=user_profile)
        fused_evidence = self.fusion.fuse(retrieved_chunks)
        response = self.reasoner.reason_with_fusion(structured_query, fused_evidence, retrieved_chunks)

        return {
            "user_input": user_input,
            "llm_status": self.llm.status(),
            "structured_query": structured_query.to_dict(),
            "retrieval_queries": query_bundle.all_queries(),
            "retrieved_chunks": [item.to_dict() for item in retrieved_chunks],
            "fused_evidence": fused_evidence.to_dict(),
            "final_answer": response.to_dict(),
        }
