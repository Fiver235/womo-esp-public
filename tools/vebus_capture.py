#!/usr/bin/env python3
"""VE.Bus-Mitschnitt vom ESP32-Sniffer (esphome/vebus-sniffer.yaml) aufzeichnen und auswerten.

    python tools/vebus_capture.py capture [--host 192.168.100.210] [-o logs/x.log] [--seconds N]
    python tools/vebus_capture.py analyze logs/x.log
    python tools/vebus_capture.py selftest

capture schreibt jede Zeile als  <Windows-Uhrzeit> <ESP-Zeit in us> <F|C> <Hex>  (F = Rahmen, C = abgeschnitten)
und zeigt live alle Rahmen, deren Inhalt sich geaendert hat (Sync und Zaehler ausgeblendet). Aktionen am DMC
mit der Uhrzeit notieren, dann lassen sie sich in der Auswertung zuordnen.

Rahmenformat (pv-baxi/esp32ess, ve.bus-library, Victron MK2-Dokument 3.14, siehe docs/DMC-RECHERCHE.md):
    Adresse(2) FD|FE Nummer ...Daten... Pruefsumme FF
Summe aller Bytes ab Index 2 inkl. Pruefsumme und FF ist 0 (mod 256); beim Sync zaehlt die 0x55 an Index 4 nicht.
Ab Index 4 sind 0xFA..0xFF als FA, Wert-0x80 kodiert.
"""

from __future__ import annotations

import argparse
import datetime as dt
import socket
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAGIC = b"\xa5\x5a"
HEADER = struct.Struct("<2sIHB")
SWITCH = {1: "Ladegeraet", 2: "Wechselrichter", 3: "Ein", 4: "Aus"}


def checksum_ok(raw: bytes) -> bool:
    """Prueft den noch kodierten Rahmen."""
    if len(raw) < 5 or raw[-1] != 0xFF:
        return False
    total = sum(raw[2:])
    if raw[2] == 0xFD and raw[4] == 0x55:
        total -= 0x55
    return total & 0xFF == 0


def destuff(raw: bytes) -> bytes:
    """Kopf bleibt, ab Index 4 FA x -> x+0x80. Pruefsumme und FF bleiben unangetastet."""
    out = bytearray(raw[:4])
    body = raw[4:-1]
    i = 0
    while i < len(body):
        b = body[i]
        if b == 0xFA and i + 1 < len(body):
            i += 1
            out.append((body[i] + 0x80) & 0xFF)
        else:
            out.append(b)
        i += 1
    out.append(raw[-1])
    return bytes(out)


def decode_panel(d: bytes) -> str:
    """Panel-Rahmen 0x40 laut MK2-Dokument Abschnitt 5.1 (Bitlage der Schalterstellung noch unbestaetigt)."""
    if not d:
        return "leer"
    info = d[0]
    if info & 0x08:  # erweitertes Format
        pos = (info & 0x03) + 1
        limit = int.from_bytes(d[1:3], "little") / 10 if len(d) >= 3 else None
        return f"erweitert Schalter={SWITCH.get(pos, pos)} Generator={(info >> 2) & 1} Grenze={limit} A"
    pos = info & 0x07
    pot, scale = (d[1], d[2]) if len(d) >= 3 else (None, None)
    amps = pot * scale / 256 if pot is not None else None
    return f"standard Panel-ID={info >> 4} Schalter={SWITCH.get(pos, pos)} Pot={pot} Skala={scale} -> {amps} A"


def decode_led(d: bytes) -> str:
    """MasterMultiLED 0x41, Lage laut ve.bus-library (Daten ab dem Byte nach der Kennung 0x41)."""
    if len(d) < 12:
        return "zu kurz"
    lim = [int.from_bytes(d[i:i + 2], "little") / 10 for i in (5, 7, 9)]
    return (f"typ={d[0]:02X} LED={d[1]:02X} blink={d[2]:02X} status={d[3]:02X} ACcfg={d[4]:02X} "
            f"I_min={lim[0]} I_max={lim[1]} I_ist={lim[2]} A switch={d[11]:02X}")


