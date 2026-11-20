"""Sensors for WalleCube UPS units."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WalleCubeConfigEntry, WalleCubeCoordinator
from .entity import WalleCubeEntity

Log = dict[str, Any]


def _num(log: Log, key: str) -> float | None:
    value = log.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _input_power(log: Log) -> float | None:
    volts, amps = _num(log, "voltageInput"), _num(log, "currentInput")
    if volts is None or amps is None:
        return None
    return round(volts * amps, 2)


def _battery_power(log: Log) -> float | None:
    """Battery power: positive while discharging, negative while charging.

    The sign of ``chargingCurrent`` is not reliable on every firmware, so the
    direction comes from the status flags. While discharging the cloud may
    report a near-zero battery current, so the output power is used as a floor.
    """
    volts, amps = _num(log, "batteryVoltage"), _num(log, "chargingCurrent")
    if volts is None or amps is None:
        return None
    power = volts * abs(amps)
    if log.get("discharging") or log.get("acOk") is False:
        return round(max(power, _num(log, "pwrOut") or 0.0), 2)
    if log.get("charging"):
        return round(-power, 2)
    return 0.0


def _cell_spread(log: Log) -> float | None:
    cells = [_num(log, f"batteryVoltage_{i}") for i in range(1, 5)]
    values = [c for c in cells if c is not None and c > 0]
    if len(values) < 2:
        return None
    return round((max(values) - min(values)) * 1000)


def _milli(device: dict[str, Any], key: str) -> float | None:
    settings = device.get("adapterSettings")
    if not isinstance(settings, dict):
        return None
    value = settings.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value / 1000


@dataclass(frozen=True, kw_only=True)
class WalleCubeSensorDescription(SensorEntityDescription):
    """Describes a WalleCube sensor."""

    value_fn: Callable[[Log], Any] | None = None
    # Values taken from the device object instead of the telemetry report.
    device_fn: Callable[[dict[str, Any]], Any] | None = None


def _field(key: str) -> Callable[[Log], float | None]:
    return lambda log: _num(log, key)


def _int_field(key: str) -> Callable[[Log], int | None]:
    def get(log: Log) -> int | None:
        value = _num(log, key)
        return None if value is None else round(value)

    return get


V = UnitOfElectricPotential.VOLT
A = UnitOfElectricCurrent.AMPERE
M = SensorStateClass.MEASUREMENT
DIAG = EntityCategory.DIAGNOSTIC

SENSORS: tuple[WalleCubeSensorDescription, ...] = (
    WalleCubeSensorDescription(
        key="battery", device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE, state_class=M,
        value_fn=_int_field("batteryCapacity"),
    ),
    WalleCubeSensorDescription(
        key="input_voltage", translation_key="input_voltage",
        device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=V,
        state_class=M, value_fn=_field("voltageInput"),
    ),
    WalleCubeSensorDescription(
        key="input_current", translation_key="input_current",
        device_class=SensorDeviceClass.CURRENT, native_unit_of_measurement=A,
        state_class=M, value_fn=_field("currentInput"),
    ),
    WalleCubeSensorDescription(
        key="input_power", translation_key="input_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT, state_class=M,
        value_fn=_input_power,
    ),
    WalleCubeSensorDescription(
        key="output_voltage", translation_key="output_voltage",
        device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=V,
        state_class=M, value_fn=_field("voltageOut"),
    ),
    WalleCubeSensorDescription(
        key="output_current", translation_key="output_current",
        device_class=SensorDeviceClass.CURRENT, native_unit_of_measurement=A,
        state_class=M, value_fn=_field("currentOut"),
    ),
    WalleCubeSensorDescription(
        key="output_power", translation_key="output_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT, state_class=M,
        value_fn=_field("pwrOut"),
    ),
    WalleCubeSensorDescription(
        key="battery_voltage", translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=V,
        state_class=M, value_fn=_field("batteryVoltage"),
    ),
    WalleCubeSensorDescription(
        key="battery_current", translation_key="battery_current",
        device_class=SensorDeviceClass.CURRENT, native_unit_of_measurement=A,
        state_class=M, value_fn=_field("chargingCurrent"),
    ),
    WalleCubeSensorDescription(
        key="battery_power", translation_key="battery_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT, state_class=M,
        value_fn=_battery_power,
    ),
    WalleCubeSensorDescription(
        key="time_left", translation_key="time_left",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0, state_class=M,
        value_fn=_field("leftSecs"),
    ),
    WalleCubeSensorDescription(
        key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS, state_class=M,
        value_fn=_field("bt"),
    ),
    WalleCubeSensorDescription(
        key="energy_out", translation_key="energy_out",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_field("totalConsumption"),
    ),
    WalleCubeSensorDescription(
        key="battery_health", translation_key="battery_health",
        native_unit_of_measurement=PERCENTAGE, state_class=M,
        entity_category=DIAG, value_fn=_field("batteryHealth"),
    ),
    WalleCubeSensorDescription(
        key="battery_cycles", translation_key="battery_cycles",
        state_class=SensorStateClass.TOTAL_INCREASING, entity_category=DIAG,
        value_fn=_int_field("batteryCycles"),
    ),
    WalleCubeSensorDescription(
        key="cell_spread", translation_key="cell_spread",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.MILLIVOLT,
        state_class=M, entity_category=DIAG, value_fn=_cell_spread,
    ),
    *(
        WalleCubeSensorDescription(
            key=f"cell_{i}_voltage", translation_key=f"cell_{i}_voltage",
            device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=V,
            suggested_display_precision=3, state_class=M,
            entity_category=DIAG, entity_registry_enabled_default=False,
            value_fn=_field(f"batteryVoltage_{i}"),
        )
        for i in range(1, 5)
    ),
    WalleCubeSensorDescription(
        key="adapter_voltage", translation_key="adapter_voltage",
        device_class=SensorDeviceClass.VOLTAGE, native_unit_of_measurement=V,
        entity_category=DIAG, entity_registry_enabled_default=False,
        device_fn=lambda dev: _milli(dev, "workVol"),
    ),
    WalleCubeSensorDescription(
        key="adapter_current", translation_key="adapter_current",
        device_class=SensorDeviceClass.CURRENT, native_unit_of_measurement=A,
        entity_category=DIAG, entity_registry_enabled_default=False,
        device_fn=lambda dev: _milli(dev, "adapterCurrent"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WalleCubeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, including units added to the account later."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [imei for imei in coordinator.data if imei not in known]
        if not new:
            return
        known.update(new)
        entities: list[SensorEntity] = []
        for imei in new:
            entities.extend(WalleCubeSensor(coordinator, imei, d) for d in SENSORS)
            entities.append(WalleCubeLastReport(coordinator, imei))
        async_add_entities(entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class WalleCubeSensor(WalleCubeEntity, SensorEntity):
    """A numeric value of a UPS unit."""

    entity_description: WalleCubeSensorDescription

    def __init__(
        self,
        coordinator: WalleCubeCoordinator,
        imei: str,
        description: WalleCubeSensorDescription,
    ) -> None:
        super().__init__(coordinator, imei, description)
        # Adapter settings are configuration, not live telemetry.
        self.always_available = description.device_fn is not None

    @property
    def native_value(self) -> Any:
        desc = self.entity_description
        if desc.device_fn is not None:
            return desc.device_fn(self.unit) if self.unit else None
        log = self.report
        return desc.value_fn(log) if log is not None and desc.value_fn else None


class WalleCubeLastReport(WalleCubeEntity, SensorEntity):
    """Time of the latest report, shown even when it is stale."""

    always_available = True

    def __init__(self, coordinator: WalleCubeCoordinator, imei: str) -> None:
        super().__init__(
            coordinator,
            imei,
            SensorEntityDescription(
                key="last_report",
                translation_key="last_report",
                device_class=SensorDeviceClass.TIMESTAMP,
                entity_category=DIAG,
            ),
        )

    @property
    def native_value(self) -> datetime | None:
        log = (self.unit or {}).get("log")
        ts = log.get("ts") if isinstance(log, dict) else None
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            return None
        return datetime.fromtimestamp(ts, timezone.utc)
