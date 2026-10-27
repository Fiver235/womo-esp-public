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

### Stand 27.10.2026, 18:55

HA neu gestartet: beide ESPs (Alde-ESP .202, Proxy .208) haben sich sofort durch den Tunnel verbunden, Integration `truma_levelcontrol` ist geladen (Einrichtungsdialog fragt nach Bluetooth-Adresse und Name). Protokoll-Konstanten laut `const.py`: Service `22bfa601-6afe-4cc5-b3ff-3e140baedeb6`, Measurement `…a610`, Password `…a619`, Store-NV `…a617`, Hersteller-ID 0x5000, Messwartezeit 3 s, Standard-Pollintervall 600 s. Offen: Proxy im Womo nahe am Gaskasten montieren, dann Discovery der zwei Sensoren abwarten oder MACs manuell eintragen.

### Aus der Truma-Anleitung LevelControl (PDF vom 27.10.2026)

- Verbinden mit iNet Box: Taste (5) kurz drücken, Status-LED (2) blinkt bis zu 2 Minuten (Sensor sichtbar), erlischt nach erfolgreichem Verbindungsaufbau. Bluetooth Klasse 2, Reichweite ca. 10 m, maximal zwei Sensoren pro iNet Box.
- Nach jedem Flaschenwechsel Taste kurz drücken (neue Messung).
- **Werksreset:** Taste 20 s halten bis LED kurz aufleuchtet, danach ist eine neue Verbindung nötig. Für den HA-Betrieb **nicht** erforderlich: die Integration nutzt das Passwort-Protokoll des Sensors, keine Bluetooth-Bindung.
- Trennen von der iNet Box geschieht nur in der App-Geräteliste.
- Batterien 2 × AAA Alkali, Wechsel nicht im Gaskasten.

Stand 19:03: Proxy hat 81 Bluetooth-Geräte gesehen, keines mit Hersteller-ID 0x5000. Nächster Schritt: Taste an beiden Sensoren kurz drücken, dann erneut prüfen.

### Stand 27.10.2026, 19:27 – Sensoren gefunden und angelegt

Nach kurzem Tastendruck an beiden Sensoren erschienen sie in der Bluetooth-Historie des Proxys (RSSI −55/−56 dB), mit den in der Truma-App vergebenen Namen:

| Sensor | Bluetooth-Adresse | Advertisement | HA-Eintrag |
|---|---|---|---|
| „T…Links" | `90:7B:C6:43:20:B0` | Hersteller-ID 0x0801, Services 0x0A00/0x1800 | „Gasflasche links" |
| „T…rechts-11kg" | `00:81:F9:6F:B2:DE` | Hersteller-ID 0x2101, Services 0x0A00/0x1800 | „Gasflasche rechts" |

**Keine automatische Erkennung:** Die Integration wartet auf Hersteller-ID 0x5000 (20480); diese Sensoren senden andere IDs (vermutlich variabler Inhalt statt fester Firmen-ID). Deshalb manuell über die Adresse anlegen. Das Anlegen per MCP-Werkzeug lief in den 30-s-Timeout und brach die laufende Einrichtung ab (`setup_error`); ein `homeassistant.reload_config_entry` je Eintrag hat das behoben.

- **Links:** erste Messung 19:24 erfolgreich: Batterie 100 %, Temperatur 22 °C, aber Füllstand 0 %, Gasmenge 0,0 kg, Messqualität 0 → Entschlüsselung stimmt, Messung selbst ohne akustische Kopplung (prüfen: sitzt der Sensor unter der Flasche?).
- **Rechts:** sechs Verbindungsversuche in Folge fehlgeschlagen („sensor not reachable this cycle") trotz RSSI −51 dB; Entitäten `unavailable`. Vermutung: Verbindung nur im Zwei-Minuten-Fenster nach Tastendruck oder bei einem der seltenen Advertisements möglich; der ESP32-Connect läuft vorher in den Timeout. Nächster Test: Taste drücken und sofort „Messung auslösen".

### Schritte

1. ESP32 per USB flashen: `.\.venv\Scripts\esphome.exe run esphome\womo-ble-proxy.yaml --device COMx`. Im Log: `wireguard: ... online`, `latest_handshake` aktualisiert sich.
2. Zu Hause in HA: Einstellungen → Geräte & Dienste → ESPHome → Gerät hinzufügen → Host `192.168.100.208`, Port 6053, Schlüssel `proxy_api_encryption_key`. Danach erscheint der ESP als Bluetooth-Proxy (Einstellungen → Bluetooth). Erledigt am 27.10.2026 („Womo BLE-Proxy").
3. ~~HACS~~ **Manuell** installieren: HACS lehnt das Repository ab (alle Dateien im Wurzelverzeichnis, keine `hacs.json`). Stattdessen die Dateien per Samba-Share nach `\\homeassistant\config\custom_components\truma_levelcontrol\` kopieren (`*.py`, `manifest.json`, `strings.json`; `de.json`/`en.json` nach `translations\`), danach HA neu starten. Erledigt am 27.10.2026 (Version 2.0.0, Dateien vorher auf Netzwerk-/Shell-Aufrufe geprüft: keine).
4. Die Sensoren werden per Discovery gemeldet oder manuell über ihre Bluetooth-MAC hinzugefügt. Truma-App dabei geschlossen halten. Messintervall unter „Konfigurieren" setzen (z. B. 30 min; jede Messung kostet Batterie des Sensors).

### Zu beachten

- Die aktive BLE-Verbindung läuft über LTE und den Tunnel; bei schlechtem Empfang schlägt eine Messung fehl und wird beim nächsten Intervall wiederholt.
- Zwei Sensoren mit gleichem Namen: die Integration unterscheidet sie per MAC; in HA ggf. umbenennen (Flasche links/rechts).
- Falls der Proxy WLAN oder Tunnel verliert, startet er **nicht** neu (`reboot_timeout: 0s`); ein Button „Proxy Neustart" ist als Entität vorhanden.
