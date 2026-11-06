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
- Powerbank mit USB-Kabel zum ESP (Entscheidung Rudi 05.11.2026, siehe „Versorgung über V+“)

## RJ45-Belegung des VE.Bus

Aus dem Victron-Schaltplan `VE_BBB_Cape_v0.80`, Seite 2, Stecker CN200/CN201. Damit ist der Widerspruch zwischen den Community-Quellen geklärt: esp32ess stimmt.

| Pin | Signal | Für den Mitschnitt | Ader T568B (mit Durchgangsprüfer bestätigen) |
|---|---|---|---|
| 1 | frei | – | |
| 2 | V+ (gemessen 9,0 V, siehe „Versorgung über V+“) | **nicht anschließen** | orange |
| 3 | GND | an GND von Modul und ESP | weiß/grün |
| 4 | A | an A+ des Moduls | blau |
| 5 | B | an B− des Moduls | weiß/blau |
| 6 | Standby | **nicht anschließen** | |
| 7 | Panel Detect | **nicht anschließen** | |
| 8 | frei | – | |

## Verdrahtung

```text
Powerbank ─── USB-Buchse ESP32

VE.Bus Pin 4 (A) ─── A+  RS485-Modul  RXD ── 1 kΩ ──┬── GPIO16 ESP32
VE.Bus Pin 5 (B) ─── B−               TXD ── VCC    2 kΩ
          3. Klemme (接大地) frei      VCC ─── 5V-Pin ESP32  └── GND
                                      GND ─── GND ESP32
VE.Bus Pin 3 (GND) ─────────────────────────── GND ESP32
```

- **RXD und TXD vorher prüfen:** Der Plan nimmt an, dass RXD der Ausgang und TXD der Eingang des Moduls ist. Die Beschriftung ist bei diesen Modulen uneinheitlich, deshalb gilt das Messergebnis aus „RS485-Modul vorbereiten“, Schritt 3. Zeigt die Messung das Gegenteil, RXD und TXD im Plan tauschen.

- **5 V am Modul** (Entscheidung Rudi 05.11.2026): Das liegt im Datenblatt des MAX485 (4,75–5,25 V). Der 5V-Pin liefert bei USB-Versorgung je nach Board etwas weniger als 5 V, ob das reicht, zeigen die Zähler. Der 3V3-Pin des ESP bleibt frei.
- **Spannungsteiler ist Pflicht:** Der Modulausgang liefert bis zu 5 V, die GPIOs vertragen nur 3,3 V. Vor dem Anschluss an GPIO16 messen: Modul versorgt, A+/B− offen, Mittelpunkt des Teilers noch nicht am GPIO. Etwa 3,3 V erwartet. Über ca. 3,4 V nicht an GPIO16 anschließen. Unter 2,5 V erkennt der ESP kein sicheres High, dann erst die Ursache klären.
- **Masse:** Pin 3 muss angeschlossen sein, sonst fehlt dem Modul der Bezug zum Bus.
- **Nicht senden können:** Der Dateneingang des Moduls (TXD) liegt fest an VCC, dadurch bleibt der Sender aus. Die Firmware weist dem UART zusätzlich keinen TX-Pin zu.
- Die dritte Klemme (接大地 = an Erde anschließen) bleibt frei. Sie führt nur zu den Schutzdioden.
- **Keine zweite Verbindung:** Die Schaltung hängt nur an der Masse des VE.Bus. Pin 3 ist die Masse der VE.Bus-Schnittstelle, im GX ist sie galvanisch vom Rest getrennt (Si8641). Wie sie im MultiPlus zum Batterie-Minus liegt, ist nicht dokumentiert. Deshalb keine Verbindung zum Bordnetz, und **PC oder Netzteil nie gleichzeitig mit dem VE.Bus**. Das gilt auch für eine Powerbank, die gerade geladen wird. Nach dem ersten Flashen läuft alles per WLAN.
- Vor dem Anschließen messen, gegen Pin 3: Pin 4 und 5 zwischen 0 und 5 V. Liegt etwas außerhalb, nicht anschließen.

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

## Werkbanktest (Schritt 2)

Das DMC hängt nur am ESP. Die Firmware `esphome/vebus-dmc-bench.yaml` spielt aufgezeichnete MultiPlus-Rahmen aus dem Mitschnitt vom 05.11.2026 ab (`tools/vebus_make_replay.py`): einmal den Hochlauf nach „Aus“, danach endlos 30 s im Zustand Ein. Rahmennummer und Prüfsumme setzt sie neu, die Berechnung stimmte an allen 50.566 MultiPlus-Rahmen des Mitschnitts. Die LEDs folgen der Aufzeichnung, nicht dem Schalter. Ungetestet.

Geprüft wird nur: Läuft das DMC ohne Fehleranzeige, reagieren die LEDs, und kommen seine Rahmen `40` fehlerfrei an?

