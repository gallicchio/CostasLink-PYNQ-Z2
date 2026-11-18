#!/usr/bin/env python3
"""explain_tests.py: measurements for the explainer of how the loop loses lock (Jason, 2026-10-30: "If you do a series
of tests and make some nice plots, I'd be happy to be instructed pedagogically on this").  Over the air at 5.2 GHz,
the B210 as the interferer, VC and the I leg read on the board's ADC as fast as it goes.

    python3 bringup/explain_tests.py pullout   the largest sudden frequency step (VC_OFF) the loop survives without a slip,
                                               with a CW 1 MHz off at rising levels: the restoring force against r
    python3 bringup/explain_tests.py drag      VC through a 1 s CW above and below the carrier, strong enough to
                                               drag (+10 MHz and -10 MHz, gain 86), each free and held; and one too
                                               weak to (gain 77)
Data: bringup/data/board_A/explain/.
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import weekend as W                                  # noqa: E402
import stages as S                                   # noqa: E402
from b210 import Stream                              # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "explain")


class Explain(W.Weekend):
    def drag_trace(self, st, mhz, off_mhz, gain, hold=False, cw_s=1.0, pre_s=0.5, post_s=2.5):
        """VC (and the I leg every fourth read) on the board's ADC, as fast as it reads, from pre_s before a CW of cw_s
        to post_s after it; the hold (if asked) from 0.1 s before the CW to 0.2 s after"""
        cl = self.cl
        rows = []
        t0 = time.time()
        th = None
        held = False
        k = 0
        while True:
            t = time.time() - t0
            if hold and not held and t >= pre_s - 0.1 and th is None:
                cl.ctrl(loop_hold=1)
                held = True
            if th is None and t >= pre_s:
                th = self.bg(self.bb.tone, mhz + off_mhz, gain=gain, seconds=cw_s)
                t_cw = time.time() - t0
            if held and th is not None and not th.is_alive() and t >= t_cw + cw_s + 0.2:
                cl.ctrl(loop_hold=0)
                held = False
                t_rel = time.time() - t0
            if t > pre_s + cw_s + post_s:
                break
            row = [round(t, 4), cl.adc("VC")]
            if k % 4 == 0:
                row.append(cl.adc("I") - st["cen"]["adc_i0"])
            rows.append(row)
            k += 1
        if th is not None:
            th.join(timeout=5)
        o = self.observe(st["cen"], st["a"], side0=st["side"])
        return {"mhz": mhz, "off_mhz": off_mhz, "gain": gain, "hold": hold, "cw_s": cw_s, "t_cw": t_cw,
                "t_release": t_rel if hold else None, "rows": rows, "after": {x: o[x] for x in ("state", "vc", "di")}}

    def drag(self, mhz=5200):
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"], kv_hz_per_v=self.kv(mhz))
        if True:
            for off, g, hold in ((10.0, 77, False), (10.0, 86, False), (-10.0, 86, False), (10.0, 86, True), (-10.0, 86, True)):
                if not self.relock(mhz, st):
                    out["runs"].append({"off_mhz": off, "gain": g, "hold": hold, "error": "no lock before"})
                    continue
                r = self.drag_trace(st, mhz, off, g, hold)
                out["runs"].append(r)
                vc = np.asarray([x[1] for x in r["rows"]])
                print("%+5.1f MHz gain %5.2f%s: %d reads; VC %.3f -> min %.3f max %.3f, end %.3f; after: %s" % (
                    off, g, " held" if hold else "", len(vc), vc[:5].mean(), vc.min(), vc.max(), vc[-5:].mean(),
                    r["after"]["state"]), flush=True)
                W.save("explain_drag_partial", out)
        return out


    def pullout(self, mhz=5200, off_mhz=1.0, gains=(None, 70, 74, 78, 80, 83, 86),
                khz=(2, 4, 6, 8, 11, 15, 20, 27, 36, 48, 64)):
        """the restoring force, measured: the loop locked, VC_OFF stepped suddenly by +-khz / Kv; survived = 0.5 s
        later on the same side, the I leg up and VC back at its lock (the integrator takes the step); the first
        failure ends that sign.  The CW (1 MHz off: its delay push is small) from a stoppable B210 stream"""
        out = {"mhz": mhz, "off_mhz": off_mhz, "rows": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        kv = self.kv(mhz)
        out.update(dsa=st["dsa"], a_leg=st["a"], kv_hz_per_v=kv)
        cl = self.cl
        stream = None

        def start(g):
            if g is None:
                return None
            sm = Stream(self.bb, mhz + off_mhz, g, rate=4e6, park_hz=-1e6, amp=0.7)
            sm.start(np.ones(4000))
            time.sleep(0.3)
            return sm

        try:
            for g in gains:
                if not self.relock(mhz, st):
                    out["rows"].append({"gain": g, "error": "no lock"})
                    continue
                vc_lock = cl.adc("VC")
                v0 = cl.dac_volts()["VC_OFF"]
                stream = start(g)
                row = {"gain": g, "vc_lock": vc_lock, "held_khz": {}, "trials": []}
                for sgn in (1, -1):
                    best = 0.0
                    for k in khz:
                        side0 = self.observe(st["cen"], st["a"])["side"]
                        cl.dac(S.DAC1, VC_OFF=float(v0 + sgn * k * 1e3 / kv))
                        time.sleep(0.5)
                        o = self.observe(st["cen"], st["a"])
                        ok = o["side"] == side0 and abs(o["di"]) > 0.5 * st["a"] and abs(o["vc"] - vc_lock) < 0.01
                        row["trials"].append({"khz": sgn * k, "ok": ok, "side": o["side"], "di": o["di"], "vc": o["vc"]})
                        if ok:
                            best = k
                            self.ramp_vc_off(v0)
                            continue
                        cl.ctrl(loop_hold=1)
                        cl.dac(S.DAC1, VC_OFF=float(v0))
                        if stream:
                            stream.stop()
                            stream = None
                        self.relock(mhz, st)
                        stream = start(g)
                        break
                    row["held_khz"]["+" if sgn > 0 else "-"] = best
                if stream:
                    stream.stop()
                    stream = None
                out["rows"].append(row)
                print("CW %+.1f MHz gain %s: survives sudden steps up to +%s / -%s kHz" % (
                    off_mhz, g, row["held_khz"].get("+"), row["held_khz"].get("-")), flush=True)
                W.save("explain_pullout_partial", out)
        finally:
            if stream:
                stream.stop()
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["drag", "pullout"])
    a = ap.parse_args(argv)
    E = Explain()
    W.OUT = OUT
    E.piece(a.what, getattr(E, a.what), 5200)


if __name__ == "__main__":
    main(sys.argv[1:])
