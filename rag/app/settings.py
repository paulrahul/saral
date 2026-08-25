"""Runtime configuration for the experimental Saral chatbot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_ALLOWED_ORIGINS = (
    "https://saralai-seven.vercel.app",
    "http://localhost:4321",
    "http://127.0.0.1:4321",
)
DEFAULT_LOGO_URL = "https://saralai-seven.vercel.app/saral-logo.png"


def _as_bool(value: str | None) -> bool:
    return value is not None and value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    relevance_threshold: float
    top_k: int
    model: str | None
    retrieval_only: bool
    allowed_origins: tuple[str, ...]
    logo_url: str = DEFAULT_LOGO_URL

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        package_root = Path(__file__).resolve().parents[1]
        origins = os.getenv("SARAL_ALLOWED_ORIGINS")
        return cls(
            data_dir=Path(os.getenv("SARAL_RAG_DATA_DIR", package_root / "data")),
            relevance_threshold=float(os.getenv("SARAL_CHAT_RELEVANCE_THRESHOLD", "0.35")),
            top_k=int(os.getenv("SARAL_CHAT_TOP_K", "3")),
            model=os.getenv("SARAL_CHAT_MODEL") or None,
            retrieval_only=_as_bool(os.getenv("SARAL_CHAT_RETRIEVAL_ONLY")),
            allowed_origins=tuple(item.strip() for item in origins.split(",") if item.strip())
            if origins
            else DEFAULT_ALLOWED_ORIGINS,
            logo_url=os.getenv("SARAL_LOGO_URL", DEFAULT_LOGO_URL),
        )

    def validate(self) -> None:
        if not -1.0 <= self.relevance_threshold <= 1.0:
            raise ValueError("SARAL_CHAT_RELEVANCE_THRESHOLD must be between -1 and 1.")
        if not 1 <= self.top_k <= 5:
            raise ValueError("SARAL_CHAT_TOP_K must be between 1 and 5.")
        if not self.model and not self.retrieval_only:
            raise ValueError(
                "Set SARAL_CHAT_MODEL for OpenRouter answers, or set SARAL_CHAT_RETRIEVAL_ONLY=true for local testing."
            )
