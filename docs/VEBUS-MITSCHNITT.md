# VE.Bus-Mitschnitt mit eigenem ESP32

Erster Schritt für „Digital Multi Control (DMC) am ESP" (siehe `docs/DMC-RECHERCHE.md`). Ein **eigener, neuer ESP32** hört am VE.Bus nur zu. Am System ändert sich nichts, das DMC bleibt angeschlossen. Der Proxy-ESP ist nicht beteiligt.

Ziel: Welche Rahmen sendet das DMC, welche des MultiPlus wertet es aus, und in welchem Zeitfenster nach dem Sync läuft das alles?

## Material

- ESP32-Entwicklungsboard (esp32dev)
- Rudis RS485-Modul „RS485 to TTL“ (MAX485 CSA, CD4069, automatische Richtungsumschaltung, Pins VCC/TXD/RXD/GND), vorbereitet wie im Abschnitt „RS485-Modul vorbereiten“
- Spannungsteiler für den Datenausgang: 1 kΩ und 2 kΩ
- Anschluss an den Bus, eines von beiden:
  - eine **freie VE.Bus-Buchse** an MultiPlus oder CCGX mit einem aufgeschnittenen Netzwerkkabel. Die zwei Buchsen sind jeweils parallel.
  - ein T-Adapter mit **allen 8 Adern parallel**. Kein „Splitter", der Adernpaare auf zwei Buchsen aufteilt.
- Für die Versorgung aus dem VE.Bus (Entscheidung Rudi 05.11.2026):
  - Abwärtswandler, einstellbar, Eingang ab 4,5 V, z. B. MP1584, **vor dem Anschluss ohne Last auf 5,0 V eingestellt**
  - Schottky-Diode, z. B. 1N5819, in Reihe in der V+-Leitung
  - Elko 220 µF, mindestens 25 V, hinter der Diode. Elko 470–1000 µF, mindestens 6,3 V, besser 10 V, am 5V-Pin des ESP. Die WLAN-Spitzen kann V+ nicht liefern.
  - Widerstand 270 Ω, mindestens 1 W, für die Belastungsprobe

## RJ45-Belegung des VE.Bus

Aus dem Victron-Schaltplan `VE_BBB_Cape_v0.80`, Seite 2, Stecker CN200/CN201. Damit ist der Widerspruch zwischen den Community-Quellen geklärt: esp32ess stimmt.

| Pin | Signal | Für den Mitschnitt | Ader T568B (mit Durchgangsprüfer bestätigen) |
|---|---|---|---|
| 1 | frei | – | |
| 2 | V+ (ca. 12 V, max. ca. 700 mW) | über Diode an den Abwärtswandler | orange |
| 3 | GND | an GND von Modul, ESP und Abwärtswandler | weiß/grün |
| 4 | A | an A+ des Moduls | blau |
| 5 | B | an B− des Moduls | weiß/blau |
| 6 | Standby | **nicht anschließen** | |
| 7 | Panel Detect | **nicht anschließen** | |
| 8 | frei | – | |

## Verdrahtung

```text
VE.Bus Pin 4 (A) ─── A+  RS485-Modul  Ausgang ── 1 kΩ ──┬── GPIO16 ESP32
VE.Bus Pin 5 (B) ─── B−               Eingang ── VCC    2 kΩ
          3. Klemme (接大地) frei      VCC ─── 5 V       └── GND
                                      GND ─── GND

VE.Bus Pin 2 (V+) ──►|── 1N5819 ──┬── IN+  Abwärtswandler  OUT+ ──┬── 5V-Pin ESP32, VCC Modul
                               220 µF      auf 5,0 V eingestellt  1000 µF
VE.Bus Pin 3 (GND) ───────────────┴── IN−                  OUT− ──┴── GND ESP32, GND Modul
```

- **5 V für Test und Betrieb** (Entscheidung Rudi 05.11.2026): Das liegt im Datenblatt des MAX485 (4,75–5,25 V), und die Versorgung bleibt für das spätere Senden gleich. Der 3V3-Pin des ESP bleibt frei.
- **Spannungsteiler ist Pflicht:** Der Modulausgang liefert bis zu 5 V, die GPIOs vertragen nur 3,3 V. Bei versorgtem Modul und offenem A+/B− an GPIO16 messen: etwa 3,3 V erwartet. Über ca. 3,4 V ESP nicht anschließen. Unter 2,5 V erkennt der ESP kein sicheres High, dann erst die Ursache klären.
- **Nicht senden können:** Der Dateneingang des Moduls liegt fest an VCC, dadurch bleibt der Sender aus. Die Firmware weist dem UART zusätzlich keinen TX-Pin zu.
- Die dritte Klemme (接大地 = an Erde anschließen) bleibt frei. Sie führt nur zu den Schutzdioden.
- **Keine zweite Verbindung:** Die Schaltung hängt nur an der Masse des VE.Bus. Pin 3 ist die Masse der VE.Bus-Schnittstelle, im GX ist sie galvanisch vom Rest getrennt (Si8641). Wie sie im MultiPlus zum Batterie-Minus liegt, ist nicht dokumentiert. Deshalb keine Verbindung zum Bordnetz, und **USB nie gleichzeitig mit dem VE.Bus**. Nach dem ersten Flashen läuft alles per WLAN.
- Vor dem Anschließen messen, gegen Pin 3: Pin 2 ca. 12 V, Pin 4 und 5 zwischen 0 und 5 V. Liegt etwas außerhalb, nicht anschließen.

