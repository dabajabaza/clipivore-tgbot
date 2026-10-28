"""Status messages still waiting for their last word, kept across restarts.

The queue lives in memory, so a process that dies mid-request — the watchdog
killing it while the proxy is down, a deploy, a reboot — takes every request
with it, and their status messages stay frozen on "Downloading… 89%" forever.
Nothing in the new process knows they exist. The verdict path cannot cover
this: when the tunnel is down, the very edit that would report the failure is
what fails, and the supervisor kills the process seconds later.

So every status message is written down when it is created and crossed out only
once Telegram has accepted its final edit. Whatever is still listed at startup
was abandoned, and gets told so before the bot takes new work.

The final text is written down *before* it is sent. Telegram may apply an edit
whose response never arrives, and the process may die between the edit and the
crossing out; in both cases the verdict may already be on screen — an Overflow
locator, say, with the source message already deleted. Recovery replays that
verdict rather than covering it with "Interrupted".
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)

from clipivore.bot import texts

logger = logging.getLogger(__name__)

_Key = tuple[int, int]


@dataclass(frozen=True)
class Verdict:
    """A status message's last word, as it is to be sent."""

    text: str
    parse_mode: str | None = None


_INTERRUPTED = Verdict(texts.INTERRUPTED)
_ABSENT = object()


class StatusLedger:
    """Every status message not yet finished, with its last word once decided.

    Never raises: a ledger that cannot be written costs the restart notice, not
    the request.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._open: dict[_Key, Verdict | None] = self._read()

    @property
    def pending(self) -> list[tuple[int, int, Verdict | None]]:
        return [(*key, verdict) for key, verdict in sorted(self._open.items())]

    def opened(self, chat_id: int, message_id: int) -> None:
        self._open[(chat_id, message_id)] = None
        self._write()

    def concluding(self, chat_id: int, message_id: int, verdict: Verdict) -> None:
        """Record the last word before it is sent, so recovery can replay it."""
        if (chat_id, message_id) not in self._open:
            return
        self._open[(chat_id, message_id)] = verdict
        self._write()

    def closed(self, chat_id: int, message_id: int) -> None:
        if self._open.pop((chat_id, message_id), _ABSENT) is _ABSENT:
            return
        self._write()

    def _read(self) -> dict[_Key, Verdict | None]:
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {
                (int(chat_id), int(message_id)): (
                    None if text is None else Verdict(str(text), parse_mode)
                )
                for chat_id, message_id, text, parse_mode in raw
            }
        except FileNotFoundError:
            return {}
        except (OSError, ValueError, TypeError) as exc:
            # Losing the list only means some frozen message stays frozen;
            # refusing to start over it would be far worse.
            logger.error("could not read status ledger %s: %s", self._path, exc)
            return {}

    def _write(self) -> None:
        # Written whole and swapped in, so a kill mid-write leaves the previous
        # list rather than a truncated one.
        temporary = self._path.with_name(f"{self._path.name}.tmp")
        try:
            rows = [
                [
                    chat_id,
                    message_id,
                    *((verdict.text, verdict.parse_mode) if verdict else (None, None)),
                ]
                for chat_id, message_id, verdict in self.pending
            ]
            temporary.write_text(json.dumps(rows), encoding="utf-8")
            os.replace(temporary, self._path)
        except OSError as exc:
            logger.warning("could not write status ledger %s: %s", self._path, exc)


async def report_interrupted(bot: Bot, ledger: StatusLedger) -> None:
    """Tell every request the previous process abandoned that it is over.

    A status whose last word was already decided gets that word again: it may
    well be on screen already, and "Interrupted" would only erase it.

    Run once Telegram is reachable and before polling starts, so nothing new is
    listed yet. A message that is gone or can no longer be edited is crossed out
    too: retrying it on every restart would never succeed. Only a transient
    failure keeps it for the next start.
    """
    for chat_id, message_id, decided in ledger.pending:
        verdict = decided or _INTERRUPTED
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=verdict.text,
                parse_mode=verdict.parse_mode,
            )
        except (TelegramNetworkError, TelegramServerError, TelegramRetryAfter) as exc:
            logger.warning("could not mark %s/%s interrupted: %s", chat_id, message_id, exc)
            continue
        except TelegramAPIError as exc:
            logger.info("dropping interrupted status %s/%s: %s", chat_id, message_id, exc)
        except Exception as exc:
            # Not a TelegramAPIError, e.g. ClientDecodeError from an HTML error
            # page: likely transient, so the entry waits for the next start.
            logger.warning(
                "could not mark %s/%s interrupted: %s: %s",
                chat_id,
                message_id,
                type(exc).__name__,
                exc,
            )
            continue
        else:
            logger.info("settled %s/%s after restart: %s", chat_id, message_id, verdict.text)
        ledger.closed(chat_id, message_id)
