#!/usr/bin/env python3
"""Befehle per SSH auf dem Cerbo GX (Venus OS) ausfuehren.

Passwort kommt aus der Umgebungsvariable CERBO_PW (nie als Argument), Host aus CERBO_HOST
(Default 192.168.1.242), Benutzer root.

    $env:CERBO_PW = "..."; python tools/cerbo_ssh.py "uname -a" "cat /opt/victronenergy/version"
"""

from __future__ import annotations

import os
import sys

import paramiko


def main(argv: list[str]) -> int:
    host = os.environ.get("CERBO_HOST", "192.168.1.242")
    pw = os.environ.get("CERBO_PW")
    if not pw:
        print("CERBO_PW nicht gesetzt", file=sys.stderr)
        return 2
    if not argv:
        print("kein Befehl angegeben", file=sys.stderr)
        return 2
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, username="root", password=pw, timeout=15, look_for_keys=False, allow_agent=False)
    rc = 0
    try:
        for cmd in argv:
            script = None
            if cmd.startswith("put:"):
                # put:<lokal>:<remote>[:<mode>]  Datei per SFTP hochladen
                parts = cmd.split(":")
                local, remote = parts[1], parts[2]
                mode = int(parts[3], 8) if len(parts) > 3 else 0o644
                sftp = cli.open_sftp()
                sftp.put(local, remote)
                sftp.chmod(remote, mode)
                sftp.close()
                print(f"put {local} -> {remote} (mode {mode:o})")
                continue
            if cmd.startswith("@"):
                # @datei: lokales Shell-Skript per stdin an "sh -s" uebergeben (kein Quoting-Problem)
                with open(cmd[1:], encoding="utf-8", newline="\n") as fh:
                    script = fh.read()
                print(f"$ sh -s < {cmd[1:]}")
                _in, out, err = cli.exec_command("sh -s", timeout=600)
                _in.write(script)
                _in.channel.shutdown_write()
            else:
                print(f"$ {cmd}")
                _in, out, err = cli.exec_command(cmd, timeout=600)
            o = out.read().decode("utf-8", "replace")
            e = err.read().decode("utf-8", "replace")
            status = out.channel.recv_exit_status()
            if o:
                print(o.rstrip("\n"))
            if e:
                print(e.rstrip("\n"), file=sys.stderr)
            if status != 0:
                print(f"[exit {status}]")
                rc = status
    finally:
        cli.close()
    return rc


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    sys.exit(main(sys.argv[1:]))
