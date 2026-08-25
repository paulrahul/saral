"""A small, optional OpenRouter answer generator for retrieved Saral context."""

from __future__ import annotations

import os
from collections.abc import Sequence

import httpx
from openai import AsyncOpenAI

from .retrieval import RetrievedChunk


class OpenRouterAnswerGenerator:
    """Generate a concise, source-bound answer after relevant retrieval succeeds."""

    def __init__(self, model: str, *, api_key: str | None = None) -> None:
        if not model.strip():
            raise ValueError("An OpenRouter chat model is required.")
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required to generate an answer.")
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "https://saralai-seven.vercel.app", "X-Title": "Saral Chat"},
            http_client=httpx.AsyncClient(timeout=30.0),
        )

    async def close(self) -> None:
        await self._client.close()

    async def generate(self, question: str, chunks: Sequence[RetrievedChunk]) -> str:
        context = "\n\n".join(
            f"[Source {number}: {chunk.article_title} — {chunk.heading}]\n{chunk.text}"
            for number, chunk in enumerate(chunks, start=1)
        )
        response = await self._client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            max_tokens=350,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are Saral's experimental English lesson assistant. Answer only from the supplied "
                        "Saral lesson excerpts. Be clear, kind, and concise for a non-technical reader. "
                        "Do not invent facts, cite sources in prose, or give medical, legal, or financial advice. "
                        "When asked which lessons fit a person or need, list the relevant supplied lesson titles first. "
                        "If the excerpts do not answer the question, say so plainly."
                    ),
                },
                {"role": "user", "content": f"Question: {question}\n\nLesson excerpts:\n{context}"},
            ],
        )
        answer = response.choices[0].message.content if response.choices else None
        if not answer or not answer.strip():
            raise RuntimeError("The answer model returned an empty response.")
        return answer.strip()
