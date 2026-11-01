import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm.observability import merge_generation_costs, reconstruct_generation_cost
from llm.publishing import attach_generation_cost, read_generation_cost
from llm.publishing.exporter import _write_article


def stage(key: str, *, status: str = "completed", cost: float = 1.0) -> dict:
    calls = [] if status in {"cached", "skipped"} else [
        {
            "modelName": "Test model",
            "model": "test/model",
            "costStatus": "reported",
            "costUsd": cost,
        }
    ]
    return {
        "key": key,
        "status": status,
        "wallTimeMs": 10,
        "costUsd": cost if calls else 0.0,
        "costStatus": "reported",
        "requestCount": len(calls),
        "calls": calls,
    }


def display(*stages: dict) -> dict:
    return {
        "totalUsd": sum(item["costUsd"] for item in stages),
        "wallTimeMs": 10,
        "requestCount": sum(item["requestCount"] for item in stages),
        "costStatus": "reported",
        "stages": list(stages),
    }


class GenerationCostTests(unittest.TestCase):
    def test_cached_stages_retain_existing_costs(self) -> None:
        previous = display(stage("content_generation", cost=2), stage("image_generation", cost=3))
        current = display(
            stage("content_generation", status="cached"),
            stage("image_generation", cost=4),
        )

        merged = merge_generation_costs(previous, current)

        self.assertEqual(merged["totalUsd"], 6)
        self.assertEqual(merged["requestCount"], 2)
        self.assertEqual(merged["stages"][0]["costUsd"], 2)
        self.assertEqual(merged["stages"][1]["costUsd"], 4)

    def test_skipped_stage_replaces_an_old_model_call(self) -> None:
        previous = display(stage("tag_evaluation", cost=2))
        current = display(stage("tag_evaluation", status="skipped"))

        merged = merge_generation_costs(previous, current)

        self.assertEqual(merged["totalUsd"], 0)
        self.assertEqual(merged["requestCount"], 0)
        self.assertEqual(merged["stages"][0]["status"], "skipped")

    def test_markdown_stage_is_never_public(self) -> None:
        merged = merge_generation_costs(None, display(stage("markdown_rebuild", status="skipped")))
        self.assertEqual(merged["stages"], [])

    def test_reconstruction_replays_successful_cost_bearing_reports(self) -> None:
        full = {
            "status": "completed",
            "startedAt": "2026-01-01T00:00:00+00:00",
            "wallTimeMs": 20,
            "totals": {"requestCount": 2},
            "stages": [stage("content_generation", cost=2), stage("image_generation", cost=3)],
        }
        partial = {
            "status": "completed",
            "startedAt": "2026-01-02T00:00:00+00:00",
            "wallTimeMs": 10,
            "totals": {"requestCount": 1},
            "stages": [stage("content_generation", status="cached"), stage("image_generation", cost=4)],
        }
        cached = {
            "status": "completed",
            "startedAt": "2026-01-03T00:00:00+00:00",
            "wallTimeMs": 0,
            "totals": {"requestCount": 0},
            "stages": [stage("content_generation", status="cached")],
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            reports = root / "articles" / "topic"
            reports.mkdir(parents=True)
            import json

            (reports / "full.json").write_text(json.dumps(full), encoding="utf-8")
            (reports / "partial.json").write_text(json.dumps(partial), encoding="utf-8")
            (reports / "cached.json").write_text(json.dumps(cached), encoding="utf-8")
            (reports / "latest.json").write_text("not relevant", encoding="utf-8")
            with patch("llm.observability.costs.COST_REPORTS_DIR", root):
                rebuilt = reconstruct_generation_cost("Topic")

        self.assertEqual(rebuilt["totalUsd"], 6)
        self.assertEqual(rebuilt["requestCount"], 2)

    def test_markdown_export_preserves_existing_generation_cost(self) -> None:
        generation_cost = display(stage("content_generation", cost=2))
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "topic.md"
            arguments = {
                "output": output,
                "title": "Topic",
                "markdown": "# Topic\n\nA useful summary.\n\nBody.",
                "tags": ["AI Basics"],
                "image": {
                    "path": "/images/topic.png",
                    "altText": "Topic",
                    "width": 1200,
                    "height": 630,
                    "mediaType": "image/png",
                },
                "source_model": "test/model",
                "language": "en",
            }
            _write_article(**arguments, generation_cost=generation_cost)
            _write_article(**arguments)

            self.assertEqual(read_generation_cost(output), generation_cost)

    def test_cost_repair_changes_only_generation_cost_line(self) -> None:
        generation_cost = display(stage("content_generation", cost=2))
        with tempfile.TemporaryDirectory() as temporary:
            articles = Path(temporary)
            output = articles / "topic.md"
            original = "---\ntitle: Topic\ngenerationCost: corrupted\n---\nBody stays here.\n"
            output.write_text(original, encoding="utf-8")
            with patch("llm.publishing.exporter.ARTICLES_DIR", articles):
                attach_generation_cost("Topic", generation_cost)
            repaired = output.read_text(encoding="utf-8")

        self.assertIn("Body stays here.", repaired)
        self.assertEqual(repaired.count("generationCost:"), 1)
        self.assertEqual(read_generation_cost_from_text(repaired), generation_cost)


def read_generation_cost_from_text(document: str) -> dict:
    import json
    import re

    match = re.search(r"^generationCost:\s*(.+)$", document, re.MULTILINE)
    if match is None:
        raise AssertionError("generationCost line is missing")
    return json.loads(match.group(1))


if __name__ == "__main__":
    unittest.main()
