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
- **Rechts:** über 20 Verbindungsversuche fehlgeschlagen, auch direkt nach erneutem Tastendruck (19:48). Mit Debug-Logging (`logger.set_level` für `custom_components.truma_levelcontrol`, `bleak_esphome`, `bleak_retry_connector`): erst „Timeout waiting for connect response after 20 s", später sofort `ESP_GATT_ERROR` (Code 133) beim Verbindungsaufbau, bei RSSI −63 bis −71 dB. Der Sensor wird gesehen, nimmt aber keine Verbindung an. Verdacht: belegt durch eine andere Zentrale (Handy mit Truma-App) oder Verbindung nur in einem bestimmten Zustand möglich. Links funktioniert mit identischem Weg, der Proxy ist also nicht die Ursache.

### Stand 27.10.2026, 19:59 – beide Sensoren lesbar

- **Rechts gelöst durch Werksreset** (Taste 20 s, danach kurz drücken): Verbindung danach beim ersten Versuch (Aufbau 13 s), Messung gelesen (Batterie 100 %, 23 °C). Der Sensor hatte offenbar einen festhängenden Verbindungszustand aus der iNet-Box-Zeit; ohne Reset lehnte er jeden Aufbau mit GATT-Fehler 133 ab. Für HA ist nach dem Reset keine neue Kopplung nötig.
- Links brauchte keinen Reset. Beide lagen beim Test auf dem Schreibtisch, Füllstand/Qualität 0 ist dort erwartbar; eine Messung lieferte zwischendurch 44 % mit Qualität 3 (vermutlich gespeicherter Altwert). Erst unter der Flasche bewerten; falls Werte schwanken, `MEASURE_WAIT_S` (3 s) in `const.py` erhöhen.
- Die Truma-App zeigt ohne iNet Box keine Füllstände; die Sensoren sprechen nur mit der Box bzw. jetzt mit HA.
- Debug-Logging wieder auf Standard gesetzt. Pollintervall Standard 600 s, pro Gerät unter „Konfigurieren" änderbar.

GATT-Profil des LevelControl (aus dem Service-Discovery, nützlich für eine spätere ESPHome-Eigenimplementierung): Dienste `22bfa601-…` (Characteristics `a610` Messung r, `a611`–`a617` r/w, `a619` Passwort r, `a61a` r/w), `22bfa6f0-…` (`a6f1` r), `22bfa701-…` (`a710`–`a715`), Device Information 0x180A, Battery 0x180F, sowie `f000ffd0-0451-…` (TI OAD-Firmware-Update → TI-CC26xx-Chip).

### Flaschentyp und -größe

In HA gibt es keine Einstellung dafür: Der Sensor liefert Prozent und Gramm fertig berechnet, der Flaschentyp wurde von der Truma-App über die iNet Box in den Sensor geschrieben (beschreibbare Characteristics `22bfa611`–`a617`/`a61a`, Kodierung unbekannt). **Geklärt (siehe Reverse Engineering unten):** der Werksreset löscht Name und Flaschenkonfiguration; beides wurde rechts wiederhergestellt. Prüfung: beide Sensoren nacheinander unter dieselbe Flasche, Messung auslösen, Werte vergleichen. Bei Abweichung entweder über die iNet Box (nur 12 V, ohne TIN-Bus, App-Verbindung) neu konfigurieren oder die Characteristic per Vergleich links/rechts selbst ermitteln.

### Reverse Engineering der Sensorkonfiguration (27.10.2026, 20:15)

