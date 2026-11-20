"""Base entity for WalleCube."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, STALE_AFTER, STATUS_ONLINE
from .coordinator import WalleCubeCoordinator


class WalleCubeEntity(CoordinatorEntity[WalleCubeCoordinator]):
    """A value of one UPS unit."""

    _attr_has_entity_name = True
    # Entities that stay available even when the unit is offline or stale.
    always_available = False

    def __init__(
        self,
        coordinator: WalleCubeCoordinator,
        imei: str,
        description: EntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._imei = imei
        self._attr_unique_id = f"{imei}_{description.key}"
        dev = coordinator.data[imei]
        model = dev.get("realModel") or dev.get("model") or "UPS"
        mac = dev.get("macAddr")
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, imei)},
            connections={(CONNECTION_NETWORK_MAC, mac.lower())} if mac else set(),
            manufacturer="WalleCube",
            model=model,
            name=dev.get("nickname") or f"WalleCube {model}",
            serial_number=imei,
            sw_version=dev.get("upsSwVer"),
            hw_version=dev.get("upsHwVer"),
        )

    @property
    def unit(self) -> dict[str, Any] | None:
        """Raw device object, or None when it left the account."""
        return (self.coordinator.data or {}).get(self._imei)

    @property
    def report(self) -> dict[str, Any] | None:
        """Latest telemetry report, or None when missing or stale."""
        dev = self.unit
        if not dev or dev.get("status") != STATUS_ONLINE:
            return None
        log = dev.get("log")
        if not isinstance(log, dict):
            return None
        ts = log.get("ts")
        if not isinstance(ts, (int, float)):
            return None
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(ts, timezone.utc)
        if age > STALE_AFTER:
            return None
        return log

    @property
    def available(self) -> bool:
        if not super().available or self.unit is None:
            return False
        return self.always_available or self.report is not None
