"""Agents that generate EasyTutor topics, Markdown content, and lesson images."""

import base64
import binascii
import hashlib
import io
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

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

    Begin your response with exactly one HTML comment in this form:
    <!-- saral-summary: one short, clear summary of this lesson -->
    The summary must be a single plain-language sentence, no more than 180
    characters. It must tell a reader what they will learn, rather than repeat
    a heading or use a question. The comment is metadata and will not be shown
    in the lesson.

    After the comment, provide the lesson in Markdown, starting with one level
    one heading. Do not add frontmatter, a preamble, an explanation, or any
    other metadata.
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
    width: int
    height: int


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
    photograph. Never render the lesson title, headings, logos, watermarks, or
    interface text. Use text only when it is essential to make the diagram
    understandable; keep it to a few short, large, high-contrast labels and
    avoid decorative text, paragraphs, tiny lettering, or unnecessary numbers.
    Do not depict a real person as a recognisable individual.

    Match the website's calm visual palette. Prefer very light warm sand or
    pale yellow backgrounds with muted, natural greens as the main colors.
    Useful reference colors are warm sand #FFFDF7, soft green #EAF4EE, muted
    green #247356, and deep green #185B43. If other colors are necessary for
    meaning or contrast, keep them soft, restrained, and harmonious with this
    palette. Avoid neon, highly saturated, harsh, or clashing colors. The
    illustration must remain clear and attractive against both the site's
    light sand theme and its dark green theme.

    Compose the image as a 1.91:1 landscape social-media preview intended for
    an exact final size of 1200 by 630 pixels. Keep important subjects and any
    essential labels comfortably inside the center safe area so they are not
    clipped by preview cards.

    Return PNG most preferably. WebP is acceptable only when PNG is not
    available. Do not return SVG or any other vector format. Keep the image
    visually simple and efficiently compressible, with a target file size
    below 500 KB. The image will also be used as a social-media preview.

    The lesson content below may contain Markdown. Use its meaning only; do
    not reproduce Markdown syntax, links, or text from it in the image.

    """

    API_URL = "https://openrouter.ai/api/v1/images"
    TARGET_SIZE = (1200, 630)
    MAX_FILE_SIZE = 500 * 1024
    BACKGROUND_COLOR = (255, 253, 247)

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
    def _normalize_image(cls, image_bytes: bytes) -> tuple[bytes, str, str]:
        """Return a social-preview-safe 1200x630 PNG or baseline JPEG."""
        try:
            with Image.open(io.BytesIO(image_bytes)) as source:
                source.seek(0)
                source = ImageOps.exif_transpose(source)
                rgba = source.convert("RGBA")
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError(
                "OpenRouter returned an unsupported or invalid raster image"
            ) from error

        # Composite transparency onto the site's warm sand color before
        # resizing. ImageOps.contain preserves the complete illustration;
        # padding is preferable to cropping instructional details or labels.
        background = Image.new("RGBA", rgba.size, (*cls.BACKGROUND_COLOR, 255))
        source_rgb = Image.alpha_composite(background, rgba).convert("RGB")
        contained = ImageOps.contain(
            source_rgb,
            cls.TARGET_SIZE,
            method=Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGB", cls.TARGET_SIZE, cls.BACKGROUND_COLOR)
        offset = (
            (cls.TARGET_SIZE[0] - contained.width) // 2,
            (cls.TARGET_SIZE[1] - contained.height) // 2,
        )
        canvas.paste(contained, offset)

        png = io.BytesIO()
        canvas.save(png, format="PNG", optimize=True, compress_level=9)
        if png.tell() <= cls.MAX_FILE_SIZE:
            return png.getvalue(), ".png", "image/png"

        # Detailed or photographic generations can make PNG unnecessarily
        # large. A baseline RGB JPEG is widely supported by preview crawlers.
        for quality in (90, 85, 80, 75, 70, 65, 60, 55):
            jpeg = io.BytesIO()
            canvas.save(
                jpeg,
                format="JPEG",
                quality=quality,
                optimize=True,
                progressive=False,
            )
            if jpeg.tell() <= cls.MAX_FILE_SIZE:
                return jpeg.getvalue(), ".jpg", "image/jpeg"

        raise ValueError("Could not compress the generated image below 500 KB")

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
        try:
            raw_image = base64.b64decode(image_data, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("OpenRouter returned invalid base64 image data") from error
        normalized_image, extension, media_type = self._normalize_image(raw_image)

        version = hashlib.sha256(normalized_image).hexdigest()[:10]
        output = self._output_dir / f"{self._slugify(topic)}-{version}{extension}"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(normalized_image)
        generated = GeneratedImage(
            path=f"/images/{output.name}",
            alt_text=self._alt_text(topic),
            model=model_name,
            media_type=media_type,
            width=self.TARGET_SIZE[0],
            height=self.TARGET_SIZE[1],
        )
        logger.info("Finished image generation for topic '%s' at %s", topic, output)
        return generated
