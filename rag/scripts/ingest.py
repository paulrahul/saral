"""Build inspectable English-article retrieval artifacts for the Saral chatbot.

The script reads Markdown articles already exported for the web site, creates
heading-aware text chunks, and optionally embeds them through OpenRouter.

Examples:

    # Inspect article chunks before loading an embedding model.
    ./.venv/bin/python -m rag.scripts.ingest --skip-embeddings

    # Create chunks.json, embeddings.npy, and index-manifest.json.
    ./.venv/bin/python -m rag.scripts.ingest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from rag.app.embeddings import OpenRouterEmbeddingClient


DEFAULT_MODEL = "openai/text-embedding-3-small"
DEFAULT_SITE_URL = "https://saralai-seven.vercel.app"
SCHEMA_VERSION = 2
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\([^)]*\)")
INLINE_MARKDOWN_PATTERN = re.compile(r"(`+|\*\*|__|\*|_)")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class Article:
    """A canonical English source article used by the experimental chatbot."""

    path: Path
    source_path: str
    source_hash: str
    slug: str
    title: str
    summary: str
    body: str
    generation_cost: dict[str, Any] | None


@dataclass(frozen=True)
class Section:
    heading: str
    text: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_source() -> Path:
    return _project_root() / "web" / "src" / "content" / "articles"


def _default_output() -> Path:
    return _project_root() / "rag" / "data"


def _split_frontmatter(raw: str, path: Path) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---"):
        raise ValueError(f"{path}: expected YAML frontmatter beginning with '---'.")

    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path}: expected YAML frontmatter beginning with '---'.")

    closing_index = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing_index is None:
        raise ValueError(f"{path}: frontmatter has no closing '---'.")

    try:
        metadata = yaml.safe_load("".join(lines[1:closing_index])) or {}
    except yaml.YAMLError as error:
        raise ValueError(f"{path}: invalid YAML frontmatter: {error}") from error
    if not isinstance(metadata, dict):
        raise ValueError(f"{path}: frontmatter must be a mapping.")
    return metadata, "".join(lines[closing_index + 1 :]).strip()


def _required_text(metadata: dict[str, Any], field: str, path: Path) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: frontmatter field '{field}' must be a non-empty string.")
    return value.strip()


def load_canonical_articles(source_dir: Path) -> list[Article]:
    """Load only canonical English article Markdown files under *source_dir*."""

    if not source_dir.is_dir():
        raise FileNotFoundError(f"Article source directory does not exist: {source_dir}")

    articles: list[Article] = []
    seen_slugs: set[str] = set()
    for path in sorted(source_dir.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        metadata, body = _split_frontmatter(raw, path)
        if metadata.get("language") != "en" or metadata.get("translationOf"):
            continue

        title = _required_text(metadata, "title", path)
        summary = _required_text(metadata, "summary", path)
        generation_cost = metadata.get("generationCost")
        if generation_cost is not None and not isinstance(generation_cost, dict):
            raise ValueError(f"{path}: frontmatter field 'generationCost' must be a mapping when present.")
        slug = path.stem
        if slug in seen_slugs:
            raise ValueError(f"Duplicate canonical English article slug: '{slug}'.")
        seen_slugs.add(slug)
        articles.append(
            Article(
                path=path,
                source_path=path.relative_to(source_dir).as_posix(),
                source_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                slug=slug,
                title=title,
                summary=summary,
                body=body,
                generation_cost=generation_cost,
            )
        )

    if not articles:
        raise ValueError(f"No canonical English articles found under {source_dir}.")
    return articles


def _clean_markdown(value: str) -> str:
    value = HTML_COMMENT_PATTERN.sub(" ", value)
    value = MARKDOWN_IMAGE_PATTERN.sub(r"\1", value)
    value = MARKDOWN_LINK_PATTERN.sub(r"\1", value)
    value = INLINE_MARKDOWN_PATTERN.sub("", value)
    value = value.replace("&nbsp;", " ")
    return WHITESPACE_PATTERN.sub(" ", value).strip()


def _sections_from_body(article: Article) -> list[Section]:
    """Turn an article into sections, retaining useful heading context."""

    sections: list[Section] = [Section(article.title, article.summary)]
    current_heading = article.title
    current_lines: list[str] = []
    in_fenced_code = False

    def flush() -> None:
        text = _clean_markdown("\n".join(current_lines))
        if text:
            sections.append(Section(current_heading, text))

    for line in article.body.splitlines():
        if line.strip().startswith("```"):
            in_fenced_code = not in_fenced_code
            continue
        heading = None if in_fenced_code else HEADING_PATTERN.match(line)
        if heading:
            flush()
            current_lines.clear()
            current_heading = _clean_markdown(heading.group(2)) or article.title
        else:
            current_lines.append(line)
    flush()
    return sections


def _split_words(text: str, max_words: int, overlap_words: int) -> list[str]:
    words = text.split()
    if len(words) <= max_words:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(len(words), start + max_words)
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - overlap_words
    return chunks


def _combine_small_sections(sections: Iterable[Section], min_words: int) -> list[Section]:
    combined: list[Section] = []
    pending: Section | None = None
    for section in sections:
        if not section.text:
            continue
        if pending is None:
            pending = section
            continue
        if len(pending.text.split()) < min_words:
            heading = pending.heading if pending.heading == section.heading else f"{pending.heading} — {section.heading}"
            pending = Section(
                heading=heading,
                text=f"{pending.text}\n\n{section.text}",
            )
        else:
            combined.append(pending)
            pending = section
    if pending is not None:
        combined.append(pending)
    return combined


def _humanise_key(key: str) -> str:
    labels = {
        "totalUsd": "total recorded cost",
        "costUsd": "recorded cost",
        "wallTimeMs": "wall time",
        "requestWallTimeMs": "request wall time",
        "latencyMs": "latency",
        "generationTimeMs": "generation time",
    }
    if key in labels:
        return labels[key]
    words = re.sub(r"(?<!^)(?=[A-Z])", " ", key).replace("_", " ")
    return words.strip().lower()


def _format_cost_value(key: str, value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)) and key.lower().endswith("usd"):
        return f"USD {value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (int, float)) and key.lower().endswith("ms"):
        return f"{value:g} ms ({value / 1000:g} seconds)"
    return str(value)


def _scalar_details(value: dict[str, Any], *, excluded: set[str] | None = None) -> str:
    excluded = excluded or set()
    details = [
        f"{_humanise_key(key)}: {_format_cost_value(key, item)}"
        for key, item in value.items()
        if key not in excluded and not isinstance(item, (dict, list))
    ]
    return "; ".join(details)


def _cost_text(article: Article) -> str | None:
    cost = article.generation_cost
    if not cost:
        return None

    paragraphs = [f"AI production cost and model information for the Saral article “{article.title}”."]
    overall = _scalar_details(cost, excluded={"stages"})
    if overall:
        paragraphs.append(f"Overall run — {overall}.")

    stages = cost.get("stages", [])
    if not isinstance(stages, list):
        raise ValueError(f"{article.path}: generationCost.stages must be a list when present.")
    for stage_number, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            raise ValueError(f"{article.path}: generationCost stage {stage_number} must be a mapping.")
        stage_name = str(stage.get("key") or f"stage {stage_number}").replace("_", " ")
        stage_details = _scalar_details(stage, excluded={"key", "calls"})
        paragraphs.append(f"Stage: {stage_name}. {stage_details}." if stage_details else f"Stage: {stage_name}.")

        calls = stage.get("calls", [])
        if not isinstance(calls, list):
            raise ValueError(f"{article.path}: calls for generationCost stage '{stage_name}' must be a list.")
        for call_number, call in enumerate(calls, start=1):
            if not isinstance(call, dict):
                raise ValueError(f"{article.path}: call {call_number} in stage '{stage_name}' must be a mapping.")
            call_details = _scalar_details(call)
            paragraphs.append(f"{stage_name} call {call_number} — {call_details}.")
    return "\n\n".join(paragraphs)


def _cost_models(cost: dict[str, Any] | None) -> list[str]:
    models: set[str] = set()
    if not cost:
        return []
    for stage in cost.get("stages", []):
        if not isinstance(stage, dict):
            continue
        for call in stage.get("calls", []):
            if not isinstance(call, dict):
                continue
            display_name = call.get("modelName")
            model_id = call.get("model")
            if display_name and model_id:
                models.add(f"{display_name} ({model_id})")
            elif display_name or model_id:
                models.add(str(display_name or model_id))
    return sorted(models, key=str.casefold)


def _cost_stage_summaries(cost: dict[str, Any] | None) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    if not cost:
        return summaries
    for stage in cost.get("stages", []):
        if not isinstance(stage, dict):
            continue
        stage_models: set[str] = set()
        for call in stage.get("calls", []):
            if not isinstance(call, dict):
                continue
            display_name = call.get("modelName")
            model_id = call.get("model")
            if display_name and model_id:
                stage_models.add(f"{display_name} ({model_id})")
            elif display_name or model_id:
                stage_models.add(str(display_name or model_id))
        summaries.append(
            {
                "key": stage.get("key"),
                "status": stage.get("status"),
                "costUsd": stage.get("costUsd"),
                "costStatus": stage.get("costStatus"),
                "models": sorted(stage_models, key=str.casefold),
            }
        )
    return summaries


def chunk_articles(
    articles: Iterable[Article], *, max_words: int = 220, min_words: int = 40,
    overlap_words: int = 30, site_url: str = DEFAULT_SITE_URL,
) -> list[dict[str, Any]]:
    """Create readable, heading-aware chunks ready for embedding."""

    if max_words <= 0 or min_words < 0 or overlap_words < 0 or overlap_words >= max_words:
        raise ValueError("Chunk settings require max_words > 0 and 0 <= overlap_words < max_words.")

    site_url = site_url.rstrip("/")
    chunks: list[dict[str, Any]] = []
    for article in articles:
        sections = _combine_small_sections(_sections_from_body(article), min_words)
        chunk_number = 0
        for section in sections:
            for part_number, text in enumerate(_split_words(section.text, max_words, overlap_words), start=1):
                chunk_number += 1
                chunks.append(
                    {
                        "id": f"{article.slug}:{chunk_number}",
                        "articleSlug": article.slug,
                        "articleTitle": article.title,
                        "articleUrl": f"{site_url}/articles/{article.slug}/",
                        "language": "en",
                        "chunkType": "lesson",
                        "heading": section.heading,
                        "part": part_number,
                        "text": text,
                        "wordCount": len(text.split()),
                        "sourcePath": article.source_path,
                        "sourceHash": article.source_hash,
                    }
                )
        cost_text = _cost_text(article)
        if cost_text:
            cost_parts = _split_words(cost_text, max_words, overlap_words)
            models = _cost_models(article.generation_cost)
            for part_number, text in enumerate(cost_parts, start=1):
                chunks.append(
                    {
                        "id": f"{article.slug}:cost:{part_number}",
                        "articleSlug": article.slug,
                        "articleTitle": article.title,
                        "articleUrl": f"{site_url}/articles/{article.slug}/#ai-production-cost",
                        "language": "en",
                        "chunkType": "generation-cost",
                        "heading": "AI production cost and models",
                        "part": part_number,
                        "text": text,
                        "wordCount": len(text.split()),
                        "sourcePath": article.source_path,
                        "sourceHash": article.source_hash,
                        "totalCostUsd": article.generation_cost.get("totalUsd"),
                        "costStatus": article.generation_cost.get("costStatus"),
                        "models": models,
                        "stageSummaries": _cost_stage_summaries(article.generation_cost),
                    }
                )
    return chunks


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(content)
        temporary_path = Path(temporary.name)
    temporary_path.replace(path)


def _create_embeddings(
    chunks: list[dict[str, Any]],
    model_name: str,
    embedding_client: OpenRouterEmbeddingClient | None = None,
):
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError(
            "NumPy is required to save embeddings. Install dependencies with "
            "'python -m pip install -r rag/requirements.txt', or run with --skip-embeddings."
        ) from error

    owns_client = embedding_client is None
    client = embedding_client or OpenRouterEmbeddingClient(model_name)
    if client.model != model_name:
        raise ValueError(
            f"Embedding client model '{client.model}' does not match requested model '{model_name}'."
        )
    try:
        vectors = np.asarray(
            client.embed_documents([str(chunk["text"]) for chunk in chunks]),
            dtype="float32",
        )
    finally:
        if owns_client:
            client.close()

    if vectors.ndim != 2 or vectors.shape[0] != len(chunks) or vectors.shape[1] == 0:
        raise RuntimeError("OpenRouter returned an invalid document embedding matrix.")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise RuntimeError("OpenRouter returned a zero-length document embedding.")
    return vectors / norms


def _atomic_save_numpy(path: Path, vectors: Any) -> None:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".npy", dir=path.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    np.save(temporary_path, vectors)
    temporary_path.replace(path)


def ingest(
    source_dir: Path,
    output_dir: Path,
    *,
    site_url: str = DEFAULT_SITE_URL,
    model_name: str = DEFAULT_MODEL,
    max_words: int = 220,
    min_words: int = 40,
    overlap_words: int = 30,
    skip_embeddings: bool = False,
    embedding_client: OpenRouterEmbeddingClient | None = None,
) -> dict[str, Any]:
    """Create artifacts and return the manifest, for use by the CLI and tests."""

    articles = load_canonical_articles(source_dir)
    chunks = chunk_articles(
        articles,
        max_words=max_words,
        min_words=min_words,
        overlap_words=overlap_words,
        site_url=site_url,
    )
    if not chunks:
        raise ValueError("No text chunks were generated from the canonical English articles.")

    embedding: dict[str, Any] = {"model": model_name, "normalized": True}
    if skip_embeddings:
        embedding["status"] = "skipped"
    else:
        vectors = _create_embeddings(chunks, model_name, embedding_client)
        embedding.update({"status": "created", "dimensions": int(vectors.shape[1])})

    manifest = {
        "schemaVersion": SCHEMA_VERSION,
        "createdAt": datetime.now(UTC).isoformat(),
        "language": "en",
        "articleCount": len(articles),
        "chunkCount": len(chunks),
        "lessonChunkCount": sum(chunk.get("chunkType") == "lesson" for chunk in chunks),
        "costChunkCount": sum(chunk.get("chunkType") == "generation-cost" for chunk in chunks),
        "chunking": {"maxWords": max_words, "minWords": min_words, "overlapWords": overlap_words},
        "embedding": embedding,
        "sources": [
            {"slug": article.slug, "path": article.source_path, "sha256": article.source_hash}
            for article in articles
        ],
    }
    # Do all fallible work before replacing an existing index. A model-loading
    # failure must leave the previous artifacts mutually consistent.
    output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(
        output_dir / "chunks.json",
        json.dumps({"schemaVersion": SCHEMA_VERSION, "language": "en", "chunks": chunks}, indent=2, ensure_ascii=False)
        + "\n",
    )
    if not skip_embeddings:
        _atomic_save_numpy(output_dir / "embeddings.npy", vectors)
    _atomic_write_text(output_dir / "index-manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Saral's English article retrieval artifacts.")
    parser.add_argument("--source", type=Path, default=_default_source(), help="Directory containing article Markdown files.")
    parser.add_argument("--output", type=Path, default=_default_output(), help="Directory for generated artifacts.")
    parser.add_argument("--site-url", default=os.getenv("SARAL_SITE_URL", DEFAULT_SITE_URL), help="Public Saral site URL.")
    parser.add_argument(
        "--model",
        default=os.getenv("SARAL_EMBEDDING_MODEL", DEFAULT_MODEL),
        help="OpenRouter embedding model name.",
    )
    parser.add_argument("--max-words", type=int, default=220, help="Maximum words in one chunk.")
    parser.add_argument("--min-words", type=int, default=40, help="Merge sections shorter than this many words.")
    parser.add_argument("--overlap-words", type=int, default=30, help="Word overlap when splitting long sections.")
    parser.add_argument("--skip-embeddings", action="store_true", help="Write chunks and manifest without loading a model.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = ingest(
        args.source,
        args.output,
        site_url=args.site_url,
        model_name=args.model,
        max_words=args.max_words,
        min_words=args.min_words,
        overlap_words=args.overlap_words,
        skip_embeddings=args.skip_embeddings,
    )
    print(f"Indexed {manifest['articleCount']} English articles into {manifest['chunkCount']} chunks.")
    print(f"Wrote {args.output / 'chunks.json'}")
    print(f"Wrote {args.output / 'index-manifest.json'}")
    if manifest["embedding"]["status"] == "created":
        print(f"Wrote {args.output / 'embeddings.npy'} ({manifest['embedding']['dimensions']} dimensions)")
    else:
        print("Embeddings were skipped; run again without --skip-embeddings to create embeddings.npy.")


if __name__ == "__main__":
    main()
