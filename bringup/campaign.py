#!/usr/bin/env python3
"""campaign.py: board A characterised as widely as the loopback allows (Jason, 2026-10-30 10:40: "parameter sweeps ...
constellations, frequencies, amplitudes and bit rates ... latency and BER in as wide a range of situations as the board
allows").  The bench: TX ANT -> 10 cm RG-316 -> two 20 dB pads -> RX ANT; the DSA875 on RX MON; the scope's ch1 REF
OUT, ch2 I MON, ch3 Q MON, ch4 VC MON (1 Mohm); the sign jumpers moved (BRINGUP_LOG 3.6).

    python3 bringup/campaign.py ber        BPSK PRBS15 on CMP_I, the loop closed: each symbol period 1-10 clocks with
                                           its sampling phase scanned; the BER against the DSA (the level) at 50, 25 and
                                           10 Mbaud; against the carrier from 3.5 to 5.9 GHz
    python3 bringup/campaign.py schemes    A1, A1w, A2, A3 with PRBS-chosen messages: symbol errors, false and missed
                                           events, latency, against the DSA, the windows' place and the carrier
    python3 bringup/campaign.py rate       A1 and A3 against the event period (2000 down to 16 clocks)
    python3 bringup/campaign.py rings      the fast path's ring in this lock's frame (A3's corners, the axis points,
                                           the +-I flip), against the DSA and the windows' place (LATENCY.md check a)
    python3 bringup/campaign.py cal        per carrier: the TX carrier null (VR_I / VR_Q, then restored) and the fast I
                                           comparator's null (I_OFF_F): the firmware's tables (REVB 15, 19)
    python3 bringup/campaign.py dyn        the loop's step response against the DSA (f_n and damping against the leg)
    python3 bringup/campaign.py slow       A1 / A2 / A3 confirmed against V_T2, the carrier nulled (REVB 17)

Each writes bringup/data/board_A/campaign/<section>_<time>.json and a verdict, and leaves the transmitter muted, the
DSA at 31.75 dB, the loop held, the trims at their values before.
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import locktests as T                               # noqa: E402
import linktests as LT                              # noqa: E402
import stages as S                                  # noqa: E402
from costaslink import SCHEMES, Scheme, point_code, CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN   # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "campaign")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, LT.O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class Frame0(Scheme):
    """a scheme whose receiver frame is this lock's: the idle on side * I, the I arm mirrored (REVB 9)"""

    def __init__(self, tx, side, mirror=True):
        super().__init__(tx.name, tx.text, tx.idle, tx.msgs, [], rot_deg=0.0, pilot=tx.pilot, t=tx.t, t2=tx.t2)
        self.mask, self.use = tx.mask, tx.use
        self.side, self.mirror = side, mirror

    def rx_point(self, iq):
        i, q = iq
        return (self.side * i, (-self.side if self.mirror else self.side) * q)


RINGS = {
    "A3": Scheme("A3", "the corners (QPSK)", (1, 0), [(1, 1), (1, -1), (-1, 1), (-1, -1)], [CMP_QP, CMP_QN, CMP_IP, CMP_IN]),
    "AX": Scheme("AX", "the axis points", (1, 1), [(1, 0), (-1, 0), (0, 1), (0, -1)], [CMP_IP, CMP_IN, CMP_QP, CMP_QN]),
    "A1r": Scheme("A1r", "the +-I flip", (1, 1), [(-1, 0), (1, 0)], [CMP_I, CMP_IP, CMP_IN]),
}
RING_ORDER = {"A3": [0, 1, 3, 2], "AX": [0, 2, 1, 3], "A1r": [0, 1]}


