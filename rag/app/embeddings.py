"""OpenRouter embedding transport shared by ingestion and runtime retrieval."""

from __future__ import annotations

import os
import time
from collections.abc import Sequence
from typing import Any, Callable

import httpx
from openai import AsyncOpenAI, OpenAI
from dotenv import load_dotenv


OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_HTTP_REFERER = "https://saralai-seven.vercel.app"
DEFAULT_APP_TITLE = "Saral Chat"


class OpenRouterEmbeddingClient:
    """Create document and query embeddings through OpenRouter.

    The synchronous method is used by the local ingestion command. Runtime
    retrieval uses the asynchronous method so an embedding request does not
    block the FastAPI event loop.
    """

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        batch_size: int = 64,
        timeout: float = 60.0,
    ) -> None:
        model = model.strip()
        if not model:
            raise ValueError("An OpenRouter embedding model is required.")
        if api_key is None:
            load_dotenv()
            api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required to create embeddings.")
        if batch_size < 1:
            raise ValueError("Embedding batch size must be at least 1.")

        self.model = model
        self.batch_size = batch_size
        self._api_key = api_key
        self._timeout = timeout
        self._sync_client: OpenAI | None = None
        self._async_client: AsyncOpenAI | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {"HTTP-Referer": DEFAULT_HTTP_REFERER, "X-Title": DEFAULT_APP_TITLE}

    def _get_sync_client(self) -> OpenAI:
        if self._sync_client is None:
            self._sync_client = OpenAI(
                api_key=self._api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers=self._headers,
                max_retries=2,
                timeout=self._timeout,
            )
        return self._sync_client

    def _get_async_client(self) -> AsyncOpenAI:
        if self._async_client is None:
            self._async_client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=OPENROUTER_BASE_URL,
                default_headers=self._headers,
                max_retries=2,
                http_client=httpx.AsyncClient(timeout=self._timeout),
            )
        return self._async_client

    @staticmethod
    def _vectors(response: Any, expected_count: int) -> list[list[float]]:
        data = sorted(response.data, key=lambda item: item.index)
        if len(data) != expected_count:
            raise RuntimeError(
                f"OpenRouter returned {len(data)} embeddings for {expected_count} input texts."
            )
        vectors = [list(item.embedding) for item in data]
        if not vectors or any(not vector for vector in vectors):
            raise RuntimeError("OpenRouter returned an empty embedding.")
        dimensions = len(vectors[0])
        if any(len(vector) != dimensions for vector in vectors):
            raise RuntimeError("OpenRouter returned embeddings with inconsistent dimensions.")
        return vectors

    @staticmethod
    def _usage(response: Any) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        if hasattr(usage, "model_dump"):
            value = usage.model_dump()
        elif isinstance(usage, dict):
            value = dict(usage)
        else:
            value = {
                key: getattr(usage, key)
                for key in ("prompt_tokens", "total_tokens", "cost")
                if getattr(usage, key, None) is not None
            }
        extra = getattr(usage, "model_extra", None)
        if isinstance(extra, dict):
            value.update(extra)
        return value

    @staticmethod
    def _validate_texts(texts: Sequence[str]) -> list[str]:
        values = [text.strip() for text in texts]
        if not values:
            raise ValueError("At least one text is required to create embeddings.")
        if any(not value for value in values):
            raise ValueError("Embedding input texts must not be empty.")
        return values

    def embed_documents(
        self,
        texts: Sequence[str],
        *,
        on_batch: Callable[[dict[str, Any], int, int], None] | None = None,
    ) -> list[list[float]]:
        """Synchronously embed document texts in stable input order."""

        values = self._validate_texts(texts)
        vectors: list[list[float]] = []
        client = self._get_sync_client()
        for start in range(0, len(values), self.batch_size):
            batch = values[start : start + self.batch_size]
            started = time.perf_counter()
            response = client.embeddings.create(model=self.model, input=batch)
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            vectors.extend(self._vectors(response, len(batch)))
            if on_batch is not None:
                on_batch(self._usage(response), elapsed_ms, len(batch))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        """Asynchronously embed one runtime search query."""

        value = self._validate_texts([text])[0]
        response = await self._get_async_client().embeddings.create(model=self.model, input=[value])
        return self._vectors(response, 1)[0]

    def close(self) -> None:
        if self._sync_client is not None:
            self._sync_client.close()
            self._sync_client = None

    async def aclose(self) -> None:
        if self._async_client is not None:
            await self._async_client.close()
            self._async_client = None
