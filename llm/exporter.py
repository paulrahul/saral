"""Export approved EasyTutor content to Astro Markdown articles."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Mapping

from llm.util import read_approved_content, read_content, read_generated_image


ARTICLES_DIR = Path(__file__).resolve().parents[1] / "web" / "src" / "content" / "articles"
TRANSLATION_LANGUAGES = ("bn", "hi")
SUMMARY_MARKER = re.compile(r"^\s*<!--\s*saral-summary:\s*(.*?)\s*-->\s*", re.DOTALL)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a slug from {value!r}")
    return slug


def article_path(topic: str, language: str = "en") -> Path:
    filename = f"{slugify(topic)}.md"
    return ARTICLES_DIR / filename if language == "en" else ARTICLES_DIR / language / filename


def is_topic_exported(topic: str) -> bool:
    return _is_article_complete(article_path(topic, "en"), language="en") and not missing_translation_languages(topic)


def missing_translation_languages(topic: str) -> tuple[str, ...]:
    return tuple(
        language
        for language in TRANSLATION_LANGUAGES
        if not _is_article_complete(article_path(topic, language), language=language)
    )


def _is_article_complete(output: Path, *, language: str) -> bool:
    if not output.is_file():
        return False
    frontmatter = output.read_text(encoding="utf-8").split("---", 2)
    required_fields = ("image:", "imageAlt:")
    if language != "en":
        required_fields = (*required_fields, "language:", "translationOf:")
    return len(frontmatter) >= 3 and all(field in frontmatter[1] for field in required_fields)


def _summary_from(markdown: str) -> str:
    marker = SUMMARY_MARKER.match(markdown)
    if marker is not None:
        summary = " ".join(marker.group(1).split())
        if not summary:
            raise ValueError("Generated Markdown has an empty saral-summary marker")
        return summary[:180]

    # Compatibility for lessons generated before the summary marker existed.
    # New content must always supply the model-written marker above.
    for line in markdown.splitlines():
        text = line.strip().lstrip("#").strip()
        text = re.sub(r"[*_`]", "", text)
        if text and not text.startswith(("-", "*")):
            return text[:180]
    raise ValueError("Approved content does not contain a summary paragraph")


def _without_title(markdown: str) -> str:
    return re.sub(r"^#\s+.+\n+", "", markdown.strip(), count=1)


def _without_summary_marker(markdown: str) -> str:
    return SUMMARY_MARKER.sub("", markdown, count=1).strip()


def _title_from(markdown: str, fallback: str) -> str:
    match = re.match(r"^#\s+(.+?)\s*$", markdown.strip(), flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _translation_parts(markdown: str) -> tuple[str, str, list[str]]:
    """Extract translated image and tag metadata kept in the translation input."""
    image_match = re.search(
        r"\n?<!--\s*saral-image-alt:\s*(.*?)\s*-->\s*$",
        markdown,
        flags=re.DOTALL,
    )
    if image_match is None:
        raise ValueError("Translated Markdown did not include the saral-image-alt marker")
    alt_text = " ".join(image_match.group(1).split())
    if not alt_text:
        raise ValueError("Translated Markdown has an empty image alt text")
    markdown_without_image = markdown[:image_match.start()].strip()
    tags_match = re.search(r"\n?<!--\s*saral-tags:\s*(\[.*\])\s*-->\s*$", markdown_without_image, re.DOTALL)
    if tags_match is None:
        raise ValueError("Translated Markdown did not include the saral-tags marker")
    try:
        translated_tags = json.loads(tags_match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError("Translated Markdown contains invalid saral-tags JSON") from error
    if not isinstance(translated_tags, list) or not translated_tags or not all(
        isinstance(tag, str) and tag.strip() for tag in translated_tags
    ):
        raise ValueError("Translated Markdown contains invalid saral-tags values")
    return markdown_without_image[:tags_match.start()].strip(), alt_text, translated_tags


def _published_at(output: Path) -> str:
    if output.is_file():
        match = re.search(r'^publishedAt:\s*["\'](.+?)["\']\s*$', output.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            return match.group(1)
    return datetime.now(timezone.utc).isoformat()


def _write_article(
    *,
    output: Path,
    title: str,
    markdown: str,
    tags: list[str],
    image: Mapping[str, str],
    source_model: str,
    language: str,
    translation_of: str | None = None,
) -> Path:
    summary = _summary_from(markdown)
    body = _without_title(_without_summary_marker(markdown))
    frontmatter = [
        "---",
        f"title: {_yaml_quote(title)}",
        f"summary: {_yaml_quote(summary)}",
        f"publishedAt: {_yaml_quote(_published_at(output))}",
        f"language: {_yaml_quote(language)}",
        "tags:",
        *[f"  - {_yaml_quote(tag)}" for tag in tags],
        f"image: {_yaml_quote(image['path'])}",
        f"imageAlt: {_yaml_quote(image['altText'])}",
        f"sourceModel: {_yaml_quote(source_model)}",
    ]
    if translation_of is not None:
        frontmatter.append(f"translationOf: {_yaml_quote(translation_of)}")
    frontmatter.extend(("---", ""))
    output.parent.mkdir(parents=True, exist_ok=True)
    document = "\n".join(frontmatter)
    output.write_text(f"{document}{body}\n", encoding="utf-8")
    return output


def export_approved_topic(topic: str, translations: Mapping[str, str]) -> list[Path]:
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

    image = read_generated_image(topic)
    if image is None:
        raise ValueError(f"Topic {topic!r} needs a generated image before publishing")

    missing_languages = missing_translation_languages(topic)
    if set(translations) != set(missing_languages):
        raise ValueError(f"Missing translations for: {', '.join(sorted(missing_languages))}")

    english_output = article_path(topic)
    outputs: list[Path] = []
    if english_output.is_file():
        # Existing English Markdown is the source of truth. Translation-only
        # runs must not rewrite it or change its original publication date.
        outputs.append(english_output)
    else:
        outputs.append(
            _write_article(
                output=english_output,
                title=topic,
                markdown=draft,
                tags=tags,
                image=image,
                source_model=model,
                language="en",
            )
        )
    for language in missing_languages:
        translated_markdown, translated_alt, translated_tags = _translation_parts(translations[language])
        outputs.append(
            _write_article(
                output=article_path(topic, language),
                title=_title_from(translated_markdown, topic),
                markdown=translated_markdown,
                tags=translated_tags,
                image={**image, "altText": translated_alt},
                source_model=model,
                language=language,
                translation_of=slugify(topic),
            )
        )
    return outputs
