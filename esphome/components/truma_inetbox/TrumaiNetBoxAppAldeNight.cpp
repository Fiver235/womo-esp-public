#include "TrumaiNetBoxAppAldeNight.h"
#include "TrumaStatusFrameBuilder.h"
#include "esphome/core/log.h"
#include "helpers.h"
#include "TrumaiNetBoxApp.h"

namespace esphome {
namespace truma_inetbox {

static const char *const TAG = "truma_inetbox.TrumaiNetBoxAppAldeNight";

static constexpr uint8_t ALDE_RESPONSE_HEADER_LENGTH = 0x1A;
static constexpr uint8_t ALDE_RESPONSE_TOTAL_LENGTH = 0x25;

StatusFrameAldeHeaterNight *TrumaiNetBoxAppAldeNight::update_prepare() {
  if (this->update_status_prepared_ || this->update_status_stale_) {
    return &this->update_status_;
  }
  // Letzten 0x55 spiegeln (gemessen: App sendet alle Felder, unknown_09 als 0x00, Zaehler unveraendert).
  this->update_status_ = this->data_;
  this->update_status_.unknown_09 = 0x00;
  this->update_status_.unknown_10 = 0xFF;
  this->update_status_.message_counter = this->data_.message_counter;

  this->update_status_prepared_ = true;
  return &this->update_status_;
}

void TrumaiNetBoxAppAldeNight::create_update_data(StatusFrame *response, uint8_t *response_len,
                                                  uint8_t command_counter) {
  status_frame_create_empty(response, STATUS_FRAME_ALDE_HEATER_NIGHT_RESPONSE, sizeof(StatusFrameAldeHeaterNight),
                            command_counter);
  response->raw[4] = ALDE_RESPONSE_HEADER_LENGTH;
  response->aldeHeaterNight = this->update_status_;
  status_frame_calculate_checksum(response);
  (*response_len) = ALDE_RESPONSE_TOTAL_LENGTH;

  ESP_LOGD(TAG, "Alde command 0x54: target %.1f start %u end %u wd %u/%u bits %02X u9 %02X ctr %02X",
           temp_code_to_decimal(this->update_status_.target_temp_room), this->update_status_.mode_start_time,
           this->update_status_.mode_end_time, (uint8_t) this->update_status_.weekday_start,
           (uint8_t) this->update_status_.weekday_end, this->update_status_.bits, this->update_status_.unknown_09,
           this->update_status_.message_counter);

  TrumaStausFrameResponseStorage<StatusFrameAldeHeaterNight, StatusFrameAldeHeaterNight>::update_submitted();
}

void TrumaiNetBoxAppAldeNight::dump_data() const {}

bool TrumaiNetBoxAppAldeNight::can_update() {
  return TrumaStausFrameResponseStorage<StatusFrameAldeHeaterNight, StatusFrameAldeHeaterNight>::can_update() &&
         this->parent_->get_is_alde_device();
}

bool TrumaiNetBoxAppAldeNight::action_night_mode(bool on) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde night mode (no 0x55 received yet).");
    return false;
  }
  ESP_LOGW(TAG, "EXPERIMENT: night mode %s via 0x54 (weekday_end %s).", on ? "ON" : "OFF", on ? "0x00" : "0x07");
  auto night = this->update_prepare();
  night->weekday_end = on ? WeekDayAlde::WEEK_DAY_ALDE_MONDAY : WeekDayAlde::WEEK_DAY_ALDE_EVERY_DAY;
  this->update_submit();
  return true;
}

bool TrumaiNetBoxAppAldeNight::action_night_temp(float temperature) {
  if (!this->can_update()) {
    ESP_LOGW(TAG, "Cannot update Alde night mode (no 0x55 received yet).");
    return false;
  }
  auto night = this->update_prepare();
  night->target_temp_room = decimal_to_room_temp(temperature);
  this->update_submit();
  return true;
}

}  // namespace truma_inetbox
}  // namespace esphome
