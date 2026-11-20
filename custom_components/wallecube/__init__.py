"""WalleCube UPS integration (cloud)."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import WalleCubeApi
from .const import CONF_TOKEN, DOMAIN
from .coordinator import WalleCubeConfigEntry, WalleCubeCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def _language(hass: HomeAssistant) -> str:
    lang = (hass.config.language or "en").split("-")[0].lower()
    return {"zh": "zh_CN", "ru": "ru_RU"}.get(lang, "en_US")


async def async_setup_entry(hass: HomeAssistant, entry: WalleCubeConfigEntry) -> bool:
    """Set up WalleCube from a config entry."""
    api = WalleCubeApi(
        async_get_clientsession(hass), entry.data[CONF_TOKEN], _language(hass)
    )
    coordinator = WalleCubeCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WalleCubeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: WalleCubeConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a unit that is no longer in the account."""
    data = entry.runtime_data.data or {}
    return not any(
        ident[0] == DOMAIN and ident[1] in data for ident in device.identifiers
    )
