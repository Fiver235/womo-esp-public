# Track B – Alde-Steuerung über den iNet-/TIN-Bus: Protokoll-Dossier

Stand 2026-10-16. Zusammengetragen aus: WomoLIN-Mitschnitten einer **echten iNet Box** (Truma Combi), Fabian Schmidts `alde`-Branch mit **echten Alde-3020-HE-Mitschnitten** (`examples/alde.txt`, `alde2.txt`), Issue-Threads (esphome-truma_inetbox #22/#53, inetbox.py #28/#33) und Mellowgroup-dk/alde-3020he-lin.

**Kernaussage:** Die bisherige Community-Schlussfolgerung „Alde sendet keine Geräteliste und quittiert nichts, daher ist Steuerung über den TIN-Bus unmöglich" ist **falsch** bzw. beruht auf Truma-Annahmen. Die Alde-Mitschnitte zeigen eine Geräteliste (Typ **0x0C**) und eine Quittung (Typ **0x0D**) – beides existiert, nur anders als bei Truma. Der eigentliche Steuerbefehl (vermutlich Typ **0x50**) wurde **nie korrekt getestet**.

---

## 1. Referenz: So steuert eine echte iNet Box eine Truma (WomoLIN, `truma_app-set_heating_to_20.log`)

LIN-Frames auf PID 0x3C (Master → Slave) / 0x3D (Slave → Master), NAD der iNet Box = 0x03. App setzt 20 °C:

```
D8  FF FF FF FF FF FF FF FF        <- iNet Box antwortet auf PID 0x18: FF = "ich habe ein Update" (sonst FE)
3C  03 05 B9 00 1F 00 00 FF        <- CP Plus: Heartbeat an NAD 03
7D  03 02 F9 00 FF FF FF FF        <- Box: Heartbeat-Antwort
3C  03 10 0B BA 00 1F 00 1E        <- CP Plus: READ (SID 0xBA), 11 Byte, Header-Byte4 = 0x1E
3C  03 21 00 00 22 FF FF FF
7D  03 10 29 FA 00 1F 00 1E        <- Box: Antwort (SID 0xFA), 41 Byte
7D  03 21 00 00 22 FF FF FF
7D  03 22 54 01 0C 32 16 D5        <- MSG-Head: 'T' 01 | len 0x0C | type 0x32 | counter 0x16 | chk 0xD5
7D  03 23 72 0B 01 00 00 00        <- Payload: Soll 0x0B72 = 2930 dK = 20.0 °C, ...
7D  03 24 00 00 00 00 01 01
7D  03 25 00 00 00 00 00 00
7D  03 26 00 00 00 00 00 00
3C  03 10 29 BB 00 1F 00 1E        <- CP Plus: DOWNLOAD (SID 0xBB)
3C  03 21 00 00 22 FF FF FF
3C  03 22 54 01 02 0D 16 85        <- MSG type 0x0D = ACK, counter 0x16 (= Counter des Befehls!)
3C  03 23 00 00 00 00 00 00 ...
7D  03 01 FB FF FF FF FF FF        <- Box: Transport-ACK
3C  03 05 B9 00 1F 00 01 FF        <- Heartbeat, Flag-Byte 01 statt 00
D8  FE FF FF FF FF FF FF FF        <- Box: "kein Update mehr"
```

Vierschritt: **Flag (0x18=FF) → Panel liest (BA) → Box sendet Befehlspuffer (0x32) → Panel quittiert (0x0D mit gleichem Counter)**.

Status-Puffer-Aufbau (gilt für Truma und Alde):

```
SID | 00 1F 00 <L> 00 00 22 FF FF FF | 54 01 <len> <type> <counter> <chk> | payload(len)
     ^ Präambel, Byte4 = L            ^ MSG-Head ('T', 0x01)
```

- Truma: L immer 0x1E. **Alde: L = len + 6** (gemessen: 0x51→0x22, 0x0C→0x14, 0x0D→0x08, 0x55→0x12, 0x53→0x2A, 0x15→0x10); READ-Anfrage des Alde-Panels trägt L = 0x1A, die Init-Antwort des Emulators ebenfalls 0x1A.
- `chk`: Prüfsumme über Payload (data_checksum ab Byte 10, Komplement).
- Typ-Konvention: Status vom Panel = ungerade Nummer, **Befehl von der Box = Status-Typ − 1** (Truma: 0x33 → 0x32, 0x35 → 0x34, 0x3D → 0x3C). Für Alde ergibt das: **0x51 → 0x50**, 0x55 → 0x54, 0x57 → 0x56.

---

## 2. Was das Alde-3020-HE-Panel an eine (emulierte) iNet Box sendet

Quelle: Fabian Schmidt `alde`-Branch, `examples/alde.txt`/`alde2.txt` (Panel 3020-113 „iNet ready", Compact 3020 HE, 2024). Alle Nachrichten SID 0xBB (Panel → Box), ohne Präambel dargestellt:

| MSG-Typ | len | Bedeutung | Beispiel (Payload) |
|---|---|---|---|
| **0x0C** | 14 | **Geräteliste (Alde-Variante von 0x0B)** – eine Nachricht pro Gerät | `02 00 01 FF DE 41 01 00 00 04 10 00 00 00` = Gerät 0/2: Alde-Panel 3020-113 (Supplier 0x41DE, Fn 0x0001)<br>`02 01 01 FF DE 41 30 03 00 02 6D 00 00 00` = Gerät 1/2: Alde Compact 3020 HE (Fn 0x0330) |
| **0x0D** | 2 | **ACK** auf eine Nachricht der Box; Byte `counter` = Counter der quittierten Nachricht | `00 FF` (Head: `54 01 02 0D 1E 7D`) |
| **0x51** | 28 | **Alde-Status** (Haupt-Statuspuffer) | `01 00 5E 0B FE FF 00 00 37 01 00 64 FF FF FF 12 71 0B FE FF FA 0A 00 1E FF FF FF FF` |
| 0x53 | 36 | Zusatz: Temperatursensor-Wahl (Auto/Bett/Panel) u. a. | `36 00 00 00 00 FD FD 00 00 02 00 00 00 01 FD FD 00 FF FF FF 01 FD FF 00 ...` |
| 0x55 | 12 | Nachtmodus (Soll, Start/Ende, Wochentage, Bits) | `FD 5E 0B DE 03 C2 01 07 07 17 03 FF` |
| 0x57 | 12 | Tagmodus | `15 63 0B DE 03 CE 04 07 07 00 00 FF` |
| 0x15 | 10 | Uhr/Datum | `48 0A 2A 09 FF FF FF 00 01 05` |

**Dekodierung 0x51 (StatusFrameAldeStatus, 28 Byte):**

| Offset | Feld | Werte |
|---|---|---|
| 0 | heater_mode | 0x00 aus, 0x01 ein |
| 1 | – | 0x00 |
| 2–3 | **target_temp_room** | u16 LE Dezikelvin: °C = (v − 2730)/10 (0x0B5E → 18.0 °C) |
| 4–5 | – | 0xFFFE |
| 6 | water_mode | 0 aus, 100 normal, 200 boost |
| 7 | el_mode | 0 / 10 / 20 / 30 = 0/1/2/3 kW |
| 8 | gas_mode | 0x00 aus, 0x37 ein |
| 9 | heater_prio | 0x00 Elektro, 0x01 Gas |
| 10 | – | 0x00 |
| 11 | – | 0x64 |
| 12–14 | – | 0xFF |
| 15 | message_counter | läuft hoch |
| 16–17 | current_temp_inside | Dezikelvin |
| 18–19 | – | 0xFFFE |
| 20–21 | current_temp_outside | Dezikelvin |
| 22–27 | – | 00 1E FF FF FF FF |

Verifiziert durch Panel-Aktionen im Mitschnitt (alde2.txt): Soll 17,5→18→20→18,5 °C, Gas ein/aus, Elektro 1/2/3 kW, Warmwasser aus/normal/boost, Priorität, Sensorwahl, Nachtmodus – jede Aktion erzeugt eine entsprechende 0x51/0x55/0x53-Nachricht.

**Init-Ablauf (beobachtet):**

```
Panel: BA 00 1F 00 1A 00 00 22 FF FF FF              READ (L=0x1A)
Box:   FA 00 1F 00 1A 00 00 22 FF FF FF 54 01 00 0A <ctr> <chk>   Init-Nachricht Typ 0x0A, leer
Panel: BB ... 54 01 02 0D <ctr> <chk> 00 FF           ACK auf die Init-Nachricht
Panel: BB ... 0C (Gerät 0/2), 0C (Gerät 1/2)          Geräteliste  <-- Typ 0x0C, nicht 0x0B!
Panel: BB ... 55, 57, 15, 51, 53                      kompletter Status
```

Danach pollt das Panel PID 0x18 und schickt Heartbeats (NAD 0x03). Im Panel-Servicemenü erscheint „Truma iNet Box".

**LIN-Identifikation:** Box antwortet auf ReadByIdentifier mit Supplier 0x4617, Function 0x1F00 (`17 46 00 1F`), Variante 0x00; Identifier 0x20 liefert die Versionsanzeige (3 Byte, z. B. `02 0E 00`), Identifier 0x22 muss beantwortet werden (Inhalt egal).

---

## 3. Warum die bisherigen Versuche scheiterten

| Projekt | Annahme | Realität |
|---|---|---|
| Mellowgroup / posexperten-crypto (2026) | `init_recieved_` wartet auf Geräteliste **0x0B**, 12 Byte | Alde sendet **0x0C**, 14 Byte → Emulator hielt sich nie für initialisiert, sendete 0x32/0x34 (**Truma**-Befehlstypen) → vom Panel ignoriert |
| dito | „Alde quittiert nie" | 0x0D-ACK ist in jedem Fabian-Mitschnitt zu sehen – auf Nachrichten, die das Panel versteht |
| Fabian `alde`-Branch (2024-04) | Befehl = **0x50** (16 Byte, Spiegel von 0x51 ohne Ist-Werte) | **nie getestet**: 5of9 testete am 24.03.2024, *bevor* die 0x0C-Erkennung eingebaut war (06.04.2024); die Meldung „Cannot update Truma" kam aus dem Truma-Pfad. Danach keine Rückmeldung mehr. |
| inetbox.py #28/#33 | – | Kein Alde-Code vorhanden (Maintainer) |

Offen ist also nur: **Welches Format akzeptiert das Alde-Panel als Befehl?** Kandidaten (in dieser Reihenfolge zu testen):

1. 0x50 mit 16 Byte (Fabians Struktur), L = 0x16 (len+6)
2. 0x50 mit 16 Byte, L = 0x1A (wie vom Panel in BA angefragt)
3. 0x50 mit 28 Byte (kompletter 0x51-Spiegel), L = 0x22
4. 0x54 / 0x56 (Nacht-/Tag-Modus-Befehle) analog

Erfolgsindikator: Panel antwortet mit **0x0D und dem Counter des Befehls**, anschließend neues 0x51 mit dem geänderten Wert; Sichtprüfung am Panel.

**→ Beantwortet durch den Mitschnitt vom 27.10.2026 (Abschnitt 6): Kandidat 2 ist richtig – 0x50, 16 Byte, L = 0x1A.**

---

## 4. Der entscheidende Vorteil: eine echte iNet Box am Alde-System

Keiner der bisherigen Reverse-Engineers hatte eine iNet Box **am Alde-Panel**. Mit deiner Installation lässt sich der echte Befehl mitschneiden, dann ist Raten überflüssig.

### Mitschnitt-Setup

- ESP32 + TJA1020 passiv am TIN-Bus (RJ12-Splitter), iNet Box **bleibt** angeschlossen und mit der Truma-App gekoppelt.
- Firmware: `esphome/alde-inetbus-observer.yaml` (Fabian `@alde`-Branch mit `observer_mode: true`). Der Observer dekodiert die Transportschicht (BA/BB/FA, Multi-Frame-Reassembly) und loggt jede Nachricht als `Multi package request/response …` inkl. Alde-Struktur-Dekodierung. **Sendet nichts.**
- Alternativ/zusätzlich `packages/tin_reader.yaml` (roher Mitschnitt mit TP-Hexdumps).
- Log per USB (`baud_rate: 500000`, `level: VERBOSE`) oder per WLAN mitschneiden und als Datei sichern.

### Messprotokoll

| # | Aktion | Erwartung im Log |
|---|---|---|
| 0 | 2 min Ruhe | Periodik: 0x18-Polls (FE), Heartbeats, gelegentlich 0x51/0x53/0x55/0x57/0x15 |
| 1 | App: Soll +1 °C | `D8 FF…` → BA → **FA … 54 01 <len> <TYP> <ctr> …** (der gesuchte Befehl) → BB 0x0D <ctr> → neues 0x51 |
| 2 | App: Soll −1 °C | wie 1 (Payload-Unterschied an Offset 2–3) |
| 3 | App: Heizung aus / ein | Payload Offset 0 |
| 4 | App: Warmwasser aus/normal/boost | Offset 6 |
| 5 | App: Elektro 0/1/2/3 kW | Offset 7 |
| 6 | App: Gas ein/aus | Offset 8 |
| 7 | App: Aventa ein / aus / Modus | eigener Typ? (Truma: 0x34/0x36) oder Feld in 0x50 |
| 8 | Dieselben Aktionen am Panel | nur 0x51 ohne vorhergehenden FA-Befehl (Kontrollgruppe) |

Pro Aktion Uhrzeit notieren; zwischen Aktionen ≥ 20 s warten.

### Auswertung

Skript: `python tools/parse_observer_log.py <log> --csv auswertung.csv` (nur Standard-Python). Es

1. extrahiert alle `Multi package request/response`-Zeilen, zerlegt sie in SID / L (Header-Byte 4) / Typ / len / Counter / Prüfsumme / Payload und dekodiert bekannte Typen (0x0C, 0x0D, 0x51, 0x53, 0x55, 0x57, 0x15, 0x33/0x32),
2. zeigt den Byte-Diff zum vorherigen Vorkommen desselben Typs (→ Feldzuordnung je Aktion),
3. verknüpft jede Box-Nachricht (FA) mit dem folgenden 0x0D-ACK (gleicher Counter = Truma-Muster, Counter−1 = Muster aus Fabians Alde-Logs) und jede READ-Anfrage mit der Antwort,
4. listet am Ende alle Box→Panel-Nachrichten außer Init als **Befehlskandidaten** mit Typ, len und L.

Notizen, die man während der Messung als eigene Zeilen ins Log tippt (z. B. „App: Soll 19 → 20"), übernimmt das Skript als Abschnittsmarker. Beispiel-Logs mit Ausgabe: `docs/samples/`.

Abgleich danach: stimmen Typ, Länge und L der echten Box-Befehle mit Fabians `StatusFrameAldeStatusResponse` (0x50, 16 Byte, L 0x16) überein?

### Implementierung (nach dem Mitschnitt)

- Fork von `Fabian-Schmidt/esphome-truma_inetbox@alde`; `TrumaStructsAlde.h`/`TrumaiNetBoxAppAldeStatus.cpp` an das gemessene Format anpassen; `action_heater_room` existiert bereits, `water`/`electric`/`gas` sind auskommentierte Vorlagen.
- Entitäten: `number` TARGET_ROOM_TEMPERATURE und ELECTRIC_POWER_LEVEL sind im Branch schon auf Alde umgeleitet; `climate ROOM` folgt demselben Muster.
- Test **ohne** echte iNet Box am Bus (NAD-Konflikt), zuerst mit Logging, Panel in Sichtweite.
- Erfolg → Rückmeldung an esphome-truma_inetbox #53 und Mellowgroup-Repo.

---

## 5. Aventa im Alde-System

- Am Alde-TIN-Bus ist die Aventa ein eigener LIN-Slave (NAD 0x02, Supplier 0x4617, Function 0x0C00). Das Panel steuert sie; Statusfelder liegen in den Signal-Frames 0x97/0x08 (Mellowgroup).
- In einem Alde-3030-Mitschnitt mit echter iNet Box (inetbox.py #33, hliebscher) fragt das Panel per ReadByIdentifier u. a. Function 0x0C00/0x0C04/0x0C07 ab – d. h. das Alde-Panel kennt mehrere Truma-Klimavarianten.
- Ob die iNet Box die Aventa im Alde-System über eigene Befehlspuffer (Truma: 0x34 manuell / 0x36 auto) steuert, zeigt Messschritt 7. Die Truma-App bietet bei Alde+Aventa Klimasteuerung an → sehr wahrscheinlich ja.

---

## 6. Alternative Wege (zur Vollständigkeit)

| Weg | Status | Bewertung |
|---|---|---|
| **JP3 „3rd Party Panel"** (Track A, holdestmade) | funktioniert laut Nutzern (Alde 3020) | gesicherter Fallback; nur AC-Auto für Aventa |
| **iNet Box behalten, per Bluetooth ansteuern** (Lorilonlon/camper-heater-bridge, PROTOCOL.md) | BLE-Protokoll der klassischen iNet Box reverse-engineered; Bridge auf Raspberry Pi (BLE-Peripheral) | kein Bus-Eingriff, aber Box bleibt (Strom, Bluetooth-Koppelung), getestet nur mit Combi |
| WomoNET.core (kommerziell, 999 €) | „Alde 3020 HE: volle Steuerung über LIN, CI-Bus-Protokoll" | bestätigt Track-A-Weg (CI-Bus = JP3), keine Doku |
| Alde Smart Control | GSM | ausgeschlossen (SIM) |

---

## 7. Quellen

- WomoLIN Truma-Mitschnitte (echte iNet Box): https://github.com/muccc/WomoLIN/tree/master/Trumalogs
- Fabian Schmidt `alde`-Branch: https://github.com/Fabian-Schmidt/esphome-truma_inetbox/tree/alde (`examples/alde.txt`, `alde2.txt`, `components/truma_inetbox/TrumaStructsAlde.h`, `TrumaiNetBoxAppAldeStatus.cpp`)
- Issue #22 (Alde no data): https://github.com/Fabian-Schmidt/esphome-truma_inetbox/issues/22 · Issue #53: https://github.com/Fabian-Schmidt/esphome-truma_inetbox/issues/53
- inetbox.py #28: https://github.com/danielfett/inetbox.py/issues/28 · #33 (Alde-3030-Mitschnitt mit iNet Box): https://github.com/danielfett/inetbox.py/issues/33
- Mellowgroup-dk/alde-3020he-lin: https://github.com/Mellowgroup-dk/alde-3020he-lin (docs/PROTOCOL.md, docs/CONTROL-NOT-SOLVED.md)
- holdestmade/esphome-alde-3020 (JP3): https://github.com/holdestmade/esphome-alde-3020
- Lorilonlon/camper-heater-bridge (iNet Box BLE): https://github.com/Lorilonlon/camper-heater-bridge
- WomoNET Alde-Kompatibilität: https://wiki.womonet.io/de/compatible-devices/alde/

---

## 6. Ergebnis des B1-Mitschnitts (27.10.2026, echte iNet Box am Alde Compact 3020 HE)

Setup: Observer (`alde-inetbus-observer.yaml`, Fabian `@alde` + Patches, `observer_mode: true`) am RJ12-Splitter, iNet Box angeschlossen, 7 App-Aktionen und dieselben Aktionen am Panel (Kontrollgruppe). Rohlog mit Markern: `docs/samples/b1-2026-10-27-app-aktionen.log`, Auswertung daneben (`…auswertung.txt`, erzeugt mit `tools/parse_observer_log.py --only-tp`). 0 Prüfsummenfehler, 133 Transportnachrichten.

**Wichtig für die Auswertung:** Im Observer-Modus ist die Logzeile `Multi package response …` die Antwort, die die Komponente *selbst* gesendet hätte (ihr Init 0x0A), nicht die der echten Box. Der Parser setzt deshalb die echten Antworten aus den `PID 3D`-Rohframes zusammen (`--source raw`, automatisch).

### Ablauf eines App-Befehls (Beispiel „Soll +1 °C", 14:58)

```
14:58:05.267  PID 18  FF FF FF FF FF FF FF FF        Box: Update liegt an (vorher FE)
14:58:06.309  3C  03 10 0B BA 00 1F 00 1A           Panel: READ (L = 0x1A)
14:58:06.355  3C  03 21 00 00 22 FF FF FF
14:58:06.362  3D  03 10 25 FA 00 1F 00 1A           Box: 37 Byte Antwort
14:58:06.413  3D  03 21 00 00 22 FF FF FF
14:58:06.459  3D  03 22 54 01 10 50 02 CD           'T' 01 | len 0x10 | type 0x50 | ctr 0x02 | chk
14:58:06.469  3D  03 23 01 00 68 0B FF FF           Payload Byte 0..5
14:58:06.525  3D  03 24 64 00 37 01 00 64           Byte 6..11
14:58:06.539  3D  03 25 FF FF FF 05 00 00           Byte 12..15, dann 00-Füllung
14:58:06.562  3D  03 26 00 00 FF FF FF FF
14:58:07.411  3C  03 10 13 BB 00 1F 00 08           Panel: ACK-Download (L = 0x08)
14:58:07.418  3C  03 21 00 00 22 FF FF FF
14:58:07.464  3C  03 22 54 01 02 0D 02 99           type 0x0D, len 2, ctr 0x02 (= Counter des Befehls)
14:58:07.466  3C  03 23 00 FF FF FF FF FF
14:58:07.532  3D  03 01 FB FF FF FF FF FF           Box: positive Antwort
14:58:07.786  PID 18  FE …                          Box: kein Update mehr
14:59:01      BB 0x51 …  Soll 19,0 °C, ctr+1        Panel: naechster PERIODISCHER Status (alle ~2 min)
```

Das Panel sendet nach einem Box-Befehl **keinen** sofortigen Status; die Bestätigung ist allein das 0x0D-ACK, der neue Wert erscheint im nächsten periodischen 0x51 (Abstand ~120 s). Bei Bedienung am Panel kommt der 0x51 dagegen innerhalb von 1–2 s.

Alle 17 App-Befehle liefen exakt so; das Panel quittierte jeden mit 0x0D und **demselben** Counter (Truma-Muster, nicht Counter−1 wie in Fabians Alde-Logs von 2024). Die Panel-Kontrollgruppe erzeugte wie erwartet nur 0x51-Downloads ohne FA.

### Format des Befehls 0x50 (16 Byte, L = 0x1A, Gesamtlänge der FA-Antwort 0x25 = 37 Byte)

| Offset | Bedeutung | Gemessene Werte | Fabians Struct |
|---|---|---|---|
| 0 | Heizung | 0x01 ein, 0x00 aus | `heater_mode` ✓ |
| 1 | Klimaautomatik (Aventa) | 0x02 ein, 0x00 aus (im 0x51-Status: 0x03 / 0x01) | `unknown_01` → **neu: Aventa-Auto-Bit** |
| 2–3 | Soll-Raumtemperatur | Dezikelvin LE, 0x0B5E = 18,0 °C, 0x0B68 = 19,0 °C | `target_temp_room` ✓ |
| 4–5 | – | immer FF FF (im 0x51: FE FF) | `unknown_04` ✓ |
| 6 | Warmwasser | 0x00 aus, 0x64 normal, 0xC8 boost | `water_mode` ✓ |
| 7 | Elektro | 0x00 / 0x0A / 0x14 / 0x1E = 0/1/2/3 kW | `el_mode` ✓ |
| 8 | Gas | 0x00 aus, 0x37 ein | `gas_mode` ✓ |
| 9 | Priorität | 0x01 (Gas) | `heater_prio` ✓ |
| 10 | – | 0x00 | `unknown_10` ✓ |
| 11 | – | 0x64 | `unknown_11` ✓ |
| 12–14 | – | FF FF FF | `unknown_12..14` ✓ |
| 15 | Bezugs-Zähler | **= Byte 15 (ctr) des zuletzt empfangenen 0x51-Status**, in allen 17 Fällen | `message_counter` – Fabian sendet `+1`, **muss gleich sein** |

Jeder Befehl trägt den kompletten Sollzustand (nicht nur das geänderte Feld); die App spiegelt den letzten 0x51 und ändert ein Feld. Der MSG-Counter im Head (Byte 15 der FA-Nachricht) ist box-eigen und stieg um ≥ 2 pro Befehl (0x02, 0x04, 0x06, 0x08, 0x0B, 0x0E, 0x12, …); das Panel akzeptiert jeden Wert und spiegelt ihn im ACK.

Aventa-Steuerung läuft **über dasselbe 0x50** (Byte 1), kein eigener Nachrichtentyp. Was die App bei „Modus wechseln" sendet (Kühlen/Heizen/Lüfter), ist noch nicht gemessen – am 27.10. nur Klimaautomatik ein/aus.

### Zusatzmessung 15:26–15:30: Nachtmodus (App) und Aventa-Beleuchtung (Panel)

Log: `docs/samples/b1-2026-10-27-nachtmodus-licht.log`.

**Nachtmodus** läuft über einen eigenen Befehl **0x54** (12 Byte, L = 0x1A, Spiegel des Nacht-Status 0x55):

```
0x55 Status vorher:   5E 0B 28 05 68 01 07 07 00 04 FF 02
0x54 "Nacht ein":     5E 0B 28 05 68 01 07 00 00 00 FF 02   ACK 0x0D ctr gleich, Payload 02 FF (!)
0x54 "Nacht aus":     5E 0B 28 05 68 01 07 07 00 00 FF 02   ACK 0x0D ctr gleich, Payload 00 FF
0x55 Status danach:   5E 0B 28 05 68 01 07 07 00 04 FF 03
```

- Byte 7: 0x07 → 0x00 bei „ein", zurück auf 0x07 bei „aus". Byte 9 (0x04 im Status) wird im Befehl als 0x00 gesendet. Byte 11 = Zähler des letzten 0x55 (gleiche Regel wie Byte 15 im 0x50).
- Das ACK auf „ein" hatte Payload `02 FF` statt `00 FF` – Bedeutung unklar (Statuscode?). „Aus" folgte nur 2 s später, daher kein Zwischenstatus; **ob „ein" wirkte, ist nicht belegt** → bei B2 mit ≥ 30 s Abstand wiederholen.
- Fabians `StatusFrameAldeHeaterNight`-Struktur passt in Länge und Lage von Soll/Start/Ende; Byte 7 ist dort noch nicht benannt.

**Aventa-Beleuchtung** (nur am Panel schaltbar, nicht in der App): im Status 0x51 sichtbar, Byte 10 wechselt 0x01 → 0x03 (ein) → 0x01 (aus). Im Befehl 0x50 ist Byte 10 bisher immer 0x00, Byte 1 (Klimaautomatik) ist 0x02 bei Status 0x03 – gleiches Muster „Status = Befehlsbit | 0x01". **Hypothese für B2:** Byte 10 = 0x02 im 0x50 schaltet die Beleuchtung. Ungetestet.

Nicht gemessen (vorerst nicht benötigt): Priorität Gas/Elektro (vermutlich Byte 9 im 0x50), Temperatursensor (vermutlich 0x52 als Spiegel von 0x53).

### Abweichungen Fabian `@alde` → notwendige Patches für B2

| Stelle | Fabian | Gemessen | Patch |
|---|---|---|---|
| `TrumaStatusFrameBuilder.h` `status_frame_create_empty` | `raw[4] = len + 6` → 0x16 | 0x1A | für Alde-Antworten `raw[4] = 0x1A` |
| `TrumaiNetBoxAppAldeStatus.cpp` `create_update_data` | `response_len = 17 + 16 = 33` | 37 (0x25), Rest 0x00 | `response_len = 0x25`, Puffer vorher nullen |
| dito `update_prepare` | `message_counter = data_.message_counter + 1` | gleich dem letzten 0x51-ctr | `+ 1` entfernen |
| `TrumaStructsAlde.h` | `unknown_01` | Aventa-Auto-Bit (0x02) | Feld benennen, Aktion ergänzen |
| Aktionen | nur `action_heater_room` | Heizung ein/aus, WW, Elektro, Gas, Aventa-Auto | fehlende `action_*` implementieren (Vorlagen auskommentiert vorhanden) |
| Init/Identifikation/Heartbeat/PID 0x18 | `03.01.FB`, `03.02.F9`, `03.06.F2.17.46.00.1F.00`, `FE`/`FF` | byteidentisch zur echten Box | keiner |

Die übrigen Panel→Box-Typen (0x0D, 0x15, 0x51, 0x53, 0x55, 0x57) entsprechen Fabians Strukturen; die Geräteliste 0x0C kam im Mitschnitt nicht vor (vermutlich nur beim Box-Start – beim B2-Test beobachten).

### B2-Testplan

1. Patches oben einbauen, `observer_mode: false`, `number`-Entität TARGET_ROOM_TEMPERATURE einkommentieren.
2. **Echte iNet Box vom Splitter abziehen** (beide NAD 0x03), ESP neu starten, Panel in Sichtweite.
3. Log: Init-Sequenz (BA → FA 0x0A → 0x0D), danach Statusfluss 0x51/0x53/… wie im Observer.
4. Soll-Temperatur über ESPHome ändern → erwartet: PID 0x18 = FF, BA, FA 0x50, 0x0D mit gleichem Counter, neues 0x51 mit dem Wert, Panelanzeige folgt.
5. Dann Heizung ein/aus, WW, Elektro, Gas, Aventa-Auto; jede Aktion gegen den Mitschnitt vom 27.10. vergleichen.

---

## 7. Ergebnis B2 (27.10.2026, 15:56) – **Steuerung über den iNet-Bus funktioniert**

Firmware `esphome/alde-inetbox-b2.yaml` (observer_mode: false, Patches aus Abschnitt 6), echte iNet Box abgezogen, ESP seit ~15:52 am Bus. Log: `docs/samples/b2-2026-10-27-erster-test.log` (Mitschnitt 15:52–16:09, Auswertung mit `tools/parse_observer_log.py`).

- Das Panel behandelte den ESP sofort als iNet Box: Heartbeat B9 → F9, Status-Downloads 0x57/0x15/0x51/0x53/0x55 → FB, Identifikation B2 → F2. Statuszähler des Panels begann wieder bei 0x01 (Neu-Registrierung).
- Befehl per API (`tools/esphome_control.py number "Alde Soll-Raumtemperatur" 18.5`) um 15:56:46:

```
15:56:46.827  PID 18  FF …                                   ESP: Update liegt an
15:56:47.255  BA 00 1F 00 1A …                               Panel: READ
15:56:47.264  FA … 54 01 10 50 01 D5 | 01 02 63 0B FF FF 64 00 37 01 00 64 FF FF FF 01   ESP: 0x50, Soll 18,5 °C
15:56:48.311  BB … 54 01 02 0D 01 9A 00 FF                   Panel: ACK, gleicher Counter, OKAY
15:58:34.856  BB 0x51 … 01 02 63 0B … ctr 02                 Panel: Status Soll 18,5 °C
```

- Beobachtung: Status-Byte 1 war nach der Neu-Registrierung 0x02 (vorher 0x01/0x03) – Bit 0 ist also nicht „immer gesetzt", Bedeutung offen; Bit 1 = Klimaautomatik bleibt.
### Befehlssequenz 16:01–16:06 (Aventa nicht am Bus, Klimaautomatik daher ausgelassen)

| Zeit | Befehl (ESP → Panel, 0x50) | Panel-ACK | im nächsten periodischen 0x51 sichtbar |
|---|---|---|---|
| 16:01:30 | Heizung aus (Byte 0 = 00) | 02 OKAY | – (Status erst nach „ein") |
| 16:01:57 | Heizung ein | 03 OKAY | 16:03:22: heater 01 ✓ |
| 16:02:25 | Warmwasser Boost (0xC8) | 04 OKAY | – |
| 16:02:52 | Warmwasser Aus (0x00) | 05 OKAY | – |
| 16:03:20 | Warmwasser Normal (0x64) | 06 OKAY | 16:03:22: water 64 ✓ |
| 16:03:47 | Elektro 1 kW (0x0A) | 07 OKAY | – |
| 16:04:15 | Elektro 2 kW (0x14) | 08 OKAY | 16:04:26: el 14 ✓ (Status kam außerplanmäßig) |
| 16:04:43 | Elektro 3 kW (0x1E) | 09 OKAY | – |
| 16:05:10 | Elektro 0 kW | 0A OKAY | 16:06:26: el 00 ✓ |
| 16:05:38 | Gas aus (0x00) | 0B OKAY | – |
| 16:06:06 | Gas ein (0x37) | 0C OKAY | 16:06:26: gas 37 ✓ |
| 16:06:33 | Soll 18,0 °C | 0D OKAY | 16:08:26: target 18,0 °C ✓ |

Jeder Befehl wurde akzeptiert; Byte 15 lief mit dem Statuszähler mit (04 → 05 → 06 → 07), der Box-eigene MSG-Counter stieg um 1 pro Befehl. Mehrere Befehle zwischen zwei Statusmeldungen bauen aufeinander auf (die Komponente hält den zuletzt gesendeten Sollzustand, bis ein neuer 0x51 kommt).

### Priorität und Nachtmodus 16:22–16:24

| Zeit | Befehl | Panel-ACK | Ergebnis |
|---|---|---|---|
| 16:22:08 | Priorität Elektro (0x50 Byte 9 = 00) | 0E OKAY | – |
| 16:22:42 | Priorität Gas (Byte 9 = 01) | 0F OKAY | 16:22:57: prio 01 ✓ |
| 16:23:13 | Nachtmodus ein (0x54, weekday_end 00) | **10 FAILED 02** | wie bei der echten App abgelehnt; Komponente macht Re-Init: Init 0x0A → Geräteliste 0x0C (1/2 Panel 41DE.01 sw 0.00.04, 2/2 Compact 3020 HE 41DE.30 sw 3.00.02) → voller Status. 0x55 danach unverändert |
| 16:23:46 | Nachtmodus aus (0x54, weekday_end 07) | 01 OKAY | kein sichtbarer Effekt (war aus) |

Fazit Nachtmodus: Die von der App gesendete Kodierung wird vom Panel in beiden Fällen (App und ESP) als ungültig quittiert. Entweder ist „ein" anders kodiert, als am 27.10. gemessen, oder das Panel verlangt weitere Felder. Offen; `action_night_mode` bleibt als Experiment markiert. Nebenbefund: 0x55 Byte 9 war in B1 0x04, in B2 0x00 – Bedeutung unbekannt.

Nebenbefund Re-Init: Der komplette Init-Pfad von Fabians Komponente (0x0A → 0x0C → 0x0D) funktioniert am Alde-Panel; das Panel liefert die Geräteliste als 0x0C mit zwei Einträgen.

### Aventa 16:30–16:34 (Aventa jetzt am Bus, antwortet als NAD 0x02 auf Identifikation)

| Zeit | Befehl (0x50) | Panel-ACK | Status |
|---|---|---|---|
| 16:30:42 | Klimaautomatik ein (Byte 1 = 02) | 02 OKAY | – |
| 16:31:15 | Klimaautomatik aus (Byte 1 = 00) | 03 OKAY | 16:31:54: Byte 1 = 01 ✓ |
| 16:31:48 | **Beleuchtung ein (Byte 10 = 02)** | 04 OKAY | **16:31:54: Byte 10 = 03 ✓ – Licht an** |
| 16:32:20 | Beleuchtung aus (Byte 10 = 00) | 05 OKAY | 16:33:5x: Byte 10 = 01 ✓ |

**Die Aventa-Beleuchtung lässt sich über den iNet-Bus schalten**, obwohl die Truma-App das nicht anbietet (Byte 10, Bit 0x02 im 0x50). Hypothese bestätigt. Sichtprüfung: Licht ging an und wieder aus.

Neue Deutung von Byte 1 im 0x51: Bit 0 = Aventa am Bus (ohne Aventa war Byte 1 = 0x02, mit Aventa 0x01/0x03), Bit 1 = Klimaautomatik. Byte 10 analog: Bit 1 = Beleuchtung, Bit 0 bisher immer gesetzt.

Damit sind alle Felder des 0x50 außer 4–5, 11–14 funktional belegt. Offen bleibt nur der Nachtmodus (0x54).

---

## 8. Heizungswerte passiv aus den Panel↔Heizung-Frames (27.10.2026)

An der iNet-Buchse sind nicht nur die Box-Abfragen (PID 0x18, 0x3C, 0x3D) sichtbar, sondern auch die Signal-Frames des festen Zeitrasters zwischen Panel und Heizung. Fabians Komponente speichert sie als `Heater_Alde_PID_xx`; die Dekodierung stammt von [Mellowgroup-dk/alde-3020he-lin](https://github.com/Mellowgroup-dk/alde-3020he-lin) (deren IDs tragen die LIN-Paritätsbits: 0x47→0x07, 0x5B→0x1B, 0xD3→0x13, 0xC4→0x04, 0x85→0x05, 0x97→0x17) und wurde gegen die Mitschnitte vom 27.10. geprüft.

| PID | Byte | Wert | Umrechnung | Prüfung im Mitschnitt |
|---|---|---|---|---|
| 0x07 | 0–1 | Raumtemperatur (Panel-Sensor), **im Sekundentakt** | Dezikelvin: (raw−2730)/10 | `62 0B` = 18,4 °C, Stufen 18,4–18,7 |
| 0x1B | 0–1 | Glykol-/Kesseltemperatur | Dezikelvin | 45 → 48 °C während Brennerlauf |
| 0x1B | 2–3 | Netzstrom gesamt | (raw & 0x7FFF)/100 A, 0x7FFF = kein Landstrom | immer `FF 7F` (kein Landstrom) |
| 0x1B | 6 | Brennerlüfter | raw × 32 U/min, 0 = Brenner aus | 0x40–0x63 = 2048–3168 U/min 14:57–15:00 |
| 0x13 | 0–1 | Platinentemperatur | Dezikelvin | 39–43 °C |
| 0x04 | 0–1 | Warmwasser-Soll | Dezikelvin; 0,0 aus / 50,0 normal / 65,0 Boost | passt zu Aktion 4 |
| 0x06 | 0–1 | Erlaubte Elektroleistung | u16 W | 0 / 1000 / 2000 / 3000 bei Aktion 5 |
| 0x15 | 0–1 | Tatsächliche Elektroleistung | u16 W | 0 (kein Landstrom) |
| 0x05 | 0 | **Aktive Energiequelle** | 0x00 keine, 0x01 Gas, 0x02 Elektro | 12 Wechsel, alle deckungsgleich mit den Aktionszeiten (Mellowgroup nennt 02/04, hier anders) |
| 0x17 | 0–1 | Klima-interner Sensor | Dezikelvin | 18,2–18,3 °C |
| 0x17 | 2–3 | Klima-Zieltemperatur | Dezikelvin, 22,0 = Ruhe-Default | 22,0 / 18,0 |
| 0x17 | 5 | Kompressor-Flag | 0x05 / 0x00 | nur 0x00 gesehen |
| 0x17 | 6 | Aventa-Beleuchtung | % | 0x64 = 100 % beim Lichttest |
| 0x08 | 0–1 | Spiegel von 0x17 Byte 2–3 | – | – |
| 0x03 | 0–1 | Heizbefehl des Panels (= Soll, solange Klima ruht) | Dezikelvin | 18,0 / 19,0 |

Nicht auf diesem Bus gesehen: Mellowgroups Frame 0xD6 (Wassertemperatur, Batteriespannung) und ein explizites Ventil- oder Fehlersignal. Hinweis auf Brennerbetrieb: Lüfter > 0 plus steigende Glykoltemperatur; zusammen mit „Energiequelle = Gas" eine brauchbare indirekte Gasausfall-Erkennung.

Umsetzung: Getter `get_alde_pid_xx()` und `get_alde_heater_frame_age_ms()` in `TrumaiNetBoxApp`, Template-Sensoren in `esphome/alde-inetbox-b2.yaml` (Abschnitt „Heizungs-Frames"). Werte werden nur veröffentlicht, wenn der letzte Heizungsframe jünger als 30 s ist.
