"""Scheduling the weekly re-crawl.

The brief asks for the crawler to "be scheduled to look for new information,
say, once per week ... ideally automatically, as a scheduled task", and to
"update the index with the new data" on each run.

Two ways to run it, deliberately:

**In-process** (`run_forever`) -- a supervised loop that sleeps between runs.
Self-contained, nothing external to configure, and convenient for a
demonstration. The cost is that scheduling only survives as long as the
process does.

**Operating-system scheduler** (cron / launchd / systemd timer) -- the correct
choice for real deployment, because the OS restarts it after a reboot and
keeps its own logs. `scripts/crawl.py --once` exists precisely so a cron entry
can call it.

State is written to disk after every run so the next one -- in either mode --
knows when the last successful crawl happened.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

WEEKLY_SECONDS = 7 * 24 * 60 * 60
STATE_FILE = "crawl_state.json"


class CrawlState:
    """Records when the crawler last ran, and what happened.

    Persisted so a restarted process does not re-crawl immediately when it
    ran only an hour ago -- which would be exactly the "hitting the servers
    unnecessarily" the brief warns against.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self.path = Path(directory) / STATE_FILE

    def read(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except OSError, json.JSONDecodeError:
            return {}

    def write(self, stats: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_run": datetime.now(UTC).isoformat(timespec="seconds"),
            "last_stats": stats,
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def last_run(self) -> datetime | None:
        raw = self.read().get("last_run")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def seconds_until_due(self, interval_seconds: float = WEEKLY_SECONDS) -> float:
        """How long until the next run is due; 0 if it is due now."""
        last = self.last_run()
        if last is None:
            return 0.0
        elapsed = (datetime.now(UTC) - last).total_seconds()
        return max(interval_seconds - elapsed, 0.0)

    def is_due(self, interval_seconds: float = WEEKLY_SECONDS) -> bool:
        return self.seconds_until_due(interval_seconds) <= 0.0


def run_forever(
    crawl: Callable[[], dict[str, Any]],
    state: CrawlState,
    *,
    interval_seconds: float = WEEKLY_SECONDS,
    stop: threading.Event | None = None,
) -> None:
    """Run `crawl` on an interval until `stop` is set.

    Waits out any remaining interval before the first run, so restarting the
    process does not trigger an immediate re-crawl.
    """
    stop = stop or threading.Event()
    while not stop.is_set():
        wait = state.seconds_until_due(interval_seconds)
        if wait > 0:
            logger.info("next crawl due in %.1f hours", wait / 3600)
            if stop.wait(wait):
                break

        try:
            stats = crawl()
            state.write(stats)
            logger.info("crawl finished: %s", stats)
        except Exception:
            # A scheduler that dies on one failed crawl stops updating the
            # index silently. Log it and wait for the next window instead.
            logger.exception("crawl failed; will retry at the next interval")
            state.write(
                {
                    "error": "crawl failed",
                    "when": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )

        if stop.wait(interval_seconds):
            break


def next_run_time(
    state: CrawlState, interval_seconds: float = WEEKLY_SECONDS
) -> datetime:
    return datetime.now(UTC) + timedelta(
        seconds=state.seconds_until_due(interval_seconds)
    )
