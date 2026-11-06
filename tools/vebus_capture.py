#!/usr/bin/env python3
"""VE.Bus-Mitschnitt vom ESP32-Sniffer (esphome/vebus-sniffer.yaml) aufzeichnen und auswerten.

    python tools/vebus_capture.py capture [--host 192.168.100.210] [-o logs/x.log] [--seconds N]
    python tools/vebus_capture.py analyze logs/x.log
    python tools/vebus_capture.py selftest

capture schreibt jede Zeile als  <Windows-Uhrzeit> <ESP-Zeit in us> <F|C|T|E> <Hex>  (F = Rahmen, C = abgeschnitten, T = vom ESP gesendet,
E = Flanken eines Rahmens aus vebus_edges.h, Auswertung mit "edges")
und zeigt live alle Rahmen, deren Inhalt sich geaendert hat (Sync und Zaehler ausgeblendet). Aktionen am DMC
mit der Uhrzeit notieren, dann lassen sie sich in der Auswertung zuordnen.

Rahmenformat (pv-baxi/esp32ess, ve.bus-library, Victron MK2-Dokument 3.14, siehe docs/DMC-RECHERCHE.md):
    Adresse(2) FD|FE Nummer ...Daten... Pruefsumme FF
Summe aller Bytes ab Index 2 inkl. Pruefsumme und FF ist 0 (mod 256); beim Sync zaehlt die 0x55 an Index 4 nicht.
Ab Index 4 sind 0xFA..0xFF als FA, Wert-0x80 kodiert.
"""

from __future__ import annotations

import argparse
import bisect
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
                        if flags == 6:  # Flanken eines Rahmens (vebus_edges.h), nur ins Log
                            log.write(f"{now} {ts} E {data.hex()}\n")
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
        if typ == "E":      # Flanken, eigene Auswertung mit "edges"
            continue
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


# ---------------------------------------------------------------------- Flanken
TICK_NS = 25.0              # Aufloesung in vebus_edges.h
BIT_NS = 1e9 / 256000       # Soll-Bitdauer


