#include "TrumaiNetBoxAppAldeStatus.h"
#include "TrumaStatusFrameBuilder.h"
#include "esphome/core/log.h"
#include "helpers.h"
#include "TrumaiNetBoxApp.h"

namespace esphome {
namespace truma_inetbox {

static const char *const TAG = "truma_inetbox.TrumaiNetBoxAppAldeStatus";

// Gemessene Konstanten der FA-Antwort der echten iNet Box (27.10.2026).
static constexpr uint8_t ALDE_RESPONSE_HEADER_LENGTH = 0x1A;  // 5. Byte der Antwort, unabhaengig von len
static constexpr uint8_t ALDE_RESPONSE_TOTAL_LENGTH = 0x25;   // 37 Byte, Rest mit 0x00 aufgefuellt
static constexpr uint8_t ALDE_FLAG_BIT = 0x02;                // Klimaautomatik / Beleuchtung

StatusFrameAldeStatusResponse *TrumaiNetBoxAppAldeStatus::update_prepare() {
  // An update is currently going on.
  if (this->update_status_prepared_ || this->update_status_stale_) {
    return &this->update_status_;
  }

  // Der Befehl ist der komplette Sollzustand: letzten Status spiegeln, dann einzelne Felder aendern.
  this->update_status_ = {};
  this->update_status_.heater_mode = this->data_.heater_mode;
  // Status 0x01/0x03 -> Befehl 0x00/0x02 (Bit 0 nur im Status).
  this->update_status_.aircon_auto = this->data_.aircon_auto & ALDE_FLAG_BIT;
  this->update_status_.target_temp_room = this->data_.target_temp_room;
  this->update_status_.unknown_04 = 0xFFFF;  // Status: 0xFFFE, Befehl: 0xFFFF (gemessen)
  this->update_status_.water_mode = this->data_.water_mode;
  this->update_status_.el_mode = this->data_.el_mode;
  this->update_status_.gas_mode = this->data_.gas_mode;
  this->update_status_.heater_prio = this->data_.heater_prio;
  this->update_status_.aventa_light = 0x00;  // in allen gemessenen Befehlen 0x00
  this->update_status_.unknown_11 = this->data_.unknown_11;
  this->update_status_.unknown_12 = this->data_.unknown_12;
  this->update_status_.unknown_13 = this->data_.unknown_13;
  this->update_status_.unknown_14 = this->data_.unknown_14;
  // Gemessen: exakt der Zaehler des zuletzt empfangenen 0x51 (Fabian: +1).
  this->update_status_.message_counter = this->data_.message_counter;

  this->update_status_prepared_ = true;
  return &this->update_status_;
}

void TrumaiNetBoxAppAldeStatus::create_update_data(StatusFrame *response, uint8_t *response_len,
                                                   uint8_t command_counter) {
  status_frame_create_empty(response, STATUS_FRAME_ALDE_STATUS_RESPONSE, sizeof(StatusFrameAldeStatusResponse),
                            command_counter);
  // Alde: 5. Byte ist konstant 0x1A (status_frame_create_empty setzt len + 6 = 0x16).
  response->raw[4] = ALDE_RESPONSE_HEADER_LENGTH;

  response->aldeStatusResponse = this->update_status_;

  // Pruefsumme laeuft ueber raw[10 .. 10 + 0x1A); die Bytes hinter dem Payload sind 0x00 (Aufrufer nullt den Puffer).
  status_frame_calculate_checksum(response);
  (*response_len) = ALDE_RESPONSE_TOTAL_LENGTH;

  ESP_LOGD(TAG, "Alde command 0x50: heater %u aircon_auto %02X target %.1f water %u el %u gas %02X prio %u ctr %02X",
           (uint8_t) this->update_status_.heater_mode, this->update_status_.aircon_auto,
           temp_code_to_decimal(this->update_status_.target_temp_room), (uint8_t) this->update_status_.water_mode,
           (uint8_t) this->update_status_.el_mode, (uint8_t) this->update_status_.gas_mode,
           (uint8_t) this->update_status_.heater_prio, this->update_status_.message_counter);

  TrumaStausFrameResponseStorage<StatusFrameAldeStatus, StatusFrameAldeStatusResponse>::update_submitted();
}

void TrumaiNetBoxAppAldeStatus::dump_data() const {}

bool TrumaiNetBoxAppAldeStatus::can_update() {
  return TrumaStausFrameResponseStorage<StatusFrameAldeStatus, StatusFrameAldeStatusResponse>::can_update() &&
         this->parent_->get_is_alde_device();
}

bool TrumaiNetBoxAppAldeStatus::action_heater_room(uint8_t temperature) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->target_temp_room = decimal_to_room_temp(temperature);
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_heater_room(float temperature) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->target_temp_room = decimal_to_room_temp(temperature);
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_heater_mode(bool on) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->heater_mode = on ? HeaterAlde::HEATER_ALDE_ON : HeaterAlde::HEATER_ALDE_OFF;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_water_mode(WaterTempAlde mode) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->water_mode = mode;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_el_mode(ElectricPowerLevelAlde level) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->el_mode = level;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_gas_mode(bool on) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->gas_mode = on ? GasModeAlde::GAS_MODE_ALDE_ON : GasModeAlde::GAS_MODE_ALDE_OFF;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_heater_prio(HeaterPriorityAlde prio) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->heater_prio = prio;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_aircon_auto(bool on) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  auto heater = this->update_prepare();
  heater->aircon_auto = on ? ALDE_FLAG_BIT : 0x00;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeStatus::action_aventa_light(bool on) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde (no status received yet).");
    return false;
  }
  ESP_LOGW(TAG, "EXPERIMENT: Aventa light via 0x50 byte 10 - untested hypothesis.");
  auto heater = this->update_prepare();
  heater->aventa_light = on ? ALDE_FLAG_BIT : 0x00;
  this->update_submit();
  return true;
}

}  // namespace truma_inetbox
}  // namespace esphome
