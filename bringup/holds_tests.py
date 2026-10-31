#!/usr/bin/env python3
"""holds_tests.py: the gateware's two holds (ID version 5, ihold.v) against the two ways the bench lost the loop
(Jason, 2026-10-30: "If someone walks in front of the antenna and blocks it or their phone wifi interferes, the lock
should recover once the incoming signal and interference levels recover").  Over the air at 5.2 GHz.

    python3 bringup/holds_tests.py holds

  interferer  the board's own link; a CW 10 MHz above or below the carrier at +9 dB for 1 s (it drags the loop to a
              rail, BRINGUP_LOG 4.5), with the interference hold off and on
  blocked     the B210's carrier (the board's TX muted) gone for 0.3 s and for 2 s, as if someone stood in front of
              the antenna, with the signal holdover off and on
Each case: VC read as fast as the ADC goes from 0.5 s before to 2.5-3 s after, the state after, the holds counted.
Data: bringup/data/board_A/holds/ (docs/lock_figures.py draws lock_holds from it).
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import weekend as W                                  # noqa: E402
import b210link as BL                                # noqa: E402
from b210 import Stream                              # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "holds")


class Holds(BL.Link):
    def trace(self, st, t_on, dur, on_fn, off_fn, post=2.5, pre=0.5):
        """VC from pre before the event to post after it; on_fn at t_on, off_fn dur later"""
        cl = self.cl
        rows = []
        t0 = time.time()
        state = 0
        while True:
            t = time.time() - t0
            if state == 0 and t >= pre:
                on_fn()
                t_ev = time.time() - t0
                state = 1
            elif state == 1 and t >= t_ev + dur:
                off_fn()
                state = 2
            if t > pre + dur + post:
                break
            rows.append([round(t, 4), cl.adc("VC")])
        o = self.observe(st["cen"], st["a"], side0=st["side"])
        return rows, t_ev, o

    def holds(self, mhz=5200):
        out = {"mhz": mhz, "runs": [], "kv_hz_per_v": self.kv(mhz)}
        cl = self.cl
        if not getattr(cl, "ihold_ok", False):
            out["error"] = "this overlay has no holds (ID version 5 has)"
            return out
        # ---- the interferer: the board's own link ----
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        for off in (10.0, -10.0):
            for protect in (False, True):
                if not self.relock(mhz, st):
                    out["runs"].append({"kind": "interferer", "off_mhz": off, "protect": protect, "error": "no lock before"})
                    continue
                cl.rx_clear()
                cl.ihold(protect)
                sm = {}

                def on():
                    sm["s"] = Stream(self.bb, mhz + off, 86, rate=4e6, park_hz=-1e6, amp=0.7)
                    sm["s"].start(np.ones(4000))

                def off_():
                    sm["s"].stop()

                rows, t_ev, o = self.trace(st, 0.5, 1.0, on, off_)
                ih = cl.ihold_state()
                cl.ihold(False)
                r = {"kind": "interferer", "off_mhz": off, "gain": 86, "protect": protect, "t_on": t_ev, "dur_s": 1.0,
                     "rows": rows, "after": o["state"], "vc_after": o["vc"], "ihold": ih}
                out["runs"].append(r)
                print("%d interferer %+5.1f MHz, +9 dB, 1 s, interference hold %s: after %s (VC %.3f); %d holds, %.2f s held" % (
                    mhz, off, "on " if protect else "off", o["state"], o["vc"], ih["holds"], ih["seconds"]), flush=True)
                W.save("holds_partial", out)
        self.restore()
        # ---- blocked: the B210's carrier, the board's TX muted ----
        off = self.offset(mhz)
        out["offset"] = off
        st = self.lock_ext(mhz, off["delta_hz"], gain=80)
        if st is None:
            out["error_blocked"] = "no lock to the B210"
            return out
        carrier = np.ones(int(self.stream.rate * 1e-3))
        try:
            for dur in (0.3, 2.0):
                for protect in (False, True):
                    o0 = self.observe(st["cen"], st["a"])
                    if o0["state"] not in ("locked", "slipped"):
                        self.stream.set(carrier)
                        r0 = self.recover_once(mhz, st["dsa"], st["cen"], st["a"])
                        if not r0["ok"]:
                            out["runs"].append({"kind": "blocked", "dur_s": dur, "protect": protect, "error": "no lock before"})
                            continue
                    st["side"] = self.observe(st["cen"], st["a"])["side"]
                    cl.rx_clear()
                    cl.shold(protect)
                    rows, t_ev, o = self.trace(st, 0.5, dur, lambda: self.stream.set(np.zeros(len(carrier))),
                                               lambda: self.stream.set(carrier), post=3.0)
                    sh = cl.shold_state()
                    cl.shold(False)
                    r = {"kind": "blocked", "dur_s": dur, "protect": protect, "t_on": t_ev, "rows": rows,
                         "after": o["state"], "vc_after": o["vc"], "shold": sh}
                    out["runs"].append(r)
                    print("%d blocked %.1f s, signal holdover %s: after %s (VC %.3f); %d holds, %.2f s held" % (
                        mhz, dur, "on " if protect else "off", o["state"], o["vc"], sh["holds"], sh["seconds"]), flush=True)
                    W.save("holds_partial", out)
        finally:
            self.stream.stop()
            self.ext = False
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["holds"])
    a = ap.parse_args(argv)
    h = Holds()
    W.OUT = OUT
    h.piece("holds", h.holds, 5200)


if __name__ == "__main__":
    main(sys.argv[1:])
