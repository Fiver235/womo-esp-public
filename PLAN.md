# Plan: Eigener Ersatz für die Truma iNet Box (Alde 3020 HE + Aventa comfort)

> **Stand 27.10.2026:** Track B2 funktioniert (siehe `docs/TRACK-B-INET-BUS.md` Abschnitt 7): der ESP32 ersetzt die iNet Box am Alde-Panel und steuert Soll, Heizung, Warmwasser, Elektro, Gas, Priorität, Klimaautomatik und sogar die Aventa-Beleuchtung. Fernzugriff per WireGuard-Tunnel vom ESP zur heimischen Fritzbox (`esphome/README.md`, Abschnitt Fernzugriff). Offen: Nachtmodus-Kodierung, Gasflaschen-Sensoren (LevelControl, siehe unten).


Stand: 2026-10-16 · Rechercheergebnis + Umsetzungsplan

---

## 1. Ausgangslage und Ziel

**Installation im Womo**

| Komponente | Rolle |
|---|---|
| Alde Compact 3020 HE + Alde-Bedienteil (Touchpanel 3020-113, „iNet ready") | Warmwasserheizung; das Bedienteil ist der **Bus-Master** |
| Truma Aventa comfort | Dachklimaanlage, hängt am selben TIN-Bus, wird vom Alde-Panel mitgesteuert (ACC) |
| Truma iNet Box | Gateway Bus ↔ Bluetooth/GSM(SMS) für die Truma-App |
| WLAN-Router im Womo | vorhanden, soll die Anbindung übernehmen |

**Ziel:** iNet Box entfernen, durch ein eigenes Gerät ersetzen, das

1. sich mit dem Womo-WLAN verbindet,
2. **Pflicht:** die Alde remote steuert – Ein/Aus, Soll-Raumtemperatur, Warmwasser, Gas/Strom-Leistung – und ihren Status liefert (Temperaturen, Betriebszustand, Fehler),
3. möglichst auch die Aventa fernsteuert,
4. ohne Cloud/SIM auskommt (iNet X ist ausgeschlossen).

**Wunsch:** Die Alde-Steuerung soll, wenn irgend möglich, **über den iNet-/TIN-Bus** laufen (d. h. echte iNet-Box-Emulation statt Umweg über JP3). Das ist nach heutigem Stand ungelöst (siehe Abschnitt 2) und wird als **Track B** (Forschung) geführt; **Track A** (JP3) sichert die Pflichtanforderung ab.

---

## 2. Rechercheergebnis: Der „iNet-Bus" (TIN-Bus)

**Physik / Transport**

- TIN-Bus = **LIN-Bus** (Single-Wire, 12 V, 9600 Baud, 8N2). Kein proprietäres Bussystem.
- Stecker: RJ12 (6P6C). Belegung laut Community: **Pin 3 = LIN, Pin 5 = GND**. Truma-TIN-Kabel sind 6-adrig; am RJ12 liegen **keine 12 V** an → eigene Stromversorgung nötig.
- Transceiver: TJA1020 (Standard in allen Projekten), alternativ MCP2003/MCP2025. Funktioniert mit 3,3-V-Logik (ESP32) ohne Pegelwandler.
- Checksumme: LIN 2.x „enhanced" für Signal-Frames, „classic" für Diagnose-Frames 0x3C/0x3D.
- Nur **ein** Master pro Bus. Truma: CP Plus ist Master. Alde: das Alde-Bedienteil ist Master (ohne Panel = Funkstille).

**Truma-Protokoll (Combi + CP Plus) – vollständig reverse-engineered**

- PID 0x18: Flag „iNet Box hat Änderung" · PIDs 0x20–0x22: Statusframes · 0x3C/0x3D: Transportlayer (Diagnose).
- SIDs: 0xB0 Assign NAD, 0xB9 Heartbeat, 0xBA Upload (Box→Panel), 0xBB Download (Panel→Box).
- Statuspuffer mit 10-Byte-Präambel + Typ-ID (z. B. 0x14/0x33 vom Panel, 0x0C/0x32 von der Box).
- Ablauf einer Steuerung: Box setzt Flag → Panel pollt → Box sendet Statuspuffer → Panel quittiert. Vorher schickt das Panel eine **Geräteliste** (Typ 0x0B via 0xBB), auf die alle Emulatoren warten.
- CP Plus braucht Firmware ≥ C4.00.00; Emulation nur, wenn **keine echte iNet Box** am Bus hängt.

**Alde-3020-HE-Protokoll – Stand 2026 (Mellowgroup-dk/alde-3020he-lin, inetbox.py #28, esphome-truma_inetbox #22/#53)**

- Fester 11-Slot-Schedule, 388 ms Zyklus. Frames: `03` Soll (Dezi-Kelvin), `C4` Warmwasser-Soll, `85` Gas ein/aus, `06` erlaubte el. Leistung, `47` Raumtemp, `08`/`97` Klima-Status (Kompressor, Licht, Soll), `D3` PCB-Temp, `55` angelegte el. Leistung, `D6` Wassertemp + Batterie, `5B` Glykoltemp + Netzstrom + Brennerlüfter.
- Slaves: NAD 1 = Boiler (Supplier 0x4617 = Truma, Function 0x0330 „Alde System"), **NAD 2 = Klimaanlage (Function 0x0C00)** – d. h. die Aventa ist ein normaler LIN-Slave des Alde-Panels.
- Eine iNet-Box-Emulation wird vom Alde-Panel **registriert und alle 1,34 s gepollt** (Panel zeigt „Truma iNet Box"), aber: Alde sendet **nie die Geräteliste**, an deren Stelle steht ein ASCII-Revisionsstring („R029"); Company-Code 0x1A statt 0x1E; angeforderte Länge 37 statt 41 Byte. Neun Varianten korrekt geformter Statuspuffer → **keine Wirkung**. Anwendungsschicht ist Alde-eigen und undecodiert.
- **Lesen funktioniert (13 Felder verifiziert), Steuern über den TIN-Bus ist bis heute nicht gelöst.**

**Der zweite Weg: JP3 „3rd Party Panel" (External Panel Port) am Alde-Bedienteil**

- Das Alde-Panel hat einen separaten Anschluss **JP3** für ein Fremdbedienteil (Alde Smart Control, CBE, Nordelettronica …). Im Panel-Menü „Installed Accessories" → „Third Party Panel" aktivieren; Fehlermeldung „3rd Party Panel C. Fail" bei Kabelbruch.
- Das ist ein **eigener LIN-Bus** (gelber Stecker „C1"/„External panel"), getrennt vom roten TIN-Bus. Das Fremdbedienteil ist hier **Master**, das Alde-Panel antwortet.
- Protokoll (holdestmade/esphome-alde-3020): Control-Frame **ID 0x1A** (8 Byte: Zone-1/2-Soll, Gas, el. Leistung 0/1/2/3 kW, Panel ein/aus, Warmwasser-Modus, AC-Auto), Info-Frame **ID 0x1B** (Temperaturen, Pumpe, Fehler, Gasventil, AC-Power). Polling alle 0,5–2 s. Status August 2026: „it works ok" (HBK1, esphome-truma_inetbox #53).
- Einschränkung: der Port unterstützt **nur ein** Fremdgerät. Hängt dort schon ein Hersteller-Panel (z. B. CBE), muss man sich entscheiden oder zwischen beiden umschalten.

---

## 3. Bestehende Open-Source-Projekte

| Projekt | Plattform | Truma Combi | Aventa | Alde 3020 HE | Bemerkung |
|---|---|---|---|---|---|
| danielfett/inetbox.py | Raspberry Pi, Python, MQTT | ✅ | – | nur lesen | Referenzimplementierung, gut dokumentiert |
| mc0110/inetbox2mqtt | ESP32 / Pico W, MicroPython, MQTT + HA-Discovery, Web-UI | ✅ | ✅ (über CP Plus) | ❌ | reif, viele Nutzer |
| Fabian-Schmidt/esphome-truma_inetbox | ESPHome | ✅ | teilweise | experimenteller `alde`-Branch, nur lesen | exzellenter LIN-Slave-Code |
| havanti/esphome-truma | ESPHome (ESP-IDF) | ✅ | ✅ Gen 2 (über CP Plus) | ❌ | aktiver Fork, Cooler/TPMS extra |
| **Mellowgroup-dk/alde-3020he-lin** | ESPHome, nur empfangen | – | Status mitlesen | ✅ **lesen** | sauber dokumentiert, Rohmitschnitte, CONTROL-NOT-SOLVED.md |
| **holdestmade/esphome-alde-3020** | ESPHome, LIN-Master an JP3 | – | nur „AC Auto" | ✅ **steuern** | funktioniert laut Nutzern, offene Issues zu Timing/Checksumme |

Fazit: Für die Truma-Welt existiert alles fertig. Für dein Alde-System gibt es **keine Lösung, die die iNet Box 1:1 emuliert** – aber die Kombination aus zwei Projekten deckt das Ziel ab.

---

## 4. Lösungsarchitektur (Empfehlung)

```
                    ┌──────────────── Womo-WLAN ────────────────┐
                    │                                           │
   Handy/Laptop ──► Router ──► ESP32-Gateway (ESPHome)          │
   (lokal/VPN)                    │  LIN-A (Slave, nur lesen)   │
                                  │  LIN-B (Master, steuern)    │
                                  │  optional IR-LED            │
                                  │                             │
        TIN-Bus (rot) ◄───────────┘  │                          │
   ┌──────┴──────┬────────────┐      │                          │
Alde-Panel    Alde 3020 HE  Aventa   │                          │
 (Master)      (NAD 1)      (NAD 2)  │                          │
   │                                 │                          │
   └── JP3 „External Panel" ◄────────┘                          │
```

**Umsetzung im Repo:** `esphome/alde-gateway.yaml` (Node) + `esphome/packages/tin_reader.yaml` (LIN-A, Mellowgroup-Mitleser) + `esphome/packages/jp3_control.yaml` (LIN-B, holdestmade-Komponente). Pins: LIN-A GPIO17/16 (9600 8N2), LIN-B GPIO27/26 (19200 8N1), Framework ESP-IDF.

**Ein ESP32, zwei LIN-Transceiver:**

| Kanal | Anschluss | Rolle | Liefert |
|---|---|---|---|
| **LIN-A** | TIN-Bus (RJ12-Splitter am „Control panel"-Anschluss des Boilers – da, wo die iNet Box hing) | passiver Slave/Sniffer, **schreibt nie** | alle 13 Boiler-Werte, Aventa-Status (Kompressor, Soll, Licht), Batteriespannung |
| **LIN-B** | JP3 am Alde-Bedienteil | LIN-Master („3rd Party Panel") | Soll-Temperatur, Ein/Aus, Gas, el. Leistung, Warmwasser-Modus, AC-Auto |

**Software:** ESPHome (beide Komponenten existieren als ESPHome-Komponenten; ESPHome kann zwei UARTs parallel). Anbindung wahlweise

- **Home Assistant** (du hast HA im Einsatz) → native API, Climate-Entities, Dashboard, Automationen; oder
- **standalone**: ESPHome-Web-Server auf dem ESP32 + MQTT – braucht keinen HA im Womo.

**Fernzugriff** (Ersatz für die App): lokal per WLAN, von unterwegs per VPN/Tailscale/WireGuard auf dem Router oder HA-Companion-App.

**Aventa – drei Optionen, gestaffelt:**

1. **ACC über JP3** („AC Auto Mode"): Alde-Panel regelt Klima automatisch nach Raum-Soll. Sofort verfügbar, aber kein manueller Kühl-/Lüfter-Modus.
2. **IR-Fernbedienung nachbilden**: Die Aventa comfort wird ab Werk mit einer IR-Fernbedienung bedient. Ein IR-LED am ESP32 (ESPHome `remote_transmitter`) kann die Codes senden → voller manueller Zugriff (Modus, Soll, Lüfterstufe, Timer), komplett unabhängig vom Bus. Codes einmal mit einem IR-Empfänger aufzeichnen. Rückmeldung kommt über LIN-A.
3. **Aventa-Felder im JP3-Protokoll suchen**: unbekannt, ob 0x1A mehr als AC-Auto transportiert – nur als Forschungsthema.

---

### Track B – Alde-Steuerung direkt über den TIN-Bus (Forschung) → Details in [docs/TRACK-B-INET-BUS.md](docs/TRACK-B-INET-BUS.md)

**Neubewertung nach Online-Recherche (16.10.2026):** Die Community-These „Alde sendet keine Geräteliste und quittiert nichts" ist widerlegt. Fabian Schmidts `alde`-Branch enthält echte Alde-3020-HE-Mitschnitte: Das Panel sendet eine Geräteliste als Typ **0x0C** (Truma: 0x0B), quittiert Nachrichten der Box mit **0x0D** (gleicher Mechanismus wie bei Truma, verifiziert an einem echten iNet-Box-Mitschnitt aus WomoLIN) und liefert den Hauptstatus als Typ **0x51** (28 Byte, vollständig dekodiert: Ein/Aus, Soll, Warmwasser, kW, Gas, Priorität, Innen-/Außentemperatur). Die Länge steht bei Alde im 5. Header-Byte (len+6). Der Befehlspuffer ist nach Truma-Konvention Typ **0x50** – Fabian hat ihn implementiert, aber **niemand hat ihn je korrekt getestet** (der einzige Test lief vor der 0x0C-Erkennung). Mellowgroup wartete auf 0x0B und schickte Truma-Befehlstypen – darum „keine Wirkung".

**Was du anders hast:** eine funktionierende iNet Box am Alde-Panel. Damit lässt sich der **echte Steuerdialog mitschneiden** – dann ist das Format von 0x50 (oder was immer die Box sendet) kein Rätsel mehr. Firmware dafür: `esphome/alde-inetbus-observer.yaml` (Fabian `@alde`, `observer_mode: true`, sendet nichts).

**Vorgehen (baut auf Phase 1 auf, kein zusätzliches Risiko, nur mitlesen):**

1. Sniffer (LIN-A) läuft, **iNet Box bleibt angeschlossen**, Truma-App per Bluetooth verbunden.
2. Ruhebild aufzeichnen (SEQUENCE-Recorder + TP-Hexdumps im Log, ≥ 2 Minuten ohne Bedienung).
3. Gezielte Einzelaktionen aus der **App** auslösen, jeweils mit Zeitstempel notieren: Soll +1 °C, Soll −1 °C, Heizung aus, Heizung ein, Warmwasser-Modus wechseln, el. Leistung 1→2 kW, Aventa ein/aus.
4. Dieselben Aktionen **am Panel** auslösen (Vergleich: welche Frames ändern sich, welche nicht).
5. Auswertung: Welche 0x3C/0x3D-Transportmeldungen (SID 0xBA/0xBB, NAD der iNet Box) gehen vor der Zustandsänderung über den Bus? Welche Puffer-Typ-IDs, welche Länge (37 Byte?), wo stehen Soll/Modus? Gibt es einen Quittungs-Frame vom Panel?
6. Nachbau in einem eigenen ESPHome-Komponenten-Fork (Basis: Fabian-Schmidt-LIN-Slave-Code, Alde-Header 0x1A, Längen aus dem Mitschnitt). Erst im Labor mit Logging, dann am Fahrzeug – **immer mit abgezogener JP3-Steuerung und nie als zweiter Master**.
7. Ergebnis zurück an die Community (Mellowgroup-Repo / esphome-truma_inetbox #53) – die warten genau auf so einen Mitschnitt.

**Erfolgsaussicht:** **gut.** Die Transport- und Statusschicht ist dekodiert, der Quittungsmechanismus nachgewiesen, ein konkreter Befehlskandidat (0x50) liegt implementiert vor; der Mitschnitt mit deiner echten iNet Box liefert das akzeptierte Format zwingend. Aufwand: 1–2 Abende Messen, 1 Abend Auswertung, dann Anpassung von Fabians Branch. Wenn Track B gelingt, kann LIN-B/JP3 entfallen und das Gerät ist ein echter 1:1-Ersatz der iNet Box (inkl. Aventa, falls die Box dafür eigene Puffer sendet – Messschritt 7).

**Zwei Teilschritte:**
- **B1 (ohne Risiko):** Observer-Firmware, echte iNet Box dran, Messprotokoll aus dem Dossier abarbeiten.
- **B2 (Experiment):** iNet Box abklemmen, `observer_mode: false`, 0x50-Befehl senden (Fabians Branch), Erfolg = 0x0D-ACK mit gleichem Counter + geändertes 0x51 + Panelanzeige. Falls B1 ein anderes Format zeigt, zuerst Branch anpassen.

**Hinweis zur App:** Prüfen, ob die Truma-App die iNet Box (Bluetooth) noch bedient. Falls die App nicht mehr geht, bleibt SMS-Steuerung der iNet Box als Auslöser.

---

## 5. Hardware-Stückliste (Prototyp)

| Teil | Hinweis | ca. Preis |
|---|---|---|
| ESP32-WROOM-32 DevKit (oder ESP32-S3 N16R8) | 3 UARTs; S3: GPIO16/17 nicht nutzbar (PSRAM) | 8–15 € |
| 2 × LIN-Transceiver-Breakout TJA1020 (oder MCP2003/MCP2025) | RXD open-drain → Pull-up 3,3 V; NSLP auf High | 2 × 5–10 € |
| RJ12-6P6C-Splitter + 6-adriges Kabel (echtes 6P6C, nicht 4-adrig Telefon) | TIN-Bus-Abgriff | 5 € |
| Stecker/Kabel für JP3 | Alde-Originalkabel „External panel" bzw. Gegenstück prüfen (Phase 0) | 5–15 € |
| DC/DC 12 V → 5 V (z. B. Mini-Buck, ≥1 A) | ESP32 + Transceiver vom Bordnetz; GND **unbedingt** gemeinsam | 3 € |
| optional: IR-LED + Transistor, IR-Empfänger (TSOP38238) | für Aventa-Option 2 | 3 € |
| Gehäuse, Sicherung 1 A im 12-V-Zweig | | 5 € |

Alternative zum Selbstlöten: fertige ESP32-LIN-Boards (ehemals „WoMoLin lin-controller"; die Firma heißt heute WomoNET – prüfen, ob die Einzelboards noch erhältlich sind).

Konkrete Amazon-Bestellliste für B1/B2 mit Links und Preisen: [docs/BESTELLLISTE.md](docs/BESTELLLISTE.md).

---

## 6. Umsetzungsplan in Phasen

### Phase 0 – Bestandsaufnahme (ohne Eingriff, 1 Abend)
- [ ] Panel-Teilenummer (3020-113?) und Firmware-/Revisionsstring im Alde-Service-Menü notieren.
- [ ] Fotos: Rückseite Alde-Panel (JP3 belegt? gelber Stecker?), Boiler-Platine (TIN-Bus-Buchsen), iNet Box (was steckt an TIN-1/TIN-2?).
- [ ] Prüfen, ob bereits ein Fremdbedienteil an JP3 hängt („Installed Accessories" → „Third Party Panel" aktiv?).
- [ ] Aventa: Generation/Baujahr (Typenschild), IR-Fernbedienung vorhanden?
- [ ] Router: fester Hostname/IP möglich, VPN-Fähigkeit.

### Phase 1 – Nur lesen am TIN-Bus (risikofrei)
- [ ] ESP32 + Transceiver A aufbauen, ESPHome mit `Mellowgroup-dk/alde-3020he-lin` (`esphome/alde-lin-reader.yaml`) flashen.
- [ ] RJ12-Splitter setzen, iNet Box bleibt vorerst dran.
- [ ] Verifizieren: Soll/Ist-Raumtemp, Warmwasser, Gas, el. Leistung, Aventa-Status gegen Panel-Anzeige.
- [ ] Eigenen Mitschnitt sichern (später wertvoll).

### Phase 1b – Track B1: Mitschnitt mit echter iNet Box (parallel zu Phase 1)
- [ ] `esphome/alde-inetbus-observer.yaml` flashen (observer_mode, sendet nichts), iNet Box bleibt dran.
- [ ] Messprotokoll aus `docs/TRACK-B-INET-BUS.md` Abschnitt 4 abarbeiten (Ruhe, App-Aktionen 1–7, Panel-Kontrollgruppe), Logs mit Zeitstempel sichern.
- [ ] Auswertung mit `python tools/parse_observer_log.py <log> --csv …`: Box→Panel-Befehle (Typ, len, L, Counter, Payload-Diff), 0x0D-ACK-Zuordnung.
- [ ] Abgleich mit Fabians 0x50-Struktur; Aventa-Befehle identifizieren.

### Phase 2b – Track B2: Befehl senden (Experiment)
- [ ] iNet Box abklemmen, `observer_mode: false`, number-Entität aktivieren; Soll ±1 °C senden.
- [ ] Erfolg: 0x0D-ACK mit Befehls-Counter + neues 0x51 mit neuem Wert + Panelanzeige. Sonst Format aus B1 in Fork übernehmen.
- [ ] Bei Erfolg: climate/select/switch für Alde im Fork ergänzen, Ergebnis an esphome-truma_inetbox #53 melden.

### Phase 2 – Steuern über JP3 (Track A)
- [ ] iNet Box abklemmen (rote Fehlermeldung im Panel einmalig im Service-Menü löschen).
- [ ] Transceiver B an JP3, `holdestmade/esphome-alde-3020` als zweite Komponente in dieselbe ESPHome-Config (eigener UART).
- [ ] Im Panel „Third Party Panel" aktivieren.
- [ ] Polling-Intervall konservativ (2000 ms, siehe Issue #14), Checksummen-Modus beobachten (Auto-Erkennung enhanced/classic).
- [ ] Testmatrix: Soll ±1 °C, Panel Ein/Aus, el. Leistung 0→1→2 kW, Warmwasser normal/boost – jeweils Rückmeldung über LIN-A prüfen.

### Phase 3 – Integration & Bedienoberfläche
- [ ] HA: Climate-Entity (Soll aus JP3, Ist aus TIN-Sniffer zusammenführen via Template-Climate), Dashboard-Karte, Benachrichtigung bei Fehler/Low Battery.
- [ ] Ohne HA: ESPHome-Webserver + MQTT, einfache Web-App.
- [ ] Fernzugriff einrichten (VPN auf Router oder Tailscale).

### Phase 4 – Aventa manuell
- [ ] IR-Codes der Aventa-Fernbedienung aufzeichnen, `remote_transmitter` einbinden, Status-Rückkopplung aus LIN-A (0x97/0x08).

### Phase 5 – Härtung
- [ ] Watchdog, Reconnect-Logik, Failsafe: bei WLAN-/Bus-Verlust keine Zustandsänderung senden.
- [ ] Verhalten bei Spannungseinbruch (Boiler-Brownout < 10,5 V) prüfen.
- [ ] Dokumentation (Pinout, Config, Wiederherstellung des Originalzustands).

---

## 7. Risiken

| Risiko | Einschätzung | Gegenmaßnahme |
|---|---|---|
| Zwei Master auf dem TIN-Bus | ernst (Gasheizung) | LIN-A ist konstruktiv **nur Empfänger** |
| JP3 schon belegt | mittel | Phase 0 klärt; ggf. Umschalter oder Verzicht |
| holdestmade-Komponente nur mit 3020 (nicht HE) getestet | mittel | Phase-2-Testmatrix; Frame-IDs/Checksumme ggf. anpassen; Rohlog führen |
| Aventa nur ACC statt manuell | niedrig | IR-Weg als Fallback |
| iNet-Box-Fehlermeldung im Panel | niedrig | einmalig im Service-Menü quittieren, Box ggf. als „nicht installiert" setzen |
| Kein 12 V am RJ12 | – | separate Versorgung + gemeinsamer GND |

---

## 8. Offene Fragen (für Phase 0)

1. Hängt an JP3 des Alde-Panels bereits etwas (CBE/Nordelettronica-Panel, Smart Control)?
2. Welche Alde-Panel-Revision (Service-Menü)? Welches Aventa-Baujahr?
3. Soll das Gerät ohne Home Assistant laufen (standalone Web/MQTT) oder in dein HA integriert werden?
4. Wie wichtig ist manueller Aventa-Betrieb (Kühlen/Lüften) gegenüber ACC?

---

## 9. Quellen

- inetbox.py (Protokollbeschreibung, RJ12-Pinout): https://github.com/danielfett/inetbox.py · Alde-Thread: https://github.com/danielfett/inetbox.py/issues/28
- inetbox2mqtt: https://github.com/mc0110/inetbox2mqtt · Verkabelung: https://github.com/mc0110/inetbox2mqtt/blob/main/doc/ELECTRIC.md
- esphome-truma_inetbox: https://github.com/Fabian-Schmidt/esphome-truma_inetbox · Alde-Issues: https://github.com/Fabian-Schmidt/esphome-truma_inetbox/issues/22 und https://github.com/Fabian-Schmidt/esphome-truma_inetbox/issues/53
- havanti/esphome-truma (Aventa Gen 2 über CP Plus): https://github.com/havanti/esphome-truma
- Alde 3020 HE LIN-Decodierung (lesen): https://github.com/Mellowgroup-dk/alde-3020he-lin (docs/PROTOCOL.md, docs/CONTROL-NOT-SOLVED.md)
- Alde 3020 Steuerung über JP3: https://github.com/holdestmade/esphome-alde-3020 · Issue #14: https://github.com/holdestmade/esphome-alde-3020/issues/14
- Alde-Handbuch 3020 HE (Installed Accessories / JP3, Fehlermeldungen, Verschaltung): https://www.manualslib.com/manual/912383/Alde-Compact-3020-He.html (S. 35, 38, 41) · Installationsanleitung: https://www.alde.co.uk/wp-content/uploads/2019/08/alde_3020_install.pdf
- Alde iNet-ready-Panel: https://en.alde.se/service-support/control-panels/alde-compact-3020-control-panel-inet-ready/
- Truma iNet-X-Kompatibilitätsliste (Serien-/Softwarestände): https://www.truma.com/gb/compability-inet-x-system
- Truma iNet Box Installationsanleitung: https://www.manualslib.com/manual/2158076/Truma-Inet-Box.html
- Smart-Control-Einbau an „External panel": https://www.practicalmotorhome.com/advice/how-to-fit-smart-control-for-aldes-3020-heating
- HA-Community-Thread Truma/Alde: https://community.home-assistant.io/t/truma-alde-motorhome-rv-integration/178409
- TJA1020 am ESP32: https://www.mikrocontroller.net/topic/583322

- **LevelControl-Gassensoren (27.10.2026):** weiterverwendbar über die HA-Integration von cyclemat plus zweiten ESP32 als Bluetooth-Proxy mit WireGuard, siehe [docs/LEVELCONTROL.md](docs/LEVELCONTROL.md). Config `esphome/womo-ble-proxy.yaml` kompiliert, noch nicht geflasht.