```text
RS485-Wandler
VCC ── 5V ESP        GND ── GND ESP
RXD ── 1 kΩ ──┬── GPIO16 ESP
             2 kΩ
              └── GND
TXD ──►|── 1N4148 ──┬── GPIO17 ESP    (Strich der Diode zum ESP)
                  10 kΩ
                    └── GND

Adapterplatine mit dem Kabel des DMC, ohne Verbindung zum VE.Bus
Pin 4 (A) ── A+ Wandler
Pin 5 (B) ── B− Wandler
Pin 3 (GND) ── GND ESP ── Minus Labornetzteil
Pin 2 (V+) ── Plus Labornetzteil
Pin 6, Pin 7 frei
```

- **Labornetzteil:** Vor dem Anschluss auf 8,5 V und eine Strombegrenzung von 150 mA einstellen. Der Strom ist ungemessen, die Grenze ist eine Annahme aus den rund 700 mW laut esp32ess. Nie die 5V-Klemme des ESP an Pin 2 und das DMC nicht ohne Klärung an das Bordnetz.
- **R14:** Entscheidung Rudi: erster Test mit R14 auf dem Wandler. Erwartung: Die Einsen kommen beim DMC vermutlich nicht sauber an, weil R11/R12 gegen 120 Ω zu wenig Spannung erzeugen. Fehlen dem DMC die Rahmen, zuerst R14 ausbauen.
- **Sperre:** Die Firmware hört vor dem Senden 5 s zu. Empfängt sie dabei MultiPlus-Rahmen, sendet sie bis zum Neustart nicht. Das ist eine Absicherung und ersetzt nicht die Trennung vom VE.Bus.
- **Ablauf:**
  1. Das DMC vom VE.Bus abziehen. Die 230 V über den Wechselrichter können dabei kurz ausfallen.
  2. Am CCGX prüfen, ob der MultiPlus weiter läuft. Der CCGX merkt sich das DMC vermutlich bis „System neu erkennen“.
  3. Aufbau verdrahten, Firmware flashen.
  4. Mitschnitt mit `tools/vebus_capture.py` starten, dann das Labornetzteil einschalten.
- **Zurück:** `vebus-sniffer.yaml` flashen, TXD wieder an VCC und das DMC wieder an den VE.Bus.

**Dritter Lauf 05.11.2026: Das DMC antwortet.** Bei den beiden ersten Läufen steckte TXD versehentlich an P14 statt an P17, der ESP hat also nichts auf die Leitung gegeben. Ihre Deutungen zu R14 und zur Richtungsumschaltung sind damit hinfällig. Mit TXD an P17 und ohne R14 gilt:

- **LEDs:** Mains On und Bulk leuchten. Das entspricht `LED=05` in den abgespielten Rahmen `41`. Der unveränderte Wandler mit automatischer Umschaltung reicht also für dieses Ergebnis, der große Umbau ist vorerst nicht nötig.
- **Rahmen vom DMC:** `F0F7 FE 40 1A A0 00`, also Schalter Ein und 16,0 A, keine UART-Fehler. 48 von 1487 Rahmen in 15 s waren fehlerhaft. Viele davon sehen nach Überschneidungen mit den Sendungen des ESP aus, geprüft ist das nicht.
- **Noch anders als am echten Bus:** Das DMC sendet `FC 0F` etwa alle 16 ms und `40` etwa alle 27 ms statt alle 500 ms. Vermutlich wartet es auf eine Antwort, die in der festen Aufzeichnung fehlt. Das ist noch nicht geklärt.
- **Knopf und Schalter (`logs/vebus-20261105-191007.log`, lokal):** Stromgrenze und Schalterstellung kommen im Rahmen `40` beim ESP an, mit denselben Werten wie am echten Bus, auch die `00 00` am Anschlag. Bei Schalter Aus bleiben LEDs und Anzeige an (Angabe Rudi), weil Versorgung und Rahmen weiterlaufen. Die Firmware spielt weiter eine feste Aufzeichnung ab, sie reagiert nicht auf das DMC.
- **Offen:** ob R14 stört, wurde nie gültig getestet. Er bleibt am Modul draußen.

**Erster Lauf 05.11.2026, mit R14, TXD falsch an P14 (`logs/vebus-20261105-182957.log`, lokal):**

- **DMC an 8,5 V:** etwa 70 mA, also rund 0,6 W. Die Ampere-Anzeige erscheint und folgt dem Drehknopf, die LEDs bleiben aus. In der Schalterstellung Aus bleibt das DMC trotz anliegender Spannung ganz aus, bis der Schalter betätigt wird (Angaben Rudi).
- **Empfang:** kein gültiger Rahmen vom DMC. Es kommen nur Nullbytes, jedes mit UART-Fehler, das heißt die Leitung liegt am Empfänger immer wieder lange auf Low. Das begann erst mit dem Einschalten des DMC. Vorher waren es 0 Bytes.

**Zweiter Lauf 05.11.2026, ohne R14, TXD falsch an P14 (`logs/vebus-20261105-184523.log`, lokal):**

