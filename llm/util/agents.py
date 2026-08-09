"""OpenRouter agent creation and execution helpers."""

import asyncio
import logging
import os
from collections.abc import Iterable, Mapping
from typing import Any

from agents import (
    Agent,
    OpenAIChatCompletionsModel,
    Runner,
    set_default_openai_client,
    set_tracing_export_api_key,
    trace,
)
from dotenv import load_dotenv
from openai import AsyncOpenAI


logger = logging.getLogger(__name__)


class AgentHelper:
    """Create and run OpenRouter-backed agents using shared client state."""

    BASE_URL = "https://openrouter.ai/api/v1"
    DEFAULT_HEADERS = {
        "HTTP-Referer": "https://myapp.example",
        "X-Title": "My Personal Agents",
    }
    _openrouter_client: AsyncOpenAI | None = None
    _openrouter_api_key: str | None = None
    _tracing_api_key: str | None = None
    _is_dotenv_loaded = False
    _is_tracing_configured = False

    def __new__(cls):
        raise TypeError(f"{cls.__name__} is a utility class and cannot be instantiated")

    @classmethod
    def _load_env(cls) -> None:
        if not cls._is_dotenv_loaded:
            logger.debug("Loading environment variables from dotenv")
            load_dotenv()
            cls._is_dotenv_loaded = True

    @classmethod
    def _load_api_key(cls, name: str) -> str:
        cls._load_env()
        value = os.environ[name]
        if not value:
            raise ValueError(f"Could not load env variable {name}")
        return value

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
            raise ValueError("AgentHelper is already configured with a different API key")

        return cls._openrouter_client

    @classmethod
    def _configure_tracing(cls, api_key: str | None = None) -> None:
        api_key = api_key or cls._tracing_api_key or cls._load_api_key("OPENAI_API_KEY")

        if cls._tracing_api_key is not None and cls._tracing_api_key != api_key:
            raise ValueError("AgentHelper tracing is already configured with a different API key")

        if not cls._is_tracing_configured:
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
        openrouter_client = cls._get_openrouter_client(api_key)
        set_default_openai_client(openrouter_client, use_for_tracing=False)
        cls._configure_tracing(tracing_api_key)

        logger.info("Creating agent '%s' with model '%s'", name, model)
        return Agent(
            name=name,
            instructions=instructions,
            model=OpenAIChatCompletionsModel(
                model=model,
                openai_client=openrouter_client,
            ),
        )

    @classmethod
    def create_agents(
        cls,
        models: Mapping[str, str],
        instructions: str,
        name_prefix: str = "Agent",
    ) -> dict[str, Agent]:
        logger.info("Creating %d agents with prefix '%s'", len(models), name_prefix)
        return {
            name: cls.create_openrouter_agent(
                model=model,
                name=f"{name_prefix} {name}",
                instructions=instructions,
            )
            for name, model in models.items()
        }

    @staticmethod
    async def run(
        agents: Iterable[Agent] | Mapping[Any, Agent],
        message: str,
        trace_name: str = "AgentHelper Run",
    ) -> dict[Any, Any]:
        agent_items = list(agents.items()) if isinstance(agents, Mapping) else [(agent, agent) for agent in agents]
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
