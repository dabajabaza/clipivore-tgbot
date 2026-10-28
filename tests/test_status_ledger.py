"""A status message cut short by a restart is told so by the next process."""

from pathlib import Path

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import EditMessageText

from clipivore.bot import texts
from clipivore.bot.progress import ProgressReporter
from clipivore.bot.status_ledger import StatusLedger, report_interrupted
from tests.helpers.bot_harness import BotHarness


def build_reporter(harness: BotHarness, ledger: StatusLedger) -> ProgressReporter:
    return ProgressReporter(harness.bot, chat_id=1, message_id=777, ledger=ledger)


def restarted(path: Path) -> StatusLedger:
    """What the next process reads back from disk."""
    return StatusLedger(path)


async def test_an_unfinished_status_survives_a_restart(harness: BotHarness, tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    reporter = build_reporter(harness, StatusLedger(path))

    await reporter.set("Downloading… 89%")

    assert restarted(path).pending == [(1, 777)]


async def test_a_delivered_verdict_crosses_the_status_out(
    harness: BotHarness, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.json"
    reporter = build_reporter(harness, StatusLedger(path))

    await reporter.finish("Download failed.")

    assert restarted(path).pending == []


async def test_a_replaced_status_is_crossed_out(harness: BotHarness, tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    reporter = build_reporter(harness, StatusLedger(path))

    await reporter.replace_with_upload()

    assert restarted(path).pending == []


async def test_a_verdict_telegram_never_accepted_stays_listed(
    harness: BotHarness, tmp_path: Path
) -> None:
    # The incident this exists for: the proxy is down, so the edit carrying
    # the failure is itself what fails.
    path = tmp_path / "ledger.json"
    reporter = build_reporter(harness, StatusLedger(path))
    harness.session.fail_on["EditMessageText"] = TelegramNetworkError(
        method=EditMessageText(chat_id=1, message_id=777, text="x"), message="timeout"
    )

    await reporter.finish("Download failed.")

    assert restarted(path).pending == [(1, 777)]


async def test_startup_tells_an_abandoned_request_it_is_over(
    harness: BotHarness, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.json"
    StatusLedger(path).opened(1, 777)
    ledger = restarted(path)

    await report_interrupted(harness.bot, ledger)

    edit = harness.session.calls_of(EditMessageText)[-1]
    assert (edit.chat_id, edit.message_id, edit.text) == (1, 777, texts.INTERRUPTED)
    assert restarted(path).pending == []


async def test_a_status_that_can_no_longer_be_edited_is_dropped(
    harness: BotHarness, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.json"
    StatusLedger(path).opened(1, 777)
    harness.session.fail_on["EditMessageText"] = TelegramBadRequest(
        method=EditMessageText(chat_id=1, message_id=777, text="x"),
        message="message to edit not found",
    )

    await report_interrupted(harness.bot, restarted(path))

    # Retrying it on every restart would never succeed.
    assert restarted(path).pending == []


async def test_a_transient_failure_keeps_the_status_for_the_next_start(
    harness: BotHarness, tmp_path: Path
) -> None:
    path = tmp_path / "ledger.json"
    StatusLedger(path).opened(1, 777)
    harness.session.fail_on["EditMessageText"] = TelegramNetworkError(
        method=EditMessageText(chat_id=1, message_id=777, text="x"), message="reset"
    )

    await report_interrupted(harness.bot, restarted(path))

    assert restarted(path).pending == [(1, 777)]


def test_a_corrupt_ledger_starts_empty_instead_of_failing(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    path.write_text("{not json", encoding="utf-8")

    assert StatusLedger(path).pending == []


def test_an_unwritable_ledger_does_not_raise(tmp_path: Path) -> None:
    ledger = StatusLedger(tmp_path / "missing-dir" / "ledger.json")

    ledger.opened(1, 777)

    assert ledger.pending == [(1, 777)]


async def test_a_queued_link_is_listed_until_it_finishes(harness: BotHarness) -> None:
    await harness.send("https://x.com/user/status/123")
    request = await harness.take()

    ledger = harness.dp["status_ledger"]
    assert len(ledger.pending) == 1

    await request.reporter.finish("Download failed.")

    assert ledger.pending == []
