"""Separated from the crawl logic so "how do we ask for a page" and "which pages
do we want" can be tested apart."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol, Self

import httpx

from .politeness import (
    DEFAULT_USER_AGENT,
    RateLimiter,
    RobotsPolicy,
    same_host,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class DisallowedByRobots(Exception):
    """Raised when robots.txt forbids a URL. Never caught and ignored."""


@dataclass(slots=True)
class FetchResult:
    url: str
    status_code: int
    text: str
    from_cache: bool = False
    etag: str | None = None
    last_modified: str | None = None

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def unchanged(self) -> bool:
        """304 Not Modified -- the server confirmed our copy is current."""
        return self.status_code == 304


class Fetcher(Protocol):
    """What the crawl logic needs from a fetcher.

    Deliberately narrower than PoliteFetcher, so the crawl can be exercised
    against a stand-in that never opens a socket.
    """

    requests_made: int

    def fetch(self, url: str, *, conditional: bool = True) -> FetchResult: ...


class PoliteFetcher:
    """Fetches pages while obeying robots.txt and a crawl delay.

    Also keeps ETag/Last-Modified per URL so a re-crawl can send a conditional
    request. A 304 response costs the server almost nothing and saves us
    parsing entirely, which matters because the brief has this running weekly
    over a corpus that changes very slowly.
    """

    def __init__(
        self,
        base_url: str,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_delay: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.robots = RobotsPolicy(base_url=base_url, user_agent=user_agent)

        delay = min_delay if min_delay is not None else self.robots.crawl_delay()
        self.limiter = RateLimiter(delay)

        self._client = client or httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                "Accept-Language": "en-GB,en;q=0.9",
            },
        )
        self._validators: dict[str, dict[str, str]] = {}
        self.requests_made = 0
        self.bytes_downloaded = 0

    @property
    def crawl_delay(self) -> float:
        return self.limiter.min_interval

    def fetch(self, url: str, *, conditional: bool = True) -> FetchResult:
        """Fetch one URL politely.

        Raises DisallowedByRobots if robots.txt forbids it, or ValueError if
        the URL points at a different host than we are permitted to crawl.
        """
        if not same_host(url, self.base_url):
            raise ValueError(f"refusing to fetch off-host URL: {url}")
        if not self.robots.can_fetch(url):
            raise DisallowedByRobots(f"robots.txt disallows {url}")

        headers: dict[str, str] = {}
        if conditional and (validators := self._validators.get(url)):
            headers.update(validators)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                response = self._client.get(url, headers=headers)
            except httpx.HTTPError as error:
                last_error = error
                # Exponential backoff on top of the crawl delay: a struggling
                # server should see us back off, not retry at the same rate.
                time.sleep(self.crawl_delay * (2**attempt))
                continue

            self.requests_made += 1
            self.bytes_downloaded += len(response.content)

            if response.status_code in RETRYABLE_STATUS:
                # Honour Retry-After when the server tells us how long to wait.
                retry_after = response.headers.get("Retry-After")
                wait = self.crawl_delay * (2**attempt)
                if retry_after and retry_after.isdigit():
                    wait = max(wait, float(retry_after))
                logger.warning(
                    "%s returned %s; backing off %.1fs (attempt %d/%d)",
                    url,
                    response.status_code,
                    wait,
                    attempt + 1,
                    self.max_retries,
                )
                time.sleep(wait)
                continue

            if etag := response.headers.get("ETag"):
                self._validators.setdefault(url, {})["If-None-Match"] = etag
            if modified := response.headers.get("Last-Modified"):
                self._validators.setdefault(url, {})["If-Modified-Since"] = modified

            return FetchResult(
                url=str(response.url),
                status_code=response.status_code,
                text=response.text,
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )

        if last_error is not None:
            raise last_error
        return FetchResult(url=url, status_code=503, text="")

    def stats(self) -> dict[str, Any]:
        return {
            "requests_made": self.requests_made,
            "bytes_downloaded": self.bytes_downloaded,
            "crawl_delay": self.crawl_delay,
            "robots_reachable": self.robots.reachable,
        }

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
