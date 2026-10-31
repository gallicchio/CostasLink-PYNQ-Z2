#!/usr/bin/env python3
"""linkup.py: set the link up at one carrier over the air (the carrier nulled, the DSA stepped down to a regulated
leg, the windows at 0.5 a, V_T2 2.9 V: weekend.py's ready) and leave it locked and released, for linkd and
unattended.py to look after.  Unlike the weekend's pieces, it does not park the board afterwards.

    python3 bringup/linkup.py --mhz 5200
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import weekend as W                                  # noqa: E402


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mhz", type=int, default=5200)
    a = ap.parse_args(argv)
    w = W.Weekend()
    st = w.ready(a.mhz)
    if st is None:
        print("no lock at %d MHz" % a.mhz, flush=True)
        sys.exit(1)
    o = w.observe(st["cen"], st["a"])
    print("%d MHz: %s at DSA %.2f, leg %.3f V, VC %.4f V; left locked and released" % (a.mhz, o["state"], st["dsa"], st["a"], o["vc"]),
          flush=True)
    try:
        w.b.sa_live()
    except Exception:                                            # noqa: BLE001
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
