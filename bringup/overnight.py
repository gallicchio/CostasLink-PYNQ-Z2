#!/usr/bin/env python3
"""overnight.py: rev A board A's unattended measurements, the night of 2026-10-29 (Jason: "plan a series of
measurements all night").  The bench as Jason left it at 16:50: TX ANT -> 10 cm RG-316 -> two 20 dB pads -> RX ANT;
the DSA875 on RX MON (J102); the SDS2104X Plus with ch1 REF OUT (J108), ch2 I MON (J104), ch3 Q MON (J105), ch4 VC MON
(J107), all 1 Mohm; the SDG1032X on REF IN, unused (JP201 on TCXO); 50 ohm on TX MON's pigtail.

    python3 bringup/overnight.py map [--step 50]        A: the receive chain over 3-6 GHz (RX MON, LOG_Q, the I/Q beat)
    python3 bringup/overnight.py iq [--step 100]        C: the demodulator's I/Q balance and quadrature, the arms' offsets
    python3 bringup/overnight.py loop [--mhz 3500 ...]  D: close the Costas loop
    python3 bringup/overnight.py drift --hours 8        E: the TCXO, VCXO, temperature and current every 10 minutes

Every section turns the transmitter on only while it measures, leaves it muted (TX_DIS high), the DSA at 31.75 dB, the
synthesizers at 5.8 GHz and the loop held; the generator stays off; the analyser is left live (bench.py).  Each writes
its rows to bringup/data/board_A/overnight/<section>_<time>.json and one verdict line to the board's log.

The DSA never goes below dsa_min(f): the demodulator kept at 0 dBm or less (its absolute maximum is +15 dBm), from the
TX ANT levels (stage2.tx_spurs) less the pads, and the chain's gain at DSA 0 measured at 16:01 (stage3.rx_mon) plus
3 dB.  VR_I / VR_Q are not written here (the carrier null stays as stage2.null left it).
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench as B                                   # noqa: E402
import stages as S                                  # noqa: E402

PAD_DB = 40.2                       # the 10 cm lead and two 20 dB pads at 5.8 GHz (0.5 + 39.7)
OUT = os.path.join(HERE, "data", "board_A", "overnight")
DEMOD_MAX_DBM = 0.0                 # what the DSA floor keeps the ADL5380's RF input under


def stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


def interp(table, x):
    """linear interpolation in {x: y}, clamped at the ends"""
    xs = sorted(table)
    if x <= xs[0]:
        return table[xs[0]]
    if x >= xs[-1]:
        return table[xs[-1]]
    for a, b in zip(xs, xs[1:]):
        if a <= x <= b:
            return table[a] + (table[b] - table[a]) * (x - a) / (b - a)


class Night:
    def __init__(self, stage="night"):
        self.b = B.Bench("A", stage)
        self.cl, self.s = self.b.cl, self.b.scope
        log = [json.loads(l) for l in open(self.b.log.path)]
        sw = [e for e in log if e.get("test") == "tx_spurs"][-1]
        self.tx_dbm = {r["mhz"]: r["carrier"] for r in sw["sweep"]}          # TX ANT, (1, 0), 250 MHz steps
        rm = [e for e in log if e.get("test") == "rx_mon_dsa"][-1]
        self.chain0 = {r["mhz"]: r["chain_db"] for r in rm["sweep"] if "chain_db" in r}   # RX ANT -> CP101 at DSA 0

    # ---- safety and state ----
    def dsa_min(self, mhz):
        rx_ant = interp(self.tx_dbm, mhz) - PAD_DB
        need = rx_ant + interp(self.chain0, mhz) + 3.0 - DEMOD_MAX_DBM
        return min(31.75, max(0.0, math.ceil(need * 4) / 4))

    def alive(self):
        """the supply on and the PYNQ answering: otherwise stop the night (the watchdog may have cut power)"""
        try:
            st = self.b.psu.setting(1)
            return bool(st["output"]) and bool(self.cl.bus.ping())
        except Exception:                                            # noqa: BLE001
            return False

    def quiet(self):
        """the transmitter muted, the DSA at its top, the loop held, both synthesizers at 5.8 GHz"""
        try:
            self.cl.ctrl(tx_dis=1, loop_hold=1)
            self.cl.safe()
            self.cl.dsa(31.75)
            self.cl.pll_tune(0, 5800.0)
            self.cl.pll_tune(1, 5800.0)
            time.sleep(S.RELOCK_S)
        except Exception as e:                                       # noqa: BLE001
            self.b.record("note", text="quiet() failed: %s" % e)

    def tune(self, mhz):
        self.cl.pll_tune(0, float(mhz))
        self.cl.pll_tune(1, float(mhz))
        time.sleep(S.RELOCK_S)
        return self.cl.pll_locked()

    def tx(self, on):
        if on:
            self.cl.hold_point(1, 0)
            self.cl.ctrl(tx_dis=0)
        else:
            self.cl.ctrl(tx_dis=1)
        time.sleep(0.05)

    # ---- instruments ----
    def scope_iq(self, vdiv=0.2, tdiv=10e-6):
        s = self.s
        s.channel(1, on=True, scale=1.0, offset=-1.65, coupling="DC", impedance="1M")
        for ch in (2, 3):
            s.channel(ch, on=True, scale=vdiv, offset=-1.65, coupling="DC", impedance="1M")
        s.channel(4, on=True, scale=0.5, offset=-1.65, coupling="DC", impedance="1M")
        s.timebase(scale=tdiv)
        s.trigger(source=2, level=1.65, slope="rising", mode="auto")

    def iq_meas(self):
        s = self.s
        time.sleep(0.15)
        return {ch: {k: s.pava(k, ch) for k in ("PKPK", "MEAN", "FREQ")} for ch in (2, 3)}

    def rx_mon(self, mhz, span=200e3):
        b = self.b
        b.sa_setup(mhz * 1e6, span, rbw=1e3, ref=0.0, att=10)
        b.sa.single()
        return b.sa.peak()

    # ---- A: the receive chain over frequency ----
    def map(self, step=50, dsas=(31.75, 28, 24, 20, 16, 12, 8, 4, 2, 0)):
        rows = []
        self.scope_iq()
        try:
            for mhz in range(3000, 6001, step):
                if not self.alive():
                    break
                lock = self.tune(mhz)
                floor = self.dsa_min(mhz)
                self.cl.dsa(31.75)
                self.tx(False)
                dis = {"rx_mon": self.rx_mon(mhz)[1], "det": self.cl.detectors()["volts"], "iq": self.iq_meas()}
                self.tx(True)
                pts = []
                for d in [x for x in dsas if x >= floor] or [floor]:
                    self.cl.dsa(d)
                    time.sleep(0.02)
                    f, p = self.rx_mon(mhz)
                    det = self.cl.detectors()["volts"]
                    pts.append({"dsa": d, "rx_mon": p, "log_q": det["LOG_Q"], "peak_q": det["PEAK_Q"], "iq": self.iq_meas()})
                self.tx(False)
                row = {"mhz": mhz, "lock": lock, "dsa_min": floor, "tx_ant_dbm": interp(self.tx_dbm, mhz),
                       "tx_dis": dis, "points": pts}
                rows.append(row)
                print(mhz, lock, "floor %.2f" % floor, "RX MON", ["%.1f" % q["rx_mon"] for q in pts],
                      "I pp", ["%.2f" % (q["iq"][2]["PKPK"] or 0) for q in pts], flush=True)
        finally:
            self.quiet()
        path = save("map", rows)
        self.b.record("verdict", test="night_map", ok=None, file=path, n=len(rows),
                      text="the receive chain over 3-6 GHz: RX MON, LOG_Q, PEAK_Q and the I/Q beat (scope) per DSA, TX on and off")
        return rows

    # ---- C: I/Q balance and quadrature ----
    def iq(self, step=100, target_pp=0.4):
        """at each frequency, the DSA set for an I beat of about target_pp (unclipped), one record of ch2 and ch3,
        each fitted with a sine at the beat: the amplitude ratio Q / I and the phase of Q against I (90 degrees ideal)"""
        import numpy as np
        rows = []
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in range(3000, 6001, step):
                if not self.alive():
                    break
                lock = self.tune(mhz)
                floor = self.dsa_min(mhz)
                self.tx(False)
                self.cl.dsa(31.75)
                off = self.iq_meas()                                  # the arms' DC with the carrier muted
                adc_off = {k: float(np.mean([self.cl.adc(k) for _ in range(8)])) for k in ("I", "Q")}
                self.tx(True)
                d = 31.75
                pp = 0
                while d >= floor:                                     # walk down until the beat is big enough
                    self.cl.dsa(d)
                    pp = self.iq_meas()[2]["PKPK"] or 0
                    if pp >= target_pp:
                        break
                    d -= 2.0
                m = self.iq_meas()
                fb = m[2]["FREQ"] or m[3]["FREQ"]
                rec = None
                if fb and fb > 1e3:
                    tdiv = min(1e-3, max(1e-6, 4.0 / fb / 10))       # about four beat periods on screen
                    self.s.timebase(scale=tdiv)
                    self.s.single()
                    t, vi, _ = self.s.waveform(2)
                    _, vq, _ = self.s.waveform(3, preamble=False)
                    self.s.run()
                    t, vi, vq = np.asarray(t), np.asarray(vi), np.asarray(vq)
                    w = 2 * np.pi * fb
                    A = np.column_stack([np.cos(w * t), np.sin(w * t), np.ones_like(t)])
                    # refine the beat frequency on I by a small search around the counter's value
                    best = None
                    for fr in np.linspace(fb * 0.98, fb * 1.02, 41):
                        A = np.column_stack([np.cos(2 * np.pi * fr * t), np.sin(2 * np.pi * fr * t), np.ones_like(t)])
                        ci, ri, *_ = np.linalg.lstsq(A, vi, rcond=None)
                        r = float(np.sum((A @ ci - vi) ** 2))
                        if best is None or r < best[0]:
                            best = (r, fr, ci)
                    _, fr, ci = best
                    A = np.column_stack([np.cos(2 * np.pi * fr * t), np.sin(2 * np.pi * fr * t), np.ones_like(t)])
                    cq, *_ = np.linalg.lstsq(A, vq, rcond=None)
                    ai, pi_ = math.hypot(ci[0], ci[1]), math.atan2(-ci[1], ci[0])
                    aq, pq = math.hypot(cq[0], cq[1]), math.atan2(-cq[1], cq[0])
                    dphi = (math.degrees(pq - pi_) + 180) % 360 - 180
                    resid_i = float(np.std(vi - A @ ci))
                    rec = {"beat_hz": float(fr), "amp_i": ai, "amp_q": aq, "ratio_db": 20 * math.log10(aq / ai) if ai else None,
                           "phase_q_minus_i_deg": dphi, "dc_i": float(ci[2]), "dc_q": float(cq[2]), "resid_i_v": resid_i,
                           "tdiv": tdiv, "n": int(len(t))}
                    self.scope_iq(vdiv=0.1)
                self.tx(False)
                row = {"mhz": mhz, "lock": lock, "dsa": d, "pp_i": pp, "muted": off, "adc_muted": adc_off, "fit": rec}
                rows.append(row)
                print(mhz, "dsa", d, "fit", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in (rec or {}).items()}, flush=True)
        finally:
            self.quiet()
        path = save("iq", rows)
        self.b.record("verdict", test="night_iq", ok=None, file=path, n=len(rows),
                      text="I/Q amplitude ratio and phase from sine fits to the scope's I MON / Q MON beat; the arms' muted DC")
        return rows

    # ---- D: the loop ----
    def beat(self):
        """the I arm's beat on the scope: the channel scaled to the signal and the trigger at its mean first (a weak
        beat at 40 mV p-p is invisible at 200 mV/div), then the timebase walked down for slow beats.  (Hz, p-p V) or
        (None, p-p) for no beat"""
        s = self.s
        s.timebase(scale=10e-6)
        time.sleep(0.25)
        pp, mean = s.pava("PKPK", 2) or 0.05, s.pava("MEAN", 2) or 1.65
        s.channel(2, scale=max(0.005, min(0.5, pp / 5)), offset=-mean)
        s.channel(3, scale=max(0.005, min(0.5, pp / 5)), offset=-(s.pava("MEAN", 3) or mean))
        s.trigger(source=2, level=mean, slope="rising", mode="auto")
        for tdiv in (10e-6, 200e-6, 5e-3):
            s.timebase(scale=tdiv)
            time.sleep(max(0.3, 14 * tdiv))
            f = s.pava("FREQ", 2)
            if f and f > 2.0 / (10 * tdiv):
                return f, s.pava("PKPK", 2)
        return None, s.pava("PKPK", 2)

    def center(self, mhz):
        """the integrator re-centred where the trims reach (5.8 GHz, the TX muted), then both synthesizers back at mhz:
        the hold keeps U112A across the retune (measured 16:55)"""
        self.tune(5800)
        r = S.loop_center(self.b)
        self.tune(mhz)
        return r["ok"]

    def u112a(self):
        vc = self.cl.adc("VC")
        return vc, 3 * S.V_MID - vc - self.cl.dac_volts()["VC_OFF"]

    def loop(self, mhzs=(3500, 4000, 5000, 5800), settle_s=3.0, offsets_khz=(0, 2, 5, 10, 20, 40)):
        import numpy as np
        out = []
        self.scope_iq()
        try:
            for mhz in mhzs:
                if not self.alive():
                    break
                floor = self.dsa_min(mhz)
                rx_ant = interp(self.tx_dbm, mhz) - PAD_DB
                dsa = min(31.75, max(floor, math.ceil((rx_ant + interp(self.chain0, mhz) + 20) * 4) / 4))
                rec = {"mhz": mhz, "dsa": dsa, "scan": [], "tries": []}
                if not self.center(mhz):
                    rec["error"] = "the integrator could not be centred"
                    out.append(rec)
                    continue
                self.cl.dsa(dsa)
                self.tx(True)
                # the beat against VC_OFF, held: |kv (v - v0)|; v0 from a fit to the points either side of the minimum
                for v in np.arange(0.9, 2.41, 0.1):
                    self.cl.dac(S.DAC1, VC_OFF=float(v))
                    time.sleep(0.15)
                    f, pp = self.beat()
                    vc, u = self.u112a()
                    rec["scan"].append({"vc_off": float(v), "vc": vc, "u112a": u, "beat_hz": f, "pp": pp})
                good = [p for p in rec["scan"] if p["beat_hz"]]
                v0 = None
                if len(good) >= 4:
                    k = int(np.argmin([p["beat_hz"] for p in good]))
                    xs = [p["vc_off"] for p in good]
                    if 0 < k < len(good) - 1:
                        # the minimum inside the scan: the beat's sign flips there; the minimum itself goes with the
                        # side its neighbours' line passes nearer
                        fits = []
                        for kside in (-1, 1):
                            ys = [(-1 if (j < k or (j == k and kside < 0)) else 1) * p["beat_hz"] for j, p in enumerate(good)]
                            a, c = np.polyfit(xs, ys, 1)
                            fits.append((float(np.sum((np.polyval([a, c], xs) - ys) ** 2)), -c / a, a))
                        _, v0, kv = min(fits)
                    else:                                       # zero beat beyond the scan: extrapolate
                        a, c = np.polyfit(xs, [p["beat_hz"] for p in good], 1)
                        v0, kv = -c / a, a
                    rec.update(v0=float(v0), kv_hz_per_v=float(kv))
                print(mhz, "dsa", dsa, "v0", v0, "beats", [(round(p["vc_off"], 2), p["beat_hz"] and round(p["beat_hz"] / 1e3, 1)) for p in rec["scan"]], flush=True)
                if v0 is None or not 0.3 < v0 < 3.0:
                    self.tx(False)
                    out.append(rec)
                    continue
                for off_khz in offsets_khz:
                    for sgn in ((1,) if off_khz == 0 else (1, -1)):
                        v = v0 + sgn * off_khz * 1e3 / abs(rec["kv_hz_per_v"])
                        self.tx(False)
                        if not self.center(mhz):
                            break
                        self.cl.dsa(dsa)
                        self.cl.dac(S.DAC1, VC_OFF=float(v))
                        self.tx(True)
                        time.sleep(0.15)
                        b0, pp0 = self.beat()
                        self.cl.ctrl(loop_hold=0)                       # release, the transmitter on
                        t0 = time.time()
                        trace = []
                        while time.time() - t0 < settle_s:
                            vc, u = self.u112a()
                            trace.append((time.time() - t0, vc, u, self.cl.adc("I"), self.cl.adc("Q")))
                        b1, pp1 = self.beat()
                        tail = trace[-8:]
                        u_end = float(np.mean([x[2] for x in tail]))
                        locked = (b1 is None) and 0.3 < u_end < 3.0 and float(np.std([x[1] for x in tail])) < 0.02
                        shot = None
                        if locked:
                            os.makedirs(OUT, exist_ok=True)
                            self.s.timebase(scale=1e-3)
                            time.sleep(0.5)
                            shot = os.path.relpath(os.path.join(OUT, "loop_locked_%d_%s.png" % (mhz, stamp())), HERE)
                            self.s.screenshot(os.path.join(HERE, shot))
                        t = {"offset_khz": sgn * off_khz, "vc_off": float(v), "beat_before_hz": b0, "pp_before": pp0,
                             "beat_after_hz": b1, "pp_after": pp1, "locked": locked, "u112a_end": u_end,
                             "vc_end": float(np.mean([x[1] for x in tail])), "trace": trace, "shot": shot}
                        if locked:                                      # how steady, and the reference: REF OUT
                            hold = []
                            for _ in range(10):
                                time.sleep(0.5)
                                hold.append(self.u112a())
                            self.s.timebase(scale=10e-6)
                            self.s.trigger(source=1, level=1.65, slope="rising", mode="auto")
                            t["ref_out_hz"] = S._ref_hz(self.b, 1)[0]
                            self.s.run()
                            t["hold_10x0.5s"] = hold
                            t["still_locked"] = self.beat()[0] is None
                        rec["tries"].append(t)
                        print(mhz, "offset %+d kHz: beat %s -> %s, U112A %.2f, VC %.3f, locked %s" % (
                            sgn * off_khz, b0 and round(b0), b1 and round(b1), u_end, t["vc_end"], locked), flush=True)
                        self.cl.ctrl(loop_hold=1)
                self.tx(False)
                out.append(rec)
        finally:
            self.cl.ctrl(loop_hold=1)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("loop", out)
        self.b.record("verdict", test="night_loop", ok=any(t["locked"] for o in out for t in o["tries"]), file=path,
                      text="the Costas loop released (TX on) from held offsets of 0-40 kHz from zero beat, per frequency")
        return out

    # ---- D2: acquisition map, lock tests ----
    def lock_state(self):
        """'locked' (VC holds through a +-0.02 V VC_OFF step: the integrator takes it up; and no beat on the scope's I
        arm), 'false' (VC holds but a beat is there: a false lock), 'unlocked' (VC follows the step), 'railed'
        (U112A at a rail).  The board's ADC cannot tell: the ADS1115 averages a kHz beat to its mean."""
        cl = self.cl
        v = cl.dac_volts()["VC_OFF"]
        vc0, u0 = self.u112a()
        if not 0.25 < u0 < 3.05:
            return "railed", {"vc": vc0, "u112a": u0}
        cl.dac(S.DAC1, VC_OFF=v + 0.02)
        time.sleep(0.35)
        vc1, u1 = self.u112a()
        cl.dac(S.DAC1, VC_OFF=v)
        time.sleep(0.35)
        s = self.s
        s.timebase(scale=10e-6)
        time.sleep(0.25)
        pp_fast = s.pava("PKPK", 2)
        s.timebase(scale=1e-3)
        time.sleep(0.4)
        pp_slow, f = s.pava("PKPK", 2), s.pava("FREQ", 2)
        held = abs(vc1 - vc0) < 0.006
        info = {"vc": vc0, "u112a": u0, "dvc_for_step": vc1 - vc0, "pp_10us": pp_fast, "pp_1ms": pp_slow, "freq_1ms": f,
                "i": cl.adc("I"), "q": cl.adc("Q")}
        if not held:
            return "unlocked", info
        # a beat shows as a swing on the fast window comparable with the slow one's; locked, both are just noise
        return ("locked" if (pp_slow or 1) < 0.12 else "false"), info

    def acquire(self, mhzs=(5000, 4500, 5500, 4000, 5800, 3500), grid=(0.9, 2.41, 0.05), settle_s=2.0):
        import numpy as np
        out = []
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in mhzs:
                if not self.alive():
                    break
                floor = self.dsa_min(mhz)
                rx_ant = interp(self.tx_dbm, mhz) - PAD_DB
                dsa = min(31.75, max(floor, math.ceil((rx_ant + interp(self.chain0, mhz) + 20) * 4) / 4))
                rows = []
                for v in np.arange(*grid):
                    self.tx(False)
                    if not self.center(mhz):
                        rows.append({"vc_off": float(v), "error": "not centred"})
                        continue
                    self.cl.dsa(dsa)
                    self.cl.dac(S.DAC1, VC_OFF=float(v))
                    vc_start = self.cl.adc("VC")
                    self.tx(True)
                    time.sleep(0.1)
                    self.cl.ctrl(loop_hold=0)
                    time.sleep(settle_s)
                    st, info = self.lock_state()
                    self.cl.ctrl(loop_hold=1)
                    rows.append(dict(vc_off=float(v), vc_start=vc_start, state=st, **info))
                    print(mhz, "start VC %.3f -> %s, VC %.3f U112A %.2f pp %s" % (vc_start, st, info["vc"], info["u112a"],
                                                                                 info.get("pp_1ms")), flush=True)
                self.tx(False)
                rec = {"mhz": mhz, "dsa": dsa, "rows": rows}
                locks = [r for r in rows if r.get("state") == "locked"]
                if locks:                                    # the lock's DSA range and hold-in range, from the middle one
                    r0 = locks[len(locks) // 2]
                    self.center(mhz)
                    self.cl.dsa(dsa)
                    self.cl.dac(S.DAC1, VC_OFF=r0["vc_off"])
                    self.tx(True)
                    time.sleep(0.1)
                    self.cl.ctrl(loop_hold=0)
                    time.sleep(settle_s)
                    st0, _ = self.lock_state()
                    dsa_walk = []
                    if st0 == "locked":
                        for d in [x for x in np.arange(dsa, 31.76, 1.0)] + [x for x in np.arange(dsa, floor - 0.01, -1.0)]:
                            self.cl.dsa(float(d))
                            time.sleep(0.4)
                            st, info = self.lock_state()
                            dsa_walk.append(dict(dsa=float(d), state=st, **info))
                            if st != "locked":
                                self.cl.dsa(dsa)
                                time.sleep(0.5)
                                if self.lock_state()[0] != "locked":
                                    break
                    rec["dsa_walk"] = dsa_walk
                    self.cl.dsa(dsa)
                    hold = []
                    if self.lock_state()[0] == "locked":
                        for sgn in (1, -1):
                            for k in range(1, 40):
                                self.cl.dac(S.DAC1, VC_OFF=r0["vc_off"] + sgn * 0.05 * k)
                                time.sleep(0.4)
                                st, info = self.lock_state()
                                hold.append(dict(dvc_off=sgn * 0.05 * k, state=st, **info))
                                if st != "locked":
                                    break
                            self.cl.dac(S.DAC1, VC_OFF=r0["vc_off"])
                            time.sleep(0.5)
                    rec["hold_in"] = hold
                    self.cl.ctrl(loop_hold=1)
                    self.tx(False)
                out.append(rec)
                save("acquire_%d" % mhz, rec)
        finally:
            self.cl.ctrl(loop_hold=1)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
        path = save("acquire", out)
        self.b.record("verdict", test="night_acquire", ok=any(r.get("state") == "locked" for o in out for r in o["rows"]),
                      file=path, text="released from a grid of VC_OFF (the integrator centred each time): locked / false / "
                      "unlocked / railed after 2 s; then, locked, the DSA and VC_OFF stepped to the edges of the lock")
        return out

    # ---- E: drift ----
    def drift(self, hours=8.0, every_s=600):
        t_end = time.time() + hours * 3600
        n = 0
        while time.time() < t_end and self.alive():
            row = {"t": time.time()}
            try:
                self.cl.dsa(0.0 if self.dsa_min(5800) <= 0 else self.dsa_min(5800))
                self.tune(5800)
                self.tx(True)
                b = self.b
                b.sa_setup(5.8e9, 200e3, rbw=1e3, ref=0.0, att=10)
                b.sa.single()
                f0, p0 = b.sa.peak()
                b.sa_setup(f0, 2e3, rbw=30, ref=0.0, att=10)
                b.sa.single()
                fc, pc = b.sa.peak()
                self.tx(False)
                self.cl.dsa(31.75)
                S.loop_center(b)
                self.s.timebase(scale=10e-6)
                self.s.trigger(source=1, level=1.65, slope="rising", mode="auto")
                ref_hz, edges, _ = S._ref_hz(b, 1)
                self.s.run()
                det = self.cl.detectors()
                ps = b.psu_read("night drift")
                row.update(carrier_hz=fc, carrier_dbm=pc, tcxo_hz=fc / 232, vcxo_hz=ref_hz, vc=self.cl.adc("VC"),
                           temp_c=det["temp_c"], v5_rf=det["v5_rf"], amps=ps["amps"], volts=ps["volts"])
            except Exception as e:                                   # noqa: BLE001
                row["error"] = str(e)[:200]
                self.quiet()
            self.b.record("night_drift", **row)
            n += 1
            print(time.strftime("%H:%M:%S"), {k: (round(v, 3) if isinstance(v, float) else v) for k, v in row.items() if k != "t"}, flush=True)
            while time.time() < row["t"] + every_s and time.time() < t_end:
                time.sleep(5)
        self.quiet()
        return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("section", choices=["map", "iq", "loop", "acquire", "drift"])
    ap.add_argument("--step", type=int, default=None)
    ap.add_argument("--mhz", type=int, nargs="*")
    ap.add_argument("--hours", type=float, default=8.0)
    a = ap.parse_args()
    n = Night(a.section)
    if a.section == "map":
        n.map(step=a.step or 50)
    elif a.section == "iq":
        n.iq(step=a.step or 100)
    elif a.section == "loop":
        n.loop(mhzs=tuple(a.mhz) if a.mhz else (3500, 4000, 5000, 5800))
    elif a.section == "acquire":
        n.acquire(mhzs=tuple(a.mhz) if a.mhz else (5000, 4500, 5500, 4000, 5800, 3500))
    else:
        n.drift(hours=a.hours)


if __name__ == "__main__":
    main()
