# Beispiel-Logs

| Datei | Quelle | Inhalt |
|---|---|---|
| `b1-2026-10-27-app-aktionen.log` | eigener Mitschnitt 27.10.2026 | **Track B1:** Observer am TIN-Bus mit echter iNet Box, Alde Compact 3020 HE + Aventa; 7 App-Aktionen + Panel-Kontrollgruppe, Marker eingefügt. Auswertung in `…auswertung.txt`. Enthält die echten 0x50-Befehle (siehe `docs/TRACK-B-INET-BUS.md` Abschnitt 6) |
| `b1-2026-10-27-nachtmodus-licht.log` | eigener Mitschnitt 27.10.2026 | Zusatz: App-Nachtmodus ein/aus (Befehl 0x54) und Aventa-Beleuchtung am Panel (Status 0x51 Byte 10) |
| `b2-2026-10-27-erster-test.log` | eigener Mitschnitt 27.10.2026 | **Track B2:** ESP als iNet Box (echte Box abgezogen), 13 Befehle 0x50 mit Panel-ACKs OKAY, Soll/Heizung/Warmwasser/Elektro/Gas (siehe `docs/TRACK-B-INET-BUS.md` Abschnitt 7) |
| `fabian-alde.txt`, `fabian-alde2.txt` | `examples/alde.txt`, `alde2.txt` aus [Fabian-Schmidt/esphome-truma_inetbox@alde](https://github.com/Fabian-Schmidt/esphome-truma_inetbox/tree/alde/examples) (MIT) | ESPHome-Logs eines emulierten iNet-Box-Knotens an einem Alde-Panel 3020-113 / Compact 3020 HE (2024), mit handschriftlichen Aktions-Markern |

Testlauf des Parsers:

```bash
python tools/parse_observer_log.py docs/samples/fabian-alde2.txt --csv alde2.csv
```

Erkenntnisse aus den Beispielen (siehe auch `docs/TRACK-B-INET-BUS.md`):

- Das Panel quittiert jede Box-Nachricht mit 0x0D; der Counter im ACK ist in Fabians Logs **um 1 kleiner** als der Counter der Init-Nachricht. Mit der echten iNet Box (27.10.2026) ist er **gleich** (Truma-Muster).
- Die Init-Antwort wurde mit L = 0x1E *und* 0x1A quittiert – das 5. Header-Byte der Box-Antwort ist offenbar nicht kritisch.
- Jede Panel-Aktion erzeugt innerhalb von 2–5 s einen passenden 0x51/0x55/0x53-Download.
