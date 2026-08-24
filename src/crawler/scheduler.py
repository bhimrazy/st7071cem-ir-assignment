"""`run_forever` is a supervised in-process loop, convenient for a demonstration
but only alive as long as the process. For real deployment prefer the OS
scheduler calling `ir-crawl --once`, which survives reboots and keeps its own
logs. Either way the last run time is written to disk."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

WEEKLY_SECONDS = 7 * 24 * 60 * 60
STATE_FILE = "crawl_state.json"
KATHMANDU = ZoneInfo("Asia/Kathmandu")


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
            "last_run": datetime.now(KATHMANDU).isoformat(timespec="seconds"),
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
        elapsed = (datetime.now(KATHMANDU) - last).total_seconds()
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
                    "when": datetime.now(KATHMANDU).isoformat(timespec="seconds"),
                }
            )

        if stop.wait(interval_seconds):
            break


def next_run_time(
    state: CrawlState, interval_seconds: float = WEEKLY_SECONDS
) -> datetime:
    return datetime.now(KATHMANDU) + timedelta(
        seconds=state.seconds_until_due(interval_seconds)
    )
