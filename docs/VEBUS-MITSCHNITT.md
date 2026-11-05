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
- Für die Versorgung aus dem VE.Bus (Entscheidung Rudi 05.11.2026):
  - Abwärtswandler, einstellbar, Eingang ab 4,5 V, z. B. MP1584, **vor dem Anschluss ohne Last auf 3,3 V eingestellt**
  - Schottky-Diode, z. B. 1N5819, in Reihe in der V+-Leitung
  - Elko 220 µF hinter der Diode, Elko 470–1000 µF am 3V3-Pin des ESP. Die WLAN-Spitzen kann V+ nicht liefern.
  - Widerstand 270 Ω, mindestens 1 W, für die Belastungsprobe

## RJ45-Belegung des VE.Bus

Aus dem Victron-Schaltplan `VE_BBB_Cape_v0.80`, Seite 2, Stecker CN200/CN201. Damit ist der Widerspruch zwischen den Community-Quellen geklärt: esp32ess stimmt.

| Pin | Signal | Für den Mitschnitt | Ader T568B (mit Durchgangsprüfer bestätigen) |
|---|---|---|---|
| 1 | frei | – | |
| 2 | V+ (ca. 12 V, max. ca. 700 mW) | über Diode an den Abwärtswandler | orange |
| 3 | GND | an GND von Modul, ESP und Abwärtswandler | weiß/grün |
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

VE.Bus Pin 2 (V+) ──►|── 1N5819 ──┬── IN+  Abwärtswandler  OUT+ ──┬── 3V3-Pin ESP32
                               220 µF      auf 3,3 V eingestellt  1000 µF