- Gleiches Bild: keine LEDs, kein gültiger Rahmen, dasselbe Muster aus Nullbytes mit UART-Fehlern, etwa 48 pro Sekunde und alle 0,5 s wiederkehrend.
- Da der ESP nichts sendete, zeigt das vermutlich, was das DMC macht, solange es keinen Bus hört. Nullbytes mit Fehler bedeuten Low-Phasen von mindestens etwa 40 µs. Die RXD-LED des Wandlers blinkte dazu.

## Übersetzung (Schritt 3)

Firmware `esphome/vebus-dmc-bridge.yaml` mit `esphome/vebus_dmc_bridge.h`, gleiche Verdrahtung wie im Werkbanktest. Stand 05.11.2026: kompiliert, nicht geflasht, ungetestet.

- **Zum DMC:** Die Rahmen kommen weiter aus der Aufzeichnung. Den LED-Rahmen `41` erzeugt die Firmware aus dem echten Zustand, den sie jede Sekunde per Modbus TCP vom CCGX liest (192.168.1.242, Unit 246): Register 31 State, 33 Mode, 22 Stromgrenze. Sind die Daten älter als 10 s, bleiben die LEDs aus.
- **LED-Zuordnung**, abgeleitet aus dem Mitschnitt und nicht vollständig geprüft:

  | State | LEDs |
  |---|---|
  | 3 Bulk | Netz + Bulk |
  | 4 Absorption | Netz + Absorption |
  | 5 Float | Netz + Float |
  | 8 Durchleitung | Netz |
  | 9 Wechselrichter | Wechselrichter |
  | 10 Assist | Netz + Wechselrichter |
  | sonst | aus |

  Überlast, Batterie und Temperatur fehlen noch, weil die Register 63–70 am CCGX nur 0 liefern.
- **Vom DMC:** Ändert sich die Schalterstellung (300 ms stabil) oder die Stromgrenze (1,5 s stabil), schreibt die Firmware **einmal** Register 33 (1 Ladegerät, 3 Ein, 4 Aus) oder Register 22. Die Stromgrenze wird dabei auf 3,1–16,0 A begrenzt. Bei Fehlern gibt es bis zu 5 Versuche im Abstand von 2 s. Der erste Rahmen nach dem Start des DMC oder nach 3 s Pause setzt nur den Ausgangswert und schreibt nichts.
- **Schreibsperre:** Mit `write_enable: "false"` steht der geplante Befehl nur im Log. Die Freigabe erfolgt erst nach dem Lesetest und durch Rudi.
- **Versuch `FC 0F`:** Das Format ist vermutlich `FC Nummer 0F von bis` und meldet fehlende Rahmennummern. Am echten Bus folgte darauf `8383 FE .. 38 01 C0 C0`. Die Firmware antwortet ebenso, höchstens alle 200 ms. Ob das die häufigen `FC 0F` beendet, zeigt der Test.
- **Registerwerte am 05.11.2026, nur gelesen, ohne DMC am Bus:** Grenze 100 (10,0 A, laut Rudi so eingestellt), State 4, Mode 3. Register 22 ist schreibbar laut Victron-Liste, am CCGX aber nicht geprüft.

**Lesetest 05.11.2026 mit `write_enable: "false"`, Ergebnis:**

- **LEDs:** Mains On und Absorption leuchten, passend zu State 4 am CCGX (Rudi).
- **Ampere-Anzeige:** Sie zeigt die Stellung des Knopfs (16 A), nicht die 10,0 A aus dem Rahmen `41`. Die Anzeige folgt also dem Knopf.
- **Befehle laut Log, Uhrzeiten aus dem Log:**

  | Uhrzeit | Handgriff | Geplanter Befehl |
  |---|---|---|
  | 20:47:34 | Knopf auf 14,0 A | Register 22 = 140, 1,5 s später |
  | 20:47:37 | Schalter Aus | Register 33 = 4 |
  | 20:47:41 | Schalter Ein | Register 33 = 3 |

  Es wurde nichts geschrieben, und die Werte stimmen mit den Handgriffen überein.
- **Störungen:** `FC 0F` kommt weiter etwa 90-mal pro Sekunde, die Antwort `38` ändert daran nichts. Zeitweise sendet das DMC abgebrochene Rahmen, die mitten im Rahmen neu beginnen. Das sieht nach Kollisionen mit den Rahmen des ESP aus. Gültige Rahmen `40` kommen trotzdem regelmäßig an. Beides ist für den Dauerbetrieb noch zu klären.

**Schalttest 05.11.2026 mit `write_enable: "true"` (Freigabe Rudi), bestanden:**

| Schritt | Log des ESP | GX laut Log |
|---|---|---|
| 1 Knopf 12 A | 20:54:05 Register 22 = 120 bestätigt | Grenze 120 |
| 2 DMC Aus | 20:54:21 Register 33 = 4 bestätigt | Mode 4, State 0, LEDs aus |
| 3 DMC Ein | 20:54:36 Register 33 = 3 bestätigt | Wechselrichter, Bulk, Absorption; LEDs folgen |
| 4 Aus über CCGX/VRM | kein Schreiben | ab etwa 20:55:20 Mode 4, LEDs aus, DMC-Schalter steht auf Ein |
| 5 DMC Aus, dann Ein | 20:55:37 Register 33 = 4, 20:56:11 Register 33 = 3 | MultiPlus läuft wieder |
| 6 Knopf 10 A | 20:56:59 Register 22 = 100 bestätigt | Grenze 100 |

