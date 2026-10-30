#!/usr/bin/env python3
"""ota.py: board A's link over the air with the FPV antennas, and the USRP B210 as interferer and band monitor (Jason,
2026-10-30: four FPV antennas: TX ANT and RX ANT on leads, the B210's TX/RX A and RX2 A).  The loopback's lead and
pads are off; nothing joins TX ANT to RX ANT but the air.

    python3 bringup/ota.py find       per carrier (5.0-5.8 GHz): the DSA stepped down from 31.75 until the loop locks
                                      with the I leg near its regulated size; the level the air gives
    python3 bringup/ota.py scan       the B210's view of the band, the board's TX off and on
    python3 bringup/ota.py interfere  the loop locked; the B210 sends a CW (0.1-20 MHz off) or 20 MHz noise bursts
                                      (duty 1/5, 1/2, 1), its gain stepped up until the lock goes; per step the lock,
                                      LOG_Q / PEAK_Q, CMP_I's and the windows' activity during, and the state after
    python3 bringup/ota.py soak --hours H   the lock watched every second, recovered automatically when lost (locklab's
                                      recovery), the band's power at the carrier every 10 minutes: losses and slips
                                      against the time of day and the band's activity

Each writes bringup/data/board_A/ota/<section>_<time>.json and a verdict; the board left muted, held, DSA 31.75, the
B210 silent.  The DSA never goes under the loopback's floor (dsa_min assumes 40 dB of path; the air's is more).
"""
import argparse
import json
import math
import os
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import locklab as LL                                 # noqa: E402
import linktests as LT                               # noqa: E402
import stages as S                                   # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "ota")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, LT.O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class OTA(LL.Lab):
    def __init__(self, b210=True):
        super().__init__()
        self.bb = None
        if b210:
            import b210
            self.bb = b210.B210()

    def lock_ota(self, mhz, target=0.15, fresh=True):
        """the DSA stepped down from 31.75 (2 dB, then 0.5) until a lock with the I leg near `target` V"""
        if fresh or mhz not in self._cen:
            self.tx(False)
            self.center(mhz)
            self._cen[mhz] = self.centres()
        cen = self._cen[mhz]
        floor = self.dsa_min(mhz)
        best = None
        for dsa in [x for x in np.arange(31.75, floor - 1e-9, -2.0)]:
            lk = self.acquire0(mhz, float(dsa), cen, starts_khz=(10, 5, -5))
            if lk is None:
                continue
            a = abs(lk["frame"]["di"])
            best = (float(dsa), a, lk)
            if a >= target:
                break
        return cen, best

    def find(self, mhzs=tuple(range(5000, 5801, 100))):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in mhzs:
                self.set_null(mhz)
                cen, best = self.lock_ota(mhz)
                if best is None:
                    out["rows"].append({"mhz": mhz, "error": "no lock at any DSA"})
                    print("%d MHz: no lock at any DSA" % mhz, flush=True)
                    continue
                dsa, a, lk = best
                o = self.observe(cen, a)
                f, p = self.rx_mon(mhz)
                row = {"mhz": mhz, "dsa": dsa, "a_leg": a, "rx_mon_dbm": p, "obs": o}
                out["rows"].append(row)
                print("%d MHz: locked at DSA %.2f, leg %.3f V, RX MON %.1f dBm, LOG_Q %.3f" % (mhz, dsa, a, p, o["log_q"]), flush=True)
                self.restore()
        finally:
            self.done("ota_find", out, "over the air: per carrier, the DSA at which the loop locks with a regulated leg")
            try:
                self.b.sa_live()
            except Exception:                                    # noqa: BLE001
                pass
        return out

    def scan(self):
        out = {}
        try:
            self.cl.ctrl(tx_dis=1, loop_hold=1)
            out["tx_off"] = self.bb.scan(4900, 5900, 20, seconds=0.2)
            self.tune(5200)
            self.tx(True)
            self.cl.hold_point(1, 0)
            out["tx_on_5200"] = self.bb.scan(5100, 5300, 20, seconds=0.2)
        finally:
            self.done("ota_scan", out, "the B210's view of the band, the board's TX off, then on at 5.2 GHz")
        return out

    def _bg(self, fn, *a, **k):
        t = threading.Thread(target=fn, args=a, kwargs=k, daemon=True)
        t.start()
        return t

    def interfere(self, mhz=5200, kinds=(("cw", 0.1), ("cw", 1.0), ("cw", 5.0), ("cw", 20.0), ("bursts", 0.2), ("bursts", 0.5),
                                          ("bursts", 1.0)), gains=tuple(range(0, 90, 10)), on_s=2.0):
        out = {"mhz": mhz, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.set_null(mhz)
            cen, best = self.lock_ota(mhz)
            if best is None:
                out["error"] = "no lock"
                return out
            dsa, a, lk = best
            out.update(dsa=dsa, a_leg=a)
            print("locked at %d MHz DSA %.2f, leg %.3f V" % (mhz, dsa, a), flush=True)
            for kind, x in kinds:
                losses = 0
                for g in gains:
                    o0 = self.observe(cen, a)
                    if o0["state"] != "locked":
                        r = self.recover_once(mhz, dsa, cen, a)
                        if not r["ok"]:
                            break
                        o0 = self.observe(cen, a)
                    if kind == "cw":
                        th = self._bg(self.bb.tone, mhz + x, gain=g, seconds=on_s)
                    else:
                        on_ms = 1.0 if x < 1 else 5.0
                        off_ms = on_ms * (1 - x) / x if x < 1 else 0.0
                        th = self._bg(self.bb.bursts, mhz, gain=g, bw_mhz=20.0, on_ms=on_ms, off_ms=off_ms, seconds=on_s)
                    time.sleep(0.4)
                    during = [self.observe(cen, a, side0=o0["side"]) for _ in range(3)]
                    th.join(timeout=on_s + 5)
                    time.sleep(0.3)
                    after = self.observe(cen, a, side0=o0["side"])
                    row = {"kind": kind, "x": x, "gain": g, "during": during, "after": after, "before": o0}
                    out["runs"].append(row)
                    st = [d["state"] for d in during]
                    print("%-6s %5.1f %s gain %2d: during %s (LOG_Q %.3f PEAK_Q %.3f CMP_I %d); after %s" % (
                        kind, x, "MHz off" if kind == "cw" else "duty", g, st, during[-1]["log_q"], during[-1]["peak_q"],
                        during[-1]["edges"]["CMP_I"], after["state"]), flush=True)
                    if after["state"] != "locked":
                        losses += 1
                        if losses >= 2:
                            break
                save("interfere_partial", out)
        finally:
            self.done("ota_interfere", out, "over the air: the B210's CW and noise bursts stepped up against the locked loop")
        return out

    def soak(self, hours=12.0, mhz=5200, scan_every_s=600):
        out = {"mhz": mhz, "events": [], "samples": 0, "scans": []}
        self.scope_iq(vdiv=0.1)
        t_end = time.time() + hours * 3600
        try:
            self.set_null(mhz)
            cen, best = self.lock_ota(mhz)
            if best is None:
                out["error"] = "no lock"
                return out
            dsa, a, lk = best
            out.update(dsa=dsa, a_leg=a, t0=time.time())
            side = lk["side"]
            t_scan = 0
            while time.time() < t_end and self.alive():
                o = self.observe(cen, a, side0=side, gate_s=0.005)
                out["samples"] += 1
                if o["state"] == "slipped":
                    out["events"].append({"t": time.time(), "kind": "slip", "log_q": o["log_q"], "peak_q": o["peak_q"]})
                    side = o["side"]
                elif o["state"] != "locked":
                    t_l = time.time()
                    r = self.recover_once(mhz, dsa, cen, a)
                    out["events"].append({"t": t_l, "kind": "loss", "state": o["state"], "log_q": o["log_q"],
                                          "peak_q": o["peak_q"], "recovered": r["ok"], "t_recover": r["t_s"]})
                    print("%s loss (%s, LOG_Q %.3f PEAK_Q %.3f): %s in %.1f s" % (time.strftime("%H:%M:%S"), o["state"],
                          o["log_q"], o["peak_q"], "recovered" if r["ok"] else "NOT recovered", r["t_s"]), flush=True)
                    if r["ok"]:
                        side = self.observe(cen, a)["side"]
                    else:
                        cen, best = self.lock_ota(mhz)
                        if best is None:
                            time.sleep(30)
                            continue
                        dsa, a, lk = best
                        side = lk["side"]
                if self.bb is not None and time.time() - t_scan > scan_every_s:
                    t_scan = time.time()
                    try:
                        out["scans"].append({"t": t_scan, **self.bb.power(mhz, seconds=0.2)})
                    except Exception as e:                       # noqa: BLE001
                        out["scans"].append({"t": t_scan, "error": str(e)[:100]})
                    n_loss = sum(1 for e in out["events"] if e["kind"] == "loss")
                    n_slip = sum(1 for e in out["events"] if e["kind"] == "slip")
                    print("%s soak: %d looks, %d losses, %d slips; the band at the carrier %s" % (
                        time.strftime("%H:%M:%S"), out["samples"], n_loss, n_slip, out["scans"][-1]), flush=True)
                    save("soak_partial", out)
                time.sleep(max(0.0, 1.0 - 0.05))
        finally:
            self.done("ota_soak", out, "over the air: the lock watched every second with automatic recovery")
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="+", choices=["find", "scan", "interfere", "soak"])
    ap.add_argument("--mhz", type=int, default=5200)
    ap.add_argument("--hours", type=float, default=12.0)
    a = ap.parse_args(argv)
    X = OTA(b210=any(s in ("scan", "interfere", "soak") for s in a.sections))
    for s in a.sections:
        print("==== %s %s" % (s, time.strftime("%H:%M:%S")), flush=True)
        try:
            if s == "interfere":
                X.interfere(mhz=a.mhz)
            elif s == "soak":
                X.soak(hours=a.hours, mhz=a.mhz)
            else:
                getattr(X, s)()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("==== %s FAILED: %s" % (s, e), flush=True)
            try:
                X.restore()
                X.cleanup()
            except Exception:                                    # noqa: BLE001
                pass


if __name__ == "__main__":
    main(sys.argv[1:])
