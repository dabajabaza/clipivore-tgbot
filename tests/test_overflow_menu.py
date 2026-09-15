"""Only the Owner can inspect and change Overflow delivery from Menu."""

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from aiogram.enums import ParseMode
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, SetMyCommands
from aiogram.types import BotCommandScopeChat

from clipivore.__main__ import _set_commands
from clipivore.bot import texts
from clipivore.bot.handlers.overflow import _keyboard
from clipivore.services.overflow import OverflowCatalog, OverflowChoice, OverflowState
from tests.helpers.bot_harness import BotHarness
from tests.helpers.factories import GUEST_ID, OWNER_ID

FAKES = "tests.helpers.fake_adapters"
EMPTY = "tests.helpers.no_adapters"


async def test_the_owner_sees_the_overflow_command(harness: BotHarness) -> None:
    await harness.send("/overflow", user_id=OWNER_ID)

    sent = harness.session.calls_of(SendMessage)
    assert len(sent) == 1
    assert sent[0].text == texts.overflow_menu(harness.overflow_catalog)
    assert sent[0].parse_mode == ParseMode.HTML
    assert sent[0].reply_markup is not None


async def test_only_the_owner_gets_overflow_in_telegrams_command_menu(
    harness: BotHarness,
) -> None:
    await _set_commands(harness.bot, owner_id=OWNER_ID)

    configured = harness.session.calls_of(SetMyCommands)
    assert len(configured) == 2
    everyone, owner = configured
    # Telegram shows one scope's list and ignores the rest, so the Owner's own
    # list has to carry /help too, or /overflow would take its place.
    assert [(command.command, command.description) for command in everyone.commands] == [
        ("help", texts.HELP_COMMAND_DESCRIPTION)
    ]
    assert everyone.scope is None
    assert [(command.command, command.description) for command in owner.commands] == [
        ("help", texts.HELP_COMMAND_DESCRIPTION),
        ("overflow", texts.OVERFLOW_COMMAND_DESCRIPTION),
    ]
    assert isinstance(owner.scope, BotCommandScopeChat)
    assert owner.scope.chat_id == OWNER_ID


async def test_a_guest_cannot_open_the_owner_setting(harness: BotHarness) -> None:
    await harness.send("/overflow", user_id=GUEST_ID)

    assert harness.session.calls == []


async def test_the_owner_can_choose_from_the_inline_menu(
    harness: BotHarness, tmp_path: Path
) -> None:
    state_file = tmp_path / "selection"
    catalog = OverflowCatalog(FAKES, state_file=state_file)
    harness.dp["overflow_catalog"] = catalog

    await harness.press("overflow:test", user_id=OWNER_ID)

    assert catalog.current.adapter_id == "test"
    assert state_file.read_text(encoding="utf-8").strip() == "test"
    assert harness.session.calls_of(AnswerCallbackQuery)
    answer_index = next(
        index
        for index, call in enumerate(harness.session.calls)
        if isinstance(call, AnswerCallbackQuery)
    )
    edit_index = next(
        index
        for index, call in enumerate(harness.session.calls)
        if isinstance(call, EditMessageText)
    )
    assert answer_index < edit_index
    assert harness.session.calls_of(EditMessageText)[0].parse_mode == ParseMode.HTML


async def test_a_failed_menu_refresh_does_not_lose_the_callback_answer(
    harness: BotHarness, tmp_path: Path
) -> None:
    catalog = OverflowCatalog(FAKES, state_file=tmp_path / "selection")
    harness.dp["overflow_catalog"] = catalog
    harness.session.fail_on["EditMessageText"] = RuntimeError("Telegram edit failed")

    await harness.press("overflow:test", user_id=OWNER_ID)

    assert catalog.current.adapter_id == "test"
    assert len(harness.session.calls_of(AnswerCallbackQuery)) == 1


async def test_selecting_the_current_choice_only_answers_the_callback(
    harness: BotHarness, tmp_path: Path
) -> None:
    state_file = tmp_path / "selection"
    catalog = OverflowCatalog(EMPTY, state_file=state_file)
    harness.dp["overflow_catalog"] = catalog

    await harness.press("overflow:none", user_id=OWNER_ID)

    assert len(harness.session.calls_of(AnswerCallbackQuery)) == 1
    assert harness.session.calls_of(EditMessageText) == []
    assert state_file.read_text(encoding="utf-8").strip() == "none"


async def test_a_guest_callback_is_silent(harness: BotHarness) -> None:
    await harness.press("overflow:none", user_id=GUEST_ID)

    assert harness.session.calls == []


def test_only_working_adapters_become_buttons(tmp_path: Path) -> None:
    catalog = OverflowCatalog(FAKES, state_file=tmp_path / "selection")
    keyboard = _keyboard(catalog)

    labels = [button.text for row in keyboard.inline_keyboard for button in row]

    assert labels == ["Off ✓", "Test destination"]
    assert len(keyboard.inline_keyboard) == 1
    menu = texts.overflow_menu(catalog)
    assert "✓ <b>Off</b>\n<i>Selected — large files won’t be delivered</i>" in menu
    # Broken Adapters are named by their own classes, not guessed from files.
    assert "<b>Broken</b>\n<i>Not configured</i>" in menu
    assert "<b>Needs arguments</b>\n<i>Not configured</i>" in menu


def test_a_selection_whose_module_disappeared_is_reported_missing(tmp_path: Path) -> None:
    state_file = tmp_path / "selection"
    state_file.write_text("removed\n")
    catalog = OverflowCatalog(FAKES, state_file=state_file)

    menu = texts.overflow_menu(catalog)

    assert "⚠ <b>Removed</b>\n<i>Selected, but missing</i>" in menu


def test_menu_matches_the_approved_html_layout_and_escapes_adapter_labels() -> None:
    off = OverflowChoice(adapter_id="none", label="none", state=OverflowState.OFF)
    share = OverflowChoice(adapter_id="share", label="Share <fast>", state=OverflowState.READY)
    yandex = OverflowChoice(
        adapter_id="yandex_disk",
        label="Yandex Disk",
        state=OverflowState.MISCONFIGURED,
    )
    catalog = cast(
        OverflowCatalog,
        SimpleNamespace(current=share, selectable=(off, share), choices=(share, yandex)),
    )

    assert texts.overflow_menu(catalog) == (
        "📦 <b>Overflow delivery</b>\n"
        "<i>Where files too large for Telegram are sent</i>\n\n"
        "✓ <b>Share &lt;fast&gt;</b>\n"
        "<i>Selected</i>\n\n"
        "○ <b>Off</b>\n"
        "<i>Large files won’t be delivered</i>\n\n"
        "⚠ <b>Yandex Disk</b>\n"
        "<i>Not configured</i>\n\n"
        "Choose a destination:"
    )
