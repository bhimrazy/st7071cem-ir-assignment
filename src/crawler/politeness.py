"""Three mechanisms: identify honestly in the User-Agent, obey robots.txt
including Crawl-delay, and rate limit so a burst cannot happen even if the
rest is wrong."""

from __future__ import annotations

import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

import httpx

DEFAULT_USER_AGENT = (
    "MiniseekAcademicCrawler/0.1 "
    "(Coventry University ST7071CEM coursework; polite; respects robots.txt)"
)

# Used only if robots.txt specifies no Crawl-delay. Deliberately conservative:
# for a corpus of a few hundred publications the extra time is irrelevant, and
# being slower than necessary has no downside for us and a real one for them.
FALLBACK_DELAY_SECONDS = 2.0


class RateLimiter:
    """Enforces a minimum interval between requests.

    Thread-safe because the delay must hold across the whole crawler, not per
    thread -- two threads each waiting 5 seconds independently would still
    produce two requests at the same instant.
    """

    __slots__ = ("_last_request", "_lock", "_min_interval")

    def __init__(self, min_interval: float) -> None:
        self._min_interval = max(min_interval, 0.0)
        self._lock = threading.Lock()
        self._last_request = 0.0

    @property
    def min_interval(self) -> float:
        return self._min_interval

    def wait(self) -> float:
        """Block until the next request is allowed. Returns seconds slept."""
        with self._lock:
            now = time.monotonic()
            earliest = self._last_request + self._min_interval
            slept = 0.0
            if now < earliest:
                slept = earliest - now
                time.sleep(slept)
            self._last_request = time.monotonic()
            return slept


@dataclass(slots=True)
class RobotsPolicy:
    """robots.txt rules for one host.

    Fetched once and reused. If robots.txt cannot be read at all we fail
    *closed* -- refusing to crawl -- because assuming permission we were never
    granted is exactly the behaviour robots.txt exists to prevent.
    """

    base_url: str
    user_agent: str = DEFAULT_USER_AGENT
    _parser: urllib.robotparser.RobotFileParser = field(
        default_factory=urllib.robotparser.RobotFileParser, repr=False
    )
    _loaded: bool = False
    _reachable: bool = False

    def load(self) -> bool:
        """Fetch and parse robots.txt. Returns whether it was reachable.

        Fetched with httpx and our own User-Agent rather than through
        RobotFileParser.read(). That method fetches with urllib's default
        agent, and on a 403 it silently sets disallow_all -- so a site with a
        bot filter in front of it makes the crawler believe it is forbidden
        from every URL, including ones robots.txt explicitly permits. The
        failure is silent and looks exactly like a correctly-obeyed rule.
        """
        robots_url = urljoin(self.base_url, "/robots.txt")
        self._parser.set_url(robots_url)
        try:
            response = httpx.get(
                robots_url,
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            )
        except httpx.HTTPError:
            self._reachable = False
            self._loaded = True
            return False

        if response.status_code == 404:
            # No robots.txt at all means no restrictions were published. An
            # empty ruleset is exactly that: can_fetch then permits every URL.
            self._parser.parse([])
            self._reachable = True
        elif response.is_success:
            self._parser.parse(response.text.splitlines())
            self._reachable = True
        else:
            # Anything else (401, 403, 5xx) tells us nothing about what is
            # permitted, so we must not assume permission.
            self._reachable = False

        self._loaded = True
        return self._reachable

    def can_fetch(self, url: str) -> bool:
        if not self._loaded:
            self.load()
        if not self._reachable:
            return False  # fail closed
        return self._parser.can_fetch(self.user_agent, url)

    def crawl_delay(self) -> float:
        """Crawl-delay for our agent, falling back to a conservative default."""
        if not self._loaded:
            self.load()
        if not self._reachable:
            return FALLBACK_DELAY_SECONDS
        try:
            declared = self._parser.crawl_delay(self.user_agent)
        except Exception:
            declared = None
        if declared is None:
            return FALLBACK_DELAY_SECONDS
        # Never go faster than the site asks, but never slower than our own
        # floor either -- a site declaring 0 should not mean an unthrottled
        # flood.
        return max(float(declared), 0.5)

    @property
    def reachable(self) -> bool:
        if not self._loaded:
            self.load()
        return self._reachable


def same_host(url: str, base_url: str) -> bool:
    """Guard against following links off the site we are allowed to crawl."""
    return urlparse(url).netloc == urlparse(base_url).netloc
