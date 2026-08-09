"""Evaluator agent for EasyTutor topics and content."""

from collections.abc import Mapping
import logging

from llm.util import AgentHelper


logger = logging.getLogger(__name__)


class Evaluator:
    INSTRUCTIONS = """
    Your current role is to evaluate the quality, relevance and eligibility
    of any content provided to you that could potentially be used for
    teaching. You might also be asked to rank a given set of content based
    on these criteria.

    Always respond with valid JSON in one of these formats:
    {"result": "yes", "reason": ""}
    {"result": "no", "reason": "string"}
    {"result": [0, 1, 2], "reason": "string"}
    When asked to evaluate a content, result should contain yes or no, yes
    indicating content passed the evaluation and vice versa. When asked to
    rank a given set of contents, result should contain a list of content
    indices (0 indexed) in descending order of ranking i.e. first index in
    result should point to the highest ranked content and so on. Each content
    in a set of contents will be separated by a new line. Reason is to be
    populated when there is a negative evaluation of any content. Include the
    reason for every excluded topic in one string, with each reason separated
    by a newline.

    The result list must contain the 0-indexed topic indices in descending
    rank order after deduplication and negative filtering.
    """

    def __init__(self, models: Mapping[str, str], instructions: str, prefix: str):
        logger.info("Initializing %s", self.__class__.__name__)
        instructions = f"""
        {instructions}

        {Evaluator.INSTRUCTIONS}
        """
        self._results = {}
        self._models = models
        self._agents = AgentHelper.create_agents(
            models=self._models,
            instructions=instructions,
            name_prefix=prefix,
        )

    async def evaluate(self, message: str, trace: str) -> dict[str, str]:
        logger.info("Starting %s evaluation", self.__class__.__name__)
        self._results = await AgentHelper.run(
            self._agents,
            message=message,
            trace_name=trace,
        )
        logger.info("Finished %s evaluation", self.__class__.__name__)
        return self._results

    def models(self) -> Mapping[str, str]:
        return self._models

class TopicEvaluator(Evaluator):
    INSTRUCTIONS = """
    Your content here will be either a single topic or a set of topics.

    Deduplicate topics, including semantic duplicates. If multiple topics
    mean the same thing, keep only the best one. Also discard any topic
    that has a negative evaluation for quality, relevance, eligibility, or
    usefulness for the target learners.
    """

    def __init__(self, context: str, models: Mapping[str, str]):
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Topic Evaluator",
        )

class ContentEvaluator(Evaluator):
    INSTRUCTIONS = """
    Your content here will be either a single short bite sized description or a
    set of such bite sized descriptions.
    """

    def __init__(self, context: str, models: Mapping[str, str]):
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Content Evaluator",
        )


class TagEvaluator(Evaluator):
    INSTRUCTIONS = """
    You will receive a proposed subject tag and a numbered list of existing
    subject tags, followed by the proposed tag as the final option. Choose the
    one canonical tag that best represents the same concept. Reuse an existing
    tag when it is a semantic duplicate; otherwise choose the proposed tag.

    Return exactly one selected index in the result list.
    """

    def __init__(self, context: str, models: Mapping[str, str]):
        instructions = f"""
        {context}

        {self.INSTRUCTIONS}
        """
        super().__init__(
            models=models,
            instructions=instructions,
            prefix="Tag Evaluator",
        )
