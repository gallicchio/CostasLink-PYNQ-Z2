#!/usr/bin/env python3
"""linktests.py: board A in loopback, the night of 2026-10-29 (Jason: "push this board as fast as possible as built":
the loop, every modulation scheme the board was designed for, and the latencies, before any rework).  The bench as
Jason left it: TX ANT -> 10 cm RG-316 -> two 20 dB pads -> RX ANT; the DSA875 on RX MON; the scope's ch1 REF OUT, ch2 I
MON, ch3 Q MON, ch4 VC MON (1 Mohm); the generator on REF IN, unused (JP201 on TCXO).

The receive chain works at 4.9-5.2 GHz (8-12 dB short of plan) and not at 5.8 (31 dB short: REVB 8), so the tests run
low in the band.  The Costas loop's sign is inverted on rev A's default jumpers (REVB 9): it locks 90 degrees round with
sign(I) chattering.  Until the jumpers are moved, `plain` forces sign(I) constant with an extreme I_OFF_F (the fast I
arm's trim, as loop_center's trial pulses do), so ERR = +-Q and the loop is a plain PLL on Q, which the inverted sign
locks at a normal, steady point.

    python3 bringup/linktests.py force   [--mhz 5000]        does an extreme I_OFF_F hold CMP_I still against the carrier
    python3 bringup/linktests.py lockcmp [--mhz 5000 5100 5200]   the plain PLL against the inverted Costas lock
    python3 bringup/linktests.py schemes [--mhz 5100]       every scheme through the loop: latency, confusion, false events
    python3 bringup/linktests.py lodrive [--mhz 5000 5200 5800]   tests D and E: each synthesizer's RFOUTA power against the
                                                            TX level (RX MON) and the I/Q beat (sim/aslaid/REPORT.md)

Each writes bringup/data/board_A/link/<section>_<time>.json and one verdict line to the board's log, and leaves the
transmitter muted, the DSA at 31.75 dB, the loop held, I_OFF_F at V_MID.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import overnight as O                               # noqa: E402
import stages as S                                  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "gateware", "driver"))
sys.path.insert(0, os.path.join(HERE, "..", "gateware"))
from costaslink import (Scheme, CostasLink, point_code, CMP_I, CMP_QP, CMP_QN, CMP_IP,   # noqa: E402
                        CMP_IN, CMP_NAMES, AD5696R_VREF)

OUT = os.path.join(HERE, "data", "board_A", "link")
KV_HZ_PER_V_5800 = 457e3                            # the RX LO's pull at 5.8 GHz (78.8 ppm/V x 25 MHz x 232)
VC_LOCK = 1.861                                     # VCXO = TCXO (stage 3.3, every frequency)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class Link(O.Night):
    def __init__(self):
        super().__init__("link")

    def regulated_dsa(self, mhz, demod_dbm=-20.0):
        """the DSA for the plan's -20 dBm at the demodulator, never under dsa_min"""
        rx_ant = O.interp(self.tx_dbm, mhz) - O.PAD_DB
        return min(31.75, max(self.dsa_min(mhz), math.ceil((rx_ant + O.interp(self.chain0, mhz) - demod_dbm) * 4) / 4))

    def kv(self, mhz):
        return KV_HZ_PER_V_5800 * mhz / 5800.0

    def set_vc(self, vc_target):
        """VC = 3 V_MID - U112A - VC_OFF, the loop held"""
        vc, u = self.u112a()
        v = 3 * S.V_MID - u - vc_target
        v = min(3.2, max(0.1, v))
        self.cl.dac(S.DAC1, VC_OFF=float(v))
        time.sleep(0.05)
        return self.cl.adc("VC"), v

    def edges(self, seconds=0.01):
        """the fast comparators' edges and high fractions over a gate (the counting gate, seq_gate.v)"""
        g = self.cl.gate(seconds=seconds)
        return g

    def ioff(self, v):
        self.cl.dac(S.DAC2, I_OFF_F=float(v))
        time.sleep(0.02)

    # ---- does an extreme I_OFF_F hold sign(I) against the carrier? ----
    def force(self, mhz=5000, dsas=None, ioffs=(S.V_MID, 3.0, 3.3, 0.3, 0.0)):
        out = {"mhz": mhz, "rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            reg = self.regulated_dsa(mhz)
            dsas = dsas or sorted({self.dsa_min(mhz), reg, min(31.75, reg + 6), 31.75})
            out["regulated_dsa"] = reg
            self.set_vc(VC_LOCK + 5e3 / self.kv(mhz))          # a 5 kHz beat, held
            self.tx(True)
            for d in dsas:
                self.cl.dsa(float(d))
                for v in ioffs:
                    self.ioff(v)
                    g = self.edges(0.01)
                    iq = self.iq_meas()
                    row = {"dsa": d, "i_off_f": v, "gate": g, "iq": iq, "adc_i": self.cl.adc("I"), "adc_q": self.cl.adc("Q"),
                           "err": self.cl.adc("ERR")}
                    out["rows"].append(row)
                    print("DSA %5.2f I_OFF_F %.2f: CMP_I edges %d duty %.3f, QP %d, QN %d; I pp %s mean %s, ERR %.3f" % (
                        d, v, g["CMP_I"]["edges"], g["CMP_I"]["duty"], g["CMP_QP"]["edges"], g["CMP_QN"]["edges"],
                        iq[2]["PKPK"], iq[2]["MEAN"], row["err"]), flush=True)
        finally:
            self.ioff(S.V_MID)
            self.quiet()
        path = save("force", out)
        self.b.record("verdict", test="link_force", ok=None, file=path,
                      text="CMP_I's edges against I_OFF_F with a 5 kHz beat held, per DSA: where the trim holds sign(I)")
        return out

    # ---- one release ----
    def trial(self, mhz, ioff, vc_start, dsa, settle_s=2.0, center=True):
        self.tx(False)
        if center and not self.center(mhz):
            return {"state": "not_centred"}
        self.cl.dsa(float(dsa))
        vc0, vco = self.set_vc(vc_start)
        self.ioff(ioff)
        self.tx(True)
        self.s.timebase(scale=1e-3)
        time.sleep(0.4)
        pp_held = self.s.pava("PKPK", 2)
        self.cl.ctrl(loop_hold=0)
        time.sleep(settle_s)
        st, info = self.lock_state()
        g = self.edges(0.01)
        # lock_state's absolute 0.12 V p-p is for the regulated level; at a weak level the beat itself is under it, so
        # a lock is VC holding through the step AND the I arm's swing under a third of the held beat's
        if st in ("locked", "false") and pp_held:
            st = "locked" if (info.get("pp_1ms") or 0) < max(0.02, pp_held / 3.0) else "false"
        info.update(state=st, vc_start=vc0, vc_off=vco, pp_held=pp_held, gate=g, adc_q=self.cl.adc("Q"),
                    adc_i=self.cl.adc("I"))
        return info

    def lockcmp(self, mhzs=(5000, 5100, 5200), offsets_khz=(-40, -20, -10, -5, -2, 2, 5, 10, 20, 40),
                conds=(("costas", S.V_MID, -2), ("costas", S.V_MID, 0), ("costas", S.V_MID, 4), ("costas", S.V_MID, 8),
                       ("plain", 0.3, 31.75), ("plain", 0.0, 31.75), ("plain", 0.0, 29.0))):
        """conds: (kind, I_OFF_F, DSA): a DSA under 20 is a step from the regulated level, else absolute.  The force
        test (20:05) found an extreme I_OFF_F holds CMP_I only at DSA 31.75 at 5.0 GHz (0.3 or 0 V; 3.0 V never
        does), so the plain PLL is tried there"""
        out = []
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in mhzs:
                if not self.alive():
                    break
                reg = self.regulated_dsa(mhz)
                rec = {"mhz": mhz, "regulated_dsa": reg, "rows": []}
                for kind, ioff, dd in conds:
                        dsa = min(31.75, max(self.dsa_min(mhz), reg + dd if dd < 20 else dd))
                        for off in offsets_khz:
                            vs = VC_LOCK + off * 1e3 / self.kv(mhz)
                            info = self.trial(mhz, ioff, vs, dsa)
                            self.cl.ctrl(loop_hold=1)
                            info.update(kind=kind, i_off_f=ioff, dsa=dsa, offset_khz=off)
                            rec["rows"].append(info)
                            print("%d %s I_OFF_F %.2f DSA %5.2f start %+3d kHz (VC %.3f) -> %s  VC %.3f U112A %.2f pp %s/%s Q %.3f" % (
                                mhz, kind, ioff, dsa, off, info.get("vc_start", float("nan")), info["state"], info.get("vc", float("nan")),
                                info.get("u112a", float("nan")), info.get("pp_1ms"), info.get("pp_held"), info.get("adc_q", float("nan"))), flush=True)
                self.tx(False)
                out.append(rec)
                save("lockcmp_partial", out)
        finally:
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("lockcmp", out)
        n = {"%s %.2f %g" % c: sum(1 for r in out for x in r["rows"] if (x.get("kind"), x.get("i_off_f")) == c[:2] and x["state"] == "locked") for c in conds}
        self.b.record("verdict", test="link_lockcmp", ok=None, file=path, locks=n,
                      text="releases from +-2..40 kHz at three trims of I_OFF_F (V_MID: the inverted Costas loop; 3.0 / 0.3: a plain PLL on Q) and four DSA settings")
        return out

# ---- the schemes in the inverted loop's frame ----
WIN = [CMP_QP, CMP_QN, CMP_IP, CMP_IN]                 # the four windows: the decisions read these, never CMP_I


def rx_schemes(rot, mirror=False):
    """the schemes the board can decide at the inverted Costas lock: the idle lands on +-Q (rot +-90), sign(I)
    chatters there, so every decision is the windows'.  TX points as the plan's (PLAN.md section 18), the frame the
    lock's.  A1 (sign(I)) has no equivalent; its flip is decided by QP / QN here (A1q).

    mirror: rev A's I arm is inverted (Response 10's ILO on U105's + input; REVB 9), so the board's (I, Q) is the
    TX point reflected (I -> -I) and then turned, not only turned.  Returns (tx, rx) pairs: tx the scheme the
    transmitter sends, rx the same messages as the receiver's comparators see them (the table, idle and mask)."""
    defs = [("A1q", "BPSK flip: the idle (on +-Q here) to its opposite, QP / QN", (1, 0), [(-1, 0)], [CMP_QP, CMP_QN]),
            ("OOK", "on-off: the idle to the null (0, 0), QP / QN", (1, 0), [(0, 0)], [CMP_QP, CMP_QN]),
            ("A2r", "1 bit: the plan's Q step, onto IP / IN in this frame", (1, 0), [(1, 1), (1, -1)], [CMP_IP, CMP_IN]),
            ("A3r", "2 bits: the plan's corners round a full idle (its QPSK), all four windows", (1, 0),
             [(1, 1), (1, -1), (-1, 1), (-1, -1)], [CMP_IP, CMP_IN, CMP_QP, CMP_QN])]
    out = []
    for name, text, idle, msgs, mask in defs:
        tx = Scheme(name, text, idle, msgs, mask, rot_deg=rot, use=WIN)
        if mirror:
            m = lambda p: (-p[0], p[1])                                  # noqa: E731
            rx = Scheme(name, text + " (I mirrored)", m(idle), [m(x) for x in msgs], mask, rot_deg=-rot, use=WIN)
        else:
            rx = tx
        out.append((tx, rx))
    return out


class Schemes(Link):
    def centres(self, span=0.06, step=0.002, seconds=0.02):
        """each window comparator's no-carrier level (TX muted, the loop held): Rice's parabola's peak"""
        import numpy as np
        self.cl.ctrl(loop_hold=1, tx_dis=1)
        time.sleep(0.05)
        out = {}
        for w in ("QP", "QN", "IP", "IN"):
            volts = [float(v) for v in np.arange(S.V_MID - span, S.V_MID + span + 1e-9, step)]
            pts = self.cl.threshold_scan(w, volts, seconds=seconds)
            try:
                v0, sig, nu0 = CostasLink.rice_fit([p for p in pts if p[1] > 0])
            except ValueError:
                v0, sig, nu0 = None, None, None
            # the 50 % duty crossing, which needs no fit (a narrow parabola gives Rice too few points at 2 mV steps)
            v50 = None
            for (va, ra, da), (vb, rb, db) in zip(pts, pts[1:]):
                if (da - 0.5) * (db - 0.5) <= 0 and da != db:
                    v50 = va + (0.5 - da) * (vb - va) / (db - da)
                    break
            if v0 is None or (v50 is not None and abs(v0 - v50) > 0.01):
                v0 = v50
            out[w] = {"v0": v0, "sigma": sig, "nu0": nu0, "scan": pts}
            print("centre", w, v0, "sigma", sig, flush=True)
        out["adc_i0"], out["adc_q0"] = self.cl.adc("I"), self.cl.adc("Q")
        return out

    def acquire_lock(self, mhz, dsa, starts_khz=(5, -5, 2, -2, 10, 20), ioff=S.V_MID):
        for k in starts_khz:
            info = self.trial(mhz, ioff, VC_LOCK + k * 1e3 / self.kv(mhz), dsa)
            if info["state"] == "locked" or (info["state"] == "false" and abs(info.get("vc", 0) - VC_LOCK) < 0.012
                                             and (info.get("pp_1ms") or 1) < 0.06):
                info["start_khz"] = k
                return info
            self.cl.ctrl(loop_hold=1)
        return None

    def frame(self, cen, a_ref=None):
        """the lock's frame now, from the Q leg's DC against its no-carrier level: rot +90 (idle on +Q) or -90, and
        whether it looks locked (the leg a good fraction of the idle's amplitude away, the windows quiet).  No VC_OFF
        step: that step can kick the inverted loop to its other stable point, 180 degrees round"""
        q = self.cl.adc("Q")
        dq = q - cen["adc_q0"]
        g = self.cl.gate(seconds=0.01, inputs=("CMP_QP", "CMP_QN"))
        quiet = g["CMP_QP"]["edges"] + g["CMP_QN"]["edges"] < 50
        ok = quiet and (a_ref is None or abs(dq) > 0.6 * a_ref)
        return (90.0 if dq > 0 else -90.0), ok, {"dq": dq, "qp_edges": g["CMP_QP"]["edges"], "qn_edges": g["CMP_QN"]["edges"]}

    def thresholds(self, cen, a_leg, t=0.5):
        th = {}
        for w in ("QP", "QN", "IP", "IN"):
            v = (cen[w]["v0"] or S.V_MID) + t * a_leg
            v = min(AD5696R_VREF - 0.001, max(0.0, v))
            self.cl.threshold(w, v)
            th[w] = v
        return th

    def run_scheme(self, s, period=2000, width=20, count=20000, first_edge=False, delay=16):
        cl = self.cl
        s_tx, s_rx = s if isinstance(s, tuple) else (s, s)
        s = s_tx
        cl.tx_points(s_tx.tx_idle(), [point_code(i, q) for i, q in s_tx.msgs])
        cl.rx_config(s_rx.idle_vector(), s_rx.mask, s_rx.lut(first_edge), s_rx.slow_exp(), delay=delay, quiet=4,
                     confirm=6, window=100, first_edge=first_edge)
        cl.hist_config("ref_to_decision", 0)
        cl.events(period=period, width=width, count=count, n=s.n)
        cl.rx_clear()
        cl.tx_go()
        time.sleep(period * count * cl.t_clk + 0.2)
        st = cl.rx_stats()
        st["confusion"] = cl.confusion()
        lo, hi = st["lat_min"], st["lat_max"]
        if st["lat_n"] and hi < 1000:
            cl.wr("RX_HIST_ADDR", 0)
            st["hist"] = [cl.rd("RX_HIST_DATA") for _ in range(hi + 2)]
        st["last"] = cl.rx_last()
        cl.hold_point(1, 0)                                   # back to the idle, the loop's carrier
        return st

    def scope_constellation(self, s, period=2500, width=500, tdiv=20e-6, vdiv=0.05):
        """long events (5 us: the MON taps' 1 k into the cable is ~0.1 us) cycling through the messages, both MONs"""
        import numpy as np
        cl, sc = self.cl, self.s
        s = s[0] if isinstance(s, tuple) else s
        cl.tx_points(s.tx_idle(), [point_code(i, q) for i, q in s.msgs])
        cl.events(period=period, width=width, count=0, n=s.n)
        cl.tx_go()
        for ch in (2, 3):
            sc.channel(ch, on=True, scale=vdiv, offset=-1.63, coupling="DC", impedance="1M")
        sc.timebase(scale=tdiv)
        sc.trigger(source=3, level=1.63, slope="rising", mode="auto")
        time.sleep(0.3)
        try:
            sc.single(timeout=3.0)
        except TimeoutError:
            sc.acquire_now()
        t2, v2, _ = sc.waveform(2)
        t3, v3, _ = sc.waveform(3)
        sc.run()
        cl.tx_stop()
        cl.hold_point(1, 0)
        k = max(1, len(v2) // 20000)
        return {"t": list(np.asarray(t2)[::k]), "i": list(np.asarray(v2)[::k]), "q": list(np.asarray(v3)[::k])}

    def fsk(self, periods=(25, 10, 5, 2), n_caps=2):
        """TX_MODE 4: the four axis points in turn, forwards and backwards; the capture's window comparators give the
        rotation's sense (the loop held through it)"""
        cl = self.cl
        pts = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        cl.tx_points(point_code(1, 0), [point_code(i, q) for i, q in pts])
        out = []
        for p in periods:
            for back in (False, True):
                cl.ctrl(loop_hold=1)
                cl.tx_timing(period=p, width=1, count=0)
                cl.tx_mode("rotate", n=4, backwards=back)
                cl.tx_go()
                time.sleep(0.002)
                cap = cl.capture("none", post=4000, start=cl.cap_force, timeout=1.0) if False else None
                cl.cap_arm("none", post=4000)
                cl.cap_force()
                c = cl.cap_read(timeout=1.0)
                cl.tx_stop()
                cl.hold_point(1, 0)
                cl.ctrl(loop_hold=0)
                seq = fsk_order(c)
                out.append({"period_clocks": p, "f_hz": 1.0 / (4 * p * cl.t_clk), "backwards": back, **seq})
                print("FSK period %d (%.2f MHz) %s: %s" % (p, 1e-6 / (4 * p * cl.t_clk), "back" if back else "fwd", seq), flush=True)
                time.sleep(0.3)
        return out

    def ber_hold(self, rot, periods=(100, 20, 10, 5, 2, 1), seconds=0.02):
        """the PRBS on the TX's Q axis, which this frame puts on I, decided by sign(I), the loop held for each run
        (the hold walks the phase ~0.1 rad in 13 ms)"""
        cl = self.cl
        # TX (0, -1) lands at (sin rot, -cos rot) ... rot +90: (+1, 0): CMP_I high
        m0 = (0, -1)
        i0 = -m0[1] * math.sin(math.radians(rot))            # the I component of message 0 in the RX frame
        cl.tx_points(point_code(1, 0), [point_code(*m0), point_code(0, 1)])
        out = []
        for p in periods:
            best = None
            for inv in (i0 > 0, not i0 > 0):                   # the mirrored I arm can flip it: keep the better
                cl.ctrl(loop_hold=1)
                r = cl.ber_run(seconds=seconds, poly=15, period=p, n=2, invert=inv)
                cl.hold_point(1, 0)
                cl.ctrl(loop_hold=0)
                r.update(period_clocks=p, baud=1.0 / (p * cl.t_clk), invert=inv)
                if best is None or (r["ber"] is not None and (best["ber"] is None or r["ber"] < best["ber"])):
                    best = r
                time.sleep(0.4)
            out.append(best)
            print("BER %.1f Mbaud: %s" % (best["baud"] / 1e6, best), flush=True)
        return out

    def schemes(self, mhz=5000, dsa_steps=(0, -2, 2), count=20000):
        out = {"mhz": mhz, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            out["centres"] = cen = self.centres()
            reg = self.regulated_dsa(mhz)
            out["regulated_dsa"] = reg
            for dd in dsa_steps:
                dsa = min(31.75, max(self.dsa_min(mhz), reg + dd))
                lk = self.acquire_lock(mhz, dsa)
                if lk is None:
                    out["runs"].append({"dsa": dsa, "error": "no lock"})
                    print("DSA", dsa, "no lock", flush=True)
                    continue
                q, i = self.cl.adc("Q"), self.cl.adc("I")
                dq, di = q - cen["adc_q0"], i - cen["adc_i0"]
                rot = 90.0 if dq > 0 else -90.0
                a_leg = abs(dq)
                th = self.thresholds(cen, a_leg)
                run = {"dsa": dsa, "lock": {k: v for k, v in lk.items() if k != "gate"}, "rot_deg": rot, "a_leg": a_leg,
                       "di_idle": di, "thresholds": th, "idle_gate": self.cl.gate(seconds=0.05), "schemes": []}
                print("DSA %.2f locked (start %+d kHz): rot %+d, a_leg %.3f V, dI %.3f; thresholds %s" % (
                    dsa, lk["start_khz"], rot, a_leg, di, {k: round(v, 3) for k, v in th.items()}), flush=True)
                # which handedness: A3r both ways, keep the one whose confusion matrix is diagonal
                diag = {}
                for mir in (False, True):
                    pair = [p for p in rx_schemes(rot, mir) if p[0].name == "A3r"][0]
                    st = self.run_scheme(pair, count=4000)
                    cm = st["confusion"]
                    diag[mir] = sum(cm[k][k] for k in range(4))
                    run.setdefault("mirror_test", {})[str(mir)] = {"confusion": cm, "decided": st["decided"]}
                mirror = diag[True] > diag[False]
                run["mirror"] = mirror
                print("  handedness: diagonal %s -> mirror %s" % (diag, mirror), flush=True)
                names = [p[0].name for p in rx_schemes(rot, mirror)]
                for name in names:
                    for fe in ((False, True) if name in ("A2r", "A3r") else (False,)):
                        rot_now, ok, fi = self.frame(cen, a_leg)
                        if not ok:
                            if self.acquire_lock(mhz, dsa) is None:
                                break
                            rot_now, ok, fi = self.frame(cen, a_leg)
                        s = [p for p in rx_schemes(rot_now, mirror) if p[0].name == name][0]
                        st = self.run_scheme(s, count=count, first_edge=fe)
                        s0 = s[0]
                        st.update(scheme=s0.name, text=s0.text, first_edge=fe, n=s0.n, rot_deg=rot_now, mirror=mirror, frame_before=fi)
                        r2, ok2, fi2 = self.frame(cen, a_leg)
                        st["state_after"] = ("locked" if ok2 else "lost") + ("" if r2 == rot_now else ", flipped")
                        st["frame_after"] = fi2
                        run["schemes"].append(st)
                        lat = [to_ns(st[k]) for k in ("lat_min", "lat_mean", "lat_max")] if st["lat_n"] else None
                        print("  %s%s: refs %d events %d decided %d false %d missed %d veto %d; latency %s ns; lock after: %s" % (
                            s0.name, " first-edge" if fe else "", st["refs"], st["events"], st["decided"], st["false"],
                            st["missed"], st["veto"], lat and ["%.1f" % x for x in lat], st["state_after"]), flush=True)
                        if not ok2 and self.acquire_lock(mhz, dsa) is None:
                            break
                if dd == dsa_steps[0]:
                    run["constellations"] = {}
                    for name in names:
                        rot_now, ok, _ = self.frame(cen, a_leg)
                        if not ok and self.acquire_lock(mhz, dsa) is None:
                            break
                        rot_now, ok, _ = self.frame(cen, a_leg)
                        s = [p for p in rx_schemes(rot_now, mirror) if p[0].name == name][0]
                        c = self.scope_constellation(s)
                        c["rot_deg"] = rot_now
                        run["constellations"][name] = c
                    save("schemes_partial", out | {"runs": out["runs"] + [run]})
                    run["fsk"] = self.fsk()
                    rot_now, ok, _ = self.frame(cen, a_leg)
                    if not ok:
                        self.acquire_lock(mhz, dsa)
                        rot_now, ok, _ = self.frame(cen, a_leg)
                    run["ber"] = self.ber_hold(rot_now)
                out["runs"].append(run)
                save("schemes_partial", out)
        finally:
            self.cl.ctrl(loop_hold=1)
            try:
                self.cl.tx_stop()
            except Exception:                                        # noqa: BLE001
                pass
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("schemes", out)
        self.b.record("verdict", test="link_schemes", ok=None, file=path,
                      text="every scheme the inverted Costas lock can decide, through the loop at %d MHz: latency, confusion, false events, the constellations, FSK's sense, the BER" % mhz)
        return out

    # ---- the fast I arm's offset, nulled (stage 3.2), and A3r tuned ----
    def null_fast_i(self, lo=0.0, hi=3.3, steps=14, seconds=0.01):
        """with no carrier (TX muted, the loop held) move I_OFF_F until CMP_I's duty is 50 %: the inverted lock then
        sits on +-Q exactly, not 10 degrees round (the arm's -26 mV put the idle at the comparator's threshold)"""
        self.cl.ctrl(loop_hold=1, tx_dis=1)
        time.sleep(0.05)
        trace = []

        def duty(v):
            self.ioff(v)
            g = self.cl.gate(seconds=seconds, inputs=("CMP_I",))
            trace.append((v, g["CMP_I"]["duty"], g["CMP_I"]["edges"]))
            return g["CMP_I"]["duty"]
        dlo, dhi = duty(lo), duty(hi)
        if (dlo - 0.5) * (dhi - 0.5) > 0:
            self.ioff(S.V_MID)
            return None, trace
        for _ in range(steps):
            mid = (lo + hi) / 2
            dm = duty(mid)
            if (dm - 0.5) * (dlo - 0.5) > 0:
                lo, dlo = mid, dm
            else:
                hi, dhi = mid, dm
        v = (lo + hi) / 2
        self.ioff(v)
        return v, trace

    def tune_a3(self, mhz, dsa=None, fracs=(0.35, 0.45, 0.55), delays=(16, 24, 32), count=20000):
        out = {"mhz": mhz}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            v, tr = self.null_fast_i()
            out["i_off_f"], out["null_trace"] = v, tr
            print("I_OFF_F null:", v, tr[-3:], flush=True)
            cen = self.centres()
            out["centres"] = cen
            dsa = dsa if dsa is not None else self.regulated_dsa(mhz)
            out["dsa"] = dsa
            lk = self.acquire_lock(mhz, dsa, ioff=v if v is not None else S.V_MID)
            if lk is None:
                out["error"] = "no lock"
                return out
            rot, ok, fi = self.frame(cen)
            a_leg = abs(fi["dq"])
            out.update(rot_deg=rot, a_leg=a_leg, di_idle=self.cl.adc("I") - cen["adc_i0"])
            print("locked: rot %+d a_leg %.3f dI %.3f" % (rot, a_leg, out["di_idle"]), flush=True)
            out["runs"] = []
            for fr in fracs:
                self.thresholds(cen, a_leg, t=fr)
                for dl in delays:
                    rot, ok, fi = self.frame(cen, a_leg)
                    if not ok:
                        if self.acquire_lock(mhz, dsa, ioff=v if v is not None else S.V_MID) is None:
                            break
                        rot, ok, fi = self.frame(cen, a_leg)
                        a_leg2 = abs(fi["dq"])
                        self.thresholds(cen, a_leg2, t=fr)
                    s = [p for p in rx_schemes(rot, True) if p[0].name == "A3r"][0]
                    st = self.run_scheme(s, count=count, delay=dl)
                    n = 4
                    st.update(frac=fr, delay=dl, rot_deg=rot, cm=[row[:n] for row in st["confusion"][:n]])
                    out["runs"].append(st)
                    print("t %.2f delay %d samples: decided %d/%d false %d missed %d, latency %.1f/%.1f/%.1f ns, diag %s" % (
                        fr, dl, st["decided"], st["refs"], st["false"], st["missed"], to_ns(st["lat_min"]),
                        to_ns(st["lat_mean"] or 0), to_ns(st["lat_max"]), [st["cm"][k][k] for k in range(4)]), flush=True)
        finally:
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("tune_a3_%d" % mhz, out)
        self.b.record("verdict", test="link_tune_a3", ok=None, file=path,
                      text="A3r (two bits, four non-idle states) against the window fraction and the decision delay, the fast I arm nulled first")
        return out

    # ---- the pilot schemes (B1, B2, A4): a weak pilot made by the ladders' references (PLAN.md section 18) ----
    def beat_pp(self, ch=3, n=3):
        self.s.timebase(scale=100e-6)
        time.sleep(0.25)
        v = [self.s.pava("PKPK", ch) for _ in range(n)]
        v = [x for x in v if x]
        return sorted(v)[len(v) // 2] if v else None

    def pilot_cal(self, mhz, dsa, rho=0.2, d0=0.02):
        """the VR_I / VR_Q offsets from the null that make a pilot of rho x the idle's amplitude along TX I and TX Q:
        the loop held 5 kHz off zero beat, the beat's p-p on both MONs (the larger of the two: the beat sweeps both)"""
        cl = self.cl
        null = cl.dac_volts()
        vr_i0, vr_q0 = null["VR_I"], null["VR_Q"]
        self.tx(False)
        self.center(mhz)
        cl.dsa(float(dsa))
        self.set_vc(VC_LOCK + 5e3 / self.kv(mhz))
        cl.hold_point(1, 0)
        cl.ctrl(tx_dis=0)
        a_pp = max(self.beat_pp(2) or 0, self.beat_pp(3) or 0)
        out = {"a_pp": a_pp, "vr_i0": vr_i0, "vr_q0": vr_q0}
        for axis in ("VR_I", "VR_Q"):
            d = d0
            for _ in range(4):
                v = (vr_i0 if axis == "VR_I" else vr_q0) + d
                assert v <= S.VR_MAX_V
                cl.dac(S.DAC1, **{axis: float(v)})
                cl.hold_point(0, 0)
                p_pp = max(self.beat_pp(2) or 0, self.beat_pp(3) or 0)
                cl.dac(S.DAC1, VR_I=vr_i0, VR_Q=vr_q0)
                r = p_pp / a_pp if a_pp else 0
                print("pilot %s +%.4f V: %.3f of the idle" % (axis, d, r), flush=True)
                out.setdefault(axis + "_trace", []).append((d, r))
                if r <= 0.02:
                    d *= 3
                    continue
                if abs(r - rho) < 0.02:
                    break
                d = d * rho / r
            out[axis + "_delta"] = d
        cl.ctrl(tx_dis=1)
        cl.hold_point(1, 0)
        return out

    def pilot_schemes(self, mhz=5000, rho=0.2, lock_dsa=None, count=20000, frac=0.4, lock_db=0.0, vdiv=0.05):
        """lock on the pilot with the DSA lowered by its 14 dB, then B1, B2, A4 through the loop"""
        import numpy as np
        cl = self.cl
        out = {"mhz": mhz, "rho": rho}
        null = cl.dac_volts()
        vr_i0, vr_q0 = null["VR_I"], null["VR_Q"]
        self.scope_iq(vdiv=0.1)
        try:
            reg = self.regulated_dsa(mhz)
            cal = self.pilot_cal(mhz, reg, rho)
            out["cal"] = cal
            di, dq = cal["VR_I_delta"], cal["VR_Q_delta"]
            lock_dsa = lock_dsa if lock_dsa is not None else max(self.dsa_min(mhz), reg - 20 * math.log10(1 / rho) + lock_db)
            out["lock_dsa"] = lock_dsa
            defs = [("B1", "2 bits: a weak pilot on +I and the four axis points, one window each", (rho, 0.0),
                     [(1, 0), (-1, 0), (0, 1), (0, -1)]),
                    ("B2", "2 bits: the pilot at 45 degrees and the four corners onto the axes, one window each",
                     (rho / math.sqrt(2), rho / math.sqrt(2)), [(1, 1), (-1, -1), (-1, 1), (1, -1)]),
                    ("A4", "1 bit: the pilot at 45 degrees, TX (-1, 1) / (1, -1) onto the axis across it",
                     (rho / math.sqrt(2), rho / math.sqrt(2)), [(-1, 1), (1, -1)])]
            self.tx(False)
            self.center(mhz)
            v_null, _ = self.null_fast_i()
            v_null = v_null if v_null is not None else S.V_MID
            out["i_off_f"] = v_null
            cen = self.centres()
            out["centres"] = cen
            out["runs"] = []
            for name, text, pilot, msgs in defs:
                vr_i = vr_i0 + di * pilot[0] / rho
                vr_q = vr_q0 + dq * pilot[1] / rho
                cl.dac(S.DAC1, VR_I=float(vr_i), VR_Q=float(vr_q))
                # lock on the pilot: the idle is the (0, 0) point with the references offset
                lk = None
                for k in (5, -5, 2, -2, 10):
                    self.tx(False)
                    self.center(mhz)
                    self.ioff(v_null)
                    cl.dac(S.DAC1, VR_I=float(vr_i), VR_Q=float(vr_q))
                    cl.dsa(float(lock_dsa))
                    self.set_vc(VC_LOCK + k * 1e3 / self.kv(mhz))
                    cl.hold_point(0, 0)
                    cl.ctrl(tx_dis=0)
                    time.sleep(0.1)
                    cl.ctrl(loop_hold=0)
                    time.sleep(2.0)
                    rot0, ok, fi = self.frame(cen)
                    vc = cl.adc("VC")
                    if ok and abs(vc - VC_LOCK) < 0.012 and abs(fi["dq"]) > 0.01:
                        lk = {"start_khz": k, "vc": vc, **fi}
                        break
                    cl.ctrl(loop_hold=1)
                rec = {"scheme": name, "pilot": pilot, "vr_i": vr_i, "vr_q": vr_q, "lock": lk}
                if lk is None:
                    rec["error"] = "no lock on the pilot"
                    out["runs"].append(rec)
                    print(name, "no lock on the pilot", flush=True)
                    continue
                # the full points' amplitude: rho is the pilot's fraction of it
                p_leg = abs(lk["dq"])
                a_leg = p_leg / rho
                self.thresholds(cen, a_leg, t=frac)
                s_sign = 1 if lk["dq"] > 0 else -1
                m = lambda p: (-p[0], p[1])                              # noqa: E731
                mp = m(pilot)
                rot_m = math.degrees(math.atan2(s_sign, 0) - math.atan2(mp[1], mp[0]))
                tx = Scheme(name, text, (0, 0), msgs, [CMP_IP, CMP_IN, CMP_QP, CMP_QN], rot_deg=rot_m, pilot=pilot, use=WIN)
                rx = Scheme(name, text, (0, 0), [m(x) for x in msgs], [CMP_IP, CMP_IN, CMP_QP, CMP_QN], rot_deg=rot_m,
                            pilot=mp, use=WIN)
                try:
                    st = self.run_scheme((tx, rx), count=count)
                except ValueError as e:
                    rec["error"] = str(e)
                    out["runs"].append(rec)
                    continue
                cl.hold_point(0, 0)
                n = len(msgs)
                st.update(rec, p_leg=p_leg, a_leg=a_leg, rot_m=rot_m, cm=[row[:n] for row in st["confusion"][:n]])
                c = self.scope_constellation((tx, rx), vdiv=vdiv)
                cl.hold_point(0, 0)
                st["constellation"] = c
                out["runs"].append(st)
                print("%s: pilot leg %.3f V (a %.3f), decided %d/%d false %d missed %d, latency %.1f/%.1f/%.1f ns, cm %s" % (
                    name, p_leg, a_leg, st["decided"], st["refs"], st["false"], st["missed"], to_ns(st["lat_min"]),
                    to_ns(st["lat_mean"] or 0), to_ns(st["lat_max"]), st["cm"]), flush=True)
                cl.ctrl(loop_hold=1)
        finally:
            self.cl.ctrl(loop_hold=1, tx_dis=1)
            self.cl.dac(S.DAC1, VR_I=vr_i0, VR_Q=vr_q0, VC_OFF=S.V_MID)
            self.ioff(S.V_MID)
            self.quiet()
        path = save("pilot_%d" % mhz, out)
        self.b.record("verdict", test="link_pilot_schemes", ok=None, file=path,
                      text="B1, B2, A4: the loop locked on a weak pilot from the ladders' references, through the loop")
        return out


# ---- the LO drive: the as-laid simulation's tests D and E (sim/aslaid/REPORT.md finding 6) ----
APWR_DBM = {0: -4.0, 1: -1.0, 2: 2.0, 3: 5.0}       # the MAX2871's RFOUTA power per side; PLL_INIT's default is 1


class LoDrive(Schemes):
    def pll_apwr(self, which, mhz, apwr):
        """one synthesizer at mhz with RFOUTA at APWR code apwr: the six words built here (max2871_regs with its
        APWR changed) and sent through the driver's SPI, RFOUTB off as PLL_INIT leaves it"""
        import max2871_regs as MR
        keep = MR.APWR
        try:
            MR.APWR = apwr
            for w in MR.regs(float(mhz), f_pfd=25.0, rfb_en=False):
                self.cl.spi(which, w)
        finally:
            MR.APWR = keep
        time.sleep(S.RELOCK_S)

    def sa_peak(self, mhz, span=200e3):
        f, p = self.rx_mon(mhz, span=span)
        return p

    def tx_drive(self, mhzs=(5000, 5200, 5800), dsa_over=6.0):
        """test D: the TX synthesizer's APWR stepped, the carrier (point (1, 0)), its +-25 MHz sidebands and the nulled
        carrier (0, 0) read at RX MON through the loopback, the DSA fixed; the RX synthesizer parked 200 MHz below so its
        own leak is out of the analyser's span"""
        out = []
        try:
            for mhz in mhzs:
                if not self.alive():
                    break
                self.cl.ctrl(tx_dis=1, loop_hold=1)
                self.cl.pll_tune(1, float(mhz - 200))
                dsa = min(31.75, self.dsa_min(mhz) + dsa_over)
                self.cl.dsa(dsa)
                rows = []
                for code in (1, 0, 2, 3, 1):
                    self.pll_apwr(0, mhz, code)
                    lock = self.cl.pll_locked()
                    self.cl.hold_point(1, 0)
                    self.cl.ctrl(tx_dis=0)
                    time.sleep(0.05)
                    car = self.sa_peak(mhz)
                    sb = {d: self.sa_peak(mhz + d) for d in (-25, 25)}
                    self.cl.hold_point(0, 0)
                    time.sleep(0.05)
                    null = self.sa_peak(mhz)
                    self.cl.ctrl(tx_dis=1)
                    off = self.sa_peak(mhz)
                    rows.append({"apwr": code, "apwr_dbm": APWR_DBM[code], "lock": lock, "carrier": car,
                                 "sb_m25": sb[-25], "sb_p25": sb[25], "null": null, "tx_dis": off})
                    print(mhz, "APWR %+.0f" % APWR_DBM[code], lock, "carrier %.1f  sidebands %.1f / %.1f  null %.1f  muted %.1f"
                          % (car, sb[-25], sb[25], null, off), flush=True)
                out.append({"mhz": mhz, "dsa": dsa, "rows": rows})
        finally:
            self.cl.ctrl(tx_dis=1)
            self.cl.pll_tune(0, 5800.0)
            self.quiet()
        return out

    def rx_drive(self, mhzs=(5000, 5200, 5800), dvc=-0.08):
        """test E: the RX synthesizer's APWR stepped, the loop held with VC set dvc off the lock for a beat of a few
        tens of kHz, the TX at (1, 0); the I and Q arms' beat amplitude by the scope's sine fits, the DSA set once for
        about 0.3 V p-p at the default drive"""
        import numpy as np
        out = []
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in mhzs:
                if not self.alive():
                    break
                self.cl.ctrl(tx_dis=1, loop_hold=1)
                self.tune(mhz)
                self.set_vc(VC_LOCK + dvc)
                self.tx(True)
                floor = self.dsa_min(mhz)
                d = 31.75
                while d > floor:
                    self.cl.dsa(d)
                    pp = self.iq_meas()[2]["PKPK"] or 0
                    if pp >= 0.3:
                        break
                    d = max(floor, d - 2.0)
                self.cl.dsa(d)
                rows = []
                for code in (1, 0, 2, 3, 1):
                    self.pll_apwr(1, mhz, code)
                    lock = self.cl.pll_locked()
                    self.set_vc(VC_LOCK + dvc)
                    fit = self.beat_fit()
                    rows.append({"apwr": code, "apwr_dbm": APWR_DBM[code], "lock": lock, "vc": self.cl.adc("VC"), **fit})
                    print(mhz, "RX APWR %+.0f" % APWR_DBM[code], lock, "beat %.0f Hz  I %.4f  Q %.4f V"
                          % (fit.get("beat_hz") or 0, fit.get("amp_i") or 0, fit.get("amp_q") or 0), flush=True)
                out.append({"mhz": mhz, "dsa": d, "rows": rows})
                self.tx(False)
        finally:
            self.cl.ctrl(tx_dis=1)
            self.cl.pll_tune(1, 5800.0)
            self.quiet()
        return out

    def beat_fit(self, n_periods=8):
        """one record of I MON and Q MON, each fitted with a sine at the beat (overnight.py iq's method)"""
        import numpy as np
        m = self.iq_meas()
        fb = m[2]["FREQ"] or m[3]["FREQ"]
        if not fb or fb < 200:
            return {"beat_hz": fb, "amp_i": None, "amp_q": None}
        tdiv = min(1e-3, max(1e-6, n_periods / fb / 10))
        self.s.timebase(scale=tdiv)
        self.s.single()
        time.sleep(max(0.3, 12 * tdiv))
        t, vi, _ = self.s.waveform(2)
        _, vq, _ = self.s.waveform(3, preamble=False)
        self.s.run()
        self.scope_iq(vdiv=0.1)
        t, vi, vq = np.asarray(t), np.asarray(vi), np.asarray(vq)
        res = {"beat_hz": fb}
        for name, v in (("i", vi), ("q", vq)):
            best = None
            for f in np.linspace(0.97 * fb, 1.03 * fb, 61):
                A = np.c_[np.sin(2 * np.pi * f * t), np.cos(2 * np.pi * f * t), np.ones_like(t)]
                c, r, *_ = np.linalg.lstsq(A, v, rcond=None)
                e = float(np.sum((A @ c - v) ** 2))
                if best is None or e < best[0]:
                    best = (e, f, c)
            res["amp_" + name] = float(np.hypot(best[2][0], best[2][1]))
            res["beat_hz"] = float(best[1])
        return res

    def apwr_check(self, mhz=5200, n=4):
        """do the APWR writes reach the parts?  TX muted, the loop held: per synthesizer and APWR code, the board's
        supply current (the E3646A) and the level at RX MON at the carrier (both LOs' own leak)"""
        out = []
        try:
            self.cl.ctrl(tx_dis=1, loop_hold=1)
            self.cl.dsa(0.0)
            self.tune(mhz)
            for which in (0, 1):
                for code in (1, 0, 1, 2, 3, 1):
                    self.pll_apwr(which, mhz, code)
                    time.sleep(0.3)
                    amps = [self.b.psu_read("apwr check")["amps"] for _ in range(n)]
                    leak = self.sa_peak(mhz)
                    row = {"which": "tx" if which == 0 else "rx", "apwr": code, "apwr_dbm": APWR_DBM[code],
                           "amps": sum(amps) / len(amps), "rx_mon_leak": leak, "lock": self.cl.pll_locked()}
                    out.append(row)
                    print("APWR check", row["which"], "%+.0f dBm" % APWR_DBM[code], "%.4f A" % row["amps"],
                          "leak %.1f dBm" % leak, flush=True)
                self.pll_apwr(which, mhz, 1)
        finally:
            self.cl.ctrl(tx_dis=1)
            self.quiet()
        return out

    def lodrive(self, mhzs=(5000, 5200, 5800)):
        d = self.tx_drive(mhzs)
        e = self.rx_drive(mhzs)
        out = {"tx_drive": d, "rx_drive": e}
        path = save("lodrive", out)
        self.b.record("verdict", test="link_lo_drive", ok=None, file=path,
                      text="tests D and E: the TX level and the I/Q beat against each synthesizer's RFOUTA power (APWR)")
        return out


# ---- the turnaround (the reply overlay, gateware a173ec9: turnaround.v; BRINGUP stage 3.4g) ----
class Mirrored(Scheme):
    """one Scheme for the driver's turnaround calls (scheme(), loopback_turnaround(), ring_run(), the fast path's
    tables): its TX points are the transmitter's, and its receiver frame is the inverted lock's, the TX point
    mirrored (I -> -I, rev A's inverted I arm: REVB 9) and turned by -rot, as rx_schemes' rx half"""

    def __init__(self, tx, rot):
        super().__init__(tx.name, tx.text + " (I mirrored, frame %+d)" % rot, tx.idle, tx.msgs, [], rot_deg=-rot,
                         pilot=tx.pilot, t=tx.t, t2=tx.t2)
        self.mask, self.use = tx.mask, tx.use

    def rx_point(self, iq):
        i, q = iq
        return Scheme.rx_point(self, (-i, q))


def turn_pairs(rot):
    """A3r and A2r from rx_schemes, and A1q2: the BPSK flip and the null as two messages on QP / QN (A1q has one
    message, and an answer must differ from its stimulus to be seen), the 1-bit floor on the fast bank's windows"""
    out = {s[0].name: s for s in rx_schemes(rot, True)}
    tx = Scheme("A1q2", "1 bit: the flip or the null, QP / QN", (1, 0), [(-1, 0), (0, 0)], [CMP_QP, CMP_QN],
                rot_deg=rot, use=WIN)
    m = lambda p: (-p[0], p[1])                                          # noqa: E731
    rx = Scheme("A1q2", tx.text + " (I mirrored)", m(tx.idle), [m(x) for x in tx.msgs], [CMP_QP, CMP_QN],
                rot_deg=-rot, use=WIN)
    out["A1q2"] = (tx, rx)
    return out


def trim_capture(cap, before=24, after=240):
    """the capture's lists around its trigger (the stimulus's TX event)"""
    t0 = cap["trigger_sample"]
    lo, hi = max(0, t0 - before), t0 + after
    out = {}
    for k, v in cap.items():
        if isinstance(v, list) and len(v) > hi:
            out[k] = v[lo:hi]
        elif not isinstance(v, list):
            out[k] = v
    out["trim_lo"] = lo
    return out


class Turn(Schemes):
    def lc(self):
        """a CostasLink on this side over the netbus's plain bus: the driver's turnaround calls take Scheme objects,
        which the network's calls pass only by name"""
        if not hasattr(self, "_lc"):
            from netbus import NetBus
            self._lc = CostasLink(NetBus(self.b.cfg["pynq_host"], self.b.cfg.get("pynq_port", 5800)))
        return self._lc

    def turn(self, mhz=5000, dsa=None, frac=0.4, count=5000, period=1000, delay=16, names=("A3r", "A2r", "A1q2"),
             delays=(16, 8, 4), mask=0x1E):
        lc = self.lc()
        out = {"mhz": mhz, "frac": frac, "delay": delay, "delays": list(delays), "mask": mask, "count": count, "period": period,
               "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            v, tr = self.null_fast_i()
            out["i_off_f"] = v
            cen = self.centres()
            out["centres"] = {w: cen[w]["v0"] for w in ("QP", "QN", "IP", "IN")}
            dsa = dsa if dsa is not None else self.regulated_dsa(mhz)
            out["dsa"] = dsa
            ioff = v if v is not None else S.V_MID
            if self.acquire_lock(mhz, dsa, ioff=ioff) is None:
                out["error"] = "no lock"
                return out
            for name in names:
                rot, ok, fi = self.frame(cen)
                if not ok:
                    if self.acquire_lock(mhz, dsa, ioff=ioff) is None:
                        out.setdefault("errors", []).append(name + ": no lock")
                        continue
                    rot, ok, fi = self.frame(cen)
                a_leg = abs(fi["dq"])
                th = self.thresholds(cen, a_leg, t=frac)
                pair = turn_pairs(rot)[name]
                s = Mirrored(pair[0], rot)
                r = {"scheme": name, "rot_deg": rot, "a_leg": a_leg, "thresholds": th, "frame": fi}
                base = self.run_scheme(pair, count=count, delay=delay)
                r["base"] = {k: base[k] for k in ("events", "decided", "refs", "false", "missed", "lat_min", "lat_max", "lat_mean")}
                r["base"]["cm_diag"] = [base["confusion"][k][k] for k in range(s.n)]
                # the counter and the captures watch the four windows only: CMP_I sits on its threshold at the inverted
                # lock and chatters (its edges were counted as arrivals in the first pass)
                combos = [("sync", d, False) for d in delays] + [("fast", delay, False)]
                if s.n <= 2:                                    # first-edge decisions work for the 1-bit schemes
                    combos += [("sync", 4, True), ("fast", 4, True)]
                for path, dl, fe in combos:
                    key = (path if path == "fast" else "sync_d%d" % dl) + ("_fe" if fe else "")
                    st = lc.loopback_turnaround(s, path=path, count=count, period=period, first_edge=fe, delay=dl,
                                                mask=mask)
                    r[key] = {k: st.get(k) for k in ("n", "miss", "min", "max", "mean", "min_ns", "mean_ns", "max_ns",
                                                     "arrivals", "span")}
                    r[key]["rx"] = {k: st["rx"][k] for k in ("events", "decided", "false", "missed", "refs")}
                    r[key]["reply"] = st["reply"]
                    cap = lc.turnaround_capture(s, path=path, first_edge=fe, delay=dl, mask=mask)
                    r[key + "_cap"] = {k: x for k, x in cap.items() if k != "capture"}
                    r[key + "_cap_raw"] = trim_capture(cap["capture"])
                    self.cl.hold_point(1, 0)
                    print("  %s %s: n %s miss %s, %.2f / %.2f / %.2f ns; capture %.2f ns (FPGA pad to pad %.2f, loop %.2f)" % (
                        name, key, r[key]["n"], r[key]["miss"], r[key]["min_ns"] or 0, r[key]["mean_ns"] or 0,
                        r[key]["max_ns"] or 0, r[key + "_cap"].get("turnaround_ns") or 0, r[key + "_cap"].get("fpga_ns") or 0,
                        r[key + "_cap"].get("loop_ns") or 0), flush=True)
                order = [0, 1, 3, 2] if s.n == 4 else None          # Gray order: each hop moves one arm
                rg = lc.ring_run(s, order=order, clocks=2000, mask=mask)
                r["ring"] = {k: rg.get(k) for k in ("hops", "span", "turnaround", "turnaround_ns", "arrivals", "n", "miss")}
                self.cl.hold_point(1, 0)
                rot2, ok2, _ = self.frame(cen, a_leg)
                r["frame_after"] = {"rot": rot2, "ok": ok2}
                out["runs"].append(r)
                print("%s %d MHz: base %d/%d %.1f ns; ring %s hops, %.2f ns a hop; frame after %+d %s" % (
                    name, mhz, base["decided"], base["refs"], to_ns(base["lat_mean"] or 0), r["ring"]["hops"],
                    r["ring"]["turnaround_ns"] or 0, rot2, ok2), flush=True)
        finally:
            try:
                lc.reply_off()
                lc.fast_off()
                lc.wr("RT_CFG", 0)
            except Exception as e:                                       # noqa: BLE001
                out.setdefault("errors", []).append("cleanup: %s" % e)
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("turn_%d" % mhz, out)
        self.b.record("verdict", test="link_turnaround", ok=None, file=path,
                      text="the turnaround on the reply overlay (sync reply, fast path, ring), A3r / A2r / A1q2 at the inverted lock")
        return out

    def turn_sweep(self, mhz=5000, dsas_rel=(-6, -3, 0, 3, 6, 9), fracs=(0.2, 0.3, 0.4, 0.55, 0.7), names=("A3r", "A1q2"),
                   reps=3, clocks=2000, mask=0x1E):
        """the fast path's ring hop against the received level (the DSA about the regulated setting: the comparators'
        overdrive) and the windows' place on the edge (frac of the leg): a hop that moves with frac is the edges' rise
        (the arm, the header's RCs, the ladder), one that moves with the level at a fixed frac is the comparators'
        dispersion; what moves with neither is fixed delay (Jason, 2026-10-29: which latency knobs pay)"""
        lc = self.lc()
        out = {"mhz": mhz, "fracs": list(fracs), "mask": mask, "clocks": clocks, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            v, tr = self.null_fast_i()
            out["i_off_f"] = v
            cen = self.centres()
            out["centres"] = {w: cen[w]["v0"] for w in ("QP", "QN", "IP", "IN")}
            reg = self.regulated_dsa(mhz)
            out["regulated_dsa"] = reg
            ioff = v if v is not None else S.V_MID
            for dd in dsas_rel:
                if not self.alive():
                    break
                dsa = min(31.75, max(self.dsa_min(mhz), reg + dd))
                if self.acquire_lock(mhz, dsa, ioff=ioff) is None:
                    out["runs"].append({"dsa": dsa, "error": "no lock"})
                    print("DSA", dsa, "no lock", flush=True)
                    continue
                for name in names:
                    rot, ok, fi = self.frame(cen)
                    if not ok:
                        if self.acquire_lock(mhz, dsa, ioff=ioff) is None:
                            out["runs"].append({"dsa": dsa, "scheme": name, "error": "no lock"})
                            continue
                        rot, ok, fi = self.frame(cen)
                    a_leg = abs(fi["dq"])
                    pair = turn_pairs(rot)[name]
                    sch = Mirrored(pair[0], rot)
                    order = [0, 1, 3, 2] if sch.n == 4 else None
                    for t in fracs:
                        th = self.thresholds(cen, a_leg, t=t)
                        hops = []
                        for _ in range(reps):
                            rg = lc.ring_run(sch, order=order, clocks=clocks, mask=mask)
                            hops.append({k: rg.get(k) for k in ("hops", "span", "turnaround_ns", "n", "miss")})
                            self.cl.hold_point(1, 0)
                        good = [h["turnaround_ns"] for h in hops if h["turnaround_ns"] and (h["hops"] or 0) > 20]
                        r = {"dsa": dsa, "dsa_rel": dd, "scheme": name, "rot_deg": rot, "a_leg": a_leg, "frac": t,
                             "thresholds": th, "rings": hops,
                             "hop_ns": (sum(good) / len(good)) if good else None,
                             "hop_ns_spread": (max(good) - min(good)) if len(good) > 1 else None}
                        out["runs"].append(r)
                        print("%s DSA %.2f (%+d) leg %.3f V frac %.2f: hop %s ns over %s" % (
                            name, dsa, dd, a_leg, t, ("%.2f" % r["hop_ns"]) if r["hop_ns"] else "-",
                            [h["hops"] for h in hops]), flush=True)
                    rot2, ok2, _ = self.frame(cen, a_leg)
                    if not ok2:
                        print("  the frame moved after", name, rot2, flush=True)
        finally:
            try:
                lc.reply_off()
                lc.fast_off()
                lc.wr("RT_CFG", 0)
            except Exception as e:                                       # noqa: BLE001
                out.setdefault("errors", []).append("cleanup: %s" % e)
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("turnsweep_%d" % mhz, out)
        self.b.record("verdict", test="link_turn_sweep", ok=None, file=path,
                      text="the fast path's ring hop against the received level and the windows' place on the edge")
        return out

    def scope_turn(self, mhz=5200, dsa=10, frac=0.4, name="A2r", path="sync", first_edge=True, delay=4,
                   tdiv=200e-9, vdiv=0.05):
        """I MON and Q MON on the scope while the board answers each of its own stimuli (single-board loopback),
        and one FPGA capture of the same: the scope's screen saved beside the data"""
        import numpy as np
        lc = self.lc()
        out = {"mhz": mhz, "dsa": dsa, "scheme": name, "path": path, "first_edge": first_edge, "delay": delay}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            v, _ = self.null_fast_i()
            cen = self.centres()
            ioff = v if v is not None else S.V_MID
            if self.acquire_lock(mhz, dsa, ioff=ioff) is None:
                out["error"] = "no lock"
                return out
            rot, ok, fi = self.frame(cen)
            a_leg = abs(fi["dq"])
            self.thresholds(cen, a_leg, t=frac)
            s = Mirrored(turn_pairs(rot)[name][0], rot)
            out.update(rot_deg=rot, a_leg=a_leg)
            cap = lc.turnaround_capture(s, path=path, first_edge=first_edge, delay=delay, mask=0x1E, reply_width=60, width=30)
            out["cap"] = {k: x for k, x in cap.items() if k != "capture"}
            out["cap_raw"] = trim_capture(cap["capture"], before=24, after=600)
            lc._turnaround_setup(s, path, None, first_edge, delay, 30, 60, 1)
            lc.events(period=2000, width=30, count=0)
            lc.tx_go()
            sc = self.s
            for ch in (2, 3):
                sc.channel(ch, on=True, scale=vdiv, offset=-1.63, coupling="DC", impedance="1M")
            sc.timebase(scale=tdiv)
            i0 = self.cl.adc("I")
            sc.trigger(source=2, level=i0, slope="falling" if fi["dq"] > 0 else "rising", mode="normal")
            time.sleep(0.5)
            try:
                sc.single(timeout=3.0)
            except TimeoutError:
                sc.trigger(source=2, level=i0, slope="rising" if fi["dq"] > 0 else "falling", mode="normal")
                sc.single(timeout=3.0)
            t2, v2, _ = sc.waveform(2)
            t3, v3, _ = sc.waveform(3)
            k = max(1, len(v2) // 4000)
            out["scope"] = {"t": list(np.asarray(t2)[::k]), "i": list(np.asarray(v2)[::k]), "q": list(np.asarray(v3)[::k])}
            os.makedirs(OUT, exist_ok=True)
            shot = os.path.join(OUT, "scope_turn_%d_%s.png" % (mhz, O.stamp()))
            sc.screenshot(shot)
            out["screenshot"] = os.path.relpath(shot, HERE)
            sc.run()
        finally:
            try:
                lc.tx_stop()
                lc.reply_off()
                lc.fast_off()
                lc.wr("RT_CFG", 0)
            except Exception as e:                                       # noqa: BLE001
                out["cleanup_error"] = str(e)
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path_ = save("scope_turn_%d" % mhz, out)
        self.b.record("verdict", test="link_scope_turn", ok=None, file=path_,
                      text="I MON / Q MON on the scope: the stimulus and the board's answer (%s, %s path)" % (name, path))
        return out


def to_ns(samples):
    return samples * 1.25


def fsk_order(c):
    """the window comparators' rising edges in the capture, in time order: the sequence of quadrants the phasor visits
    (QP, IN, QN, IP for one sense, the reverse for the other)"""
    names = ("CMP_QP", "CMP_IN", "CMP_QN", "CMP_IP")
    ev = []
    for n in names:
        x = c[n]
        for k in range(1, len(x)):
            if x[k] and not x[k - 1]:
                ev.append((k, n))
    ev.sort()
    seq = [n for _, n in ev]
    nxt = {a: b for a, b in zip(names, names[1:] + names[:1])}
    fwd = sum(1 for a, b in zip(seq, seq[1:]) if nxt[a] == b)
    rev = sum(1 for a, b in zip(seq, seq[1:]) if nxt[b] == a)
    return {"edges": len(seq), "steps_QP_IN_QN_IP": fwd, "steps_reverse": rev, "first": seq[:12]}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("section", choices=["force", "lockcmp", "schemes", "tune_a3", "pilot", "lodrive", "apwr_check", "turn", "scope_turn", "turnsweep"])
    ap.add_argument("--dsa", type=float)
    ap.add_argument("--mhz", type=int, nargs="*")
    a = ap.parse_args(argv)
    L = LoDrive() if a.section in ("lodrive", "apwr_check") else (Turn() if a.section in ("turn", "scope_turn", "turnsweep") else Schemes())
    if a.section == "scope_turn":
        L.scope_turn(*(a.mhz or [5200]), dsa=a.dsa if a.dsa is not None else 10)
        return
    if a.section == "turnsweep":
        for m in (a.mhz or [5000]):
            L.turn_sweep(m)
        return
    if a.section == "turn":
        for m in (a.mhz or [5000]):
            L.turn(m, dsa=a.dsa)
        return
    if a.section == "apwr_check":
        rows = L.apwr_check(*(a.mhz or [5200]))
        path = save("apwr_check", rows)
        L.b.record("verdict", test="link_apwr_check", ok=None, file=path, text="the APWR writes against the supply current and the LOs' leak")
    elif a.section == "lodrive":
        L.lodrive(tuple(a.mhz) if a.mhz else (5000, 5200, 5800))
    elif a.section == "pilot":
        for m in (a.mhz or [5000]):
            L.pilot_schemes(m, rho=0.3, frac=0.35, lock_db=2.0, vdiv=0.1)
    elif a.section == "tune_a3":
        for m in (a.mhz or [5000, 5200]):
            L.tune_a3(m)
    elif a.section == "schemes":
        for m in (a.mhz or [5000]):
            L.schemes(m)
    elif a.section == "force":
        L.force(*(a.mhz or [5000]))
    elif a.section == "lockcmp":
        L.lockcmp(tuple(a.mhz) if a.mhz else (5000, 5100, 5200))


if __name__ == "__main__":
    main(sys.argv[1:])