Jeder Schreibbefehl war nach etwa 50 ms bestätigt, ohne Fehlversuch. Home Assistant zeigt die Änderungen etwa 30 s später. „Letzter Befehl gewinnt“ funktioniert damit, wie in `docs/DMC-RECHERCHE.md` beschrieben, über einen Stellungswechsel am DMC.

**Versuche gegen `FC 0F`, 05.11.2026, beide ohne Erfolg:**

- **Neustart des ESP und automatischer Busstart:** Nach einer Pause von 2 s und einem Busstart ab Nummer 0 sendet das DMC kurz viele `40`, danach kommt die Flut wieder. Eine Lücke hängt jeweils fest, zum Beispiel `05 07` oder `2E 2F`.
- **Busstart erst beim Einschalten des DMC:** Die Erkennung war fehlerhaft. Restliche Bytes nach dem Anhalten zählten als „DMC meldet sich“, sodass der Bus etwa alle 5 s neu startete und das DMC nicht mehr antwortete. Der Versuch ist zurückgenommen, die Firmware steht wieder auf dem Stand des Schalttests. Der Code liegt nur lokal in der Sicherung.
- **Nebenbefund:** Um 21:12:04 meldete das DMC Schalter Aus, und der ESP schrieb Register 33 = 4. Der MultiPlus war damit aus. Steht der Schalter auf Aus und der Bus ist still, bleibt das DMC nach dem Einschalten dunkel und sendet nichts. Wird es danach auf Ein gestellt, gilt das als Ausgangswert und schreibt nichts. Das ist für den Betrieb zu bedenken.

**Erst hören, dann senden, 06.11.2026:** Bei Schalter Ladegerät blinkten unregelmäßig zusätzlich die LEDs Inverter On, Float und Bulk auf. Mains On und Absorption blieben dabei an. Der Mitschnitt zeigte, dass der ESP nach dem Zeitplan der Aufzeichnung sendet, auch wenn das DMC gerade selbst sendet. Das DMC bricht dann ab und sendet neu. Die Firmware sendet jetzt erst, wenn RX eine Zeit lang am Stück auf Ruhepegel war, und wartet dafür höchstens 5 ms. Der eigene Rahmen kommt nicht auf RX zurück. Low auf RX bedeutet also, dass das DMC sendet.

| je 3 min                     | vorher | Ruhe 80 µs | Ruhe 300 µs |
|------------------------------|--------|------------|-------------|
| gestörte Rahmen              | 320    | 999        | 204         |
| `40` gestört                 | 29     | –          | –           |
| `40` fehlt ~1 s              | 9      | 1          | 1           |
| `FC 0F` pro Sekunde          | 86     | 95         | 71          |
| Blinken (von Rudi gezählt)   | 9+     | 4+         | keins       |

80 µs waren zu kurz. Das DMC sendet `FC 0F` in Paketen mit etwa 0,1 ms Pause, und der ESP drängte sich in diese Lücken. Mit 300 µs ist das Blinken weg. Die Flut `FC 0F` bleibt.

**Ursachensuche `FC 0F`, 06.11.2026.** Die Firmware schreibt jetzt auch die selbst gesendeten Rahmen in den Mitschnitt (Zeilenart `T`), damit beide Seiten in einer Zeitachse stehen. Mitschnitte lokal: `logs/vebus-20261106-*.log`.

Was die Mitschnitte belegen:

- **Die gestörten Rahmen sind eine Folge der Flut.** Sie entstehen dort, wo ESP und DMC gleichzeitig senden. Ohne Flut sendet das DMC nur alle 500 ms.
- **`FC 0F a b` meldet eine Lücke in den Rahmennummern:** `a` ist die erste Nummer, die dem DMC fehlt (nach einem eigenen Rahmen dessen Nummer), `b` die Nummer des gerade empfangenen Datenrahmens. Eine Meldung kommt 0,1 bis 0,2 ms nach dem ersten Datenrahmen, der auf einen Sync folgt. Folgt ein Datenrahmen ohne Sync dazwischen, kommt keine Meldung. Oft wiederholt das DMC danach eine ältere Meldung.
- **Das DMC zählt den Sync des ESP nicht mit.** Am echten Bus trägt ein Rahmen des DMC direkt nach einem Sync dessen Nummer plus 1 (541 von 541 Fällen). Auf der Werkbank trägt er die Nummer des Sync selbst oder eine kleinere (134 von 138 Fällen, mit aufgezeichneter und mit eigener Zeitbasis). Aus Sicht des DMC fehlt damit in jedem 20-ms-Takt eine Nummer, und es meldet sie. Am echten Bus kommt `FC 0F` nur beim Busstart und beim Dazukommen eines Geräts vor.
- **Aufbau der Zeitangaben:** Die Uhr des MultiPlus hat 24 Bit und zählt in Schritten von 0,4 µs. Der Sync trägt sie als `55 lo mid hi`. `E4` trägt als Bytes 2–3 die Periode (50000 im Hochlauf, sonst etwa 50048) und als Bytes 4–6 die Zeit, zu der der nächste Sync beginnt. Der Sync selbst trägt diese Zeit plus 910 bis 956 Schritte. Die Abstände der Sync-Zeiten streuen am echten Bus nur um ±2 Schritte.
- **Das DMC startet zeitweise neu:** Es bleibt gut 5 s still und beginnt dann mit Rahmennummer 00. Gesehen nur mit eigener Zeitbasis (zweimal) und ohne `E4`.