class Camp(T.Lock0):
    def __init__(self):
        super().__init__()
        self._cen = {}

    # ---- a lock, with the no-carrier centres cached per carrier ----
    def lock_at(self, mhz, dsa, fresh=False):
        if fresh or mhz not in self._cen:
            self.tx(False)
            self.center(mhz)
            self._cen[mhz] = self.centres()
        cen = self._cen[mhz]
        lk = self.acquire0(mhz, dsa, cen)
        if lk is None:
            return None
        return cen, lk["side"], abs(lk["frame"]["di"]), lk

    def ensure(self, mhz, dsa, cen, a_leg=None):
        side, ok, fi = self.frame0(cen, a_leg)
        if ok:
            return side
        lk = self.acquire0(mhz, dsa, cen)
        return lk["side"] if lk else None

    # ---- the BER ----
    def ber_once(self, side, p, phase, seconds, cdr=None):
        """one PRBS15 BPSK run through the board's own link.  cdr (default: when the overlay has it, ID version 4, and
        the symbol is 2 clocks or more): the check's timing recovered from CMP_I's edges, sampled mid-symbol, `phase`
        unused; without it the check's frame is a random draw against the TX's (BRINGUP_LOG 4.6)"""
        cl = self.cl
        if cdr is None:
            cdr = bool(getattr(cl, "cdr", False)) and p >= 2
        cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
        if not cdr:
            r = cl.ber_run(seconds=seconds, poly=15, period=p, phase=phase, n=2, invert=side > 0)
            cl.hold_point(1, 0)
            return r
        cl.tx_timing(period=p)
        cl.tx_prbs(15)
        cl.tx_mode("prbs", n=2)
        cl.tx_go()
        time.sleep(0.005)
        cl.ber_config(15, None, invert=side > 0, enable=True, cdr=True, period=p)
        time.sleep(seconds)
        cl.ber_config(15, None, invert=side > 0, enable=False, cdr=True, period=p)
        r = cl.ber()
        r["cdr_state"] = cl.cdr_state()                  # with each segment: 5.0 GHz's random ones (BRINGUP_LOG 4.9)
        cl.tx_stop()
        cl.hold_point(1, 0)
        r["cdr"] = True
        return r

    def best_phase(self, side, p, seconds=0.05):
        scan = []
        for ph in range(8 * p):
            r = self.ber_once(side, p, ph, seconds)
            scan.append(r["ber"] if r["ber"] is not None else 1.0)
        n = len(scan)
        good = [b <= min(scan) + 1e-12 for b in scan]
        best, run, start = (0, 0), 0, None
        for k in range(2 * n):                         # the longest circular run at the minimum: its middle
            if good[k % n]:
                run += 1
                if run == 1:
                    start = k
                if run > best[0]:
                    best = (run, start)
            else:
                run = 0
        mid = (best[1] + best[0] // 2) % n if best[0] else int(np.argmin(scan))
        return mid, scan, min(best[0], n)

    def ber(self):
        out = {"rates": [], "levels": [], "carriers": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                reg = self.regulated_dsa(mhz)
                lk = self.lock_at(mhz, reg)
                if lk is None:
                    continue
                cen, side, a_leg, _ = lk
                for p in (1, 2, 3, 4, 5, 6, 8, 10):
                    side = self.ensure(mhz, reg, cen) or side
                    ph, scan, width = self.best_phase(side, p)
                    r = self.ber_once(side, p, ph, 1.0)
                    row = {"mhz": mhz, "dsa": reg, "a_leg": a_leg, "period": p, "mbaud": 100.0 / p, "phase": ph,
                           "open_phases": width, "of": 8 * p, "scan": scan, **r}
                    out["rates"].append(row)
                    print("%d MHz %5.1f Mbaud: open %d of %d phases; at %d: %d bits, BER %s" % (
                        mhz, 100.0 / p, width, 8 * p, ph, r["bits"], r["ber"]), flush=True)
                save("ber_partial", out)
                for p in (2, 4, 10):
                    for dsa in sorted(set([reg] + [float(x) for x in np.arange(reg, 31.76, 2.0)] + [31.75])):
                        lk = self.acquire0(mhz, dsa, cen)
                        if lk is None:
                            out["levels"].append({"mhz": mhz, "dsa": dsa, "period": p, "error": "no lock"})
                            print("%d MHz DSA %.2f: no lock" % (mhz, dsa), flush=True)
                            continue
                        side, a = lk["side"], abs(lk["frame"]["di"])
                        ph, scan, width = self.best_phase(side, p, seconds=0.02)
                        r = self.ber_once(side, p, ph, 1.0)
                        s2, ok, _ = self.frame0(cen, a)
                        out["levels"].append({"mhz": mhz, "dsa": dsa, "period": p, "a_leg": a, "phase": ph,
                                              "open_phases": width, "lock_after": ok, **r})
                        print("%d MHz %4.1f Mbaud DSA %5.2f leg %.3f V: open %d/%d, BER %s%s" % (
                            mhz, 100.0 / p, dsa, a, width, 8 * p, r["ber"], "" if ok else " (lock lost)"), flush=True)
                    save("ber_partial", out)
            for mhz in (3500, 4000, 4500, 4800, 4900, 5000, 5100, 5200, 5300, 5400, 5500, 5600, 5700, 5800, 5900):
                reg = self.regulated_dsa(mhz)
                lk = self.lock_at(mhz, reg, fresh=True)
                if lk is None:
                    out["carriers"].append({"mhz": mhz, "dsa": reg, "error": "no lock"})
                    print("%d MHz DSA %.2f: no lock" % (mhz, reg), flush=True)
                    continue
                cen, side, a_leg, _ = lk
                for p in (2, 4):
                    ph, scan, width = self.best_phase(side, p, seconds=0.02)
                    r = self.ber_once(side, p, ph, 1.0)
                    out["carriers"].append({"mhz": mhz, "dsa": reg, "period": p, "a_leg": a_leg, "phase": ph,
                                            "open_phases": width, **r})
                    print("%d MHz DSA %.2f leg %.3f V %4.1f Mbaud: open %d/%d, BER %s" % (
                        mhz, reg, a_leg, 100.0 / p, width, 8 * p, r["ber"]), flush=True)
                save("ber_partial", out)
        finally:
            self.cleanup()
            path = save("ber", out)
            self.b.record("verdict", test="campaign_ber", ok=None, file=path,
                          text="BPSK PRBS15 on CMP_I, the loop closed: against the symbol period and sampling phase, "
                               "the DSA, and the carrier")
        return out

    # ---- the BER, segmented: a 180-degree slip inverts every bit (the self-synchronising check reads 1 / 3) ----
    def segs(self, side, p, phase, n=10, seconds=0.02):
        """n short runs, each classed by the self-synchronising check's rate r = mismatches / 3 / bits:
        clean (r = 0); inverted or constant (r near 1/3: every check fails, the loop slipped 180 degrees or the
        decision stuck); beating (r near 1/6: the data times a slow +-1, the loop unlocked); partial (r under 0.1:
        bit errors in a locked loop, the eye)"""
        c = {"clean": 0, "inverted": 0, "beating": 0, "partial": 0, "bits": 0, "err_bits_partial": 0.0, "rates": []}
        for _ in range(n):
            r = self.ber_once(side, p, phase, seconds)
            b, e = r["bits"] or 0, r["mismatches"] or 0
            c["bits"] += b
            x = e / 3.0 / b if b else None
            c["rates"].append(x)
            if e == 0:
                c["clean"] += 1
            elif x is not None and x > 0.28:
                c["inverted"] += 1
            elif x is not None and x > 0.1:
                c["beating"] += 1
            else:
                c["partial"] += 1
                c["err_bits_partial"] += e / 3.0
        return c

    def data_push(self, side, p, seconds=1.0):
        """the loop's lock point with the data running: the Q leg's and I leg's DC (the slow ADC's average) during a
        PRBS run against the idle's; a Q that moves is a phase offset the data makes"""
        cl = self.cl
        q0, i0, vc0 = cl.adc("Q"), cl.adc("I"), cl.adc("VC")
        cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
        cl.tx_timing(period=p)
        cl.tx_prbs(15)
        cl.tx_mode("prbs", n=2)
        cl.tx_go()
        time.sleep(0.3)
        q1, i1, vc1 = cl.adc("Q"), cl.adc("I"), cl.adc("VC")
        time.sleep(max(0.0, seconds - 0.3))
        q2 = cl.adc("Q")
        cl.tx_stop()
        cl.hold_point(1, 0)
        time.sleep(0.2)
        return {"q_idle": q0, "q_data": q1, "q_data_late": q2, "i_idle": i0, "i_data": i1, "vc_idle": vc0, "vc_data": vc1}

    def ber2(self):
        out = {"phases": [], "levels": [], "push": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                reg = self.regulated_dsa(mhz)
                lk = self.lock_at(mhz, reg, fresh=True)
                if lk is None:
                    continue
                cen, side, a_leg, _ = lk
                for p in (1, 2, 4, 10, 20, 100):
                    side = self.ensure(mhz, reg, cen, a_leg) or side
                    d = self.data_push(side, p)
                    d.update(mhz=mhz, period=p, mbaud=100.0 / p, dsa=reg, a_leg=a_leg, side=side)
                    s2, ok, _ = self.frame0(cen, a_leg)
                    d["lock_after"] = ok
                    out["push"].append(d)
                    print("%d MHz %5.1f Mbaud: Q leg %+.4f V with data (idle %.4f), I leg %+.4f, VC %+.4f; lock after %s" % (
                        mhz, 100.0 / p, d["q_data"] - d["q_idle"], d["q_idle"], d["i_data"] - d["i_idle"],
                        d["vc_data"] - d["vc_idle"], ok), flush=True)
                for p, step in ((1, 1), (2, 1), (4, 2), (10, 5)):
                    for ph in range(0, 8 * p, step):
                        side = self.ensure(mhz, reg, cen, a_leg) or side
                        c = self.segs(side, p, ph, n=8)
                        c.update(mhz=mhz, period=p, phase=ph, dsa=reg)
                        out["phases"].append(c)
                        print("%d MHz %5.1f Mbaud phase %2d: clean %d inverted %d beating %d partial %d (%.0f bit errors in %d bits)" % (
                            mhz, 100.0 / p, ph, c["clean"], c["inverted"], c["beating"], c["partial"], c["err_bits_partial"], c["bits"]), flush=True)
                    save("ber2_partial", out)
                for p in (1, 2):
                    rows = [r for r in out["phases"] if r["mhz"] == mhz and r["period"] == p]
                    best = max(rows, key=lambda r: (r["clean"], -r["partial"]))["phase"]
                    for dsa in [float(x) for x in np.arange(max(self.dsa_min(mhz), reg - 6), 31.76, 2.0)] + [31.75]:
                        lk = self.acquire0(mhz, dsa, cen)
                        if lk is None:
                            out["levels"].append({"mhz": mhz, "period": p, "dsa": dsa, "error": "no lock"})
                            continue
                        side, a = lk["side"], abs(lk["frame"]["di"])
                        c = self.segs(side, p, best, n=25, seconds=0.04)
                        c.update(mhz=mhz, period=p, phase=best, dsa=dsa, a_leg=a)
                        out["levels"].append(c)
                        print("%d MHz %5.1f Mbaud DSA %5.2f leg %.3f: clean %d inverted %d beating %d partial %d (%.0f in %d bits)" % (
                            mhz, 100.0 / p, dsa, a, c["clean"], c["inverted"], c["beating"], c["partial"], c["err_bits_partial"], c["bits"]), flush=True)
                    save("ber2_partial", out)
        finally:
            self.cleanup()
            path = save("ber2", out)
            self.b.record("verdict", test="campaign_ber2", ok=None, file=path,
                          text="the BER in short segments, each clean / inverted (a 180-degree slip) / partial; the data's "
                               "push on the loop's lock point; against the rate, the phase and the DSA")
        return out

    # ---- the schemes, random messages ----
    def scheme_run(self, name, side, count=20000, period=2000, width=20, delay=16, first_edge=False, window=100):
        cl = self.cl
        tx = SCHEMES[name]
        rx = Frame0(tx, side)
        rx_s = Scheme(name, tx.text, rx.rx_point(tx.idle), [rx.rx_point(m) for m in tx.msgs], [], t=tx.t, t2=tx.t2)
        rx_s.mask, rx_s.use = tx.mask, tx.use
        cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
        cl.rx_config(rx_s.idle_vector(), rx_s.mask, rx_s.lut(first_edge), rx_s.slow_exp(), delay=delay, quiet=4,
                     confirm=10, window=window, first_edge=first_edge)
        cl.hist_config("ref_to_decision", 0)
        cl.events(period=period, width=width, count=count, n=tx.n, source="prbs" if tx.n > 1 else "count")
        cl.rx_clear()
        cl.tx_go()
        time.sleep(period * count * cl.t_clk + 0.2)
        st = cl.rx_stats()
        cm = cl.confusion()
        st["confusion"] = [row[:tx.n] for row in cm[:tx.n]]
        st["symbol_errors"] = sum(cm[a][b] for a in range(tx.n) for b in range(tx.n) if a != b)
        st["right"] = sum(cm[a][a] for a in range(tx.n))
        lo, hi = st["lat_min"], st["lat_max"]
        if st["lat_n"] and hi < 1000:
            cl.wr("RX_HIST_ADDR", 0)
            st["hist"] = [cl.rd("RX_HIST_DATA") for _ in range(hi + 2)]
        cl.hold_point(1, 0)
        return st

    def schemes(self):
        out = {"runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                reg = self.regulated_dsa(mhz)
                for dd in (-6, -3, 0, 3, 6, 9):
                    dsa = min(31.75, max(self.dsa_min(mhz), reg + dd))
                    lk = self.lock_at(mhz, dsa)
                    if lk is None:
                        out["runs"].append({"mhz": mhz, "dsa": dsa, "error": "no lock"})
                        print("%d DSA %.2f no lock" % (mhz, dsa), flush=True)
                        continue
                    cen, side, a_leg, _ = lk
                    for frac in (0.3, 0.4, 0.5, 0.6):
                        th = self.thresholds(cen, a_leg, frac)
                        idle = self.cl.gate(seconds=0.2)
                        false_idle = sum(idle[k]["edges"] for k in ("CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN"))
                        for name in ("A1", "A1w", "A2", "A3"):
                            side = self.ensure(mhz, dsa, cen, a_leg) or side
                            st = self.scheme_run(name, side)
                            lat = [st[k] * st["sample_ns"] for k in ("lat_min", "lat_mean", "lat_max")] if st["lat_n"] else None
                            st.update(mhz=mhz, dsa=dsa, dsa_rel=dd, a_leg=a_leg, frac=frac, scheme=name, side=side,
                                      thresholds=th, idle_edges_200ms=false_idle, lat_ns=lat)
                            out["runs"].append(st)
                            print("%d DSA %5.2f leg %.3f frac %.1f %-3s: sent %d decided %d right %d wrong %d false %d missed %d; %s ns; idle edges %d" % (
                                mhz, dsa, a_leg, frac, name, st["events"], st["decided"], st["right"], st["symbol_errors"],
                                st["false"], st["missed"], lat and "%.1f/%.1f/%.1f" % tuple(lat), false_idle), flush=True)
                    save("schemes_partial", out)
        finally:
            self.cleanup()
            path = save("schemes", out)
            self.b.record("verdict", test="campaign_schemes", ok=None, file=path,
                          text="A1/A1w/A2/A3 with PRBS-chosen messages against the DSA, the windows' place and the carrier")
        return out

    # ---- how fast the events may come ----
    def rate(self, mhz=5000):
        out = {"mhz": mhz, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            reg = self.regulated_dsa(mhz)
            lk = self.lock_at(mhz, reg)
            cen, side, a_leg, _ = lk
            self.thresholds(cen, a_leg, 0.5)
            for name in ("A1", "A2", "A3"):
                for period in (2000, 500, 200, 100, 64, 48, 32, 24, 16):
                    for width in sorted(set([min(20, period // 2), max(2, period // 4)])):
                        side = self.ensure(mhz, reg, cen, a_leg) or side
                        count = int(min(50000, max(5000, 0.2 / (period * 1e-8))))
                        st = self.scheme_run(name, side, count=count, period=period, width=width,
                                             window=max(4, min(100, period - 6)))
                        st.update(scheme=name, period=period, width=width, count=count)
                        out["runs"].append(st)
                        print("%-3s every %4d clocks (%.2f Mev/s), %2d wide: sent %d decided %d right %d wrong %d false %d missed %d" % (
                            name, period, 100.0 / period, width, st["events"], st["decided"], st["right"], st["symbol_errors"],
                            st["false"], st["missed"]), flush=True)
        finally:
            self.cleanup()
            path = save("rate", out)
            self.b.record("verdict", test="campaign_rate", ok=None, file=path,
                          text="A1 / A2 / A3 against the event period: how fast the decoder takes events")
        return out

    # ---- the fast path's rings in this frame ----
    def rings(self, fracs=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7), dsas_rel=(-6, 0, 6), reps=3, clocks=2000):
        lc = self.lc() if hasattr(self, "lc") else None
        if lc is None:
            from netbus import NetBus
            from costaslink import CostasLink
            lc = CostasLink(NetBus(self.b.cfg["pynq_host"], self.b.cfg.get("pynq_port", 5800)))
        out = {"runs": [], "clocks": clocks}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                reg = self.regulated_dsa(mhz)
                for dd in dsas_rel:
                    dsa = min(31.75, max(self.dsa_min(mhz), reg + dd))
                    lk = self.lock_at(mhz, dsa)
                    if lk is None:
                        continue
                    cen, side, a_leg, _ = lk
                    for name in ("A3", "AX", "A1r"):
                        for t in fracs:
                            side = self.ensure(mhz, dsa, cen, a_leg) or side
                            th = self.thresholds(cen, a_leg, t)
                            sch = Frame0(RINGS[name], side)
                            hops = []
                            for _ in range(reps):
                                try:
                                    rg = lc.ring_run(sch, order=RING_ORDER[name], clocks=clocks, mask=0x1F)
                                    hops.append({k: rg.get(k) for k in ("hops", "span", "turnaround_ns")})
                                except Exception as e:                       # noqa: BLE001
                                    hops.append({"error": str(e)[:120]})
                                self.cl.hold_point(1, 0)
                            ok = [h["turnaround_ns"] for h in hops if h.get("turnaround_ns") and h.get("hops", 0) > 20
                                  and 0.97 < h["hops"] * h["turnaround_ns"] / (clocks * 10.0) < 1.03]
                            r = {"mhz": mhz, "dsa": dsa, "dsa_rel": dd, "a_leg": a_leg, "ring": name, "frac": t,
                                 "rings": hops, "hop_ns": float(np.mean(ok)) if ok else None, "n_clean": len(ok)}
                            out["runs"].append(r)
                            print("%d DSA %5.2f %-3s frac %.1f: hop %s ns (%d clean of %d; hops %s)" % (
                                mhz, dsa, name, t, "%.2f" % r["hop_ns"] if ok else "-", len(ok), reps,
                                [h.get("hops") for h in hops]), flush=True)
                    save("rings_partial", out)
        finally:
            try:
                lc.reply_off(); lc.fast_off(); lc.wr("RT_CFG", 0)
            except Exception:                                        # noqa: BLE001
                pass
            self.cleanup()
            path = save("rings", out)
            self.b.record("verdict", test="campaign_rings", ok=None, file=path,
                          text="the fast path's ring hop in the designed lock's frame (A3, the axis points, the +-I flip) "
                               "against the DSA and the windows' place")
        return out

    # ---- the per-carrier tables ----
    def cal(self, mhzs=(4900, 5000, 5100, 5200, 5300, 5400, 5500, 5600, 5800)):
        cl = self.cl
        vr0 = {k: cl.dac_volts()[k] for k in ("VR_I", "VR_Q")}
        out = {"vr_before": vr0, "rows": []}
        try:
            for mhz in mhzs:
                cl.dac(S.DAC1, VR_I=float(vr0["VR_I"]), VR_Q=float(vr0["VR_Q"]))
                self.tx(False)
                self.center(mhz)
                v_null, _ = self.null_fast_i()
                self.ioff(S.V_MID)
                cl.ctrl(loop_hold=1)
                self.tune(mhz)
                cl.dsa(float(self.dsa_min(mhz)))
                self.tx(True)
                cl.hold_point(1, 0)
                time.sleep(0.05)
                f1, p1 = self.rx_mon(mhz, span=200e3)

                def car():
                    self.b.sa_setup(f1, 20e3, rbw=300, ref=0.0, att=10)
                    self.b.sa.single()
                    return self.b.sa.peak()[1]
                cl.hold_point(0, 0)
                time.sleep(0.03)
                p0 = car()
                best = dict(vr0)
                for span, step in ((0.08, 0.01), (0.02, 0.0025)):
                    for k in ("VR_I", "VR_Q"):
                        res = []
                        for v in np.arange(best[k] - span, best[k] + span + 1e-9, step):
                            v = float(min(0.45, max(0.0, v)))
                            cl.dac(S.DAC1, **{k: v})
                            time.sleep(0.02)
                            res.append((v, car()))
                        best[k] = min(res, key=lambda x: x[1])[0]
                        cl.dac(S.DAC1, **{k: best[k]})
                p0n = car()
                cl.hold_point(1, 0)
                time.sleep(0.03)
                p1n = car()
                self.tx(False)
                row = {"mhz": mhz, "i_off_f_null": v_null, "carrier_dbm": p1, "null_before": p0, "dbc_before": p0 - p1,
                       "vr_null": best, "null_after": p0n, "carrier_after": p1n, "dbc_after": p0n - p1n}
                out["rows"].append(row)
                print("%d MHz: I_OFF_F null %s V; carrier %.1f dBm; feedthrough %.1f dBc as set, %.1f dBc at VR_I %.4f VR_Q %.4f" % (
                    mhz, "%.3f" % v_null if v_null is not None else "none", p1, p0 - p1, p0n - p1n, best["VR_I"], best["VR_Q"]), flush=True)
                save("cal_partial", out)
        finally:
            cl.dac(S.DAC1, VR_I=float(vr0["VR_I"]), VR_Q=float(vr0["VR_Q"]))
            self.cleanup()
            try:
                self.b.sa_live()
            except Exception:                                        # noqa: BLE001
                pass
            path = save("cal", out)
            self.b.record("verdict", test="campaign_cal", ok=None, file=path,
                          text="per carrier: the TX carrier null (VR_I / VR_Q; restored after) and the fast I comparator's "
                               "null (I_OFF_F): the firmware's tables")
        return out

    # ---- the loop against the level ----
    def dyn(self, mhz=5000, dsas_rel=(-6, -3, 0, 3, 6, 9)):
        out = {"mhz": mhz, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            reg = self.regulated_dsa(mhz)
            for dd in dsas_rel:
                dsa = min(31.75, max(self.dsa_min(mhz), reg + dd))
                lk = self.lock_at(mhz, dsa)
                if lk is None:
                    continue
                cen, side, a_leg, _ = lk
                print(" DSA %.2f, leg %.3f V:" % (dsa, a_leg), flush=True)
                sr = self.step_response(mhz, cen, delta=0.005)
                fits = [c["fit"] for c in sr["caps"] if c.get("fit") and c["fit"].get("model") == "under"
                        and 0.15 < c["fit"]["zeta"] < 2 and 300 < c["fit"]["fn_hz"] < 3e4]
                out["runs"].append({"dsa": dsa, "a_leg": a_leg, "step": sr, "fits": fits})
                self.cl.ctrl(loop_hold=1)
        finally:
            self.cleanup()
            path = save("dyn", out)
            self.b.record("verdict", test="campaign_dyn", ok=None, file=path,
                          text="the loop's step response against the DSA: f_n and damping against the leg")
        return out

    # ---- the slow path's working point ----
    def slow(self, vs=(1.65, 1.9, 2.1, 2.3, 2.5, 2.7, 2.9, 3.1)):
        cl = self.cl
        vr0 = {k: cl.dac_volts()[k] for k in ("VR_I", "VR_Q")}
        out = {"rows": []}
        null = {}
        try:
            cals = sorted(f for f in os.listdir(OUT) if f.startswith("cal_2")) if os.path.isdir(OUT) else []
            if cals:
                null = {r["mhz"]: r["vr_null"] for r in json.load(open(os.path.join(OUT, cals[-1])))["rows"]}
            self.scope_iq(vdiv=0.1)
            for mhz in (5000, 5200):
                if mhz in null:
                    cl.dac(S.DAC1, VR_I=float(null[mhz]["VR_I"]), VR_Q=float(null[mhz]["VR_Q"]))
                reg = self.regulated_dsa(mhz)
                lk = self.lock_at(mhz, reg, fresh=True)
                if lk is None:
                    continue
                cen, side, a_leg, _ = lk
                self.thresholds(cen, a_leg, 0.5)
                for v in vs:
                    cl.dac(S.DAC2, V_T2=float(v))
                    for name in ("A1", "A2", "A3"):
                        side = self.ensure(mhz, reg, cen, a_leg) or side
                        st = self.scheme_run(name, side, count=4000)
                        out["rows"].append({"mhz": mhz, "v_t2": v, "scheme": name, "nulled": mhz in null,
                                            **{k: st[k] for k in ("events", "decided", "confirm", "veto", "right", "symbol_errors")}})
                        print("%d V_T2 %.2f %-3s: decided %d confirmed %d vetoed %d" % (mhz, v, name, st["decided"], st["confirm"], st["veto"]), flush=True)
                cl.dac(S.DAC2, V_T2=S.V_MID)
                cl.dac(S.DAC1, VR_I=float(vr0["VR_I"]), VR_Q=float(vr0["VR_Q"]))
        finally:
            cl.dac(S.DAC2, V_T2=S.V_MID)
            cl.dac(S.DAC1, VR_I=float(vr0["VR_I"]), VR_Q=float(vr0["VR_Q"]))
            self.cleanup()
            path = save("slow", out)
            self.b.record("verdict", test="campaign_slow", ok=None, file=path,
                          text="A1 / A2 / A3 confirmed against V_T2 with the carrier nulled per frequency")
        return out

    def cleanup(self):
        try:
            self.cl.tx_stop()
        except Exception:                                            # noqa: BLE001
            pass
        self.cl.ctrl(loop_hold=1)
        self.ioff(S.V_MID)
        self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.cl.dac(S.DAC2, V_T2=S.V_MID)
        self.quiet()


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="+", choices=["ber", "ber2", "schemes", "rate", "rings", "cal", "dyn", "slow"])
    a = ap.parse_args(argv)
    C = Camp()
    for s in a.sections:
        print("==== %s %s" % (s, time.strftime("%H:%M:%S")), flush=True)
        try:
            getattr(C, s)()
        except Exception as e:                                       # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("==== %s FAILED: %s" % (s, e), flush=True)
            C.cleanup()


if __name__ == "__main__":
    main(sys.argv[1:])
