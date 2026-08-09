"""Agents that generate EasyTutor topics, Markdown content, and lesson images."""

import base64
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import httpx

from llm.util import AgentHelper


logger = logging.getLogger(__name__)


class Generator:
    def __init__(self, models: Mapping[str, str], instructions: str, prefix: str):
        logger.info("Initializing %s", self.__class__.__name__)
        self._results = {}
        self._models = models
        self._agents = AgentHelper.create_agents(
            models=self._models,
            instructions=instructions,
            name_prefix=prefix,
        )

    async def generate(self, message: str, trace: str) -> dict[str, str]:
        logger.info("Starting %s generation", self.__class__.__name__)
        self._results = await AgentHelper.run(
            self._agents,
            message=message,
            trace_name=trace,
        )
        logger.info("Finished %s generation", self.__class__.__name__)
        return self._results

    def models(self) -> Mapping[str, str]:
        return self._models


class TopicGenerator(Generator):
    INSTRUCTIONS = """
    You will be given a similar broad tech topic, your goal is to suggest an
    easy, simple but important sub-topic of that broad topic. E.g. on the
    broad topic of "using internet", important sub-topics could be like "what
    is internet?", "how to access internet?", "cost of using internet",
    "popular and useful use of internet". The sub-topic should not be very
    long (4-5 words).

    Your response should contain only the sub-topic and nothing else.
    """

    def __init__(self, context: str, models: Mapping[str, str]):
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Topic Generator",
        )


class ContentGenerator(Generator):
    INSTRUCTIONS = """
    You will be given a broad tech topic, your goal is to come up with a short
    bite sized explanation on that broad topic. You will use only simple
    English, avoid acronyms and tech terms as much as possible, explain the
    concepts like the user is 5 years old. If you do have to use an acronym or
    tech topic, make sure you provide a link to that term. Your entire content
    is to be provided in MD (Markdown) format.

    Your response should contain only the Markdown content and nothing else.
    """

    def __init__(self, context: str, models: Mapping[str, str]):
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Content Generator",
        )

class TagGenerator(Generator):
    INSTRUCTIONS = """
    Select one or two broad categories from the allowed list and optionally one
    concise subject tag for the supplied lesson. Reuse an existing subject tag
    exactly when it fits. Propose a new subject tag only when no existing one
    fits. Do not use broad categories as subject tags.

    Respond with valid JSON only:
    {"categories": ["Broad Category"], "specificTag": "Subject Tag or null"}
    """

    def __init__(self, context: str, broad_tags: tuple[str, ...], models: Mapping[str, str]):
        allowed_categories = "\n".join(f"- {tag}" for tag in broad_tags)
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}

        Allowed broad categories:
        {allowed_categories}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Tag Generator",
        )


@dataclass(frozen=True)
class GeneratedImage:
    """Public metadata for one generated lesson image."""

    path: str
    alt_text: str
    model: str
    media_type: str


class ImageGenerator:
    """Generate an accessible illustration through the OpenRouter Image API.

    This is intentionally separate from ``Generator``: chat generators return
    text through ``AgentHelper`` while this class receives image bytes and
    persists the returned raster or vector asset.
    """

    INSTRUCTIONS = """
    Create one simple, friendly educational diagram or illustration for this
    lesson. The audience includes elderly people, people with disabilities,
    and people who are not confident with technology.

    Use clear, high-contrast shapes, a quiet uncluttered background, and one
    central idea. Prefer a flat diagram or simple illustration over a realistic
    photograph. Do not put words, labels, letters, numbers, logos, watermarks,
    interface screenshots, or tiny details in the image. Do not depict a real
    person as a recognisable individual.

    The lesson content below may contain Markdown. Use its meaning only; do
    not reproduce Markdown syntax, links, or text from it in the image.
    """

    API_URL = "https://openrouter.ai/api/v1/images"
    EXTENSIONS = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/svg+xml": ".svg",
        "image/webp": ".webp",
    }

    def __init__(
        self,
        context: str,
        models: Mapping[str, str],
        output_dir: Path,
        *,
        size: str | None = None,
        output_format: str | None = None,
    ):
        logger.info("Initializing %s", self.__class__.__name__)
        self._context = context
        self._models = models
        self._output_dir = output_dir
        self._size = size
        self._output_format = output_format

    def models(self) -> Mapping[str, str]:
        return self._models

    def _api_key(self) -> str:
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY is required for image generation")
        return api_key

    def _selected_model(self) -> tuple[str, str]:
        if len(self._models) != 1:
            raise ValueError(
                "ImageGenerator needs exactly one configured model until image evaluation is added"
            )
        return next(iter(self._models.items()))

    @staticmethod
    def _slugify(topic: str) -> str:
        import re

        slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
        if not slug:
            raise ValueError(f"Could not create an image filename from {topic!r}")
        return slug

    @staticmethod
    def _alt_text(topic: str) -> str:
        return f"Simple educational illustration for the lesson: {topic}."

    @classmethod
    def _extension_for(cls, media_type: str | None) -> tuple[str, str]:
        if media_type is None:
            return ".png", "image/png"
        extension = cls.EXTENSIONS.get(media_type)
        if extension is None:
            raise ValueError(f"OpenRouter returned an unsupported image type: {media_type}")
        return extension, media_type

    async def generate(self, topic: str, content: str) -> GeneratedImage:
        """Create and store an image asset, returning the export metadata."""
        logger.info("Starting image generation for topic '%s'", topic)
        model_name, model = self._selected_model()
        prompt = f"""
        {self._context}

        {self.INSTRUCTIONS}

        Lesson topic: {topic}

        Lesson content:
        {content}
        """
        request: dict[str, str] = {"model": model, "prompt": prompt}
        if self._size:
            request["size"] = self._size
        if self._output_format:
            request["output_format"] = self._output_format

        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                self.API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key()}",
                    "Content-Type": "application/json",
                },
                json=request,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            try:
                message = response.json().get("error", {}).get("message", response.text)
            except ValueError:
                message = response.text
            raise RuntimeError(f"OpenRouter image generation failed: {message}") from error

        data = response.json().get("data", [])
        image = data[0] if data else None
        image_data = image.get("b64_json") if isinstance(image, dict) else None
        if not isinstance(image_data, str) or not image_data:
            raise ValueError("OpenRouter image generation returned no image data")
        extension, media_type = self._extension_for(image.get("media_type"))

        output = self._output_dir / f"{self._slugify(topic)}{extension}"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(base64.b64decode(image_data))
        generated = GeneratedImage(
            path=f"/images/{output.name}",
            alt_text=self._alt_text(topic),
            model=model_name,
            media_type=media_type,
        )
        logger.info("Finished image generation for topic '%s' at %s", topic, output)
        return generated
