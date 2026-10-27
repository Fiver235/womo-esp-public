# Verdrahtung Track B1/B2 mit dem LIN-Modul „FST T151"

Stand 26.10.2026. Gilt für B1 (nur mitlesen) **und** B2 (als iNet-Box-Slave senden) – die Verdrahtung ist identisch, B1 nutzt die TX-Leitung nur nicht.

## Was das „FST T151" ist

„FST T151" ist der Platinenaufdruck der generischen **TTL-UART-zu-LIN-Module mit TJA1020** (Amazon: Gutol B0G1G75NY3, AILOVA/MEROURII B0895WQ5VM, DONGKER B0HC67CFCG – alle dieselbe Platine, unterschiedliche Verkäufer). Es ist genau das Modul, das inetbox.py und inetbox2mqtt in ihrer Doku verwenden. Chip: NXP TJA1020, Versorgung 12 V, UART-Seite 3,3-V-tauglich (RXD ist Open-Drain mit Pull-up auf dem Board), Break-Erzeugung macht der ESP32 per UART.

Stiftleiste (7 Pins, Beschriftung kann je nach Charge leicht abweichen – **vor dem Anschluss am Aufdruck prüfen**):

| Aufdruck | Bedeutung | Anmerkung |
|---|---|---|
| `12V` (auch `VBAT`/`VCC`) | Versorgung Transceiver | 8–18 V, aus dem Bordnetz, **abgesichert** |
| `GND` | Masse | manche Boards haben zwei GND-Pins (UART-Seite / Bus-Seite); beide sind verbunden |
| `TX` (auch `TXD`) | **Ausgang** des Moduls = empfangene Busdaten | → ESP32 **RX** |
| `RX` (auch `RXD`) | **Eingang** des Moduls = zu sendende Daten | ← ESP32 **TX** |
| `LIN` | Busleitung | → TIN-Bus Pin 3 |
| `INH` | Inhibit-Ausgang des TJA1020 | **frei lassen** |
| `SLP` (auch `NSLP`) | Sleep-Eingang, aktiv low | normalerweise auf dem Board hochgezogen → frei lassen; bei Empfangsproblemen fest auf **3,3 V** legen |

Die Richtung von TX/RX ist aus Sicht des Moduls gemeint. Das ist der häufigste Fehler: kommt nichts an, TX und RX am ESP32 tauschen.

## Komplette Verdrahtung

```
 Bordnetz 12 V ──[Sicherung 2 A]──┬──────────────────────────────► FST T151  12V
                                  │
                                  └──► MP1584 Step-Down IN+   OUT+ (5,0 V) ──► ESP32  5V/VIN
 Bordnetz GND ────────────────────┬──► MP1584 IN−   OUT− ────────────────────► ESP32  GND
                                  │
                                  ├──────────────────────────────────────────► FST T151  GND
                                  │
                                  └──► TIN-Bus RJ12 Pin 5 (GND)   (über Schraubklemmen-Adapter)

 TIN-Bus RJ12 Pin 3 (LIN) ──────────────────────────────────────────────────► FST T151  LIN

 FST T151  TX  ────────────────────────────────────────────────────────────► ESP32  GPIO16 (UART2 RX)
 FST T151  RX  ◄────────────────────────────────────────────────────────────  ESP32  GPIO17 (UART2 TX)
 FST T151  INH   – frei –
 FST T151  SLP   – frei –   (Fallback: ──► ESP32 3V3)
```

Reihenfolge Bus-Seite: Boiler-TIN-Buchse → **RJ12-Splitter** (Buchse 1: iNet Box, Buchse 2: Sniffer) → **RJ12-Kabel 6-adrig 1:1** → **RJ12-Buchse-auf-Schraubklemmen-Adapter** → Klemme 3 = LIN, Klemme 5 = GND.

### Pin-für-Pin-Tabelle

| Von | Nach | Kabel |
|---|---|---|
| Bordnetz + (z. B. Zuleitung iNet Box, WAGO-Abzweig) | Sicherungshalter → FST `12V` **und** MP1584 `IN+` | rot |
| Bordnetz − | MP1584 `IN−`, FST `GND`, ESP32 `GND`, RJ12-Klemme 5 | schwarz – **ein gemeinsamer Massepunkt** |
| MP1584 `OUT+` (auf 5,0 V eingestellt) | ESP32 `5V`/`VIN` | rot |
| MP1584 `OUT−` | ESP32 `GND` | schwarz |
| RJ12-Klemme 3 (LIN) | FST `LIN` | beliebig, kurz halten |
| FST `TX` | ESP32 `GPIO16` | F/F-Jumper |
| FST `RX` | ESP32 `GPIO17` | F/F-Jumper |
| FST `INH`, `SLP` | – | – |

