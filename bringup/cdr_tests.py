#!/usr/bin/env python3
"""cdr_tests.py: the BER check's timing recovery on the board (ID version 4, ber_cdr.v; the overlay of 2026-10-30
17:31 in ~/costaslink_cdr).  Over the air at 5.2 GHz.

    python3 bringup/cdr_tests.py self     the board's own link, PRBS15 at 2, 4, 10 clocks a symbol, 20 runs each, with
                                          the fixed phase (a random draw against the TX's frame, BRINGUP_LOG 4.6) and
                                          with the timing recovered (mid-symbol from the tracked edge)
    python3 bringup/cdr_tests.py b210     the B210's BPSK (board TX muted) checked with the timing recovered, 1 s runs
                                          at 1 and 2 Mbaud, gains 4 and 6: the BER and the clocks' offset
Data: bringup/data/board_A/cdr/.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import weekend as W                                  # noqa: E402
import b210link as BL                                # noqa: E402
from costaslink import point_code                    # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "cdr")


class CDR(BL.Link):
    def self_run(self, side, p, cdr, seconds=0.05, phase=None):
        cl = self.cl
        cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
        cl.tx_timing(period=p)
        cl.tx_prbs(15)
        cl.tx_mode("prbs", n=2)
        cl.tx_go()
        time.sleep(0.01)
        cl.ber_config(15, phase, invert=side > 0, enable=True, cdr=cdr, period=p)
        time.sleep(seconds)
        c = cl.cdr_state() if cdr else None
        cl.ber_config(15, phase, invert=side > 0, enable=False, cdr=cdr, period=p)
        r = cl.ber()
        cl.tx_stop()
        cl.hold_point(1, 0)
        rate = r["mismatches"] / 3.0 / r["bits"] if r["bits"] else None
        return {"rate": rate, "bits": r["bits"], "mismatches": r["mismatches"], "cdr": c}

    def selflink(self, mhz=5200, periods=(4, 2, 10), runs=20):
        out = {"mhz": mhz, "rows": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        side = st["side"]
        for p in periods:
            for cdr in (False, True):
                rs = []
                for _ in range(runs):
                    if not self.relock(mhz, st):
                        break
                    side = st["side"]
                    rs.append(self.self_run(side, p, cdr, phase=None if cdr else (p * 8) // 2))
                bad = sum(1 for r in rs if r["rate"] is None or r["rate"] > 0)
                bits = sum(r["bits"] or 0 for r in rs)
                mism = sum(r["mismatches"] or 0 for r in rs)
                out["rows"].append({"period": p, "cdr": cdr, "runs": rs, "bad": bad, "bits": bits, "mismatches": mism})
                print("%d self link %4.1f Mbaud, %s: %d of %d runs with errors; %d bits, %d mismatches (BER %s)" % (
                    mhz, 100.0 / p, "timing recovered" if cdr else "fixed phase   ", bad, len(rs), bits, mism,
                    "%.2e" % (mism / 3.0 / bits) if bits else None), flush=True)
                W.save("cdr_self_partial", out)
        return out

    def b210cdr(self, mhz, gain=80, nseg=3):
        """a short check for the weekend's rounds: the B210's BPSK at 1 and 2 Mbaud through the board's timing
        recovery, nseg runs of 1 s each; the clocks' offset tracked round by round"""
        off = self.offset(mhz)
        out = {"mhz": mhz, "offset": off}
        st = self.lock_ext(mhz, off["delta_hz"], gain=gain)
        try:
            if st is None:
                out["error"] = "no lock to the B210"
                return out
            out["lock"] = st
            out["ber"] = [self.ber_cdr_ext(mhz, st, baud=b, nseg=nseg) for b in (1e6, 2e6)]
        finally:
            if getattr(self, "stream", None):
                self.stream.stop()
            self.ext = False
        return out

    def b210(self, mhz=5200, gain=80):
        off = self.offset(mhz)
        out = {"mhz": mhz, "offset": off}
        out["to"] = self.to_board(mhz, off["delta_hz"], gain=gain, fixed=False, events=False)
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["self", "b210"])
    a = ap.parse_args(argv)
    c = CDR()
    W.OUT = OUT
    c.piece({"self": "selflink", "b210": "b210"}[a.what], getattr(c, {"self": "selflink", "b210": "b210"}[a.what]), 5200)


if __name__ == "__main__":
    main(sys.argv[1:])