Versuche, alle ohne Wirkung auf die Flut:

| Versuch | Ergebnis |
|---|---|
| Zeit in Sync und `E4` aus der eigenen Uhr, Sync im festen 20-ms-Raster | Flut unverändert, etwa 80 pro Sekunde |
| Sync zusätzlich auf wenige µs genau zum in `E4` angekündigten Zeitpunkt, Abstand 945 und 969 Schritte | unverändert |
| Auf jedes `FC 0F` sofort Sync und `38 01 C0 C0`, wie der MultiPlus beim Busstart | Das DMC antwortet auf jedes `38` mit weiteren `FC 0F`, die Flut verdoppelt sich |
| `E4` weglassen, aufgezeichnete Zeit | `FC 0F` hört auf, das DMC sendet aber rund 40 s gar nichts mehr, auch kein `40` |
| `E4` weglassen, eigene Zeit | `FC 0F` nach jedem anderen Datenrahmen, `40` etwa 10-mal pro Sekunde |

Offen ist damit nur noch, **warum das DMC den Sync des ESP nicht annimmt**. Inhalt, Prüfsumme und Zeitangaben stimmen mit dem echten Sync überein. Der Unterschied muss in etwas liegen, das der UART-Mitschnitt nicht zeigt, zum Beispiel im genauen Signalverlauf. Nächster Schritt: den echten Sync am VE.Bus flankengenau aufzeichnen (Oszilloskop oder der ESP als Logikanalysator) und mit dem Sync des ESP vergleichen.

Für die Versuche lässt sich die Firmware über den Mitschnitt-Port umschalten, ohne neu zu flashen: `tools/vebus_capture.py capture --script "0=L1,30=De4,60=A L0"` (`L0/L1` eigene Zeitbasis, `R0/R1/R2` Antwort auf `FC 0F`, `Dxx/Uxx/A` Rahmentyp auslassen oder wieder senden, `O<n>` Abstand der Sync-Zeit). Die Antwort mit `38` ist jetzt abgeschaltet (`fc_reply: "0"`). **Nicht geklärt:** Beim Flashen im Betrieb mit eigener Zeitbasis ist die Verbindung zum ESP abgerissen, danach war er nicht mehr erreichbar. Der zeitgenaue Sync sperrt kurz die Interrupts, ein Zusammenhang ist möglich. Vor dem Flashen deshalb `L0` senden.

**Flankenaufzeichnung, vorbereitet am 06.11.2026, am Gerät ungetestet.** Die Firmware `esphome/vebus-sniffer-edges.yaml` ist der passive Mitschnitt mit einem Zusatz (`esphome/vebus_edges.h`): Die RMT-Einheit des ESP32 misst am selben RX-Pin jede Flanke eines Rahmens auf 25 ns. Sie kann wie `vebus-sniffer.yaml` nicht senden. Aufgezeichnet wird zufällig jeder dritte Rahmen, als Zeile `E` im Log. Rahmen mit weniger als 0,3 ms Abstand landen in einem Datensatz.

Ablauf:

1. Noch auf der Werkbank flashen: `.\.venv\Scripts\esphome.exe run esphome\vebus-sniffer-edges.yaml --device 192.168.100.210`. Danach sendet der ESP nichts mehr, das DMC wird still.
2. Powerbank vom ESP ab, Labornetzteil aus.
3. Umverdrahten wie in „Verdrahtung“ oben: TXD des Wandlers von der Diode weg fest an VCC, A, B und GND an den VE.Bus. Das DMC hängt dabei nicht am Wandler und nicht am VE.Bus.
4. Powerbank an. Aufzeichnen: `python tools\vebus_capture.py capture --seconds 120`.
5. Auswerten: `python tools\vebus_capture.py edges logs\<datei>.log`. Die Tabelle zeigt je Rahmenart den Abstand der Bytes in Bit (8N1 ohne Pause = 10,00), die Bitdauer, die Lage der Flanken zum Bitraster und den kürzesten Puls. Darunter stehen Beispiele mit allen Pulsen.
6. Zurück auf die Werkbank: Verdrahtung aus „Werkbanktest“, `vebus-dmc-bridge.yaml` flashen.