def edge_segments(data: bytes) -> list[tuple[int, float]]:
    """RMT-Symbole -> Abschnitte (Pegel, Dauer in ns). Dauer 0 beendet den Rahmen."""
    seg: list[tuple[int, float]] = []
    for (word,) in struct.iter_unpack("<I", data[: len(data) // 4 * 4]):
        for dur, lvl in ((word & 0x7FFF, (word >> 15) & 1), ((word >> 16) & 0x7FFF, word >> 31)):
            if dur == 0:
                return seg
            seg.append((lvl, dur * TICK_NS))
    return seg


def edge_decode(seg: list[tuple[int, float]]) -> dict:
    """Dekodiert die Abschnitte als 8N1 und misst die Flanken gegen das Bitraster jedes Bytes."""
    starts, levels, t = [], [], 0.0
    for lvl, dur in seg:
        starts.append(t)
        levels.append(lvl)
        t += dur
    end = t

    def level(at: float) -> int:
        if at >= end or not starts:
            return 1        # nach dem Rahmen: Ruhepegel
        return levels[max(0, bisect.bisect_right(starts, at) - 1)]

    out = {"bytes": [], "starts": [], "stop_bad": 0, "rise": [], "fall": [], "fit": [0.0, 0.0],
           "short": min((d for _, d in seg), default=0.0)}
    pos, i = 0.0, 0
    while True:
        j = next((k for k in range(i, len(starts)) if levels[k] == 0 and starts[k] >= pos - 1), None)
        if j is None:
            break
        t0 = starts[j]
        value = 0
        for b in range(8):
            value |= level(t0 + (b + 1.5) * BIT_NS) << b
        out["stop_bad"] += 0 if level(t0 + 9.5 * BIT_NS) else 1
        out["bytes"].append(value)
        out["starts"].append(t0)
        pos = t0 + 9.5 * BIT_NS
        for k in range(j + 1, len(starts)):   # Flanken innerhalb des Bytes
            dt = starts[k] - t0
            if dt >= pos - t0:
                break
            n = round(dt / BIT_NS)
            out["rise" if levels[k] else "fall"].append(dt - n * BIT_NS)
            out["fit"][0] += dt * n
            out["fit"][1] += n * n
        i = j + 1
    return out


def edge_wave(frame: bytes, stop_bits: int = 1, gap_after: dict | None = None) -> bytes:
    """Nur fuer den Selbsttest: 8N1-Signal eines Rahmens als RMT-Symbole. gap_after: Byteindex -> Zusatzbits Pause."""
    bits: list[int] = []
    for idx, byte in enumerate(frame):
        bits += [0] + [(byte >> b) & 1 for b in range(8)] + [1] * stop_bits
        bits += [1] * (gap_after or {}).get(idx, 0)
    runs: list[list[int]] = []
    for bit in bits:
        if runs and runs[-1][0] == bit:
            runs[-1][1] += 1
        else:
            runs.append([bit, 1])
    if runs[-1][0] == 1:
        runs.pop()          # Ruhe am Ende: die Hardware meldet sie als Dauer 0
    durs = [(lvl, round(n * BIT_NS / TICK_NS)) for lvl, n in runs] + [(1, 0)]
    if len(durs) % 2:
        durs.append((0, 0))
    return b"".join(struct.pack("<I", d0 | l0 << 15 | d1 << 16 | l1 << 31)
                    for (l0, d0), (l1, d1) in zip(durs[0::2], durs[1::2]))


def edges(path: Path, examples: int) -> int:
    groups: dict[str, dict] = defaultdict(lambda: {"n": 0, "ok": 0, "gaps": [], "bit": [], "rise": [], "fall": [],
                                                   "short": [], "stop_bad": 0, "examples": []})
    total = 0
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        parts = line.split()
        if len(parts) != 4 or parts[2] != "E":
            continue
        total += 1
        seg = edge_segments(bytes.fromhex(parts[3]))
        d = edge_decode(seg)
        raw = bytes(d["bytes"])
        first = raw[: raw.index(0xFF) + 1] if 0xFF in raw else raw    # ein Datensatz kann mehrere Rahmen enthalten
        if len(first) >= 5 and first[2] in (0xFC, 0xFD, 0xFE):
            name = f"{first[:2].hex()} " + ("Sync" if first[2] == 0xFD else f"{first[2]:02X} {first[4]:02X}")
        else:
            name = "unklar"   # Aufzeichnung begann mitten im Rahmen, oder Stoerung
        g = groups[name]
        g["n"] += 1
        g["ok"] += 1 if checksum_ok(first) else 0
        st = d["starts"][: len(first)]
        g["gaps"] += [(b - a) / BIT_NS for a, b in zip(st, st[1:])]
        if d["fit"][1]:
            g["bit"].append(d["fit"][0] / d["fit"][1])
        g["rise"] += d["rise"]
        g["fall"] += d["fall"]
        g["short"].append(d["short"])
        g["stop_bad"] += d["stop_bad"]
        if len(g["examples"]) < examples:
            g["examples"].append((parts[0], first, st, seg))
    if not total:
        print("Keine Flanken-Zeilen (E) im Log. Firmware vebus-sniffer-edges.yaml und Befehl E<n> pruefen.")
        return 1

    def stat(v: list[float], f: str = "{:.2f}") -> str:
        return "-" if not v else "/".join(f.format(x) for x in (min(v), sum(v) / len(v), max(v)))

    print(f"{total} Datensaetze mit Flanken. Bitdauer Soll {BIT_NS:.1f} ns, Byteabstand Soll 10,00 Bit (8N1 ohne Pause).\n")
    print("Rahmen          Anzahl   ok  Byteabstand Bit    Bitdauer ns           steigend  fallend  kuerzester  Stopp-")
    print("                             min/mittel/max     min/mittel/max        ns        ns       Puls ns     fehler")
    for name in sorted(groups, key=lambda k: -groups[k]["n"]):
        g = groups[name]
        rise = f"{sum(g['rise']) / len(g['rise']):+.0f}" if g["rise"] else "-"
        fall = f"{sum(g['fall']) / len(g['fall']):+.0f}" if g["fall"] else "-"
        print(f"{name:14s} {g['n']:7d} {g['ok']:4d}  {stat(g['gaps']):18s} {stat(g['bit'], '{:.1f}'):21s} "
              f"{rise:>8s} {fall:>8s} {min(g['short']):11.0f} {g['stop_bad']:10d}")
    print("\nSteigend und fallend: mittlere Abweichung der Flanken vom Bitraster des Bytes.")
    print("Beispiele: je Byte der Wert und der Abstand zum Byte davor in Bit, danach die Pulse in Bit (L = Low, H = High)")
    for name in sorted(groups, key=lambda k: -groups[k]["n"]):
        for now, first, st, seg in groups[name]["examples"]:
            gaps = [""] + [f"{(b - a) / BIT_NS:.2f}" for a, b in zip(st, st[1:])]
            print(f"\n{name}  {now}")
            print("  " + " ".join(f"{v:02x}" + (f"(+{gp})" if gp else "") for v, gp in zip(first, gaps)))
            print("  " + " ".join(f"{'H' if lvl else 'L'}{dur / BIT_NS:.2f}" for lvl, dur in seg[:120]))
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
    # Flanken: 8N1 dicht an dicht, mit zwei Stoppbits und mit einer Pause nach dem 0x55
    for stop, gap, want in ((1, None, [10.0] * 9), (2, None, [11.0] * 9), (1, {4: 3}, [10.0] * 4 + [13.0] + [10.0] * 4)):
        d = edge_decode(edge_segments(edge_wave(sync, stop, gap)))
        assert bytes(d["bytes"]) == sync and d["stop_bad"] == 0, d
        got = [(b - a) / BIT_NS for a, b in zip(d["starts"], d["starts"][1:])]
        assert all(abs(x - y) < 0.02 for x, y in zip(got, want)), got
        assert abs(d["fit"][0] / d["fit"][1] - BIT_NS) < 5, d["fit"]

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
    e = sub.add_parser("edges")
    e.add_argument("file")
    e.add_argument("--examples", type=int, default=2, help="Beispiele je Rahmenart")
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
    if args.cmd == "edges":
        return edges(Path(args.file), args.examples)
    return selftest()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