## RS485-Modul vorbereiten

Aufschriften laut Foto vom 05.11.2026: MAX485 CSA, CD4069UBM, R14 „121“ (120 Ω), R3/R4 „472“ (4,7 kΩ), zwei Sicherungen „010“ und drei Schutzdioden an A+/B−. Der MAX485 schafft laut Datenblatt 2,5 MBit/s, 256 kBaud sind beim Empfang kein Problem. Der Händler nennt 3,3–5 V (Rudi 05.11.2026), das Datenblatt 4,75–5,25 V. Die Bedeutung von R11 und R12 ist auf dem Foto nicht lesbar und wird unten gemessen.

Alles ohne Busanschluss und ohne ESP:

1. **R14 entfernen,** das ist der 120-Ω-Abschluss. Zwischen A+ und B− darf stromlos danach kein kleiner Widerstand mehr messbar sein, mehr als 10 kΩ.
2. **Pull-Widerstände suchen:** Stromlos messen von A+ nach VCC, von A+ nach GND, von B− nach VCC und von B− nach GND. Liegt ein Wert unter etwa 100 kΩ, führt er vermutlich über R11 oder R12. Den betreffenden Widerstand entfernen und erneut messen.
3. **Eingang und Ausgang bestimmen:** Das Modul mit 5 V versorgen, A+ und B− offen. TXD und RXD nacheinander über 10 kΩ gegen GND legen und die Spannung am Pin messen. Bleibt sie bei etwa 5 V, ist der Pin der **Ausgang**, er kommt an den Spannungsteiler. Sinkt sie deutlich, ist er der **Eingang**, er kommt fest an VCC. Die Beschriftung TXD/RXD ist bei diesen Modulen uneinheitlich, deshalb messen.

Für den Mitschnitt reicht das so. Zum Senden muss das Modul umgebaut werden, siehe nächster Abschnitt.

## Umbau zum Senden (später)

Entscheidung Rudi 05.11.2026: Dieses Modul bleibt auch für den Betrieb, es sind mehrere vorhanden. Der Umbau ist ein Plan und noch nicht erprobt. Er setzt die unten geprüfte Schaltung voraus.

**Warum unverändert nicht:** Bei diesen Modulen liegt der Dateneingang DI üblicherweise fest auf GND, und der CD4069 steuert aus dem Datensignal nur die Richtung. Eine 0 wird aktiv getrieben, bei einer 1 schaltet der Treiber ab und nur Pull-Widerstände ziehen den Bus zurück. Bei 256 kBaud dauert ein Bit 3,9 µs. Mit 4,7 kΩ wäre das vermutlich zu langsam, und kleinere Pull-Widerstände würden den Bus dauerhaft belasten. Nach dem Umbau treibt der MAX485 beide Pegel selbst. Ob die Pull-Widerstände am Betriebsmodul trotzdem nötig sind, klärt der Betriebsabschnitt unten.

Den Umbau zuerst an einem zweiten Modul machen. Das unveränderte Modul bleibt für den Mitschnitt und als Reserve.

1. **Schaltung prüfen,** stromlos mit dem Durchgangsprüfer. Pinbelegung des MAX485 laut Datenblatt: 1 RO, 2 /RE, 3 DE, 4 DI, 5 GND, 6 A, 7 B, 8 VCC. Erwartet: Pin 2 und 3 verbunden und am CD4069, Pin 4 auf GND, Pin 1 am Ausgang des Moduls. Weicht etwas ab, erst klären und nicht weiterbauen.
2. **MAX485 Pin 2/3 und Pin 4 freilegen:** Pins anheben oder die Leiterbahnen durchtrennen. Pin 2 und 3 müssen untereinander verbunden bleiben. Danach darf Pin 2/3 keinen Durchgang mehr zum CD4069 haben und Pin 4 keinen mehr nach GND.
3. **Eingang des Moduls weiter fest an VCC,** damit der CD4069 einen festen Pegel hat.
4. **Neu verdrahten:**

```text
MAX485 Pin 4 (DI)       ── GPIO17 ESP32
MAX485 Pin 2+3 (/RE+DE) ── GPIO4 ESP32
MAX485 Pin 2+3          ── 10 kΩ ── GND   Pflicht: Treiber bleibt aus, solange der ESP nicht aktiv treibt
Ausgang des Moduls      ── GPIO16 ESP32 wie beim Mitschnitt
```

