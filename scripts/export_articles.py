#!/usr/bin/env python3
"""Export approved EasyTutor drafts to Astro Markdown articles."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT_FILE = ROOT / "llm" / "content.json"
APPROVAL_FILE = ROOT / "llm" / "approved_content.json"
ARTICLES_DIR = ROOT / "web" / "src" / "content" / "articles"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a slug from {value!r}")
    return slug


def summary_from(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip().lstrip("#").strip()
        text = re.sub(r"[*_`]", "", text)
        if text and not text.startswith(("-", "*")):
            return text[:180]
    raise ValueError("Approved content does not contain a summary paragraph")


def without_title(markdown: str) -> str:
    return re.sub(r"^#\s+.+\n+", "", markdown.strip(), count=1)


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def export_topic(topic: str, raw_content: dict, approval: dict) -> Path:
    model = approval["model"]
    draft = raw_content.get(topic, {}).get(model)
    if not draft:
        raise ValueError(f"No content for approved model {model!r} on topic {topic!r}")

    body = without_title(draft)
    tags = approval.get("tags", [])
    if not tags:
        raise ValueError(f"Topic {topic!r} needs at least one tag before publishing")

    published_at = approval.get("publishedAt", date.today().isoformat())
    frontmatter = "\n".join([
        "---",
        f"title: {yaml_quote(topic)}",
        f"summary: {yaml_quote(summary_from(body))}",
        f"publishedAt: {published_at}",
        "tags:",
        *[f"  - {yaml_quote(tag)}" for tag in tags],
        f"sourceModel: {yaml_quote(model)}",
        "---",
        "",
    ])

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    output = ARTICLES_DIR / f"{slugify(topic)}.md"
    output.write_text(f"{frontmatter}{body}\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Export approved content to Astro Markdown")
    parser.add_argument("--topic", help="Export one approved topic; defaults to the latest approved topic")
    parser.add_argument("--all", action="store_true", help="Export every approved topic")
    args = parser.parse_args()
    if args.topic and args.all:
        parser.error("Use either --topic or --all")

    raw_content = json.loads(CONTENT_FILE.read_text(encoding="utf-8"))
    approvals = json.loads(APPROVAL_FILE.read_text(encoding="utf-8"))
    topics = list(approvals) if args.all else [args.topic or next(reversed(approvals))]

    for topic in topics:
        if topic not in approvals:
            raise ValueError(f"Topic {topic!r} has not been approved for publishing")
        output = export_topic(topic, raw_content, approvals[topic])
        print(f"Exported {topic!r} to {output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
