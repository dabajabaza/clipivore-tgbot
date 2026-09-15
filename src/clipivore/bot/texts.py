"""Every string the bot says, in one place.

English throughout, and plain text rather than HTML or Markdown: replies quote
things the bot does not control — uploader handles, yt-dlp messages, external
locators full of punctuation — and plain text is the only format none of them
can break. The exceptions are the delivery verdict and the Owner-only Overflow
Menu; every dynamic string in their HTML is escaped.
"""

from html import escape

from clipivore.services.overflow import (
    SAVED_SELECTION_ID,
    OverflowCatalog,
    OverflowChoice,
    OverflowState,
)
from clipivore.services.providers import ProviderCatalog

HELP = (
    "Send me a link to a post and I'll download the video from it.\n\n"
    "{providers}\n\n"
    "A message may hold several links at once. "
    "Clips up to {max_mb} MB arrive here in the chat. {overflow}"
)
HELP_PROVIDER = "• {provider}: {hint}"
HELP_PROVIDER_BROKEN = "• {provider}: unavailable — the owner needs to check the bot's log."

HELP_OVERFLOW_READY = "Larger clips are delivered through {adapter}."
HELP_OVERFLOW_OFF = "Larger clips cannot be delivered while Overflow delivery is off."
HELP_OVERFLOW_MISSING = (
    "Larger clips cannot be delivered because the selected Overflow Adapter is missing."
)
HELP_OVERFLOW_MISCONFIGURED = (
    "Larger clips cannot be delivered because Overflow delivery is configured incorrectly."
)

HELP_COMMAND_DESCRIPTION = "What I can download"

NO_LINK = "No link I recognise. Send me a link to a post — /help lists what I can download."
NOT_A_POST = "That short link doesn't lead to a post on {provider}."
PROVIDER_MISCONFIGURED = (
    "Downloads from {provider} are configured incorrectly. The owner needs to check the bot's log."
)

QUEUED = "Queued…"
QUEUED_POSITION = "Queued — {position} in line."
QUEUE_FULL = "Queue is full ({limit} requests). Try again in a few minutes."
DOWNLOADING = "Downloading…"
DOWNLOADING_PROGRESS = "Downloading… {progress}"
# Clips usually arrive as separate video and audio files, each reporting its
# own 0→100%; naming the stream keeps the second run from looking like a restart.
DOWNLOADING_VIDEO_PROGRESS = "Downloading video… {progress}"
DOWNLOADING_AUDIO_PROGRESS = "Downloading audio… {progress}"
UPLOADING = "Uploading to Telegram… ({size})"
UPLOADING_MANY = "Uploading to Telegram… ({index}/{total}, {size})"
DELIVERING_OVERFLOW = "Too big for Telegram — delivering through {adapter}…"
SENT = "Sent."
# The label bot/captions.py wraps into the link to the post itself.
OPEN_IN = "Open in {provider}"

OVERFLOW_RESULT = "Too big for Telegram ({size}). Delivered through {adapter}:\n\n{location}"

NO_VIDEO = "That post has no video in it."
POST_UNAVAILABLE = "Can't reach that post — it may be deleted, protected or suspended."
NETWORK_UNAVAILABLE = (
    "Can't reach {provider} right now (network or proxy is down). Try again later."
)
DOWNLOAD_FAILED = "Download failed. The details are in the bot's log."
OVERFLOW_FAILED = "Downloaded it, but {adapter} couldn't complete Overflow delivery."
OVERFLOW_DISABLED = (
    "This clip is larger than Telegram's {max_mb} MB limit{observed}. Overflow delivery is off."
)
OVERFLOW_MISSING = (
    "This clip is larger than Telegram's {max_mb} MB limit{observed}. The selected Overflow "
    "Adapter ({adapter}) is missing. The owner needs to choose another in Menu."
)
OVERFLOW_MISCONFIGURED = (
    "This clip is larger than Telegram's {max_mb} MB limit{observed}. Overflow delivery through "
    "{adapter} is configured incorrectly. The owner needs to choose another in Menu."
)
# How the size in the verdict was learned: an aborted download versus a clip
# that finished downloading and only then failed the ceiling.
OVERFLOW_STOPPED_AT = "stopped at {size}"
OVERFLOW_CLIP_SIZE = "the clip is {size}"

OVERFLOW_MENU_TITLE = "Overflow delivery"
OVERFLOW_MENU_HINT = "Where files too large for Telegram are sent"
OVERFLOW_MENU_PROMPT = "Choose a destination:"
OVERFLOW_MENU_SELECTED = "Selected"
OVERFLOW_MENU_AVAILABLE = "Available"
OVERFLOW_MENU_OFF = "Large files won’t be delivered"
OVERFLOW_MENU_MISSING = "Missing"
OVERFLOW_MENU_MISCONFIGURED = "Not configured"
OVERFLOW_MENU_SELECTED_OFF = "Selected — large files won’t be delivered"
OVERFLOW_MENU_SELECTED_MISSING = "Selected, but missing"
OVERFLOW_MENU_SELECTED_MISCONFIGURED = "Selected, but not configured"
OVERFLOW_COMMAND_DESCRIPTION = "Overflow delivery"
OVERFLOW_CURRENT_MARKER = " ✓"
OVERFLOW_OFF_LABEL = "Off"
OVERFLOW_SAVED_SELECTION = "Saved selection"
OVERFLOW_NOT_SELECTABLE = "That Overflow Adapter is not available."
OVERFLOW_SAVE_FAILED = "Couldn't save the Overflow delivery selection. See the bot's log."
OVERFLOW_SELECTED = "Selected {adapter}."
TIMED_OUT = "Gave up after {minutes} minutes — the video is too long or the link is too slow."
AUTH_EXPIRED = (
    "Can't download right now: the owner's {provider} session needs renewing. Owner notified."
)