- **Versorgung:** bleibt bei 5 V wie im Mitschnitt, der Teiler am Modulausgang auch. GPIO17 und GPIO4 brauchen keinen Teiler, die Eingänge des MAX485 erkennen 3,3 V laut Datenblatt als High (ab 2,0 V).
- **Dauersenden verhindern:** Bleibt der Treiber dauerhaft an, blockiert er die Leitung. Deshalb der Pull-down, dazu in der Firmware eine hardwaregesteuerte Umschaltung (RS485-Modus des UART) und eine Sperre gegen Dauersenden.
- **Mitschnitt mit umgebautem Modul:** Die jetzige Firmware steuert GPIO4 und GPIO17 nicht an, der Pull-down hält den Treiber aus. Das umgebaute Modul hört also ebenfalls nur zu.

## Unterschied zum Betrieb

Der Mitschnitt hängt am echten VE.Bus. Im geplanten Betrieb (`docs/DMC-RECHERCHE.md`, Abschnitt Vorgehen) kommt das DMC vom VE.Bus ab und bekommt ein **eigenes Kabel zum ESP**. Der ESP spielt dem DMC gegenüber den MultiPlus und schaltet den echten MultiPlus per WLAN über den GX. **Gesendet wird also nur zum DMC, nicht auf den VE.Bus.** Das alles ist noch ein Plan, ob das DMC damit läuft, klärt erst der Werkbanktest.

| | Mitschnitt | Betrieb |
|---|---|---|
| A+ und B− | VE.Bus Pin 4 und 5 | Pin 4 und 5 des DMC-Kabels |
| 12 V für Abwärtswandler | VE.Bus Pin 2 und 3 | offen, siehe unten |
| Versorgung des DMC | aus dem VE.Bus | muss der Aufbau liefern: 12 V an Pin 2 und 3 des DMC-Kabels |
| Abwärtswandler, Diode, Elkos, 5 V, Teiler, GPIO16 | wie oben | unverändert |
| GPIO17, GPIO4, Pull-down | frei | laut „Umbau zum Senden“ |

- **Quelle der 12 V offen:** Entweder nur Pin 2 und 3 einer VE.Bus-Buchse oder abgesichertes Bordnetz. Der ESP muss den MultiPlus auch einschalten können, also auch im Aus-Zustand laufen. Dafür zuerst V+ im Aus-Zustand messen (Aktion 4 unten). Bei Bordnetz keine Verbindung zu VE.Bus-Pin 3 herstellen, solange die Massen nicht geprüft sind.
- **R14 am Betriebsmodul:** entfernen. Die kurze Leitung zum DMC braucht vermutlich keinen Abschluss, und er würde den Sendestrom deutlich erhöhen.
- **R11 und R12 am Betriebsmodul vorerst drauflassen:** Auf der eigenen Leitung hält sonst niemand den Ruhepegel, wenn weder ESP noch DMC senden. Ob die Pull-Widerstände nötig sind, zeigt der Werkbanktest.

## Reicht die Leistung?

V+ ist keine feste Spannungsquelle. esp32ess hat an einem anderen MultiPlus gemessen: 11,65 V Leerlauf und ca. 39 Ω Innenwiderstand, ohne Digital Multi Control. Laut Victron-Schaltplan versorgt V+ auch die Schnittstelle im GX, vermutlich hängt auch das DMC daran. Alle teilen sich dasselbe Budget, und bei zu viel Last sackt die Spannung für alle ab.

| Grobe Abschätzung, nicht gemessen | Leistung aus V+ |
|---|---|
| ESP32 bei 80 MHz mit Modem-Sleep, im Mittel ca. 50–70 mA an 5 V über den Längsregler des Boards | ca. 0,25–0,35 W |
| RS485-Modul | ca. 0,01–0,02 W |
| Wandlerverluste, ca. 80 % Wirkungsgrad | ca. 0,1 W |
| **Summe im Mittel** | **ca. 0,35–0,45 W**, Spitzen beim Senden puffern die Elkos |

**Belastungsprobe vor dem Anschluss der Schaltung:** An der VE.Bus-Buchse, alles im Normalbetrieb, DMC und GX angeschlossen:

1. Spannung Pin 2 gegen Pin 3 ohne Last messen: V0.
2. 270 Ω kurz zwischen Pin 2 und Pin 3, etwa 40 mA: V1 messen. Innenwiderstand R = (V0 − V1) / (V1 / 270).
3. Während der Probe prüfen: DMC-Anzeige normal, GX zeigt den MultiPlus weiter an, kein Alarm.

Weiter nur, wenn V1 über 9 V bleibt und nichts auffällt. Im Betrieb an Pin 2 nachmessen: Fällt die Spannung unter 9 V oder zeigt der GX VE.Bus-Fehler, Schaltung sofort abziehen.

Das Anstecken lädt den 220-µF-Elko und zieht V+ für einige Millisekunden herunter. Deshalb nur anstecken, wenn ein kurzer Aussetzer der 230 V nicht stören würde.

## Inbetriebnahme

1. ESP per USB flashen, noch **ohne** Bus und ohne Abwärtswandler am 5V-Pin:

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
