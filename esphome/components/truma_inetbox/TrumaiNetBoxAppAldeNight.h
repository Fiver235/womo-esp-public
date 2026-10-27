#pragma once

#include "TrumaStausFrameResponseStorage.h"
#include "TrumaStructs.h"

namespace esphome {
namespace truma_inetbox {

// Alde-Nachtmodus: Status 0x55 (Panel -> Box) und Befehl 0x54 (Box -> Panel, gleiche 12-Byte-Struktur).
// EXPERIMENT (27.10.2026): Die echte App sendete fuer "Nachtmodus ein" weekday_end = 0x00, das Panel
// quittierte mit ACK-Code 0x02 (INVALID_MSG); "aus" (weekday_end = 0x07) wurde mit 0x00 quittiert.
// Die Komponente setzt die Box nach einem ACK-Fehler zurueck (Re-Init), das ist beim Test einzuplanen.
class TrumaiNetBoxAppAldeNight
    : public TrumaStausFrameResponseStorage<StatusFrameAldeHeaterNight, StatusFrameAldeHeaterNight> {
 public:
  StatusFrameAldeHeaterNight *update_prepare() override;
  void create_update_data(StatusFrame *response, uint8_t *response_len, uint8_t command_counter) override;
  void dump_data() const override;
  bool can_update() override;

  // Nachtmodus ein/aus, Kodierung wie von der App gesendet (weekday_end 0x00 / 0x07).
  bool action_night_mode(bool on);
  // Nacht-Solltemperatur.
  bool action_night_temp(float temperature);
};

}  // namespace truma_inetbox
}  // namespace esphome