**Erster Lauf auf der Werkbank, 06.11.2026** (`logs/vebus-20261106-edges-bench.log`, lokal): Die Messfirmware lief kurz am DMC, bevor umverdrahtet wurde. Ohne Bus sendet das DMC alle 500 ms nur seinen Rahmen `40`. 38 Rahmen, alle mit gültiger Prüfsumme dekodiert:

- **Bitdauer des DMC: 3985 ns, also etwa 250 900 Baud**, nicht 256 000. Der ESP sendet mit 3906 ns je Bit und ist damit 2 % schneller. Ein UART verträgt das bei Datenrahmen. Ob das DMC die Bitdauer im Sync (Byte `55`) enger prüft, ist die naheliegende nächste Frage.
- **Pause nach der Adresse:** Zwischen dem 2. und 3. Byte liegen 13 statt 10 Bit, also 3 Bit Pause. Alle anderen Bytes folgen dicht an dicht.
- **Fehler der Messfirmware:** Der UART empfängt neben der RMT-Einheit am selben Pin nichts mehr (0 Bytes). Die Flanken reichen für die Auswertung, die Zeilen `F` fehlen aber. Vor der Messung am VE.Bus beheben oder bewusst nur mit den Flanken arbeiten.

Gesucht wird alles, worin sich der Sync von den Datenrahmen oder vom Signal des ESP unterscheidet: Pausen zwischen den Bytes, ein zweites Stoppbit, zusätzliche Pulse, eine andere Bitdauer. Der ESP sendet 8N1 ohne Pausen mit 3906 ns je Bit. Die Auswertung ist bisher nur mit künstlichen Daten geprüft (`selftest`).

**Noch offen vor dem Einbau:** die häufigen `FC 0F` (Ursache eingegrenzt, siehe oben), die LEDs für Überlast, Batterie und Temperatur, die Ampere-Anzeige folgt nur dem Knopf, die dauerhafte Versorgung von ESP und DMC sowie die eigene Leitung zum DMC.

**Test:**
1. Flashen mit `write_enable: "false"`, Labornetzteil an, DMC auf Ein.
2. Die LEDs sollten zum MultiPlus passen. Schalter und Knopf erzeugen nur Log-Einträge.
3. Erst danach `write_enable: "true"` und die Reihe aus `docs/MULTIPLUS-SCHALTER.md`: DMC schaltet, CCGX/VRM/HA schalten, wieder DMC, jeweils LEDs und Zustand prüfen.

## Unterschied zum Betrieb

Der Mitschnitt hängt am echten VE.Bus. Im geplanten Betrieb (`docs/DMC-RECHERCHE.md`, Abschnitt Vorgehen) kommt das DMC vom VE.Bus ab und bekommt ein **eigenes Kabel zum ESP**. Der ESP spielt dem DMC gegenüber den MultiPlus und schaltet den echten MultiPlus per WLAN über den GX. **Gesendet wird also nur zum DMC, nicht auf den VE.Bus.** Das alles ist noch ein Plan, ob das DMC damit läuft, klärt erst der Werkbanktest.

| | Mitschnitt | Betrieb |
|---|---|---|
| A+ und B− | VE.Bus Pin 4 und 5 | Pin 4 und 5 des DMC-Kabels |
| Versorgung des ESP | Powerbank | offen, siehe unten |
| Versorgung des DMC | aus dem VE.Bus | muss der Aufbau liefern, an Pin 2 und 3 des DMC-Kabels |
| 5 V am Modul, Teiler, GPIO16 | wie oben | unverändert |
| GPIO17, GPIO4, Pull-down | frei | laut „Umbau zum Senden“ |

- **Quelle offen:** Vermutlich abgesichertes Bordnetz mit Abwärtswandler auf 5 V, Pin 2 und 3 einer VE.Bus-Buchse nur, wenn die Messung unter „Versorgung über V+“ das hergibt. Der ESP muss den MultiPlus auch einschalten können, also auch im Aus-Zustand laufen. Bei Bordnetz keine Verbindung zu VE.Bus-Pin 3 herstellen, solange die Massen nicht geprüft sind.
- **Spannung für das DMC offen:** Falls es an V+ hängt, bekommt es heute höchstens die gemessenen 9 V. Ob es die Batteriespannung bis ca. 14 V verträgt, ist nicht bekannt. Vor dem Anschluss klären.
- **R14 am Betriebsmodul:** entfernen. Die kurze Leitung zum DMC braucht vermutlich keinen Abschluss, und er würde den Sendestrom deutlich erhöhen.
- **R11 und R12 am Betriebsmodul vorerst drauflassen:** Auf der eigenen Leitung hält sonst niemand den Ruhepegel, wenn weder ESP noch DMC senden. Ob die Pull-Widerstände nötig sind, zeigt der Werkbanktest.

## Versorgung über V+ (vorerst nicht verwendet)

