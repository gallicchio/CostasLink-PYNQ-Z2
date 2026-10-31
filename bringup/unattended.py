#!/usr/bin/env python3
"""unattended.py: the link left alone for hours while the USRP B210 throws interference at it, and nothing touches
the board (Jason, 2026-10-31: the boards run unattended; 'this part just needs to work reliably without
intervention').  The board's own recovery (gateware/driver/linkd.py) and status page (dashboard.py) do all the work;
this program only drives the B210 and reads the page (HTTP, which is not a client of the board and so never pauses
linkd).

    python3 bringup/unattended.py --mhz 5200 --hours 10 [--gap 20 120]

Before it starts, the link must be locked at --mhz with linkd active (a setup run, then a minute of silence: it
waits for that).  Then, at random gaps of --gap seconds, one disturbance chosen at random:
    drag_below / drag_above  a CW 1-40 MHz below / above the carrier at gain 80-89.75 for 1-10 s (it can drag the loop off)
    near                     a CW 2-50 kHz off at gain 80-89.75 for 1-5 s
    bursts                   8 MHz noise bursts of 10 us - 1 ms every 1-100 ms at gain 80-89.75 for 5-30 s
    beacons                  1 ms every 102.4 ms for 30 s
Each record: what was sent, the page's state and linkd's counts before and after, and when the page read locked
again.  bringup/data/board_A/unattended/.  The summary: disturbances, losses, recoveries, failures, the longest
time not locked, and the share of the run locked.
"""
import argparse
import json
import os
import random
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "board_A", "unattended")
DASH = "http://192.168.8.142:8080"


def now():
    return json.loads(urllib.request.urlopen(DASH + "/api/now", timeout=5).read())


def note(text, seconds, kind="intervention"):
    """announce a disturbance on the status page (dashboard.py's POST /api/note), so a loss it causes reads as expected"""
    t = time.time()
    body = json.dumps({"text": text, "kind": kind, "source": "unattended.py", "t_start": t, "t_end": t + seconds}).encode()
    try:
        urllib.request.urlopen(urllib.request.Request(DASH + "/api/note", data=body, method="POST"), timeout=5).read()
    except Exception:                                            # noqa: BLE001 - an older page, or the server restarting
        pass


def wait(cond, timeout, poll=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = now()
            if cond(r):
                return r
        except Exception:                                        # noqa: BLE001
            pass
        time.sleep(poll)
    return None


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mhz", type=float, default=5200.0)
    ap.add_argument("--hours", type=float, default=10.0)
    ap.add_argument("--gap", type=float, nargs=2, default=(20.0, 120.0))
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    from b210 import B210
    bb = B210()
    rng = random.Random(a.seed)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "run_%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))
    print("waiting for the link to be locked with linkd active ...", flush=True)
    r0 = wait(lambda r: r.get("state") == "locked" and (r.get("linkd") or {}).get("mode") == "locked", 600)
    if r0 is None:
        print("the link is not locked with linkd active: set it up first", flush=True)
        return
    t_end = time.time() + a.hours * 3600
    n = 0
    sums = {"disturbances": 0, "lost_after": 0, "not_back": 0, "worst_back_s": 0.0}
    while time.time() < t_end:
        time.sleep(rng.uniform(*a.gap))
        kind = rng.choice(["drag_below", "drag_above", "near", "bursts", "beacons"])
        g = rng.choice([80.0, 83.0, 86.0, 89.75])
        try:
            before = now()
        except Exception as e:                                   # noqa: BLE001
            before = {"error": str(e)}
        rec = {"t": time.time(), "kind": kind, "gain": g}
        if kind in ("drag_below", "drag_above"):
            off = rng.choice([1.0, 5.0, 10.0, 20.0, 40.0]) * (-1 if kind == "drag_below" else 1)
            T = rng.uniform(1.0, 10.0)
            rec.update(off_mhz=off, seconds=T)
            note("B210: CW %+.0f MHz from the carrier at gain %.2f for %.1f s" % (off, g, T), T)
            bb.tone(a.mhz + off, gain=g, seconds=T)
        elif kind == "near":
            k = rng.choice([-50, -30, -20, -10, -5, -2, 2, 5, 10, 20, 30, 50])
            T = rng.uniform(1.0, 5.0)
            rec.update(off_khz=k, seconds=T)
            note("B210: CW %+d kHz from the carrier at gain %.2f for %.1f s" % (k, g, T), T)
            bb.tone(a.mhz + 2.0, gain=g, seconds=T, offset_hz=k * 1e3 - 2e6, rate=5e6)
        elif kind == "bursts":
            on_ms = rng.choice([0.01, 0.1, 1.0])
            per_ms = rng.choice([1.0, 10.0, 20.0, 100.0])
            if on_ms >= per_ms:
                per_ms = 10 * on_ms
            T = rng.uniform(5.0, 30.0)
            rec.update(on_ms=on_ms, per_ms=per_ms, seconds=T)
            note("B210: 8 MHz noise bursts of %g ms every %g ms at gain %.2f for %.0f s" % (on_ms, per_ms, g, T), T)
            bb.bursts(a.mhz, gain=g, bw_mhz=8.0, on_ms=on_ms, off_ms=per_ms - on_ms, seconds=T)
        else:
            rec.update(on_ms=1.0, per_ms=102.4, seconds=30.0)
            note("B210: noise bursts at a WiFi beacon's rhythm (1 ms every 102.4 ms) at gain %.2f for 30 s" % g, 30.0)
            bb.bursts(a.mhz, gain=g, bw_mhz=8.0, on_ms=1.0, off_ms=101.4, seconds=30.0)
        t_off = time.time()
        L0 = (before.get("linkd") or {})
        back = wait(lambda r: r.get("state") == "locked" and (r.get("linkd") or {}).get("mode") == "locked", 300)
        t_back = (time.time() - t_off) if back else None
        after = back or {}
        L1 = after.get("linkd") or {}
        rec.update(state_before=before.get("state"), back_s=t_back, losses=L1.get("losses", 0) - L0.get("losses", 0),
                   recoveries=L1.get("recoveries", 0) - L0.get("recoveries", 0), failed=L1.get("failed", 0) - L0.get("failed", 0),
                   gw_lock=after.get("gw_lock"))
        n += 1
        sums["disturbances"] += 1
        sums["lost_after"] += 1 if rec["losses"] else 0
        sums["not_back"] += 1 if t_back is None else 0
        if t_back is not None:
            sums["worst_back_s"] = max(sums["worst_back_s"], t_back)
        with open(path, "a") as f:
            f.write(json.dumps(rec) + "\n")
        print("%s #%d %-10s gain %5.2f %s: %s | %s" % (time.strftime("%H:%M:%S"), n, kind, g,
              ", ".join("%s %s" % (k, ("%.2f" % v) if isinstance(v, float) else v) for k, v in rec.items()
                        if k in ("off_mhz", "off_khz", "on_ms", "per_ms", "seconds")),
              ("locked again %.1f s after it ended" % t_back) if t_back is not None else "NOT LOCKED 300 s after it ended",
              "%d loss, %d recovered by linkd, %d failed tries" % (rec["losses"], rec["recoveries"], rec["failed"])), flush=True)
    print("summary:", json.dumps(sums), flush=True)
    with open(path, "a") as f:
        f.write(json.dumps({"summary": sums}) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
