# Digital Multi Control am ESP weiterverwenden – Recherche

Stand 01.11.2026. Frage: Kann das vorhandene **Digital Multi Control (DMC)** statt am VE.Bus an einem ESP32 hängen, sodass Schalter und Drehknopf weiter funktionieren, der Color Control GX aber nicht gesperrt ist und „letzter Befehl gewinnt" gilt (siehe `docs/MULTIPLUS-SCHALTER.md`)?

## 1. Was bei Victron offen ist und was nicht

| Teil | Offen? | Beleg |
|---|---|---|
| Venus OS (GX-Software): Oberfläche gui-v2, venus-platform, viele D-Bus-Treiber | ja, GitHub `victronenergy` | dbus-api-Wiki [3] |
| **mk2-dbus**, der VE.Bus-Treiber des GX (setzt `/ModeIsAdjustable`, sperrt bei DMC) | **nein** | im Wiki ohne Link = „not (yet) open sourced" [3]; Repo existiert nicht öffentlich |
| Firmware von MultiPlus, DMC, MK3 | nein | – |
| **MK2-Protokoll** (PC ↔ MK2/MK3-Schnittstelle) | **offiziell dokumentiert** | Victron-PDF 3.14 [1] |
| VE.Bus auf der Leitung (RS485-Rahmen zwischen den Geräten) | nicht offiziell; von der Community entschlüsselt | esp32ess [5], ve.bus-library [6] |
| Hardware-Schaltplan VE.Bus-Anschluss (Venus GX Cape) | ja | venusgx-hardware [7] |

Victron rät selbst, nie direkt auf dem VE.Bus zu sprechen, sondern über MK2/MK3 [1, Community-Antwort]. „Quelloffen" stimmt also für die GX-Software, aber genau das Stück, das die DMC-Sperre macht, und das Leitungsprotokoll sind es nicht.

## 2. Offiziell bestätigt: GX-Schalter gesperrt, solange ein DMC da ist

- Victron-Handbuch: *„The On/Off and Charger Only controls on the GX device are disabled when a DMC is present."* Der GX merkt sich das auch nach dem Entfernen, bis „System neu erkennen" [4].
- Für ältere Multi/Quattro/EasySolar (also den MultiPlus 12/3000/120-16) kann der **Remote-On/Off-Anschluss nicht zusammen mit einem GX** benutzt werden; nur MultiPlus-II/Quattro-II dürfen das [4].
- Gemessen am Womo: `vebus/257/Devices/Dmc/Version` = 1120120, `/ModeIsAdjustable` = 0.

Folge: Am echten VE.Bus kann das DMC nicht bleiben, wenn der GX schalten soll.

## 3. Was über die DMC-Kommunikation bekannt ist

**Aus dem offiziellen MK2-Dokument [1]:**
- **Panel-Rahmen 0x40** (vom DMC gesendet, auf dem VE.Bus): Byte 0 = Panel- und Schalterinfo (Schalterstellung, Rahmenformat-Bit 3, Generator-Bit), dann entweder *Pot-Wert + Panel-Skala* (Standardformat) oder *absolute Stromgrenze in 0,1 A* (erweitertes Format). Schalterstellung 1 = nur Ladegerät, 2 = nur Wechselrichter, 3 = Ein, 4 = Aus (erweitert: +1).
- Panel-Zustand wird typischerweise **alle ½ s** gesendet.
- **MasterMultiLED-Rahmen 0x41** (vom MultiPlus): LED-Zustände, AC-Eingangskonfiguration mit Bits „DMC dedicated" und „Remote panel detected", minimale/maximale/aktuelle Eingangsstromgrenze (0,1 A), Schalterregister. Daraus kann ein DMC seine LEDs und den Bereich des Drehknopfs ableiten.
- RJ45-Steuerleitungen: **Pin 7 „Panel detect"** (auf GND = Fernbedienteil vorhanden, Gerät startet erst nach Ein-Befehl) und **Pin 6 „Standby"**.

**Aus der Community [5, 6]:**
- 256000 Baud, 8N1, RS485.
- Der MultiPlus sendet **alle 20 ms einen Sync-Rahmen** (`83 83 FD <Nr> 55 … FF`); andere Teilnehmer senden in Zeitfenstern danach (ve.bus-library: 8,0–9,5 ms nach Sync).
- Datenrahmen `<Adresse 2 Byte> FE <Nr> <Befehl> … <Prüfsumme> FF`, Byte-Stuffing für 0xFA–0xFF, 8-Bit-Prüfsumme. Adresse 0x8383 = MultiPlus, 0x98F7 = MK3.
- Versorgung im RJ45: rund **12 V, max. ca. 700 mW** vom MultiPlus (gemessen 11,65 V, ca. 39 Ω Innenwiderstand) [5].
- **Pinbelegung laut Victron-Schaltplan [7], Seite 2:** 1 frei, 2 V+, 3 GND, 4 A, 5 B, 6 Standby, 7 Panel Detect, 8 frei. esp32ess stimmt damit überein, die Angabe A = 3, B = 4, GND = 5 in der ve.bus-library nicht.

**Nicht gefunden:** Ein Projekt, das gegenüber einem DMC den MultiPlus nachbildet. Alle Projekte sprechen *mit* dem MultiPlus, nicht *als* MultiPlus.

## 4. Lösungsweg „DMC am ESP"