def describe(raw: bytes) -> dict:
    ok = checksum_ok(raw)
    addr = raw[:2].hex() if len(raw) >= 2 else "?"
    kind = raw[2] if len(raw) >= 3 else -1
    info = {"ok": ok, "addr": addr, "kind": kind, "sync": kind == 0xFD and len(raw) >= 5 and raw[4] == 0x55,
            "cmd": None, "data": b"", "text": ""}
    if info["sync"] or len(raw) < 6:
        return info
    plain = destuff(raw) if raw[-1] == 0xFF else raw
    info["cmd"] = plain[4]
    info["data"] = plain[5:-2] if ok else plain[5:]
    if info["cmd"] == 0x40:
        info["text"] = decode_panel(info["data"])
    elif info["cmd"] == 0x41:
        info["text"] = decode_led(info["data"])
    return info


# ---------------------------------------------------------------------- Aufzeichnung
def read_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("Verbindung vom ESP getrennt")
        buf += chunk
    return bytes(buf)


def read_record(sock: socket.socket) -> tuple[int, int, bytes]:
    head = read_exact(sock, HEADER.size)
    magic, ts, length, flags = HEADER.unpack(head)
    while magic != MAGIC:  # neu aufsetzen, falls der Strom verrutscht ist
        head = head[1:] + read_exact(sock, 1)
        magic, ts, length, flags = HEADER.unpack(head)
    return ts, flags, read_exact(sock, length)


def capture(host: str, port: int, out: Path, seconds: float | None, script: list | None = None) -> int:
    """Zeichnet auf und verbindet neu: Bei VE.Bus-Versorgung kann der ESP im Aus-Zustand stromlos werden.

    script: Liste (Sekunden ab Start, Text). Der Text geht als Befehl an die Werkbank-Firmware (Versuche)."""
    script = sorted(script or [])
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Schreibe nach {out}, Ende mit Strg+C")
    seen: dict[tuple, bytes] = {}
    frames = syncs = bad = 0
    start = time.monotonic()
    next_status = start + 5
    with out.open("a", encoding="ascii", buffering=1) as log:
        log.write(f"# Start {dt.datetime.now().isoformat(timespec='seconds')} {host}\n")
        waiting = False
        try:
            while seconds is None or time.monotonic() - start < seconds:
                now = dt.datetime.now().strftime("%H:%M:%S")
                try:
                    sock = socket.create_connection((host, port), timeout=5)
                except OSError:
                    if not waiting:
                        print(f"{now} {host}:{port} nicht erreichbar, versuche es weiter")
                        log.write(f"# Getrennt {now}\n")
                        waiting = True
                    time.sleep(2)
                    continue
                waiting = False
                print(f"{now} verbunden mit {host}:{port}")
                log.write(f"# Verbindung {now}\n")
                sock.settimeout(10)
                try:
                    while seconds is None or time.monotonic() - start < seconds:
                        ts, flags, data = read_record(sock)
                        now = dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                        if flags == 2:
                            if len(data) == 24 and time.monotonic() >= next_status:
                                f, s, b, ue, ov, dr = struct.unpack("<6I", data)
                                print(f"{now} ESP: Rahmen {f}, Sync {s}, Bytes {b}, UART-Fehler {ue}, "
                                      f"Ueberlaeufe {ov}, verworfen {dr} | hier: {frames} Rahmen, "
                                      f"{bad} Pruefsummenfehler")
                                log.write(f"# stats {now} {f} {s} {b} {ue} {ov} {dr}\n")
                                next_status = time.monotonic() + 5
                            continue
                        while script and time.monotonic() - start >= script[0][0]:
                            text = script.pop(0)[1]
                            sock.sendall(text.encode("ascii"))
                            print(f"{now} Befehl an den ESP: {text}")
                        if flags == 4:  # vom ESP selbst gesendet (Werkbank), nur ins Log
                            log.write(f"{now} {ts} T {data.hex()}\n")
                            continue
                        if flags == 5:  # Befehl, vom ESP bestaetigt
                            log.write(f"# cmd {now} {ts} {data.decode('ascii', 'replace')}\n")
                            continue
                        log.write(f"{now} {ts} {'C' if flags else 'F'} {data.hex()}\n")
                        frames += 1
                        info = describe(data)
                        bad += 0 if (info["ok"] or flags) else 1  # abgeschnitten ist kein Pruefsummenfehler
                        syncs += 1 if info["sync"] else 0
                        if info["sync"] or flags:
                            continue
                        key = (info["addr"], info["kind"], info["cmd"])
                        if seen.get(key) != info["data"]:
                            seen[key] = info["data"]
                            cmd = "--" if info["cmd"] is None else f"{info['cmd']:02X}"
                            print(f"{now} {info['addr']} cmd {cmd} {info['data'].hex(' ')} {info['text']}")
                except OSError as err:
                    print(f"{dt.datetime.now():%H:%M:%S} Verbindung verloren: {err}")
                finally:
                    sock.close()
        except KeyboardInterrupt:
            pass
    print(f"Ende: {frames} Rahmen, davon {syncs} Sync, {bad} Pruefsummenfehler")
    return 0


