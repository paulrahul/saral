import asyncio
import json
import logging
import os
import string
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AsyncOpenAI

from agents import (
    Agent,
    Runner,
    OpenAIChatCompletionsModel,
    set_default_openai_client,
    set_tracing_export_api_key,
    trace
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)
TOPICS_FILE = Path(__file__).with_name("topics.json")
CONTENT_FILE = Path(__file__).with_name("content.json")


def _read_evaluations(path: Path) -> dict[str, dict]:
    with path.open() as fp:
        data = json.load(fp)

    if isinstance(data, dict):
        return data

    evaluations = {}
    for entry in reversed(data):
        for model_name, evaluation in entry.items():
            evaluations.setdefault(model_name, evaluation)

    return evaluations


def _write_evaluations(path: Path, new_evaluations: dict[str, dict]) -> None:
    evaluations = {}
    try:
        evaluations = _read_evaluations(path)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new history", path)

    # Put the newest results first and replace any older result from that model.
    for model_name in new_evaluations:
        evaluations.pop(model_name, None)
    evaluations = {**new_evaluations, **evaluations}

    with path.open("w") as fp:
        json.dump(evaluations, fp, indent=2)
        fp.write("\n")


def _write_content(topic: str, content: dict[str, str]) -> None:
    content_by_topic = {}
    try:
        with CONTENT_FILE.open() as fp:
            content_by_topic = json.load(fp)
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new cache", CONTENT_FILE)

    content_by_topic.setdefault(topic, {}).update(content)
    with CONTENT_FILE.open("w") as fp:
        json.dump(content_by_topic, fp, indent=2)
        fp.write("\n")


def _normalize_topic(topic: str) -> str:
    return topic.lower().strip().translate(str.maketrans("", "", string.punctuation))


def _read_cached_topic_values(path: Path) -> list[str]:
    return [topic for _, topic in _read_cached_topic_items(path)]


def _read_used_topic_values(path: Path) -> list[str]:
    evaluations = _read_evaluations(path)
    if not evaluations:
        return []

    latest_evaluation = next(iter(evaluations.values()))
    return latest_evaluation.get("used", [])


def _read_cached_topic_items(path: Path) -> list[tuple[str, str]]:
    evaluations = _read_evaluations(path)
    if not evaluations:
        return []

    latest_evaluation = next(iter(evaluations.values()))
    return [
        (model, topic)
        for topic, model in latest_evaluation.get("result", {}).items()
    ]


def _loadenv(name, check=True):
    val = os.environ[name]
    if check and not val:
        raise ValueError(f"Could not load env variable {name}")

    return val


