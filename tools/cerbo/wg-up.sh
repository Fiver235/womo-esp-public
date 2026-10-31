#!/bin/sh
# WireGuard-Tunnel wg0 auf dem Cerbo GX (Venus OS) aufbauen. Idempotent.
# Liegt auf dem Cerbo unter /data/wireguard/wg-up.sh und wird aus /data/rc.local gestartet.
# Konfiguration: /data/wireguard/wg0.conf (nur fuer wg setconf), Adresse unten.
# Wartet auf Netz/DNS (WLAN kommt beim Boot spaeter als rc.local) und versucht es bis zu 30 Minuten.
WG=/data/wireguard/wg
CONF=/data/wireguard/wg0.conf
ADDR=192.168.100.209/24
NET=192.168.100.0/24
LOG=/data/wireguard/wg-up.log

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

if [ ! -x "$WG" ] || [ ! -r "$CONF" ]; then
  log "wg oder wg0.conf fehlt - Abbruch"
  exit 1
fi

# Logdatei klein halten (Flash)
[ -f "$LOG" ] && [ "$(wc -c < "$LOG")" -gt 20000 ] && tail -n 50 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"

modprobe wireguard 2>/dev/null

n=0
while [ $n -lt 180 ]; do
  n=$((n + 1))
  if ! ip link show wg0 >/dev/null 2>&1; then
    ip link add wg0 type wireguard || { log "ip link add fehlgeschlagen"; sleep 10; continue; }
  fi
  # setconf loest den Endpoint-Hostnamen auf -> schlaegt ohne DNS fehl, dann erneut versuchen
  if "$WG" setconf wg0 "$CONF" 2>>"$LOG"; then
    ip addr replace "$ADDR" dev wg0
    ip link set wg0 up
    ip route replace "$NET" dev wg0
    log "wg0 aktiv (Versuch $n)"
    exit 0
  fi
  sleep 10
done
log "wg0 nach $n Versuchen nicht aufgebaut"
exit 1
