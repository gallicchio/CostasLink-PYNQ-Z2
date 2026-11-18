#!/usr/bin/env python3
"""locktests.py: board A after the sign jumpers moved (2026-10-30 08:03: SIGN B1 / JP101 on Q+, SIGN B2 / JP102 on Q-;
REVB 9's remedy).  The Costas loop now locks where it was designed to: the idle on +-I, Q at its no-carrier level and
sign(I) steady (the first check, `link/lockcheck_swapped_20261030_080602.json`: 7 of 8 starts at 5.0 and 5.2 GHz).
TODO.md step 1's runs.  The bench as before: TX ANT -> 10 cm RG-316 -> two 20 dB pads -> RX ANT; the DSA875 on RX MON;
the scope's ch1 REF OUT, ch2 I MON, ch3 Q MON, ch4 VC MON (1 Mohm).

    python3 bringup/locktests.py lock    [--mhz 5000 5200]   pull-in, hold-in (a slow ramp of VC_OFF, then steps), the
                                                             step response (f_n and damping from Q MON), the DSA range,
                                                             the hold test
    python3 bringup/locktests.py schemes [--mhz 5000 5200]   the plan's A1, A1w, A2, A3 in the plan's frame; the PRBS BER
                                                             on CMP_I with the loop closed; FSK; the thresholds by
                                                             counting and the idle's false events against the windows'

Each writes bringup/data/board_A/link/<section>0_<mhz>_<time>.json and a verdict line, and leaves the transmitter
muted, the DSA at 31.75 dB, the loop held, VC_OFF and I_OFF_F at V_MID.
"""
import argparse
import math
import sys
import time

import numpy as np

import linktests as LT
import stages as S
from costaslink import SCHEMES, Scheme, point_code

PLAN = ("A1", "A1w", "A2", "A3")


def rx_pair(name, side, mirror):
    """(tx, rx) for one of the plan's schemes at this lock: the idle on side * I, and the board's I arm mirrored
    (REVB 9) or not.  The receiver sees R(theta) M p: with the mirror that is (side i, -side q), without (side i, side q)"""
    tx = SCHEMES[name]
    sq = -side if mirror else side
    f = lambda p: (side * p[0], sq * p[1])                              # noqa: E731
    rx = Scheme(name, tx.text, f(tx.idle), [f(m) for m in tx.msgs], [], rot_deg=0.0, t=tx.t, t2=tx.t2)
    rx.mask, rx.use = tx.mask, tx.use
    return tx, rx


