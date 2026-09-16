"""Reddit posts, including the short links its sharing UI emits.

The Provider accepts a post, not a raw ``v.redd.it`` media URL: the post is what
carries the title, author and the stable link used in the delivery caption.
"""

import re
from pathlib import Path
from typing import ClassVar

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from clipivore.domain import Downloader
from clipivore.services.cookies import CookieSession
from clipivore.services.downloader import EngineProfile, YtDlpDownloader
from clipivore.services.providers import Provider, ProviderContext
from clipivore.services.redirects import follow

_POST_LINK = re.compile(
    r"https?://(?:[\w-]+\.)?reddit\.com/"
    r"(?:(?:r|user)/[^/\s]+/)?comments/(?P<id>[A-Za-z0-9]+)[^\s<>\"',]*",
    re.IGNORECASE,
)
_SHORT_LINK = re.compile(
    r"https?://(?:redd\.it/[A-Za-z0-9]+|(?:[\w-]+\.)?reddit\.com/"
    r"(?:r/[^/\s]+/)?s/[A-Za-z0-9]+)[^\s<>\"',]*",
    re.IGNORECASE,
)
_ALLOWED_HOSTS = frozenset(
    {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "m.reddit.com", "redd.it"}
)


class RedditSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    reddit_cookies_file: Path | None = Field(
        default=None,
        alias="REDDIT_COOKIES_FILE",
        description=(
            "Netscape-format cookies.txt of the owner's Reddit session. Without it only public "
            "posts download."
        ),
    )

    @field_validator("reddit_cookies_file", mode="before")
    @classmethod
    def _empty_path_means_unset(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


PROFILE = EngineProfile(
    allowed_extractors=("reddit",),
    # A session cannot grant membership or an explicit quarantine opt-in.
    account_state_markers=("private subreddit", "quarantined subreddit"),
    auth_markers=("account authentication is required",),
    no_video_markers=("no media found",),
    unavailable_markers=("not found",),
    description_fields=("alt_title", "description"),
    profile_url=lambda handle: f"https://www.reddit.com/user/{handle}",
    profile_from_uploader=True,
)


class RedditProvider(Provider):
    name: ClassVar[str] = "Reddit"
    hint: ClassVar[str] = (
        "reddit.com/r/<community>/comments/<id> — redd.it and share links work too"
    )
    post_link: ClassVar[re.Pattern[str]] = _POST_LINK
    short_link: ClassVar[re.Pattern[str] | None] = _SHORT_LINK

    def __init__(self, context: ProviderContext) -> None:
        cookies_file = RedditSettings().reddit_cookies_file
        if cookies_file is not None and cookies_file.is_dir():
            raise ValueError(f"REDDIT_COOKIES_FILE must be a file, got directory {cookies_file}")
        self.cookies = CookieSession(cookies_file, setting="REDDIT_COOKIES_FILE")
        self._proxy = context.proxy
        self._downloader = YtDlpDownloader(PROFILE, cookies=self.cookies, proxy=context.proxy)

    @property
    def downloader(self) -> Downloader:
        return self._downloader

    async def resolve(self, url: str) -> str:
        if not self.is_short(url):
            return url
        return await follow(
            url,
            allowed_hosts=_ALLOWED_HOSTS,
            is_target=lambda candidate: bool(_POST_LINK.match(candidate)),
            find_targets=_posts_in,
            proxy=self._proxy,
            outside_message=f"{url} leads outside Reddit",
        )


def _posts_in(text: str) -> list[str]:
    return [match.group(0) for match in _POST_LINK.finditer(text)]