OWNER_AUTH_EXPIRED = (
    "{provider} rejected the stored cookies — export cookies.txt from the browser again and "
    "replace {path} on the server.\n\n{provider} said: {detail}"
)

FFMPEG_MISSING = (
    "ffmpeg is not installed, so only single-stream formats can be downloaded and "
    "quality will be capped below what the account can see."
)


def help_message(max_mb: int, overflow: OverflowChoice, providers: ProviderCatalog) -> str:
    if overflow.state is OverflowState.READY:
        detail = HELP_OVERFLOW_READY.format(adapter=overflow.label)
    elif overflow.state is OverflowState.MISSING:
        detail = HELP_OVERFLOW_MISSING
    elif overflow.state is OverflowState.MISCONFIGURED:
        detail = HELP_OVERFLOW_MISCONFIGURED
    else:
        detail = HELP_OVERFLOW_OFF
    return HELP.format(max_mb=max_mb, overflow=detail, providers=_provider_lines(providers))


def _provider_lines(providers: ProviderCatalog) -> str:
    """What the bot can be sent, one line each — including what is broken.

    A Provider that cannot serve is listed as unavailable rather than hidden:
    somebody whose link is being refused deserves to see that the bot knows the
    platform and has a problem with it, not that it never heard of it.
    """
    lines = [
        (
            HELP_PROVIDER.format(provider=choice.name, hint=choice.cls.hint)
            if choice.ready and choice.cls is not None
            else HELP_PROVIDER_BROKEN.format(provider=choice.name)
        )
        for choice in providers.choices
    ]
    # No empty case: a bot with no ready Provider exits at startup rather than
    # reaching a /help, so a string for it would be one nobody can ever read.
    return "\n".join(lines)


def downloading_progress(stream: str, progress: str) -> str:
    if stream == "video":
        return DOWNLOADING_VIDEO_PROGRESS.format(progress=progress)
    if stream == "audio":
        return DOWNLOADING_AUDIO_PROGRESS.format(progress=progress)
    return DOWNLOADING_PROGRESS.format(progress=progress)


def overflow_unavailable(overflow: OverflowChoice, *, max_mb: int, observed: str = "") -> str:
    """The size-limit verdict; ``observed`` says how far the download got."""
    detail = f" ({observed})" if observed else ""
    if overflow.state is OverflowState.MISSING:
        return OVERFLOW_MISSING.format(max_mb=max_mb, adapter=overflow.label, observed=detail)
    if overflow.state is OverflowState.MISCONFIGURED:
        return OVERFLOW_MISCONFIGURED.format(
            max_mb=max_mb, adapter=overflow_label(overflow), observed=detail
        )
    return OVERFLOW_DISABLED.format(max_mb=max_mb, observed=detail)


def overflow_menu(catalog: OverflowCatalog) -> str:
    current = catalog.current
    choices = (
        current,
        *(choice for choice in catalog.selectable if choice.adapter_id != current.adapter_id),
        *(
            choice
            for choice in catalog.choices
            if choice.adapter_id != current.adapter_id
            and choice.state in {OverflowState.MISSING, OverflowState.MISCONFIGURED}
        ),
    )
    rendered = "\n\n".join(
        _overflow_menu_choice(choice, selected=choice.adapter_id == current.adapter_id)
        for choice in choices
    )
    return (
        f"📦 <b>{OVERFLOW_MENU_TITLE}</b>\n"
        f"<i>{OVERFLOW_MENU_HINT}</i>\n\n"
        f"{rendered}\n\n"
        f"{OVERFLOW_MENU_PROMPT}"
    )


def _overflow_menu_choice(choice: OverflowChoice, *, selected: bool) -> str:
    if selected and choice.state is OverflowState.MISSING:
        icon, detail = "⚠", OVERFLOW_MENU_SELECTED_MISSING
    elif selected and choice.state is OverflowState.MISCONFIGURED:
        icon, detail = "⚠", OVERFLOW_MENU_SELECTED_MISCONFIGURED
    elif selected and choice.state is OverflowState.OFF:
        icon, detail = "✓", OVERFLOW_MENU_SELECTED_OFF
    elif selected:
        icon, detail = "✓", OVERFLOW_MENU_SELECTED
    elif choice.state is OverflowState.OFF:
        icon, detail = "○", OVERFLOW_MENU_OFF
    elif choice.state is OverflowState.READY:
        icon, detail = "○", OVERFLOW_MENU_AVAILABLE
    elif choice.state is OverflowState.MISSING:
        icon, detail = "⚠", OVERFLOW_MENU_MISSING
    else:
        icon, detail = "⚠", OVERFLOW_MENU_MISCONFIGURED
    return f"{icon} <b>{escape(overflow_label(choice))}</b>\n<i>{detail}</i>"


def overflow_label(overflow: OverflowChoice) -> str:
    if overflow.adapter_id == SAVED_SELECTION_ID:
        return OVERFLOW_SAVED_SELECTION
    if overflow.state is OverflowState.OFF:
        return OVERFLOW_OFF_LABEL
    return overflow.label


def human_size(size_bytes: int) -> str:
    """Size as a person would say it, which is all these numbers are used for."""
    kilobytes = size_bytes / 1024
    megabytes = kilobytes / 1024
    if megabytes >= 1024:
        return f"{megabytes / 1024:.1f} GB"
    if megabytes >= 1:
        return f"{megabytes:.0f} MB"
    # A short GIF-mp4 is well under a megabyte; "0 MB" would read as a glitch.
    return f"{kilobytes:.0f} KB"
