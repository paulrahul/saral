"""Persist OpenRouter cost and timing reports for Saral generation runs."""

from __future__ import annotations

import asyncio
import contextvars
import json
import time
import uuid
from collections import OrderedDict
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[2]
COST_REPORTS_DIR = REPO_ROOT / "llm" / "generated" / "cost-reports"
LOCAL_STAGE_KEYS = {"markdown_rebuild"}


def _slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a metrics filename from {value!r}")
    return slug


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H-%M-%SZ")


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _as_number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


class OpenRouterCostMeter:
    """Collect one run's per-stage OpenRouter usage and wall-clock timing."""

    _current_call: contextvars.ContextVar[tuple["OpenRouterCostMeter", str, str, str, float] | None] = (
        contextvars.ContextVar("saral_openrouter_cost_call", default=None)
    )

    def __init__(
        self,
        *,
        kind: str,
        trigger: str,
        main_topic: str,
        topic: str | None = None,
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if kind not in {"article", "topic_generation"}:
            raise ValueError(f"Unsupported cost-report kind: {kind!r}")
        self.kind = kind
        self.trigger = trigger
        self.main_topic = main_topic
        self.topic = topic
        self.run_id = run_id or uuid.uuid4().hex
        self.metadata = dict(metadata or {})
        self._started_at = _now()
        self._started_perf = time.perf_counter()
        self._finished_at: datetime | None = None
        self._finished_perf: float | None = None
        self._status = "running"
        self._error: str | None = None
        self._stages: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def start_stage(self, key: str) -> None:
        stage = self._stages.setdefault(
            key,
            {"key": key, "status": "running", "startedPerf": time.perf_counter(), "calls": []},
        )
        if stage["status"] in {"cached", "skipped"}:
            stage["status"] = "running"
            stage["startedPerf"] = time.perf_counter()

    def finish_stage(self, key: str, status: str = "completed") -> None:
        self.start_stage(key)
        stage = self._stages[key]
        stage["status"] = status
        stage["wallTimeMs"] = round((time.perf_counter() - stage["startedPerf"]) * 1000)

    def mark_stage(self, key: str, status: str) -> None:
        if status not in {"cached", "skipped"}:
            raise ValueError(f"Unsupported non-call stage status: {status!r}")
        self._stages[key] = {"key": key, "status": status, "wallTimeMs": 0, "calls": []}

    def has_calls(self) -> bool:
        """Return whether this run made any metered model requests."""
        return any(stage["calls"] for stage in self._stages.values())

    @contextmanager
    def capture_call(self, *, stage: str, model_name: str, model: str) -> Iterator[None]:
        token = self._current_call.set((self, stage, model_name, model, time.perf_counter()))
        try:
            yield
        finally:
            self._current_call.reset(token)

    @classmethod
    async def capture_openrouter_response(cls, response: httpx.Response) -> None:
        """HTTPX hook that records OpenRouter generation IDs for text calls."""
        scope = cls._current_call.get()
        if scope is None or response.request.url.host != "openrouter.ai":
            return
        meter, stage, model_name, model, started_perf = scope
        generation_id = response.headers.get("X-Generation-Id")
        if generation_id:
            meter._record_call(
                stage=stage,
                model_name=model_name,
                model=model,
                generation_id=generation_id,
                request_wall_time_ms=round((time.perf_counter() - started_perf) * 1000),
            )

    def _record_call(
        self,
        *,
        stage: str,
        model_name: str,
        model: str,
        generation_id: str | None = None,
        request_wall_time_ms: int | None = None,
        usage: Mapping[str, Any] | None = None,
    ) -> None:
        self.start_stage(stage)
        calls: list[dict[str, Any]] = self._stages[stage]["calls"]
        if generation_id and any(call.get("generationId") == generation_id for call in calls):
            return
        call: dict[str, Any] = {
            "modelName": model_name,
            "model": model,
            "generationId": generation_id,
            "requestWallTimeMs": request_wall_time_ms,
            "costStatus": "pending" if generation_id else "reported",
        }
        if usage:
            call.update(
                {
                    "costUsd": _as_number(usage.get("cost")),
                    "inputTokens": usage.get("prompt_tokens"),
                    "outputTokens": usage.get("completion_tokens"),
                    "totalTokens": usage.get("total_tokens"),
                }
            )
        calls.append(call)

    def record_image_call(
        self,
        *,
        stage: str,
        model_name: str,
        model: str,
        usage: Mapping[str, Any] | None,
        request_wall_time_ms: int,
    ) -> None:
        self._record_call(
            stage=stage,
            model_name=model_name,
            model=model,
            request_wall_time_ms=request_wall_time_ms,
            usage=usage,
        )

    async def resolve_costs(self, api_key: str | None) -> None:
        """Resolve authoritative text-call costs from OpenRouter generation IDs."""
        pending = [
            call
            for stage in self._stages.values()
            for call in stage["calls"]
            if call.get("generationId") and call.get("costStatus") == "pending"
        ]
        if not pending or not api_key:
            return

        async with httpx.AsyncClient(timeout=20) as client:
            for call in pending:
                for attempt in range(3):
                    try:
                        response = await client.get(
                            "https://openrouter.ai/api/v1/generation",
                            headers={"Authorization": f"Bearer {api_key}"},
                            params={"id": call["generationId"]},
                        )
                        if response.status_code == 404 and attempt < 2:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        response.raise_for_status()
                        data = response.json().get("data", {})
                        call.update(
                            {
                                "costUsd": _as_number(data.get("total_cost")),
                                "provider": data.get("provider_name"),
                                "inputTokens": data.get("tokens_prompt"),
                                "outputTokens": data.get("tokens_completion"),
                                "totalTokens": (data.get("tokens_prompt") or 0) + (data.get("tokens_completion") or 0),
                                "cachedTokens": data.get("native_tokens_cached"),
                                "reasoningTokens": data.get("native_tokens_reasoning"),
                                "latencyMs": data.get("latency"),
                                "generationTimeMs": data.get("generation_time"),
                                "costStatus": "reported",
                            }
                        )
                        break
                    except (httpx.HTTPError, ValueError):
                        if attempt == 2:
                            call["costStatus"] = "unavailable"
                        else:
                            await asyncio.sleep(0.5 * (attempt + 1))

    def _stage_document(self, stage: Mapping[str, Any]) -> dict[str, Any]:
        calls = [dict(call) for call in stage["calls"]]
        known_costs = [call["costUsd"] for call in calls if isinstance(call.get("costUsd"), (int, float))]
        unresolved = any(call.get("costStatus") in {"pending", "unavailable"} for call in calls)
        wall_time_ms = stage.get("wallTimeMs")
        if not isinstance(wall_time_ms, int):
            wall_time_ms = round((time.perf_counter() - stage["startedPerf"]) * 1000)
        return {
            "key": stage["key"],
            "status": stage["status"],
            "wallTimeMs": wall_time_ms,
            "costUsd": round(sum(known_costs), 8),
            "costStatus": "partial" if unresolved else "reported",
            "requestCount": len(calls),
            "calls": calls,
        }

    def document(self) -> dict[str, Any]:
        stages = [self._stage_document(stage) for stage in self._stages.values()]
        known_cost = sum(stage["costUsd"] for stage in stages)
        cost_partial = any(stage["costStatus"] == "partial" for stage in stages)
        finished_perf = self._finished_perf or time.perf_counter()
        finished_at = self._finished_at or _now()
        result: dict[str, Any] = {
            "version": 1,
            "runId": self.run_id,
            "kind": self.kind,
            "trigger": self.trigger,
            "mainTopic": self.main_topic,
            "topic": self.topic,
            "slug": _slugify(self.topic) if self.topic else None,
            "startedAt": self._started_at.isoformat(),
            "finishedAt": finished_at.isoformat(),
            "wallTimeMs": round((finished_perf - self._started_perf) * 1000),
            "status": self._status,
            "error": self._error,
            "metadata": self.metadata,
            "totals": {
                "costUsd": round(known_cost, 8),
                "costStatus": "partial" if cost_partial else "reported",
                "requestCount": sum(stage["requestCount"] for stage in stages),
            },
            "stages": stages,
        }
        return result

    def _report_directory(self) -> Path:
        if self.kind == "topic_generation":
            return COST_REPORTS_DIR / "topic-runs"
        if self.topic is None:
            raise ValueError("Article cost reports require a topic")
        return COST_REPORTS_DIR / "articles" / _slugify(self.topic)

    def persist(self) -> Path:
        document = self.document()
        filename = f"{_timestamp(self._started_at)}__{self.run_id}.json"
        output = self._report_directory() / filename
        _atomic_write_json(output, document)
        if self.kind == "article" and self._status == "completed":
            _atomic_write_json(output.parent / "latest.json", document)
        return output

    def display_cost(self) -> dict[str, Any]:
        """Return the latest article metrics safe to embed in Markdown.

        Detailed audit reports keep OpenRouter generation IDs locally. The
        website only needs the cost, timing, model, provider, and token fields
        needed to explain a lesson's latest generation run.
        """
        return display_cost_from_report(self.document())

    async def finish(self, *, api_key: str | None, error: BaseException | None = None) -> Path:
        if error is None:
            self._status = "completed"
        else:
            self._status = "failed"
            self._error = f"{type(error).__name__}: {error}"
            for stage in self._stages.values():
                if stage["status"] == "running":
                    self.finish_stage(stage["key"], "failed")
        self._finished_at = _now()
        self._finished_perf = time.perf_counter()
        await self.resolve_costs(api_key)
        return self.persist()


def display_cost_from_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return public display metrics from a persisted run report."""
    stages = document.get("stages")
    if not isinstance(stages, list):
        raise ValueError("Cost report does not contain a valid stage list")
    display_stages: list[dict[str, Any]] = []
    for stage in stages:
        if not isinstance(stage, Mapping) or not isinstance(stage.get("key"), str):
            raise ValueError("Cost report contains an invalid stage")
        if stage["key"] in LOCAL_STAGE_KEYS:
            continue
        calls = stage.get("calls")
        if not isinstance(calls, list) or not all(isinstance(call, Mapping) for call in calls):
            raise ValueError(f"Cost stage {stage['key']!r} contains invalid calls")
        public_calls = [
            {
                key: value
                for key, value in call.items()
                if key != "generationId" and value is not None
            }
            for call in calls
        ]
        known_costs = [
            float(call["costUsd"])
            for call in public_calls
            if isinstance(call.get("costUsd"), (int, float))
        ]
        unresolved = any(
            call.get("costStatus") in {"pending", "unavailable"}
            for call in public_calls
        )
        display_stages.append(
            {
                "key": stage["key"],
                "status": stage.get("status", "completed"),
                "wallTimeMs": stage.get("wallTimeMs", 0),
                "costUsd": round(sum(known_costs), 8),
                "costStatus": "partial" if unresolved else "reported",
                "requestCount": len(public_calls),
            }
            | {"calls": public_calls}
        )
    return _cost_document(display_stages, wall_time_ms=document.get("wallTimeMs"))


def _cost_document(stages: list[dict[str, Any]], *, wall_time_ms: object = None) -> dict[str, Any]:
    total_cost = round(
        sum(float(stage.get("costUsd", 0)) for stage in stages),
        8,
    )
    request_count = sum(int(stage.get("requestCount", 0)) for stage in stages)
    partial = any(stage.get("costStatus") == "partial" for stage in stages)
    if not isinstance(wall_time_ms, int) or wall_time_ms < 0:
        wall_time_ms = sum(
            int(stage.get("wallTimeMs", 0))
            for stage in stages
            if isinstance(stage.get("wallTimeMs"), int)
        )
    return {
        "totalUsd": total_cost,
        "wallTimeMs": wall_time_ms,
        "requestCount": request_count,
        "costStatus": "partial" if partial else "reported",
        "stages": stages,
    }


def merge_generation_costs(
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply one run to the costs of the artifacts it reused or replaced.

    Cached stages retain the calls that originally produced their artifact.
    Any non-cached stage replaces the old stage, including a deliberately
    skipped zero-call stage. Local, non-model stages never appear publicly.
    """
    merged: OrderedDict[str, dict[str, Any]] = OrderedDict()
    if previous is not None:
        stages = previous.get("stages")
        if not isinstance(stages, list):
            raise ValueError("Existing generation costs do not contain a valid stage list")
        for stage in stages:
            if isinstance(stage, Mapping) and isinstance(stage.get("key"), str):
                if stage["key"] not in LOCAL_STAGE_KEYS:
                    merged[stage["key"]] = dict(stage)

    current_stages = current.get("stages")
    if not isinstance(current_stages, list):
        raise ValueError("Current generation costs do not contain a valid stage list")
    replaced = False
    for stage in current_stages:
        if not isinstance(stage, Mapping) or not isinstance(stage.get("key"), str):
            raise ValueError("Current generation costs contain an invalid stage")
        key = stage["key"]
        if key in LOCAL_STAGE_KEYS:
            continue
        if stage.get("status") == "cached":
            continue
        merged[key] = dict(stage)
        replaced = True

    if previous is None:
        wall_time_ms = current.get("wallTimeMs")
    elif not replaced:
        wall_time_ms = previous.get("wallTimeMs")
    else:
        wall_time_ms = None
    return _cost_document(list(merged.values()), wall_time_ms=wall_time_ms)


def reconstruct_generation_cost(topic: str) -> dict[str, Any]:
    """Rebuild a topic's effective costs from successful, cost-bearing runs."""
    reports_dir = COST_REPORTS_DIR / "articles" / _slugify(topic)
    reports: list[dict[str, Any]] = []
    for path in reports_dir.glob("*.json"):
        if path.name == "latest.json":
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(document, dict) or document.get("status") != "completed":
            continue
        totals = document.get("totals")
        if not isinstance(totals, Mapping) or not totals.get("requestCount"):
            continue
        reports.append(document)
    reports.sort(key=lambda report: str(report.get("startedAt", "")))
    if not reports:
        raise ValueError(f"No successful model-call cost reports found for topic {topic!r}")

    effective: dict[str, Any] | None = None
    for report in reports:
        effective = merge_generation_costs(effective, display_cost_from_report(report))
    if effective is None or not effective["requestCount"]:
        raise ValueError(f"Could not reconstruct model-call costs for topic {topic!r}")
    return effective


def write_rerun_batch(document: Mapping[str, Any]) -> Path:
    """Persist a parent manifest that links all per-topic rerun reports."""
    batch_id = document.get("batchId")
    if not isinstance(batch_id, str) or not batch_id:
        raise ValueError("Rerun batch documents require a batchId")
    output = COST_REPORTS_DIR / "rerun-batches" / f"{batch_id}.json"
    _atomic_write_json(output, document)
    return output


def append_local_stage(report_path: Path, *, key: str, wall_time_ms: int, status: str = "completed") -> None:
    """Add a non-billable rerun step to an already-written article report."""
    document = json.loads(report_path.read_text(encoding="utf-8"))
    stages = document.get("stages")
    if not isinstance(stages, list):
        raise ValueError(f"Invalid cost report: {report_path}")
    stages.append(
        {
            "key": key,
            "status": status,
            "wallTimeMs": wall_time_ms,
            "costUsd": 0.0,
            "costStatus": "reported",
            "requestCount": 0,
            "calls": [],
        }
    )
    started_at = datetime.fromisoformat(document["startedAt"])
    finished_at = _now()
    document["finishedAt"] = finished_at.isoformat()
    document["wallTimeMs"] = round((finished_at - started_at).total_seconds() * 1000)
    _atomic_write_json(report_path, document)
    if document.get("kind") == "article" and document.get("status") == "completed":
        _atomic_write_json(report_path.parent / "latest.json", document)
