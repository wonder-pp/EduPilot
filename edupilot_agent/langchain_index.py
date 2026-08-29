from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings


def chunk_to_document(chunk: Dict[str, Any]) -> Document:
    tags = chunk.get("tags", [])
    metadata = {
        "chunk_id": chunk.get("chunk_id", ""),
        "type": chunk.get("type", "advice"),
        "person_id": chunk.get("person_id", "unknown"),
        "major": chunk.get("major", ""),
        "target": chunk.get("target", ""),
        "stage": chunk.get("stage", ""),
        "topic": chunk.get("topic", ""),
        "tags": tags,
        "time_range": chunk.get("time_range", ""),
        "reason": chunk.get("reason", ""),
        "tradeoff": chunk.get("tradeoff", ""),
        "lesson": chunk.get("lesson", ""),
        "province": chunk.get("province", ""),
        "hometown_province": chunk.get("hometown_province", ""),
        "content": chunk.get("content", ""),
    }
    lines = [
        f"类型: {metadata['type']}",
        f"人物: {metadata['person_id']}",
        f"专业: {metadata['major']}",
        f"目标: {metadata['target']}",
        f"阶段: {metadata['stage']}",
        f"主题: {metadata['topic']}",
        f"标签: {', '.join(tags) if isinstance(tags, list) else tags}",
    ]
    if chunk.get("province"):
        lines.append(f"工作省份: {chunk['province']}")
    if chunk.get("hometown_province"):
        lines.append(f"家乡省份: {chunk['hometown_province']}")
    lines.append(f"内容: {chunk.get('content', '')}")
    if metadata["reason"]:
        lines.append(f"原因: {metadata['reason']}")
    if metadata["tradeoff"]:
        lines.append(f"取舍: {metadata['tradeoff']}")
    if metadata["lesson"]:
        lines.append(f"复盘: {metadata['lesson']}")
    return Document(page_content="\n".join(lines), metadata=metadata)


def load_chunk_documents(kb_path: str | Path) -> List[Document]:
    path = Path(kb_path)
    chunks = json.loads(path.read_text(encoding="utf-8"))
    return [chunk_to_document(chunk) for chunk in chunks]


def load_all_chunk_documents(kb_paths: List[str | Path]) -> List[Document]:
    """加载多个数据源并合并"""
    all_docs = []
    for kb_path in kb_paths:
        p = Path(kb_path)
        if p.exists():
            docs = load_chunk_documents(p)
            all_docs.extend(docs)
            print(f"  Loaded {len(docs)} chunks from {p.name}")
    return all_docs


def build_embeddings(model: str | None = None, base_url: str | None = None) -> OpenAIEmbeddings:
    load_dotenv()
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    api_key = os.getenv("EMBEDDING_API_KEY") or dashscope_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Missing embedding API key. Set DASHSCOPE_API_KEY or EMBEDDING_API_KEY.")

    resolved_base_url = (
        base_url
        or os.getenv("EMBEDDING_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or ("https://dashscope.aliyuncs.com/compatible-mode/v1" if dashscope_key else None)
    )
    return OpenAIEmbeddings(
        model=model or os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
        api_key=api_key,
        base_url=resolved_base_url,
        chunk_size=10,
        tiktoken_enabled=False,
        check_embedding_ctx_length=False,
    )


def build_vector_store(
    kb_path: str | Path,
    persist_dir: str | Path,
    embedding_model: str | None = None,
    base_url: str | None = None,
) -> None:
    # 支持多个数据源（逗号分隔）
    if "," in str(kb_path):
        kb_paths = [p.strip() for p in str(kb_path).split(",")]
        documents = load_all_chunk_documents(kb_paths)
    else:
        documents = load_chunk_documents(kb_path)
    embeddings = build_embeddings(model=embedding_model, base_url=base_url)
    vector_store = FAISS.from_documents(documents, embeddings)
    vector_store.save_local(str(persist_dir))
    print(f"Built LangChain FAISS vector store with {len(documents)} documents at {persist_dir}")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Build official LangChain FAISS index from EduPilot chunks.")
    parser.add_argument("--kb", default="edupilot_agent/data/interview_chunks.json", help="Chunks JSON path")
    parser.add_argument("--persist-dir", default="edupilot_agent/data/langchain_faiss", help="FAISS output dir")
    parser.add_argument("--embedding-model", default=None, help="Embedding model name")
    parser.add_argument("--base-url", default=None, help="OpenAI-compatible embedding base_url")
    args = parser.parse_args()

    build_vector_store(
        kb_path=args.kb,
        persist_dir=args.persist_dir,
        embedding_model=args.embedding_model,
        base_url=args.base_url,
    )


if __name__ == "__main__":
    main()
