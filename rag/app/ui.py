"""Routes for the static Saral chat page and its public branding settings."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"


def register_ui(app: FastAPI, *, logo_url: str, site_url: str) -> None:
    """Keep /chat/ working both with local Uvicorn and Vercel's static CDN."""

    @app.get("/chat", include_in_schema=False)
    @app.get("/chat/", include_in_schema=False)
    async def chat_page() -> FileResponse:
        return FileResponse(PUBLIC_DIR / "chat" / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/chat-config", include_in_schema=False)
    async def chat_config() -> JSONResponse:
        # Never expose the API key or model configuration to the browser.
        return JSONResponse(
            {"logoUrl": logo_url, "siteUrl": site_url},
            headers={"Cache-Control": "no-store"},
        )

    # Vercel serves public/** directly from its CDN. Uvicorn needs an explicit
    # fallback after the API routes so local /chat/ works with the same assets.
    if not os.getenv("VERCEL"):
        app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="chat-assets")