VE.Bus Pin 3 (GND) ───────────────┴── IN−                  OUT− ──┴── GND ESP32
```

Die 3,3 V gehen direkt an den 3V3-Pin, nicht an 5V/VIN: Der Längsregler auf dem Board würde sonst rund ein Drittel der knappen Leistung verheizen.

- RE und DE fest auf GND bedeutet: Empfangen an, Treiber aus. DI liegt zusätzlich auf GND. Die Firmware weist dem UART auch keinen TX-Pin zu. Senden ist also doppelt ausgeschlossen.
- **Keine zweite Verbindung:** Die Schaltung hängt nur an der Masse des VE.Bus. Pin 3 ist die Masse der VE.Bus-Schnittstelle, im GX ist sie galvanisch vom Rest getrennt (Si8641). Wie sie im MultiPlus zum Batterie-Minus liegt, ist nicht dokumentiert. Deshalb keine Verbindung zum Bordnetz, und **USB nie gleichzeitig mit dem VE.Bus**. Nach dem ersten Flashen läuft alles per WLAN.
- Vor dem Anschließen messen, gegen Pin 3: Pin 2 ca. 12 V, Pin 4 und 5 zwischen 0 und 5 V. Liegt etwas außerhalb, nicht anschließen.

## Reicht die Leistung?

V+ ist keine feste Spannungsquelle. esp32ess hat an einem anderen MultiPlus gemessen: 11,65 V Leerlauf und ca. 39 Ω Innenwiderstand, ohne Digital Multi Control. Laut Victron-Schaltplan versorgt V+ auch die Schnittstelle im GX, vermutlich hängt auch das DMC daran. Alle teilen sich dasselbe Budget, und bei zu viel Last sackt die Spannung für alle ab.

| Grobe Abschätzung, nicht gemessen | Leistung aus V+ |
|---|---|
| ESP32 bei 80 MHz mit Modem-Sleep, im Mittel ca. 50–70 mA an 3,3 V | ca. 0,2–0,3 W |
| RS485-Modul | ca. 0,02 W |
| Wandlerverluste, ca. 80 % Wirkungsgrad | ca. 0,1 W |
| **Summe im Mittel** | **ca. 0,3–0,4 W**, Spitzen beim Senden puffern die Elkos |

**Belastungsprobe vor dem Anschluss der Schaltung:** An der VE.Bus-Buchse, alles im Normalbetrieb, DMC und GX angeschlossen:

1. Spannung Pin 2 gegen Pin 3 ohne Last messen: V0.
2. 270 Ω kurz zwischen Pin 2 und Pin 3, etwa 40 mA: V1 messen. Innenwiderstand R = (V0 − V1) / (V1 / 270).
3. Während der Probe prüfen: DMC-Anzeige normal, GX zeigt den MultiPlus weiter an, kein Alarm.

Weiter nur, wenn V1 über 9 V bleibt und nichts auffällt. Im Betrieb an Pin 2 nachmessen: Fällt die Spannung unter 9 V oder zeigt der GX VE.Bus-Fehler, Schaltung sofort abziehen.

Das Anstecken lädt den 220-µF-Elko und zieht V+ für einige Millisekunden herunter. Deshalb nur anstecken, wenn ein kurzer Aussetzer der 230 V nicht stören würde.

## Inbetriebnahme

1. ESP per USB flashen, noch **ohne** Bus und ohne Abwärtswandler am 3V3-Pin:

   ```bash
   .\.venv\Scripts\esphome.exe run esphome\vebus-sniffer.yaml --device COMx
   ```

   Im Log stehen die WLAN-Adresse, „TCP-Stream auf Port 8484" und der WireGuard-Handshake. Das WLAN nutzt dieselben Zugangsdaten wie die anderen ESPs, die Adresse kommt dort per DHCP. Über WireGuard (eigener Fritzbox-Peer) ist der ESP fest unter **192.168.100.210** erreichbar, wie Alde-ESP (.202) und Proxy (.208).
2. USB abziehen, Belastungsprobe machen, dann die Schaltung anstecken. Das Log gibt es nun per WLAN (`esphome logs`). Alle 30 s meldet es die Zähler. Erwartet: **50 Sync pro Sekunde**, UART-Fehler und Überläufe bleiben bei 0. Viele UART-Fehler und kein Sync: A und B tauschen, das ist beim reinen Empfang unkritisch.
3. Mitschnitt starten, von überall, wo das Heimnetz erreichbar ist:

   ```bash
   .\.venv\Scripts\python.exe tools\vebus_capture.py capture --host 192.168.100.210
   ```

   Die Datei landet unter `logs/vebus-<Datum>-<Zeit>.log`. Live erscheinen alle Rahmen mit geändertem Inhalt, Ende mit Strg+C.

## Aktionen während des Mitschnitts

Jede Aktion mit Uhrzeit notieren, mindestens 30 s Abstand. **„Aus" und „Ladegerät" unterbrechen die 230-V-Versorgung über den Wechselrichter**, also auch die Aventa.

1. 2 Minuten nichts tun (Grundzustand)
2. Drehknopf langsam auf Minimum, dann Maximum, dann zurück
3. Schalter: Ein → Ladegerät → Ein
4. Schalter: Ein → Aus, 1 Minute warten, → Ein. Der Bus sollte dabei weiterlaufen: Der GX meldete den MultiPlus vom 01.11. 17:42 bis 04.11. 15:17 durchgehend als „off" statt „nicht verfügbar", und das DMC zeigt im Aus-Zustand weiter Status an. Laut MK2-Dokument bleibt die interne Versorgung an, solange die Standby-Leitung auf GND liegt, und der GX kann sie laut Schaltplan ziehen. V+ selbst ist im Aus-Zustand noch nicht gemessen; einmal an Pin 2 nachmessen. Sollte der ESP doch ausfallen, verbindet sich das Werkzeug danach selbst wieder.
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
| Firmware `esphome/vebus-sniffer.yaml`, `esphome/vebus_sniffer.h` | kompiliert mit WireGuard, noch auf keinem ESP |
| `tools/vebus_capture.py` | Selbsttest OK: echte Beispielrahmen aus esp32ess, TCP-Strecke mit Testserver, Wiederverbinden |
| Versorgung über VE.Bus | Stromaufnahme nur geschätzt, Belastungsprobe an der Anlage offen |
| WireGuard 192.168.100.210 | Peer in der Fritzbox angelegt, Handshake noch ungetestet; der Tunnel kostet zusätzlich etwas Strom |
| Mitschnitt an der Anlage | offen, Hardware fehlt noch |
