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

    def links(self, mhzs=(5000, 5200, 5500), b210_gains=(0, 20, 40, 60, 75), target_rx_mon=-40.0, max_rx_mon=-25.0):
        """every link once the antennas are up: the ambient band (both TXs off) at RX MON and on the B210; the board's
        own link at DSA 31.75 first (the DSA it would need for RX MON near the loopback's regulated -40 dBm, then a
        lock there); the board's TX at the B210; the B210's CW (1 MHz off) at RX MON and at its own RX, its gain
        stepped, stopped before RX MON passes max_rx_mon"""
        cl, bb = self.cl, self.bb
        out = {"ambient": {}, "board": [], "b210_rx": [], "b210_tx": []}
        self.scope_iq(vdiv=0.1)
        try:
            cl.ctrl(tx_dis=1, loop_hold=1)
            cl.dsa(0.0)
            amb = []
            for f in range(4900, 5901, 100):
                self.tune(f)
                ff, p = self.peak_at(f * 1e6, 100e6, rbw=1e6, ref=-20.0) if hasattr(self, "peak_at") else self.rx_mon(f, span=100e6)
                amb.append({"mhz": f, "rx_mon_peak_dbm": p, "at_hz": ff})
            out["ambient"]["rx_mon_dsa0"] = amb
            print("ambient at RX MON (DSA 0, TX off, 100 MHz spans): %s" % ["%d:%.0f" % (r["mhz"], r["rx_mon_peak_dbm"]) for r in amb], flush=True)
            cl.dsa(31.75)
            out["ambient"]["b210"] = [bb.power(f, seconds=0.1, gain=40) for f in (5000, 5200, 5500)]
            print("ambient on the B210 (gain 40): %s" % ["%d: mean %.1f peak %.1f busy %.0f%%" % (r["mhz"], r["mean_dbfs"], r["peak_dbfs"],
                  100 * r["busy"]) for r in out["ambient"]["b210"]], flush=True)
            for mhz in mhzs:
                self.set_null(mhz)
                self.tune(mhz)
                cl.dsa(31.75)
                self.tx(True)
                time.sleep(0.1)
                f, p = self.rx_mon(mhz, span=200e3)
                need = 31.75 - (target_rx_mon - p)
                row = {"mhz": mhz, "rx_mon_at_31_75": p, "dsa_for_target": need}
                verdict = "too loud: needs %.1f dB more than the DSA has (a pad on RX ANT)" % (-31.75 + need) if need > 31.75 else (
                    "too quiet: %.1f dB short even at DSA 0" % (-need) if need < 0 else "fine: DSA %.1f for RX MON at %.0f dBm" % (need, target_rx_mon))
                row["verdict"] = verdict
                r2 = bb.power(mhz, seconds=0.05, gain=30)
                row["b210_hears_board"] = r2
                if 0 <= need <= 31.75:
                    d = max(self.dsa_min(mhz), math.ceil(need * 4) / 4)
                    cl.dsa(float(d))
                    time.sleep(0.05)
                    f2, p2 = self.rx_mon(mhz, span=200e3)
                    row.update(dsa_used=d, rx_mon_at_dsa=p2)
                    self.tx(False)
                    self.center(mhz)
                    self._cen[mhz] = self.centres()
                    lk = self.acquire0(mhz, float(d), self._cen[mhz], starts_khz=(10, 5, 20))
                    row["locked"] = lk is not None
                    row["a_leg"] = abs(lk["frame"]["di"]) if lk else None
                    self.cl.ctrl(loop_hold=1)
                out["board"].append(row)
                print("board %d MHz: RX MON %.1f dBm at DSA 31.75 -> %s; locked %s (leg %s); the B210 hears it at %.1f dBFS (gain 30)" % (
                    mhz, p, verdict, row.get("locked"), row.get("a_leg") and "%.3f V" % row["a_leg"], r2["mean_dbfs"]), flush=True)
                self.tx(False)
                self.restore()
            # the B210 as the interferer: its CW 1 MHz above 5200 MHz, the board muted, the DSA at 31.75 then at the link's
            mhz = 5200
            self.tune(mhz)
            cl.ctrl(tx_dis=1, loop_hold=1)
            link = [r for r in out["board"] if r["mhz"] == mhz]
            d_link = link[0].get("dsa_used", 31.75) if link else 31.75
            for g in b210_gains:
                res = {"gain": g}
                th = self._bg(bb.tone, mhz + 1.0, gain=g, seconds=2.5)
                time.sleep(0.6)
                for d in (31.75, d_link):
                    cl.dsa(float(d))
                    time.sleep(0.05)
                    ff, pp = self.peak_at((mhz + 1.0) * 1e6, 200e3, rbw=1e3, ref=0.0)
                    res["rx_mon_dsa_%.2f" % d] = pp
                th.join(timeout=5)
                cl.dsa(31.75)
                out["b210_tx"].append(res)
                print("B210 CW at %d+1 MHz, gain %2d: at RX MON %s dBm" % (mhz, g, {k: "%.1f" % v for k, v in res.items() if k != "gain"}), flush=True)
                if max(v for k, v in res.items() if k != "gain") > max_rx_mon:
                    print("  stopped: RX MON over %.0f dBm" % max_rx_mon, flush=True)
                    break
            # the B210 hearing itself (the tone sent from one thread, received in this one)
            for g in (0, 30, 60):
                th = self._bg(bb.tone, 5201.0, gain=g, seconds=1.5)
                time.sleep(0.5)
                try:
                    r = bb.power(5200, seconds=0.05, gain=30)
                except Exception as e:                           # noqa: BLE001
                    r = {"error": str(e)[:100]}
                th.join(timeout=5)
                out["b210_rx"].append({"gain": g, **r})
                print("B210 hears its own CW at gain %d: %s" % (g, r), flush=True)
        finally:
            try:
                self.b.sa_live()
            except Exception:                                    # noqa: BLE001
                pass
            self.done("ota_links", out, "over the air: every link (the ambient band, board to board, board to B210, B210 to board, B210 to itself)")
        return out

    def peak_at(self, hz, span=20e3, rbw=300, ref=0.0):
        b = self.b
        b.sa_setup(hz, span, rbw=rbw, ref=ref, att=10)
        b.sa.single()
        return b.sa.peak()

    def _bg(self, fn, *a, **k):
        t = threading.Thread(target=fn, args=a, kwargs=k, daemon=True)
        t.start()
        return t

    def interfere(self, mhz=5200, kinds=(("cw", 0.1), ("cw", 1.0), ("cw", 5.0), ("cw", 20.0), ("bursts", 0.2), ("bursts", 0.5),
                                          ("bursts", 1.0)), gains=(30, 40, 50, 55, 60, 65, 70, 75, 80, 89.75), on_s=2.0):
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
                        th = self._bg(self.bb.bursts, mhz, gain=g, bw_mhz=8.0, on_ms=on_ms, off_ms=off_ms, seconds=on_s)
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

    def soak(self, hours=12.0, mhz=5200, scan_every_s=600, mhzs=None, rotate_s=3600):
        """the lock watched every second (3.9a's detector), recovered automatically when lost (locklab's recovery,
        then a fresh lock_ota if that fails); the carrier rotated through `mhzs` every rotate_s; the band's power
        at the carrier from the B210 every scan_every_s (RX gain 10: the board's carrier reads about -13 dBFS at 30).
        Events: slips (back on the other Costas point), losses (with LOG_Q / PEAK_Q at the moment: interference or
        signal gone), and whether and how fast recovery worked"""
        mhzs = list(mhzs or [mhz])
        out = {"mhzs": mhzs, "events": [], "samples": 0, "scans": [], "segments": [], "t0": time.time()}
        self.scope_iq(vdiv=0.1)
        t_end = time.time() + hours * 3600
        k = 0
        try:
            while time.time() < t_end and self.alive():
                f = mhzs[k % len(mhzs)]
                k += 1
                self.set_null(f)
                cen, best = self.lock_ota(f)
                seg = {"mhz": f, "t_start": time.time(), "looks": 0, "losses": 0, "slips": 0}
                if best is None:
                    seg["error"] = "no lock"
                    out["segments"].append(seg)
                    print("%s %d MHz: no lock; next carrier" % (time.strftime("%H:%M:%S"), f), flush=True)
                    time.sleep(30)
                    continue
                dsa, a, lk = best
                seg.update(dsa=dsa, a_leg=a)
                side = lk["side"]
                t_seg_end = min(t_end, time.time() + rotate_s)
                t_scan = 0
                print("%s %d MHz: locked at DSA %.2f, leg %.3f V" % (time.strftime("%H:%M:%S"), f, dsa, a), flush=True)
                while time.time() < t_seg_end and self.alive():
                    o = self.observe(cen, a, side0=side, gate_s=0.005)
                    out["samples"] += 1
                    seg["looks"] += 1
                    if o["state"] == "slipped":
                        out["events"].append({"t": time.time(), "mhz": f, "kind": "slip", "log_q": o["log_q"], "peak_q": o["peak_q"]})
                        seg["slips"] += 1
                        side = o["side"]
                    elif o["state"] != "locked":
                        t_l = time.time()
                        o2 = o
                        for _ in range(5):                       # look again over about a second: interference passing?
                            time.sleep(0.15)
                            o2 = self.observe(cen, a, side0=side, gate_s=0.005)
                            if o2["state"] in ("locked", "slipped"):
                                break
                        if o2["state"] in ("locked", "slipped"):
                            out["events"].append({"t": t_l, "mhz": f, "kind": "blip", "state": o["state"], "log_q": o["log_q"],
                                                  "peak_q": o["peak_q"], "after": o2["state"]})
                            side = o2["side"]
                            continue
                        r = self.recover_once(f, dsa, cen, a)
                        out["events"].append({"t": t_l, "mhz": f, "kind": "loss", "state": o["state"], "log_q": o["log_q"],
                                              "peak_q": o["peak_q"], "recovered": r["ok"], "t_recover": r["t_s"]})
                        seg["losses"] += 1
                        print("%s %d MHz loss (%s, LOG_Q %.3f PEAK_Q %.3f): %s in %.1f s" % (time.strftime("%H:%M:%S"), f, o["state"],
                              o["log_q"], o["peak_q"], "recovered" if r["ok"] else "NOT recovered", r["t_s"]), flush=True)
                        if r["ok"]:
                            side = self.observe(cen, a)["side"]
                        else:
                            cen, best = self.lock_ota(f)
                            if best is None:
                                break
                            dsa, a, lk = best
                            side = lk["side"]
                    if self.bb is not None and time.time() - t_scan > scan_every_s:
                        t_scan = time.time()
                        try:
                            out["scans"].append({"t": t_scan, **self.bb.power(f, seconds=0.2, gain=10)})
                        except Exception as e:                   # noqa: BLE001
                            out["scans"].append({"t": t_scan, "mhz": f, "error": str(e)[:100]})
                        n_loss = sum(1 for e in out["events"] if e["kind"] == "loss")
                        n_slip = sum(1 for e in out["events"] if e["kind"] == "slip")
                        n_blip = sum(1 for e in out["events"] if e["kind"] == "blip")
                        print("%s soak: %d looks, %d losses, %d slips, %d blips; the band at %d MHz %s" % (
                            time.strftime("%H:%M:%S"), out["samples"], n_loss, n_slip, n_blip, f,
                            {x: (round(y, 1) if isinstance(y, float) else y) for x, y in out["scans"][-1].items() if x in ("mean_dbfs", "peak_dbfs", "busy")}),
                            flush=True)
                        save("soak_partial", out)
                    time.sleep(0.95)
                seg["t_end"] = time.time()
                out["segments"].append(seg)
                self.cl.ctrl(loop_hold=1)
                self.restore()
                save("soak_partial", out)
        finally:
            self.done("ota_soak", out, "over the air: the lock watched every second with automatic recovery, the carrier rotated hourly")
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="+", choices=["links", "find", "scan", "interfere", "soak"])
    ap.add_argument("--mhz", type=int, default=5200)
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--rotate", default="", help="carriers to rotate through hourly, e.g. 5200,5000,5500")
    a = ap.parse_args(argv)
    X = OTA(b210=any(s in ("links", "scan", "interfere", "soak") for s in a.sections))
    for s in a.sections:
        print("==== %s %s" % (s, time.strftime("%H:%M:%S")), flush=True)
        try:
            if s == "interfere":
                X.interfere(mhz=a.mhz)
            elif s == "soak":
                X.soak(hours=a.hours, mhzs=[int(x) for x in a.rotate.split(",")] if a.rotate else [a.mhz])
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
