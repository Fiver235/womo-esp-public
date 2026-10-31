"""Truma LevelControl manual-measure button (config-entry based)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import TrumaCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the measure button from a config entry."""
    coordinator: TrumaCoordinator = hass.data[DOMAIN][entry.entry_id]
    address: str = entry.data[CONF_ADDRESS]
    async_add_entities([TrumaMeasureButton(coordinator, address, entry.title)])


class TrumaMeasureButton(ButtonEntity):
    """Press to take a fresh measurement now."""

    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: TrumaCoordinator, address: str, name_prefix: str) -> None:
        self._coordinator = coordinator
        self._address = address.upper()
        self._attr_name = f"{name_prefix} Messung auslösen"
        self._attr_unique_id = f"{self._address}_measure_now"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            name=name_prefix,
            manufacturer="Truma",
            model="LevelControl",
        )

    async def async_press(self) -> None:
        await self._coordinator.async_request_refresh()
