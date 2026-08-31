"""FastAPI host for Saral's experimental chatbot and static chat UI."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from .llm import OpenRouterAnswerGenerator
from .rag import NO_RELEVANT_LESSON, RagResult, RagService
from .settings import Settings
from .ui import register_ui


MAX_REQUEST_BYTES = 4_096


class AskRequest(BaseModel):
    question: Annotated[str, Field(min_length=1, max_length=1_000)]


class Source(BaseModel):
    title: str
    url: str
    heading: str
    score: float


class AskResponse(BaseModel):
    relevant: bool
    answer: str
    sources: list[Source]


class RetrievalOnlyAnswerGenerator:
    """Skip answer generation; semantic queries still use paid embeddings."""

    async def generate(self, _question: str, chunks) -> str:
        excerpts = "\n\n".join(f"**{chunk.article_title}**\n{chunk.text}" for chunk in chunks)
        return f"Retrieval-only test mode: these Saral lesson excerpts may help.\n\n{excerpts}"


def _result_to_response(result: RagResult) -> AskResponse:
    payload = result.to_dict()
    return AskResponse(
        relevant=payload["relevant"],
        answer=payload["answer"] or NO_RELEVANT_LESSON,
        sources=[Source(**source) for source in payload["sources"]],
    )


def create_app(settings: Settings | None = None, *, service: RagService | None = None) -> FastAPI:
    """Build the ASGI app. Loading the retrieval index is deferred to startup."""

    settings = settings or Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings.validate()
        active_service = service or RagService.load(settings.data_dir, relevance_threshold=settings.relevance_threshold)
        generator: Any
        if settings.retrieval_only:
            generator = RetrievalOnlyAnswerGenerator()
        else:
            generator = OpenRouterAnswerGenerator(settings.model or "")
        app.state.service = active_service
        app.state.generator = generator
        try:
            yield
        finally:
            await active_service.close()
            if isinstance(generator, OpenRouterAnswerGenerator):
                await generator.close()

    app = FastAPI(title="Saral Chat", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Request body is too large."})
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        return RedirectResponse(url="/chat/")

    @app.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        service: RagService = request.app.state.service
        return {
            "status": "ok",
            "mode": "retrieval-only" if settings.retrieval_only else "openrouter",
            "embeddingModel": service._index.model_name,
            "embeddingDimensions": service._index.dimensions,
        }

    @app.post("/ask", response_model=AskResponse)
    async def ask(payload: AskRequest, request: Request) -> AskResponse:
        try:
            result = await request.app.state.service.ask(
                payload.question,
                request.app.state.generator,
                limit=settings.top_k,
            )
            return _result_to_response(result)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="Saral could not prepare an answer right now.") from error

    register_ui(app, logo_url=settings.logo_url, site_url=settings.site_url)
    return app


app = create_app()
