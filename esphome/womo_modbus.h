// Einmaliger Modbus-TCP-Schreibbefehl an den Color Control GX im Womo (MultiPlus EIN/AUS).
//
// Konzept "Letzter Befehl gewinnt" (docs/MULTIPLUS-SCHALTER.md):
//  * pro Tastendruck genau EIN Write Single Register (Funktion 06) auf Register 33 (/Mode),
//    3 = Ein, 4 = Aus
//  * keine Wiederholung bei Fehler, kein Schreiben beim Start, kein zyklisches Durchsetzen
//  * der Befehl laeuft in einer eigenen FreeRTOS-Task, damit Bluetooth-Proxy und API im
//    Hauptloop nicht blockiert werden (Verbindungsaufbau max. 2 s, Antwort max. 2 s)
//  * waehrend ein Befehl laeuft, wird ein weiterer Tastendruck verworfen (nicht gepuffert)

#pragma once

#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstring>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include "esphome/core/log.h"

namespace womo_modbus {

static const char *const TAG = "womo_modbus";

enum Result : int { IDLE = 0, BUSY = 1, OK = 2, FAILED = 3 };

inline std::atomic<int> g_result{IDLE};
inline std::atomic<uint16_t> g_value{0};
inline std::atomic<bool> g_busy{false};
inline std::atomic<uint32_t> g_seq{0};  // zaehlt abgeschlossene Befehle (fuer die Anzeige)
inline char g_error[64] = "";

struct Job {
  char ip[16];
  uint8_t unit;
  uint16_t reg;
  uint16_t value;
};

inline bool recv_all(int s, uint8_t *buf, size_t len) {
  size_t got = 0;
  while (got < len) {
    int r = lwip_recv(s, buf + got, len - got, 0);
    if (r <= 0) return false;
    got += (size_t) r;
  }
  return true;
}

inline bool write_single_register(const Job &j, char *err, size_t errlen) {
  static uint16_t tx = 0;
  int s = lwip_socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (s < 0) {
    snprintf(err, errlen, "socket() fehlgeschlagen");
    return false;
  }
  struct sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_port = htons(502);
  if (inet_pton(AF_INET, j.ip, &addr.sin_addr) != 1) {
    snprintf(err, errlen, "ungueltige GX-Adresse %s", j.ip);
    lwip_close(s);
    return false;
  }

  // Verbindungsaufbau mit Zeitlimit (nicht blockierend + select)
  int flags = lwip_fcntl(s, F_GETFL, 0);
  lwip_fcntl(s, F_SETFL, flags | O_NONBLOCK);
  int r = lwip_connect(s, (struct sockaddr *) &addr, sizeof(addr));
  if (r != 0 && errno != EINPROGRESS) {
    snprintf(err, errlen, "GX nicht erreichbar (connect %d)", errno);
    lwip_close(s);
    return false;
  }
  if (r != 0) {
    fd_set wfds;
    FD_ZERO(&wfds);
    FD_SET(s, &wfds);
    struct timeval to = {2, 0};
    r = lwip_select(s + 1, nullptr, &wfds, nullptr, &to);
    int so_error = 0;
    socklen_t sl = sizeof(so_error);
    if (r <= 0 || lwip_getsockopt(s, SOL_SOCKET, SO_ERROR, &so_error, &sl) != 0 || so_error != 0) {
      snprintf(err, errlen, "GX nicht erreichbar (Port 502)");
      lwip_close(s);
      return false;
    }
  }
  lwip_fcntl(s, F_SETFL, flags);
  struct timeval tv = {2, 0};
  lwip_setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
  lwip_setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

  const uint16_t t = ++tx;
  const uint8_t frame[12] = {
      (uint8_t) (t >> 8), (uint8_t) t,          // Transaction-ID
      0, 0,                                     // Protocol-ID
      0, 6,                                     // Laenge: Unit + 5 Byte PDU
      j.unit,                                   // Unit-ID (VE.Bus-Dienst am GX)
      6,                                        // Write Single Register
      (uint8_t) (j.reg >> 8), (uint8_t) j.reg,  // Register
      (uint8_t) (j.value >> 8), (uint8_t) j.value,
  };
  if (lwip_send(s, frame, sizeof(frame), 0) != (int) sizeof(frame)) {
    snprintf(err, errlen, "Senden fehlgeschlagen");
    lwip_close(s);
    return false;
  }

  uint8_t hdr[7];
  if (!recv_all(s, hdr, sizeof(hdr))) {
    snprintf(err, errlen, "keine Antwort vom GX");
    lwip_close(s);
    return false;
  }
  const uint16_t rx_t = (hdr[0] << 8) | hdr[1];
  const uint16_t len = (hdr[4] << 8) | hdr[5];
  if (rx_t != t || hdr[2] != 0 || hdr[3] != 0 || hdr[6] != j.unit || len < 2 || len > 16) {
    snprintf(err, errlen, "ungueltiger Modbus-Header");
    lwip_close(s);
    return false;
  }
  uint8_t pdu[15];
  const size_t pdu_len = len - 1;
  bool got = recv_all(s, pdu, pdu_len);
  lwip_close(s);
  if (!got) {
    snprintf(err, errlen, "Antwort unvollstaendig");
    return false;
  }
  if (pdu[0] == (6 | 0x80)) {
    // 1 = Funktion nicht erlaubt, 2 = Register unbekannt, 10/11 = Unit-ID/Dienst falsch.
    // Bei gesperrtem Modus (Digital Multi Control noch erkannt) lehnt der GX den Write ab.
    snprintf(err, errlen, "Modbus-Ausnahme %u", pdu_len > 1 ? pdu[1] : 0);
    return false;
  }
  if (pdu_len != 5 || pdu[0] != 6 || pdu[1] != (uint8_t) (j.reg >> 8) || pdu[2] != (uint8_t) j.reg ||
      pdu[3] != (uint8_t) (j.value >> 8) || pdu[4] != (uint8_t) j.value) {
    snprintf(err, errlen, "unerwartete Antwort");
    return false;
  }
  return true;
}

inline void task_fn(void *arg) {
  Job *j = static_cast<Job *>(arg);
  char err[64] = "";
  bool ok = write_single_register(*j, err, sizeof(err));
  strncpy(g_error, ok ? "" : err, sizeof(g_error) - 1);
  g_value = j->value;
  g_result = ok ? OK : FAILED;
  g_seq++;
  delete j;
  g_busy = false;
  vTaskDelete(nullptr);
}

// Startet genau einen Schreibbefehl. false = es laeuft noch einer (Tastendruck wird verworfen).
inline bool start_write(const char *ip, uint8_t unit, uint16_t reg, uint16_t value) {
  bool expected = false;
  if (!g_busy.compare_exchange_strong(expected, true)) return false;
  Job *j = new Job{};
  strncpy(j->ip, ip, sizeof(j->ip) - 1);
  j->unit = unit;
  j->reg = reg;
  j->value = value;
  g_result = BUSY;
  if (xTaskCreate(task_fn, "modbus_w", 4096, j, 5, nullptr) != pdPASS) {
    delete j;
    strncpy(g_error, "Task nicht gestartet", sizeof(g_error) - 1);
    g_result = FAILED;
    g_seq++;
    g_busy = false;
    return false;
  }
  return true;
}

}  // namespace womo_modbus
