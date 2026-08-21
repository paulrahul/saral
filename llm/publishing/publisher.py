"""Commit and push a bounded set of generated publication artifacts."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx


logger = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SITE_URL = "https://saralai-seven.vercel.app/"


@dataclass(frozen=True)
class Publication:
    """A bounded group of local artifacts to commit and push together."""

    title: str
    paths: tuple[Path, ...]
    removed_paths: tuple[Path, ...] = ()


class _LatestArticleTitleParser(HTMLParser):
    """Extract the first article heading from the homepage's latest section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._latest_depth = 0
        self._heading_depth = 0
        self._title_parts: list[str] = []
        self.title: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = dict(attrs).get("class", "") or ""
        if self._latest_depth:
            self._latest_depth += 1
        elif tag == "section" and "latest" in classes.split():
            self._latest_depth = 1

        if self._latest_depth and self.title is None:
            if self._heading_depth:
                self._heading_depth += 1
            elif tag == "h2":
                self._heading_depth = 1

    def handle_endtag(self, tag: str) -> None:
        if self._heading_depth:
            self._heading_depth -= 1
            if self._heading_depth == 0 and tag == "h2":
                self.title = " ".join("".join(self._title_parts).split())
        if self._latest_depth:
            self._latest_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._heading_depth:
            self._title_parts.append(data)


def _run_git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return result


def _latest_article_title(document: str) -> str | None:
    parser = _LatestArticleTitleParser()
    parser.feed(document)
    parser.close()
    return parser.title


def _cache_busted_url(url: str, revision: str) -> str:
    parts = urlsplit(url)
    query = urlencode({"saral_revision": revision})
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", query, parts.fragment))


async def _wait_for_latest_article(expected_title: str, revision: str) -> None:
    site_url = os.getenv("SARAL_SITE_URL", DEFAULT_SITE_URL)
    timeout = float(os.getenv("SARAL_DEPLOY_TIMEOUT_SECONDS", "300"))
    poll_interval = float(os.getenv("SARAL_DEPLOY_POLL_SECONDS", "10"))
    if timeout <= 0 or poll_interval <= 0:
        raise ValueError("Deployment timeout and poll interval must be positive")

    deadline = time.monotonic() + timeout
    last_observation = "the site did not return a response"
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        while True:
            try:
                response = await client.get(_cache_busted_url(site_url, revision))
                response.raise_for_status()
                deployed_title = _latest_article_title(response.text)
                if deployed_title == expected_title:
                    logger.info("Verified deployed article '%s' at %s", expected_title, site_url)
                    return
                last_observation = (
                    f"latest article was {deployed_title!r}"
                    if deployed_title is not None
                    else "the latest article title could not be found"
                )
            except httpx.HTTPError as error:
                last_observation = str(error)

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out after {timeout:g}s waiting for {expected_title!r} at "
                    f"{site_url}: {last_observation}"
                )
            await asyncio.sleep(min(poll_interval, remaining))


async def publish(publication: Publication, *, verify_latest: bool = True) -> str:
    """Commit and push only the supplied paths, optionally verifying the homepage."""
    discovered_root = await asyncio.to_thread(
        _run_git, REPOSITORY_ROOT, "rev-parse", "--show-toplevel"
    )
    if Path(discovered_root.stdout.strip()).resolve() != REPOSITORY_ROOT:
        raise RuntimeError(f"Expected git repository root to be {REPOSITORY_ROOT}")

    removed_paths = {path.resolve(strict=False) for path in publication.removed_paths}
    resolved_paths: set[Path] = set()
    relative_paths: list[str] = []
    for path in publication.paths:
        resolved = path.resolve(strict=False)
        resolved_paths.add(resolved)
        try:
            relative = resolved.relative_to(REPOSITORY_ROOT)
        except ValueError as error:
            raise ValueError(f"Refusing to publish path outside the repository: {path}") from error
        if not resolved.is_file() and resolved not in removed_paths:
            raise FileNotFoundError(f"Publication artifact does not exist: {resolved}")
        relative_path = relative.as_posix()
        if relative_path not in relative_paths:
            relative_paths.append(relative_path)
    unexpected_removals = removed_paths - resolved_paths
    if unexpected_removals:
        raise ValueError("Every removed publication path must also be present in paths")
    if not relative_paths:
        raise ValueError("Publication requires at least one artifact path")

    # --all includes removed superseded images. The bounded pathspec preserves
    # every unrelated working-tree and index change.
    await asyncio.to_thread(
        _run_git, REPOSITORY_ROOT, "add", "--all", "--", *relative_paths
    )
    staged = await asyncio.to_thread(
        _run_git,
        REPOSITORY_ROOT,
        "diff",
        "--cached",
        "--name-status",
        "--",
        *relative_paths,
    )
    if staged.stdout.strip():
        logger.info("Publishing these artifacts:\n%s", staged.stdout.rstrip())
        commit = await asyncio.to_thread(
            _run_git,
            REPOSITORY_ROOT,
            "commit",
            "--only",
            "-m",
            f"content(publish): {publication.title}",
            "--",
            *relative_paths,
        )
        logger.info("Created publication commit: %s", commit.stdout.strip())
    else:
        logger.info("Publication artifacts have no uncommitted changes; using the current commit")

    branch = os.getenv("SARAL_PUBLISH_BRANCH") or (
        await asyncio.to_thread(_run_git, REPOSITORY_ROOT, "branch", "--show-current")
    ).stdout.strip()
    if not branch:
        raise RuntimeError("Cannot publish from a detached HEAD without SARAL_PUBLISH_BRANCH")
    remote = os.getenv("SARAL_PUBLISH_REMOTE", "origin")
    await asyncio.to_thread(_run_git, REPOSITORY_ROOT, "push", remote, f"HEAD:{branch}")
    revision = (
        await asyncio.to_thread(_run_git, REPOSITORY_ROOT, "rev-parse", "HEAD")
    ).stdout.strip()
    logger.info("Pushed publication revision %s to %s/%s", revision, remote, branch)
    if verify_latest:
        await _wait_for_latest_article(publication.title, revision)
    return revision
