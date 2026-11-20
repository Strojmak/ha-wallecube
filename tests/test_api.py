"""Tests for the cloud client. They need only aiohttp and pytest, not Home Assistant."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from pathlib import Path
from typing import Any, Callable

import aiohttp
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "wallecube_api",
    Path(__file__).parents[1] / "custom_components" / "wallecube" / "api.py",
)
api = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(api)


class FakeResponse:
    def __init__(self, status: int, body: Any) -> None:
        self.status = status
        self._body = body

    async def json(self, content_type: Any = None) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class RaisingResponse:
    """A request that fails before any response, like a network error."""

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def __aenter__(self) -> None:
        raise self._exc

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class FakeSession:
    """Answers each request with ``responder(params)`` and records the params."""

    def __init__(self, responder: Callable[[dict | None], Any]) -> None:
        self._responder = responder
        self.calls: list[dict | None] = []
        self.requests: list[dict] = []

    def request(self, method, url, *, json=None, params=None, headers=None,
                timeout=None, allow_redirects=True):
        assert allow_redirects is False
        self.calls.append(params)
        self.requests.append(
            {"method": method, "url": url, "json": json, "headers": headers or {}}
        )
        return self._responder(params)


def dev(n: int) -> dict:
    return {"imei": f"IMEI{n}", "log": {}}


def page(items: list, next_url: str | None, total: Any = "omit") -> dict:
    body: dict = {"code": 200, "data": items, "pagination": {"nextPageUrl": next_url}}
    if total != "omit":
        body["total"] = total
    return body


def by_page(pages: dict[int, dict]) -> Callable[[dict | None], FakeResponse]:
    return lambda params: FakeResponse(200, pages[(params or {}).get("page", 1)])


def run(coro):
    return asyncio.run(coro)


def imeis(devices: list[dict]) -> list[str]:
    return [d["imei"] for d in devices]


def test_single_page() -> None:
    session = FakeSession(by_page({1: page([dev(1), dev(2)], None, 2)}))
    result = run(api.WalleCubeApi(session, "t").get_devices())
    assert imeis(result) == ["IMEI1", "IMEI2"]
    assert session.calls == [None]


def test_two_pages() -> None:
    session = FakeSession(by_page({1: page([dev(1)], "x?page=2", 2), 2: page([dev(2)], None, 2)}))
    result = run(api.WalleCubeApi(session, "t").get_devices())
    assert imeis(result) == ["IMEI1", "IMEI2"]
    assert session.calls == [None, {"page": 2}]


def test_empty_middle_page_is_not_the_end() -> None:
    session = FakeSession(by_page({
        1: page([dev(1)], "x?page=2"),
        2: page([], "x?page=3"),
        3: page([dev(2)], None),
    }))
    result = run(api.WalleCubeApi(session, "t").get_devices())
    assert imeis(result) == ["IMEI1", "IMEI2"]
    assert len(session.calls) == 3


def test_missing_total_relies_on_next_page() -> None:
    session = FakeSession(by_page({1: page([dev(1)], None)}))
    assert imeis(run(api.WalleCubeApi(session, "t").get_devices())) == ["IMEI1"]


@pytest.mark.parametrize("total", ["2", " 2 ", "+2"])
def test_numeric_string_total_is_checked(total: str) -> None:
    session = FakeSession(by_page({1: page([dev(1)], None, total)}))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


@pytest.mark.parametrize("total", [None, "n/a", "1.0", True, 1.5])
def test_unusable_total_is_ignored(total: Any) -> None:
    session = FakeSession(by_page({1: page([dev(1)], None, total)}))
    assert imeis(run(api.WalleCubeApi(session, "t").get_devices())) == ["IMEI1"]


def test_incomplete_list_fails() -> None:
    session = FakeSession(by_page({1: page([dev(1)], None, 3)}))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


def test_duplicates_do_not_satisfy_total() -> None:
    session = FakeSession(by_page({1: page([dev(1)], "x?page=2", 2), 2: page([dev(1)], None, 2)}))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


def test_page_cap() -> None:
    session = FakeSession(lambda params: FakeResponse(200, page([], "x")))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())
    assert len(session.calls) == api.MAX_PAGES


@pytest.mark.parametrize("status", [301, 302, 401, 403])
def test_auth_statuses(status: int) -> None:
    session = FakeSession(lambda params: FakeResponse(status, None))
    with pytest.raises(api.WalleCubeAuthError):
        run(api.WalleCubeApi(session, "t").get_devices())


@pytest.mark.parametrize("status", [404, 500, 502])
def test_server_errors_are_not_auth(status: int) -> None:
    session = FakeSession(lambda params: FakeResponse(status, None))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


def test_non_json_body() -> None:
    session = FakeSession(lambda params: FakeResponse(200, ValueError("html")))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


def test_no_token_is_auth_error() -> None:
    session = FakeSession(lambda params: FakeResponse(200, page([], None)))
    with pytest.raises(api.WalleCubeAuthError):
        run(api.WalleCubeApi(session).get_devices())
    assert session.calls == []


def test_login_refusal_keeps_cloud_message() -> None:
    session = FakeSession(lambda params: FakeResponse(200, {"code": 422, "msg": "bad code"}))
    with pytest.raises(api.WalleCubeError) as err:
        run(api.WalleCubeApi(session).login("a@example.com", "000000"))
    assert not isinstance(err.value, api.WalleCubeAuthError)
    assert err.value.api_message == "bad code"


def test_login_success_stores_token() -> None:
    session = FakeSession(lambda params: FakeResponse(
        200, {"code": 200, "data": {"token": "abc", "user": {"userId": 1}}}))
    client = api.WalleCubeApi(session)
    assert run(client.login("a@example.com", "123456")) == "abc"
    assert client.token == "abc"


def test_login_without_token_fails() -> None:
    session = FakeSession(lambda params: FakeResponse(200, {"code": 200, "data": {}}))
    with pytest.raises(api.WalleCubeAuthError):
        run(api.WalleCubeApi(session).login("a@example.com", "123456"))


@pytest.mark.parametrize(
    "body",
    [
        {"code": 200, "data": [dev(1)], "total": 1},
        {"code": 200, "data": [dev(1)], "total": 1, "pagination": None},
        {"code": 200, "data": [dev(1)], "total": 1, "pagination": {"currentPage": 1}},
    ],
)
def test_missing_pagination_is_an_error(body: dict) -> None:
    session = FakeSession(lambda params: FakeResponse(200, body))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


@pytest.mark.parametrize("total", [-1, "-3"])
def test_negative_total_is_an_error(total: Any) -> None:
    session = FakeSession(by_page({1: page([dev(1)], None, total)}))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


@pytest.mark.parametrize(
    "exc", [aiohttp.ClientError("boom"), asyncio.TimeoutError()]
)
def test_network_errors_are_connection_errors(exc: BaseException) -> None:
    session = FakeSession(lambda params: RaisingResponse(exc))
    with pytest.raises(api.WalleCubeConnectionError):
        run(api.WalleCubeApi(session, "t").get_devices())


def test_device_request_url_and_headers() -> None:
    session = FakeSession(by_page({1: page([dev(1)], None, 1)}))
    run(api.WalleCubeApi(session, "secret-token", language="ru_RU").get_devices())
    req = session.requests[0]
    assert req["method"] == "GET"
    assert req["url"] == "https://ups.fenjilab.com/api/v1/cs/devices"
    assert req["headers"]["Authorization"] == "Bearer secret-token"
    assert req["headers"]["App-Version"] == api.APP_VERSION
    assert req["headers"]["Accept-Language"] == "ru_RU"


def test_login_requests_have_no_token() -> None:
    session = FakeSession(lambda params: FakeResponse(
        200, {"code": 200, "data": {"token": "abc"}}))
    client = api.WalleCubeApi(session)
    run(client.request_code("a@example.com"))
    run(client.login("a@example.com", "123456"))
    send, login = session.requests
    assert send["url"].endswith("/api/v1/publics/sign/token")
    assert send["json"] == {"username": "a@example.com", "type": "2"}
    assert login["url"].endswith("/api/v1/publics/signup")
    assert login["json"] == {"username": "a@example.com", "token": "123456"}
    assert "Authorization" not in send["headers"]
    assert "Authorization" not in login["headers"]


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def test_records_without_imei_are_skipped_and_reported_once() -> None:
    body = page([dev(1), {"imei": ""}, {"log": {}}, "junk"], None, 1)
    session = FakeSession(lambda params: FakeResponse(200, body))
    client = api.WalleCubeApi(session, "t")
    handler = _Records()
    api._LOGGER.addHandler(handler)
    try:
        assert imeis(run(client.get_devices())) == ["IMEI1"]
        assert imeis(run(client.get_devices())) == ["IMEI1"]
    finally:
        api._LOGGER.removeHandler(handler)
    assert handler.messages == [
        "Ignoring 3 device record(s) without an IMEI in the cloud answer"
    ]
