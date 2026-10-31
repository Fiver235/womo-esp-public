"""Low-level Truma LevelControl BLE access and measurement parsing.

Reverse-engineered from the official app (LevelControl 2.2.1) and verified
against real readings. Connection uses bleak_retry_connector - the same
helper Home Assistant's own BLE integrations use - so the sporadic
connect/service-discovery timeouts of plain bleak are retried automatically.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import (
    MEASURE_WAIT_S,
    TRIGGER_GO,
    TRIGGER_INIT,
    UUID_MEASUREMENT,
    UUID_PASSWORD,
    UUID_STORE_NV,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class TrumaReading:
    """One parsed measurement."""

    percent: int
    grams: int
    battery: int
    temperature: int
    quality: int
    raw: str

    @property
    def kg(self) -> float:
        return self.grams / 1000.0


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) & 0xFF
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for b in data:
        i = (i + 1) & 0xFF
        j = (j + s[i]) & 0xFF
        s[i], s[j] = s[j], s[i]
        out.append(b ^ s[(s[i] + s[j]) & 0xFF])
    return bytes(out)


def _derive_key(password: bytes) -> bytes:
    """RC4 key = 5-byte password XOR the ASCII bytes of "TRUMA"."""
    if len(password) != 5:
        raise ValueError(f"password must be 5 bytes, got {len(password)}")
    return bytes(p ^ m for p, m in zip(password, b"TRUMA"))


def _parse(dec: bytes) -> TrumaReading:
    grams = int.from_bytes(dec[1:3], "little") * 100
    return TrumaReading(
        percent=dec[0],
        grams=grams,
        battery=dec[3],
        temperature=dec[4],
        quality=(dec[6] >> 6) & 0b11 if len(dec) > 6 else 0,
        raw=dec.hex(" "),
    )


async def async_read_measurement(device: BLEDevice, name: str = "Truma") -> TrumaReading:
    """Connect (with retries), trigger a fresh measurement, read and decode it.

    `device` must be a BLEDevice from HA's bluetooth helper.
    """
    client = await establish_connection(
        BleakClientWithServiceCache,
        device,
        name,
        max_attempts=4,
    )
    try:
        password = bytes(await client.read_gatt_char(UUID_PASSWORD))
        key = _derive_key(password)

        # Force a fresh measurement: initialize (0x03) then trigger (0x02).
        for value in (TRIGGER_INIT, TRIGGER_GO):
            try:
                await client.write_gatt_char(
                    UUID_STORE_NV, bytes([value]), response=False
                )
                await asyncio.sleep(0.4)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("trigger write %#x failed: %s", value, err)

        await asyncio.sleep(MEASURE_WAIT_S)

        raw = bytes(await client.read_gatt_char(UUID_MEASUREMENT))
        dec = _rc4(key, raw)
        reading = _parse(dec)
        _LOGGER.debug("measurement raw=%s decoded=%s", raw.hex(" "), reading)
        return reading
    finally:
        await client.disconnect()
