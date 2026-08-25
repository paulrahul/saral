from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from rag.app.embeddings import OpenRouterEmbeddingClient


class FakeSyncEmbeddings:
    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def create(self, *, model, input):
        self.batches.append(list(input))
        data = [
            SimpleNamespace(index=index, embedding=[float(len(text)), float(index + 1)])
            for index, text in enumerate(input)
        ]
        return SimpleNamespace(data=list(reversed(data)))


class FakeSyncClient:
    def __init__(self) -> None:
        self.embeddings = FakeSyncEmbeddings()

    def close(self) -> None:
        return None


class FakeAsyncEmbeddings:
    async def create(self, *, model, input):
        return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[1.0, 2.0])])


class FakeAsyncClient:
    def __init__(self) -> None:
        self.embeddings = FakeAsyncEmbeddings()

    async def close(self) -> None:
        return None


class EmbeddingClientTests(unittest.TestCase):
    def test_batches_documents_and_restores_response_order(self) -> None:
        client = OpenRouterEmbeddingClient("example/embed", api_key="test", batch_size=2)
        fake = FakeSyncClient()
        client._sync_client = fake

        vectors = client.embed_documents(["one", "three", "four"])

        self.assertEqual(fake.embeddings.batches, [["one", "three"], ["four"]])
        self.assertEqual(vectors, [[3.0, 1.0], [5.0, 2.0], [4.0, 1.0]])

    def test_embeds_runtime_query_asynchronously(self) -> None:
        client = OpenRouterEmbeddingClient("example/embed", api_key="test")
        client._async_client = FakeAsyncClient()

        vector = asyncio.run(client.embed_query("How can I stay safe?"))

        self.assertEqual(vector, [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
