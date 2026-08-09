"""Agents that generate EasyTutor topics and Markdown content."""

import logging
from collections.abc import Mapping

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