Werkzeug: `tools/levelcontrol_dump.py` (liest alle Characteristics über den Proxy per aioesphomeapi; `--write` für Schreibtests). **Nebenwirkung:** Der ESPHome-Proxy liefert Advertisements und nimmt Verbindungsaufträge nur für die zuletzt abonnierte API-Verbindung an. Solange das Werkzeug läuft und danach, bis HA sich neu verbindet, bekommt HA keine Advertisements mehr („sensor not advertising right now", Polls scheitern still). **Nach jedem Einsatz des Werkzeugs den ESPHome-Eintrag „Womo BLE-Proxy" in HA neu laden** (`homeassistant.reload_config_entry`), am 27.10. kostete das zwei Stunden ohne Messwerte. Zwei Erkenntnisse zum Zugriff über den ESPHome-Proxy: Verbindungsaufträge nimmt der Proxy nur von der API-Verbindung an, die gerade Advertisements abonniert hat (Abo während des Zugriffs halten), und vor dem Verbinden auf ein Advertisement des Sensors warten.

**Protokoll-Details (beide Sensoren, Modell „TRUMA I1", Hardware 1.0):**

- Passwort (`a619`, 5 Byte) ist eine feste Umsortierung der MAC-Bytes [4],[1],[3],[5],[2] (90:7B:C6:43:20:B0 → `20 7b 43 b0 c6`). RC4-Schlüssel = Passwort XOR `TRUMA`.
- **Der RC4-Keystream läuft innerhalb einer Verbindung über alle Lesezugriffe der Characteristics des Dienstes `22bfa601` fort** (`a610`, `a611`…`a616`, `a61a`); `a617` (Trigger) ist Klartext und zählt nicht mit. Die HA-Integration liest pro Verbindung nur `a610` und sieht deshalb immer den Stromanfang.
- Firmware links 1.1.1.0 (002), rechts 1.0.7.0 (002); Seriennummern 0000000035121011 / 0000000030102002. Dienst `f000ffd0` = TI-OAD-Firmware-Update (TI CC26xx).

**Entschlüsselter Inhalt (links = konfiguriert, rechts = nach Werksreset):**

| Char | Bytes | links | rechts (Reset) | Deutung |
|---|---|---|---|---|
| `a610` | 8 | `00 00 00 64 17 00 00 00` | gleich | Messung: % / g·100 (LE) / Batterie / Temp / – / Qualität |
| `a611` | 16 | `0000000035121011` | `0000000030102002` | Seriennummer (ASCII) |
| `a612` | 12 | `Links` + Nullen | `000030102002` | **Name**, nach Reset Standard aus Seriennummer |
| `a613` | 6 | `04 6e 00 1c 00 00` | `00 0a 00 00 00 00` | Kopf: Flaschentyp-ID? / Parameter |
| `a614` | 20 | u16×10: 35 47 59 71 83 154 193 233 272 390 | Nullen | Tabelle 1 (steigend; Füllhöhe?) |
| `a615` | 20 | u16×10: 79 135 202 275 353 835 1102 1369 1636 2431 | Nullen | Tabelle 2 (steigend; Masse/Volumen?) |
| `a616` | 10 | u8×10: 207 187 167 145 123 100 76 52 26 0 | Nullen | Tabelle 3 (fallend) |
| `a61a` | 10 | u8×10: 131 114 97 82 67 53 40 28 16 5 | Nullen | Tabelle 4 (fallend) |
| `a617` | 1 | `00` | `00` | Trigger (Klartext, Schreiben 0x03 dann 0x02) |
| `a710` | 16 | `00 00 9f 00 … be 17 64 00 00 00 03 00` | `00 00 3d …` | Klartext, Byte 2 variiert (Zähler?) |
| `a711` | 4 | `20 bf 02 00` | gleich | Klartext |

**Schreiben (bestätigt 20:25 am rechten Sensor):** Klartext-Writes auf `a612` quittiert der Sensor mit GATT-Fehler 0x80 (Application error). Akzeptiert wird der Wert **RC4-verschlüsselt mit frischem Keystream** (eigener Strom für Writes, beginnt pro Verbindung bei 0; Lesezugriffe vorher zählen nicht mit – zumindest wenn nur das Passwort gelesen wurde). Die Änderung ist erst nach **Kommando `0x01` auf `a617`** (Klartext) dauerhaft; ohne das Kommando stand beim Zurücklesen der alte Wert. `a617` ist also ein Kommandoregister: 0x01 = Konfiguration speichern (Store NV), 0x03/0x02 = Messung anstoßen (so nutzt es die HA-Integration). Beispiel: `python tools/levelcontrol_dump.py 00:81:F9:6F:B2:DE --proxy 192.168.100.208 --write a612:7265636874732d31316b6700 --write "!a617:01" --write-encrypt`. Nebeneffekt: `a610` zeigte danach Qualität 3 und 5 % – das Kommando löst offenbar auch eine Messung aus.

**Wiederherstellung rechts (27.10.2026, 20:40, erledigt):** Beide Flaschen sind 11-kg-Stahl, daher Konfiguration 1:1 von links kopiert (fünf verschlüsselte Writes in einer Verbindung – der Write-Keystream läuft über die Writes fort – plus `!a617:01`), danach rechts zurückgelesen: identisch. Der Sensor prüft die Länge (zu kurze Tabelle → GATT-Fehler 7 „Invalid offset"). Verbindungen brechen gelegentlich auf Funkebene ab (Fehler 8); dann einfach wiederholen, ohne Speicherkommando wird nichts übernommen.

Referenzwerte **Truma LevelControl, 11-kg-Stahlflasche** (zum Wiederherstellen nach einem Reset):

```
a613: 04 6e 00 1c 00 00
a614: 23 00 2f 00 3b 00 47 00 53 00 9a 00 c1 00 e9 00 10 01 86 01
a615: 4f 00 87 00 ca 00 13 01 61 01 43 03 4e 04 59 05 64 06 7f 09
a616: cf bb a7 91 7b 64 4c 34 1a 00
a61a: 83 72 61 52 43 35 28 1c 10 05
Befehl: python tools/levelcontrol_dump.py <MAC> --proxy 192.168.100.208 --write-encrypt   --write a613:046e001c0000 --write a614:23002f003b00470053009a00c100e90010018601   --write a615:4f008700ca001301610143034e04590564067f09 --write a616:cfbba7917b644c341a00   --write a61a:837261524335281c1005 --write "!a617:01"
```

**Weitere Felder (Dienst `22bfa701`, 22:20):** `a715` (16 B) liegt ebenfalls im RC4-Strom (Offset nach den `22bfa601`-Reads, also fortlaufend über Dienstgrenzen) und ist auf beiden Sensoren `ff 00 … 00`, also kein Unterschied. `a710` Byte 2 ist ein laufender Wert (links 159, rechts 61 → 18 bei späterem Lesen), kein Konfigurationsparameter; Rest identisch (`be 17 64 … 03`). `a714` ist nur schreibbar. Damit sind alle lesbaren Felder beider Sensoren gleich.

**Messverhalten auf der Tischplatte (22:15):** links misst mit Koppelkissen nach unten 44 % / Qualität 3 (Echo aus der Tischplatte), mit Kissen nach oben 0 % / Qualität 0 → echte Messung. Rechts liefert in derselben Lage 0 % / Qualität 0. Da die lesbare Konfiguration identisch ist, bleiben als Ursachen: Koppelkissen/Auflage (Kissen muss sauber und plan aufliegen), Firmware-Unterschied (1.0.7 vs 1.1.1) oder ein nicht lesbarer Parameter (`a714`). Test: beide Sensoren an exakt derselben Stelle vergleichen.

**Advertisement (22:30):** Das 10-Byte-Herstellerfeld ist komplett variabel: links `01 08 …` (19:21) → `00 49 …` (22:27), rechts `01 21 …` → `00 76 …`/`00 77 …`. Die vermeintliche Hersteller-ID ist also ein Zähler plus 8 Byte vermutlich verschlüsselter Nutzdaten (Messwert?). Die Integration erkennt deshalb nur Sensoren, deren Zähler zufällig auf 0x5000 steht; Discovery müsste über den Namen `T?…` oder die Service-UUID 0x0A00 laufen. Entschlüsselung des Adv-Payloads (für passives Lesen ohne Verbindung) ist offen.

**Vergleich unter derselben Flasche (22:25):** links 90 % / 9,9 kg / Qualität 3, rechts 0 % / Qualität 0 trotz identischer lesbarer Konfiguration. Offene Erklärungen: Firmware 1.0.7 (rechts) interpretiert die kopierten Tabellen anders; nur schreibbares `a714` enthält einen beim App-Setup gesetzten Parameter; Konfiguration wird erst nach Neustart des Sensors (Batterien raus) aus dem Flash übernommen. Lösung: Neustart des Sensors (siehe „Gelöst").

**Gelöst (22:34):** Nach Batterien raus/rein misst der rechte Sensor unter derselben Flasche **89 % / 9,8 kg / Qualität 3** (links 90 % / 9,9 kg). Rohwert `59 62 00 64 15 2b c0 00`. Die per Bluetooth geschriebene Konfiguration wird also erst nach einem **Neustart des Sensors** wirksam; das Speicherkommando 0x01 legt sie nur im Flash ab. Vollständige Wiederherstellung nach Werksreset = Tabellen schreiben + `!a617:01` + Batterien kurz entnehmen + Taste drücken.

**Der Werksreset hat die Flaschenkonfiguration (a613–a616, a61a) und den Namen gelöscht.** Die Tabellen sind die vom Flaschentyp abhängige Kalibrierung, die die App über die iNet Box geschrieben hat. Wiederherstellung rechts: entweder die Werte vom linken Sensor kopieren (nur bei gleichem Flaschentyp!) oder Tabellen für den gewünschten Typ ermitteln.

### Schritte

1. ESP32 per USB flashen: `.\.venv\Scripts\esphome.exe run esphome\womo-ble-proxy.yaml --device COMx`. Im Log: `wireguard: ... online`, `latest_handshake` aktualisiert sich.
2. Zu Hause in HA: Einstellungen → Geräte & Dienste → ESPHome → Gerät hinzufügen → Host `192.168.100.208`, Port 6053, Schlüssel `proxy_api_encryption_key`. Danach erscheint der ESP als Bluetooth-Proxy (Einstellungen → Bluetooth). Erledigt am 27.10.2026 („Womo BLE-Proxy").
3. ~~HACS~~ **Manuell** installieren: HACS lehnt das Repository ab (alle Dateien im Wurzelverzeichnis, keine `hacs.json`). Stattdessen die Dateien per Samba-Share nach `\\homeassistant\config\custom_components\truma_levelcontrol\` kopieren (`*.py`, `manifest.json`, `strings.json`; `de.json`/`en.json` nach `translations\`), danach HA neu starten. Erledigt am 27.10.2026 (Version 2.0.0, Dateien vorher auf Netzwerk-/Shell-Aufrufe geprüft: keine).
4. Die Sensoren werden per Discovery gemeldet oder manuell über ihre Bluetooth-MAC hinzugefügt. Truma-App dabei geschlossen halten. Messintervall unter „Konfigurieren" setzen (z. B. 30 min; jede Messung kostet Batterie des Sensors).

### Zu beachten

- Die aktive BLE-Verbindung läuft über LTE und den Tunnel; bei schlechtem Empfang schlägt eine Messung fehl und wird beim nächsten Intervall wiederholt.
- Zwei Sensoren mit gleichem Namen: die Integration unterscheidet sie per MAC; in HA ggf. umbenennen (Flasche links/rechts).
- Falls der Proxy WLAN oder Tunnel verliert, startet er **nicht** neu (`reboot_timeout: 0s`); ein Button „Proxy Neustart" ist als Entität vorhanden.
