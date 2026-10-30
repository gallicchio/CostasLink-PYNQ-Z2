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
        sc.channel(3, scale=0.02, offset=-q_mean)
        v0 = self.cl.dac_volts()["VC_OFF"]
        out = {"delta": delta, "khz": delta * self.kv(mhz) / 1e3, "a_mon": a_mon, "q_mean": q_mean, "caps": []}
        for tdiv in tdivs:
            sc.timebase(scale=tdiv, delay=4 * tdiv)
            for sgn in (+1, -1):
                got = None
                for slope, lev in (("rising", q_mean + 0.012), ("falling", q_mean - 0.012)):
                    sc.trigger(source=3, level=lev, slope=slope)
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
    ap.add_argument("section", choices=["lock", "schemes", "all"])
    ap.add_argument("--mhz", type=int, nargs="+", default=[5000, 5200])
    a = ap.parse_args(argv)
    L = Lock0()
    for mhz in a.mhz:
        if a.section in ("lock", "all"):
            L.lock(mhz)
        if a.section in ("schemes", "all"):
            L.schemes0(mhz)


if __name__ == "__main__":
    main(sys.argv[1:])