Ursprünglich sollte der ESP aus V+ laufen. Rudi hat am 05.11.2026 an der Buchse des DMC, bei abgezogenem DMC, nur **9,0 V ohne Last** gemessen; der MultiPlus lief laut Home Assistant im Ladebetrieb bei 13,6 V Batteriespannung. Die Ursache ist nicht geklärt. esp32ess hat an einem anderen MultiPlus 11,65 V Leerlauf und ca. 39 Ω Innenwiderstand gemessen. Der Innenwiderstand an dieser Anlage ist unbekannt, und mit angestecktem DMC ist noch nicht gemessen. Deshalb läuft der Mitschnitt von der Powerbank.

Falls V+ später doch in Frage kommt, zuerst messen: DMC und GX angeschlossen, an einer freien Buchse.

1. Spannung Pin 2 gegen Pin 3 ohne Last messen: V0.
2. 270 Ω (mindestens 1 W) wenige Sekunden zwischen Pin 2 und Pin 3: V1 messen. Innenwiderstand R = (V0 − V1) / (V1 / 270).
3. Während der Probe prüfen: DMC-Anzeige normal, GX zeigt den MultiPlus weiter an, kein Alarm. Sonst Widerstand sofort entfernen.

Die Probe zieht V+ kurz herunter, deshalb nur, wenn ein kurzer Aussetzer der 230 V nicht stören würde. Der Aufbau bräuchte aus V+ grob geschätzt 0,35–0,45 W, mit Abwärtswandler auf 5 V, Schottky-Diode und Elkos für die WLAN-Spitzen. Ob das geht, ergibt sich aus V0 und R. Die frühere Grenze von 9 V unter Last ist mit 9,0 V Leerlauf nicht einzuhalten.

## Inbetriebnahme

1. ESP per USB am PC flashen, noch **ohne** Bus:

   ```bash
   .\.venv\Scripts\esphome.exe run esphome\vebus-sniffer.yaml --device COMx
   ```

   Im Log stehen die WLAN-Adresse, „TCP-Stream auf Port 8484" und der WireGuard-Handshake. Das WLAN nutzt dieselben Zugangsdaten wie die anderen ESPs, die Adresse kommt dort per DHCP. Über WireGuard (eigener Fritzbox-Peer) ist der ESP fest unter **192.168.100.210** erreichbar, wie Alde-ESP (.202) und Proxy (.208).
2. Vom PC abziehen, Powerbank anstecken, Schaltung an den Bus anschließen. Manche Powerbanks schalten bei kleinem Strom ab, dann verschwindet der ESP aus dem WLAN. Das Log gibt es nun per WLAN (`esphome logs`). Alle 30 s meldet es die Zähler. Erwartet: **50 Sync pro Sekunde**, UART-Fehler und Überläufe bleiben bei 0. Viele UART-Fehler und kein Sync: A und B tauschen, das ist beim reinen Empfang unkritisch.
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
4. Schalter: Ein → Aus, 1 Minute warten, → Ein. Gemessen am 05.11.2026: Der Bus verstummt etwa 2 s nach „Aus" vollständig und V+ fällt auf 2,2 V, siehe „Ergebnisse".
5. Mit Landstrom: dasselbe, und Landstrom einmal ab und wieder an. So sieht man die LED- und Stromrahmen in allen Zuständen.
6. Einmal das RJ45-Kabel des DMC ziehen und wieder stecken: Das zeigt, was beim Start des DMC ausgetauscht wird. Vorsicht: Der MultiPlus kann dabei seinen Zustand ändern, deshalb nur, wenn eine kurze Unterbrechung der 230 V nicht stört.

## Auswertung

```bash
.\.venv\Scripts\python.exe tools\vebus_capture.py analyze logs\vebus-<Datei>.log
```

Ergibt je Adresse und Befehl: Anzahl, Prüfsummenfehler, Varianten, mittleren Abstand und die Lage nach dem Sync in ms. Dazu kommt die Zeitachse der Änderungen an Panel-Rahmen 0x40 und LED-Rahmen 0x41, die sich mit den notierten Aktionen vergleichen lässt.

Die Dekodierung von 0x40 und 0x41 stammt aus dem MK2-Dokument und der ve.bus-library. Die Schalterstellungen und die Stromgrenze passen zu den Handgriffen im Mitschnitt vom 05.11.2026, die LED-Bits sind noch nicht einzeln geprüft.

## Ergebnisse vom 05.11.2026

Mitschnitt `logs/vebus-20261105-171337.log` (lokal, nicht im Repo), etwa 8 Minuten mit Drehknopf und Schalter, Landstrom vorhanden. **R14 (120 Ω) war dabei noch auf dem Modul.** MultiPlus und CCGX liefen danach normal weiter. Über die Wirkung von R14 auf die übrigen Geräte sagt das nur begrenzt etwas aus.

