#!/usr/bin/env python3
"""Auswertung von ESPHome-Observer-Logs (truma_inetbox, Branch alde) fuer Track B.

Liest ein ESPHome-Log (USB oder Web-Konsole, ANSI-Farben egal) und extrahiert alle
Zeilen der Form

    [18:22:48][D][truma_inetbox.LinBusProtocol:226]: Multi package request BB.00.1F.00.08....FF (19)
    [18:22:48][D][truma_inetbox.LinBusProtocol:232]: Multi package response FA.00.1F.00.1A....9F (17)

ACHTUNG Observer-Modus: "Multi package response" ist dort die Antwort, die die
Komponente SELBST gesendet haette (ihr Init 0x0A), nicht die der echten iNet Box.
Enthaelt das Log VERBOSE-Rohframes

    [14:58:06][V][truma_inetbox.LinBusListener:405]: PID 3C      03.10.0B.BA.00.1F.00.1A.ED (9)  - MASTER
    [14:58:06][V][truma_inetbox.LinBusListener:405]: PID 3D      03.10.25.FA.00.1F.00.1A.93 (9)  - SLAVE

setzt das Skript die Transportschicht (LIN-TP: PCI 0x1X First Frame mit Laenge,
0x2X Consecutive Frames) fuer NAD 0x03 selbst zusammen und ignoriert die
"Multi package"-Zeilen (--source auto|raw|multi).

Jede Nachricht wird in SID / Praeambel (Header-Byte 4 = L) / MSG-Head ('T' 01 len type
counter chk) / Payload zerlegt, die Pruefsumme nachgerechnet, bekannte Typen dekodiert
(0x0A Init, 0x0B/0x0C Geraeteliste, 0x0D ACK, 0x15 Uhr, 0x33/0x32 Truma-Heizung,
0x51/0x50 Alde-Status, 0x53 Alde-Addon, 0x55/0x57 Nacht-/Tagmodus).

Verknuepfungen:
  * BA (READ) -> naechste FA (Antwort der Box)
  * FA (Box -> Panel) -> naechstes BB 0x0D mit gleichem Counter  => "ACK"
  * gleicher Typ+Richtung -> Byte-Diff zum vorherigen Vorkommen

Zeilen im Log, die keine ESPHome-Logzeilen sind (z. B. selbst eingetippte Notizen wie
"Temperatur auf 18 Grad geaendert"), werden als Aktions-Marker uebernommen.

Aufruf:
    python tools/parse_observer_log.py LOGDATEI [--csv out.csv] [--only-tp] [--no-diff]

Nur Standardbibliothek. Getestet gegen examples/alde.txt und alde2.txt aus
Fabian-Schmidt/esphome-truma_inetbox@alde.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
TS_RE = re.compile(r"^\[(\d\d:\d\d:\d\d)(?:\.\d+)?\]")
MSG_RE = re.compile(
    r"Multi package (request|response)\s*((?:[0-9A-Fa-f]{2}\.)+[0-9A-Fa-f]{2})\s*\((\d+)\)"
)
LOGLINE_RE = re.compile(r"^\[\d\d:\d\d:\d\d\]\[[A-Z]\]|^\[[A-Z]\]\[")
RAW_RE = re.compile(r"PID (3C|3D)\s+((?:[0-9A-Fa-f]{2}\.)+[0-9A-Fa-f]{2})\s*\((\d+)\)")
BOX_NAD = 0x03

SID_NAMES = {
    0xBA: "READ  (Panel->Box: bitte senden)",
    0xBB: "DOWNLOAD (Panel->Box)",
    0xFA: "UPLOAD (Box->Panel)",
}

TYPE_NAMES = {
    0x0A: "INIT (Box)",
    0x0B: "DEVICES (Truma)",
    0x0C: "DEVICES (Alde)",
    0x0D: "ACK",
    0x15: "CLOCK",
    0x14: "CLOCK-SET (Box)",
    0x32: "HEATER-CMD (Truma, Box)",
    0x33: "HEATER-STATUS (Truma)",
    0x34: "AIRCON-MANUAL-CMD (Box)",
    0x35: "AIRCON-MANUAL-STATUS",
    0x36: "AIRCON-AUTO-CMD (Box)",
    0x37: "AIRCON-AUTO-STATUS",
    0x3C: "TIMER-CMD (Box)",
    0x3D: "TIMER-STATUS",
    0x50: "ALDE-STATUS-CMD (Box)",  # bestaetigt 27.10.2026 (echte iNet Box, Alde 3020 HE)
    0x51: "ALDE-STATUS",
    0x52: "ALDE-ADDON-CMD (Box) [Hypothese]",
    0x53: "ALDE-ADDON",
    0x54: "ALDE-NIGHT-CMD (Box)",  # bestaetigt 27.10.2026 (App: Nachtmodus)
    0x55: "ALDE-NIGHT",
    0x56: "ALDE-DAY-CMD (Box) [Hypothese]",
    0x57: "ALDE-DAY",
}

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So", "taeglich"]


def data_checksum(data: bytes, start: int = 0) -> int:
    """Fabian-Schmidt helpers.cpp: Summe mit Ueberlauf-Korrektur (-255), Komplement."""
    s = start
    for b in data:
        s += b
        if s >= 256:
            s -= 255
    return (~s) & 0xFF


def temp(v: int) -> str:
    if v in (0, 0xFFFF, 0xFFFE, 0x7FFF):
        return f"-- (0x{v:04X})"
    return f"{v / 10.0 - 273.0:.1f}°C"


def u16(p: bytes, o: int) -> int:
    return p[o] | (p[o + 1] << 8)


def hexs(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


@dataclass
class Msg:
    idx: int
    line_no: int
    time: str
    direction: str  # request / response
    sid: int
    raw: bytes
    declared_len: int
    hdr_l: Optional[int] = None
    msg_len: Optional[int] = None
    msg_type: Optional[int] = None
    counter: Optional[int] = None
    chk: Optional[int] = None
    chk_ok: Optional[bool] = None
    payload: bytes = b""
    note: str = ""
    decoded: str = ""
    diff: str = ""
    ack_ref: str = ""
    marker: str = ""  # letzter Aktions-Marker vor dieser Nachricht

    @property
    def dir_short(self) -> str:
        return "Box->Panel" if self.sid == 0xFA else "Panel->Box"


def parse_message(idx: int, line_no: int, time: str, direction: str, hexstr: str, declared: int) -> Msg:
    raw = bytes(int(x, 16) for x in hexstr.split("."))
    m = Msg(idx, line_no, time, direction, raw[0], raw, declared)
    if len(raw) != declared:
        m.note += f"Laenge {len(raw)} != deklariert {declared}; "
    if len(raw) >= 11:
        m.hdr_l = raw[4]
        pre_ok = raw[1:4] == b"\x00\x1F\x00" and raw[5:8] == b"\x00\x00\x22"
        if not pre_ok:
            m.note += "Praeambel abweichend; "
    if len(raw) >= 17 and raw[11] == 0x54 and raw[12] == 0x01:
        m.msg_len = raw[13]
        m.msg_type = raw[14]
        m.counter = raw[15]
        m.chk = raw[16]
        m.payload = raw[17 : 17 + m.msg_len]
        if len(m.payload) < m.msg_len:
            m.note += f"Payload kuerzer ({len(m.payload)}) als len {m.msg_len}; "
        # Pruefsumme: ab Byte 10 (= das 0xFF vor 'T') ueber den Rest, chk-Byte als 0
        body = bytearray(raw[10:])
        body[6] = 0
        m.chk_ok = data_checksum(bytes(body)) == m.chk
        if m.hdr_l is not None and m.msg_len is not None and m.sid != 0xBA:
            # Panel->Box: L = len+6. Box->Panel: konstant 0x1A (Alde, gemessen) bzw. 0x1E (Truma).
            if m.sid == 0xFA:
                if m.hdr_l not in (0x1A, 0x1E):
                    m.note += f"L=0x{m.hdr_l:02X} (Box) weder 0x1A noch 0x1E; "
            elif m.hdr_l != m.msg_len + 6:
                m.note += f"L=0x{m.hdr_l:02X} != len+6=0x{m.msg_len + 6:02X}; "
    elif len(raw) == 11 and m.sid == 0xBA:
        pass  # reine READ-Anfrage
    else:
        m.note += "kein MSG-Head; "
    m.decoded = decode(m)
    return m


def decode(m: Msg) -> str:
    t, p = m.msg_type, m.payload
    if t is None:
        return "READ-Anfrage" if m.sid == 0xBA else ""
    try:
        if t == 0x0A:
            return "Init (leer)"
        if t == 0x0D:
            return f"ACK fuer Counter 0x{m.counter:02X}  payload={hexs(p)}"
        if t in (0x0B, 0x0C) and len(p) >= 12:
            sup = u16(p, 4) if t == 0x0C else None
            fn = u16(p, 6) if t == 0x0C else None
            hw = f"{u16(p, 4):04X}.{p[6]:02X}" if t == 0x0B else f"supplier 0x{sup:04X} fn 0x{fn:04X}"
            sw = ".".join(str(x) for x in p[7:10]) if t == 0x0B else ".".join(str(x) for x in p[8:11])
            return f"Geraet {p[1] + 1}/{p[0]} state=0x{p[2]:02X} {hw} sw={sw} rest={hexs(p[11:] if t == 0x0C else p[10:])}"
        if t == 0x15 and len(p) >= 7:
            return f"Uhr {p[0]:02d}:{p[1]:02d}:{p[2]:02d} disp={hexs(p[3:6])} mode=0x{p[6]:02X} rest={hexs(p[7:])}"
        if t in (0x51, 0x50) and len(p) >= 16:
            water = {0: "aus", 100: "normal", 200: "boost"}.get(p[6], f"0x{p[6]:02X}")
            gas = {0x00: "aus", 0x37: "ein"}.get(p[8], f"0x{p[8]:02X}")
            prio = {0: "Elektro", 1: "Gas"}.get(p[9], f"0x{p[9]:02X}")
            s = (
                f"Heizung={'EIN' if p[0] == 1 else 'AUS' if p[0] == 0 else hex(p[0])} b1=0x{p[1]:02X} "
                f"Soll={temp(u16(p, 2))} u4..5={hexs(p[4:6])} WW={water} El={p[7] // 10 if p[7] % 10 == 0 else p[7]}kW "
                f"Gas={gas} Prio={prio} u10..14={hexs(p[10:15])} ctr={p[15]:02X}"
            )
            if len(p) >= 28:
                s += f" | Innen={temp(u16(p, 16))} Aussen={temp(u16(p, 20))} rest={hexs(p[22:28])}"
            return s
        if t in (0x55, 0x57, 0x54, 0x56) and len(p) >= 12:
            st, en = u16(p, 2), u16(p, 4)
            wd = lambda x: WEEKDAYS[x] if x < len(WEEKDAYS) else f"0x{x:02X}"
            return (
                f"Soll={temp(u16(p, 0))} Start={st // 60:02d}:{st % 60:02d} Ende={en // 60:02d}:{en % 60:02d} "
                f"Tage={wd(p[6])}-{wd(p[7])} bits=0x{p[8]:02X} u9=0x{p[9]:02X} u10=0x{p[10]:02X} ctr={p[11]:02X}"
            )
        if t in (0x53, 0x52) and len(p) >= 20:
            sensor = {0: "Auto", 2: "Bett", 3: "Panel"}.get(p[15], f"0x{p[15]:02X}")
            return f"Sensor={sensor} ctr={p[19]:02X} u0..14={hexs(p[0:15])} u20..={hexs(p[20:])}"
        if t in (0x33, 0x32) and len(p) >= 12:
            return (
                f"Truma: Soll-Raum={temp(u16(p, 0))} Soll-Wasser={temp(u16(p, 2))} "
                f"mix={hexs(p[4:7])} el={u16(p, 7) if len(p) > 8 else '?'} rest={hexs(p[9:])}"
            )
    except (IndexError, ValueError) as e:  # defensiv: nie am Dekodieren scheitern
        return f"(decode error: {e})"
    return ""


def diff_bytes(prev: bytes, cur: bytes) -> str:
    if len(prev) != len(cur):
        return f"Laenge {len(prev)}->{len(cur)}"
    out = []
    for i, (a, b) in enumerate(zip(prev, cur)):
        if a != b:
            out.append(f"@{i}:{a:02X}->{b:02X}")
    return " ".join(out) if out else "="


class TpAssembler:
    """Setzt LIN-Transportschicht-Frames (PID 0x3C Master / 0x3D Slave) fuer NAD 0x03 zusammen.

    Nur Nachrichten, die mit einem First Frame (PCI 0x1X) beginnen, werden erzeugt; Single
    Frames (Heartbeat B9/F9, Identifikation B2/F2, ACK FB) sind keine Multi-package-Nachrichten.
    """

    def __init__(self, direction: str) -> None:
        self.direction = direction
        self.buf: Optional[bytearray] = None
        self.length = 0
        self.next_sn = 0
        self.start: tuple[int, str] = (0, "")
        self.note = ""

    def feed(self, ln: int, ts: str, data: bytes) -> Optional[tuple[int, str, bytes, int, str]]:
        """Gibt (zeile, zeit, bytes, deklarierte_laenge, note) zurueck, wenn eine Nachricht komplett ist."""
        if len(data) < 8 or data[0] != BOX_NAD:
            return None
        pci = data[1]
        kind = pci >> 4
        if kind == 1:  # First Frame: Laenge in Byte 2 (Low-Byte; High-Nibble von PCI = 0 hier)
            lost = ""
            if self.buf is not None:
                lost = f"vorherige unvollstaendige Nachricht verworfen ({len(self.buf)}/{self.length} Byte); "
            self.length = ((pci & 0x0F) << 8) | data[2]
            self.buf = bytearray(data[3:8])
            self.next_sn = 1
            self.start = (ln, ts)
            self.note = lost
        elif kind == 2 and self.buf is not None:
            if (pci & 0x0F) != (self.next_sn & 0x0F):
                self.note += f"Sequenz {pci & 0x0F} statt {self.next_sn & 0x0F}; "
            self.next_sn += 1
            self.buf += data[2:8]
        else:
            return None
        if len(self.buf) >= self.length:
            out = (self.start[0], self.start[1], bytes(self.buf[: self.length]), self.length, self.note)
            self.buf = None
            return out
        return None


def parse_log(path: str, source: str = "auto") -> tuple[list[Msg], list[tuple[int, str]], str]:
    multi: list[Msg] = []
    raw: list[Msg] = []
    markers: list[tuple[int, str]] = []
    last_marker = ""
    asm = {"3C": TpAssembler("request"), "3D": TpAssembler("response")}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln, line in enumerate(fh, 1):
            line = ANSI_RE.sub("", line).rstrip("\r\n")
            if not line.strip():
                continue
            ts = TS_RE.match(line)
            mm = MSG_RE.search(line)
            if mm:
                m = parse_message(len(multi), ln, ts.group(1) if ts else "", mm.group(1), mm.group(2), int(mm.group(3)))
                m.marker = last_marker
                multi.append(m)
                continue
            rm = RAW_RE.search(line)
            if rm:
                data = bytes(int(x, 16) for x in rm.group(2).split("."))
                done = asm[rm.group(1).upper()].feed(ln, ts.group(1) if ts else "", data)
                if done:
                    dln, dts, b, declared, note = done
                    m = parse_message(len(raw), dln, dts, asm[rm.group(1).upper()].direction, ".".join(f"{x:02X}" for x in b), declared)
                    m.note = note + m.note
                    m.marker = last_marker
                    raw.append(m)
                continue
            if not LOGLINE_RE.match(line) and not line.startswith("[") and re.search(r"[A-Za-z]", line):
                # freie Notiz im Log = Aktions-Marker
                last_marker = line.strip()
                markers.append((ln, last_marker))
    use_raw = source == "raw" or (source == "auto" and any(m.sid == 0xFA for m in raw))
    if use_raw:
        return raw, markers, "raw (LIN-TP aus PID-3C/3D-Frames zusammengesetzt)"
    return multi, markers, "multi (Multi-package-Zeilen der Komponente)"


def link_messages(msgs: list[Msg]) -> None:
    """READ->Antwort, Box-Nachricht->ACK und Diffs zum vorherigen gleichen Typ."""
    last_by_key: dict[tuple[int, Optional[int]], Msg] = {}
    for i, m in enumerate(msgs):
        key = (m.sid, m.msg_type)
        if m.msg_type is not None:
            prev = last_by_key.get(key)
            if prev is not None:
                m.diff = diff_bytes(prev.payload, m.payload)
            last_by_key[key] = m
        if m.sid == 0xBA:
            for n in msgs[i + 1 : i + 6]:
                if n.sid == 0xFA:
                    m.ack_ref = f"-> Antwort #{n.idx}"
                    break
            else:
                m.ack_ref = "-> KEINE Antwort der Box"
        if m.sid == 0xFA and m.counter is not None:
            for n in msgs[i + 1 : i + 12]:
                if n.sid == 0xBB and n.msg_type == 0x0D:
                    if n.counter == m.counter:
                        m.ack_ref = f"ACK #{n.idx} (ctr 0x{n.counter:02X}) OK (gleicher Counter, Truma-Muster)"
                    elif n.counter == ((m.counter - 1) & 0xFF):
                        # In Fabians Alde-Mitschnitten quittiert das Panel immer mit ctr-1.
                        m.ack_ref = f"ACK #{n.idx} (ctr 0x{n.counter:02X}) OK (Counter-1, Alde-Muster)"
                    else:
                        m.ack_ref = f"ACK #{n.idx} mit FREMDEM ctr 0x{n.counter:02X} (erwartet 0x{m.counter:02X})"
                    break
            else:
                m.ack_ref = "KEIN 0x0D-ACK innerhalb der naechsten 11 Nachrichten"


def print_report(msgs: list[Msg], markers: list[tuple[int, str]], only_tp: bool, show_diff: bool, source: str = "") -> None:
    print(f"{len(msgs)} Multi-package-Nachrichten, {len(markers)} Marker, Quelle: {source}\n")
    cur_marker = None
    for m in msgs:
        if m.marker != cur_marker:
            cur_marker = m.marker
            if cur_marker:
                print(f"\n=== {cur_marker} ===")
        if only_tp and m.sid != 0xFA and not (m.sid == 0xBB and m.msg_type == 0x0D) and m.sid != 0xBA:
            continue
        sid = SID_NAMES.get(m.sid, f"SID 0x{m.sid:02X}")
        head = f"#{m.idx:04d} {m.time or '--:--:--'} [{m.dir_short}] {sid}"
        if m.msg_type is not None:
            tn = TYPE_NAMES.get(m.msg_type, "?")
            chk = "chk OK" if m.chk_ok else "CHK FEHLER"
            head += f" | L=0x{m.hdr_l:02X} type=0x{m.msg_type:02X} ({tn}) len={m.msg_len} ctr=0x{m.counter:02X} {chk}"
        else:
            head += f" | L=0x{m.hdr_l:02X}" if m.hdr_l is not None else ""
        print(head)
        if m.payload:
            print(f"      payload: {hexs(m.payload)}")
        if m.decoded:
            print(f"      {m.decoded}")
        if show_diff and m.diff and m.diff != "=":
            print(f"      diff zu vorherigem gleichen Typ: {m.diff}")
        if m.ack_ref:
            print(f"      {m.ack_ref}")
        if m.note:
            print(f"      ! {m.note.strip()}")

    # Zusammenfassung
    print("\n=== Zusammenfassung ===")
    combos: dict[tuple[int, Optional[int], Optional[int], Optional[int]], int] = {}
    for m in msgs:
        combos[(m.sid, m.msg_type, m.msg_len, m.hdr_l)] = combos.get((m.sid, m.msg_type, m.msg_len, m.hdr_l), 0) + 1
    print("SID    type  len   L     Anzahl  Bedeutung")
    for (sid, t, ln, L), n in sorted(combos.items(), key=lambda kv: (kv[0][0], kv[0][1] or 0)):
        ts = f"0x{t:02X}" if t is not None else "--  "
        print(f"0x{sid:02X}   {ts}  {str(ln) if ln is not None else '--':>3}   {('0x%02X' % L) if L is not None else '--  '}  {n:6d}  {TYPE_NAMES.get(t, '') if t is not None else 'READ'}")
    box = [m for m in msgs if m.sid == 0xFA]
    print(f"\nBox->Panel-Nachrichten: {len(box)}")
    for m in box:
        if m.msg_type != 0x0A:
            print(f"  #{m.idx:04d} {m.time} type=0x{m.msg_type:02X} len={m.msg_len} L=0x{m.hdr_l:02X} {m.ack_ref}  <-- BEFEHLSKANDIDAT")
    bad = [m for m in msgs if m.chk_ok is False]
    if bad:
        print(f"\nPruefsummenfehler: {len(bad)} (#{', #'.join(str(m.idx) for m in bad[:20])})")


def write_csv(msgs: list[Msg], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["idx", "zeile", "zeit", "marker", "richtung", "sid", "L", "type", "typename", "len", "counter", "chk_ok", "payload", "decoded", "diff", "ack", "note"])
        for m in msgs:
            w.writerow([
                m.idx, m.line_no, m.time, m.marker, m.dir_short, f"0x{m.sid:02X}",
                f"0x{m.hdr_l:02X}" if m.hdr_l is not None else "",
                f"0x{m.msg_type:02X}" if m.msg_type is not None else "",
                TYPE_NAMES.get(m.msg_type, "") if m.msg_type is not None else "READ",
                m.msg_len if m.msg_len is not None else "",
                f"0x{m.counter:02X}" if m.counter is not None else "",
                "" if m.chk_ok is None else ("ja" if m.chk_ok else "NEIN"),
                hexs(m.payload), m.decoded, m.diff, m.ack_ref, m.note.strip(),
            ])


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("logfile")
    ap.add_argument("--csv", help="Tabelle zusaetzlich als CSV (Semikolon) schreiben")
    ap.add_argument("--only-tp", action="store_true", help="nur READ / Box-Nachrichten / ACKs anzeigen")
    ap.add_argument("--no-diff", action="store_true", help="Byte-Diffs unterdruecken")
    ap.add_argument("--source", choices=["auto", "raw", "multi"], default="auto",
                    help="raw: aus PID-3C/3D-Rohframes zusammensetzen (echte Box-Antworten); multi: Multi-package-Zeilen; auto: raw wenn vorhanden")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    msgs, markers, source = parse_log(a.logfile, a.source)
    if not msgs:
        print("Keine 'Multi package'-Zeilen oder PID-3C/3D-Frames gefunden. Ist es ein Log der truma_inetbox-Komponente (Level DEBUG/VERBOSE)?")
        return 1
    link_messages(msgs)
    print_report(msgs, markers, a.only_tp, not a.no_diff, source)
    if a.csv:
        write_csv(msgs, a.csv)
        print(f"\nCSV geschrieben: {a.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