class AgentHelper:
    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_HEADERS = {
        # Optional but recommended by OpenRouter
        "HTTP-Referer": "https://myapp.example",
        "X-Title": "My Personal Agents",
    }
    _openrouter_client: AsyncOpenAI | None = None
    _openrouter_api_key: str | None = None
    _tracing_api_key: str | None = None
    _is_dotenv_loaded = False
    _is_tracing_configured = False

    def __new__(cls):
        raise TypeError(
            f"{cls.__name__} is a utility class and cannot be instantiated"
        )

    @classmethod
    def _load_env(cls) -> None:
        if not cls._is_dotenv_loaded:
            logger.debug("Loading environment variables from dotenv")
            load_dotenv()
            cls._is_dotenv_loaded = True

    @classmethod
    def _load_api_key(cls, name: str) -> str:
        cls._load_env()
        return _loadenv(name)

    @classmethod
    def _get_openrouter_client(cls, api_key: str | None = None) -> AsyncOpenAI:
        api_key = api_key or cls._load_api_key("OPENROUTER_API_KEY")

        if cls._openrouter_client is None:
            logger.info("Creating OpenRouter client")
            cls._openrouter_client = AsyncOpenAI(
                api_key=api_key,
                base_url=cls.BASE_URL,
                default_headers=cls.DEFAULT_HEADERS,
            )
            cls._openrouter_api_key = api_key
        else:
            logger.debug("Reusing cached OpenRouter client")

        if cls._openrouter_api_key != api_key:
            raise ValueError(
                "AgentHelper is already configured with a different API key"
            )

        return cls._openrouter_client

    @classmethod
    def _configure_tracing(cls, api_key: str | None = None) -> None:
        api_key = (
            api_key
            or cls._tracing_api_key
            or cls._load_api_key("OPENAI_API_KEY")
        )

        if cls._tracing_api_key is not None and cls._tracing_api_key != api_key:
            raise ValueError(
                "AgentHelper tracing is already configured with a different API key"
            )

        if not cls._is_tracing_configured:
            # This key is ONLY used to upload traces.
            # Inference will still go through OpenRouter.
            logger.info("Configuring tracing export")
            set_tracing_export_api_key(api_key)
            cls._tracing_api_key = api_key
            cls._is_tracing_configured = True

    @classmethod
    def create_openrouter_agent(
        cls,
        model: str,
        name: str,
        instructions: str,
        *,
        api_key: str | None = None,
        tracing_api_key: str | None = None,
    ) -> Agent:
        # --------------------------------------------------------------------
        # Configure OpenRouter client (used ONLY for inference)
        # --------------------------------------------------------------------

        openrouter_client = cls._get_openrouter_client(api_key)

        # Use this client for inference only.
        # Do NOT use it for tracing.
        set_default_openai_client(
            openrouter_client,
            use_for_tracing=False,
        )

        # --------------------------------------------------------------------
        # Configure tracing
        # --------------------------------------------------------------------

        cls._configure_tracing(tracing_api_key)

        # --------------------------------------------------------------------
        # Model
        # --------------------------------------------------------------------
        agent_model = OpenAIChatCompletionsModel(
            model=model,
            openai_client=openrouter_client,
        )

        # --------------------------------------------------------------------
        # Agent
        # --------------------------------------------------------------------
        # Agent that generates tech topics
        logger.info("Creating agent '%s' with model '%s'", name, model)
        agent = Agent(
            name=name,
            instructions=instructions,
            model=agent_model,
        )

        return agent

    @classmethod
    def create_agents(
        cls,
        models: Mapping[str, str],
        instructions: str,
        name_prefix: str = "Agent",
    ) -> dict[str, Agent]:
        logger.info("Creating %d agents with prefix '%s'", len(models), name_prefix)
        agents = {}
        for name, model in models.items():
            agents[name] = cls.create_openrouter_agent(
                model=model,
                name=f"{name_prefix} {name}",
                instructions=instructions,
            )

        return agents

    @staticmethod
    async def run(
        agents: Iterable[Agent] | Mapping[Any, Agent],
        message: str,
        trace_name: str = "AgentHelper Run",
    ) -> dict[Any, Any]:
        if isinstance(agents, Mapping):
            agent_items = list(agents.items())
        else:
            agent_items = [(agent, agent) for agent in agents]

        logger.info("Running %d agents for trace '%s'", len(agent_items), trace_name)
        with trace(trace_name):
            results = await asyncio.gather(
                *(Runner.run(agent, message) for _, agent in agent_items)
            )
        logger.info("Completed %d agent runs for trace '%s'", len(results), trace_name)

        return {
            key: result.final_output
            for (key, _), result in zip(agent_items, results)
        }

class Generator(object):
    def __init__(self, models, instructions, prefix):
        logger.info("Initializing %s", self.__class__.__name__)
        self._results = []
        self._models = models

        self._agents = AgentHelper.create_agents(
            models=self._models, instructions=instructions,
            name_prefix=prefix
        )

    async def generate(self, message, trace):
        logger.info("Starting %s generation", self.__class__.__name__)
        self._results = await AgentHelper.run(
            self._agents,
            message=message,
            trace_name=trace,
        )
        logger.info("Finished %s generation", self.__class__.__name__)
        return self._results

