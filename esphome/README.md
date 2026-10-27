# ESPHome-Konfiguration „Alde Gateway"

Ersatz für die Truma iNet Box: liest den TIN-Bus passiv mit (LIN-A) und steuert das Alde-Bedienteil über dessen JP3-„External panel"-Port (LIN-B). Hintergrund und Phasenplan in [../PLAN.md](../PLAN.md).

## Dateien

| Datei | Zweck |
|---|---|
| `alde-gateway.yaml` | Node-Config (Board, WLAN, API, OTA, Web-UI), bindet die Packages ein |
| `packages/tin_reader.yaml` | LIN-A: Mitleser des TIN-Bus, **schreibt nie** (Basis: Mellowgroup-dk/alde-3020he-lin, MIT) |
| `packages/jp3_control.yaml` | LIN-B: LIN-Master an JP3, Steuerung der Alde (Basis: holdestmade/esphome-alde-3020, MIT) |
| `alde-inetbus-observer.yaml` | **Track B1:** separater Node zum Mitschneiden des TIN-Bus **mit** echter iNet Box (Fabian Schmidt `@alde`, `observer_mode: true`, sendet nichts). Messprotokoll in [../docs/TRACK-B-INET-BUS.md](../docs/TRACK-B-INET-BUS.md) |
| `alde-inetbox-b2.yaml` | **Track B2:** iNet-Box-Emulation, **sendet** Befehle (0x50/0x54) an das Alde-Panel. Nur mit abgezogener echter iNet Box! Ersetzt den Observer auf demselben ESP32 |
| `secrets.yaml.example` | Vorlage für `secrets.yaml` (nicht einchecken) |
| `../tools/esphome_control.py` | Entitäten des Knotens ohne Home Assistant per nativer API schalten (`list`, `number`, `switch`, `select`), Key aus `secrets.yaml` |
| `../tools/parse_observer_log.py` | Auswertung der Observer-Logs: Nachrichten tabellieren, dekodieren, ACKs zuordnen, Diffs zwischen Aktionen |

## Verdrahtung

```
                 ESP32-WROOM-32 DevKit
                 ┌──────────────────┐
 12V Bord ──Buck─┤ 5V/VIN       GND ├──────────────┬────────────┬── Fahrzeugmasse
                 │                  │              │            │
   TIN-Bus       │ GPIO16 (RX) ◄────┤ RXD  TJA1020 │ LIN ──► RJ12 Pin 3 (LIN)
   (LIN-A)       │ GPIO17 (TX) ────►│ TXD   (A)    │ GND ──► RJ12 Pin 5 (GND)
                 │                  │ VBAT ◄── 12V │
                 │                  │              │
   JP3 Panel     │ GPIO26 (RX) ◄────┤ RXD  TJA1020 │ LIN ──► JP3 LIN-Ader
   (LIN-B)       │ GPIO27 (TX) ────►│ TXD   (B)    │ GND ──► JP3 GND
                 └──────────────────┘ VBAT ◄── 12V
```

- Detaillierte Pin-für-Pin-Verdrahtung mit dem LIN-Modul „FST T151" (TJA1020-Board): [../docs/VERDRAHTUNG.md](../docs/VERDRAHTUNG.md).
- Am RJ12 des TIN-Bus liegen **keine 12 V** an – Versorgung aus dem Bordnetz, 1-A-Sicherung.
- TJA1020: RXD ist Open-Drain → Pull-up auf 3,3 V (viele Breakouts haben ihn; sonst 10 kΩ nachrüsten). NSLP auf High legen.
- Masse aller Teilnehmer verbinden, sonst keine Kommunikation.
- JP3-Pinbelegung vor dem Anschluss am Panel/Kabel messen (Phase 0); Alde-Originalkabel „External panel" verwenden.

## Inbetriebnahme

ESPHome ist auf diesem Notebook in einer Projekt-Venv installiert (`C:\Code\Truma\.venv`, ESPHome 2026.10.0). Vor jedem Aufruf aktivieren (PowerShell):

```bash
C:\Code\Truma\.venv\Scripts\Activate.ps1
```

Neuinstallation auf einem anderen Rechner:

```bash
python -m venv .venv && .venv/Scripts/pip install esphome
```

`esphome/secrets.yaml` ist angelegt (API-Key und Passwörter generiert) – **WLAN-SSID und -Passwort darin eintragen**. Die Datei ist per `.gitignore` ausgeschlossen.

**USB-Treiber:** Der CP2102-Treiber (Silicon Labs) ist noch nicht installiert; Windows 11 lädt ihn beim ersten Einstecken des ESP32 normalerweise per Windows Update nach. Erscheint danach kein „Silicon Labs CP210x USB to UART Bridge (COMx)" im Geräte-Manager: Treiber von https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers installieren. Boards mit CH340-Chip brauchen stattdessen den WCH-CH341SER-Treiber.

Track B1 (Observer, erster Schritt):

```bash
esphome run esphome/alde-inetbus-observer.yaml
```

Phase 1 Gateway (nur lesen): in `alde-gateway.yaml` die Zeile `jp3_control:` auskommentieren, dann

```bash
esphome run esphome/alde-gateway.yaml
```

Phase 2 (steuern): JP3 verkabeln, im Alde-Panel **Settings → Installed Accessories → Third Party Panel** aktivieren, `jp3_control:` wieder einkommentieren, erneut flashen. Erwartete Log-Zeilen: `alde3020: Info frame …` ohne `checksum`/`timeout`-Warnungen.

## Bekannte Punkte

- `alde3020` ist nur mit einer Alde 3020 (nicht HE) nachgewiesen; Checksummen-Modus wird automatisch erkannt. Bei „Jumping values" Polling-Intervall `SEND_INTERVAL_MS` in `alde3020.h` auf 2000 erhöhen (Fork nötig).
- Der TIN-Setpoint (`TIN Setpoint`) ist bei aktiver Klimaanlage nicht der Sollwert (siehe Kommentar im Package).
- Logger läuft auf `DEBUG`, damit die Transport-Frames (0x3C/0x3D) für Track B sichtbar sind. Nach Abschluss auf `INFO`.

## Fernzugriff (WireGuard)

Der Nighthawk M5 im Womo kann kein VPN und hat im LTE-Netz keine öffentliche Adresse. Der B2-Knoten baut deshalb selbst einen WireGuard-Tunnel zur Fritzbox zu Hause auf (`wireguard:` in `alde-inetbox-b2.yaml`, Peer „alde-inetbox" in der Fritzbox unter Internet → Freigaben → VPN (WireGuard)). Schlüssel in `secrets.yaml` (`wg_private_key`, `wg_peer_public_key`, `wg_preshared_key`), übernommen aus der von der Fritzbox erzeugten `.conf`.

- Tunnel-Adresse des ESP: `192.168.100.202`, nur das Heimnetz `192.168.100.0/24` läuft durch den Tunnel.
- `time: sntp` ist Pflicht (Handshake braucht die Uhrzeit); `reboot_timeout: 0s` bei `api`, `wifi` und `wireguard`, damit die Heizungssteuerung bei Verbindungsverlust nicht neu startet.
- Home Assistant (zu Hause): ESPHome-Integration → Gerät **manuell** hinzufügen, Host `192.168.100.202`, Port 6053, Schlüssel `api_encryption_key`. Auto-Discovery funktioniert über VPN nicht.
- Kontrolle: Entitäten „WireGuard verbunden" und „WireGuard letzter Handshake"; im Log `wireguard: Remote peer is online`.
- Erster Test 27.10.2026 17:58: Handshake innerhalb von 5 s nach Boot, Peer online, keine LIN-Fehler.
