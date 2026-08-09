"""Export approved EasyTutor content to Astro Markdown articles."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from llm.util import read_approved_content, read_content, read_generated_image


ARTICLES_DIR = Path(__file__).resolve().parents[1] / "web" / "src" / "content" / "articles"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a slug from {value!r}")
    return slug


def article_path(topic: str) -> Path:
    return ARTICLES_DIR / f"{slugify(topic)}.md"


def is_topic_exported(topic: str) -> bool:
    output = article_path(topic)
    if not output.is_file():
        return False
    frontmatter = output.read_text(encoding="utf-8").split("---", 2)
    return len(frontmatter) >= 3 and "image:" in frontmatter[1] and "imageAlt:" in frontmatter[1]


def _summary_from(markdown: str) -> str:
    for line in markdown.splitlines():
        text = line.strip().lstrip("#").strip()
        text = re.sub(r"[*_`]", "", text)
        if text and not text.startswith(("-", "*")):
            return text[:180]
    raise ValueError("Approved content does not contain a summary paragraph")


def _without_title(markdown: str) -> str:
    return re.sub(r"^#\s+.+\n+", "", markdown.strip(), count=1)


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def export_approved_topic(topic: str) -> Path:
    approval = read_approved_content(topic)
    if approval is None:
        raise ValueError(f"Topic {topic!r} has not been approved for publishing")

    model = approval.get("model")
    if not isinstance(model, str):
        raise ValueError(f"Topic {topic!r} does not have an approved model")

    draft = read_content(topic).get(model)
    if not draft:
        raise ValueError(f"No content for approved model {model!r} on topic {topic!r}")

    tags = approval.get("tags", [])
    if not isinstance(tags, list) or not tags or not all(isinstance(tag, str) for tag in tags):
        raise ValueError(f"Topic {topic!r} needs at least one valid tag before publishing")

    published_at = datetime.now(timezone.utc).isoformat()
    image = read_generated_image(topic)
    if image is None:
        raise ValueError(f"Topic {topic!r} needs a generated image before publishing")
    body = _without_title(draft)
    frontmatter = "\n".join([
        "---",
        f"title: {_yaml_quote(topic)}",
        f"summary: {_yaml_quote(_summary_from(body))}",
        f"publishedAt: {_yaml_quote(published_at)}",
        "tags:",
        *[f"  - {_yaml_quote(tag)}" for tag in tags],
        f"image: {_yaml_quote(image['path'])}",
        f"imageAlt: {_yaml_quote(image['altText'])}",
        f"sourceModel: {_yaml_quote(model)}",
        "---",
        "",
    ])

    output = article_path(topic)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{frontmatter}{body}\n", encoding="utf-8")
    return output
