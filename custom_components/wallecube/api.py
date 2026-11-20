"""Minimal async client for the WalleCube cloud (ups.fenjilab.com).

The API is not documented by the vendor. Endpoints and fields were taken
from the official WalleCube mobile app. Responses are wrapped as
``{"code": 200, "msg": "...", "data": ...}``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

API_BASE = "https://ups.fenjilab.com"
APP_VERSION = "1.0.29"

# Login "type" values used by the app.
LOGIN_TYPE_PHONE = "1"
LOGIN_TYPE_EMAIL = "2"


class WalleCubeError(Exception):
    """Generic API error."""


class WalleCubeConnectionError(WalleCubeError):
    """The server could not be reached or answered garbage."""


class WalleCubeAuthError(WalleCubeError):
    """The token is missing, expired or the verification code is wrong."""


class WalleCubeApi:
    """Talks to the WalleCube cloud."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        token: str | None = None,
        language: str = "en_US",
        timeout: float = 20,
    ) -> None:
        self._session = session
        self._token = token
        self._language = language
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def token(self) -> str | None:
        """Current bearer token."""
        return self._token

    async def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> dict[str, Any]:
        headers = {
            "App-Version": APP_VERSION,
            "Accept-Language": self._language,
            "Accept": "application/json",
        }
        if auth:
            if not self._token:
                raise WalleCubeAuthError("No token")
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            async with self._session.request(
                method,
                f"{API_BASE}{path}",
                json=json_body,
                headers=headers,
                timeout=self._timeout,
                # An expired token is answered with a 302 to the web login page.
                allow_redirects=False,
            ) as resp:
                if resp.status in (301, 302, 401, 403):
                    raise WalleCubeAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise WalleCubeConnectionError(f"HTTP {resp.status}")
                try:
                    payload = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise WalleCubeConnectionError("Response is not JSON") from err
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise WalleCubeConnectionError(str(err) or type(err).__name__) from err

        if not isinstance(payload, dict):
            raise WalleCubeConnectionError("Unexpected response")
        code = payload.get("code")
        if code in (401, 403):
            raise WalleCubeAuthError(str(payload.get("msg")))
        if code != 200:
            raise WalleCubeError(f"API code {code}: {payload.get('msg')}")
        return payload

    async def request_code(self, username: str, login_type: str = LOGIN_TYPE_EMAIL) -> None:
        """Ask the cloud to send a one-time login code to e-mail or phone."""
        await self._request(
            "POST",
            "/api/v1/publics/sign/token",
            {"username": username, "type": login_type},
            auth=False,
        )

    async def login(self, username: str, code: str) -> str:
        """Exchange the one-time code for a bearer token."""
        try:
            payload = await self._request(
                "POST",
                "/api/v1/publics/signup",
                {"username": username, "token": code},
                auth=False,
            )
        except WalleCubeError as err:
            if isinstance(err, WalleCubeConnectionError):
                raise
            raise WalleCubeAuthError(str(err)) from err
        data = payload.get("data")
        token = data.get("token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise WalleCubeAuthError("Login response has no token")
        self._token = token
        return token

    async def get_me(self) -> dict[str, Any]:
        """Return the account profile."""
        payload = await self._request("GET", "/api/v1/cs/me")
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return all UPS units of the account, each with its latest ``log``."""
        payload = await self._request("GET", "/api/v1/cs/devices")
        data = payload.get("data")
        if not isinstance(data, list):
            raise WalleCubeConnectionError("Device list missing")
        return [d for d in data if isinstance(d, dict) and d.get("imei")]
