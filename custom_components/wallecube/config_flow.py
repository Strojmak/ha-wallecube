"""Config flow for WalleCube: log in with a one-time code sent by e-mail."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import WalleCubeApi, WalleCubeAuthError, WalleCubeConnectionError, WalleCubeError
from .const import CONF_CODE, CONF_TOKEN, CONF_USER_ID, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

EMAIL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL, autocomplete="email")
        )
    }
)
CODE_SCHEMA = vol.Schema({vol.Required(CONF_CODE): str})
TOKEN_SCHEMA = vol.Schema(
    {vol.Required(CONF_TOKEN): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
)


class WalleCubeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for WalleCube."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None

    def _api(self, token: str | None = None) -> WalleCubeApi:
        return WalleCubeApi(async_get_clientsession(self.hass), token)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how to sign in."""
        return self.async_show_menu(step_id="user", menu_options=["email", "token"])

    async def async_step_email(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the account e-mail and send a login code to it."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._username = user_input[CONF_USERNAME].strip()
            try:
                await self._api().request_code(self._username)
            except WalleCubeConnectionError:
                errors["base"] = "cannot_connect"
            except WalleCubeError as err:
                _LOGGER.debug("Sending the code failed: %s", err)
                errors["base"] = "send_code_failed"
            else:
                return await self.async_step_code()
        suggested = {CONF_USERNAME: self._username} if self._username else None
        return self.async_show_form(
            step_id="email",
            data_schema=self.add_suggested_values_to_schema(EMAIL_SCHEMA, suggested),
            errors=errors,
        )

    async def async_step_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Exchange the code from the e-mail for a token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api = self._api()
            try:
                token = await api.login(self._username or "", user_input[CONF_CODE].strip())
            except WalleCubeConnectionError:
                errors["base"] = "cannot_connect"
            except WalleCubeAuthError:
                errors["base"] = "invalid_code"
            else:
                return await self._async_finish(token)
        return self.async_show_form(
            step_id="code",
            data_schema=CODE_SCHEMA,
            errors=errors,
            description_placeholders={"username": self._username or ""},
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Use a bearer token obtained elsewhere."""
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
            return await self._async_finish(token, step_id="token")
        return self.async_show_form(step_id="token", data_schema=TOKEN_SCHEMA, errors=errors)

    async def _async_finish(self, token: str, step_id: str = "code") -> ConfigFlowResult:
        """Validate the token, then create or update the entry."""
        api = self._api(token)
        errors: dict[str, str] = {}
        try:
            me = await api.get_me()
            await api.get_devices()
        except WalleCubeConnectionError:
            errors["base"] = "cannot_connect"
        except WalleCubeAuthError:
            errors["base"] = "invalid_auth"
        except WalleCubeError as err:
            _LOGGER.debug("Token check failed: %s", err)
            errors["base"] = "unknown"
        if errors:
            if step_id == "token":
                return self.async_show_form(
                    step_id="token", data_schema=TOKEN_SCHEMA, errors=errors
                )
            return self.async_show_form(
                step_id="code",
                data_schema=CODE_SCHEMA,
                errors=errors,
                description_placeholders={"username": self._username or ""},
            )

        user_id = str(me.get("userId") or "")
        if not user_id:
            return self.async_abort(reason="unknown")
        await self.async_set_unique_id(user_id)
        data = {CONF_TOKEN: token, CONF_USER_ID: user_id}
        if self._username:
            data[CONF_USERNAME] = self._username

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )

        self._abort_if_unique_id_configured()
        title = self._username or me.get("nickname") or f"WalleCube {user_id}"
        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """The token stopped working."""
        self._username = entry_data.get(CONF_USERNAME)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user pick how to sign in again."""
        return self.async_show_menu(
            step_id="reauth_confirm", menu_options=["email", "token"]
        )
