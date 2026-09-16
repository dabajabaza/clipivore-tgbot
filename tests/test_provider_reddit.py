"""Reddit as a Provider: post links, share links and its own metadata."""

from pathlib import Path

import pytest
from yt_dlp.utils import DownloadError

from clipivore.errors import AuthExpired, DownloadFailed, NoVideoInPost, PostUnavailable
from clipivore.providers import reddit
from clipivore.providers.reddit import RedditProvider
from clipivore.services import downloader
from clipivore.services.providers import ProviderCatalog, ProviderContext, ProviderState

POST = "https://www.reddit.com/r/videos/comments/6rrwyj/that_small_heart_attack/"


def urls(*sources: str | None) -> list[str]:
    return [link.url for link in ProviderCatalog(ProviderContext()).extract(*sources)]


@pytest.mark.parametrize(
    "url",
    [
        POST,
        "https://reddit.com/comments/124pp33",
        "https://old.reddit.com/r/videos/comments/6rrwyj/title/",
        "https://m.reddit.com/user/creepyt0es/comments/nip71r/title/",
        "https://www.reddit.com/r/videos/comments/6rrwyj/title/?utm_source=share",
    ],
)
def test_direct_post_spellings_are_recognised(url: str) -> None:
    assert urls(url) == [url]
    assert RedditProvider.post_link.match(url)


@pytest.mark.parametrize(
    "url",
    ["https://redd.it/6rrwyj", "https://www.reddit.com/r/videos/s/AbC123?utm_source=share"],
)
def test_share_links_are_recognised_as_short_links(url: str) -> None:
    assert urls(url) == [url]
    assert RedditProvider.is_short(url)
    assert not RedditProvider.post_link.match(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.reddit.com/r/videos",
        "https://www.reddit.com/r/videos/s/",
        "https://v.redd.it/abc123",
        "https://www.redditmedia.com/r/videos/comments/6rrwyj/title/",
    ],
)
def test_non_post_urls_are_left_alone(url: str) -> None:
    assert urls(url) == []


def test_post_id_is_read_from_the_direct_link() -> None:
    assert RedditProvider.post_id(POST) == "6rrwyj"


async def test_a_direct_post_never_resolves_over_the_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unexpected(*args: object, **kwargs: object) -> str:
        raise AssertionError("direct post tried to resolve")

    monkeypatch.setattr(reddit, "follow", unexpected)
    assert await RedditProvider(ProviderContext()).resolve(POST) == POST


async def test_a_share_link_uses_the_restricted_redirect_follower(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    async def fake_follow(url: str, **kwargs: object) -> str:
        seen.update(kwargs)
        assert url == "https://redd.it/6rrwyj"
        return POST

    monkeypatch.setattr(reddit, "follow", fake_follow)
    assert await RedditProvider(ProviderContext()).resolve("https://redd.it/6rrwyj") == POST
    assert seen["allowed_hosts"] == reddit._ALLOWED_HOSTS
    assert seen["outside_message"] == "https://redd.it/6rrwyj leads outside Reddit"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("No media found", NoVideoInPost),
        ("Private subreddit; an account that has been approved is required", PostUnavailable),
        ("Quarantined subreddit; an account that has opted in is required", PostUnavailable),
        ("Account authentication is required", AuthExpired),
        ("An extractor error has occurred", DownloadFailed),
    ],
)
def test_reddit_errors_have_honest_verdicts(message: str, expected: type[Exception]) -> None:
    assert isinstance(downloader._classify(DownloadError(message), reddit.PROFILE), expected)


def test_reddit_title_text_author_and_post_id_reach_the_clip(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    entry = {
        "id": "media-id",
        "display_id": "6rrwyj",
        "alt_title": "A full Reddit title",
        "description": "The self text",
        "uploader": "someone",
        "upload_date": "20260916",
        "requested_downloads": [{"filepath": str(video)}],
    }

    [clip] = downloader._clips_from_info(entry, POST, reddit.PROFILE)

    assert clip.post_id == "6rrwyj"
    assert clip.description == "A full Reddit title\n\nThe self text"
    assert clip.uploader_url == "https://www.reddit.com/user/someone"


class TestRedditConfiguration:
    def test_a_cookie_directory_disables_only_reddit(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("REDDIT_COOKIES_FILE", str(tmp_path))

        choice = ProviderCatalog(ProviderContext()).get("reddit")

        assert choice is not None
        assert choice.state is ProviderState.MISCONFIGURED
        assert choice.claims(POST)
        assert "REDDIT_COOKIES_FILE must be a file" in choice.error

    def test_an_empty_cookie_setting_means_anonymous_access(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("REDDIT_COOKIES_FILE", " ")

        provider = RedditProvider(ProviderContext())

        assert provider.cookies is not None
        assert provider.cookies.source is None
        assert provider.cookies.setting == "REDDIT_COOKIES_FILE"
