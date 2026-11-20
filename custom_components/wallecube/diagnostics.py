"""Diagnostics for WalleCube."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN, CONF_USER_ID, CONF_USERNAME
from .coordinator import WalleCubeConfigEntry

TO_REDACT = {
    CONF_TOKEN,
    CONF_USERNAME,
    CONF_USER_ID,
    "imei",
    "macAddr",
    "ipAddr",
    "wolMacs",
    "weatherCity",
    "weatherAdcode",
    "weatherLocationId",
    "logId",
    "nickname",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: WalleCubeConfigEntry
) -> dict[str, Any]:
    """Return redacted entry data and the raw device list."""
    devices = list((entry.runtime_data.data or {}).values())
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "devices": async_redact_data(devices, TO_REDACT),
    }
