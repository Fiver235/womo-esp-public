#!/usr/bin/env python3
"""Entitaeten eines ESPHome-Knotens per nativer API steuern (ohne Home Assistant).

Nutzt aioesphomeapi (kommt mit ESPHome). Verschluesselung: api_encryption_key aus esphome/secrets.yaml.

Aufruf (aus der Projekt-Venv):
    python tools/esphome_control.py list
    python tools/esphome_control.py number "Alde Soll-Raumtemperatur" 18.5
    python tools/esphome_control.py switch "Alde Heizung" on|off
    python tools/esphome_control.py select "Alde Warmwasser" Normal
Optionen: --host 192.168.1.240 (Default)
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

import aioesphomeapi

ROOT = Path(__file__).resolve().parent.parent


def read_secret(name: str) -> str:
    text = (ROOT / "esphome" / "secrets.yaml").read_text(encoding="utf-8")
    m = re.search(rf'^{name}:\s*"?([^"\n]+)"?', text, re.M)
    if not m:
        raise SystemExit(f"{name} nicht in esphome/secrets.yaml")
    return m.group(1).strip()


async def run(args: argparse.Namespace) -> int:
    api = aioesphomeapi.APIClient(args.host, 6053, "", noise_psk=read_secret("api_encryption_key"))
    await api.connect(login=True)
    try:
        entities, _services = await api.list_entities_services()
        by_name = {e.name: e for e in entities}
        if args.cmd == "list":
            for e in entities:
                print(f"{type(e).__name__:28s} key={e.key:<12d} {e.name}")
            return 0
        ent = by_name.get(args.name)
        if ent is None:
            print(f"Entitaet '{args.name}' nicht gefunden. Vorhanden:")
            for n in by_name:
                print("  ", n)
            return 1
        if args.cmd == "number":
            api.number_command(ent.key, float(args.value))
        elif args.cmd == "switch":
            api.switch_command(ent.key, args.value.lower() in ("on", "1", "true", "ein"))
        elif args.cmd == "select":
            api.select_command(ent.key, args.value)
        await asyncio.sleep(0.5)  # Befehl rausgehen lassen
        print(f"gesendet: {args.cmd} '{args.name}' = {args.value}")
        return 0
    finally:
        await api.disconnect()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="192.168.1.240")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for c in ("number", "switch", "select"):
        p = sub.add_parser(c)
        p.add_argument("name")
        p.add_argument("value")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
