"""Polling coordinator for the Truma LevelControl."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
import time

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .smoothing import FilterState, LevelFilter
from .truma import TrumaReading, async_read_measurement

_LOGGER = logging.getLogger(__name__)


class TrumaCoordinator(DataUpdateCoordinator[TrumaReading]):
    """Connects to the sensor on a schedule and keeps the latest reading."""

    def __init__(
        self, hass: HomeAssistant, address: str, poll_interval: int
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {address}",
            update_interval=timedelta(seconds=poll_interval),
        )
        self.address = address.upper()
        self.last_success_time: datetime | None = None
        # Plausibilitaetsfilter (smoothing.py). Jede erfolgreiche Messung laeuft genau einmal hindurch.
        self.level_filter = LevelFilter()

    def restore_filter(self, state: dict) -> None:
        """Filterzustand aus dem letzten HA-Lauf uebernehmen (von der Sensor-Entitaet aufgerufen).

        Die erste Messung ist zu diesem Zeitpunkt meist schon in einen leeren Filter gelaufen;
        sie wird auf den wiederhergestellten Zustand noch einmal angewendet.
        """
        self.level_filter = LevelFilter(FilterState.from_dict(state))
        if self.data is not None and self.last_success_time is not None:
            self._apply_filter(self.data, self.last_success_time.timestamp())

    def _apply_filter(self, reading: TrumaReading, ts: float) -> None:
        self.level_filter.update(reading.percent, reading.grams, reading.quality, ts)
        _LOGGER.debug(
            "%s filter: raw %s%% q%s -> %s%% (%s)",
            self.address, reading.percent, reading.quality,
            self.level_filter.display_percent, self.level_filter.state.status,
        )

    async def _async_update_data(self) -> TrumaReading:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if ble_device is None:
            _LOGGER.debug("%s not advertising right now, will retry", self.address)
            raise UpdateFailed("sensor not advertising right now")
        try:
            reading = await async_read_measurement(ble_device, name=self.address)
            self.last_success_time = dt_util.utcnow()
            self._apply_filter(reading, time.time())
            return reading
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("read attempt failed: %s", err)
            raise UpdateFailed("sensor not reachable this cycle") from err
