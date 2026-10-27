#!/usr/bin/env python3
"""Alle lesbaren GATT-Characteristics eines Truma LevelControl ueber den ESPHome-Bluetooth-Proxy auslesen.

Nur LESEN. Zweck: Flaschentyp-Konfiguration finden (Vergleich zweier Sensoren).
Verbindet sich direkt per aioesphomeapi mit dem Proxy (womo-ble-proxy), nicht ueber Home Assistant.
ACHTUNG: Der Proxy bedient nur die zuletzt abonnierte API-Verbindung. Danach in Home Assistant den
ESPHome-Eintrag "Womo BLE-Proxy" neu laden, sonst bekommt HA keine Advertisements mehr.

Aufruf (Projekt-Venv, Notebook im Womo-WLAN oder Tunnel):
    python tools/levelcontrol_dump.py 90:7B:C6:43:20:B0 00:81:F9:6F:B2:DE [--proxy 192.168.1.241] [--json out.json]

Fuer jede Characteristic: Handle, UUID, Rohbytes, ASCII und (falls Passwort lesbar) RC4-Entschluesselung
mit Schluessel = Passwort XOR "TRUMA" (Protokoll aus cyclemat/HAOS-Truma-Levelcontrol-Integration).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import aioesphomeapi

ROOT = Path(__file__).resolve().parent.parent
UUID_PASSWORD = "22bfa619-6afe-4cc5-b3ff-3e140baedeb6"
PROP_READ = 0x02


def read_secret(name: str) -> str:
    text = (ROOT / "esphome" / "secrets.yaml").read_text(encoding="utf-8")
    m = re.search(rf'^{name}:\s*"?([^"\n]+)"?', text, re.M)
    if not m:
        raise SystemExit(f"{name} nicht in esphome/secrets.yaml")
    return m.group(1).strip()


def mac_to_int(mac: str) -> int:
    return int(mac.replace(":", ""), 16)


def rc4(key: bytes, data: bytes) -> bytes:
    S = list(range(256))
    j = 0
    for i in range(256):
        j = (j + S[i] + key[i % len(key)]) & 0xFF
        S[i], S[j] = S[j], S[i]
    out = bytearray()
    i = j = 0
    for b in data:
        i = (i + 1) & 0xFF
        j = (j + S[i]) & 0xFF
        S[i], S[j] = S[j], S[i]
        out.append(b ^ S[(S[i] + S[j]) & 0xFF])
    return bytes(out)


class Rc4Stream:
    """Fortlaufender RC4-Keystream (wird pro Verbindung neu begonnen)."""

    def __init__(self) -> None:
        self.pos = 0

    def take(self, key: bytes, n: int) -> bytes:
        ks = rc4(key, bytes(self.pos + n))  # Keystream = RC4 ueber Nullen
        out = ks[self.pos : self.pos + n]
        self.pos += n
        return out


def printable(b: bytes) -> str:
    return "".join(chr(x) if 32 <= x < 127 else "." for x in b)


async def dump_device(api: aioesphomeapi.APIClient, feature_flags: int, mac: str, adv_wait: float, writes=None, write_encrypt=False) -> dict:
    addr = mac_to_int(mac)
    connected = asyncio.get_running_loop().create_future()

    def on_state(state: bool, mtu: int, error: int) -> None:
        if not connected.done():
            if state:
                connected.set_result(True)
            else:
                connected.set_exception(RuntimeError(f"connect failed, error={error}"))
        elif not state:
            print(f"  [{mac}] getrennt (error={error})")

    print(f"\n=== {mac} ===")
    # Die Sensoren senden nur alle paar Minuten ein Advertisement; ein Verbindungsaufbau ohne
    # vorheriges Advertisement laeuft in den Timeout. Also erst auf das Advertisement warten.
    seen = asyncio.get_running_loop().create_future()

    def on_adv(resp) -> None:
        for adv in resp.advertisements:
            if adv.address == addr and not seen.done():
                seen.set_result((adv.rssi, adv.address_type))

    # WICHTIG: Der ESPHome-Proxy nimmt Verbindungsauftraege nur von der API-Verbindung an, die gerade
    # Advertisements abonniert hat. Das Abo muss also waehrend des gesamten Zugriffs bestehen bleiben.
    unsub_adv = api.subscribe_bluetooth_le_raw_advertisements(on_adv)
    print(f"  warte auf Advertisement (max {adv_wait:.0f} s) ...")
    try:
        rssi, atype = await asyncio.wait_for(seen, adv_wait)
    except asyncio.TimeoutError:
        unsub_adv()
        raise RuntimeError("kein Advertisement gesehen")
    print(f"  Advertisement gesehen: RSSI {rssi} dB, address_type {atype} -> verbinde")
    unsub = await api.bluetooth_device_connect(addr, on_state, timeout=40.0, feature_flags=feature_flags, address_type=atype)
    try:
        await asyncio.wait_for(connected, 45)
        print("  verbunden")
        services = await api.bluetooth_gatt_get_services(addr)
        result = {"address": mac, "characteristics": []}
        password = None
        stream = Rc4Stream()
        chars = []
        for svc in services.services:
            for ch in svc.characteristics:
                chars.append((svc.uuid, ch))
        # Passwort zuerst, damit die Entschluesselung fuer alle anderen bereitsteht
        chars.sort(key=lambda t: 0 if t[1].uuid == UUID_PASSWORD else 1)
        if writes:
            # Erst Passwort lesen (Schluessel), dann schreiben, dann alles lesen (Kontrolle).
            pw_ch = next(ch for _, ch in chars if ch.uuid == UUID_PASSWORD)
            password = bytes(await api.bluetooth_gatt_read(addr, pw_ch.handle, timeout=15.0))
            key = bytes(p ^ m for p, m in zip(password, b"TRUMA"))
            wstream = Rc4Stream()
            for short, payload in writes:
                plain = short.startswith("!")
                short = short.lstrip("!")
                target = next(ch for _, ch in chars if ch.uuid[4:8] == short)
                data = payload
                if write_encrypt and not plain:
                    data = bytes(a ^ b for a, b in zip(payload, wstream.take(key, len(payload))))
                print(f"  SCHREIBE h{target.handle} {short}: {payload.hex(' ')}" + (f" (verschluesselt: {data.hex(' ')})" if (write_encrypt and not plain) else " (plain)"))
                await api.bluetooth_gatt_write(addr, target.handle, data, response=True, timeout=15.0)
            print("  Schreiben fertig, trenne und lese in neuer Verbindung zur Kontrolle")
            return {"address": mac, "written": [(s_, p_.hex()) for s_, p_ in writes]}
        for svc_uuid, ch in chars:
            entry = {"service": svc_uuid, "uuid": ch.uuid, "handle": ch.handle, "properties": ch.properties}
            if ch.properties & PROP_READ:
                try:
                    data = bytes(await api.bluetooth_gatt_read(addr, ch.handle, timeout=15.0))
                    entry["hex"] = data.hex(" ")
                    entry["ascii"] = printable(data)
                    if ch.uuid == UUID_PASSWORD and len(data) == 5:
                        password = data
                    if password and ch.uuid != UUID_PASSWORD and ch.uuid[4:8] != "a617" and svc_uuid.startswith("22bfa601") and data:
                        # Der Sensor fuehrt den RC4-Keystream ueber alle Reads der 22bfa601-Characteristics
                        # innerhalb einer Verbindung fort (bestaetigt 27.10.2026).
                        key = bytes(p ^ m for p, m in zip(password, b"TRUMA"))
                        dec = bytes(a ^ b for a, b in zip(data, stream.take(key, len(data))))
                        entry["rc4_hex"] = dec.hex(" ")
                        entry["rc4_ascii"] = printable(dec)
                except Exception as e:  # noqa: BLE001
                    entry["error"] = repr(e)
            result["characteristics"].append(entry)
            short = ch.uuid[4:8] if ch.uuid.endswith("0000-1000-8000-00805f9b34fb") else ch.uuid[:8]
            line = f"  h{ch.handle:3d} {short} p={ch.properties:02x} "
            if "hex" in entry:
                line += f"{entry['hex']}  |{entry['ascii']}|"
                if "rc4_hex" in entry:
                    line += f"  rc4: {entry['rc4_hex']} |{entry['rc4_ascii']}|"
            elif "error" in entry:
                line += f"FEHLER {entry['error']}"
            else:
                line += "(nicht lesbar)"
            print(line)
        return result
    finally:
        try:
            await api.bluetooth_device_disconnect(addr, timeout=10.0)
        except Exception:  # noqa: BLE001
            pass
        unsub()
        unsub_adv()


async def run(args: argparse.Namespace) -> int:
    api = aioesphomeapi.APIClient(args.proxy, 6053, "", noise_psk=read_secret("proxy_api_encryption_key"))
    await api.connect(login=True)
    try:
        info = await api.device_info()
        flags = info.bluetooth_proxy_feature_flags_compat(api.api_version)
        print(f"Proxy {info.name} ({info.mac_address}), BLE-Proxy-Flags {flags}")
        results = []
        writes = []
        for w in args.write or []:
            short, hexdata = w.split(":", 1)
            writes.append((short.lower(), bytes.fromhex(hexdata)))
        if writes and len(args.addresses) != 1:
            raise SystemExit("--write nur mit genau einer Adresse")
        for mac in args.addresses:
            try:
                results.append(await dump_device(api, flags, mac, args.adv_wait, writes, args.write_encrypt))
            except Exception as e:  # noqa: BLE001
                print(f"  [{mac}] FEHLER: {e!r}")
                results.append({"address": mac, "error": repr(e)})
        if args.json:
            Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")
            print(f"\nJSON: {args.json}")
        return 0
    finally:
        await api.disconnect()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("addresses", nargs="+")
    ap.add_argument("--proxy", default="192.168.1.241")
    ap.add_argument("--json")
    ap.add_argument("--adv-wait", type=float, default=300.0, help="max. Wartezeit auf ein Advertisement je Sensor (s)")
    ap.add_argument("--write", action="append", help="Characteristic schreiben, Form KURZ:HEX (z. B. a612:7265...). Praefix ! = immer Klartext (z. B. !a617:01). Nur eine Adresse. VORSICHT.")
    ap.add_argument("--write-encrypt", action="store_true", help="Schreibdaten mit fortlaufendem RC4-Strom verschluesseln")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    return asyncio.run(run(a))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
