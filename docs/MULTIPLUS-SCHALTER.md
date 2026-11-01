# MultiPlus EIN/AUS per Taster am Womo-BLE-Proxy

Stand 01.11.2026. Ersetzt das **Digital Multi Control (DMC)** durch einen federnden Schalter `(EIN)–0–(AUS)` am ESP32 „Womo BLE-Proxy". Grundlage: Konzept „MultiPlus-II 12/3000 im Wohnmobil: lokale und entfernte Ein-/Aus-Steuerung, letzter Befehl gewinnt" (Rudi, 31.10.2026), angepasst an die gemessene Anlage.

## Anlage (gemessen 01.11.2026 über MQTT am GX)

| Punkt | Wert |
|---|---|
| GX | **Color Control GX**, Produkt-ID C001, HQ18265EVPR, Firmware **v3.90-beta9** (Backup v3.56) |
| GX im Womo-WLAN | **192.168.1.242 fest** seit 01.11.2026 (vorher 192.168.1.25 per DHCP; der Nighthawk M5 kann keine Reservierung). Signal 57 % |
| GX über WireGuard | 192.168.100.209 (nur für HA zu Hause, nicht für den Taster) |
| Wechselrichter | MultiPlus 12/3000/120-16, VE.Bus-Instanz 257, Firmware 1362, über MK3 an `/dev/ttyO1` |
| DMC | angeschlossen, Version 1120120 |
| `/Mode` | 4 (Aus), wirkungslos: `/ModeIsAdjustable` = 0, Zustand 9 = Wechselrichten |
| Modbus TCP | **an** seit 01.11.2026; VE.Bus-Dienst `com.victronenergy.vebus.ttyO1` = **Unit-ID 246**. Lesetest Register 33 = 4 |
| Proxy-ESP | Innenraum, 192.168.1.241, WLAN −63 dBm |

Fernbedienung gibt es schon doppelt: VRM Remote Console und in Home Assistant `select.multiplus_12_3000_120_16_id_257` (on / off / charger_only / inverter_only) über die `victron_mqtt`-Instanz des GX. Beide sind wie der Taster gesperrt, solange das DMC erkannt ist.

## Ablauf eines Tastendrucks (Firmware `esphome/womo-ble-proxy.yaml` + `esphome/womo_modbus.h`)

1. GPIO25 (EIN) oder GPIO26 (AUS) wird gegen GND geschlossen, interner Pull-up, 50 ms Entprellung.
2. Nur die Druckflanke zählt. Beide gleichzeitig: kein Befehl. In den ersten 10 s nach dem Start: kein Befehl.
3. Eine eigene FreeRTOS-Task öffnet eine TCP-Verbindung zu `${gx_ip}:502` (max. 2 s), schreibt **einmal** Register 33 mit 3 (Ein) oder 4 (Aus), Funktion 06, Unit-ID `${vebus_unit_id}`, wartet max. 2 s auf die Bestätigung und schließt.
4. Keine Wiederholung bei Fehlern, kein zyklisches Schreiben, nichts beim Start oder nach WLAN-Wiederkehr. Ein Tastendruck, während noch ein Befehl läuft, wird verworfen.
5. Ergebnis in HA: `text_sensor` „MultiPlus letzter Tasterbefehl" (`EIN bestaetigt`, `AUS Fehler: Modbus-Ausnahme 1` usw.), Tasterzustände als Binärsensoren.

Damit gilt: Der zuletzt **vom GX verarbeitete** Befehl bestimmt den Zustand, egal ob vom Taster, vom GX-Menü, aus VRM oder aus HA.

## Verdrahtung

```text
Schalter Kontakt EIN ── GPIO25
Schalter Kontakt AUS ── GPIO26
Schalter gemeinsam  ── GND
```

Keine Spannung an die Kontakte legen. Bei langer Leitung externe 10-kΩ-Pull-ups nach 3,3 V und verdrillte Leitung. Keine Leitung zum MultiPlus nötig, der Weg läuft über WLAN, GX und VE.Bus.

