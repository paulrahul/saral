"""A small, optional OpenRouter answer generator for retrieved Saral context."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Sequence

import httpx
from openai import AsyncOpenAI, BadRequestError

from .retrieval import RetrievedChunk
from .settings import DEFAULT_CHAT_MAX_TOKENS, DEFAULT_CHAT_REASONING, validate_answer_options


logger = logging.getLogger(__name__)


def _reasoning_is_mandatory(error: BadRequestError) -> bool:
    """Recognize OpenRouter's rejection of a disabled-reasoning request."""

    message = str(error).lower()
    return "reasoning is mandatory" in message and "cannot be disabled" in message


class OpenRouterAnswerGenerator:
    """Generate a concise, source-bound answer after relevant retrieval succeeds."""

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        max_tokens: int = DEFAULT_CHAT_MAX_TOKENS,
        reasoning: str = DEFAULT_CHAT_REASONING,
    ) -> None:
        if not model.strip():
            raise ValueError("An OpenRouter chat model is required.")
        validate_answer_options(max_tokens, reasoning)
        api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required to generate an answer.")
        self.model = model
        self.max_tokens = max_tokens
        self.reasoning = reasoning
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
        messages = [
            {
                "role": "system",
                "content": (
                    "You are Saral's experimental English lesson assistant. Answer only from the supplied "
                    "Saral lesson excerpts. Be clear, kind, and concise for a non-technical reader. "
                    "Aim for no more than 200 words, and use fewer when a short answer is enough. "
                    "Do not invent facts, cite sources in prose, or give medical, legal, or financial advice. "
                    "When asked which lessons fit a person or need, list the relevant supplied lesson titles first. "
                    "If the excerpts do not answer the question, say so plainly."
                ),
            },
            {"role": "user", "content": f"Question: {question}\n\nLesson excerpts:\n{context}"},
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                max_tokens=self.max_tokens,
                # 'default' leaves model/provider defaults untouched. 'off'
                # requests no reasoning where the selected model permits it.
                extra_body={"reasoning": {"enabled": False}} if self.reasoning == "off" else None,
                messages=messages,
            )
        except BadRequestError as error:
            if self.reasoning != "off" or not _reasoning_is_mandatory(error):
                raise
            logger.info("Answer model requires reasoning; retrying without the disabled-reasoning override.")
            response = await self._client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                max_tokens=self.max_tokens,
                messages=messages,
            )
        choice = response.choices[0] if response.choices else None
        message = choice.message if choice else None
        answer = message.content if message else None
        if not isinstance(answer, str) or not answer.strip():
            usage = getattr(response, "usage", None)
            details = getattr(usage, "completion_tokens_details", None)
            # Log only diagnostic metadata, never the question, excerpts,
            # generated answer, reasoning text, credentials, or raw response.
            logger.warning(
                "Answer model returned no usable text: %s",
                json.dumps(
                    {
                        "requested_model": self.model,
                        "response_model": getattr(response, "model", None),
                        "response_id": getattr(response, "id", None),
                        "provider": getattr(response, "provider", None),
                        "finish_reason": getattr(choice, "finish_reason", None),
                        "max_tokens": self.max_tokens,
                        "reasoning_setting": self.reasoning,
                        "prompt_tokens": getattr(usage, "prompt_tokens", None),
                        "completion_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                        "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                        "has_answer_text": isinstance(answer, str) and bool(answer.strip()),
                        "has_reasoning": bool(
                            getattr(message, "reasoning", None) or getattr(message, "reasoning_details", None)
                        ),
                    },
                    default=str,
                ),
            )
            raise RuntimeError("The answer model returned an empty response.")
        return answer.strip()
