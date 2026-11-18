import unittest
from unittest.mock import Mock, patch
from uuid import UUID

from pgvector import Vector
from rag.retriever import (
    chunk_text,
    ensure_source_indexed,
    extract_document_text,
    ingest_document,
    retrieve_context,
)
from rag.vectorstore import search_chunks


SOURCE_ID = UUID("12345678-1234-5678-1234-567812345678")


class RagTests(unittest.TestCase):
    def test_chunk_text_overlaps_adjacent_chunks(self):
        chunks = chunk_text(
            "one two three four five six seven",
            chunk_words=5,
            overlap_words=2,
        )

        self.assertEqual(chunks, ["one two three four five", "four five six seven"])

    def test_chunk_text_rejects_invalid_overlap(self):
        with self.assertRaisesRegex(ValueError, "smaller than chunk size"):
            chunk_text("words", chunk_words=2, overlap_words=2)

    def test_extract_document_text_decodes_utf8_and_rejects_other_formats(self):
        self.assertEqual(
            extract_document_text("brief.md", b"# Scope\n\nUse PostgreSQL."),
            "# Scope\n\nUse PostgreSQL.",
        )
        with self.assertRaisesRegex(ValueError, "Only PDF"):
            extract_document_text("brief.docx", b"not supported")

    @patch("rag.retriever.store_document", return_value=SOURCE_ID)
    @patch("rag.retriever.embed_texts", return_value=[[0.1] * 384])
    def test_ingest_document_embeds_and_persists_chunks(
        self,
        embed_texts,
        store_document,
    ):
        result = ingest_document(
            title="brief.md",
            text="A project brief with a few useful words.",
        )

        self.assertEqual(result["document_id"], SOURCE_ID)
        self.assertEqual(result["chunk_count"], 1)
        embed_texts.assert_called_once_with(["A project brief with a few useful words."])
        self.assertEqual(store_document.call_args.kwargs["source_type"], "upload")

    @patch("rag.retriever.ingest_document")
    @patch("rag.retriever.project_repository.get_project")
    @patch("rag.retriever.document_exists", return_value=False)
    def test_selected_saved_project_plan_is_indexed_on_demand(
        self,
        _document_exists,
        get_project,
        ingest_document,
    ):
        get_project.return_value = {
            "project_idea": "Build a trip planner.",
            "plan": {"requirements": {"functional_requirements": ["Create trips."]}},
        }

        ensure_source_indexed(SOURCE_ID)

        ingest_document.assert_called_once()
        self.assertEqual(ingest_document.call_args.kwargs["document_id"], SOURCE_ID)
        self.assertEqual(
            ingest_document.call_args.kwargs["source_type"],
            "project_plan",
        )
        self.assertIn(
            "Create trips.",
            ingest_document.call_args.kwargs["text"],
        )

    @patch("rag.retriever._rerank_model")
    @patch("rag.retriever.search_chunks")
    @patch("rag.retriever.embed_query", return_value=[0.0] * 384)
    def test_retrieval_searches_only_selected_sources_then_reranks(
        self,
        _embed_query,
        search_chunks,
        rerank_model,
    ):
        search_chunks.return_value = [
            {
                "document_id": SOURCE_ID,
                "title": "Project brief",
                "source_type": "upload",
                "content": "A first matching passage.",
                "similarity": 0.8,
            },
            {
                "document_id": SOURCE_ID,
                "title": "Project brief",
                "source_type": "upload",
                "content": "A better reranked passage.",
                "similarity": 0.7,
            },
        ]
        rerank_model.return_value.rerank.return_value = [0.2, 0.9]

        result = retrieve_context([SOURCE_ID], "Which database?")

        self.assertEqual(search_chunks.call_args.args[0], [SOURCE_ID])
        self.assertIn("A better reranked passage.", result["context"])
        self.assertEqual(result["sources"][0]["title"], "Project brief")
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(search_chunks.call_args.kwargs["limit"], 12)

    @patch.dict("os.environ", {"RAG_RERANK_ENABLED": "off"})
    @patch("rag.retriever._rerank_model")
    def test_vector_only_mode_skips_cross_encoder(self, rerank_model):
        from rag.retriever import _rerank

        candidates = [
            {"content": "lower", "similarity": 0.2},
            {"content": "higher", "similarity": 0.8},
        ]

        ranked = _rerank("query", candidates)

        self.assertEqual([item["content"] for item in ranked], ["higher", "lower"])
        rerank_model.assert_not_called()

    @patch("rag.vectorstore._connect")
    def test_search_chunks_binds_query_as_pgvector(self, connect):
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        cursor = Mock()
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection.cursor.return_value = cursor
        cursor.fetchall.return_value = []
        connect.return_value = connection

        search_chunks([SOURCE_ID], [0.1] * 384, limit=1)

        params = cursor.execute.call_args.args[1]
        self.assertIsInstance(params[0], Vector)
        vector_values = params[0].to_list()
        self.assertEqual(len(vector_values), 384)
        self.assertAlmostEqual(vector_values[0], 0.1)
        self.assertIs(params[0], params[2])


if __name__ == "__main__":
    unittest.main()
