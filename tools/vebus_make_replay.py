#!/usr/bin/env python3
"""Erzeugt esphome/vebus_dmc_replay.h aus einem VE.Bus-Mitschnitt fuer den Werkbanktest mit dem DMC.

    python tools/vebus_make_replay.py logs/x.log --start HH:MM:SS.mmm --loop HH:MM:SS.mmm --end HH:MM:SS.mmm

Uebernommen werden nur die Rahmen des MultiPlus (Adresse 8383): einmal ab --start (Hochlauf), danach
endlos der Abschnitt von --loop bis --end. Die Rahmennummer und die Pruefsumme setzt die Firmware beim
Senden neu, weil sich die Nummer alle Teilnehmer teilen. Das Skript prueft die Berechnung vorher an allen
MultiPlus-Rahmen des Mitschnitts und bricht bei einer Abweichung ab.

Eintrag im Blob: u16 Abstand zum vorigen Rahmen in 100 us | u8 Laenge | Rahmen ohne Pruefsumme und FF
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"(\S+) (\d+) F ([0-9a-f]+)$")
ADDR = bytes.fromhex("8383")


def split_frame(raw: bytes) -> tuple[bytes, bytes]:
    """Trennt den kodierten Rahmen in Kopf+Daten und die kodierte Pruefsumme (ohne FF)."""
    end = len(raw) - 1
    if end >= 2 and raw[end - 2] == 0xFA:
        return raw[: end - 2], raw[end - 2 : end]
    return raw[: end - 1], raw[end - 1 : end]


def checksum(head: bytes) -> bytes:
    """Kodierte Pruefsumme: Summe ab Index 2 inkl. Pruefsumme und FF ist 0, beim Sync ohne die 0x55."""
    total = sum(head[2:]) + 0xFF
    if head[2] == 0xFD and head[4] == 0x55:
        total -= 0x55
    value = -total & 0xFF
    return bytes([0xFA, value - 0xFA]) if value > 0xFA else bytes([value])  # 0xFA steht im Mitschnitt allein


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--start", required=True)
    ap.add_argument("--loop", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("-o", "--out", default=str(ROOT / "esphome" / "vebus_dmc_replay.h"))
    args = ap.parse_args()

    frames: list[tuple[str, int, bytes]] = []
    for line in Path(args.log).read_text(encoding="ascii", errors="replace").splitlines():
        m = LINE.match(line.strip())
        if m:
            raw = bytes.fromhex(m[3])
            if raw[:2] == ADDR and raw[-1] == 0xFF and len(raw) >= 6:
                frames.append((m[1], int(m[2]), raw))

    wrong = sum(1 for _, _, raw in frames if checksum(split_frame(raw)[0]) != split_frame(raw)[1])
    print(f"{len(frames)} MultiPlus-Rahmen, Pruefsumme falsch berechnet: {wrong}")
    if wrong or not frames:
        return 1

    picked = [f for f in frames if args.start <= f[0] < args.end]
    loop_index = next(i for i, f in enumerate(picked) if f[0] >= args.loop)
    blob = bytearray()
    loop_offset = 0
    prev = picked[0][1]
    for i, (_, ts, raw) in enumerate(picked):
        if i == loop_index:
            loop_offset = len(blob)
            prev = ts - 200  # Nahtstelle der Schleife: Abstand kommt aus dem letzten Rahmen
        delta = min((ts - prev) // 100, 0xFFFF)
        prev = ts
        head = split_frame(raw)[0]
        blob += struct.pack("<HB", delta, len(head)) + head

    lines = [
        "// Erzeugt von tools/vebus_make_replay.py, nicht von Hand aendern.",
        f"// Quelle {Path(args.log).name}, {args.start} bis {args.end}, Schleife ab {args.loop}.",
        "#pragma once",
        "#include <cstddef>",
        "#include <cstdint>",
        "namespace vebus_dmc_replay {",
        f"static constexpr size_t LOOP_OFFSET = {loop_offset};",
        f"static constexpr size_t SIZE = {len(blob)};",
        "static const uint8_t DATA[SIZE] = {",
    ]
    for i in range(0, len(blob), 24):
        lines.append(",".join(f"0x{b:02x}" for b in blob[i : i + 24]) + ",")
    lines += ["};", "}  // namespace vebus_dmc_replay", ""]
    Path(args.out).write_text("\n".join(lines), encoding="ascii", newline="\n")
    print(f"{len(picked)} Rahmen, {len(blob)} Bytes, Schleife ab Byte {loop_offset} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