# ---------------------------------------------------------------------- Auswertung
def analyze(path: Path) -> int:
    groups: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "bad": 0, "payloads": defaultdict(int), "times": [],
                                                     "slot": [], "first": None})
    last_sync = None
    syncs = []
    cut = 0
    changes: list[str] = []
    last_payload: dict[tuple, bytes] = {}
    base = last_abs = 0     # fortlaufende Zeit ueber 32-Bit-Ueberlauf und ESP-Neustarts
    prev_raw = None
    restarts = 0
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("# Verbindung"):
            restarts += 1
            base, prev_raw, last_sync = last_abs, None, None
            continue
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 4:
            continue
        now, ts, typ, hexdata = parts[0], int(parts[1]), parts[2], parts[3]
        if prev_raw is not None and ts < prev_raw:
            base += 1 << 32
        prev_raw = ts
        ts += base
        last_abs = ts
        if typ == "C":
            cut += 1
            continue
        raw = bytes.fromhex(hexdata)
        info = describe(raw)
        if info["sync"]:
            if last_sync is not None:
                syncs.append((ts - last_sync) / 1000)
            last_sync = ts
            continue
        key = (info["addr"], info["kind"], info["cmd"])
        g = groups[key]
        g["n"] += 1
        g["bad"] += 0 if info["ok"] else 1
        g["payloads"][info["data"]] += 1
        g["times"].append(ts)
        g["first"] = g["first"] or hexdata
        if last_sync is not None:
            g["slot"].append((ts - last_sync) / 1000)
        if info["ok"] and last_payload.get(key) != info["data"]:
            last_payload[key] = info["data"]
            if info["cmd"] in (0x40, 0x41):
                changes.append(f"{now} {info['addr']} {info['cmd']:02X} {info['data'].hex(' ')}  {info['text']}")

    if syncs:
        print(f"Sync: {len(syncs) + 1} Stueck, Abstand {min(syncs):.2f} / {sum(syncs) / len(syncs):.2f} / "
              f"{max(syncs):.2f} ms (min/mittel/max)")
    print(f"Verbindungen: {restarts}, abgeschnittene Rahmen: {cut}\n")
    print("Adresse Art Befehl     Anzahl Fehler Varianten  Abstand ms  nach Sync ms min/max  erstes Beispiel")
    for key in sorted(groups, key=lambda k: (k[0], k[1], -1 if k[2] is None else k[2])):
        g = groups[key]
        times = g["times"]
        gap = (times[-1] - times[0]) / 1000 / (len(times) - 1) if len(times) > 1 else 0
        slot = f"{min(g['slot']):7.2f}/{max(g['slot']):7.2f}" if g["slot"] else "      -"
        cmd = "--" if key[2] is None else f"{key[2]:02X}"
        print(f"{key[0]:7s} {key[1]:02X}  {cmd:6s} {g['n']:9d} {g['bad']:6d} {len(g['payloads']):9d} {gap:11.1f}  "
              f"{slot:>17s}  {g['first'][:48]}")
    print("\nAenderungen von Panel-Rahmen 0x40 und LED-Rahmen 0x41 (mit den notierten Aktionen vergleichen):")
    print("\n".join(changes) if changes else "keine")
    return 0