class Evaluator(object):
    INSTRUCTIONS = """
    Your current role is to evaluate the quality, relevance and eligibility
    of any content provided to you that could potentially be used for
    teaching. You might also be asked to rank a given set of content based
    on these criteria.

    Deduplicate topics, including semantic duplicates. If multiple topics
    mean the same thing, keep only the best one. Also discard any topic
    that has a negative evaluation for quality, relevance, eligibility, or
    usefulness for the target learners.

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
    def __init__(self, context):
        logger.info("Initializing %s", self.__class__.__name__)

        instructions = f"""
        {context}

        {Evaluator.INSTRUCTIONS}
        """
        self._results = []
        self._models = {
            "MoonshotAI: Kimi K3": "moonshotai/kimi-k3",
        }

        self._agents = AgentHelper.create_agents(
            models=self._models, instructions=instructions,
            name_prefix="Easytutor: Evaluator"
        )

    async def evaluate(self, message, trace):
        logger.info("Starting %s evaluation", self.__class__.__name__)
        self._results = await AgentHelper.run(
            self._agents,
            message=message,
            trace_name=trace,
        )
        logger.info("Finished %s evaluation", self.__class__.__name__)
        return self._results

class TopicGenerator(Generator):
    INSTRUCTIONS = """
    You will be given a similar broad tech topic, your goal is to suggest an
    easy, simple but important  sub-topic of that broad topic. E.g. on the
    broad topic of "using internet", important sub-topics could be like "what
    is internet?", "how to access internet?", "cost of using internet",
    "popular and useful use of internet". The sub-topic should not be very
    long (4-5 words).

    Your response should contain only the sub-topic and nothing else.
    """
    def __init__(self, context):
        instructions = f"""
        {context}

        {TopicGenerator.INSTRUCTIONS}
        """
        Generator.__init__(
            self,
            models = {
                "Z.ai: GLM 5.2": "z-ai/glm-5.2",
                "DeepSeek V4 Flash 0731": "deepseek/deepseek-v4-flash-0731",
                "OpenAI: GPT-5.6 Luna": "openai/gpt-5.6-luna"
            },
            instructions=instructions,
            prefix="Topic Generator"
        )

class ContentGenerator(Generator):
    INSTRUCTIONS = """
    You will be given a broad tech topic, your goal is to come up with a short
    byte sized explanation on that broad topic. You will use only simple
    English, avoid acronyms and tech terms as much as possible, explain the
    concepts like the user is 5 years old. If you do have to use an acronym or
    tech topic, make sure you provide a link to that term. Your entire content
    is to be provided in MD (Markdown) format.

    Your response should contain only the Markdown content and nothing else.
    """
    def __init__(self, context):
        instructions = f"""
        {context}

        {ContentGenerator.INSTRUCTIONS}
        """
        Generator.__init__(
            self,
            models = {
                "Z.ai: GLM 5.2": "z-ai/glm-5.2",
                "OpenAI: GPT-5.6 Luna": "openai/gpt-5.6-luna"
            },
            instructions=instructions,
            prefix="Content Generator")

class EasyTutorAgent(object):
    CONTEXT = """
    you are a tech educator specialising in tech education for elderly, poor and
    the usually tech marginalised people in society. you do not teach  advanced
    levels or concepts. your mission is always enabling marginalised sections on
    the basics of emerging technologies in very simple terms and descriptions,
    so that the students can later on themselves get deeper into any topic if
    they are interested. The goal is to ensure that marginalised groups do not
    get left behind in key technologies which affect the society and are often
    needed for personal needs. E.g. using internet, using smart phones, using
    messenger apps, using websites, placing online orders, using google.
    """

    def __init__(self):
        logger.info("Initializing EasyTutorAgent")
        self._topic_generator = TopicGenerator(context=EasyTutorAgent.CONTEXT)
        self._content_generator = ContentGenerator(context=EasyTutorAgent.CONTEXT)
        self._evaluator = Evaluator(context=EasyTutorAgent.CONTEXT)

    async def _rank_topics(
        self,
        main_topic: str,
        topic_items: list[tuple[str, str]],
    ) -> None:
        topics_to_rank = "\n".join(
            f"{index}. {topic}"
            for index, (_, topic) in enumerate(topic_items)
        )

        eval_message = f"""
        Rank the following sub-topics for the main topic {main_topic}.

        {topics_to_rank}
        """
        eval_results = await self._evaluator.evaluate(
            message=eval_message,
            trace="EasyTutor: Topic Evaluation"
        )

        normalized_eval_results = {}
        try:
            existing_evaluations = _read_evaluations(TOPICS_FILE)
        except FileNotFoundError:
            existing_evaluations = {}
        for eval_key, eval_output in eval_results.items():
            eval_json = json.loads(eval_output)
            ranked_indices = eval_json["result"]
            reason = eval_json.get("reason", "")
            if isinstance(reason, list):
                reason = "\n".join(str(item) for item in reason)
            else:
                reason = str(reason)

            if not isinstance(ranked_indices, list):
                raise ValueError(
                    f"Evaluator {eval_key!r} returned a non-ranking result: "
                    f"{ranked_indices!r}"
                )

            normalized_result = {}
            for index in ranked_indices:
                model, topic = topic_items[index]
                normalized_result[topic] = model

            normalized_eval_results[eval_key] = {
                "result": normalized_result,
                "reason": reason,
                "used": existing_evaluations.get(eval_key, {}).get("used", []),
            }

        _write_evaluations(TOPICS_FILE, normalized_eval_results)
        print(normalized_eval_results)

    def _get_next_topic(self) -> tuple[str, str] | None:
        try:
            topic_items = _read_cached_topic_items(TOPICS_FILE)
        except FileNotFoundError:
            return None

        return topic_items[0] if topic_items else None

    def _remove_used_topic(self, topic: str) -> None:
        evaluations = _read_evaluations(TOPICS_FILE)
        evaluator_model, latest_evaluation = next(iter(evaluations.items()))
        if latest_evaluation["result"].pop(topic, None) is not None:
            latest_evaluation.setdefault("used", []).append(topic)
        _write_evaluations(TOPICS_FILE, {evaluator_model: latest_evaluation})
        logger.info("Removed used topic '%s' from the topic cache", topic)

    async def generate_topics(self, main_topic):
        cached_topics = []
        used_topics = []
        topic_results = {}
        try:
            cached_topics = _read_cached_topic_values(TOPICS_FILE)
            used_topics = _read_used_topic_values(TOPICS_FILE)
        except FileNotFoundError:
            logger.info(
                "No existing topics file found at %s",
                TOPICS_FILE,
            )
        except json.JSONDecodeError as e:
            logger.info("Could not parse topics file; generating new topics: %s", e)
        except (PermissionError, OSError) as e:
            logger.info("Error reading topics file: %s", e)

        # Generate topics
        all_existing_topics = cached_topics + used_topics
        existing_topics = "\n".join(f"- {topic}" for topic in all_existing_topics)
        topic_prompt = f"Suggest a topic for {main_topic}"
        if existing_topics:
            topic_prompt = f"""
            Suggest a topic for {main_topic}

            Do not suggest any of these already-used topics:
            {existing_topics}
            """

        topic_results = await self._topic_generator.generate(
            message=topic_prompt,
            trace="EasyTutor: Topic Generation")

        existing_topic_set = {
            _normalize_topic(topic)
            for topic in all_existing_topics
        }
        unique_topic_results = {
            model: topic
            for model, topic in topic_results.items()
            if _normalize_topic(topic) not in existing_topic_set
        }
        skipped_count = len(topic_results) - len(unique_topic_results)
        if skipped_count:
            logger.info("Skipped %d repeated generated topics", skipped_count)

        topic_results = unique_topic_results
        if len(topic_results) == 0:
            logger.info("No new unique topics were generated")
            return

        logger.info("New topics generated: %s", topic_results)
        all_topic_items = _read_cached_topic_items(TOPICS_FILE) + list(
            topic_results.items()
        )
        await self._rank_topics(main_topic, all_topic_items)


    async def run(self):
        logger.info("Starting EasyTutorAgent run")

        MAIN_TOPIC = "Teaching AI"

        next_topic = self._get_next_topic()
        if next_topic is None:
            logger.info("No ranked topics remain; generating and ranking new topics")
            await self.generate_topics(MAIN_TOPIC)
            next_topic = self._get_next_topic()

        if next_topic is None:
            logger.info("No topic is available for content generation")
            return

        model, topic = next_topic
        logger.info("Generating content for top-ranked topic '%s' from '%s'", topic, model)
        content_results = await self._content_generator.generate(
            message=topic,
            trace="EasyTutor: Content Generation",
        )
        _write_content(topic, content_results)
        self._remove_used_topic(topic)

        logger.info("Finished EasyTutorAgent run")

if __name__ == "__main__":
    agent = EasyTutorAgent()
    asyncio.run(agent.run())
