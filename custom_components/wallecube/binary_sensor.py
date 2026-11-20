"""Binary sensors for WalleCube UPS units."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_ONLINE
from .coordinator import WalleCubeConfigEntry
from .entity import WalleCubeEntity


@dataclass(frozen=True, kw_only=True)
class WalleCubeBinaryDescription(BinarySensorEntityDescription):
    """Describes a WalleCube binary sensor."""

    field: str


BINARY_SENSORS: tuple[WalleCubeBinaryDescription, ...] = (
    WalleCubeBinaryDescription(
        key="on_grid", translation_key="on_grid",
        device_class=BinarySensorDeviceClass.POWER, field="acOk",
    ),
    WalleCubeBinaryDescription(
        key="charging", device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        field="charging",
    ),
    WalleCubeBinaryDescription(
        key="discharging", translation_key="discharging", field="discharging",
    ),
    WalleCubeBinaryDescription(
        key="overload", translation_key="overload",
        device_class=BinarySensorDeviceClass.PROBLEM, field="overLoad",
    ),
)

ONLINE = BinarySensorEntityDescription(
    key="online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WalleCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors, including units added to the account later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [imei for imei in coordinator.data if imei not in known]
        if not new:
            return
        known.update(new)
        entities: list[BinarySensorEntity] = []
        for imei in new:
            entities.extend(
                WalleCubeBinarySensor(coordinator, imei, d) for d in BINARY_SENSORS
            )
            entities.append(WalleCubeOnline(coordinator, imei, ONLINE))
        async_add_entities(entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class WalleCubeBinarySensor(WalleCubeEntity, BinarySensorEntity):
    """A status flag of a UPS unit."""

    entity_description: WalleCubeBinaryDescription

    @property
    def is_on(self) -> bool | None:
        log = self.report
        value = log.get(self.entity_description.field) if log else None
        return value if isinstance(value, bool) else None


class WalleCubeOnline(WalleCubeEntity, BinarySensorEntity):
    """Whether the cloud sees the unit online with fresh data."""

    always_available = True

    @property
    def is_on(self) -> bool:
        dev: dict[str, Any] | None = self.unit
        return bool(dev and dev.get("status") == STATUS_ONLINE and self.report is not None)
