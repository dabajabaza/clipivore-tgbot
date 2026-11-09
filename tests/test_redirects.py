"""Following a short link: which hops carry the owner's cookies, and which never do."""

from collections.abc import AsyncIterator
from http.cookiejar import Cookie, CookieJar

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from clipivore.errors import LinkRefused
from clipivore.services.redirects import follow

HOST = "127.0.0.1"


def jar_for(domain: str) -> CookieJar:
    jar = CookieJar()
    jar.set_cookie(
        Cookie(
            version=0,
            name="reddit_session",
            value="secret",
            port=None,
            port_specified=False,
            domain=domain,
            domain_specified=False,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=False,
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
        )
    )
    return jar


@pytest.fixture
async def server() -> AsyncIterator[TestServer]:
    """A share link the way Reddit serves it to a server: 403 without a session."""

    async def share(request: web.Request) -> web.Response:
        if "reddit_session=secret" not in request.headers.get("Cookie", ""):
            return web.Response(status=403, text="You've been blocked by network security.")
        raise web.HTTPMovedPermanently(location="/r/CatJoy/comments/1xngwj6/title/")

    app = web.Application()
    app.router.add_get("/r/CatJoy/s/qo5tcrjjqJ", share)
    test_server = TestServer(app, host=HOST)
    await test_server.start_server()
    try:
        yield test_server
    finally:
        await test_server.close()


async def resolve(server: TestServer, cookies: CookieJar | None) -> str:
    return await follow(
        str(server.make_url("/r/CatJoy/s/qo5tcrjjqJ")),
        allowed_hosts=frozenset({HOST}),
        is_target=lambda url: "/comments/" in url,
        find_targets=lambda body: [],
        cookies=cookies,
        outside_message="outside",
    )


async def test_the_session_gets_a_share_link_past_the_block(server: TestServer) -> None:
    resolved = await resolve(server, jar_for(HOST))

    assert resolved == str(server.make_url("/r/CatJoy/comments/1xngwj6/title/"))


async def test_without_the_session_the_block_is_a_refusal_not_a_wrong_link(
    server: TestServer,
) -> None:
    # Reading the block page for a post link used to end as "doesn't lead to a
    # post", which blamed the person for the platform saying no.
    with pytest.raises(LinkRefused) as refused:
        await resolve(server, None)
    assert refused.value.status == 403


async def test_cookies_for_another_domain_are_not_sent(server: TestServer) -> None:
    # The jar decides per hop, so a session never leaks to a host it was not
    # issued for, even one the allowlist lets through.
    with pytest.raises(LinkRefused):
        await resolve(server, jar_for("reddit.com"))
