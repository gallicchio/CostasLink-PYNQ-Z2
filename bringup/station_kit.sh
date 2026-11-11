#!/bin/bash
# A courtyard demo station's software for a second laptop (DEMO_COURTYARD.md): only the files demo.py and demoscope.py
# load, plus the two files of ~/lab-instrument-control the scope needs, in one tarball.  Nothing else of the repository.
#   bringup/station_kit.sh [out.tar.gz]        (default: ./costaslink_station_<date>.tar.gz)
# On the other laptop:  tar xzf costaslink_station_*.tar.gz; cd costaslink_station; cat STATION.txt
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
P=$(dirname "$HERE")
LIC=${LAB_INSTRUMENT_CONTROL:-$HOME/lab-instrument-control}
OUT=${1:-$PWD/costaslink_station_$(date +%Y%m%d_%H%M).tar.gz}
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
K=$T/costaslink_station
mkdir -p "$K/bringup" "$K/gateware/driver" "$K/lic/siglent"
cp "$HERE"/{demo.py,demo.html,twoboard.py,bench.py,scope_e.py,demoscope.py,wifi_check.py,bench_config_laptop.json} "$K/bringup/"
cp "$P"/gateware/driver/{costaslink.py,netbus.py,linkd.py} "$K/gateware/driver/"
cp "$P"/gateware/{regmap.py,max2871_regs.py,board_constants.py} "$K/gateware/"
cp "$LIC/scpi_link.py" "$K/lic/"
cp "$LIC/siglent/siglent_SDS1104XE.py" "$K/lic/siglent/"
SRC="$(git -C "$P" rev-parse --short HEAD)$(git -C "$P" diff --quiet -- bringup gateware/driver || echo ' + uncommitted changes')"
cat > "$K/run_station.sh" <<'RUN'
#!/bin/bash
# run_station.sh A|B [demo.py options]   the station's demo (and on B the scope's 5 s view cycle), in the foreground;
# Ctrl-C stops both.  The page: http://localhost:8090/
D=$(cd "$(dirname "$0")" && pwd)
export LAB_INSTRUMENT_CONTROL=$D/lic
W=${1:?A or B}; shift
cd "$D/bringup" || exit 1
if [ "$W" = B ] && [ -z "${NO_SCOPE:-}" ]; then
    python3 demoscope.py preset B && { python3 demoscope.py cycle B > "$D/scope_cycle.log" 2>&1 & echo $! > "$D/scope_cycle.pid"; }
    trap 'kill -TERM $(cat "$D/scope_cycle.pid") 2>/dev/null' EXIT
elif [ "$W" = A ] && [ -z "${NO_SCOPE:-}" ]; then
    python3 demoscope.py preset A
fi
python3 demo.py "$W" "$@"
RUN
chmod +x "$K/run_station.sh"
cat > "$K/STATION.txt" <<TXT
CostasLink courtyard demo, one station's laptop (packed $(date '+%Y-%m-%d %H:%M') from $SRC).

Needs: python3 with numpy; a USB-Ethernet dongle (or the laptop's own port) wired straight to this station's PYNQ;
the scope on USB, readable by this user (Ubuntu: the user in group plugdev, /dev/usbtmc* group plugdev).  Any SDS1104X-E:
the only one on USB is used whatever its serial number; with two or more, name it: SCOPE_B=<serial or IP> ./run_station.sh B
(the serial is in its *IDN?, or: python3 lic/scpi_link.py usb).

1. The wired port: a fixed address on the PYNQs' subnet, no gateway, e.g.
     sudo nmcli con add type ethernet ifname <dongle> con-name pynq ipv4.method manual ipv4.addresses 192.168.2.11/24 ipv4.never-default yes ipv6.method disabled
   (.11: any 192.168.2.x but the PYNQs' .98 / .99 works on the direct cable; under .100 keeps clear of the lab router's DHCP
   pool, should the profile ever come up on the router's network.)
   PYNQ A answers at 192.168.2.99, PYNQ B at 192.168.2.98 (each also asks for DHCP first; with none it keeps the fixed one).
   Check: ping 192.168.2.98; the PYNQ's own page http://192.168.2.98:8080/ shows its link.
2. WiFi: the demo needs none.  Off (nmcli radio wifi off), or on 2.4 GHz, or on a 5 GHz channel outside the return's band:
   python3 bringup/wifi_check.py lists this laptop's channel and every access point within +-94 MHz of 5400 and of 5800
   (the laptop's own 5 GHz radio was the interferer in the lab, BRINGUP_LOG 4.80 / 4.82).  2.4 GHz only:
     nmcli con modify <the WiFi's name> 802-11-wireless.band bg; nmcli con up <the WiFi's name>
3. Station B (the beam's receiver):  ./run_station.sh B        Station A (the sender):  ./run_station.sh A
   The scope preset is set at start (B: I ch1, Q ch2, CMP I MON ch3, VC MON ch4 with no feed-through; and its view
   cycles every 5 s between the time traces and the I/Q constellation).  NO_SCOPE=1 ./run_station.sh B runs without it.
4. The page: http://localhost:8090/ (full screen: F11).  It shows "setting up" for about a minute after a cold start
   (or picks up the PYNQ's own lock in 2 s when the PYNQ has had it), then the numbers.
5. Stop: Ctrl-C.  The PYNQ keeps the link up by itself (its link.json) while no laptop drives it.
TXT
tar -C "$T" -czf "$OUT" costaslink_station
echo "$OUT ($(du -h "$OUT" | cut -f1)) from $SRC"
