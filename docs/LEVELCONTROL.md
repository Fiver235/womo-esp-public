# Truma LevelControl (Gasflaschen-Sensoren) ohne iNet Box

Stand 27.10.2026. Zwei LevelControl-Sensoren waren bisher per Bluetooth an die iNet Box gekoppelt. Ziel: Füllstände weiter in Home Assistant (läuft zu Hause) sehen.

## Ergebnis der Recherche

**Weiterverwenden ist möglich.** Die Home-Assistant-Integration [cyclemat/HAOS-Truma-Levelcontrol-Integration](https://github.com/cyclemat/HAOS-Truma-Levelcontrol-Integration) (GPL-3, HACS) liest die Sensoren direkt per BLE. Protokoll (aus der Truma-App rückentwickelt, Datei `truma.py` der Integration):

- Aktive GATT-Verbindung, kein reines Advertisement. Der Sensor sendet nur alle paar Minuten ein Advertisement und erlaubt **eine** Verbindung gleichzeitig (Truma-App währenddessen schließen).
- Ablauf: 5-Byte-Passwort aus einer Characteristic lesen → RC4-Schlüssel = Passwort XOR `"TRUMA"` → Messung anstoßen (zwei Einzelbyte-Writes `0x03`, `0x02` auf die `STORE_NV`-Characteristic, je 0,4 s Pause) → verschlüsselte Messung lesen und mit RC4 entschlüsseln.
- Antwort: Byte 0 Füllstand %, Byte 1–2 Gasmenge in 100 g (LE), Byte 3 Batterie %, Byte 4 Temperatur °C, Byte 6 Bits 7–6 Messqualität 0–3.
- Entitäten in HA: Füllstand, Gasmenge, Batterie, Temperatur, Messqualität, Zeitpunkt der letzten Messung, Button „Messung auslösen". Messintervall pro Gerät einstellbar.
- Empfohlene Hardware laut Autor: ESP32 als Bluetooth-Proxy nahe am Gaskasten oder RTL8761B-USB-Stick; billige Kombi-Sticks scheitern oft beim Verbinden.

Die Truma-App zeigt die Sensoren weiterhin lokal per Bluetooth an; die iNet Box lieferte nur die Fernanzeige.

**Alternative (Ersatz):** Mopeka Pro Check, ESPHome-Komponente [`mopeka_pro_check`](https://esphome.io/components/sensor/mopeka_pro_check/) (rein passiv, Presets 6/11/14 kg). Ca. 89–99 € pro Sensor ([Fritz Berger](https://www.fritz-berger.de/artikel/mopeka-pro-fuellstand-messgeraet-fuer-gasflaschen-mit-bluetooth-451114), [Reimo](https://www.reimo.com/ch/camping-shop/gastechnik-gaskocher-gasflasche/gasflaschen-fuellstandsanzeige/)). Nur sinnvoll, falls die LevelControl-Integration nicht zuverlässig läuft.

## Umsetzung: zweiter ESP32 als Bluetooth-Proxy mit WireGuard

Home Assistant baut die Verbindung zu ESPHome-Geräten selbst auf; hinter dem Nighthawk M5 (nur VPN-Passthrough, kein VPN-Client, Mobilfunk-NAT) ist ein ESP von zu Hause nicht erreichbar. Lösung wie beim Alde-ESP: WireGuard direkt auf dem ESP zur Fritzbox.

| Baustein | Wert |
|---|---|
| Config | `esphome/womo-ble-proxy.yaml` |
| Hardware | ESP32-WROOM-32 DevKit, 5 V per USB oder MP1584 aus 12 V, Platz nahe am Gaskasten |
| WLAN | Womo-WLAN, feste IP 192.168.1.241 (Alde-ESP: .240) |
| WireGuard | eigener Peer in der Fritzbox (Internet → Freigaben → VPN (WireGuard) → Einzelgerät), Tunnel-Adresse 192.168.100.208, Keepalive 25 s, nur 192.168.100.0/24 durch den Tunnel, `reboot_timeout: 0s` |
| Schlüssel | `proxy_wg_*` und `proxy_api_encryption_key` in `esphome/secrets.yaml` (nicht in Git) |
| BLE | `esp32_ble_tracker` + `bluetooth_proxy` mit `active: true` (GATT-Verbindungen nötig) |

**Wichtig:** Ein WireGuard-Peer (Schlüsselpaar) kann nur von einem Gerät benutzt werden. Der Alde-ESP hat 192.168.100.202, der Proxy 192.168.100.208.

### Stand 27.10.2026, 18:46

Proxy geflasht (COM9), WLAN 192.168.1.241, SNTP synchron, WireGuard-Handshake 18:46:16, Peer online. Vom Heimnetz aus ist Port 6053 auf 192.168.100.208 erreichbar (Ping antwortet der ESP durch den Tunnel nicht, das ist normal). In HA ist bisher nur der Alde-ESP eingetragen, HACS vorhanden, LevelControl-Repository noch nicht hinzugefügt.

### Schritte

1. ESP32 per USB flashen: `.\.venv\Scripts\esphome.exe run esphome\womo-ble-proxy.yaml --device COMx`. Im Log: `wireguard: ... online`, `latest_handshake` aktualisiert sich.
2. Zu Hause in HA: Einstellungen → Geräte & Dienste → ESPHome → Gerät hinzufügen → Host `192.168.100.208`, Port 6053, Schlüssel `proxy_api_encryption_key`. Danach erscheint der ESP als Bluetooth-Proxy (Einstellungen → Bluetooth). Erledigt am 27.10.2026 („Womo BLE-Proxy").
3. ~~HACS~~ **Manuell** installieren: HACS lehnt das Repository ab (alle Dateien im Wurzelverzeichnis, keine `hacs.json`). Stattdessen die Dateien per Samba-Share nach `\homeassistant\config\custom_components\truma_levelcontrol\` kopieren (`*.py`, `manifest.json`, `strings.json`; `de.json`/`en.json` nach `translations\`), danach HA neu starten. Erledigt am 27.10.2026 (Version 2.0.0, Dateien vorher auf Netzwerk-/Shell-Aufrufe geprüft: keine).
4. Die Sensoren werden per Discovery gemeldet oder manuell über ihre Bluetooth-MAC hinzugefügt. Truma-App dabei geschlossen halten. Messintervall unter „Konfigurieren" setzen (z. B. 30 min; jede Messung kostet Batterie des Sensors).

### Zu beachten

- Die aktive BLE-Verbindung läuft über LTE und den Tunnel; bei schlechtem Empfang schlägt eine Messung fehl und wird beim nächsten Intervall wiederholt.
- Zwei Sensoren mit gleichem Namen: die Integration unterscheidet sie per MAC; in HA ggf. umbenennen (Flasche links/rechts).
- Falls der Proxy WLAN oder Tunnel verliert, startet er **nicht** neu (`reboot_timeout: 0s`); ein Button „Proxy Neustart" ist als Entität vorhanden.
