import os
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector

from rag.embeddings import VECTOR_DIMENSIONS


CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('upload', 'project_plan')),
    content_sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

CREATE_CHUNKS_TABLE = f"""
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id BIGSERIAL PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    embedding vector({VECTOR_DIMENSIONS}) NOT NULL,
    UNIQUE (document_id, chunk_index)
)
"""

CREATE_CHUNKS_INDEX = """
CREATE INDEX IF NOT EXISTS knowledge_chunks_embedding_hnsw_idx
ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)
"""

_schema_ready = False
_schema_lock = Lock()


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not configured.")
    return database_url


def _connect() -> psycopg.Connection:
    _ensure_schema()
    timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
    if timeout < 1:
        raise ValueError("DB_CONNECT_TIMEOUT must be at least 1 second.")
    connection = psycopg.connect(_database_url(), connect_timeout=timeout)
    try:
        register_vector(connection)
        return connection
    except Exception:
        connection.close()
        raise


def _ensure_schema() -> None:
    global _schema_ready
    with _schema_lock:
        if _schema_ready:
            return

        timeout = int(os.getenv("DB_CONNECT_TIMEOUT", "5"))
        if timeout < 1:
            raise ValueError("DB_CONNECT_TIMEOUT must be at least 1 second.")
        with psycopg.connect(_database_url(), connect_timeout=timeout) as connection:
            with connection.cursor() as cursor:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
                cursor.execute(CREATE_DOCUMENTS_TABLE)
                cursor.execute(CREATE_CHUNKS_TABLE)
                cursor.execute(CREATE_CHUNKS_INDEX)
        _schema_ready = True


def store_document(
    *,
    document_id: UUID | None,
    title: str,
    source_type: str,
    content_sha256: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> UUID:
    if len(chunks) != len(embeddings):
        raise ValueError("Every knowledge chunk must have one embedding.")

    document_id = document_id or uuid4()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO knowledge_documents (id, title, source_type, content_sha256)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    title = EXCLUDED.title,
                    source_type = EXCLUDED.source_type,
                    content_sha256 = EXCLUDED.content_sha256
                """,
                (document_id, title, source_type, content_sha256),
            )
            cursor.execute(
                "DELETE FROM knowledge_chunks WHERE document_id = %s",
                (document_id,),
            )
            cursor.executemany(
                """
                INSERT INTO knowledge_chunks
                    (document_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (document_id, index, chunk, embedding)
                    for index, (chunk, embedding) in enumerate(
                        zip(chunks, embeddings)
                    )
                ],
            )
    return document_id


def search_chunks(
    document_ids: list[UUID],
    query_embedding: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    if not document_ids or limit < 1:
        return []

    query_vector = Vector(query_embedding)
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    d.id,
                    d.title,
                    d.source_type,
                    c.content,
                    1 - (c.embedding <=> %s) AS similarity
                FROM knowledge_chunks AS c
                JOIN knowledge_documents AS d ON d.id = c.document_id
                WHERE c.document_id = ANY(%s::uuid[])
                ORDER BY c.embedding <=> %s
                LIMIT %s
                """,
                (query_vector, document_ids, query_vector, limit),
            )
            rows = cursor.fetchall()

    return [
        {
            "document_id": row[0],
            "title": row[1],
            "source_type": row[2],
            "content": row[3],
            "similarity": float(row[4]),
        }
        for row in rows
    ]


def document_exists(document_id: UUID) -> bool:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM knowledge_documents WHERE id = %s",
                (document_id,),
            )
            return cursor.fetchone() is not None


def list_documents(limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT d.id, d.title, d.source_type, COUNT(c.id)
                FROM knowledge_documents AS d
                LEFT JOIN knowledge_chunks AS c ON c.document_id = d.id
                WHERE d.source_type = 'upload'
                GROUP BY d.id
                ORDER BY d.created_at DESC, d.id
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
    return [
        {
            "document_id": row[0],
            "title": row[1],
            "source_type": row[2],
            "chunk_count": row[3],
        }
        for row in rows
    ]


def delete_document(document_id: UUID) -> bool:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM knowledge_documents WHERE id = %s",
                (document_id,),
            )
            return cursor.rowcount > 0