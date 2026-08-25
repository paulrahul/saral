"""Vercel Python entrypoint for the Saral chatbot ASGI application."""

if __package__:
    from .app.main import app
else:
    from app.main import app


__all__ = ["app"]
