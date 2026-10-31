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

## Datenweg – Entscheidung 31.10.2026 (nachmittags): **WireGuard direkt auf dem Cerbo**

Der Plan mit Headscale/TailscaleGX scheiterte am Speicher: Der Cerbo GX (Venus OS v3.56, armv7, 512-MB-NAND) hat eine **/data-Partition von nur 29 MB** (3,7 MB belegt, fast nur Logs). TailscaleGX ist 36 MB groß, Aufräumen hilft nicht; 45 MB UBI sind zwar unverteilt, ein `ubirsvol` am laufenden Gerät wurde als zu riskant verworfen.

Stattdessen ist der Cerbo jetzt **WireGuard-Peer der FRITZ!Box**, wie die ESPs, mit Heimnetz-Adresse **192.168.100.209**:

```
HA 192.168.100.15 ──LAN──► FRITZ!Box .254 ──WireGuard──► Cerbo wg0 192.168.100.209  (:8883 MQTT on LAN SSL)
```

| Baustein | Umsetzung |
|---|---|
| Kernel-Modul | `wireguard` ist Teil von Venus OS (5.10.109-venus-17), lädt per `modprobe` |
| `wg`-Tool | nicht im Victron-Feed; `usr/bin/wg` aus Debian bullseye `wireguard-tools_1.0.20210223-1_armhf.deb` (glibc 2.31 = Venus dunfell), 47 KB, SHA256 geprüft, liegt in `/data/wireguard/wg` – Script `tools/cerbo/install_wg.sh` |
| Konfiguration | `/data/wireguard/wg0.conf` (Mode 600) aus dem FRITZ!Box-Export, **AllowedIPs = 192.168.100.0/24** (Internet/VRM weiter über den M5); lokale Kopie `secrets/` (gitignored) |
| Aufbau | `/data/wireguard/wg-up.sh` (`tools/cerbo/wg-up.sh`): `ip link add wg0 type wireguard`, `wg setconf`, Adresse, Route; wartet bis 30 min auf Netz/DNS, Log `/data/wireguard/wg-up.log` |
| Autostart | `/data/rc.local` startet `wg-up.sh` im Hintergrund; /data und rc.local überleben Firmware-Updates |
| Werkzeug | `tools/cerbo_ssh.py` (paramiko, Passwort aus `CERBO_PW`, `@script` per stdin, `put:` per SFTP) |

Ergebnis 31.10. 11:29 UTC: Handshake sofort, Cerbo pingt .250 und HA durch den Tunnel.

Die vormittags eingerichtete FRITZ!Box-Route 100.64.0.0/10 → .250 und die Headscale-ACL-Regel für `ha` werden für den Cerbo nicht mehr gebraucht (Rückbau offen, schaden nicht). Historie der Headscale-Variante siehe unten.

### Historie: Variante Headscale (verworfen für den Cerbo)

#### Datenweg (ursprünglich: statische Route, ohne NAT)

```
HA 192.168.100.15 ──► FRITZ!Box .254 ──(statische Route 100.64.0.0/10 → .250)──► .250 ──(tailscale0)──► Cerbo 100.64.0.x :8883
Cerbo ──(accept-routes: 192.168.100.0/24 via 100.64.0.1)──► .250 ──► HA
```

- **FRITZ!Box** (durch Rudi): Heimnetz → Netzwerk → Netzwerkeinstellungen → IPv4-Routen → Neue Route: Netzwerk `100.64.0.0`, Subnetzmaske `255.192.0.0`, Gateway `192.168.100.250`, aktiv. Damit erreichen alle Geräte im Heimnetz das Tailnet über .250.
- **Host .250:** keine Änderung nötig (ip_forward=1, FORWARD accept, Tailscale-Regel `oifname tailscale0 accept`; kein Masquerading, der Cerbo sieht HA als 192.168.100.15).
- **Cerbo:** Subnetz-Route annehmen (`tailscale set --accept-routes`), damit Antworten an 192.168.100.0/24 durch den Tunnel gehen. Die Route ist in Headscale bereits freigegeben.
- **Headscale-ACL (`/etc/headscale/policy.hujson`):** Die Policy erlaubt nur Benutzer als Quelle (`group:admins`, `birgit@`). Pakete mit Heimnetz-Absender werden am Zielknoten verworfen, obwohl die Route stimmt. Ergänzt am 31.10.2026: Host `ha` = 192.168.100.15/32 und Regel `{ src: ["ha"], dst: ["*:*"] }` (nach Registrierung des Cerbo auf dessen Adresse und Port 8883 einengen). Prüfen/laden: `headscale policy check -f … && systemctl reload headscale`. Sicherung: `policy.hujson.bak-<Datum>`.
- **Test (bestanden 31.10.2026):** Vom LAN-Host homebridge (.12, kein VPN) Ping auf 100.64.0.1 OK mit ICMP-Redirect der FRITZ!Box auf .250; nach der ACL-Regel (temporär auch für .12) Ping auf das Notebook 100.64.0.3 durch den Tunnel OK (4/4, ~40 ms). Test-Host danach wieder aus der Policy entfernt.

Verworfene Alternativen: Tailscale-Add-on in HA (HA selbst als Client; weniger Eingriffe, aber nur HA profitiert), HAProxy-TCP-Weiterleitung auf .250 (nur MQTT), Masquerading auf .250 (verdeckt die Quelladresse).

## Schritte

1. Headscale: Pre-Auth-Key für den Cerbo erzeugen (`headscale preauthkeys create --user rudi --expiration 24h`).
2. Cerbo (Womo): Package Manager → TailscaleGX installieren → Einstellungen → Allgemein → Remote access via tailscale: Login-Server `https://headscale.winsysteme.de`, Auth-Key eintragen, Verbindung erlauben. Cerbo zeigt seine 100.64.0.x-Adresse. Knoten in Headscale prüfen (`headscale nodes list`).
3. Cerbo: Einstellungen → Dienste → **MQTT on LAN (SSL)** einschalten; Passwort des Sicherheitsprofils notieren. Prüfen, dass Orion XS und MPPT per **VE.Direct** am Cerbo hängen (Geräteliste).
4. ~~FRITZ!Box-Route eintragen~~ (erledigt 31.10.), am Cerbo accept-routes setzen; Test von HA: Ping auf die Cerbo-IP, dann `openssl s_client` auf Cerbo-IP:8883.
5. HA: Einstellungen → Geräte & Dienste → Integration hinzufügen → `victron_mqtt` (zweite Instanz): Host = Cerbo-Tailnet-IP, Port 8883, SSL an, Passwort, Modus „Full", Namen mit Präfix „Womo". Alternativ Core-Integration `victron_gx`.
6. Entitäten prüfen: Batterie (SmartShunt/BMV), Solarladeregler, DC/DC-Lader (Orion XS), Systemübersicht; Recorder-Ausschlüsse für hochfrequente Werte.

## Offene Punkte

- Verhalten von TailscaleGX mit Headscale (Login-Server-Option) in der Praxis.
- Cerbo-Firmwarestand (Package Manager braucht Venus OS ≥ 3.10, TailscaleGX ≥ v1.6).
- Ob der Orion XS per VE.Direct angebunden ist.
