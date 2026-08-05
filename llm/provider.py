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
TOPICS_EVAL_FILE = Path(__file__).with_name("topics_eval.json")


def _read_latest_json_entry(path: Path) -> dict:
    with path.open() as fp:
        data = json.load(fp)

    if isinstance(data, list):
        return data[-1] if data else {}

    return data


def _read_json_entries(path: Path) -> list[dict]:
    with path.open() as fp:
        data = json.load(fp)

    if isinstance(data, list):
        return data

    return [data]


def _append_json_entry(path: Path, entry: dict) -> None:
    entries = []
    try:
        with path.open() as fp:
            data = json.load(fp)
            entries = data if isinstance(data, list) else [data]
    except FileNotFoundError:
        pass
    except json.JSONDecodeError:
        logger.info("Existing JSON file at %s is invalid; starting a new history", path)

    entries.append(entry)
    with path.open("w") as fp:
        json.dump(entries, fp, indent=2)


def _normalize_topic(topic: str) -> str:
    return topic.lower().strip().translate(str.maketrans("", "", string.punctuation))


def _read_cached_topic_values(path: Path) -> list[str]:
    topics = []
    for entry in _read_json_entries(path):
        topics.extend(entry.values())

    return topics


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
    def __init__(self, instructions, prefix):
        logger.info("Initializing %s", self.__class__.__name__)
        self._results = []
        self._models = {
            "Z.ai: GLM 5.2": "z-ai/glm-5.2",
            "DeepSeek V4 Flash 0731": "deepseek/deepseek-v4-flash-0731"
        }

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

    Always respond with valid JSON in one of these formats:
    {"result": "yes", "reason": ""}
    {"result": "no", "reason": "string"}
    {"result": [0, 1, 2], "reason": ""}
    When asked to evaluate a content, result should contain yes or no, yes
    indicating content passed the evaluation and vice versa. When asked to
    rank a given set of contents, result should contain a list of content
    indices (0 indexed) in descending order of ranking i.e. first index in
    result should point to the highest ranked content and so on. Each content
    a set of contents will be separated by a new line. Reason is to be
    populated when there is a negative evaluation of any content providing the
    reason it was deemed negative.
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

        Generator.__init__(self, instructions=instructions, prefix="Topic Generator")

class ContentGenerator(Generator):
    INSTRUCTIONS = """
    """
    def __init__(self, context):
        instructions = f"""
        {context}

        {ContentGenerator.INSTRUCTIONS}
        """

        Generator.__init__(self, instructions=instructions, prefix="Content Generator")

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
        self._evaluator = Evaluator(context=EasyTutorAgent.CONTEXT)

    async def run(self, new=False):
        logger.info("Starting EasyTutorAgent run")

        MAIN_TOPIC = "Teaching AI"

        cached_topics = []
        topic_results = {}
        try:
            topic_results = _read_latest_json_entry(TOPICS_FILE)
            cached_topics = _read_cached_topic_values(TOPICS_FILE)
            if topic_results and not new:
                logger.info("Using latest cached topics entry from %s", TOPICS_FILE)
        except FileNotFoundError:
            logger.info(
                "No existing topics file found at %s; generating new topics",
                TOPICS_FILE,
            )
        except json.JSONDecodeError as e:
            logger.info("Could not parse topics file; generating new topics: %s", e)
        except (PermissionError, OSError) as e:
            logger.info("Error reading topics file: %s", e)

        if new or len(topic_results) == 0:
            # Generate topics
            existing_topics = "\n".join(f"- {topic}" for topic in cached_topics)
            topic_prompt = f"Suggest a topic for {MAIN_TOPIC}"
            if existing_topics:
                topic_prompt = f"""
                Suggest a topic for {MAIN_TOPIC}

                Do not suggest any of these already-used topics:
                {existing_topics}
                """

            topic_results = await self._topic_generator.generate(
                message=topic_prompt,
                trace="EasyTutor: Topic Generation")

            existing_topic_set = {
                _normalize_topic(topic)
                for topic in cached_topics
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
                logger.info("Finished EasyTutorAgent run")
                return

            _append_json_entry(TOPICS_FILE, topic_results)

        # Print topics
        for k, v in topic_results.items():
            print(f"Model {k}'s topic: {v}")

        normalized_eval_results = {}
        if not new:
            try:
                normalized_eval_results = _read_latest_json_entry(TOPICS_EVAL_FILE)
            except FileNotFoundError:
                logger.info(
                    "No existing evaluation file found at %s; evaluating topics",
                    TOPICS_EVAL_FILE,
                )
            except json.JSONDecodeError as e:
                logger.info(
                    "Could not parse evaluation file; evaluating topics: %s",
                    e,
                )
            except (PermissionError, OSError) as e:
                logger.info("Error reading evaluation file: %s", e)

        if normalized_eval_results:
            logger.info(
                "Using latest cached evaluation entry from %s",
                TOPICS_EVAL_FILE,
            )
            print(normalized_eval_results)
            logger.info("Finished EasyTutorAgent run")
            return

        # Evaluate topics
        topics = "\n".join(topic_results.values())
        eval_message=f"""
        Rank the following sub-topics for the main topic {MAIN_TOPIC}

        {topics}
        """
        # print(f"{eval_message=}")

        eval_results = await self._evaluator.evaluate(
            message=eval_message,
            trace="EasyTutor: Topic Evaluation"
        )

        topics_by_index = list(topic_results.items())
        for eval_key, eval_output in eval_results.items():
            eval_json = json.loads(eval_output)
            eval_result = eval_json["result"]
            reason = eval_json.get("reason", "")

            if isinstance(eval_result, list):
                normalized_result = {
                    topics_by_index[index][0]: topics_by_index[index][1]
                    for index in eval_result
                }
            else:
                normalized_result = {
                    topic: eval_result
                    for topic in topic_results.values()
                }

            normalized_eval_results[eval_key] = {
                "result": normalized_result,
                "reason": reason,
            }

        _append_json_entry(TOPICS_EVAL_FILE, normalized_eval_results)

        print(normalized_eval_results)
        logger.info("Finished EasyTutorAgent run")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--new', '-n', action='store_true', help='Generate new')
    args = parser.parse_args()

    agent = EasyTutorAgent()
    asyncio.run(agent.run(args.new))
