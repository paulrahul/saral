from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    from fastapi.testclient import TestClient
except ImportError:  # Dependencies are intentionally installed only for this stage.
    TestClient = None

from rag.app.main import create_app
from rag.app.rag import RagService
from rag.app.retrieval import RetrievalIndex
from rag.app.settings import Settings


class FakeEmbedder:
    model = "fake"

    async def embed_query(self, _text):
        return [1.0, 0.0]

    async def aclose(self):
        return None


@unittest.skipIf(TestClient is None, "FastAPI dependencies are not installed")
class MainTests(unittest.TestCase):
    def _settings(self, data: Path) -> Settings:
        return Settings(
            data_dir=data,
            relevance_threshold=0.0,
            top_k=2,
            model=None,
            retrieval_only=True,
            allowed_origins=("http://localhost:4321",),
        )

    def _write_index(self, data: Path) -> None:
        chunks = {
            "chunks": [
                {
                    "id": "safety:1",
                    "articleSlug": "safety",
                    "articleTitle": "Stay safe",
                    "articleUrl": "https://example.test/articles/safety/",
                    "heading": "Safety",
                "text": "Never share a password.",
                }
            ]
        }
        (data / "chunks.json").write_text(json.dumps(chunks), encoding="utf-8")
        (data / "index-manifest.json").write_text(
            json.dumps({"chunkCount": 1, "embedding": {"status": "created", "model": "fake", "dimensions": 2}}),
            encoding="utf-8",
        )
        np.save(data / "embeddings.npy", np.array([[1.0, 0.0]], dtype=np.float32))

    def test_health_and_retrieval_only_ask(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            data = Path(temporary_directory)
            self._write_index(data)
            index = RetrievalIndex(
                json.loads((data / "chunks.json").read_text(encoding="utf-8"))["chunks"],
                np.array([[1.0, 0.0]], dtype=np.float32),
                model_name="fake",
                embedder=FakeEmbedder(),
            )
            service = RagService(index, relevance_threshold=0.0)
            with TestClient(create_app(self._settings(data), service=service)) as client:
                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertEqual(health.json()["mode"], "retrieval-only")
                response = client.post("/ask", json={"question": "How can I stay safe?"})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.json()["relevant"])
                self.assertIn("Retrieval-only test mode", response.json()["answer"])
                chat = client.get("/chat/")
                self.assertEqual(chat.status_code, 200)
                self.assertIn("Ask Saral", chat.text)
                self.assertIn("Technology made simple", chat.text)
                self.assertIn("only questions covered by lessons published on Saral", chat.text)
                self.assertIn("--saral-paper", chat.text)
                self.assertIn("--saral-paper: #dce5dc", chat.text)
                self.assertIn("https://paulrahul.github.io/#contact", chat.text)
                self.assertIn("saral-question-row", chat.text)
                self.assertIn("#saral-question .block-label", chat.text)
                self.assertIn("--block-title-text-color: var(--saral-green-dark) !important", chat.text)
                self.assertIn("#saral-chatbot .prose :not(a)", chat.text)


if __name__ == "__main__":
    unittest.main()
