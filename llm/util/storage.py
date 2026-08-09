"""Storage helpers for generated EasyTutor topics and content."""

import json
import logging
import string
from pathlib import Path


logger = logging.getLogger(__name__)
GENERATED_DIR = Path(__file__).resolve().parents[1] / "generated"
TOPICS_FILE = GENERATED_DIR / "topics.json"
CONTENT_FILE = GENERATED_DIR / "content.json"
APPROVAL_FILE = GENERATED_DIR / "approved_content.json"
TAGS_FILE = GENERATED_DIR / "tags.json"
IMAGES_FILE = GENERATED_DIR / "images.json"
BROAD_TAGS = (
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
)


def _read_json(path: Path) -> dict:
    with path.open() as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return data


def _is_evaluation_map(data: dict) -> bool:
    return bool(data) and all(
        isinstance(evaluation, dict) and "result" in evaluation
        for evaluation in data.values()
    )


def read_evaluations(path: Path, main_topic: str) -> dict[str, dict]:
    data = _read_json(path)
    if main_topic in data:
        evaluations = data[main_topic]
        if not isinstance(evaluations, dict):
            raise ValueError(f"Expected evaluations for main topic {main_topic!r}")
        return evaluations

    # Support the old flat shape until this main topic is written again.
    return data if _is_evaluation_map(data) else {}


def write_evaluations(
    path: Path,
    main_topic: str,
    new_evaluations: dict[str, dict],
) -> None:
    try:
        journals = _read_json(path)
    except FileNotFoundError:
        journals = {}
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new history", path)
        journals = {}

    if _is_evaluation_map(journals):
        journals = {main_topic: journals}

    evaluations = journals.get(main_topic, {})
    if not isinstance(evaluations, dict):
        raise ValueError(f"Expected evaluations for main topic {main_topic!r}")

    for model_name in new_evaluations:
        evaluations.pop(model_name, None)
    journals[main_topic] = {**new_evaluations, **evaluations}

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as file:
        json.dump(journals, file, indent=2)
        file.write("\n")


def read_content(topic: str) -> dict[str, str]:
    try:
        content_by_topic = _read_json(CONTENT_FILE)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; ignoring the content cache", CONTENT_FILE)
        return {}

    content = content_by_topic.get(topic, {})
    if not isinstance(content, dict):
        raise ValueError(f"Expected cached content for topic {topic!r}")
    return {
        model: value
        for model, value in content.items()
        if isinstance(model, str) and isinstance(value, str)
    }


def write_content(topic: str, content: dict[str, str]) -> None:
    try:
        content_by_topic = _read_json(CONTENT_FILE)
    except FileNotFoundError:
        content_by_topic = {}
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new cache", CONTENT_FILE)
        content_by_topic = {}

    content_by_topic.setdefault(topic, {}).update(content)
    CONTENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CONTENT_FILE.open("w") as file:
        json.dump(content_by_topic, file, indent=2)
        file.write("\n")


def read_approved_content(topic: str) -> dict | None:
    try:
        approvals = _read_json(APPROVAL_FILE)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; ignoring the approval cache", APPROVAL_FILE)
        return None

    approval = approvals.get(topic)
    if approval is None:
        return None
    if not isinstance(approval, dict):
        raise ValueError(f"Expected approval for topic {topic!r}")
    return approval


def write_approved_content(topic: str, model: str, tags: list[str]) -> None:
    try:
        approvals = _read_json(APPROVAL_FILE)
    except FileNotFoundError:
        approvals = {}
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new approval cache", APPROVAL_FILE)
        approvals = {}

    approval = approvals.setdefault(topic, {})
    approval["model"] = model
    approval["tags"] = tags
    APPROVAL_FILE.parent.mkdir(parents=True, exist_ok=True)
    with APPROVAL_FILE.open("w") as file:
        json.dump(approvals, file, indent=2)
        file.write("\n")


def read_generated_image(topic: str) -> dict[str, str] | None:
    """Return cached public image metadata for a topic, if present."""
    try:
        images = _read_json(IMAGES_FILE)
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; ignoring the image cache", IMAGES_FILE)
        return None

    image = images.get(topic)
    if image is None:
        return None
    if not isinstance(image, dict) or not all(
        isinstance(image.get(field), str) and image[field]
        for field in ("path", "altText", "model", "mediaType")
    ):
        raise ValueError(f"Expected valid generated-image metadata for topic {topic!r}")
    return {
        "path": image["path"],
        "altText": image["altText"],
        "model": image["model"],
        "mediaType": image["mediaType"],
    }


def write_generated_image(
    topic: str,
    path: str,
    alt_text: str,
    model: str,
    media_type: str,
) -> None:
    """Persist image metadata after its asset has been written to public/images."""
    try:
        images = _read_json(IMAGES_FILE)
    except FileNotFoundError:
        images = {}
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new image cache", IMAGES_FILE)
        images = {}

    images[topic] = {
        "path": path,
        "altText": alt_text,
        "model": model,
        "mediaType": media_type,
    }
    IMAGES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with IMAGES_FILE.open("w") as file:
        json.dump(images, file, indent=2)
        file.write("\n")


def read_specific_tags() -> list[str]:
    try:
        data = _read_json(TAGS_FILE)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new tag registry", TAGS_FILE)
        return []

    tags = data.get("specific", [])
    return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []


def add_specific_tag(tag: str) -> None:
    tags = read_specific_tags()
    if tag not in tags:
        tags.append(tag)

    TAGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with TAGS_FILE.open("w") as file:
        json.dump({"specific": tags}, file, indent=2)
        file.write("\n")


def normalize_topic(topic: str) -> str:
    return topic.lower().strip().translate(str.maketrans("", "", string.punctuation))


def read_cached_topic_values(path: Path, main_topic: str) -> list[str]:
    return [topic for _, topic in read_cached_topic_items(path, main_topic)]


def read_used_topic_values(path: Path, main_topic: str) -> list[str]:
    evaluations = read_evaluations(path, main_topic)
    if not evaluations:
        return []
    return next(iter(evaluations.values())).get("used", [])


def read_cached_topic_items(path: Path, main_topic: str) -> list[tuple[str, str]]:
    evaluations = read_evaluations(path, main_topic)
    if not evaluations:
        return []
    latest_evaluation = next(iter(evaluations.values()))
    return [
        (model, topic)
        for topic, model in latest_evaluation.get("result", {}).items()
    ]
