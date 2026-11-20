"""Polling coordinator for the WalleCube cloud."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import WalleCubeApi, WalleCubeAuthError, WalleCubeError
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type WalleCubeConfigEntry = ConfigEntry[WalleCubeCoordinator]


class WalleCubeCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Fetches every UPS of the account in a single request.

    ``data`` maps the unit IMEI (its stable hardware id) to the raw device
    object returned by the cloud, including the latest ``log``.
    """

    config_entry: WalleCubeConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: WalleCubeConfigEntry, api: WalleCubeApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            devices = await self.api.get_devices()
        except WalleCubeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except WalleCubeError as err:
            raise UpdateFailed(str(err)) from err
        return {str(dev["imei"]): dev for dev in devices}
