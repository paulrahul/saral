"""Load and validate model choices for the EasyTutor pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MODEL_CONFIG_FILE = Path(__file__).with_name("models.json")
MODEL_COMPONENTS = (
    "topic_generator",
    "content_generator",
    "tag_generator",
    "image_generator",
    "translator",
    "topic_evaluator",
    "content_evaluator",
    "tag_evaluator",
)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Model config is missing: {path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Model config contains invalid JSON at line {error.lineno}, column {error.colno}: {path}"
        ) from error
    except OSError as error:
        raise ValueError(f"Could not read model config {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Model config must contain a JSON object: {path}")
    return value


def load_model_config(path: Path = MODEL_CONFIG_FILE) -> dict[str, dict[str, str]]:
    """Return validated display-name to model-ID mappings for each component."""
    document = _read_object(path)
    if document.get("version") != 1:
        raise ValueError(f"Model config {path} must have version 1")
    unexpected_fields = set(document) - {"version", "models", "alternatives"}
    if unexpected_fields:
        raise ValueError(
            f"Model config {path} has unsupported fields: {', '.join(sorted(unexpected_fields))}"
        )

    models = document.get("models")
    if not isinstance(models, dict):
        raise ValueError(f"Model config {path} must contain a 'models' object")
    missing = set(MODEL_COMPONENTS) - set(models)
    unexpected = set(models) - set(MODEL_COMPONENTS)
    if missing:
        raise ValueError(f"Model config {path} is missing: {', '.join(sorted(missing))}")
    if unexpected:
        raise ValueError(f"Model config {path} has unknown components: {', '.join(sorted(unexpected))}")

    result: dict[str, dict[str, str]] = {}
    for component in MODEL_COMPONENTS:
        result[component] = _validate_model_mapping(
            models[component],
            component=component,
            section="models",
            require_models=True,
        )

    alternatives = document.get("alternatives", {})
    if not isinstance(alternatives, dict):
        raise ValueError(f"Model config {path} field 'alternatives' must be an object")
    unknown_alternatives = set(alternatives) - set(MODEL_COMPONENTS)
    if unknown_alternatives:
        raise ValueError(
            f"Model config {path} has alternatives for unknown components: "
            f"{', '.join(sorted(unknown_alternatives))}"
        )
    for component, configured_models in alternatives.items():
        normalized = _validate_model_mapping(
            configured_models,
            component=component,
            section="alternatives",
            require_models=False,
        )
        duplicate_names = set(normalized) & set(result[component])
        if duplicate_names:
            raise ValueError(
                f"Model config {path} repeats active model names in alternatives for {component!r}: "
                f"{', '.join(sorted(duplicate_names))}"
            )
    return result


def _validate_model_mapping(
    value: object,
    *,
    component: str,
    section: str,
    require_models: bool,
) -> dict[str, str]:
    if not isinstance(value, dict) or (require_models and not value):
        qualifier = "a non-empty object" if require_models else "an object"
        raise ValueError(f"Model config {section} entry {component!r} must be {qualifier}")
    normalized: dict[str, str] = {}
    for display_name, model_id in value.items():
        if not isinstance(display_name, str) or not display_name.strip():
            raise ValueError(
                f"Model config {section} entry {component!r} has an invalid display name"
            )
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError(
                f"Model config {section} entry {component!r} has an invalid model ID "
                f"for {display_name!r}"
            )
        normalized[display_name.strip()] = model_id.strip()
    return normalized
