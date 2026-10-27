# Bestellliste (Amazon.de) – Track B1 und B2

Stand 16.10.2026, Preise wie auf Amazon.de angezeigt (ändern sich täglich; Verfügbarkeit prüfen). B1 (Mitschnitt) und B2 (Befehl senden) brauchen **dieselbe Hardware** – ein ESP32, ein LIN-Transceiver am TIN-Bus. Nichts davon ist für JP3/Track A.

## Pflicht

| # | Artikel | Link | Preis | Warum / Hinweis |
|---|---|---|---|---|
| 1 | **ESP32 NodeMCU Dev Kit C, CP2102, 38 Pin** – AZDelivery 3er-Pack | https://www.amazon.de/dp/B074RGW2VQ | 21,99 € | Board `esp32dev` aus den YAMLs. 3er-Pack: ein Reserve-ESP und einer später fürs Gateway. Einzelstück-Alternative: BerryBase https://www.amazon.de/dp/B09RKDCHSQ (6,80 €) oder USB-C-Variante https://www.amazon.de/dp/B0DGG7LXMF (7,59 €). |
| 2 | **TTL-UART-zu-LIN-Modul TJA1020** (MEROURII/AILOVA) | https://www.amazon.de/dp/B0895WQ5VM | 21,99 € | Genau das Modul, das inetbox.py / inetbox2mqtt dokumentieren (Pins 12V, GND, TX, RX, LIN, INH, SLP). 3,3-V-tauglich. **2 Stück bestellen** („Spare 5 % bei 2"): einer als Reserve bzw. später für JP3/Track A. Günstigere Alternative mit gleichem Chip: https://www.amazon.de/dp/B0HC67CFCG (17,69 €). |
| 3 | **RJ12-Splitter 6P6C, 1 Stecker → 2 Buchsen** (1aTTack) | https://www.amazon.de/dp/B0FCZNP46K | 6,76 € | Wird in die TIN-Buchse am Boiler gesteckt; iNet Box in Buchse 1, Sniffer in Buchse 2. Muss **6P6C** sein (alle 6 Kontakte), kein RJ11-Telefonsplitter. Alternative 1 Buchse → 2 Buchsen: https://www.amazon.de/dp/B0GSF54127 (3,59 €, dann zusätzlich ein kurzes Kabel #4 zum Boiler nötig). |
| 4 | **RJ12-Kabel 6-adrig 1:1, 2 m** (InLine 18842) | https://www.amazon.de/dp/B005I1UE3E | 4,38 € | Vom Splitter zum Sniffer. 6P6C, 1:1 belegt – wichtig, viele Telefonkabel sind nur 4-adrig oder gekreuzt. 1-m-Version: InLine 18848 (4,75 €). |
| 5 | **RJ12-Buchse auf Schraubklemmen, lötfrei, 2 Stück** (MEIRIYFA) | https://www.amazon.de/dp/B0FX8R5L5W | 10,99 € | Kabel #4 einstecken, Pin 3 (LIN) und Pin 5 (GND) per Schraubklemme abgreifen – kein Kabel aufschneiden, kein Crimpen. Zweites Stück für später. |
| 6 | **Step-Down 12 V → 5 V, MP1584EN, einstellbar** (6er-Pack) | https://www.amazon.de/dp/B0FC5QSS1Y | 7,99 € | Versorgung des ESP32 aus dem Bordnetz (am RJ12 liegt keine Spannung). Vor dem Anschluss mit Multimeter auf 5,0 V einstellen. Für B1 alternativ Powerbank/Laptop-USB – dann entfällt #6, GND trotzdem verbinden. |
| 7 | **Inline-Sicherungshalter Mini-Flachsicherung** (5er) | https://www.amazon.de/dp/B0B4NH8L69 | 6,99 € | In die 12-V-Zuleitung zu Transceiver + Step-Down. Mitgelieferte 15-A-Sicherungen **nicht** verwenden → #8. |
| 8 | **Mini-Flachsicherungen 2 A** (10 Stück) | https://www.amazon.de/dp/B0BJPFX5M3 | 3,99 € | Absicherung des Abgriffs. |
| 9 | **WAGO 221-413 Verbindungsklemmen** (3-polig) | https://www.amazon.de/dp/B0CDPC692C | 6,13 € | 12 V/GND sauber vom Bordnetz abzweigen (z. B. an der Zuleitung der iNet Box oder einer Verteilerklemme), wieder lösbar. |
| 10 | **Jumper-Kabel-Set M/M, M/F, F/F** (ELEGOO 3×40) | https://www.amazon.de/dp/B01EV70C78 | 6,99 € | ESP32 ↔ Transceiver (F/F), Transceiver ↔ Schraubklemmen (M-Ende in Klemme). |
| 11 | **ESP32 Breakout-Board 38 Pin mit Schraubklemmen** (2 Stück) | https://www.amazon.de/dp/B0BJF1W86K | 8,99 € | Macht den Aufbau im Fahrzeug rüttelfest – ESP32 aufstecken, alle Leitungen in Schraubklemmen. Für den ersten Labortest verzichtbar, fürs Womo empfehlenswert. |

**Summe Pflicht (mit 2 × #2): ca. 129 €** – mit Einzel-ESP (#1 BerryBase) und nur einem Transceiver ca. 92 €.

## Voraussetzungen, die du vermutlich schon hast

- Micro-USB- bzw. USB-C-Kabel passend zum ESP32 (Datenkabel, kein reines Ladekabel)
- Multimeter (Step-Down einstellen, RJ12-Pins nachmessen: Pin 3 ≈ 12 V Ruhepegel, Pin 5 = 0 V)
- Kleiner Schlitzschraubendreher (Schraubklemmen), Abisolierzange
- Laptop mit Python ≥ 3.10 für ESPHome
- Truma-App auf dem Handy, mit der iNet Box gekoppelt (für B1 die Befehlsquelle)

## Nicht nötig für B1/B2 (erst für Track A / Gateway-Endausbau)

- zweiter LIN-Transceiver (bereits als Reserve in #2 enthalten)
- Alde-Originalkabel „External panel" für JP3
- Gehäuse, IR-LED/IR-Empfänger für die Aventa-Option

## Aufbau-Reihenfolge (Kurzfassung)

1. Step-Down auf 5,0 V einstellen (ohne Last, Multimeter).
2. ESP32 auf Breakout #11; Transceiver #2: `12V`→ Sicherung → Bordnetz +, `GND` → Bordnetz − **und** ESP-GND, `TX`→GPIO16 (ESP RX), `RX`→GPIO17 (ESP TX), `LIN`→ Schraubklemme Pin 3, Transceiver-`GND` zusätzlich → Schraubklemme Pin 5.
3. Splitter #3 an den TIN-Anschluss des Boilers, iNet Box in Buchse 1, Kabel #4 in Buchse 2 → Adapter #5.
4. `esphome run esphome/alde-inetbus-observer.yaml`, Log beobachten: `Multi package request …` erscheint → Bus läuft.

Pinbelegung TX/RX des Transceivers: Die Beschriftung meint die Richtung aus Sicht des Moduls (TX = Modul sendet zum ESP). Falls kein Empfang: TX/RX tauschen – das ist der häufigste Fehler. Vollständige Verdrahtung mit dem „FST T151"-Modul: [VERDRAHTUNG.md](VERDRAHTUNG.md).
