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

    def scope_constellation(self, s, period=2500, width=500, tdiv=20e-6):
        """long events (5 us: the MON taps' 1 k into the cable is ~0.1 us) cycling through the messages, both MONs"""
        import numpy as np
        cl, sc = self.cl, self.s
        s = s[0] if isinstance(s, tuple) else s
        cl.tx_points(s.tx_idle(), [point_code(i, q) for i, q in s.msgs])
        cl.events(period=period, width=width, count=0, n=s.n)
        cl.tx_go()
        for ch in (2, 3):
            sc.channel(ch, on=True, scale=0.05, offset=-1.63, coupling="DC", impedance="1M")
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
    ap.add_argument("section", choices=["force", "lockcmp", "schemes"])
    ap.add_argument("--mhz", type=int, nargs="*")
    a = ap.parse_args(argv)
    L = Schemes()
    if a.section == "schemes":
        for m in (a.mhz or [5000]):
            L.schemes(m)
    elif a.section == "force":
        L.force(*(a.mhz or [5000]))
    elif a.section == "lockcmp":
        L.lockcmp(tuple(a.mhz) if a.mhz else (5000, 5100, 5200))


if __name__ == "__main__":
    main(sys.argv[1:])
