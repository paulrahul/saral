from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from rag.scripts.ingest import ingest


class FakeEmbeddingClient:
    model = "example/embedding-model"

    def __init__(self) -> None:
        self.inputs: list[str] = []

    def embed_documents(self, texts):
        self.inputs = list(texts)
        return [[3.0, 4.0] for _text in texts]


class IngestTests(unittest.TestCase):
    def test_writes_only_canonical_english_article_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "articles"
            source.mkdir()
            (source / "hello.md").write_text(
                """---
title: Hello AI
summary: A short introduction to asking an AI assistant for help.
language: en
generationCost:
  totalUsd: 0.0123
  costStatus: reported
  stages:
    - key: content_generation
      status: completed
      costUsd: 0.0123
      calls:
        - modelName: Example Model
          model: example/model
          provider: Example Provider
          inputTokens: 100
          outputTokens: 50
---
# Hello AI

This introduction explains the purpose of the lesson.

## Ask a clear question

Give the assistant enough useful detail to provide a helpful answer.
""",
                encoding="utf-8",
            )
            (source / "hi").mkdir()
            (source / "hi" / "hello.md").write_text(
                """---
title: नमस्ते एआई
summary: अनुवादित लेख।
language: hi
translationOf: hello
---
अनुवादित पाठ
""",
                encoding="utf-8",
            )

            output = root / "index"
            manifest = ingest(source, output, site_url="https://example.test", skip_embeddings=True)

            self.assertEqual(manifest["articleCount"], 1)
            self.assertEqual(manifest["embedding"]["status"], "skipped")
            chunks = json.loads((output / "chunks.json").read_text(encoding="utf-8"))["chunks"]
            self.assertGreaterEqual(len(chunks), 1)
            self.assertTrue(all(chunk["language"] == "en" for chunk in chunks))
            lesson_chunks = [chunk for chunk in chunks if chunk["chunkType"] == "lesson"]
            self.assertTrue(
                all(chunk["articleUrl"] == "https://example.test/articles/hello/" for chunk in lesson_chunks)
            )
            cost_chunks = [chunk for chunk in chunks if chunk["chunkType"] == "generation-cost"]
            self.assertGreaterEqual(len(cost_chunks), 1)
            self.assertIn("Example Model (example/model)", cost_chunks[0]["models"])
            self.assertEqual(cost_chunks[0]["stageSummaries"][0]["costUsd"], 0.0123)
            self.assertIn("content generation", cost_chunks[0]["text"])
            self.assertEqual(manifest["costChunkCount"], len(cost_chunks))
            self.assertFalse((output / "embeddings.npy").exists())

    def test_writes_normalised_openrouter_embeddings_and_model_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "articles"
            source.mkdir()
            (source / "hello.md").write_text(
                """---
title: Hello AI
summary: A short introduction to using AI.
language: en
---
# Hello AI

Ask a clear question and check the answer carefully.
""",
                encoding="utf-8",
            )
            output = root / "index"
            client = FakeEmbeddingClient()

            manifest = ingest(
                source,
                output,
                model_name=client.model,
                embedding_client=client,
            )

            vectors = np.load(output / "embeddings.npy", allow_pickle=False)
            self.assertEqual(manifest["embedding"]["model"], client.model)
            self.assertEqual(manifest["embedding"]["dimensions"], 2)
            self.assertTrue(client.inputs)
            np.testing.assert_allclose(vectors[0], np.array([0.6, 0.8], dtype=np.float32))


if __name__ == "__main__":
    unittest.main()
