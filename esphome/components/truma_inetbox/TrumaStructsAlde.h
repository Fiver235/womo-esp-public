#pragma once

#include "TrumaEnums.h"
#include "TrumaEnumsAlde.h"

namespace esphome {
namespace truma_inetbox {

// Length 14 (0x0E) - MSG x0B
struct StatusFrameAldeDevice {  // NOLINT(altera-struct-pack-align)
  uint8_t device_count;
  uint8_t device_id;
  TRUMA_DEVICE_STATE state;
  // 0x00
  uint8_t unknown_1;
  uint16_t hardware_revision_major;
  uint8_t hardware_revision_minor;
  // `software_revision[0].software_revision[1].software_revision[2]`
  // software_revision[0] -> TRUMA_DEVICE
  uint8_t software_revision[3];
  // 0xAD, 0x0B on CPplus with Combi4 or 0x66 on CPplus with Vario Heat Comfort ohne E
  // 0x00 on Combi4, Vario Heat
  // 0x10 on Alde Paneel
  // 0x6D on Alde Compact 3020 HE
  uint8_t unknown_2;
  // 0x10, 0x12 on CPplus
  // 0x00 on Combi4, Vario Heat
  // 0x00 on Alde Paneel & Alde Compact 3020 HE
  uint8_t unknown_3;
  uint8_t unknown_4;
  uint8_t unknown_5;
} __attribute__((packed));

// Length 28 (0x1C) - MSG x51
// Feldbelegung bestaetigt am 27.10.2026 (Alde Compact 3020 HE + Aventa, echte iNet Box, siehe
// docs/TRACK-B-INET-BUS.md Abschnitt 6).
struct StatusFrameAldeStatus {  // NOLINT(altera-struct-pack-align)
  HeaterAlde heater_mode;
  // Bit 0 im Status immer gesetzt, Bit 1 (0x02) = Klimaautomatik (Aventa) ein -> 0x01 / 0x03.
  uint8_t aircon_auto;
  TargetTemp target_temp_room;
  uint16_t unknown_04;  // xFFFE
  WaterTempAlde water_mode;
  ElectricPowerLevelAlde el_mode;
  GasModeAlde gas_mode;
  HeaterPriorityAlde heater_prio;
  // Bit 0 im Status immer gesetzt, Bit 1 (0x02) = Aventa-Beleuchtung ein (nur am Panel schaltbar) -> 0x01 / 0x03.
  uint8_t aventa_light;
  uint8_t unknown_11;  // x64
  uint8_t unknown_12;  // xFF
  uint8_t unknown_13;  // xFF
  uint8_t unknown_14;  // xFF
  uint8_t message_counter;
  TargetTemp current_temp_inside;
  uint16_t unknown_18;  // xFFFE
  TargetTemp current_temp_outside;
  uint8_t unknown_22;   // x00
  uint8_t unknown_23;   // x1E
  uint16_t unknown_24;  // xFFFF
  uint16_t unknown_26;  // xFFFF
} __attribute__((packed));

// Length 16 (0x10) - MSG x50 - Befehl Box -> Panel, kompletter Sollzustand.
// Gemessen 27.10.2026 (17 Befehle der echten iNet Box): L-Byte der FA-Antwort = 0x1A, Gesamtlaenge 0x25,
// Byte 15 = message_counter des zuletzt empfangenen 0x51 (NICHT +1).
struct StatusFrameAldeStatusResponse {  // NOLINT(altera-struct-pack-align)
  HeaterAlde heater_mode;
  uint8_t aircon_auto;  // 0x02 = Klimaautomatik ein, 0x00 = aus (ohne Bit 0, anders als im Status)
  TargetTemp target_temp_room;
  uint16_t unknown_04;  // xFFFF (im Status xFFFE)
  WaterTempAlde water_mode;
  ElectricPowerLevelAlde el_mode;
  GasModeAlde gas_mode;
  HeaterPriorityAlde heater_prio;
  uint8_t aventa_light;  // gemessen immer 0x00; HYPOTHESE: 0x02 schaltet die Aventa-Beleuchtung (ungetestet)
  uint8_t unknown_11;  // x64
  uint8_t unknown_12;  // xFF
  uint8_t unknown_13;  // xFF
  uint8_t unknown_14;  // xFF
  uint8_t message_counter;  // = message_counter des letzten 0x51
} __attribute__((packed));

// Length 36 (0x24) - MSG x53
struct StatusFrameAldeAddon {  // NOLINT(altera-struct-pack-align)
  uint8_t unknown_00[15];
  TempSensorUsageAlde temp_sensor;
  uint8_t unknown_16[3];  // xFF
  uint8_t message_counter;
  uint8_t unknown_20[16];
} __attribute__((packed));

// Length 12 (0x0C) - MSG x55 (Status) und x54 (Befehl Box -> Panel, gleiche Struktur).
// Gemessen 27.10.2026: App "Nachtmodus ein" sendet weekday_end 0x07 -> 0x00 (Panel-ACK 0x02 = INVALID_MSG!),
// "Nachtmodus aus" weekday_end 0x07 (ACK 0x00). unknown_09 im Befehl 0x00 (Status 0x04),
// message_counter = Zaehler des letzten 0x55.
struct StatusFrameAldeHeaterNight {  // NOLINT(altera-struct-pack-align)
  TargetTemp target_temp_room;
  uint16_t mode_start_time;  // 0x03DE - 990/60 -> 16.5 -> 16:30
  uint16_t mode_end_time;    // 0x01C2 - 450/60 -> 07.5 -> 07:30
  WeekDayAlde weekday_start;
  WeekDayAlde weekday_end;
  uint8_t bits;        // 17 sensor bett, 7 sensor paneel / auto with night mode, 6 Night mode off, 3 hot water, 1
  uint8_t unknown_09;  // x03, x02, x01
  uint8_t unknown_10;  // 0xFF
  uint8_t message_counter;
} __attribute__((packed));

// Length 12 (0x0C) - MSG x57
struct StatusFrameAldeHeaterDay {  // NOLINT(altera-struct-pack-align)
  TargetTemp target_temp_room;
  uint16_t mode_start_time;  // 0x03DE - 990/60 -> 16.5 -> 16:30
  uint16_t mode_end_time;    // 0x04CE - 1230/60 -> 20.5 -> 20:30
  WeekDayAlde weekday_start;
  WeekDayAlde weekday_end;
  uint8_t bits;
  uint8_t unknown_09;  // 0x00
  uint8_t unknown_10;  // 0xFF
  uint8_t message_counter;
} __attribute__((packed));

// ALDE direct heater message structs

// ex: 5E.0B.00.FF.FF.FF.FF.FF
// ex: 40.0B.00
struct Heater_Alde_PID_03 {  // NOLINT(altera-struct-pack-align)
  TargetTemp temp;           // 15-18°C
  uint8_t unknown_02;       // 0x00
} __attribute__((packed));

// ex: AA.0A.FF.FF.FF.FF.FF.FF
struct Heater_Alde_PID_04 {  // NOLINT(altera-struct-pack-align)
  TargetTemp temp;           // 0°C
} __attribute__((packed));

// ex: 01.08.90.FF.FF.FF.FF.FF
// ex: 00.08.90
struct Heater_Alde_PID_05 {  // NOLINT(altera-struct-pack-align)
  uint8_t unknown_00;       // 0x01 - ? On or Off
  uint8_t unknown_01;       // 0x08
  uint8_t unknown_02;       // 0x90
} __attribute__((packed));

// ex: 00.00.2F.F5.FF.FF.FF.FF
// ex: 00.00.2F.F5
struct Heater_Alde_PID_06 {  // NOLINT(altera-struct-pack-align)
  uint8_t unknown_00;       // 0x00
  uint8_t unknown_01;       // 0x00
  uint16_t unknown_02;      // 0xF52F
} __attribute__((packed));

// ex: 58.0B.FF.FF.2B.00.20.44
// ex: 57.0B.FF.FF.2B.00.20.44
// ex: 55.0B.FF.FF.2B.00.20.44
// ex: 56.0B.FF.FF.2B.00.20.44
// ex: B8.0B.FF.FF.2B.00.20.44
struct Heater_Alde_PID_07 {  // NOLINT(altera-struct-pack-align)
  TargetTemp temp;           // 17.4-27-28.2°C
  uint16_t unknown_02;      // 0xFFFF
  uint8_t unknown_04;       // 0x2B
  uint8_t unknown_05;       // 0x00
  uint8_t unknown_06;       // 0x20
  uint8_t unknown_07;       // 0x44
} __attribute__((packed));

// ex: EE.0C.04.FF.FF.FF.FF.FF
// ex: DA.0C.04.FF.FF.FF.FF.FF
// ex: D0.0C.04.FF.FF.FF.FF.FF
// ex: E4.0C.04.FF.FF.FF.FF.FF
// ex: E0.0B.00
struct Heater_Alde_PID_13 {  // NOLINT(altera-struct-pack-align)
  TargetTemp temp;           // 30-31-56 - 58°C
  uint8_t unknown_02;       // 0x04
} __attribute__((packed));

// ex: 00.00.2F.F5.04.0B.FF.FF
// ex: 00.00.2F.F5.0E.0B.FF.FF
// ex: 00.00.2F.F5.C2.0B
struct Heater_Alde_PID_15 {  // NOLINT(altera-struct-pack-align)
  uint8_t unknown_00;       // 0x00
  uint8_t unknown_01;       // 0x00
  uint16_t unknown_02;      // 0xF52F
  TargetTemp temp;           // 9-10-28°C
} __attribute__((packed));

// ex: D0.0C.FF.7F.FF.7F.6D.00
// ex: DA.0C.FF.7F.FF.7F.6D.00
// ex: DA.0C.FF.7F.FF.7F.45.00
// ex: D6.0B.FF.7F.FF.7F.00.00
struct Heater_Alde_PID_1B {  // NOLINT(altera-struct-pack-align)
  TargetTemp temp;           // 30-55-57°C
  uint16_t unknown_02;      // 0x7FFF
  uint16_t unknown_04;      // 0x7FFF
  uint8_t unknown_06;       // 0x6D x45
  uint8_t unknown_07;       // 0x00
} __attribute__((packed));

}  // namespace truma_inetbox
}  // namespace esphome