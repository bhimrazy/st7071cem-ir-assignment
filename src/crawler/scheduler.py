"""`run_forever` is a supervised in-process loop, convenient for a demonstration
but only alive as long as the process. For real deployment prefer the OS
scheduler calling `ir-crawl --once`, which survives reboots and keeps its own
logs. Either way the last run time is written to disk."""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import schedule

logger = logging.getLogger(__name__)

HOUR_SECONDS = 60 * 60
DAY_SECONDS = 24 * HOUR_SECONDS
WEEKLY_SECONDS = 7 * DAY_SECONDS
STATE_FILE = "crawl_state.json"
KATHMANDU = ZoneInfo("Asia/Kathmandu")

# Accepted on --schedule, so a run interval never needs a separate flag: a
# number plus one of these unit spellings, e.g. "1week", "100h", "3months".
# A month is approximated as 30 days -- there is no calendar-exact "month" of
# seconds, and the coursework brief only needs "roughly monthly".
_INTERVAL_UNITS: dict[str, float] = {
    # "m" is deliberately not mapped here -- it would be read as minutes by
    # anyone testing and as months by anyone deploying, so both stay spelled
    # out ("min"/"mo") rather than guessing which one a bare "m" meant.
    "min": 60.0,
    "mins": 60.0,
    "minute": 60.0,
    "minutes": 60.0,
    "h": HOUR_SECONDS,
    "hr": HOUR_SECONDS,
    "hrs": HOUR_SECONDS,
    "hour": HOUR_SECONDS,
    "hours": HOUR_SECONDS,
    "d": DAY_SECONDS,
    "day": DAY_SECONDS,
    "days": DAY_SECONDS,
    "w": WEEKLY_SECONDS,
    "wk": WEEKLY_SECONDS,
    "wks": WEEKLY_SECONDS,
    "week": WEEKLY_SECONDS,
    "weeks": WEEKLY_SECONDS,
    "mo": 30 * DAY_SECONDS,
    "mos": 30 * DAY_SECONDS,
    "month": 30 * DAY_SECONDS,
    "months": 30 * DAY_SECONDS,
}
_INTERVAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*$")


def parse_interval(text: str) -> float:
    """ "1week", "100h", "2months", ... -> seconds.

    Raises ValueError, with a message meant to be shown to the user as-is,
    if `text` isn't a number followed by one of the known units.
    """
    match = _INTERVAL_RE.match(text)
    unit_seconds = match and _INTERVAL_UNITS.get(match.group(2).lower())
    if not match or unit_seconds is None:
        raise ValueError(
            f"can't understand interval {text!r} -- try e.g. 1week, 100h, "
            "2months, 12hours"
        )
    return float(match.group(1)) * unit_seconds


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
    """Run `crawl` on an interval until `stop` is set, via the `schedule`
    package.

    `schedule` owns the run-every-N-seconds bookkeeping; we only need to
    point its job's first `next_run` at what `CrawlState` says is actually
    due, so restarting the process does not trigger an immediate re-crawl
    just because it happened to restart mid-interval.
    """
    stop = stop or threading.Event()

    def job() -> None:
        try:
            stats = crawl()
            state.write(stats)
            logger.info("crawl finished: %s", stats)
        except Exception:
            # A scheduler that dies on one failed crawl stops updating the
            # index silently. Log it and let `schedule` retry next interval.
            logger.exception("crawl failed; will retry at the next interval")
            state.write(
                {
                    "error": "crawl failed",
                    "when": datetime.now(KATHMANDU).isoformat(timespec="seconds"),
                }
            )

    scheduled = schedule.every(round(interval_seconds)).seconds.do(job)
    due_in = state.seconds_until_due(interval_seconds)
    # `schedule` compares against naive local time, not our timezone-aware
    # KATHMANDU clock -- harmless here since the machine's own local time
    # already is Asia/Kathmandu.
    scheduled.next_run = datetime.now() + timedelta(seconds=due_in)  # noqa: DTZ005
    logger.info("next crawl due in %.1f hours", due_in / 3600)

    try:
        while not stop.is_set():
            schedule.run_pending()
            if stop.wait(1):
                break
    finally:
        schedule.cancel_job(scheduled)


def next_run_time(
    state: CrawlState, interval_seconds: float = WEEKLY_SECONDS
) -> datetime:
    return datetime.now(KATHMANDU) + timedelta(
        seconds=state.seconds_until_due(interval_seconds)
    )
