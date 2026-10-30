#!/usr/bin/env python3
"""podtests.py: the measurements behind TODO.md's pop-in steps 2 and 3 (board A, 2026-10-30), each run once Jason says
the cabling is in place.

    python3 bringup/podtests.py leak    test B: TX ANT and RX ANT each on a 50 ohm terminator, no lead between them, the
                                        DSA875 on RX MON (J102).  RX MON and the I/Q beat with the TX on (1, 0) and
                                        muted, at DSA 31.75 and 0, every 50 MHz over 4.9-6.0 GHz; the TX carrier and the
                                        RX LO's own leak read apart (the RX LO sits -18 ppm off with the loop held).
                                        Against REVB 10's leak in loopback (about -53 dBm at 5.0-5.5 GHz): if it stays,
                                        it is on the board; if it falls 20 dB or more, it was the lead, jacks and pads
    python3 bringup/podtests.py lomon   test C: the DSA875 on LO RX MON (J109).  RFOUTB on, the RX synthesizer stepped
                                        3.0-6.0 GHz (the MAX2871's top) every 50 MHz, the LO's level at the jack
                                        (sim/aslaid/REPORT.md: a peak near 3.8 GHz and a null near 4.3)

Each writes bringup/data/board_A/pod/<section>_<time>.json and a verdict, and leaves the transmitter muted, the DSA at
31.75 dB, the loop held, RFOUTB off, and the analyser sweeping live at full span.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import overnight as O                               # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "pod")
TCXO_PPM = -1.006                                   # the night's carrier / 232 (BRINGUP_LOG 3.5)
VCXO_PPM = -18.34                                   # VC 1.65 V, the loop held


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class Pod(O.Night):
    def __init__(self):
        super().__init__("pod")

    def peak_at(self, hz, span=20e3, rbw=300, ref=0.0):
        b = self.b
        b.sa_setup(hz, span, rbw=rbw, ref=ref, att=10)
        b.sa.single()
        return b.sa.peak()

    def leak(self, lo=4900, hi=6000, step=50, dsas=(31.75, 0.0)):
        cl = self.cl
        out = {"rows": []}
        self.scope_iq()
        try:
            cl.ctrl(loop_hold=1, tx_dis=1)
            cl.dac(O.S.DAC1, VC_OFF=O.S.V_MID)
            # the guard: with the loopback still in place RX MON at 5.0 GHz, DSA 20, reads about -45 dBm; terminated,
            # about -53 or less.  Above -48 dBm the run stops before it lowers the DSA under its loopback floor
            self.tune(5000)
            cl.dsa(20.0)
            self.tx(True)
            cl.hold_point(1, 0)
            time.sleep(0.05)
            g = self.peak_at(5000e6 * (1 + TCXO_PPM * 1e-6))[1]
            out["guard_dbm"] = g
            print("guard: RX MON %.1f dBm at 5.0 GHz, DSA 20, TX on" % g, flush=True)
            if g > -48.0:
                out["error"] = "RX MON %.1f dBm: the loopback seems still connected; stopped" % g
                print(out["error"], flush=True)
                return out
            for mhz in range(lo, hi + 1, step):
                if not self.alive():
                    break
                lock = self.tune(mhz)
                f_tx = mhz * 1e6 * (1 + TCXO_PPM * 1e-6)
                f_rx = mhz * 1e6 * (1 + VCXO_PPM * 1e-6)
                row = {"mhz": mhz, "lock": lock, "f_tx": f_tx, "f_rx_lo": f_rx, "pts": []}
                for on in (False, True):
                    self.tx(on)
                    cl.hold_point(1, 0)
                    for d in dsas:
                        cl.dsa(float(d))
                        time.sleep(0.02)
                        ftx, ptx = self.peak_at(f_tx)
                        frx, prx = self.peak_at(f_rx)
                        row["pts"].append({"tx_on": on, "dsa": d, "tx_carrier": ptx, "tx_hz": ftx, "rx_lo": prx,
                                           "rx_lo_hz": frx, "iq": self.iq_meas()})
                self.tx(False)
                cl.dsa(31.75)
                out["rows"].append(row)
                p = {(x["tx_on"], x["dsa"]): x for x in row["pts"]}
                print("%d MHz: TX carrier at RX MON, TX on %s / muted %s (DSA 31.75, 0); RX LO leak %s" % (
                    mhz, ["%.1f" % p[(True, d)]["tx_carrier"] for d in dsas], ["%.1f" % p[(False, d)]["tx_carrier"] for d in dsas],
                    ["%.1f" % p[(False, d)]["rx_lo"] for d in dsas]), flush=True)
        finally:
            self.quiet()
            try:
                self.b.sa_live()
            except Exception as e:                                   # noqa: BLE001
                print("sa_live failed:", e, flush=True)
            path = save("leak", out)
            self.b.record("verdict", test="pod_leak", ok=None, file=path, n=len(out["rows"]),
                          text="test B: TX ANT and RX ANT each terminated, RX MON and the I/Q beat with the TX on and "
                               "muted at DSA 31.75 and 0, 4.9-6.0 GHz (REVB 10: on the board, or the lead and pads?)")
        return out

    def lomon(self, lo=3000, hi=6000, step=50):
        cl = self.cl
        out = {"rows": []}
        try:
            cl.ctrl(loop_hold=1, tx_dis=1)
            cl.dac(O.S.DAC1, VC_OFF=O.S.V_MID)
            cl.pll_tune(0, 5800.0)                    # the TX synthesizer parked; its leak into J109 is -65 dBm or less
            for mhz in range(lo, hi + 1, step):
                args = () if mhz % 25 == 0 else (5.0, 15)
                cl.pll_tune(1, float(mhz), *args, lo_mon=True)
                time.sleep(O.S.RELOCK_S)
                lock = cl.pll_locked()
                f_rx = mhz * 1e6 * (1 + VCXO_PPM * 1e-6)
                f, p = self.peak_at(f_rx, span=2e6, rbw=10e3, ref=10.0)
                out["rows"].append({"mhz": mhz, "lock": lock, "hz": f, "dbm": p})
                print("%d MHz: LO RX MON %.1f dBm (%s)" % (mhz, p, lock), flush=True)
        finally:
            try:
                cl.pll_tune(1, 5800.0, lo_mon=False)
            except Exception as e:                                   # noqa: BLE001
                print("RFOUTB off failed:", e, flush=True)
            self.quiet()
            try:
                self.b.sa_live()
            except Exception as e:                                   # noqa: BLE001
                print("sa_live failed:", e, flush=True)
            path = save("lomon", out)
            self.b.record("verdict", test="pod_lomon", ok=None, file=path, n=len(out["rows"]),
                          text="test C: LO RX MON (J109) against the RX synthesizer's frequency, RFOUTB on, 3.0-6.0 GHz "
                               "(sim/aslaid: a peak near 3.8 GHz, a null near 4.3)")
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("section", choices=["leak", "lomon"])
    a = ap.parse_args(argv)
    P = Pod()
    getattr(P, a.section)()


if __name__ == "__main__":
    main(sys.argv[1:])
