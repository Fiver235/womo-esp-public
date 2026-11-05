# VE.Bus-Mitschnitt mit eigenem ESP32

Erster Schritt für „Digital Multi Control (DMC) am ESP" (siehe `docs/DMC-RECHERCHE.md`). Ein **eigener, neuer ESP32** hört am VE.Bus nur zu. Am System ändert sich nichts, das DMC bleibt angeschlossen. Der Proxy-ESP ist nicht beteiligt.

Ziel: Welche Rahmen sendet das DMC, welche des MultiPlus wertet es aus, und in welchem Zeitfenster nach dem Sync läuft das alles?

## Material

- ESP32-Entwicklungsboard (esp32dev)
- RS485-Modul für **3,3 V** mit getrennt herausgeführten Pins **RO, RE, DE, DI**, z. B. MAX3485 oder SP3485. **Keine Module mit automatischer Richtungsumschaltung** (nur TXD/RXD ohne DE/RE), die können den Bus treiben.
- Vom Modul die Widerstände entfernen: den 120-Ω-Abschluss zwischen A und B sowie die Pull-up/Pull-down-Widerstände auf A und B. Sie sind für langsame Busse gedacht und belasten den VE.Bus. Prüfen: Im stromlosen Modul darf zwischen A und B kein kleiner Widerstand mehr messbar sein.
- Anschluss an den Bus, eines von beiden:
  - eine **freie VE.Bus-Buchse** an MultiPlus oder CCGX mit einem aufgeschnittenen Netzwerkkabel. Die zwei Buchsen sind jeweils parallel.
  - ein T-Adapter mit **allen 8 Adern parallel**. Kein „Splitter", der Adernpaare auf zwei Buchsen aufteilt.
- **USB-Powerbank** oder Notebook im Akkubetrieb zur Versorgung

## RJ45-Belegung des VE.Bus

Aus dem Victron-Schaltplan `VE_BBB_Cape_v0.80`, Seite 2, Stecker CN200/CN201. Damit ist der Widerspruch zwischen den Community-Quellen geklärt: esp32ess stimmt.

| Pin | Signal | Für den Mitschnitt | Ader T568B (mit Durchgangsprüfer bestätigen) |
|---|---|---|---|
| 1 | frei | – | |
| 2 | V+ (ca. 12 V, max. ca. 700 mW) | **nicht anschließen** | |
| 3 | GND | an GND des Moduls und des ESP | weiß/grün |
| 4 | A | an A des Moduls | blau |
| 5 | B | an B des Moduls | weiß/blau |
| 6 | Standby | **nicht anschließen** | |
| 7 | Panel Detect | **nicht anschließen** | |
| 8 | frei | – | |

## Verdrahtung

```text
VE.Bus Pin 4 (A) ─── A   RS485-Modul   RO ─── GPIO16 ESP32
VE.Bus Pin 5 (B) ─── B                 RE ─┐
VE.Bus Pin 3 (GND) ─ GND               DE ─┴─ GND
                                       DI ─── GND
                                       VCC ── 3V3 ESP32
                                       GND ── GND ESP32
```

- RE und DE fest auf GND bedeutet: Empfangen an, Treiber aus. DI liegt zusätzlich auf GND. Die Firmware weist dem UART auch keinen TX-Pin zu. Senden ist also doppelt ausgeschlossen.
- **Versorgung schwimmend halten:** ESP nur aus Powerbank oder Notebook-Akku, nicht aus dem Bordnetz und kein Netzteil. Pin 3 ist die Masse der VE.Bus-Schnittstelle, im GX ist sie galvanisch vom Rest getrennt (Si8641). Wie sie im MultiPlus zum Batterie-Minus liegt, ist nicht dokumentiert. Eine Verbindung zum Bordnetz könnte eine Ausgleichsstrom-Schleife bauen.
- Vor dem Anschließen messen, gegen Pin 3: Pin 2 ca. 12 V, Pin 4 und 5 zwischen 0 und 5 V. Liegt etwas außerhalb, nicht anschließen.

## Inbetriebnahme

1. ESP per USB flashen, noch **ohne** Bus:

   ```bash
   .\.venv\Scripts\esphome.exe run esphome\vebus-sniffer.yaml --device COMx
   ```

   Im Log stehen die WLAN-Adresse und „TCP-Stream auf Port 8484". Der ESP holt sich die Adresse per DHCP und ist als `vebus-sniffer.local` erreichbar.
2. Bus anschließen. Alle 30 s meldet das Log die Zähler. Erwartet: **50 Sync pro Sekunde**, UART-Fehler und Überläufe bleiben bei 0. Viele UART-Fehler und kein Sync: A und B tauschen, das ist beim reinen Empfang unkritisch.
3. Mitschnitt starten, das Notebook muss im Womo-WLAN sein:

   ```bash
   .\.venv\Scripts\python.exe tools\vebus_capture.py capture --host vebus-sniffer.local
   ```

   Die Datei landet unter `logs/vebus-<Datum>-<Zeit>.log`. Live erscheinen alle Rahmen mit geändertem Inhalt, Ende mit Strg+C.

## Aktionen während des Mitschnitts

Jede Aktion mit Uhrzeit notieren, mindestens 30 s Abstand. **„Aus" und „Ladegerät" unterbrechen die 230-V-Versorgung über den Wechselrichter**, also auch die Aventa.

1. 2 Minuten nichts tun (Grundzustand)
2. Drehknopf langsam auf Minimum, dann Maximum, dann zurück
3. Schalter: Ein → Ladegerät → Ein
4. Schalter: Ein → Aus, 1 Minute warten, → Ein. Wichtig: Läuft der Sync im Aus-Zustand weiter?
5. Mit Landstrom: dasselbe, und Landstrom einmal ab und wieder an. So sieht man die LED- und Stromrahmen in allen Zuständen.
6. Einmal das RJ45-Kabel des DMC ziehen und wieder stecken: Das zeigt, was beim Start des DMC ausgetauscht wird. Vorsicht: Der MultiPlus kann dabei seinen Zustand ändern, deshalb nur, wenn eine kurze Unterbrechung der 230 V nicht stört.

## Auswertung

```bash
.\.venv\Scripts\python.exe tools\vebus_capture.py analyze logs\vebus-<Datei>.log
```

Ergibt je Adresse und Befehl: Anzahl, Prüfsummenfehler, Varianten, mittleren Abstand und die Lage nach dem Sync in ms. Dazu kommt die Zeitachse der Änderungen an Panel-Rahmen 0x40 und LED-Rahmen 0x41, die sich mit den notierten Aktionen vergleichen lässt.

Die Dekodierung von 0x40 und 0x41 stammt aus dem MK2-Dokument und der ve.bus-library. An echten DMC-Rahmen ist sie noch nicht bestätigt, insbesondere nicht die Bitlage der Schalterstellung.

## Stand

| Punkt | Stand 05.11.2026 |
|---|---|
| Firmware `esphome/vebus-sniffer.yaml`, `esphome/vebus_sniffer.h` | kompiliert, noch auf keinem ESP |
| `tools/vebus_capture.py` | Selbsttest OK: echte Beispielrahmen aus esp32ess, TCP-Strecke mit Testserver |
| Mitschnitt an der Anlage | offen, Hardware fehlt noch |