Alternative für den reinen B1-Labortest: ESP32 per USB vom Laptop versorgen, MP1584 entfällt. **GND zwischen ESP32, FST und Fahrzeug muss trotzdem verbunden sein**, sonst kommt nichts an.

### ESP32-Schraubklemmen-Breakout (DT-Y6549)

Die Klemmen sind 1:1 die Pins des DevKits. Belegung der Stromversorgung (Kontrolle 27.10.2026 anhand Fotos):

| Klemme | Bedeutung | Anschluss |
|---|---|---|
| `V5` (ganz links, obere Reihe) | VIN, 5 V Eingang des Onboard-Reglers | MP1584 `OUT+` (5,0 V) |
| `GND` (obere Reihe zwischen `P13` und `P12`, untere Reihe neben `P19` und ganz rechts) | Masse | MP1584 `OUT−` |
| `CMD`, `CLK`, `SD0`–`SD3` | SPI-Flash des Moduls | **nie belegen** – auf GND gelegt bootet der ESP32 nicht |
| `P16` / `P17` (untere Reihe zwischen `P4` und `P5`, Beschriftung liegt unter den Steckern) | GPIO16 RX / GPIO17 TX | FST `TX` / FST `RX` |

Vor dem ersten Einschalten: MP1584 `OUT` ohne Last auf 5,0 V stellen und die Polarität der Ausgangsleitungen mit dem Multimeter prüfen – die Mini-Module sind oft nur auf der Unterseite beschriftet.

## Zuordnung zu den ESPHome-Configs

| Config | UART | Pins | Modus |
|---|---|---|---|
| `esphome/alde-inetbus-observer.yaml` (B1) | `lin_uart_bus`, 9600 8N2 | TX GPIO17 / RX GPIO16 | `observer_mode: true` – sendet nichts |
| dieselbe Datei (B2) | dito | dito | `observer_mode: false` – antwortet als Slave (PID 0x18, Heartbeat, 0x3D), iNet Box **abklemmen** |
| `esphome/packages/tin_reader.yaml` (LIN-A im Gateway) | `tin_uart`, 9600 8N2 | TX GPIO17 / RX GPIO16 | nur lesen |

Die Pinbelegung GPIO16/17 ist in allen drei Configs gleich, das Modul muss zwischen B1, B2 und dem späteren Gateway nicht umgesteckt werden.

## Inbetriebnahme-Check

1. MP1584 ohne Last auf 5,0 V einstellen (Multimeter an OUT).
2. Am RJ12-Adapter messen: Klemme 3 gegen Klemme 5 ≈ 12 V Ruhepegel, kurze Einbrüche bei Busverkehr. Keine 12 V → Splitter/Kabel prüfen (6P6C? 1:1?).
3. FST `12V` gegen `GND` = Bordspannung; FST `TX` gegen `GND` im Leerlauf ≈ 3,3 V (High), mit Busverkehr flackernd.
4. ESP32 flashen (`esphome run esphome/alde-inetbus-observer.yaml`), Log: `Multi package request …` und `Alde Panel alive: ON` → fertig.

## Wenn nichts ankommt

| Symptom | Ursache | Maßnahme |
|---|---|---|
| Log leer, FST `TX` konstant ~2,7 V | Modul ohne Masse-Bezug oder defekt (vgl. inetbox.py Issue #52: zwei Boards nacheinander tot) | GND-Kette prüfen; `SLP` auf 3,3 V; Reserve-Modul |
| Log leer, FST `TX` toggelt | TX/RX vertauscht | GPIO16/17 tauschen |
| nur Prüfsummenfehler | Stop-Bits/Baud | 9600 **8N2** in der Config belassen; Kabel kürzen |
| `Alde Panel alive` bleibt OFF, aber Frames kommen | normal in B1 bis die Box pollt | abwarten, Log auf `BA.00.1F` prüfen |
