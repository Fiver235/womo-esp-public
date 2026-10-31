"""Truma LevelControl sensors (config-entry based)."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    PERCENTAGE,
    UnitOfMass,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TrumaCoordinator
from .truma import TrumaReading

# key, label, unit, device_class, state_class, icon, getter
_DESCRIPTIONS: list[tuple] = [
    ("fill_level", "Füllstand", PERCENTAGE, None,
     SensorStateClass.MEASUREMENT, "mdi:gauge", lambda r: r.percent),
    ("gas_amount", "Gasmenge", UnitOfMass.KILOGRAMS, SensorDeviceClass.WEIGHT,
     SensorStateClass.MEASUREMENT, "mdi:propane-tank", lambda r: round(r.kg, 2)),
    ("battery", "Batterie", PERCENTAGE, SensorDeviceClass.BATTERY,
     SensorStateClass.MEASUREMENT, None, lambda r: r.battery),
    ("temperature", "Temperatur", UnitOfTemperature.CELSIUS,
     SensorDeviceClass.TEMPERATURE, SensorStateClass.MEASUREMENT, None,
     lambda r: r.temperature),
    ("quality", "Messqualität", None, None,
     SensorStateClass.MEASUREMENT, "mdi:signal", lambda r: r.quality),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors from a config entry."""
    coordinator: TrumaCoordinator = hass.data[DOMAIN][entry.entry_id]
    address: str = entry.data[CONF_ADDRESS]
    name: str = entry.title

    entities: list = [
        TrumaSensor(coordinator, address, name, desc) for desc in _DESCRIPTIONS
    ]
    entities.append(TrumaLastSeenSensor(coordinator, address, name))
    entities.append(TrumaFilteredLevelSensor(coordinator, address, name))
    entities.append(TrumaFilteredMassSensor(coordinator, address, name))
    async_add_entities(entities)


class _BaseEntity(CoordinatorEntity[TrumaCoordinator]):
    def __init__(self, coordinator: TrumaCoordinator, address: str, name_prefix: str) -> None:
        super().__init__(coordinator)
        self._address = address.upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            name=name_prefix,
            manufacturer="Truma",
            model="LevelControl",
        )


class TrumaSensor(_BaseEntity, SensorEntity):
    """A single measurement value from the LevelControl."""

    def __init__(self, coordinator, address, name_prefix, desc) -> None:
        super().__init__(coordinator, address, name_prefix)
        key, label, unit, dev_class, state_class, icon, getter = desc
        self._getter: Callable[[TrumaReading], object] = getter
        self._attr_name = f"{name_prefix} {label}"
        self._attr_unique_id = f"{self._address}_{key}"
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = dev_class
        self._attr_state_class = state_class
        if icon:
            self._attr_icon = icon

    @property
    def available(self) -> bool:
        # Keep the last value shown; only unavailable before the first success.
        return self.coordinator.data is not None

    @property
    def native_value(self):
        if self.coordinator.data is None:
            return None
        return self._getter(self.coordinator.data)


class TrumaLastSeenSensor(_BaseEntity, SensorEntity):
    """Timestamp of the last successful measurement."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, coordinator, address, name_prefix) -> None:
        super().__init__(coordinator, address, name_prefix)
        self._attr_name = f"{name_prefix} Zuletzt gelesen"
        self._attr_unique_id = f"{self._address}_last_seen"

    @property
    def available(self) -> bool:
        return self.coordinator.last_success_time is not None

    @property
    def native_value(self):
        return self.coordinator.last_success_time


class _FilterStoredData(ExtraStoredData):
    """Filterzustand, den HA zusammen mit dem Entitaetszustand sichert."""

    def __init__(self, data: dict) -> None:
        self._data = data

    def as_dict(self) -> dict:
        return self._data


class TrumaFilteredLevelSensor(_BaseEntity, RestoreEntity, SensorEntity):
    """Plausibilitaetsgefilterter, geglaetteter Fuellstand (siehe smoothing.py).

    Haelt den letzten Wert bei "kein Echo" (Fahrt), verwirft Einzelausreisser und uebernimmt
    einen neuen Pegel (Flaschenwechsel) erst nach drei uebereinstimmenden Messungen.
    """

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:gauge"

    def __init__(self, coordinator, address, name_prefix) -> None:
        super().__init__(coordinator, address, name_prefix)
        self._attr_name = f"{name_prefix} Füllstand geglättet"
        self._attr_unique_id = f"{self._address}_fill_level_filtered"

    async def async_added_to_hass(self) -> None:
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            self.coordinator.restore_filter(extra.as_dict())
        await super().async_added_to_hass()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData:
        return _FilterStoredData(self.coordinator.level_filter.state.as_dict())

    @property
    def available(self) -> bool:
        return self.coordinator.level_filter.display_percent is not None

    @property
    def native_value(self):
        return self.coordinator.level_filter.display_percent

    @property
    def extra_state_attributes(self) -> dict:
        attrs = self.coordinator.level_filter.attributes()
        if self.coordinator.data is not None:
            attrs["rohwert"] = self.coordinator.data.percent
            attrs["rohwert_qualitaet"] = self.coordinator.data.quality
        attrs["fahrt_entitaet"] = self.coordinator.drive_entity or None
        attrs["fahrt_spannung"] = self.coordinator.drive_voltage
        attrs["fahrt_schwelle"] = self.coordinator.drive_min_voltage
        return attrs


class TrumaFilteredMassSensor(_BaseEntity, SensorEntity):
    """Gasmenge aus dem geglaetteten Fuellstand und der erkannten Flaschengroesse."""

    _attr_native_unit_of_measurement = UnitOfMass.KILOGRAMS
    _attr_device_class = SensorDeviceClass.WEIGHT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:propane-tank"

    def __init__(self, coordinator, address, name_prefix) -> None:
        super().__init__(coordinator, address, name_prefix)
        self._attr_name = f"{name_prefix} Gasmenge geglättet"
        self._attr_unique_id = f"{self._address}_gas_amount_filtered"

    @property
    def available(self) -> bool:
        return self.coordinator.level_filter.display_kg is not None

    @property
    def native_value(self):
        return self.coordinator.level_filter.display_kg
