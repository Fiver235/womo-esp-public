#!/bin/sh
# Laedt das Debian-bullseye-Paket wireguard-tools (armhf, glibc 2.31 wie Venus OS dunfell),
# prueft die SHA256 gegen packages.debian.org und legt nur das Binary "wg" nach /data/wireguard.
# Entpackt mit Python (busybox hat kein ar-Applet verlinkt).
# Ausfuehren: python tools/cerbo_ssh.py @tools/cerbo/install_wg.sh
set -e
DEB_URL="http://ftp.de.debian.org/debian/pool/main/w/wireguard/wireguard-tools_1.0.20210223-1_armhf.deb"
DEB_SHA="cc206072c60ef2eed4827cda5882c74966ef485b209b4950be3925e6cdcefd16"

mkdir -p /data/wireguard/tmp
cd /data/wireguard/tmp
[ -s wgt.deb ] || wget -q -T 20 -O wgt.deb "$DEB_URL"
S=$(sha256sum wgt.deb | cut -d' ' -f1)
echo "sha256 $S"
if [ "$S" != "$DEB_SHA" ]; then
  echo "SHA256 FALSCH - Abbruch"
  exit 1
fi
python3 - <<'EOF'
import io, lzma, tarfile
# .deb = ar-Archiv: "!<arch>\n" + Header(60 Byte: name16 mtime12 uid6 gid6 mode8 size10 magic2) + Daten (auf 2 Byte gerundet)
data = open("wgt.deb", "rb").read()
assert data[:8] == b"!<arch>\n", "kein ar-Archiv"
pos = 8
members = {}
while pos + 60 <= len(data):
    hdr = data[pos:pos + 60]
    name = hdr[0:16].decode().strip().rstrip("/")
    size = int(hdr[48:58].decode().strip())
    members[name] = data[pos + 60:pos + 60 + size]
    pos += 60 + size + (size % 2)
print("ar-Mitglieder:", ", ".join(members))
blob = members["data.tar.xz"]
t = tarfile.open(fileobj=io.BytesIO(lzma.decompress(blob)))
m = t.getmember("./usr/bin/wg")
with open("/data/wireguard/wg", "wb") as out:
    out.write(t.extractfile(m).read())
print("wg extrahiert:", m.size, "Byte")
EOF
chmod 755 /data/wireguard/wg
cd /data
rm -rf /data/wireguard/tmp
echo "== /data/wireguard"
ls -la /data/wireguard
echo "== test"
/data/wireguard/wg --version
/data/wireguard/wg genkey | wc -c
df -k /data | tail -n 1