```text
DMC ──RJ45/RS485 (eigenes Kabel)── ESP32 ──WLAN/Modbus TCP── Color Control GX ──VE.Bus── MultiPlus
     ◄ Sync alle 20 ms, 0x41 LEDs/Stromgrenzen          ▲ Zustand lesen (Register/MQTT)
     ► 0x40 Schalter + Knopf                              ▼ bei Änderung EINMAL schreiben
```

- Der ESP spielt gegenüber dem DMC den MultiPlus: Sync-Rahmen, LED-/Stromgrenzen-Rahmen aus dem echten Zustand (vom GX gelesen).
- DMC-Schalter **ändert sich** → ein Schreibbefehl Register 33 (`/Mode`: 1 Ladegerät, 3 Ein, 4 Aus). Drehknopf ändert sich → Eingangsstromgrenze (Register 22 `/Ac/ActiveIn/CurrentLimit`, vorher prüfen, ob schreibbar).
- Der GX sieht kein DMC mehr → Modus frei, VRM und Home Assistant schalten mit.
- **Einschränkung:** Der DMC-Schalter rastet. „Letzter Befehl gewinnt" gilt nur über Stellungswechsel: Hat HA ausgeschaltet und die Wippe steht noch auf Ein, muss man einmal Aus–Ein schalten. Die LEDs zeigen trotzdem den echten Zustand.

### Vorgehen

1. **Passiver Mitschnitt** am bestehenden VE.Bus (nur Empfänger, sendet nichts; DMC bleibt dran): alle Rahmen mit Zeitstempel, dabei Schalter und Knopf bedienen. Ziel: welche Rahmen das DMC sendet und welche des MultiPlus es auswertet (0x41, 0x80, E4, Adressierung).
2. **Werkbank:** DMC an eigenem Kabel am ESP, 12 V über abgesicherte Leitung, ESP sendet Sync + mitgeschnittene MultiPlus-Rahmen. Prüfen, ob das DMC ohne Fehleranzeige läuft und LEDs/Display reagieren.
3. Übersetzung DMC ↔ Modbus, Einbau, Testplan aus `MULTIPLUS-SCHALTER.md`.

**Hardware:** Entscheidung Rudi 05.11.2026: **eigener neuer ESP32** für alle Schritte, der Proxy bleibt unberührt. Dazu RS485-Transceiver für 3,3 V und 256 kBaud (z. B. MAX3485/SP3485; Abschluss- und Bias-Widerstände auf dem Modul entfernen, laut [5, 6]) und ein RJ45-Anschluss. Verdrahtung und Ablauf von Schritt 1: `docs/VEBUS-MITSCHNITT.md`.

### Risiken

- Das DMC erwartet eventuell mehr als Sync und 0x41 (Geräteabfrage, Versionsrahmen); dann muss mehr nachgebildet werden. Klärt Schritt 1.
- Falsche Verdrahtung kann ESP oder DMC beschädigen; daher trotz Schaltplan erst messen. Die Masse der VE.Bus-Schnittstelle nicht ungeprüft mit dem Bordnetz verbinden.
- Firmware-Änderungen von Victron können das Verhalten ändern (kein offizielles Protokoll).

## 5. Vergleich

| | Federschalter (fertig) | DMC am ESP |
|---|---|---|
| Aufwand | erledigt, nur verdrahten | Mitschnitt, Auswertung, Nachbildung, eigener ESP |
| Bedienung | Ein/Aus tastend | Ein/Aus/Ladegerät rastend, Stromgrenzen-Knopf, 8 LEDs, Display |
| Letzter Befehl gewinnt | direkt | nur über Stellungswechsel |
| Risiko | gering | mittel, Protokoll inoffiziell |

## Quellen

1. Victron, *Interfacing with VE.Bus products – MK2 Protocol 3.14*: https://www.victronenergy.com/upload/documents/Technical-Information-Interfacing-with-VE-Bus-products-MK2-Protocol-3-14.pdf (Abschnitte 3.5, 5, 5.1, 6.2)
2. Victron, *Digital Multi Control 200/200A GX*, Handbuch rev 00, 10/2023: https://www.victronenergy.com/upload/documents/Digital_Multi_Control_GX/153833-Digital_Multi_Control-pdf-en.pdf
3. Victron Venus-Wiki, *dbus api*: https://github.com/victronenergy/venus/wiki/dbus-api
4. Victron GX-Handbuch, *Connecting Victron products* und *Troubleshooting*: https://www.victronenergy.com/media/pg/Venus_GX/en/connecting-victron-products.html, https://www.victronenergy.com/media/pg/CCGX/en/troubleshooting.html
5. pv-baxi, *esp32ess* (VE.Bus-Protokoll, Pinbelegung, Versorgung): https://github.com/pv-baxi/esp32ess
6. mkrasselt1, *ve.bus-library* (ESP32, Sync-Fenster, Rahmen 0x41/0x80): https://github.com/mkrasselt1/ve.bus-library, Vorläufer PepeTheFroggie: https://github.com/PepeTheFroggie/Victron-VE.Bus---esp32
7. Victron, *venusgx-hardware* (VE.Bus-Anschluss, Schaltplan Seite 2): https://github.com/victronenergy/venusgx-hardware/blob/master/VE_BBB_Cape_v0.80_released.pdf
8. Victron Community, *Open-Source ESP32-Bibliothek für VE.Bus RS485*: https://community.victronenergy.com/t/open-source-esp32-bibliothek-fur-ve-bus-rs485-multiplus-direkt-steuern-ohne-cerbo-gx/56431
