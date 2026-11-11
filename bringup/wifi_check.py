"""Which WiFi is inside the return's band here, this laptop's own included: a check to run on site (no root).

    python3 wifi_check.py [--mhz 5400 5800] [--all]

The receiver's arms pass +-94 MHz around its carrier (twoboard.wifi_tag); a WiFi channel whose span overlaps that
band is in band.  In the lab (BRINGUP_LOG 4.80) the laptop's own radio on channels 60/64 (5300-5320) and 100 (5500),
all in 5400's band, took A -> B at 5400 from 100 % to nothing, while over cable (4.82) every carrier was clean.  The
beam at 4800 is below every WiFi channel; the return (5400 or 5800, station A's receiver) is the one at risk, from
either laptop's radio and from the access points in view.  So for each candidate return carrier it lists the access
points in band, strongest first, and says whether this laptop's own channel is one of them; and whether the WiFi's
subnet overlaps the PYNQs' 192.168.2.0/24.  What to do about it: section 10 of DEMO_COURTYARD.md.
"""
import argparse
import ipaddress
import re
import subprocess

RX_HALF_BAND = 94            # MHz either side of the carrier (the receiver's arms, as twoboard.wifi_tag)
PYNQ_NET = ipaddress.ip_network("192.168.2.0/24")
# 5 GHz channels bonded for 40 / 80 / 160 MHz (IEEE 802.11 channel blocks): the block holding the primary channel
BLOCKS = {40: [(36, 40), (44, 48), (52, 56), (60, 64), (100, 104), (108, 112), (116, 120), (124, 128), (132, 136),
               (140, 144), (149, 153), (157, 161), (165, 169)],
          80: [(36, 48), (52, 64), (100, 112), (116, 128), (132, 144), (149, 161)],
          160: [(36, 64), (100, 128)]}


def ch_mhz(ch):
    return 2407 + 5 * ch if ch <= 14 else 5000 + 5 * ch


def span(ch, width):
    """(low, high) MHz that a channel of `width` MHz with primary `ch` occupies."""
    width = width or 20
    if ch > 14 and width > 20:
        for lo, hi in BLOCKS.get(width, []):
            if lo <= ch <= hi:
                return ch_mhz(lo) - 10, ch_mhz(hi) + 10
    f = ch_mhz(ch)
    return f - width / 2, f + width / 2


def access_points():
    out = subprocess.run(["nmcli", "-t", "-f", "IN-USE,SSID,BSSID,CHAN,BANDWIDTH,SIGNAL,DEVICE", "dev", "wifi", "list"],
                         capture_output=True, text=True, check=True).stdout
    aps = []
    for line in out.splitlines():
        f = [x.replace("\\:", ":") for x in re.split(r"(?<!\\):", line)]
        if len(f) < 7 or not f[3].isdigit():
            continue
        width = int(re.sub(r"\D", "", f[4]) or 0)
        ch = int(f[3])
        aps.append({"mine": f[0] == "*", "ssid": f[1] or "--", "bssid": f[2], "ch": ch, "width": width or 20,
                    "signal": int(f[5] or 0), "dev": f[6], "span": span(ch, width)})
    return aps


def wifi_nets():
    out = subprocess.run(["ip", "-4", "-o", "addr", "show"], capture_output=True, text=True).stdout
    return [(m.group(1), ipaddress.ip_interface(m.group(2)).network)
            for m in re.finditer(r"^\d+:\s+(\S+)\s+inet\s+(\S+)", out, re.M) if m.group(1).startswith("wl")]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mhz", type=float, nargs="+", default=[5400.0, 5800.0], help="return carriers to check")
    ap.add_argument("--all", action="store_true", help="list every access point seen, not only those in band")
    args = ap.parse_args()
    aps = sorted(access_points(), key=lambda a: -a["signal"])
    mine = [a for a in aps if a["mine"]]
    fmt = "  {mark} {ssid:<24} {bssid}  ch {ch:>3}  {lo:.0f}-{hi:.0f} MHz  signal {signal:>3}"
    if mine:
        for a in mine:
            print(f"this laptop ({a['dev']}): {a['ssid']} on ch {a['ch']}, {a['span'][0]:.0f}-{a['span'][1]:.0f} MHz")
    else:
        print("this laptop: no WiFi association")
    for mhz in args.mhz:
        lo, hi = mhz - RX_HALF_BAND, mhz + RX_HALF_BAND
        inband = [a for a in aps if a["span"][0] < hi and a["span"][1] > lo]
        own = [a for a in inband if a["mine"]]
        verdict = ("THIS LAPTOP'S OWN CHANNEL IS IN BAND" if own else
                   f"{len(inband)} access point(s) in band" if inband else "clear")
        print(f"\nreturn at {mhz:.0f} MHz (band {lo:.0f}-{hi:.0f}): {verdict}")
        for a in inband:
            print(fmt.format(mark="*" if a["mine"] else " ", lo=a["span"][0], hi=a["span"][1], **a))
    ssids = {a["ssid"] for a in mine}
    for s in sorted(ssids):
        g = [a for a in aps if a["ssid"] == s and a["ch"] <= 14]
        print(f"\n{s} on 2.4 GHz here: " + (", ".join(f"ch {a['ch']} (signal {a['signal']})" for a in g) or "none seen"))
    for dev, net in wifi_nets():
        clash = net.overlaps(PYNQ_NET)
        print(f"{dev}: {net}" + ("  OVERLAPS the PYNQs' 192.168.2.0/24" if clash else ", no overlap with the PYNQs' 192.168.2.0/24"))
    if args.all:
        print("\nevery access point seen:")
        for a in aps:
            print(fmt.format(mark="*" if a["mine"] else " ", lo=a["span"][0], hi=a["span"][1], **a))


if __name__ == "__main__":
    main()
