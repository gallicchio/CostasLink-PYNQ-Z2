#!/usr/bin/env python3
"""b210demo.py: the USRP B210 as a source of interference for a demonstration, each burst announced on the board's
status page (its B210 lane and its 'Now' line), so whoever watches sees what the radio is doing beside what the link is
doing (Jason, 2026-10-31: the students on Monday).

    python3 bringup/b210demo.py cw +5 [--gain 80] [--seconds 10]       a CW 5 MHz above the carrier (MHz, signed)
    python3 bringup/b210demo.py near -20 [--gain 85] [--seconds 5]     a CW 20 kHz below it (kHz, signed)
    python3 bringup/b210demo.py bursts [--on-ms 1] [--per-ms 10] [--bw-mhz 8] [--gain 85] [--seconds 20]
    python3 bringup/b210demo.py beacons [--gain 85] [--seconds 30]      WiFi beacons' rhythm: 1 ms every 102.4 ms
    python3 bringup/b210demo.py random [--minutes 30] [--quiet 20 60]  one of the above at random, quiet between

--mhz 5200 is the link's carrier.  Gains 70-89.75 (the B210's TX gain in dB; 89.75 is its full power, about +11 dB over
the board's carrier at RX ANT over the bench's 30-40 cm, BRINGUP_LOG 4.2).  The board's own recovery (linkd) and
self-test (selftest.py) keep running: this program never talks to the board, only to its page.
"""
import argparse
import os
import random
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import soak as S                                     # noqa: E402

DASH = S.DASH


def send(bb, mhz, kind, p):
    """the burst, announced on the page for as long as the radio really sends it (soak.Soak.b210)"""
    print("%s %s" % (time.strftime("%H:%M:%S"), S.describe(kind, p)), flush=True)
    s = S.Soak.__new__(S.Soak)
    s.mhz, s.bb = mhz, bb
    s.b210(kind, p, announce=True)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["cw", "near", "bursts", "beacons", "random"])
    ap.add_argument("offset", nargs="?", type=float, default=None, help="cw: MHz from the carrier; near: kHz")
    ap.add_argument("--mhz", type=float, default=5200.0)
    ap.add_argument("--gain", type=float, default=None)
    ap.add_argument("--seconds", type=float, default=None)
    ap.add_argument("--on-ms", type=float, default=1.0)
    ap.add_argument("--per-ms", type=float, default=10.0)
    ap.add_argument("--bw-mhz", type=float, default=8.0)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--quiet", type=float, nargs=2, default=(20.0, 60.0))
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args(argv)
    from b210 import B210
    bb = B210()
    if a.what == "cw":
        send(bb, a.mhz, "cw_far", {"off_mhz": a.offset if a.offset is not None else 5.0, "gain": a.gain or 80.0, "seconds": a.seconds or 10.0})
    elif a.what == "near":
        send(bb, a.mhz, "cw_near", {"off_khz": a.offset if a.offset is not None else -20.0, "gain": a.gain or 85.0, "seconds": a.seconds or 5.0})
    elif a.what in ("bursts", "beacons"):
        on, per = (1.0, 102.4) if a.what == "beacons" else (a.on_ms, a.per_ms)
        send(bb, a.mhz, "bursts", {"bw_mhz": a.bw_mhz, "off_mhz": 0.0, "on_ms": on, "per_ms": per, "gain": a.gain or 85.0,
                                   "seconds": a.seconds or (30.0 if a.what == "beacons" else 20.0), "seed": 1})
    else:
        rng = random.Random(a.seed if a.seed is not None else int(time.time()))
        t_stop = time.time() + 60 * a.minutes
        while time.time() < t_stop:
            time.sleep(rng.uniform(*a.quiet))
            kind = rng.choice(("cw_far", "cw_near", "bursts"))
            send(bb, a.mhz, kind, S.draw(kind, rng, 20.0))


if __name__ == "__main__":
    main(sys.argv[1:])