class Lock0(LT.Schemes):
    # ---- the lock's frame now ----
    def frame0(self, cen, a_leg=None):
        """the idle's side (+1: on +I), whether it looks locked (CMP_I quiet, the I leg well away from its no-carrier
        level, Q near its own), and the numbers"""
        di = self.cl.adc("I") - cen["adc_i0"]
        dq = self.cl.adc("Q") - cen["adc_q0"]
        g = self.cl.gate(seconds=0.01, inputs=("CMP_I", "CMP_QP", "CMP_QN"))
        quiet = g["CMP_I"]["edges"] < 50
        ok = quiet and (a_leg is None or abs(di) > 0.6 * a_leg) and (a_leg is None or abs(dq) < 0.3 * a_leg)
        return (1 if di > 0 else -1), ok, {"di": di, "dq": dq, "cmp_i_edges": g["CMP_I"]["edges"],
                                           "cmp_i_duty": g["CMP_I"]["duty"], "vc": self.cl.adc("VC")}

    def acquire0(self, mhz, dsa, cen, starts_khz=(5, -5, 2, -2, 10, -10), center=True):
        for k in starts_khz:
            info = self.trial(mhz, S.V_MID, LT.VC_LOCK + k * 1e3 / self.kv(mhz), dsa, center=center)
            side, ok, fi = self.frame0(cen)
            if info["state"] == "locked" and ok:
                info.update(start_khz=k, side=side, frame=fi)
                return info
            self.cl.ctrl(loop_hold=1)
        return None

    def locked_now(self, vc_lock, tol=0.006):
        vc = self.cl.adc("VC")
        g = self.cl.gate(seconds=0.005, inputs=("CMP_I",))
        return abs(vc - vc_lock) < tol and g["CMP_I"]["edges"] < 25, vc, g["CMP_I"]["edges"]

    def ramp_vc_off(self, target, step=0.01, dwell=0.05):
        v = self.cl.dac_volts()["VC_OFF"]
        n = max(1, int(abs(target - v) / step))
        for x in np.linspace(v, target, n + 1)[1:]:
            self.cl.dac(S.DAC1, VC_OFF=float(x))
            time.sleep(dwell)

    # ---- the lock ----
    def hold_in(self, mhz, cen, vc_lock, step=0.02, dwell=0.15):
        """the static hold-in: VC_OFF ramped away from the lock in small steps (the integrator follows), each way, until
        the lock is lost or U112A nears its rail (then it is the integrator's range, not the loop's)"""
        v0 = self.cl.dac_volts()["VC_OFF"]
        out = {}
        for sgn in (+1, -1):
            last_ok, why = 0.0, None
            for k in range(1, 200):
                v = v0 + sgn * k * step
                if not 0.1 <= v <= 3.2:
                    why = "VC_OFF at the DAC's limit"
                    break
                self.cl.dac(S.DAC1, VC_OFF=float(v))
                time.sleep(dwell)
                ok, vc, e = self.locked_now(vc_lock)
                u = 3 * S.V_MID - vc - v
                if not ok:
                    why = "lost (VC %.3f, CMP_I %d edges)" % (vc, e)
                    break
                last_ok = sgn * k * step
                if not 0.3 < u < 3.0:
                    why = "U112A at %.2f V: the integrator's range" % u
                    break
            out["+" if sgn > 0 else "-"] = {"dvc_off": last_ok, "khz": last_ok * self.kv(mhz) / 1e3, "end": why}
            print("  hold-in %s: held to dVC_OFF %+.2f V (%+.0f kHz), %s" % ("+" if sgn > 0 else "-", last_ok,
                  last_ok * self.kv(mhz) / 1e3, why), flush=True)
            if ok:
                self.ramp_vc_off(v0)
            else:
                self.cl.ctrl(loop_hold=1)
                self.cl.dac(S.DAC1, VC_OFF=float(v0))
                return out, False
        return out, True

    def steps(self, mhz, cen, vc_lock, deltas=(0.01, 0.02, 0.05, 0.1, 0.2, 0.4)):
        """the dynamic hold-in: VC_OFF stepped by delta from the lock; locked 0.5 s later, on the same side?"""
        v0 = self.cl.dac_volts()["VC_OFF"]
        side0, _, _ = self.frame0(cen)
        rows = []
        for d in deltas:
            for sgn in (+1, -1):
                self.cl.dac(S.DAC1, VC_OFF=float(v0 + sgn * d))
                time.sleep(0.5)
                ok, vc, e = self.locked_now(vc_lock)
                side, ok2, fi = self.frame0(cen)
                r = {"dvc_off": sgn * d, "khz": sgn * d * self.kv(mhz) / 1e3, "locked": bool(ok and ok2),
                     "slipped": bool(ok and side != side0), "vc": vc, "cmp_i_edges": e}
                rows.append(r)
                print("  step %+.2f V (%+.0f kHz): %s%s" % (sgn * d, r["khz"], "held" if r["locked"] else "lost",
                      ", to the other side" if r["slipped"] else ""), flush=True)
                if r["locked"]:
                    self.ramp_vc_off(v0)
                    side0, _, _ = self.frame0(cen)
                else:
                    self.cl.ctrl(loop_hold=1)
                    self.cl.dac(S.DAC1, VC_OFF=float(v0))
                    return rows, False
        return rows, True

    def step_response(self, mhz, cen, delta=0.01, tdivs=(100e-6, 1e-3)):
        """Q MON after a VC_OFF step of delta (a frequency step of Kv delta): the phase error's transient, from which a
        second-order fit gives f_n and the damping.  Up, then back down, each timebase"""
        sc = self.s
        sc.timebase(scale=1e-3)
        sc.trigger(source=3, level=1.63, slope="rising", mode="auto")
        time.sleep(0.6)
        i_mean, q_mean = sc.pava("MEAN", 2), sc.pava("MEAN", 3)
        self.cl.ctrl(tx_dis=1, loop_hold=1)
        time.sleep(0.3)
        i_off = sc.pava("MEAN", 2)
        self.cl.ctrl(tx_dis=0, loop_hold=0)
        time.sleep(0.8)
        a_mon = abs(i_mean - i_off)
        vdiv = max(0.01, 1.2 * a_mon / 4)                   # +-1.2 a on the screen: the transient is never clipped
        lev = max(0.012, 0.25 * a_mon)
        sc.channel(3, scale=vdiv, offset=-q_mean)
        v0 = self.cl.dac_volts()["VC_OFF"]
        out = {"delta": delta, "khz": delta * self.kv(mhz) / 1e3, "a_mon": a_mon, "q_mean": q_mean, "vdiv": vdiv,
               "trigger_offset": lev, "caps": []}
        for tdiv in tdivs:
            sc.timebase(scale=tdiv, delay=4 * tdiv)
            for sgn in (+1, -1):
                got = None
                for slope, lv in (("rising", q_mean + lev), ("falling", q_mean - lev)):
                    sc.trigger(source=3, level=lv, slope=slope)
                    sc.arm()
                    self.cl.dac(S.DAC1, VC_OFF=float(v0 + (delta if sgn > 0 else 0.0)))
                    try:
                        sc.wait_stop(0.8)
                        got = slope
                    except TimeoutError:
                        sc.stop()
                    if got:
                        break
                    self.cl.dac(S.DAC1, VC_OFF=float(v0 if sgn > 0 else v0 + delta))   # undo, settle, try the other slope
                    time.sleep(0.4)
                if not got:                                  # neither slope fired: a forced record, kept as such
                    sc.acquire_now()
                t, q, _ = sc.waveform(3)
                t, q = np.asarray(t), np.asarray(q)
                k = max(1, len(q) // 4000)
                fit = fit_step(t[::k], q[::k] - q_mean, a_mon)
                out["caps"].append({"tdiv": tdiv, "up": sgn > 0, "slope": got, "t": list(t[::k]), "q": list(q[::k]),
                                    "fit": fit})
                print("  step %s at %g s/div: trigger %s; %s" % ("up" if sgn > 0 else "down", tdiv, got, fit and
                      {k2: (round(v, 3) if isinstance(v, float) else v) for k2, v in fit.items()}), flush=True)
                time.sleep(0.5)
                if sgn > 0 and not got:
                    break
            self.cl.dac(S.DAC1, VC_OFF=float(v0))
            time.sleep(0.5)
        sc.timebase(delay=0)
        self.scope_iq(vdiv=0.1)
        sc.run()
        return out

    def dsa_range(self, mhz, cen, step=2.0):
        rows = []
        dsas = sorted(set([float(x) for x in np.arange(self.dsa_min(mhz), 31.75, step)] + [31.75]))
        for d in dsas:
            lk = self.acquire0(mhz, d, cen, starts_khz=(5, -5, 2))
            r = {"dsa": d, "locked": lk is not None}
            if lk:
                r.update(side=lk["side"], di=lk["frame"]["di"], dq=lk["frame"]["dq"], start_khz=lk["start_khz"],
                         cmp_i_duty=lk["frame"]["cmp_i_duty"])
            rows.append(r)
            print("  DSA %5.2f: %s" % (d, ("locked, dI %+.3f dQ %+.3f" % (r["di"], r["dq"])) if lk else "no lock"), flush=True)
            self.cl.ctrl(loop_hold=1)
        return rows

    def hold_test(self, cen, vc_lock, holds_s=(0.001, 0.01, 0.1, 1.0, 10.0)):
        """LOOP_HOLD for each time from a lock (the sequencer under 1 s, the PC above), then released: Q at the end of
        the hold (the phase walked) and the lock 0.5 s after (the same side: no cycle slip)"""
        cl = self.cl
        rows = []
        for h in holds_s:
            side0, ok0, f0 = self.frame0(cen)
            if h < 1.0:
                clocks = int(h / cl.t_clk)
                settle = int(0.05 / cl.t_clk)
                cl.seq_program([(settle, {"loop_hold": 0, "tx_dis": 0, "tr_a": 1}),
                                (clocks, {"loop_hold": 1, "tx_dis": 0, "tr_a": 1}),
                                (settle, {"loop_hold": 0, "tx_dis": 0, "tr_a": 1})])
                cl.seq_run()
                cl.wait_s((2 * settle + clocks) * cl.t_clk + 0.05)
                dq_end = None
            else:
                cl.ctrl(loop_hold=1)
                time.sleep(h)
                dq_end = cl.adc("Q") - cen["adc_q0"]
                cl.ctrl(loop_hold=0)
            time.sleep(0.5)
            side, ok, fi = self.frame0(cen)
            ok2, vc, e = self.locked_now(vc_lock)
            r = {"hold_s": h, "locked_after": bool(ok and ok2), "slipped": side != side0, "dq_end": dq_end, "frame": fi}
            rows.append(r)
            print("  hold %g s: %s%s%s" % (h, "locked after" if r["locked_after"] else "LOST", ", slipped" if r["slipped"] else "",
                  "" if dq_end is None else ", Q moved %+.3f V in the hold" % dq_end), flush=True)
        return rows

    def lock(self, mhz=5000):
        out = {"mhz": mhz}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            out["centres"] = cen = self.centres()
            reg = self.regulated_dsa(mhz)
            out["regulated_dsa"] = reg
            print("%d MHz, DSA %.2f; no carrier I %.3f Q %.3f" % (mhz, reg, cen["adc_i0"], cen["adc_q0"]), flush=True)
            print(" pull-in:", flush=True)
            rows = []
            for k in (2, -2, 5, -5, 10, -10, 15, -15, 20, -20, 30, -30, 40, -40, 60, -60):
                info = self.trial(mhz, S.V_MID, LT.VC_LOCK + k * 1e3 / self.kv(mhz), reg)
                side, ok, fi = self.frame0(cen)
                info.update(offset_khz=k, side=side, frame=fi, state0=info["state"] if ok or info["state"] != "locked" else "locked_off_axis")
                rows.append({x: y for x, y in info.items() if x != "gate"})
                print("  %+3d kHz -> %s (side %+d, dI %+.3f, dQ %+.3f, VC %.3f)" % (k, info["state0"], side, fi["di"], fi["dq"],
                      fi["vc"]), flush=True)
                self.cl.ctrl(loop_hold=1)
            out["pull_in"] = rows
            lk = self.acquire0(mhz, reg, cen)
            if lk is None:
                out["error"] = "no lock for the hold-in"
                return out
            vc_lock = lk["frame"]["vc"]
            a_leg = abs(lk["frame"]["di"])
            out.update(vc_lock=vc_lock, a_leg=a_leg)
            print(" hold-in, a slow ramp:", flush=True)
            out["hold_in"], ok = self.hold_in(mhz, cen, vc_lock)
            if not ok and self.acquire0(mhz, reg, cen) is None:
                return out
            print(" hold-in, steps:", flush=True)
            out["steps"], ok = self.steps(mhz, cen, vc_lock)
            if not ok and self.acquire0(mhz, reg, cen) is None:
                return out
            print(" the step response:", flush=True)
            out["step_response"] = self.step_response(mhz, cen)
            if not self.frame0(cen, a_leg)[1] and self.acquire0(mhz, reg, cen) is None:
                return out
            print(" the hold test:", flush=True)
            out["hold_test"] = self.hold_test(cen, vc_lock)
            print(" the DSA range:", flush=True)
            out["dsa_range"] = self.dsa_range(mhz, cen)
        finally:
            self.cl.ctrl(loop_hold=1)
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
            path = LT.save("lock0_%d" % mhz, out)
            self.b.record("verdict", test="lock0", ok=None, file=path, mhz=mhz,
                          text="the Costas loop at its designed point (sign jumpers moved): pull-in, hold-in, the step "
                               "response, the hold test, the DSA range")
        return out

    # ---- the plan's schemes ----
    def false_events(self, cen, a_leg, fracs=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8), seconds=1.0):
        rows = []
        for t in fracs:
            th = self.thresholds(cen, a_leg, t)
            g = self.cl.gate(seconds=seconds)
            rows.append({"frac": t, "thresholds": th, "rx_events": g["rx_events"],
                         "edges": {k: g[k]["edges"] for k in ("CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN")},
                         "duty": {k: g[k]["duty"] for k in ("CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN")}})
            print("  windows at %.1f a: edges in %g s %s" % (t, seconds, rows[-1]["edges"]), flush=True)
        self.thresholds(cen, a_leg, 0.5)
        return rows

    def ber0(self, side, periods=(100, 20, 10, 5, 4, 2, 1), seconds=1.0):
        """the PRBS (BPSK, (1, 0) / (-1, 0)) with the loop closed: the Costas loop tracks through the data, as it is
        designed to; message 0 lands on side * I"""
        cl = self.cl
        cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
        out = []
        for p in periods:
            inv = side > 0
            r = cl.ber_run(seconds=seconds, poly=15, period=p, n=2, invert=inv)
            cl.hold_point(1, 0)
            if r.get("ber") is not None and r["ber"] > 0.4:                   # the other sense: say so, keep both
                r2 = cl.ber_run(seconds=seconds, poly=15, period=p, n=2, invert=not inv)
                cl.hold_point(1, 0)
                r = dict(r2, other_sense=r)
                inv = not inv
            r.update(period_clocks=p, baud=1.0 / (p * cl.t_clk), invert=inv, loop="closed")
            out.append(r)
            print("  BER %.1f Mbaud: %s" % (r["baud"] / 1e6, {k: v for k, v in r.items() if k != "other_sense"}), flush=True)
            time.sleep(0.3)
        return out

    def schemes0(self, mhz=5000, count=20000):
        out = {"mhz": mhz, "runs": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            out["centres"] = cen = self.centres()
            reg = self.regulated_dsa(mhz)
            out["regulated_dsa"] = reg
            lk = self.acquire0(mhz, reg, cen)
            if lk is None:
                out["error"] = "no lock"
                return out
            side, a_leg = lk["side"], abs(lk["frame"]["di"])
            th = self.thresholds(cen, a_leg)
            out.update(side=side, a_leg=a_leg, thresholds=th, lock={k: v for k, v in lk.items() if k != "gate"})
            print("%d MHz DSA %.2f locked: side %+d, a_leg %.3f V, dQ %+.3f; thresholds %s" % (
                mhz, reg, side, a_leg, lk["frame"]["dq"], {k: round(v, 3) for k, v in th.items()}), flush=True)
            print(" the thresholds by counting (Rice):", {w: (cen[w]["v0"], cen[w]["sigma"]) for w in ("QP", "QN", "IP", "IN")},
                  flush=True)
            diag = {}
            for mir in (False, True):
                st = self.run_scheme(rx_pair("A3", side, mir), count=4000)
                diag[mir] = sum(st["confusion"][k][k] for k in range(4))
                out.setdefault("mirror_test", {})[str(mir)] = {"confusion": st["confusion"], "decided": st["decided"]}
            mirror = diag[True] > diag[False]
            out["mirror"] = mirror
            print(" handedness: A3's diagonal %s -> mirror %s" % (diag, mirror), flush=True)
            for name in PLAN:
                for fe in ((False, True) if name in ("A1", "A2") else (False,)):
                    side_now, ok, fi = self.frame0(cen, a_leg)
                    if not ok:
                        lk = self.acquire0(mhz, reg, cen)
                        if lk is None:
                            break
                        side_now, ok, fi = self.frame0(cen, a_leg)
                    st = self.run_scheme(rx_pair(name, side_now, mirror), count=count, first_edge=fe)
                    s2, ok2, fi2 = self.frame0(cen, a_leg)
                    st.update(scheme=name, text=SCHEMES[name].text, first_edge=fe, n=SCHEMES[name].n, side=side_now,
                              mirror=mirror, frame_before=fi, frame_after=fi2,
                              state_after=("locked" if ok2 else "lost") + ("" if s2 == side_now else ", flipped"))
                    out["runs"].append(st)
                    lat = [LT.to_ns(st[k]) for k in ("lat_min", "lat_mean", "lat_max")] if st["lat_n"] else None
                    print("  %s%s: refs %d events %d decided %d false %d missed %d veto %d; latency %s ns; after: %s" % (
                        name, " first-edge" if fe else "", st["refs"], st["events"], st["decided"], st["false"],
                        st["missed"], st["veto"], lat and ["%.1f" % x for x in lat], st["state_after"]), flush=True)
            LT.save("schemes0_partial", out)
            out["constellations"] = {}
            for name in PLAN:
                side_now, ok, _ = self.frame0(cen, a_leg)
                if not ok and self.acquire0(mhz, reg, cen) is None:
                    break
                side_now, ok, _ = self.frame0(cen, a_leg)
                c = self.scope_constellation(rx_pair(name, side_now, mirror))
                c["side"] = side_now
                out["constellations"][name] = c
            side_now, ok, _ = self.frame0(cen, a_leg)
            if not ok:
                self.acquire0(mhz, reg, cen)
                side_now, ok, _ = self.frame0(cen, a_leg)
            print(" the BER, the loop closed:", flush=True)
            out["ber"] = self.ber0(side_now)
            side_now, ok, _ = self.frame0(cen, a_leg)
            out["ber_state_after"] = "locked" if ok else "lost"
            if not ok:
                self.acquire0(mhz, reg, cen)
            print(" FSK:", flush=True)
            out["fsk"] = self.fsk()
            side_now, ok, _ = self.frame0(cen, a_leg)
            if not ok:
                self.acquire0(mhz, reg, cen)
            print(" the idle's false events:", flush=True)
            out["false_events"] = self.false_events(cen, a_leg)
        finally:
            self.cl.ctrl(loop_hold=1)
            try:
                self.cl.tx_stop()
            except Exception:                                        # noqa: BLE001
                pass
            self.ioff(S.V_MID)
            self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
            self.quiet()
            path = LT.save("schemes0_%d" % mhz, out)
            self.b.record("verdict", test="schemes0", ok=None, file=path, mhz=mhz,
                          text="the plan's schemes at the designed lock (A1, A1w, A2, A3), the BER on CMP_I with the loop "
                               "closed, FSK, the thresholds by counting and the idle's false events")
        return out


def _step_only(self, mhz, deltas=(0.005, 0.01)):
    """the step response alone, re-run (the first pass's Q MON at 20 mV/div clipped at 5.0 GHz and lost the trigger
    at 5.2): from a lock at the regulated DSA, each delta"""
    out = {"mhz": mhz, "runs": []}
    self.scope_iq(vdiv=0.1)
    try:
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        reg = self.regulated_dsa(mhz)
        out["regulated_dsa"] = reg
        for d in deltas:
            if self.acquire0(mhz, reg, cen) is None:
                out["runs"].append({"delta": d, "error": "no lock"})
                continue
            print(" %d MHz, step %.3f V:" % (mhz, d), flush=True)
            out["runs"].append(self.step_response(mhz, cen, delta=d))
            self.cl.ctrl(loop_hold=1)
    finally:
        self.cl.ctrl(loop_hold=1)
        self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.quiet()
        path = LT.save("step0_%d" % mhz, out)
        self.b.record("verdict", test="step0", ok=None, file=path, mhz=mhz,
                      text="the loop's step response re-run, Q MON scaled to the idle (f_n and damping)")
    return out


def _confirm_scan(self, mhz, confirms=(6, 8, 10, 12, 16, 24, 32), count=4000):
    """A1 vetoed every decision at confirm 6 (60 ns after the decision) while A2 and A3 were confirmed: the slow I
    stage's gain of 20 idles it overdriven (PATHS.md section 7: start the confirm delay at 80 ns).  A1 and A2 at each
    confirm delay, to find where the slow I agrees"""
    out = {"mhz": mhz, "rows": []}
    self.scope_iq(vdiv=0.1)
    try:
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        reg = self.regulated_dsa(mhz)
        lk = self.acquire0(mhz, reg, cen)
        if lk is None:
            out["error"] = "no lock"
            return out
        side, a_leg = lk["side"], abs(lk["frame"]["di"])
        self.thresholds(cen, a_leg)
        diag = {}
        for mir in (False, True):
            st = self.run_scheme(rx_pair("A3", side, mir), count=2000)
            diag[mir] = sum(st["confusion"][k][k] for k in range(4))
        mirror = diag[True] > diag[False]
        for c in confirms:
            for name in ("A1", "A2"):
                side_now, ok, _ = self.frame0(cen, a_leg)
                if not ok:
                    if self.acquire0(mhz, reg, cen) is None:
                        break
                    side_now, ok, _ = self.frame0(cen, a_leg)
                tx, rx = rx_pair(name, side_now, mirror)
                cl = self.cl
                cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
                cl.rx_config(rx.idle_vector(), rx.mask, rx.lut(False), rx.slow_exp(), delay=16, quiet=4, confirm=c,
                             window=100)
                cl.events(period=2000, width=20, count=count, n=tx.n)
                cl.rx_clear()
                cl.tx_go()
                time.sleep(2000 * count * cl.t_clk + 0.2)
                st = cl.rx_stats()
                cl.hold_point(1, 0)
                out["rows"].append({"confirm_clocks": c, "scheme": name, **st})
                print("  confirm %d clocks (%d ns): %s decided %d confirmed %d vetoed %d" % (
                    c, c * 10, name, st["decided"], st["confirm"], st["veto"]), flush=True)
        # the slow comparators held at each point (the loop held), to see what CMP_I_S reads
        statics = []
        for pt in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            self.cl.ctrl(loop_hold=1)
            self.cl.hold_point(*pt)
            time.sleep(0.02)
            g = self.cl.gate(seconds=0.002)
            statics.append({"tx_point": pt, "duty": {k: g[k]["duty"] for k in ("CMP_I", "CMP_I_S", "CMP_QP_S", "CMP_QN_S",
                                                                                  "CMP_QP", "CMP_QN")}})
            print("  held at TX %s: %s" % (pt, {k: round(v, 2) for k, v in statics[-1]["duty"].items()}), flush=True)
        self.cl.hold_point(1, 0)
        out["statics"] = statics
    finally:
        self.cl.ctrl(loop_hold=1)
        try:
            self.cl.tx_stop()
        except Exception:                                            # noqa: BLE001
            pass
        self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.quiet()
        path = LT.save("confirm0_%d" % mhz, out)
        self.b.record("verdict", test="confirm0", ok=None, file=path, mhz=mhz,
                      text="A1 / A2 against the confirm delay: where the slow I comparator agrees; the slow comparators at each held point")
    return out


def _dsa_only(self, mhz):
    """the DSA range alone, re-run (the first pass at 5.2 GHz lost every release above DSA 2 to a centring that could
    not bring a clipped VC back at a low DSA; overnight.Night.center now centres at DSA 31.75)"""
    out = {"mhz": mhz}
    self.scope_iq(vdiv=0.1)
    try:
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        out["dsa_range"] = self.dsa_range(mhz, cen)
    finally:
        self.cl.ctrl(loop_hold=1)
        self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.quiet()
        path = LT.save("dsa0_%d" % mhz, out)
        self.b.record("verdict", test="dsa0", ok=None, file=path, mhz=mhz, text="the DSA range at the designed lock, re-run")
    return out


def _vt2_scan(self, mhz, vs=(1.65, 1.75, 1.85, 1.95, 2.1, 2.3, 2.6), confirm=10, count=4000):
    """the slow Q window's threshold: V_T2 was left at V_MID (its default), so at a point with Q near zero (A1's flip)
    CMP_QP_S or CMP_QN_S reads the leg's offset and the expected (0, 0) is vetoed.  V_T2 at the Q legs' no-carrier
    level plus k a, A1 and A2 at each (the confirm 100 ns: PATHS.md section 7 says 80 ns or more).  The slow Q stage
    (U502) is x20, so V_T2 sits above 20 times the arm's static error (BRINGUP.md section 5): absolute volts here"""
    out = {"mhz": mhz, "rows": []}
    self.scope_iq(vdiv=0.1)
    try:
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        reg = self.regulated_dsa(mhz)
        lk = self.acquire0(mhz, reg, cen)
        if lk is None:
            out["error"] = "no lock"
            return out
        side, a_leg = lk["side"], abs(lk["frame"]["di"])
        self.thresholds(cen, a_leg)
        q0 = 0.5 * ((cen["QP"]["v0"] or S.V_MID) + (cen["QN"]["v0"] or S.V_MID))
        out.update(a_leg=a_leg, q0=q0)
        diag = {}
        for mir in (False, True):
            st = self.run_scheme(rx_pair("A3", side, mir), count=2000)
            diag[mir] = sum(st["confusion"][k][k] for k in range(4))
        mirror = diag[True] > diag[False]
        for v in vs:
            k = (v - q0) / a_leg
            self.cl.dac(S.DAC2, V_T2=float(v))
            time.sleep(0.02)
            g = self.cl.gate(seconds=0.01, inputs=("CMP_QP_S", "CMP_QN_S", "CMP_I_S"))
            idle = {x: g[x]["duty"] for x in ("CMP_QP_S", "CMP_QN_S", "CMP_I_S")}
            for name in ("A1", "A2", "A3"):
                side_now, ok, _ = self.frame0(cen, a_leg)
                if not ok:
                    if self.acquire0(mhz, reg, cen) is None:
                        break
                    side_now, ok, _ = self.frame0(cen, a_leg)
                tx, rx = rx_pair(name, side_now, mirror)
                cl = self.cl
                cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
                cl.rx_config(rx.idle_vector(), rx.mask, rx.lut(False), rx.slow_exp(), delay=16, quiet=4, confirm=confirm,
                             window=100)
                cl.events(period=2000, width=20, count=count, n=tx.n)
                cl.rx_clear()
                cl.tx_go()
                time.sleep(2000 * count * cl.t_clk + 0.2)
                st = cl.rx_stats()
                cl.hold_point(1, 0)
                out["rows"].append({"k": k, "v_t2": v, "idle_slow": idle, "scheme": name, **st})
                print("  V_T2 %.3f V (q0 + %.2f a): idle QP_S %.2f QN_S %.2f; %s decided %d confirmed %d vetoed %d" % (
                    v, k, idle["CMP_QP_S"], idle["CMP_QN_S"], name, st["decided"], st["confirm"], st["veto"]), flush=True)
    finally:
        self.cl.dac(S.DAC2, V_T2=S.V_MID)
        self.cl.ctrl(loop_hold=1)
        try:
            self.cl.tx_stop()
        except Exception:                                            # noqa: BLE001
            pass
        self.cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.quiet()
        path = LT.save("vt2_%d" % mhz, out)
        self.b.record("verdict", test="vt2", ok=None, file=path, mhz=mhz,
                      text="the slow Q window's threshold V_T2 against A1 / A2 / A3's confirmation (V_T2 had been left at V_MID)")
    return out


def _drift_rates(self, mhz, cen, offsets_khz=(-60, -40, -30, -20, -15, -10, 10, 15, 20, 30, 40, 60), ioff=S.V_MID,
                 release_s=0.003, reps=2):
    """the unlocked loop's push: VC held at each offset from the lock (TX on, the integrator centred), released for
    release_s by the sequencer; VC's rate (V/s) is (ERR - V_MID) / (R126 C130).  Pull-in from both sides needs the rate
    toward the lock from both (VC falling for + offsets, rising for -).  Until 2026-10-31 the release step named only
    loop_hold, and a sequencer step drives every bit it does not name to 1: the TX was muted for the release, so 3.6d's
    rates were the integrator with no carrier (BRINGUP_LOG 4.12).  The step now keeps the TX on"""
    rows = []
    for off in offsets_khz:
        rates = []
        for _ in range(reps):
            self.tx(False)
            self.center(mhz)
            self.cl.dsa(float(self.regulated_dsa(mhz)))
            self.ioff(ioff)
            self.set_vc(LT.VC_LOCK + off * 1e3 / self.kv(mhz))
            self.tx(True)
            time.sleep(0.1)
            g = self.cl.gate(seconds=0.01, inputs=("CMP_I",))
            v0 = self.cl.adc("VC")
            tr_a = self.cl.rd("CTRL") >> self.cl.CTRL_BITS["tr_a"] & 1
            self.cl.seq_program([(release_s / self.cl.t_clk, {"loop_hold": 0, "tx_dis": 0, "tx_gate": 1, "tr_a": tr_a})])
            self.cl.seq_run()
            time.sleep(release_s + 0.03)
            v1 = self.cl.adc("VC")
            rates.append((v1 - v0) / release_s)
        r = {"offset_khz": off, "rate_v_s": float(np.mean(rates)), "rates": rates, "cmp_i_duty": g["CMP_I"]["duty"],
             "toward_lock": bool(np.mean(rates) * off < 0)}
        rows.append(r)
        print("  I_OFF_F %.2f, %+3d kHz: VC %+6.1f V/s (%s), CMP_I duty %.2f" % (ioff, off, r["rate_v_s"],
              "toward the lock" if r["toward_lock"] else "AWAY", g["CMP_I"]["duty"]), flush=True)
    self.ioff(S.V_MID)
    self.tx(False)
    return rows


def _diag(self, mhz=5000):
    """four quick checks (2026-10-30, Jason's questions): the pull-in's one-sidedness (the unlocked push, with I_OFF_F at
    V_MID and at the fast I arm's null), the BER at 100 / 50 Mbaud against the sampling phase, whether TX_MODE 4's
    direction bit reverses the ladder's own sequence (the capture reads the pads back), and the TX carrier nulled at
    this frequency with VR_I / VR_Q (then A1's confirmation and flip again; the trims restored after)"""
    from linktests import fsk_order
    from costaslink import Scheme, CMP_IP
    out = {"mhz": mhz}
    cl = self.cl
    vr0 = {k: cl.dac_volts()[k] for k in ("VR_I", "VR_Q")}
    out["vr_before"] = vr0
    self.scope_iq(vdiv=0.1)
    try:
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        reg = self.regulated_dsa(mhz)
        # A: the push
        v_null, _ = self.null_fast_i()
        out["i_off_f_null"] = v_null
        print(" A. the unlocked loop's push (I_OFF_F null with no carrier: %s V)" % v_null, flush=True)
        out["push_vmid"] = self.drift_rates(mhz, cen)
        if v_null is not None:
            out["push_null"] = self.drift_rates(mhz, cen, ioff=v_null)
            print("  releases with I_OFF_F at its null:", flush=True)
            rel = []
            for k in (-60, -40, -30, -20, -15, 15, 30, 60):
                info = self.trial(mhz, v_null, LT.VC_LOCK + k * 1e3 / self.kv(mhz), reg)
                side, ok, fi = self.frame0(cen)
                rel.append({"offset_khz": k, "state": info["state"], "ok": ok, "frame": fi})
                print("   %+3d kHz -> %s" % (k, info["state"] if ok or info["state"] != "locked" else "locked, off axis"), flush=True)
                cl.ctrl(loop_hold=1)
            out["pull_in_null"] = rel
            self.ioff(S.V_MID)
        LT.save("diag_partial", out)
        # B: the BER against the sampling phase
        print(" B. the BER against the sampling phase:", flush=True)
        lk = self.acquire0(mhz, reg, cen)
        rows = []
        if lk:
            side = lk["side"]
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
            for p, nph in ((1, 8), (2, 16)):
                for ph in range(nph):
                    r = cl.ber_run(seconds=0.2, poly=15, period=p, phase=ph, n=2, invert=side > 0)
                    cl.hold_point(1, 0)
                    r.update(period_clocks=p, phase=ph)
                    rows.append(r)
                    print("   %3.0f Mbaud, phase %2d (%.2f ns into the symbol): BER %s" % (100.0 / p, ph, ph * 1.25, r["ber"]), flush=True)
                    s2, ok, _ = self.frame0(cen)
                    if not ok:
                        self.acquire0(mhz, reg, cen)
        out["ber_phase"] = rows
        LT.save("diag_partial", out)
        # C: does the rotation's direction bit reverse the ladder?
        print(" C. FSK: the ladder's own sequence, read back:", flush=True)
        fsk = []
        pts = [(1, 0), (0, 1), (-1, 0), (0, -1)]
        cl.tx_points(point_code(1, 0), [point_code(i, q) for i, q in pts])
        for back in (False, True):
            cl.ctrl(loop_hold=1)
            cl.tx_timing(period=10, width=1, count=0)
            cl.tx_mode("rotate", n=4, backwards=back)
            cl.tx_go()
            time.sleep(0.002)
            cl.cap_arm("none", post=4000)
            cl.cap_force()
            c = cl.cap_read(timeout=1.0)
            cl.tx_stop()
            cl.hold_point(1, 0)
            codes = c.get("TX_PINS") or []
            seq = [codes[0]] if codes else []
            for x in codes[1:]:
                if x != seq[-1]:
                    seq.append(x)
            fsk.append({"backwards": back, "tx_codes": seq[:24], "rx": fsk_order(c),
                        "codes_expected": [point_code(i, q) for i, q in pts]})
            print("   %s: TX pins %s; RX windows %s" % ("backwards" if back else "forwards", seq[:12], fsk_order(c)["first"][:8]), flush=True)
        out["fsk_pins"] = fsk
        cl.ctrl(loop_hold=0)
        LT.save("diag_partial", out)
        # D: the carrier null at this frequency
        print(" D. the TX carrier null with VR_I / VR_Q:", flush=True)
        cl.ctrl(loop_hold=1)
        self.tune(mhz)
        cl.dsa(float(self.dsa_min(mhz)))
        self.tx(True)
        cl.hold_point(1, 0)
        time.sleep(0.05)
        f1, p1 = self.rx_mon(mhz, span=200e3)
        def car():
            b = self.b
            b.sa_setup(f1, 20e3, rbw=300, ref=0.0, att=10)
            b.sa.single()
            return b.sa.peak()[1]
        cl.hold_point(0, 0)
        time.sleep(0.05)
        p0 = car()
        print("   (1, 0) %.1f dBm at %.0f Hz; (0, 0) with the trims as they were %.1f dBm: %.1f dBc" % (p1, f1, p0, p0 - p1), flush=True)
        best = dict(vr0)
        trace = []
        for span, step in ((0.08, 0.01), (0.02, 0.0025)):
            for k in ("VR_I", "VR_Q"):
                vals = np.arange(best[k] - span, best[k] + span + 1e-9, step)
                res = []
                for v in vals:
                    v = float(min(0.45, max(0.0, v)))
                    cl.dac(S.DAC1, **{k: v})
                    time.sleep(0.02)
                    res.append((v, car()))
                    trace.append({k: v, "dbm": res[-1][1]})
                best[k] = min(res, key=lambda x: x[1])[0]
                cl.dac(S.DAC1, **{k: best[k]})
                time.sleep(0.02)
        p0n = car()
        cl.hold_point(1, 0)
        time.sleep(0.05)
        p1n = car()
        out["null"] = {"before": {"carrier": p1, "null": p0, "dbc": p0 - p1}, "vr_null": best,
                       "after": {"carrier": p1n, "null": p0n, "dbc": p0n - p1n}, "trace": trace}
        print("   nulled at VR_I %.4f, VR_Q %.4f: (0, 0) %.1f dBm, (1, 0) %.1f dBm: %.1f dBc" % (
            best["VR_I"], best["VR_Q"], p0n, p1n, p0n - p1n), flush=True)
        # then A1 again: its confirmation and its flip
        self.tx(False)
        self.center(mhz)
        cen = self.centres()
        lk = self.acquire0(mhz, reg, cen)
        if lk:
            side, a_leg = lk["side"], abs(lk["frame"]["di"])
            self.thresholds(cen, a_leg)
            cl.dac(S.DAC2, V_T2=2.0)
            tx, rx = rx_pair("A1", side, True)
            cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
            cl.rx_config(rx.idle_vector(), rx.mask, rx.lut(False), rx.slow_exp(), delay=16, quiet=4, confirm=10, window=100)
            cl.events(period=2000, width=20, count=4000, n=tx.n)
            cl.rx_clear()
            cl.tx_go()
            time.sleep(2000 * 4000 * cl.t_clk + 0.2)
            st = cl.rx_stats()
            cl.hold_point(1, 0)
            out["a1_after_null"] = st
            print("   A1 with the carrier nulled (V_T2 2.0 V, confirm 100 ns): decided %d confirmed %d vetoed %d" % (
                st["decided"], st["confirm"], st["veto"]), flush=True)
            self.s.timebase(scale=20e-6)
            cl.ctrl(tx_dis=1, loop_hold=1)
            time.sleep(0.4)
            nc = (self.s.pava("MEAN", 2), self.s.pava("MEAN", 3))
            cl.ctrl(tx_dis=0, loop_hold=0)
            time.sleep(0.5)
            c = self.scope_constellation(T_SCH["A1"])
            i, q = np.array(c["i"]) - nc[0], np.array(c["q"]) - nc[1]
            x = side * i
            m = 0.5 * (np.percentile(x, 3) + np.percentile(x, 97))
            idle = (float(np.median(i[x > m])), float(np.median(q[x > m])))
            fl = (float(np.median(i[x <= m])), float(np.median(q[x <= m])))
            ang = math.degrees(math.atan2(fl[1], fl[0]) - math.atan2(idle[1], idle[0])) % 360
            out["a1_flip_after_null"] = {"idle": idle, "flip": fl, "angle_deg": ang}
            print("   the flip with the carrier nulled: %.0f degrees from the idle (its Q %.3f V, %.2f a)" % (
                ang, fl[1], abs(fl[1]) / math.hypot(*idle)), flush=True)
    finally:
        cl.dac(S.DAC1, VR_I=float(vr0["VR_I"]), VR_Q=float(vr0["VR_Q"]))
        cl.dac(S.DAC2, V_T2=S.V_MID)
        cl.ctrl(loop_hold=1)
        try:
            cl.tx_stop()
        except Exception:                                            # noqa: BLE001
            pass
        self.ioff(S.V_MID)
        cl.dac(S.DAC1, VC_OFF=S.V_MID)
        self.quiet()
        try:
            self.b.sa_live()
        except Exception as e:                                       # noqa: BLE001
            print("sa_live failed:", e, flush=True)
        out["vr_restored"] = {k: cl.dac_volts()[k] for k in ("VR_I", "VR_Q")}
        path = LT.save("diag_%d" % mhz, out)
        self.b.record("verdict", test="diag0", ok=None, file=path, mhz=mhz,
                      text="the unlocked push against I_OFF_F, the BER against the sampling phase, FSK's direction bit "
                           "read back, the TX carrier nulled with VR_I / VR_Q and A1 again (the trims restored)")
    return out


T_SCH = SCHEMES
Lock0.drift_rates = _drift_rates
Lock0.diag = _diag
Lock0.vt2_scan = _vt2_scan
Lock0.dsa_only = _dsa_only
Lock0.step_only = _step_only
Lock0.confirm_scan = _confirm_scan


def fit_step(t, y, a_mon):
    """the phase error after a frequency step, phi = asin(y / a), against a second-order loop's
    A e^(-s t') sin(w t') (underdamped) and A (e^(-s1 t') - e^(-s2 t')) (overdamped), t' = t - t0; the better fit"""
    from scipy.optimize import curve_fit
    if not a_mon or a_mon < 0.01 or len(t) < 50:
        return None
    phi = np.arcsin(np.clip(y / a_mon, -1, 1))
    pk = int(np.argmax(np.abs(phi)))
    if abs(phi[pk]) < 0.05:
        return {"note": "no transient", "peak_rad": float(phi[pk])}
    sgn = np.sign(phi[pk])
    T = t[-1] - t[0]

    def under(tt, A, s, w, t0):
        x = np.clip(tt - t0, 0, None)
        return A * np.exp(-s * x) * np.sin(w * x)

    def over(tt, A, s1, s2, t0):
        x = np.clip(tt - t0, 0, None)
        return A * (np.exp(-s1 * x) - np.exp(-s2 * x))

    t_pk = max(t[pk] - t[0], T / 200)
    best = None
    for kind, f, p0 in (("under", under, (sgn * abs(phi[pk]) * 1.3, 1 / (2 * t_pk), math.pi / (2 * t_pk), t[0] + T / 10)),
                        ("over", over, (sgn * abs(phi[pk]) * 2, 0.5 / t_pk, 3 / t_pk, t[0] + T / 10))):
        try:
            p, _ = curve_fit(f, t, phi, p0=p0, maxfev=20000)
        except (RuntimeError, ValueError):
            continue
        res = float(np.sqrt(np.mean((f(t, *p) - phi) ** 2)))
        if best is None or res < best[2]:
            best = (kind, p, res)
    if best is None:
        return {"note": "no fit", "peak_rad": float(phi[pk])}
    kind, p, res = best
    if kind == "under":
        A, s, w, t0 = p
        wn = math.hypot(s, w)
        zeta = abs(s) / wn
    else:
        A, s1, s2, t0 = p
        wn = math.sqrt(abs(s1 * s2))
        zeta = (abs(s1) + abs(s2)) / (2 * wn)
    return {"model": kind, "fn_hz": wn / (2 * math.pi), "zeta": zeta, "peak_rad": float(phi[pk]), "t_peak_s": float(t[pk] - p[3]),
            "rms_rad": res, "params": [float(x) for x in p]}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("section", choices=["lock", "schemes", "all", "step", "confirm", "dsa", "vt2", "diag"])
    ap.add_argument("--mhz", type=int, nargs="+", default=[5000, 5200])
    a = ap.parse_args(argv)
    L = Lock0()
    for mhz in a.mhz:
        if a.section in ("lock", "all"):
            L.lock(mhz)
        if a.section in ("schemes", "all"):
            L.schemes0(mhz)
        if a.section == "diag":
            L.diag(mhz)
        if a.section == "vt2":
            L.vt2_scan(mhz)
        if a.section == "dsa":
            L.dsa_only(mhz)
        if a.section == "step":
            L.step_only(mhz)
        if a.section == "confirm":
            L.confirm_scan(mhz)


if __name__ == "__main__":
    main(sys.argv[1:])
