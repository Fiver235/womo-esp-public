# Victron-System im Womo → Home Assistant

Stand 31.10.2026. Ziel: Cerbo GX, Orion XS und MPPT aus dem Womo in das heimische Home Assistant (192.168.100.15, HA OS 2026.10.4) einbinden. Der heimische Cerbo (192.168.100.200) läuft dort bereits über die HACS-Integration `victron_mqtt`.

## Ist-Zustand (geprüft)

| | |
|---|---|
| VPN | selbst gehostetes Headscale v0.29.2 (`https://headscale.winsysteme.de`), Tailnet 100.64.0.0/10, Benutzer `rudi` |
| Subnetz-Router | Host `haproxy` = 192.168.100.250 = Tailnet-Knoten `ate-subnet-250` (100.64.0.1), Debian 13, Tailscale 1.104.2; bietet 192.168.100.0/24 an, Route in Headscale freigegeben und aktiv |
| Forwarding auf .250 | `ip_forward=1`, FORWARD-Policy ACCEPT, Tailscale-Regel `oifname tailscale0 accept` → LAN → Tailnet wird weitergeleitet, aber **nicht maskiert** (ts-postrouting maskiert nur Tailnet → LAN) |
| Heimrouter | FRITZ!Box 192.168.100.254 (Standard-Gateway von .250 und vermutlich von HA); WireGuard-Server für die Womo-ESPs |
| Womo | Nighthawk M5 (kein VPN-Client); Alde-ESP und BLE-Proxy per WireGuard in HA; Cerbo GX noch ohne Fernzugriff |
| HA | Integrationen `victron_mqtt` (HACS, geladen) und `victron_gx` (Core, Discovery des Heim-Cerbo ignoriert); Tailscale-Add-on nicht nötig |

Venus OS hat **kein** eingebautes Tailscale (Victron hat die native Umsetzung zurückgestellt). Community-Paket: [kwindrem/TailscaleGX](https://github.com/kwindrem/TailscaleGX) über den Package Manager; unterstützt Auth-Key und alternativen Login-Server (Headscale, „nicht garantiert").

## Datenweg (Entscheidung 31.10.2026: statische Route, **ohne NAT**)

```
HA 192.168.100.15 ──► FRITZ!Box .254 ──(statische Route 100.64.0.0/10 → .250)──► .250 ──(tailscale0)──► Cerbo 100.64.0.x :8883
Cerbo ──(accept-routes: 192.168.100.0/24 via 100.64.0.1)──► .250 ──► HA
```

- **FRITZ!Box** (durch Rudi): Heimnetz → Netzwerk → Netzwerkeinstellungen → IPv4-Routen → Neue Route: Netzwerk `100.64.0.0`, Subnetzmaske `255.192.0.0`, Gateway `192.168.100.250`, aktiv. Damit erreichen alle Geräte im Heimnetz das Tailnet über .250.
- **Host .250:** keine Änderung nötig (ip_forward=1, FORWARD accept, Tailscale-Regel `oifname tailscale0 accept`; kein Masquerading, der Cerbo sieht HA als 192.168.100.15).
- **Cerbo:** Subnetz-Route annehmen (`tailscale set --accept-routes`), damit Antworten an 192.168.100.0/24 durch den Tunnel gehen. Die Route ist in Headscale bereits freigegeben.
- **Test:** von HA aus Ping auf 100.64.0.1 (beweist die FRITZ!Box-Route), danach Ping auf die Cerbo-Adresse (beweist accept-routes).

Verworfene Alternativen: Tailscale-Add-on in HA (HA selbst als Client; weniger Eingriffe, aber nur HA profitiert), HAProxy-TCP-Weiterleitung auf .250 (nur MQTT), Masquerading auf .250 (verdeckt die Quelladresse).

## Schritte

1. Headscale: Pre-Auth-Key für den Cerbo erzeugen (`headscale preauthkeys create --user rudi --expiration 24h`).
2. Cerbo (Womo): Package Manager → TailscaleGX installieren → Einstellungen → Allgemein → Remote access via tailscale: Login-Server `https://headscale.winsysteme.de`, Auth-Key eintragen, Verbindung erlauben. Cerbo zeigt seine 100.64.0.x-Adresse. Knoten in Headscale prüfen (`headscale nodes list`).
3. Cerbo: Einstellungen → Dienste → **MQTT on LAN (SSL)** einschalten; Passwort des Sicherheitsprofils notieren. Prüfen, dass Orion XS und MPPT per **VE.Direct** am Cerbo hängen (Geräteliste).
4. FRITZ!Box-Route eintragen, am Cerbo accept-routes setzen; Test von HA: Ping auf 100.64.0.1 und auf die Cerbo-IP, dann `openssl s_client` auf Cerbo-IP:8883.
5. HA: Einstellungen → Geräte & Dienste → Integration hinzufügen → `victron_mqtt` (zweite Instanz): Host = Cerbo-Tailnet-IP, Port 8883, SSL an, Passwort, Modus „Full", Namen mit Präfix „Womo". Alternativ Core-Integration `victron_gx`.
6. Entitäten prüfen: Batterie (SmartShunt/BMV), Solarladeregler, DC/DC-Lader (Orion XS), Systemübersicht; Recorder-Ausschlüsse für hochfrequente Werte.

## Offene Punkte

- Verhalten von TailscaleGX mit Headscale (Login-Server-Option) in der Praxis.
- Cerbo-Firmwarestand (Package Manager braucht Venus OS ≥ 3.10, TailscaleGX ≥ v1.6).
- Ob der Orion XS per VE.Direct angebunden ist.
