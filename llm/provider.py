import asyncio
import logging
import os
from collections.abc import Iterable, Mapping
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
    def __init__(self):
        pass

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
        self._evaluator = Evaluator()

    async def run(self):
        logger.info("Starting EasyTutorAgent run")
        # Generate topics
        results = await self._topic_generator.generate(
            message="Suggest a topic for teaching AI",
            trace="EasyTutor: Topic Generation")

        # Evaluate topics
        for k, v in results.items():
            print(f"Model {k}'s topic: {v}")
        logger.info("Finished EasyTutorAgent run")

if __name__ == "__main__":
    agent = EasyTutorAgent()
    asyncio.run(agent.run())
