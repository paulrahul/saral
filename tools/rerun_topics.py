#!/usr/bin/env python3
"""Back up, invalidate, and rerun every already-used EasyTutor topic.

The script deliberately invokes ``python -m llm.main`` for article work.  It
only adapts the topic queue temporarily, so reruns take the same generation
path as ordinary article runs.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm.metrics import (
    COST_REPORTS_DIR,
    OpenRouterCostMeter,
    append_local_stage,
    write_rerun_batch,
)


MAIN_TOPIC = "Teaching AI"
IMAGES_DIR = REPO_ROOT / "web" / "public" / "images"
ARTICLES_DIR = REPO_ROOT / "web" / "src" / "content" / "articles"
TRANSLATION_LANGUAGES = ("bn", "hi")
CONTENT_FILE = REPO_ROOT / "llm" / "generated" / "content.json"
APPROVAL_FILE = REPO_ROOT / "llm" / "generated" / "approved_content.json"
TAGS_FILE = REPO_ROOT / "llm" / "generated" / "tags.json"
IMAGES_FILE = REPO_ROOT / "llm" / "generated" / "images.json"
TOPICS_FILE = REPO_ROOT / "llm" / "generated" / "topics.json"
BROAD_TAGS = {
    "AI Basics",
    "Everyday Technology",
    "Internet & Web",
    "Mobile Devices",
    "Communication",
    "Online Safety",
    "Privacy",
    "Digital Money",
    "Online Services",
    "Accessibility",
    "Emerging Technology",
}
BACKUP_ROOT = REPO_ROOT / "tools" / ".rerun-backup"
LATEST_BACKUP = BACKUP_ROOT / "latest"


def datetime_now_iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


@dataclass(frozen=True)
class Selection:
    content: bool = False
    evaluation: bool = False
    images: bool = False
    translations: bool = False
    markdown: bool = False

    @property
    def has_requested_work(self) -> bool:
        return any((self.content, self.evaluation, self.images, self.translations, self.markdown))

    @property
    def requires_agent(self) -> bool:
        return not self.markdown or self.content or self.evaluation or self.images or self.translations

    @property
    def invalidate_approval(self) -> bool:
        return self.content or self.evaluation

    @property
    def invalidate_images(self) -> bool:
        return self.content or self.evaluation or self.images

    @property
    def invalidate_all_articles(self) -> bool:
        return self.content or self.evaluation

    @property
    def invalidate_translations(self) -> bool:
        return self.content or self.evaluation or self.translations

    @property
    def rebuild_articles(self) -> bool:
        return self.images or self.markdown


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rerun every used EasyTutor topic, optionally invalidating selected caches."
    )
    parser.add_argument("-c", "--content", action="store_true", help="Regenerate content and all downstream data")
    parser.add_argument("-e", "--evaluation", action="store_true", help="Re-evaluate content and regenerate downstream data")
    parser.add_argument("-i", "--images", action="store_true", help="Regenerate images and refresh article references")
    parser.add_argument("-t", "--translations", action="store_true", help="Regenerate translated articles")
    parser.add_argument("-m", "--markdown", action="store_true", help="Rebuild Markdown without translating it")
    parser.add_argument("-a", "--all", action="store_true", help="Regenerate all supported data")
    parser.add_argument(
        "--topic",
        action="append",
        default=[],
        metavar="NAME",
        help="Rerun one used topic; repeat this option to select several topics",
    )
    parser.add_argument("-dr", "--dry-run", action="store_true", help="Show the work that would be performed")
    parser.add_argument("--restore", action="store_true", help="Restore the latest rerun backup and exit")
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation")
    return parser.parse_args()


def selection_from(args: argparse.Namespace) -> Selection:
    if args.all:
        return Selection(True, True, True, True, True)
    return Selection(args.content, args.evaluation, args.images, args.translations, args.markdown)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Required file is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Required file contains invalid JSON: {path}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def read_json_or_empty(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return read_json(path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_bytes(path, (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))


def current_evaluation(topics: dict[str, Any]) -> dict[str, Any]:
    journals = topics.get(MAIN_TOPIC)
    if not isinstance(journals, dict) or not journals:
        raise ValueError(f"No evaluations found for main topic {MAIN_TOPIC!r}")
    evaluation = next(iter(journals.values()))
    if not isinstance(evaluation, dict):
        raise ValueError(f"Invalid evaluation record for main topic {MAIN_TOPIC!r}")
    return evaluation


def used_topics(topics: dict[str, Any]) -> list[str]:
    used = current_evaluation(topics).get("used", [])
    if not isinstance(used, list) or not all(isinstance(topic, str) and topic.strip() for topic in used):
        raise ValueError("Expected a list of used topic names")
    return list(dict.fromkeys(used))


def slugify(value: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a slug from {value!r}")
    return slug


def article_path(topic: str, language: str = "en") -> Path:
    filename = f"{slugify(topic)}.md"
    return ARTICLES_DIR / filename if language == "en" else ARTICLES_DIR / language / filename


def article_paths(topic: str) -> tuple[Path, ...]:
    return (article_path(topic), *(article_path(topic, language) for language in TRANSLATION_LANGUAGES))


def image_asset_path(metadata: Any) -> Path | None:
    if not isinstance(metadata, dict):
        return None
    public_path = metadata.get("path")
    if not isinstance(public_path, str) or not public_path.startswith("/images/"):
        return None
    filename = Path(public_path).name
    if not filename or filename != public_path.removeprefix("/images/"):
        return None
    return IMAGES_DIR / filename


def affected_paths(topics: list[str], selection: Selection) -> set[Path]:
    """Return files that must be restorable for this run."""
    paths: set[Path] = set()
    # The queue is temporarily changed around every normal agent invocation.
    if selection.requires_agent:
        paths.add(TOPICS_FILE)
        # A normal run can fill a partially-complete cache even when no flag was
        # supplied, so retain all topic-scoped stores for an accurate restore.
        paths.update((CONTENT_FILE, APPROVAL_FILE, IMAGES_FILE, TAGS_FILE))

    if selection.invalidate_images or selection.requires_agent:
        images = read_json_or_empty(IMAGES_FILE)
        for topic in topics:
            asset = image_asset_path(images.get(topic))
            if asset is not None:
                paths.add(asset)

    for topic in topics:
        if (
            selection.invalidate_all_articles
            or selection.invalidate_translations
            or selection.rebuild_articles
            or selection.requires_agent
        ):
            paths.update(article_paths(topic))
    return paths


def relative_to_root(path: Path) -> Path:
    try:
        return path.resolve(strict=False).relative_to(REPO_ROOT)
    except ValueError as error:
        raise ValueError(f"Refusing to back up a path outside the repository: {path}") from error


def create_backup(paths: set[Path], command: list[str]) -> Path:
    """Create the next latest backup before any persistent change is made."""
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    staging = BACKUP_ROOT / f".staging-{uuid.uuid4().hex}"
    files_dir = staging / "files"
    manifest_entries: list[dict[str, str | bool]] = []
    try:
        for path in sorted(paths):
            relative = relative_to_root(path)
            exists = path.is_file()
            manifest_entries.append({"path": str(relative), "exists": exists})
            if exists:
                target = files_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        manifest = {
            "version": 1,
            "command": command,
            "files": manifest_entries,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        if LATEST_BACKUP.exists():
            shutil.rmtree(LATEST_BACKUP)
        staging.replace(LATEST_BACKUP)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return LATEST_BACKUP


def add_created_paths_to_backup(paths: set[Path]) -> None:
    """Record generated image files that did not exist before this run."""
    manifest_path = LATEST_BACKUP / "manifest.json"
    manifest = read_json(manifest_path)
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError(f"Invalid backup manifest: {manifest_path}")
    existing = {entry.get("path") for entry in entries if isinstance(entry, dict)}
    for path in sorted(paths):
        relative = str(relative_to_root(path))
        if relative not in existing:
            entries.append({"path": relative, "exists": False})
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def restore_latest_backup() -> None:
    manifest_path = LATEST_BACKUP / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("No latest rerun backup exists")
    manifest = read_json(manifest_path)
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError(f"Invalid backup manifest: {manifest_path}")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("exists"), bool):
            raise ValueError(f"Invalid backup manifest entry: {entry!r}")
        target = REPO_ROOT / entry["path"]
        relative_to_root(target)
        if entry["exists"]:
            source = LATEST_BACKUP / "files" / entry["path"]
            if not source.is_file():
                raise ValueError(f"Backup is missing file data for {entry['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        else:
            target.unlink(missing_ok=True)
    print(f"Restored latest backup from {LATEST_BACKUP}")


def remove_topic_entries(path: Path, topics: list[str]) -> None:
    data = read_json_or_empty(path)
    if not data:
        return
    changed = False
    for topic in topics:
        if topic in data:
            data.pop(topic)
            changed = True
    if changed:
        write_json(path, data)


def clean_specific_tags() -> None:
    """Keep only registry tags still referenced by an approved topic."""
    approvals = read_json_or_empty(APPROVAL_FILE)
    referenced: list[str] = []
    for approval in approvals.values():
        if isinstance(approval, dict) and isinstance(approval.get("tags"), list):
            for tag in approval["tags"]:
                if isinstance(tag, str) and tag not in BROAD_TAGS and tag not in referenced:
                    referenced.append(tag)
    tags = read_json_or_empty(TAGS_FILE)
    existing = tags.get("specific", []) if isinstance(tags.get("specific", []), list) else []
    retained = [tag for tag in existing if isinstance(tag, str) and tag in referenced]
    retained.extend(tag for tag in referenced if tag not in retained)
    write_json(TAGS_FILE, {"specific": retained})


def remove_articles(topics: list[str], *, include_english: bool, include_translations: bool) -> None:
    for topic in topics:
        if include_english:
            article_path(topic).unlink(missing_ok=True)
        if include_translations:
            for language in TRANSLATION_LANGUAGES:
                article_path(topic, language).unlink(missing_ok=True)


def invalidate(topics: list[str], selection: Selection) -> None:
    if selection.content:
        remove_topic_entries(CONTENT_FILE, topics)
    if selection.invalidate_approval:
        remove_topic_entries(APPROVAL_FILE, topics)
        clean_specific_tags()
    if selection.invalidate_images:
        images = read_json_or_empty(IMAGES_FILE)
        assets_to_remove = [image_asset_path(images.get(topic)) for topic in topics]
        remaining_assets = {
            image_asset_path(metadata)
            for topic, metadata in images.items()
            if topic not in topics and image_asset_path(metadata) is not None
        }
        remove_topic_entries(IMAGES_FILE, topics)
        for asset in assets_to_remove:
            if asset is not None and asset not in remaining_assets:
                asset.unlink(missing_ok=True)
    if selection.invalidate_all_articles:
        remove_articles(topics, include_english=True, include_translations=True)
    elif selection.invalidate_translations:
        remove_articles(topics, include_english=False, include_translations=True)


def queue_topic(original_topics: dict[str, Any], topic: str) -> dict[str, Any]:
    """Return a temporary queue with one used topic as the next article."""
    temporary = copy.deepcopy(original_topics)
    evaluation = current_evaluation(temporary)
    result = evaluation.get("result", {})
    if not isinstance(result, dict):
        raise ValueError("Expected a topic result map")
    evaluation["result"] = {topic: "Admin rerun", **{key: value for key, value in result.items() if key != topic}}
    evaluation["used"] = [used for used in used_topics(temporary) if used != topic]
    return temporary


def run_normal_agent(
    topic: str,
    original_topics: dict[str, Any],
    *,
    batch_id: str,
    options: list[str],
) -> tuple[bool, str]:
    write_json(TOPICS_FILE, queue_topic(original_topics, topic))
    print(f"\nRunning normal article pipeline for: {topic}")
    run_id = uuid.uuid4().hex
    environment = os.environ | {
        "SARAL_RUN_TRIGGER": "rerun_topics",
        "SARAL_COST_RUN_ID": run_id,
        "SARAL_RERUN_BATCH_ID": batch_id,
        "SARAL_RERUN_OPTIONS": ",".join(options),
    }
    completed = subprocess.run(
        [sys.executable, "-m", "llm.main", "--no-publish"],
        cwd=REPO_ROOT,
        check=False,
        env=environment,
    )
    if completed.returncode:
        print(f"FAILED: {topic} (exit code {completed.returncode})", file=sys.stderr)
        return False, run_id
    return True, run_id


def report_path(topic: str, run_id: str) -> Path | None:
    reports = COST_REPORTS_DIR / "articles" / slugify(topic)
    matches = list(reports.glob(f"*__{run_id}.json"))
    return matches[0] if len(matches) == 1 else None


def rebuild_with_meter(topic: str, batch_id: str, options: list[str]) -> tuple[list[Path], Path]:
    meter = OpenRouterCostMeter(
        kind="article",
        trigger="rerun_topics",
        main_topic=MAIN_TOPIC,
        topic=topic,
        metadata={"rerun_batch_id": batch_id, "rerun_options": options},
    )
    meter.start_stage("markdown_rebuild")
    try:
        outputs = rebuild_markdown(topic)
    except BaseException as error:
        report = asyncio.run(meter.finish(api_key=None, error=error))
        raise RuntimeError(f"Markdown rebuild cost report: {report}") from error
    meter.finish_stage("markdown_rebuild")
    return outputs, asyncio.run(meter.finish(api_key=None))


def generated_image_paths(topics: list[str]) -> set[Path]:
    images = read_json_or_empty(IMAGES_FILE)
    return {
        asset
        for topic in topics
        if (asset := image_asset_path(images.get(topic))) is not None
    }


def rebuild_markdown(topic: str) -> list[Path]:
    # Importing llm.util initializes configured agents, which a dry run and the
    # cache-management portions of this tool do not need.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from llm.exporter import rebuild_exported_topic

    return rebuild_exported_topic(topic)


def print_plan(topics: list[str], selection: Selection, backup_paths: set[Path]) -> None:
    options = [
        name
        for name, enabled in (
            ("content", selection.content),
            ("evaluation", selection.evaluation),
            ("images", selection.images),
            ("translations", selection.translations),
            ("markdown", selection.markdown),
        )
        if enabled
    ]
    print(f"Selected used topics ({len(topics)}):")
    for topic in topics:
        print(f"  - {topic}")
    print("Requested work: " + (", ".join(options) if options else "normal rerun (no invalidation)"))
    print(f"Files in latest backup: {len(backup_paths)}")
    if selection.content:
        print("Content invalidation also refreshes approvals, images, translations, and articles.")
    elif selection.evaluation:
        print("Evaluation invalidation also refreshes images, translations, and articles.")
    elif selection.images:
        print("Image references will be rebuilt without re-translating article bodies.")


def confirm(args: argparse.Namespace) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise ValueError("Refusing a non-interactive run without --yes")
    answer = input("Create a latest backup and continue? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        raise ValueError("Cancelled")


def main() -> int:
    args = parse_args()
    try:
        if args.restore:
            if args.dry_run:
                print(f"Would restore latest backup from {LATEST_BACKUP}")
                return 0
            restore_latest_backup()
            return 0

        selection = selection_from(args)
        try:
            original_topic_bytes = TOPICS_FILE.read_bytes()
        except FileNotFoundError as error:
            raise ValueError(f"Required file is missing: {TOPICS_FILE}") from error
        original_topics = read_json(TOPICS_FILE)
        all_used_topics = used_topics(original_topics)
        if not all_used_topics:
            print("No used topics found. Nothing was changed.", file=sys.stderr)
            return 1

        requested_topics = list(dict.fromkeys(args.topic))
        unknown_topics = [topic for topic in requested_topics if topic not in all_used_topics]
        if unknown_topics:
            raise ValueError(
                "Requested topic is not currently used: " + ", ".join(repr(topic) for topic in unknown_topics)
            )
        topics = requested_topics or all_used_topics

        paths = affected_paths(topics, selection)
        print_plan(topics, selection, paths)
        if args.dry_run:
            return 0
        confirm(args)
        backup = create_backup(paths, sys.argv[1:])
        print(f"Created backup at {backup}")

        invalidate(topics, selection)
        successful: list[str] = []
        failed: list[str] = []
        option_names = [
            name
            for name, enabled in (
                ("content", selection.content),
                ("evaluation", selection.evaluation),
                ("images", selection.images),
                ("translations", selection.translations),
                ("markdown", selection.markdown),
            )
            if enabled
        ]
        batch_id = f"{int(time.time())}-{uuid.uuid4().hex[:12]}"
        batch_started_at = time.time()
        batch_reports: list[dict[str, Any]] = []
        article_report_paths: dict[str, Path] = {}
        try:
            if selection.requires_agent:
                for topic in topics:
                    completed, run_id = run_normal_agent(
                        topic,
                        original_topics,
                        batch_id=batch_id,
                        options=option_names,
                    )
                    output = report_path(topic, run_id)
                    if output is not None:
                        article_report_paths[topic] = output
                    batch_reports.append(
                        {
                            "topic": topic,
                            "slug": slugify(topic),
                            "runId": run_id,
                            "report": str(output.relative_to(COST_REPORTS_DIR)) if output else None,
                            "status": "completed" if completed else "failed",
                        }
                    )
                    if completed:
                        successful.append(topic)
                    else:
                        failed.append(topic)
            else:
                successful = list(topics)

            if selection.rebuild_articles:
                for topic in successful:
                    try:
                        if selection.requires_agent:
                            rebuild_started_at = time.perf_counter()
                            outputs = rebuild_markdown(topic)
                            output = article_report_paths.get(topic)
                            if output is not None:
                                append_local_stage(
                                    output,
                                    key="markdown_rebuild",
                                    wall_time_ms=round((time.perf_counter() - rebuild_started_at) * 1000),
                                )
                        else:
                            outputs, output = rebuild_with_meter(topic, batch_id, option_names)
                            batch_reports.append(
                                {
                                    "topic": topic,
                                    "slug": slugify(topic),
                                    "runId": output.stem.rsplit("__", 1)[-1],
                                    "report": str(output.relative_to(COST_REPORTS_DIR)),
                                    "status": "completed",
                                }
                            )
                        print(f"Rebuilt Markdown for {topic}: {', '.join(str(path) for path in outputs)}")
                    except Exception as error:
                        failed.append(topic)
                        print(f"FAILED to rebuild Markdown for {topic}: {error}", file=sys.stderr)
        finally:
            # The normal agent moves queued topics into ``used``.  Regeneration
            # must not change this persistent queue or its ordering.
            atomic_write_bytes(TOPICS_FILE, original_topic_bytes)

        add_created_paths_to_backup(generated_image_paths(topics))
        succeeded = [topic for topic in successful if topic not in failed]
        report_cost = 0.0
        for entry in batch_reports:
            if not entry.get("report"):
                continue
            try:
                report_data = read_json(COST_REPORTS_DIR / entry["report"])
                report_cost += float(report_data.get("totals", {}).get("costUsd", 0))
            except (ValueError, TypeError):
                pass
        batch_output = write_rerun_batch(
            {
                "version": 1,
                "batchId": batch_id,
                "trigger": "rerun_topics",
                "options": option_names or ["normal"],
                "startedAt": datetime_now_iso(batch_started_at),
                "finishedAt": datetime_now_iso(time.time()),
                "wallTimeMs": round((time.time() - batch_started_at) * 1000),
                "topics": batch_reports,
                "totals": {"costUsd": round(report_cost, 8), "topicCount": len(batch_reports)},
            }
        )
        print(f"Wrote rerun cost manifest to {batch_output}")
        print(f"\nCompleted {len(succeeded)} topic(s); {len(failed)} failed.")
        if failed:
            print("Failed topics: " + ", ".join(dict.fromkeys(failed)), file=sys.stderr)
            return 1
        return 0
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
