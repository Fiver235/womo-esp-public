# Lokale ESPHome-Komponenten

## truma_inetbox

Kopie von https://github.com/Fabian-Schmidt/esphome-truma_inetbox, Branch `alde`,
Commit `40bcbc96498f939a02ee6f4ee9acc043cb98f691` (2024-04-06, "alde changes"), MIT-Lizenz.

Lokale Aenderungen gegenueber dem Original:

- `__init__.py`: `CORE.using_esp_idf` -> `CORE.using_toolchain_esp_idf`, `CORE.is_rp2040` -> `CORE.is_rp2`
  (Attribute in ESPHome 2026.x umbenannt; ohne den Patch bricht `to_code` mit AttributeError ab).

Dies ist die Basis fuer den Track-B-Fork (Alde-Befehlspuffer 0x50, siehe ../../docs/TRACK-B-INET-BUS.md).
- alle Quellen: `u_int8_t`/`u_int16_t`/`u_int32_t` -> `uint8_t`/`uint16_t`/`uint32_t`
  (BSD-Typen sind in der ESP-IDF-5.5-Toolchain nicht mehr deklariert).
- `LinBusListener_esp_idf.cpp`: `portTickType` -> `TickType_t` (FreeRTOS-Legacy-Name in ESP-IDF 5.x entfernt).
- `LinBusListener_esp_idf.cpp` komplett ersetzt durch die Fassung aus
  https://github.com/havanti/esphome-truma (Commit c463d7d, 2026-10-25, MIT): nutzt die
  Ersatz-`uart`-Komponente mit Event-Queue, korrekte `uart_port_t`-Casts, Task-Prioritaeten.

## uart

Kopie von https://github.com/havanti/esphome-truma `components/uart` (Commit c463d7d). Ersetzt die
eingebaute ESPHome-`uart`-Komponente fuer ESP-IDF um `truma_IDFUARTComponent`, das die
FreeRTOS-Event-Queue des UART-Treibers (`get_uart_event_queue()`) herausfuehrt; die
ESPHome-eigene IDFUARTComponent hat seit 2026 keine Queue mehr. Muss in `external_components`
mit aufgefuehrt werden: `components: [ truma_inetbox, uart ]`.

## B2-Patches (27.10.2026, aus dem Mitschnitt mit echter iNet Box)

Grundlage: `docs/TRACK-B-INET-BUS.md` Abschnitt 6.

| Datei | Änderung |
|---|---|
| `TrumaStructsAlde.h` | `unknown_01` → `aircon_auto` (Klimaautomatik, Bit 0x02), `unknown_10` → `aventa_light` (Bit 0x02, nur Status); Kommentare mit Messwerten |
| `TrumaiNetBoxAppAldeStatus.cpp` | `create_update_data`: 5. Byte `0x1A` statt `len+6`, Gesamtlänge `0x25`; `update_prepare`: `message_counter` = letzter 0x51-Zähler (ohne `+1`), `unknown_04 = 0xFFFF`, Flag-Bytes ohne Bit 0; neue Aktionen `action_heater_mode`, `action_water_mode`, `action_el_mode`, `action_gas_mode`, `action_heater_prio`, `action_aircon_auto`, `action_aventa_light` (Hypothese), `action_heater_room(float)` |
| `TrumaiNetBoxAppAldeNight.h/.cpp` (neu) | Nachtmodus: Status 0x55 speichern, Befehl 0x54 senden (`action_night_mode`, `action_night_temp`). Experiment, siehe Doku (ACK 0x02 bei „ein") |
| `TrumaiNetBoxApp.h/.cpp` | `alde_night_` registriert (Parent, update, reset, Sendepfad, 0x55-Handler, `has_update_to_submit_`) |

Die ESPHome-Entitäten für B2 sind als Template-Lambdas in `../alde-inetbox-b2.yaml` angelegt (kein eigener Platform-Code nötig).