- **Teilnehmer:** `8383` MultiPlus, `98F7` CCGX, **`F0F7` DMC**.
- **DMC, Rahmen `40`, etwa alle 500 ms:** erstes Datenbyte `18` Ladegerät, `1A` Ein, `1B` Aus. Die beiden nächsten Bytes sind die Stromgrenze in 0,1 A, niedriges Byte zuerst (`A0 00` = 16,0 A).
- **Drehknopf:** Am Anschlag unten sendet das DMC kurz `00 00` (0,0 A). Der MultiPlus begrenzt das auf 3,1 A. Der niedrigste am DMC abgelesene Wert war 3,5 A. Die Übersetzung nach Modbus muss also begrenzen und darf nicht blind 0 schreiben.
- **MultiPlus, Rahmen `41`:** Schalterbyte `77` Ein, `74` und dann `44` Aus, `55` Ladegerät. Die Untergrenze ist bei Ein 3,1 A, bei Aus und Ladegerät 0,0 A.
- **Aus:** Etwa 2 s nach dem Umschalten **verstummt der ganze Bus**, auch DMC und CCGX. In Home Assistant bleiben die letzten Werte stehen, die Anzeige hängt ohnehin etwa 30 s nach.
- **Wieder Ein:** Der MultiPlus startet den Bus **zuerst**, etwa 0,6 s vor dem ersten Rahmen `40` des DMC. Das passt zur Messung an Pin 6 unten: Das Einschalten läuft über die Standby-Leitung, nicht über einen VE.Bus-Rahmen.
- **Spannungen gegen Pin 3, DMC angeschlossen, Multimeter im Bereich V DC:**

  | Schalter | Pin 2 (V+) | Pin 6 (Standby) | Pin 7 (Panel Detect) |
  |---|---|---|---|
  | Ein | 8,35 V | 0 V | 0 V |
  | Aus | 2,2 V | 12,5 V | 0 V |
  | Ladegerät | 8,85 V | 0 V | 0 V |

  Deutung: Pin 7 liegt fest auf GND und meldet das Bedienteil. Bei Ein und Ladegerät liegt Pin 6 auf GND, bei Aus nicht. Dann fällt V+ zusammen und das DMC verliert vermutlich seine Versorgung. Wer Pin 6 zieht, ist nicht gemessen, sehr wahrscheinlich das DMC. Die Spannungen gelten für die Messung am 05.11.2026 mit Landstrom. Beide Punkte zählen für den Betrieb: **Pin 6 führt bis 12,5 V und darf nie direkt an einen GPIO, und V+ kann einen ESP im Aus-Zustand nicht versorgen.**
- **Start des Busses:** Die Rahmennummern beginnen bei 0, das DMC meldet sich früh mit `F0F7 FC 0F 00 07`.
- **Zähler:** 58.154 Rahmen, davon 21.226 Sync und 10 mit Prüfsummenfehler, keine Überläufe.
- **Rahmen `00 FB xx`:** Genau diese 10 kurzen Rahmen werden als Fehler gezählt, sie kommen nur rund um Zustandswechsel vor. Die Summe aller Bytes vor `FF` ist immer `0x17A`, das spricht für ein festes Muster. In derselben Zeit stieg der UART-Fehlerzähler ebenfalls um 10. Ob es echte Rahmen oder Empfangsfehler sind, ist offen. Alle übrigen Rahmen hatten keine Prüfsummenfehler.

**Ohne DMC:** Nach dem Abziehen des DMC meldete Home Assistant den MultiPlus ab 17:34 als aus und seine Werte ab 17:41 als nicht verfügbar. Nach „System neu erkennen“ am CCGX lässt er sich laut Rudi (05.11.2026) wieder über CCGX und VRM schalten, auch von Aus zurück auf Ein. Damit ist die Grundlage des Umbaus bestätigt. Die Ursache des Ausfalls ist nicht geklärt, und ein Mitschnitt dieses Zustands liegt nicht vor. Beim Umbau also einplanen: DMC abziehen, danach sofort neu erkennen und prüfen.

**Noch offen:**
- R14 ausbauen und vergleichen.
- Start des DMC mitschneiden (Punkt 6 oben).
- Für Schritt 2: wie der ESP dem DMC „Aus" darstellt und ob das DMC dauerhafte Versorgung im Aus-Zustand verträgt, denn am echten MultiPlus verliert es sie.

## Stand

| Punkt | Stand 05.11.2026 |
|---|---|
| Firmware `esphome/vebus-sniffer.yaml`, `esphome/vebus_sniffer.h` | per USB geflasht (COM9), läuft und empfängt den VE.Bus |
| `tools/vebus_capture.py` | Selbsttest OK: echte Beispielrahmen aus esp32ess, TCP-Strecke mit Testserver, Wiederverbinden |
| Versorgung | Mitschnitt von der Powerbank. V+ gemessen 9,0 V ohne DMC, mit DMC 8,35–8,85 V, bei Aus 2,2 V. V+ scheidet als Versorgung des ESP aus |
| WireGuard 192.168.100.210 | Peer in der Fritzbox angelegt, Handshake im Log erfolgreich (05.11.2026, WLAN WDS6G) |
| Mitschnitt an der Anlage | erster Lauf mit Drehknopf und Schalter erfolgreich, noch mit R14 auf dem Modul; siehe „Ergebnisse" |
