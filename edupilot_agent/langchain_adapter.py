from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from edupilot_agent.langchain_index import build_embeddings
from edupilot_agent.schemas import RetrievedChunk


class LangChainRetrieverAdapter:
    """Adapter from an official LangChain retriever to EduPilot RetrievedChunk."""

    def __init__(self, retriever=None, vector_store=None):
        self.retriever = retriever
        # 保留 vector_store 引用以支持 similarity_search_with_score 拿真实距离
        self.vector_store = vector_store

    def retrieve(self, queries: List[str], top_k: int = 8,
                 user_profile: dict | None = None) -> List[RetrievedChunk]:
        """检索支持三种数据源加权和条件匹配加分。

        user_profile: 可选，如 {"major": "数据科学与大数据技术", "stage": "2024级",
                        "hometown_province": "河南省", "target": "保研"}
        """
        merged: Dict[str, RetrievedChunk] = {}
        for query in queries:
            # 扩大原始检索范围，加权排序后再截断
            fetch_k = max(top_k * 4, 16)
            if self.vector_store is not None:
                docs_with_scores = self.vector_store.similarity_search_with_score(query, k=fetch_k)
                for doc, distance in docs_with_scores:
                    base_similarity = 1.0 / (1.0 + float(distance))
                    weighted = self._apply_weighting(doc, base_similarity, user_profile, query)
                    item = self._to_retrieved_chunk(
                        doc, query=query, rank=0, top_k=fetch_k, score=weighted
                    )
                    existing = merged.get(item.chunk_id)
                    if existing is None or item.score > existing.score:
                        merged[item.chunk_id] = item
            else:
                docs = self.retriever.invoke(query)
                for rank, doc in enumerate(docs[:fetch_k]):
                    base_score = float(fetch_k - rank) / float(fetch_k)
                    weighted = self._apply_weighting(doc, base_score, user_profile, query)
                    item = self._to_retrieved_chunk(
                        doc, query=query, rank=rank, top_k=fetch_k, score=weighted
                    )
                    existing = merged.get(item.chunk_id)
                    if existing is None or item.score > existing.score:
                        merged[item.chunk_id] = item
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:top_k]

    def _apply_weighting(self, doc: Document, base_score: float,
                         user_profile: dict | None, query: str) -> float:
        """三种数据源加权 + 条件匹配加分。"""
        metadata = doc.metadata or {}
        chunk_type = str(metadata.get("type", ""))
        data_source = str(metadata.get("data_source", ""))
        content_text = str(metadata.get("content", "")) + doc.page_content

        # --- 1. 判断所属数据源类别并乘基础权重 ---
        # 深度访谈: 0.5 (优先级最高)
        # 公众号访谈: 0.3
        # 年级普查: 0.2
        # 老数据(interview_chunks/employment): 过渡为"0.4 深度访谈类"
        if data_source == "deep_interview" or chunk_type == "employment":
            src_weight = 0.5
            src_cat = "deep"
        elif chunk_type == "public_interview":
            src_weight = 0.3
            src_cat = "public"
        elif chunk_type == "census":
            src_weight = 0.2
            src_cat = "census"
        else:
            # 老 interview_chunks 里的 profile/timeline 视同深度访谈，advice 类视同公众号
            if chunk_type in ("profile", "timeline", "decision"):
                src_weight = 0.5
                src_cat = "deep"
            else:
                src_weight = 0.4  # advice/reflection/method 介于深度和公众号之间
                src_cat = "public"

        weighted = base_score * src_weight

        # --- 2. 条件匹配加分（同一类别中，字段命中越多分越高）---
        up = user_profile or {}
        match_bonus = 0.0
        max_bonus = 0.2  # 加分上限 0.2，避免超过 1.0

        def _field_match(key: str, md_key: str | None = None) -> bool:
            v = up.get(key, "")
            if not v:
                return False
            md_key = md_key or key
            md_v = str(metadata.get(md_key, ""))
            return bool(md_v) and v[:2] in md_v  # 前两字命中即可（省/专业都够用）

        # 专业 +0.06
        if _field_match("major"):
            match_bonus += 0.06
        # 家乡省份 +0.05
        if _field_match("hometown_province") or _field_match("province", "province"):
            match_bonus += 0.05
        # 去向类型(保研/就业/考研) +0.05
        if up.get("target") or up.get("future_path"):
            goal = (up.get("target") or up.get("future_path") or "")
            # 在 content_text / tags / topic 中搜索
            if goal and goal[:2] and (
                goal[:2] in content_text or
                goal[:2] in str(metadata.get("topic", "")) or
                goal[:2] in str(metadata.get("future_path", ""))
            ):
                match_bonus += 0.05
        # 年级(同届) +0.04
        if up.get("stage") and str(metadata.get("stage", "")):
            # 普查数据永远是最新届，depth访谈是往届。
            # 如果用户是大三，对保研问题来说往届(2019-2022)更有参考价值，反而加分
            user_stage = up["stage"]
            md_stage = str(metadata["stage"])
            if src_cat == "census" and md_stage == user_stage:
                match_bonus += 0.04
            elif src_cat in ("deep", "public") and md_stage != user_stage:
                match_bonus += 0.03  # 往届学长学姐对当前届更有参考

        match_bonus = min(match_bonus, max_bonus)
        weighted += match_bonus

        # --- 3. 归一化：最终分数保持在 [0,1] ---
        # src_weight 最大值 0.5 + bonus 0.2 = 0.7；再乘一个放大系数让语义分更有区分度
        weighted = weighted / 0.7
        weighted = max(0.0, min(1.0, weighted))

        return weighted

    def _to_retrieved_chunk(
        self, doc: Document, query: str, rank: int, top_k: int, score: float | None = None
    ) -> RetrievedChunk:
        metadata = dict(doc.metadata)
        content = {
            **metadata,
            "content": self._extract_content(doc.page_content),
        }
        # score 为真实相似度；若未提供则用排名估算（回退场景）
        final_score = score if score is not None else float(top_k - rank) / float(top_k)
        return RetrievedChunk(
            chunk_id=str(metadata.get("chunk_id", "")),
            type=str(metadata.get("type", "advice")),
            person_id=str(metadata.get("person_id", "unknown")),
            content=content,
            score=final_score,
            matched_query=query,
        )

    def _extract_content(self, page_content: str) -> str:
        for line in page_content.splitlines():
            if line.startswith("内容:"):
                return line.split(":", 1)[1].strip()
        return page_content


def load_faiss_retriever(
    persist_dir: str | Path,
    embedding_model: str | None = None,
    base_url: str | None = None,
    k: int = 8,
    fetch_k: int = 30,
):
    embeddings = build_embeddings(model=embedding_model, base_url=base_url)
    # 使用正斜杠路径以兼容 Windows 和 FAISS
    persist_dir_str = str(persist_dir).replace("\\", "/")
    vector_store = FAISS.load_local(
        persist_dir_str,
        embeddings,
        allow_dangerous_deserialization=True,
    )
    # 同时返回 retriever 和 vector_store，adapter 优先用 vector_store 拿真实分数
    retriever = vector_store.as_retriever(
        search_type="mmr",
        search_kwargs={"k": k, "fetch_k": fetch_k},
    )
    return LangChainRetrieverAdapter(retriever=retriever, vector_store=vector_store)
