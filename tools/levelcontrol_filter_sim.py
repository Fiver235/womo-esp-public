#!/usr/bin/env python3
"""Plausibilitaetsfilter (ha/custom_components/truma_levelcontrol/smoothing.py) gegen die echte
Home-Assistant-Historie beider LevelControl laufen lassen.

Datenbasis: Zustandswechsel von sensor.gasflasche_{links,rechts}_{fullstand,messqualitat} aus dem
HA-Recorder, 27.10.-31.10.2026 und rechts 2.-3.11.2026 (fast leere Flasche mit Fehlmessungen).
HA speichert nur Aenderungen; die Integration misst alle ~10 min. Die Simulation legt daher ein
Raster von 10:08 min ueber die Stufenfunktion (gleicher Wert bis zur naechsten Aenderung),
"unavailable" unterbricht die Reihe.

    python tools/levelcontrol_filter_sim.py [--sensor links|rechts|leer] [--all] [--check]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ha" / "custom_components" / "truma_levelcontrol"))
from smoothing import FilterState, LevelFilter  # noqa: E402

CAPACITY_G = 11000  # beide Flaschen 11 kg Stahl

# "MMDD HH:MM[:SS] wert"  (wert: Zahl oder u = unavailable)
RECHTS_FUELL = """
1027 19:25 u
1027 19:58 0
1027 22:34 89
1027 22:44 95
1027 22:54 97
1027 23:05 98
1027 23:25 99
1028 00:16 100
1028 00:25:25 0
1028 00:25:52 98
1028 00:36 100
1028 07:38 4
1028 10:20 u
1028 13:25 100
1028 13:45 0
1028 13:55 13
1028 14:05 0
1028 14:15 13
1028 14:25 14
1028 14:36 0
1028 14:46 13
1028 15:06 0
1028 15:16 99
1028 15:26 12
1028 15:36 0
1028 15:47 12
1028 15:57 0
1028 16:07 13
1028 16:11 14
1028 16:25 100
1029 09:25 99
1029 09:36 98
1029 14:20 97
1029 16:01 98
1029 16:21 97
1029 16:41 96
1029 17:02 95
1029 17:22 96
1029 17:42 95
1029 18:13 94
1029 19:14 95
1029 19:24 94
1029 19:34 93
1029 19:44 94
1029 20:25 93
1029 21:25 92
1029 23:57 91
1030 00:08 92
1030 00:28 91
1030 00:38 90
1030 01:49 89
1030 02:19 88
1030 03:41 87
1030 04:31 86
1030 05:52 85
1030 06:23 86
1030 07:04 85
1030 07:14 86
1030 07:24 85
1030 07:34 84
1030 08:55 83
1030 11:17 82
1030 12:18 83
1030 12:38 82
1030 12:58 81
1030 13:19 82
1030 13:29 81
1030 15:00 80
1030 15:10 81
1030 15:51 80
1030 16:11 79
1030 16:42 78
1030 16:52 80
1030 17:02 79
1030 17:42 78
1030 18:13 79
1030 18:23 78
1030 18:53 77
1030 19:24 76
1030 20:15 75
1030 20:25 76
1030 20:35 75
1030 20:45 76
1030 20:55 75
1030 21:05 76
1030 21:15 75
1030 21:25 76
1030 21:36 75
1030 21:46 76
1030 22:57 75
1030 23:37 74
1031 00:08 73
1031 00:18 74
1031 01:39 73
1031 02:30 72
1031 03:51 71
1031 04:52 70
1031 05:02 71
1031 05:12 70
1031 06:23 69
1031 07:44 68
1031 07:55 69
1031 08:05 68
1031 08:15 69
1031 08:25 67
"""

RECHTS_QUAL = """
1027 19:25 u
1027 19:58 0
1027 22:34 3
1028 00:25:25 0
1028 00:25:52 3
1028 07:38 0
1028 10:20 u
1028 13:25 3
1028 13:45 0
1028 13:55 3
1028 14:05 0
1028 14:15 3
1028 14:36 0
1028 14:46 3
1028 15:06 0
1028 15:16 3
1028 15:36 0
1028 15:47 3
1028 15:57 0
1028 16:07 3
"""

LINKS_FUELL = """
1027 19:24 0
1027 19:54 44
1027 19:55 0
1027 22:12 44
1027 22:22 0
1027 22:27 90
1027 22:37 0
1028 00:25 93
1028 00:35 97
1028 00:45 93
1028 07:38 100
1028 07:58 98
1028 10:20 u
1028 13:20 13
1028 13:41 0
1028 14:11 15
1028 14:21 0
1028 14:31 13
1028 14:42 0
1028 15:02 13
1028 15:22 12
1028 15:32 15
1028 15:43 12
1028 16:03 13
1028 16:11 12
1028 16:17 0
1028 16:27 12
1028 16:37 13
1028 16:58 11
1028 17:08 12
1028 17:18 11
1028 18:29 10
1028 19:30 9
1028 19:50 10
1028 20:10 9
1028 20:30 11
1028 20:41 9
1028 20:51 8
1028 21:01 9
1028 21:11 8
1028 21:41 7
1028 22:15:33 8
1028 22:15:54 7
1028 22:26 8
1028 22:36 7
1028 22:46 8
1028 22:56 7
1028 23:47 6
1028 23:57 7
1029 00:07 15
1029 00:17 0
1029 00:37 6
1029 00:58 0
1030 13:49 51
1030 13:59 47
1030 14:09 46
1030 14:39 97
1030 14:49 100
1031 08:14 0
"""

LINKS_QUAL = """
1027 19:24 0
1027 19:54 3
1027 19:55 0
1027 22:12 3
1027 22:22 0
1027 22:27 3
1027 22:37 0
1028 00:25 3
1028 10:20 u
1028 13:20 3
1028 13:41 0
1028 14:11 3
1028 14:21 0
1028 14:31 3
1028 14:42 0
1028 15:02 3
1028 16:17 0
1028 16:27 3
1028 20:51 0
1028 21:01 3
1028 21:31 0
1029 00:07 3
1029 00:17 0
1030 13:49 3
1031 08:14 0
"""

# Rechte Flasche fast leer, nicht getauscht: Fehlmessungen mit Qualitaet 3 (Ausloeser fuer den Umbau)
LEER_FUELL = """
1102 23:00 13
1102 23:00:46 12
1102 23:21 11
1103 01:43 10
1103 01:53 11
1103 02:03 10
1103 06:37 9
1103 07:48 8
1103 08:08 7
1103 08:18 8
1103 08:38 7
1103 08:48 8
1103 09:19 7
1103 09:29 9
1103 09:39 7
1103 09:59 40
1103 10:09 41
1103 10:19 8
1103 10:30 7
1103 10:40 40
1103 10:50 7
1103 11:10 40
1103 11:20 8
1103 11:30 9
1103 11:40 7
1103 11:51 8
1103 12:01 9
1103 12:11 7
1103 12:21 6
1103 12:31 7
1103 12:41 11
1103 12:51 7
1103 13:02 8
1103 13:12 6
1103 13:42 35
1103 13:52 34
1103 14:02 35
1103 14:13 7
1103 14:23 35
1103 14:33 7
1103 14:43 9
1103 14:53 6
1103 15:24 34
1103 15:34 7
1103 15:44 33
1103 15:54 6
1103 16:04 22
1103 16:14 7
1103 16:45 6
1103 17:05 7
1103 17:26 8
1103 17:36 62
1103 17:46 6
1103 17:56 30
1103 18:06 6
1103 19:27 0
1103 19:37 49
1103 19:47 51
1103 19:58 52
1103 20:08 6
1103 20:28 0
1103 20:38 46
1103 20:48 0
"""

LEER_QUAL = """
1102 23:00 3
1103 08:08 0
1103 09:29 3
1103 09:39 0
1103 09:59 3
1103 10:19 0
1103 10:40 3
1103 10:50 0
1103 11:10 3
1103 11:20 0
1103 11:30 3
1103 11:40 0
1103 11:51 3
1103 12:11 0
1103 12:41 3
1103 12:51 0
1103 13:42 3
1103 14:13 0
1103 14:23 3
1103 14:33 0
1103 14:43 3
1103 14:53 0
1103 15:24 3
1103 15:34 0
1103 15:44 3
1103 15:54 0
1103 16:04 3
1103 16:14 0
1103 17:36 3
1103 17:46 0
1103 17:56 3
1103 18:06 0
1103 19:37 3
1103 20:08 0
1103 20:38 3
1103 20:48 0
"""

END = datetime(2026, 10, 31, 8, 35)
LEER_END = datetime(2026, 11, 3, 20, 50)
STEP = timedelta(seconds=608)


def parse(block: str) -> list[tuple[datetime, int | None]]:
    out = []
    for line in block.strip().splitlines():
        d, t, v = line.split()
        parts = [int(x) for x in t.split(":")]
        ts = datetime(2026, int(d[:2]), int(d[2:]), parts[0], parts[1], parts[2] if len(parts) > 2 else 0)
        out.append((ts, None if v == "u" else int(v)))
    return out


def value_at(series: list[tuple[datetime, int | None]], ts: datetime) -> int | None:
    cur = None
    for t, v in series:
        if t <= ts:
            cur = v
        else:
            break
    return cur


def resample(fuell: str, qual: str, end: datetime = END) -> list[tuple[datetime, int, int]]:
    fs, qs = parse(fuell), parse(qual)
    ts = fs[0][0]
    out = []
    while ts <= end:
        f, q = value_at(fs, ts), value_at(qs, ts)
        if f is not None and q is not None:
            out.append((ts, f, q))
        ts += STEP
    return out


def run(name: str, fuell: str, qual: str, show_all: bool, end: datetime = END) -> LevelFilter:
    samples = resample(fuell, qual, end)
    flt = LevelFilter()
    print(f"\n=== {name}: {len(samples)} Messungen ===")
    print(f"{'Zeit':17s} {'roh':>4s} {'Q':>2s} {'Anzeige':>8s}  Status")
    last_line = None
    rejected = 0
    for ts, pct, q in samples:
        disp = flt.update(pct, int(CAPACITY_G * pct / 100), q, ts.timestamp())
        st = flt.state.status
        if st.startswith("unplausibel"):
            rejected += 1
        line = (disp, st)
        if show_all or line != last_line:
            print(f"{ts:%d.%m %H:%M}     {pct:4d} {q:2d} {str(disp):>8s}  {st}")
        last_line = line
    print(f"-> {rejected} von {len(samples)} Messungen als unplausibel gehalten; "
          f"Endanzeige {flt.display_percent} % / {flt.display_kg} kg, Rohwert zuletzt {samples[-1][1]} %")
    return flt


def feed(flt: LevelFilter, values, start: float, step: float = 608.0, driving: bool = False) -> float:
    t = start
    for pct, q in values:
        flt.update(pct, int(CAPACITY_G * pct / 100), q, t, driving=driving)
        t += step
    return t


def check() -> int:
    """Erwartetes Verhalten pruefen. Rueckgabe: Anzahl Fehler."""
    errors = 0

    def expect(name: str, ok: bool, detail: object = "") -> None:
        nonlocal errors
        print(f"{'OK    ' if ok else 'FEHLER'} {name} {detail}")
        errors += 0 if ok else 1

    # 3.11.: fast leere Flasche, Anzeige darf nie auf die Fehlmessungen springen.
    flt = LevelFilter()
    shown = []
    for ts, pct, q in resample(LEER_FUELL, LEER_QUAL, LEER_END):
        d = flt.update(pct, int(CAPACITY_G * pct / 100), q, ts.timestamp())
        if ts >= datetime(2026, 11, 3, 9, 0) and d is not None:
            shown.append(d)
    expect("3.11.: Anzeige bleibt zwischen 5 und 10 %", min(shown) >= 5 and max(shown) <= 10,
           f"min {min(shown)} max {max(shown)}")

    # Echter Flaschenwechsel: wird uebernommen, aber nicht vor 90 Minuten.
    flt = LevelFilter()
    t = feed(flt, [(8, 3)] * 8, 0.0)
    t0 = t
    steps = 0
    while flt.display_percent != 100 and steps < 30:
        t = feed(flt, [(100, 3)], t)
        steps += 1
    took = (t - t0) / 60
    expect("Flaschenwechsel 8 -> 100 % nach 90 bis 130 min",
           flt.display_percent == 100 and 90 <= took <= 130, f"{took:.0f} min")

    # Drei passende Fehlmessungen in Folge duerfen nichts aendern.
    flt = LevelFilter()
    t = feed(flt, [(7, 0)] * 8, 0.0)
    t = feed(flt, [(35, 3), (34, 3), (35, 3)], t)
    expect("3 Fehlmessungen in Folge aendern nichts", flt.display_percent == 7, flt.display_percent)

    # Falscher Pegel korrigiert sich selbst nach unten.
    flt = LevelFilter()
    t = feed(flt, [(52, 3)] * 5, 0.0)
    t = feed(flt, [(6, 0)] * 14, t)
    expect("falscher Pegel 52 % korrigiert sich",
           flt.display_percent is not None and flt.display_percent <= 8, flt.display_percent)

    # Fahrt: Messungen zaehlen nicht, auch nicht fuer einen neuen Pegel.
    flt = LevelFilter()
    t = feed(flt, [(80, 3)] * 6, 0.0)
    t = feed(flt, [(12, 3)] * 15, t, driving=True)
    expect("Fahrt haelt den Wert", flt.display_percent == 80 and len(flt.state.votes) <= 6,
           flt.display_percent)

    # Volle Flasche bleibt bei kurzem Echoausfall stehen.
    flt = LevelFilter()
    t = feed(flt, [(100, 3)] * 6, 0.0)
    t = feed(flt, [(0, 0)] * 6, t)
    expect("1 h kein Echo aendert die volle Flasche nicht", flt.display_percent == 100,
           flt.display_percent)

    # Gesicherter Zustand: gleiche Fassung voll, alte Fassung nur Anzeige.
    flt = LevelFilter()
    feed(flt, [(40, 3)] * 6, 0.0)
    again = LevelFilter(FilterState.from_dict(flt.state.as_dict()))
    expect("Neustart behaelt Pegel und Messungen",
           again.state.accepted == 40 and len(again.state.votes) == len(flt.state.votes))
    old = {"accepted": 46.0, "accepted_at": 1.0, "smoothed": 50.8, "display": 51,
           "capacity_g": 11100, "recent": [46.0]}
    legacy = LevelFilter(FilterState.from_dict(old))
    expect("alter Zustand behaelt nur die Anzeige",
           legacy.state.accepted is None and legacy.display_percent == 51)
    feed(legacy, [(0, 0), (6, 0), (46, 3), (6, 0), (6, 0)], 0.0)
    expect("danach Median als Startwert", legacy.display_percent == 6, legacy.display_percent)
    return errors


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sensor", choices=["links", "rechts", "leer"])
    ap.add_argument("--all", action="store_true", help="jede Messung ausgeben, nicht nur Aenderungen")
    ap.add_argument("--check", action="store_true", help="erwartetes Verhalten pruefen")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    if a.check:
        return 1 if check() else 0
    if a.sensor in (None, "rechts"):
        run("rechts 27.-31.10.", RECHTS_FUELL, RECHTS_QUAL, a.all)
    if a.sensor in (None, "links"):
        run("links 27.-31.10.", LINKS_FUELL, LINKS_QUAL, a.all)
    if a.sensor in (None, "leer"):
        run("rechts 2.-3.11. fast leer", LEER_FUELL, LEER_QUAL, a.all, LEER_END)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