## Inbetriebnahme (Reihenfolge)

| # | Schritt | Wer | Stand |
|---|---|---|---|
| 1 | DMC vom MultiPlus abklemmen | Rudi | offen |
| 2 | GX: Einstellungen → VE.Bus-System → Erweitert → **System neu erkennen**, ggf. GX neu starten | Rudi | offen |
| 3 | Prüfen: `vebus/257/ModeIsAdjustable` = 1, Ein/Aus im GX-Menü und in VRM wirkt | Claude/Rudi | offen |
| 4 | Landstrom-Stromgrenze, die bisher am DMC-Drehknopf stand, über GX/VRM/HA einstellen | Rudi | offen |
| 5 | GX: Modbus TCP einschalten und Unit-ID ablesen | Claude | erledigt 01.11. per MQTT (`W/…/settings/0/Settings/Services/Modbus` = 1), Unit-ID 246 |
| 6 | GX: feste Adresse 192.168.1.242 | Claude | erledigt 01.11. per MQTT, siehe unten; WireGuard-Tunnel blieb stehen |
| 7 | Proxy per OTA flashen | Claude | erledigt 01.11. 07:35; Entitäten „MultiPlus Taster EIN/AUS" und „MultiPlus letzter Tasterbefehl" in HA vorhanden |
| 8 | Testplan aus dem Konzept: lokal EIN → VRM AUS → lokal EIN → … , ESP-Neustart ohne Tastendruck, WLAN-Unterbrechung | Rudi + Claude | offen |

## Grenzen

- Der Taster braucht WLAN und einen laufenden GX. Fallen Nighthawk oder GX aus, bleibt der Hauptschalter am MultiPlus.
- „Aus" beendet Wechselrichten **und** Laden. Für Laden ohne Wechselrichter wäre `Nur Ladegerät` (1) die Betriebsart; der Taster kennt nur Ein und Aus.
- Keine Sicherheitsfunktion: BMS-Sperren, Sicherungen und Hauptschalter bleiben vorrangig. Eine Modbus-Bestätigung heißt nicht, dass der MultiPlus tatsächlich anläuft.
- Modbus TCP hat keine Authentifizierung. Port 502 nur im Womo-WLAN, nicht über den WireGuard-Tunnel freigeben.
- Der CCGX läuft mit einer Beta-Firmware jenseits der von Victron für den CCGX empfohlenen v3.55. Register 33 ist dort unverändert, Verhalten trotzdem im Test prüfen.

## Netzwerk des GX per MQTT ändern (ohne SSH, 01.11.2026)

Der CCGX nimmt Netzwerkbefehle über `W/<Portal-ID>/platform/0/Network/SetValue` an, Wert ist ein JSON-String mit dem connman-Dienst (aus `N/…/platform/0/Network/Services`) und **genau einer** Eigenschaft je Befehl:

```text
{"Service": "/net/connman/service/wifi_000f00799613_5744533647_managed_psk", "Method": "manual"}
{"Service": "/net/connman/service/wifi_000f00799613_5744533647_managed_psk", "Address": "192.168.1.242"}
```

`Method: manual` übernimmt die laufenden DHCP-Werte (Netzmaske, Gateway, DNS) als feste Konfiguration. Mehrere Eigenschaften in einem Befehl funktionieren nicht: venus-platform setzt jede einzeln auf Basis der *aktuellen* Konfiguration, die späteren Felder schreiben die alte Adresse zurück (so beim ersten Versuch passiert, ohne Folgen). Zurück auf DHCP: `{"Service": "…", "Method": "dhcp"}` oder am GX-Display unter Einstellungen → WLAN.

Root-SSH lehnt das von Rudi genannte Passwort ab (Passwort und keyboard-interactive), obwohl der Server beide Verfahren anbietet. Für Taster und Netzwerk wird SSH nicht gebraucht.