# ---------------------------------------------------------------------- Selbsttest
def selftest() -> int:
    sync = bytes.fromhex("8383FD0255511802 97FF")           # Beispiel aus esp32ess
    e4 = bytes.fromhex("8383FE03E48050C3400D03000E000000A809007AFF")  # Beispiel aus esp32ess
    assert checksum_ok(sync), "Sync-Pruefsumme"
    assert checksum_ok(e4), "E4-Pruefsumme"
    assert describe(sync)["sync"]
    assert describe(e4)["cmd"] == 0xE4
    assert not checksum_ok(e4[:-2] + b"\x7b\xff"), "falsche Pruefsumme muss auffallen"
    # Kodierung: 0xFF im Datenteil = FA 7F
    assert destuff(bytes.fromhex("8383FE0141FA7F00FF"))[4:6] == b"\x41\xff"
    # Panel-Rahmen, standard und erweitert (MK2-Dokument 5.1)
    assert "Schalter=Ein" in decode_panel(bytes([0x03, 128, 16])) and "8.0 A" in decode_panel(bytes([0x03, 128, 16]))
    assert "Schalter=Ein" in decode_panel(bytes([0x0A, 0xA0, 0x00])) and "16.0 A" in decode_panel(bytes([0x0A, 0xA0, 0x00]))
    # LED-Rahmen: Lage laut ve.bus-library, frame[4]=41, frame[5]=10 ...
    led = bytes([0x10, 0x01, 0x00, 0x02, 0x80, 0x2C, 0x01, 0xA0, 0x00, 0xA0, 0x00, 0x30])
    assert "I_max=16.0" in decode_led(led) and "switch=30" in decode_led(led)

    # Ende-zu-Ende: gleiches Datensatzformat wie vebus_sniffer.h ueber echtes TCP
    import tempfile
    import threading
    srv = socket.create_server(("127.0.0.1", 0))
    port = srv.getsockname()[1]

    def feed() -> None:
        conn, _ = srv.accept()
        srv.close()  # danach ist der ESP "stromlos": capture muss weiter versuchen, ohne zu haengen
        for i, (flags, data) in enumerate([(0, sync), (0, e4), (1, b"\x83\x83"), (2, struct.pack("<6I", 2, 1, 31, 0, 0, 0))]):
            conn.sendall(HEADER.pack(MAGIC, 1000 + i * 20000, len(data), flags) + data)
        conn.close()

    threading.Thread(target=feed, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "t.log"
        capture("127.0.0.1", port, out, 2)  # Sender schliesst nach den Testdaten
        text = out.read_text()
        assert "# Verbindung" in text and "# Getrennt" in text, text
        lines = [x for x in text.splitlines() if not x.startswith("#")]
        assert len(lines) == 3, lines
        assert lines[0].split()[2:] == ["F", sync.hex()] and lines[2].split()[2] == "C"
        assert analyze(out) == 0
    print("Selbsttest OK")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--host", default="192.168.100.210")  # WireGuard-Adresse des Sniffers
    c.add_argument("--port", type=int, default=8484)
    c.add_argument("-o", "--out")
    c.add_argument("--seconds", type=float)
    c.add_argument("--script", default="",
                   help="nur Werkbank: Befehle an die Firmware, z. B. '0=L1 R0,20=De4,40=A' (Sekunde=Text)")
    a = sub.add_parser("analyze")
    a.add_argument("file")
    sub.add_parser("selftest")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    if args.cmd == "capture":
        name = args.out or str(ROOT / "logs" / f"vebus-{dt.datetime.now():%Y%m%d-%H%M%S}.log")
        script = [(float(t), text) for t, text in (item.split("=", 1) for item in args.script.split(",") if item)]
        return capture(args.host, args.port, Path(name), args.seconds, script)
    if args.cmd == "analyze":
        return analyze(Path(args.file))
    return selftest()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
