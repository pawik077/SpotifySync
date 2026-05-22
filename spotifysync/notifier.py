from collections import defaultdict
from enum import IntEnum
import logging
import apprise

from .api import SyncSummary

logger = logging.getLogger("SpotifySync")


class Verbosity(IntEnum):
    SHORT = 0
    MEDIUM = 1
    FULL = 2


def _format_message(summary: SyncSummary, verbosity: Verbosity) -> tuple[str, str]:
    if summary.errors:
        title = "Spotify Sync Error"
        body = "\n".join(summary.errors)
    else:
        title = "Spotify Sync Log"
        removed = (
            ""
            if not summary.removed
            else (
                "Removed tracks:\n"
                + "\n".join([f"{x.artist} - {x.title}" for x in summary.removed])
                if verbosity >= Verbosity.MEDIUM
                else f"Removed: {len(summary.removed)}"
            )
        )
        added = (
            ""
            if not summary.added
            else (
                "Added tracks:\n"
                + "\n".join(
                    [
                        f"{x[0].artist} - {x[0].title} ({x[1].name})"
                        for x in summary.added
                    ]
                )
                if verbosity >= Verbosity.MEDIUM
                else f"Added: {len(summary.added)}"
            )
        )
        reordered = (
            ""
            if not summary.reordered
            else (
                "Reordered tracks:\n"
                + "\n".join(
                    [
                        f"{x[0].artist} - {x[0].title} (from {x[1]} to {x[2]})"
                        for x in summary.reordered
                    ]
                )
                if verbosity == Verbosity.FULL
                else f"Reordered: {len(summary.reordered)}"
            )
        )
        warnings = (
            ""
            if not summary.warnings
            else ("Warnings:\n" + "\n".join([x for x in summary.warnings]))
        )
        body = "\n".join([x for x in [removed, added, reordered, warnings] if x])

    return title, body


def notify(summary: SyncSummary, notify_urls: list[dict]) -> None:
    if not notify_urls:
        return
    if not any(
        [
            summary.errors,
            summary.removed,
            summary.added,
            summary.reordered,
            summary.warnings,
        ]
    ):
        return
    by_verbosity: dict[Verbosity, list[str]] = defaultdict(list)
    for notifier in notify_urls:
        url = notifier.get("url")
        if not url:
            continue
        by_verbosity[Verbosity(notifier.get("verbosity", Verbosity.FULL))].append(url)

    for verbosity, urls in by_verbosity.items():
        title, body = _format_message(summary, verbosity)
        ap = apprise.Apprise()
        for url in urls:
            ap.add(url)
        ap.notify(title=title, body=body)
