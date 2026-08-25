from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from unittest.mock import AsyncMock
from pathlib import Path

import numpy as np

from rag.app.rag import NO_RELEVANT_LESSON, RagService
from rag.app.retrieval import RetrievalIndex


class FakeEmbedder:
    model = "fake"

    async def embed_query(self, text):
        query = text.lower()
        if "safe" in query:
            vector = [1.0, 0.0]
        elif "message" in query:
            vector = [0.0, 1.0]
        else:
            vector = [-1.0, 0.0]
        return vector

    async def aclose(self):
        return None


class WrongModelEmbedder(FakeEmbedder):
    model = "different-model"


class RetrievalTests(unittest.TestCase):
    def _index(self, embedder=None) -> RetrievalIndex:
        chunks = [
            {
                "id": "privacy:1",
                "articleSlug": "privacy",
                "articleTitle": "Keep your information private",
                "articleUrl": "https://example.test/articles/privacy/",
                "heading": "Stay safe",
                "text": "Do not share passwords.",
            },
            {
                "id": "messages:1",
                "articleSlug": "messages",
                "articleTitle": "Write messages with AI",
                "articleUrl": "https://example.test/articles/messages/",
                "heading": "Drafting messages",
                "text": "Ask AI to help write a message.",
            },
            {
                "id": "privacy:cost:1",
                "articleSlug": "privacy",
                "articleTitle": "Keep your information private",
                "articleUrl": "https://example.test/articles/privacy/#ai-production-cost",
                "heading": "AI production cost and models",
                "chunkType": "generation-cost",
                "totalCostUsd": 0.0123,
                "costStatus": "reported",
                "models": ["Example Model (example/model)"],
                "stageSummaries": [
                    {
                        "key": "image_generation",
                        "status": "completed",
                        "costUsd": 0.01,
                        "costStatus": "reported",
                        "models": ["Example Image Model (example/image-model)"],
                    }
                ],
                "text": "The recorded cost was USD 0.0123 using Example Model.",
            },
        ]
        return RetrievalIndex(
            chunks,
            np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]),
            model_name="fake",
            embedder=embedder or FakeEmbedder(),
        )

    def test_retrieves_relevant_chunks_above_threshold(self) -> None:
        service = RagService(self._index(), relevance_threshold=0.5)
        result = asyncio.run(service.retrieve("How can I stay safe?", limit=2))
        self.assertTrue(result.relevant)
        self.assertEqual(result.sources[0].article_slug, "privacy")
        self.assertEqual(result.sources[0].score, 1.0)

    def test_cost_questions_search_only_generation_cost_chunks(self) -> None:
        service = RagService(self._index(), relevance_threshold=-1.0)
        result = asyncio.run(service.retrieve("Which model and provider were used?", limit=2))
        self.assertTrue(result.sources)
        self.assertTrue(all(source.heading == "AI production cost and models" for source in result.sources))

    def test_load_rejects_index_without_created_embeddings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            (data / "chunks.json").write_text(json.dumps({"chunks": []}), encoding="utf-8")
            (data / "index-manifest.json").write_text(
                json.dumps({"embedding": {"status": "skipped"}}), encoding="utf-8"
            )
            np.save(data / "embeddings.npy", np.array([]))
            with self.assertRaisesRegex(ValueError, "no created embeddings"):
                RetrievalIndex.load(data)

    def test_rejects_query_embedder_that_does_not_match_index_model(self) -> None:
        index = self._index(WrongModelEmbedder())
        with self.assertRaisesRegex(ValueError, "does not match index model"):
            asyncio.run(index.search("How can I stay safe?"))

    def test_no_relevant_result_has_no_sources(self) -> None:
        service = RagService(self._index(), relevance_threshold=0.99)
        result = asyncio.run(service.retrieve("Can you recommend a restaurant?", limit=1))
        self.assertFalse(result.relevant)
        self.assertEqual(result.sources, [])
        self.assertEqual(NO_RELEVANT_LESSON, "I could not find a relevant Saral lesson for that question yet.")

    def test_lists_all_topics_without_calling_answer_model(self) -> None:
        generator = AsyncMock()
        result = asyncio.run(RagService(self._index()).ask("List all topics available", generator))
        self.assertTrue(result.relevant)
        self.assertIn("Keep your information private", result.answer)
        self.assertIn("Write messages with AI", result.answer)
        generator.generate.assert_not_called()

    def test_lists_all_article_costs_and_models_without_answer_model(self) -> None:
        generator = AsyncMock()
        result = asyncio.run(RagService(self._index()).ask("List the costs and models for all articles", generator))
        self.assertIn("USD 0.0123", result.answer)
        self.assertIn("Example Model (example/model)", result.answer)
        self.assertIn("Write messages with AI", result.answer)
        self.assertIn("cost unavailable", result.answer)
        generator.generate.assert_not_called()

    def test_answers_individual_article_cost_concisely_without_answer_model(self) -> None:
        generator = AsyncMock()
        result = asyncio.run(
            RagService(self._index()).ask("What was the cost of generation of Keep your information private?", generator)
        )
        self.assertIn("total recorded AI production cost", result.answer)
        self.assertIn("USD 0.0123", result.answer)
        self.assertNotIn("input tokens", result.answer)
        generator.generate.assert_not_called()

    def test_answers_stage_cost_and_model_concisely(self) -> None:
        generator = AsyncMock()
        result = asyncio.run(
            RagService(self._index()).ask(
                "Which model generated the image for Keep your information private and what did it cost?",
                generator,
            )
        )
        self.assertIn("image generation", result.answer)
        self.assertIn("USD 0.01", result.answer)
        self.assertIn("Example Image Model", result.answer)
        generator.generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
