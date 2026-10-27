#pragma once

#include "TrumaStausFrameResponseStorage.h"
#include "TrumaStructs.h"

namespace esphome {
namespace truma_inetbox {

// Alde-Status 0x51 (Panel -> Box) und Befehl 0x50 (Box -> Panel).
// Befehlsformat gemessen am 27.10.2026 mit echter iNet Box, siehe docs/TRACK-B-INET-BUS.md Abschnitt 6.
class TrumaiNetBoxAppAldeStatus : public TrumaStausFrameResponseStorage<StatusFrameAldeStatus, StatusFrameAldeStatusResponse> {
 public:
  StatusFrameAldeStatusResponse *update_prepare() override;
  void create_update_data(StatusFrame *response, uint8_t *response_len, uint8_t command_counter) override;
  void dump_data() const override;
  bool can_update() override;

  // Soll-Raumtemperatur (ganze Grad). 0 oder < 5 wird als "aus" kodiert, die Heizung bleibt aber ein.
  bool action_heater_room(uint8_t temperature);
  // Soll-Raumtemperatur in 0,5-Grad-Schritten (wie die Truma-App).
  bool action_heater_room(float temperature);
  // Heizung ein/aus (Byte 0).
  bool action_heater_mode(bool on);
  // Warmwasser aus / normal / boost (Byte 6).
  bool action_water_mode(WaterTempAlde mode);
  // Elektro 0 / 1 / 2 / 3 kW (Byte 7).
  bool action_el_mode(ElectricPowerLevelAlde level);
  // Gas ein/aus (Byte 8).
  bool action_gas_mode(bool on);
  // Prioritaet Gas / Elektro (Byte 9). Nicht gemessen, Belegung aus dem Status uebernommen.
  bool action_heater_prio(HeaterPriorityAlde prio);
  // Klimaautomatik (Aventa) ein/aus (Byte 1, 0x02).
  bool action_aircon_auto(bool on);
  // EXPERIMENT: Aventa-Beleuchtung (Byte 10, 0x02). Nur im Status beobachtet, als Befehl ungetestet.
  bool action_aventa_light(bool on);
};

}  // namespace truma_inetbox
}  // namespace esphome
