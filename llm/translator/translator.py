"""Translate approved lesson Markdown into the site's supported languages."""

import asyncio
import logging
from collections.abc import Mapping

from agents import Agent

from llm.util import AgentHelper


logger = logging.getLogger(__name__)


class Translator:
    """Run the configured translation model(s) once for each target language."""

    LANGUAGES = {
        "bn": "Bengali",
        "hi": "Hindi",
    }

    INSTRUCTIONS = """
    Translate the supplied English lesson into the requested target language.
    The readers include elderly people, people with disabilities, and people
    who are not confident using technology. Use plain, warm, everyday language
    that is easy to read.

    Preserve the Markdown structure: headings, paragraphs, ordered and
    unordered lists, emphasis, and links. Translate visible link text, but do
    not change link URLs. Do not add information, remove safety advice, or
    change the meaning. Do not translate proper product names unless there is a
    widely used local-language name.

    Translate every reader-facing field. This includes the level-one Markdown
    heading (the article title), the value of the saral-summary comment, all
    visible lesson content, and the value of the saral-image-alt comment.

    For an acronym or technical term that has no natural translation, use the
    target-language transliteration followed by the original English term in
    parentheses on its first occurrence. For example, in Hindi: एआई (AI).
    Use only the target-language transliteration for later occurrences. Apply
    this rule separately to each such term, and do not alter link URLs.

    The input may begin with an HTML comment in this exact form:
    <!-- saral-summary: lesson summary -->.
    Keep that comment at the beginning, preserve `saral-summary` exactly, and
    translate only its summary value. It is metadata and must not be turned
    into visible text.

    The input ends with an HTML comment in this exact form:
    <!-- saral-image-alt: image description -->.
    Keep that comment at the end, preserve `saral-image-alt` exactly, and
    translate only its image-description value. It is metadata and must not be
    turned into visible text.

    Return only the translated Markdown body. Do not add frontmatter, a title
    outside the source content, a language label, notes, or an explanation.
    """

    def __init__(self, models: Mapping[str, str], context: str, prefix: str):
        logger.info("Initializing %s", self.__class__.__name__)
        self._models = models
        self._agents: dict[str, dict[str, Agent]] = {}

        for language_code, language_name in self.LANGUAGES.items():
            instructions = f"""
            {context}

            {self.INSTRUCTIONS}

            Target language: {language_name}
            """
            self._agents[language_code] = AgentHelper.create_agents(
                models=self._models,
                instructions=instructions,
                name_prefix=f"{prefix} {language_name}",
            )

    async def generate(self, message: str, trace: str) -> dict[str, dict[str, str]]:
        """Return ``{language_code: {model_name: translated_markdown}}``."""
        logger.info("Starting %s translation", self.__class__.__name__)
        language_codes = tuple(self.LANGUAGES)
        translations = await asyncio.gather(
            *(
                AgentHelper.run(
                    self._agents[language_code],
                    message=message,
                    trace_name=f"{trace}: {self.LANGUAGES[language_code]}",
                )
                for language_code in language_codes
            )
        )
        results = dict(zip(language_codes, translations, strict=True))
        logger.info("Finished %s translation", self.__class__.__name__)
        return results

    def models(self) -> Mapping[str, str]:
        return self._models

    def languages(self) -> Mapping[str, str]:
        return self.LANGUAGES
