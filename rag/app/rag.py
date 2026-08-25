"""Interface-independent RAG service and local command-line test harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .retrieval import ArticleCostReference, RetrievalIndex, RetrievedChunk


NO_RELEVANT_LESSON = "I could not find a relevant Saral lesson for that question yet."


class AnswerGenerator(Protocol):
    async def generate(self, question: str, chunks: list[RetrievedChunk]) -> str: ...


@dataclass(frozen=True)
class RagResult:
    """A response that the later FastAPI and Gradio layers can present unchanged."""

    relevant: bool
    answer: str | None
    sources: list[RetrievedChunk]

    def to_dict(self) -> dict[str, Any]:
        return {
            "relevant": self.relevant,
            "answer": self.answer,
            "sources": [
                {
                    "title": source.article_title,
                    "url": source.article_url,
                    "heading": source.heading,
                    "score": round(source.score, 4),
                }
                for source in self.sources
            ],
        }


class RagService:
    """Retrieve Saral lessons and optionally turn relevant context into an answer."""

    def __init__(self, index: RetrievalIndex, *, relevance_threshold: float = 0.35) -> None:
        if not -1.0 <= relevance_threshold <= 1.0:
            raise ValueError("The relevance threshold must be between -1 and 1.")
        self._index = index
        self.relevance_threshold = relevance_threshold

    @classmethod
    def load(cls, data_dir: Path, *, relevance_threshold: float = 0.35) -> "RagService":
        return cls(RetrievalIndex.load(data_dir), relevance_threshold=relevance_threshold)

    async def retrieve(self, question: str, *, limit: int = 3) -> RagResult:
        if len(question.strip()) > 1_000:
            raise ValueError("Questions must be 1,000 characters or fewer.")
        words = self._normalised_words(question)
        cost_question = bool(words & {"cost", "costs", "model", "models", "provider", "providers", "token", "tokens", "latency", "production"})
        sources = await self._index.search(
            question,
            limit=limit,
            chunk_type="generation-cost" if cost_question else None,
        )
        relevant_sources = [
            source
            for source in sources
            if source.score >= self.relevance_threshold or source.metadata_matched
        ]
        return RagResult(relevant=bool(relevant_sources), answer=None, sources=relevant_sources)

    @staticmethod
    def _normalised_words(question: str) -> set[str]:
        return set(re.findall(r"[a-z]+", question.lower()))

    def _catalogue_answer(self, question: str) -> str | None:
        words = self._normalised_words(question)
        catalogue_subject = bool(words & {"topic", "topics", "lesson", "lessons", "article", "articles", "content"})
        catalogue_request = bool(words & {"list", "show", "available", "all", "which", "what"})
        qualified_request = bool(
            words
            & {
                "relevant",
                "related",
                "suitable",
                "appropriate",
                "recommend",
                "recommended",
                "elderly",
                "older",
                "senior",
                "beginner",
                "beginners",
            }
        )
        if (
            not catalogue_subject
            or not catalogue_request
            or qualified_request
            or bool(words & {"cost", "costs", "model", "models"})
        ):
            return None
        articles = self._index.articles()
        lines = ["Here are the Saral lessons currently available:"]
        lines.extend(f"{number}. [{article.title}]({article.url})" for number, article in enumerate(articles, start=1))
        return "\n\n".join(lines)

    def _all_costs_answer(self, question: str) -> str | None:
        words = self._normalised_words(question)
        if not (words & {"cost", "costs", "model", "models"}) or not (words & {"all", "every", "each", "list"}):
            return None
        costs = self._index.article_costs()
        if not costs:
            return "Cost and model information is not available for the indexed Saral articles."
        lines = ["Here is the available AI production information for every Saral article:"]
        for number, article in enumerate(costs, start=1):
            total = f"USD {article.total_cost_usd:.8f}".rstrip("0").rstrip(".") if article.total_cost_usd is not None else "cost unavailable"
            status = f"; status: {article.cost_status}" if article.cost_status else ""
            models = ", ".join(article.models) if article.models else "model information unavailable"
            lines.append(f"{number}. [{article.title}]({article.url}) — {total}{status}. Models: {models}.")
        return "\n\n".join(lines)

    @staticmethod
    def _requested_cost_stage(question: str) -> str | None:
        words = RagService._normalised_words(question)
        if "image" in words or "illustration" in words or "diagram" in words:
            return "image_generation"
        if "bengali" in words or "bangla" in words or "bn" in words:
            return "translation_bn"
        if "hindi" in words or "hi" in words:
            return "translation_hi"
        if "tag" in words or "tags" in words:
            return "tag_generation"
        normalised = " ".join(re.findall(r"[a-z]+", question.lower()))
        if "content evaluation" in normalised or "article evaluation" in normalised:
            return "content_evaluation"
        if "content generation" in normalised or "draft generation" in normalised:
            return "content_generation"
        return None

    @staticmethod
    def _matching_cost_article(question: str, costs: list[ArticleCostReference]) -> ArticleCostReference | None:
        normalised_question = " ".join(re.findall(r"[a-z0-9]+", question.lower()))
        for article in costs:
            normalised_title = " ".join(re.findall(r"[a-z0-9]+", article.title.lower()))
            if normalised_title and normalised_title in normalised_question:
                return article
        return None

    def _individual_cost_answer(self, question: str) -> str | None:
        words = self._normalised_words(question)
        if not words & {"cost", "costs", "model", "models", "provider", "providers", "token", "tokens", "latency", "production"}:
            return None
        article = self._matching_cost_article(question, self._index.article_costs())
        if article is None:
            return None
        if article.total_cost_usd is None:
            return f"Cost and model information is not available for [{article.title}]({article.url})."

        stage_key = self._requested_cost_stage(question)
        if stage_key:
            stage = next((stage for stage in article.stages if stage.get("key") == stage_key), None)
            if stage is None:
                return f"The requested production-stage information is not available for [{article.title}]({article.url})."
            label = stage_key.replace("_", " ")
            raw_cost = stage.get("costUsd")
            cost = f"USD {float(raw_cost):.8f}".rstrip("0").rstrip(".") if isinstance(raw_cost, (int, float)) else "unavailable"
            models = stage.get("models", [])
            model_text = ", ".join(str(model) for model in models) if isinstance(models, list) and models else "unavailable"
            status = stage.get("costStatus") or stage.get("status")
            status_text = f" The recorded status is **{status}**." if status else ""
            return (
                f"For [{article.title}]({article.url}), the recorded **{label}** cost is **{cost}**. "
                f"The model used was **{model_text}**.{status_text}"
            )

        total = f"USD {article.total_cost_usd:.8f}".rstrip("0").rstrip(".")
        answer = f"The total recorded AI production cost for [{article.title}]({article.url}) is **{total}**."
        if article.cost_status == "partial":
            answer += " The record is marked **partial**, so the actual total may be higher where a call's cost was unavailable."
        if words & {"model", "models"}:
            models = ", ".join(article.models) if article.models else "unavailable"
            answer += f" Models recorded for this article: **{models}**."
        return answer

    def deterministic_answer(self, question: str) -> RagResult | None:
        """Answer corpus-wide catalogue questions without retrieval or an LLM call."""

        if len(question.strip()) > 1_000:
            raise ValueError("Questions must be 1,000 characters or fewer.")
        answer = self._all_costs_answer(question) or self._individual_cost_answer(question) or self._catalogue_answer(question)
        return RagResult(relevant=True, answer=answer, sources=[]) if answer else None

    async def ask(self, question: str, generator: AnswerGenerator, *, limit: int = 3) -> RagResult:
        deterministic_result = self.deterministic_answer(question)
        if deterministic_result:
            return deterministic_result
        result = await self.retrieve(question, limit=limit)
        if not result.relevant:
            return RagResult(relevant=False, answer=NO_RELEVANT_LESSON, sources=[])
        answer = await generator.generate(question, result.sources)
        return RagResult(relevant=True, answer=answer, sources=result.sources)

    async def close(self) -> None:
        await self._index.close()


def _default_data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search Saral's local article index.")
    parser.add_argument("question", nargs="?", help="Question to search for. Omit with --interactive.")
    parser.add_argument("--data", type=Path, default=_default_data_dir(), help="Directory containing ingestion artifacts.")
    parser.add_argument("--top-k", type=int, default=3, help="Maximum relevant chunks to return.")
    parser.add_argument("--threshold", type=float, default=0.35, help="Minimum cosine similarity for relevance.")
    parser.add_argument("--answer", action="store_true", help="Generate an OpenRouter answer after relevant retrieval.")
    parser.add_argument("--model", help="OpenRouter model used with --answer.")
    parser.add_argument("--interactive", action="store_true", help="Ask questions repeatedly without sending model requests.")
    return parser.parse_args()


def _print_result(result: RagResult, *, include_text: bool = True) -> None:
    if result.answer:
        print(f"\nAnswer\n{result.answer}")
    if not result.sources:
        if not result.answer:
            print("\nNo sufficiently relevant Saral lesson was found.")
        return
    print("\nRetrieved lessons")
    for number, source in enumerate(result.sources, start=1):
        print(f"{number}. {source.article_title} ({source.heading}) — score {source.score:.3f}")
        print(f"   {source.article_url}")
        if include_text:
            print(f"   {source.text}")


async def _generate_answer(service: RagService, question: str, model: str, limit: int) -> RagResult:
    from .llm import OpenRouterAnswerGenerator

    generator = OpenRouterAnswerGenerator(model)
    try:
        return await service.ask(question, generator, limit=limit)
    finally:
        await generator.close()


async def _run_cli(args: argparse.Namespace) -> None:
    service = RagService.load(args.data, relevance_threshold=args.threshold)
    try:
        if args.interactive:
            print("Saral retrieval test. Press Enter on an empty line to exit.")
            while question := input("\nQuestion: ").strip():
                _print_result(await service.retrieve(question, limit=args.top_k))
            return

        if args.answer:
            result = await _generate_answer(service, args.question, args.model, args.top_k)
        else:
            result = service.deterministic_answer(args.question) or await service.retrieve(
                args.question, limit=args.top_k
            )
        _print_result(result)
        print("\nJSON")
        print(json.dumps(result.to_dict(), indent=2))
    finally:
        await service.close()


def main() -> None:
    args = parse_args()
    if args.answer and not args.model:
        raise SystemExit("--model is required with --answer so a paid model is never selected implicitly.")
    if args.interactive and (args.question or args.answer):
        raise SystemExit("--interactive cannot be combined with a question or --answer.")
    if not args.interactive and not args.question:
        raise SystemExit("Provide a question or use --interactive.")

    asyncio.run(_run_cli(args))


if __name__ == "__main__":
    main()
