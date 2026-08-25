"""Run the local Saral RAG ingestion pipeline with cost and latency metering."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv

from llm.observability import OpenRouterCostMeter
from rag.scripts.ingest import DEFAULT_MODEL, DEFAULT_SITE_URL, ingest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARTICLE_SOURCE = REPOSITORY_ROOT / "web" / "src" / "content" / "articles"
RAG_DATA_DIR = REPOSITORY_ROOT / "rag" / "data"
RAG_DATA_PATHS = (
    RAG_DATA_DIR / "chunks.json",
    RAG_DATA_DIR / "embeddings.npy",
    RAG_DATA_DIR / "index-manifest.json",
)
INGESTION_STAGE = "rag_ingestion"


@dataclass(frozen=True)
class IngestionResult:
    manifest: dict[str, Any]
    report_path: Path
    paths: tuple[Path, ...] = RAG_DATA_PATHS

    @property
    def cost_usd(self) -> float:
        totals = self.report.get("totals", {})
        value = totals.get("costUsd") if isinstance(totals, dict) else None
        return float(value) if isinstance(value, (int, float)) else 0.0

    @property
    def report(self) -> dict[str, Any]:
        import json

        value = json.loads(self.report_path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"Invalid ingestion report: {self.report_path}")
        return value


async def run_metered_ingestion(
    *,
    trigger: str,
    main_topic: str,
    topics: Iterable[str],
    article_run_id: str | None = None,
    rerun_batch_id: str | None = None,
    full_rebuild: bool = False,
) -> IngestionResult:
    """Refresh the complete index while charging only new or changed chunks."""

    load_dotenv()
    topic_list = list(dict.fromkeys(topic for topic in topics if topic))
    model = os.getenv("SARAL_EMBEDDING_MODEL", DEFAULT_MODEL)
    metadata: dict[str, Any] = {
        "topics": topic_list,
        "articleRunId": article_run_id,
        "rerunBatchId": rerun_batch_id,
        "fullRebuild": full_rebuild,
    }
    meter = OpenRouterCostMeter(
        kind="ingestion",
        trigger=trigger,
        main_topic=main_topic,
        topic=topic_list[0] if len(topic_list) == 1 else None,
        metadata={key: value for key, value in metadata.items() if value is not None},
    )
    meter.start_stage(INGESTION_STAGE)

    def record_batch(usage: dict[str, Any], elapsed_ms: int, input_count: int) -> None:
        meter.record_embedding_call(
            stage=INGESTION_STAGE,
            model_name=model,
            model=model,
            usage=usage,
            request_wall_time_ms=elapsed_ms,
            input_count=input_count,
        )

    try:
        manifest = await asyncio.to_thread(
            ingest,
            ARTICLE_SOURCE,
            RAG_DATA_DIR,
            site_url=os.getenv("SARAL_SITE_URL", DEFAULT_SITE_URL),
            model_name=model,
            full_rebuild=full_rebuild,
            on_embedding_batch=record_batch,
        )
    except BaseException as error:
        report_path = await meter.finish(api_key=None, error=error)
        raise RuntimeError(f"RAG ingestion failed; cost report written to {report_path}") from error

    embedding = manifest.get("embedding", {})
    if isinstance(embedding, dict) and embedding.get("embeddedChunks") == 0:
        meter.finish_stage(INGESTION_STAGE, "cached")
    else:
        meter.finish_stage(INGESTION_STAGE)
    meter.metadata.update(
        {
            "articleCount": manifest.get("articleCount"),
            "chunkCount": manifest.get("chunkCount"),
            "embeddedChunks": embedding.get("embeddedChunks") if isinstance(embedding, dict) else None,
            "reusedChunks": embedding.get("reusedChunks") if isinstance(embedding, dict) else None,
            "removedChunks": embedding.get("removedChunks") if isinstance(embedding, dict) else None,
        }
    )
    report_path = await meter.finish(api_key=None)
    return IngestionResult(manifest=manifest, report_path=report_path)
