import hashlib
import json
import os
import re
from threading import Lock
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import UUID

from fastembed.rerank.cross_encoder import TextCrossEncoder
from pypdf import PdfReader

from rag.embeddings import embed_texts, embed_query
from rag.vectorstore import document_exists, search_chunks, store_document
from services import project_repository
from services.observability import observe


_reranker: TextCrossEncoder | None = None
_reranker_lock = Lock()


def _rerank_model() -> TextCrossEncoder:
    global _reranker
    with _reranker_lock:
        if _reranker is None:
            _reranker = TextCrossEncoder(
                model_name="Xenova/ms-marco-MiniLM-L-6-v2"
            )
        return _reranker


def extract_document_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        pages = PdfReader(BytesIO(content)).pages
        text = "\n".join(page.extract_text() or "" for page in pages)
    elif suffix in {".md", ".txt"}:
        text = content.decode("utf-8-sig")
    else:
        raise ValueError("Only PDF, Markdown, and plain-text files are supported.")

    normalized = re.sub(r"[ \t]+", " ", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    if not normalized.strip():
        raise ValueError("The uploaded file contains no extractable text.")
    return normalized.strip()


def chunk_text(text: str, chunk_words: int = 220, overlap_words: int = 40) -> list[str]:
    if chunk_words < 1 or overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("Chunk overlap must be non-negative and smaller than chunk size.")

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def ingest_document(
    *,
    title: str,
    text: str,
    source_type: str = "upload",
    document_id: UUID | None = None,
) -> dict[str, Any]:
    chunks = chunk_text(
        text,
        chunk_words=int(os.getenv("RAG_CHUNK_WORDS", "220")),
        overlap_words=int(os.getenv("RAG_CHUNK_OVERLAP_WORDS", "40")),
    )
    if not chunks:
        raise ValueError("The document contains no text to index.")

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    embeddings = embed_texts(chunks)
    document_id = store_document(
        document_id=document_id,
        title=title,
        source_type=source_type,
        content_sha256=digest,
        chunks=chunks,
        embeddings=embeddings,
    )
    return {
        "document_id": document_id,
        "title": title,
        "source_type": source_type,
        "chunk_count": len(chunks),
    }


def _project_plan_text(project: dict[str, Any]) -> str:
    return (
        f"Project idea:\n{project['project_idea']}\n\n"
        "Previously generated project plan:\n"
        f"{json.dumps(project['plan'], ensure_ascii=False, indent=2)}"
    )


def ensure_source_indexed(source_id: UUID) -> None:
    if document_exists(source_id):
        return

    project = project_repository.get_project(source_id)
    if project is None:
        raise LookupError(f"Knowledge source {source_id} was not found.")

    ingest_document(
        document_id=source_id,
        title=f"Saved project: {project['project_idea'][:100]}",
        text=_project_plan_text(project),
        source_type="project_plan",
    )


def _rerank(query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates:
        return []
    if os.getenv("RAG_RERANK_ENABLED", "on").lower() in {"0", "false", "off"}:
        return sorted(
            candidates,
            key=lambda candidate: candidate["similarity"],
            reverse=True,
        )

    model = _rerank_model()
    with _reranker_lock:
        scores = list(
            model.rerank(
                query,
                [candidate["content"] for candidate in candidates],
            )
        )
    if len(scores) != len(candidates):
        raise RuntimeError("The reranker returned an unexpected number of scores.")

    ranked = []
    for candidate, score in zip(candidates, scores):
        result = dict(candidate)
        result["rerank_score"] = float(score)
        ranked.append(result)
    return sorted(ranked, key=lambda candidate: candidate["rerank_score"], reverse=True)


def retrieve_context(
    document_ids: list[UUID],
    query: str,
    *,
    candidate_count: int = 12,
    result_count: int = 4,
) -> dict[str, Any]:
    if not document_ids:
        return {"context": "", "sources": []}

    with observe(
        "rag.retrieve",
        {
            "source_count": len(document_ids),
            "candidate_count": candidate_count,
            "result_count": result_count,
        },
    ) as observation:
        candidates = search_chunks(
            document_ids,
            embed_query(query),
            limit=candidate_count,
        )
        ranked = _rerank(query, candidates)[:result_count]

        source_map: dict[UUID, dict[str, Any]] = {}
        context_sections = []
        for item in ranked:
            source_id = item["document_id"]
            source_map[source_id] = {
                "document_id": source_id,
                "title": item["title"],
                "source_type": item["source_type"],
            }
            context_sections.append(
                f"[Source: {item['title']} | ID: {source_id}]\n{item['content']}"
            )

        result = {
            "context": "\n\n".join(context_sections),
            "sources": list(source_map.values()),
        }
        if observation is not None:
            observation.update(
                output={
                    "candidate_count": len(candidates),
                    "result_count": len(ranked),
                    "source_ids": [str(source_id) for source_id in source_map],
                }
            )
        return result