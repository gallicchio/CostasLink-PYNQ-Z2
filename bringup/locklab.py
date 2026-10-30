#!/usr/bin/env python3
"""locklab.py: the Costas loop's lock and its loss, with the link's real conditions in mind (Jason, 2026-10-30 11:15:
"loss of lock will continue to be the biggest problem ... interference and a low and changing signal amplitude ...
the WiFi and ISM bands ... intermittent").  Board A in loopback (TX ANT -> lead -> 40 dB -> RX ANT), the sign jumpers
moved (BRINGUP_LOG 3.6), the TX carrier nulled per frequency from campaign.py cal's table while a test runs (the
trims restored after).

    python3 bringup/locklab.py detect     what tells locked from false-locked, beating and no signal: CMP_I's edges,
                                          the windows', the I and Q legs, LOG_Q and PEAK_Q (the AD8310 on Q), VC
    python3 bringup/locklab.py drop       dropouts: the TX muted 1 us - 1 s by the sequencer, the loop free or held
                                          through it (blanking): back on the same side, slipped, or lost
    python3 bringup/locklab.py fade       fades: the DSA stepped 3-25 dB for 10 ms - 1 s and back
    python3 bringup/locklab.py cw         a CW interferer stronger than the signal: the wanted carrier a weak pilot
                                          from VR_I / VR_Q (the ladder at (0, 0)), the interferer the ladder rotating
                                          through the axis points (amplitude a, f_rot 10 kHz - 12.5 MHz off), steady and
                                          in sequencer-gated bursts (WiFi-like), the loop free or held in the bursts
    python3 bringup/locklab.py slips      the weak end: the lock watched for 30 s at each DSA up to where it fails
    python3 bringup/locklab.py recover    loss forced (a VC_OFF kick), then a firmware-style recovery (detect, hold,
                                          centre, release from above, check); its time and success
    python3 bringup/locklab.py falselock  releases from -60 to +60 kHz: where the loop ends, and what the detectors
                                          say there

Each writes bringup/data/board_A/locklab/<section>_<time>.json and a verdict, and leaves the transmitter muted, the DSA
at 31.75 dB, the loop held, the trims as they were.
"""
import argparse
import glob
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import campaign as C                                 # noqa: E402
import linktests as LT                               # noqa: E402
import stages as S                                   # noqa: E402
from costaslink import point_code                    # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "locklab")
VR_PER_A = 0.42                                      # the VR change that moves the ladder node by one level, a (0.33 V / 0.786)


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, LT.O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


def null_table():
    fs = sorted(glob.glob(os.path.join(HERE, "data", "board_A", "campaign", "cal_2*.json")))
    if not fs:
        return {}
    return {r["mhz"]: r["vr_null"] for r in json.load(open(fs[-1]))["rows"] if r["dbc_after"] < -40}


class Lab(C.Camp):
    def __init__(self):
        super().__init__()
        self.vr0 = {k: self.cl.dac_volts()[k] for k in ("VR_I", "VR_Q")}
        self.nulls = null_table()

    def set_null(self, mhz, pilot=0.0):
        """the carrier nulled for mhz (the nearest entry), plus a pilot of `pilot` a along +I"""
        if not self.nulls:
            return None
        k = min(self.nulls, key=lambda m: abs(m - mhz))
        v = self.nulls[k]
        self.cl.dac(S.DAC1, VR_I=float(v["VR_I"] + VR_PER_A * pilot), VR_Q=float(v["VR_Q"]))
        return {"VR_I": v["VR_I"] + VR_PER_A * pilot, "VR_Q": v["VR_Q"], "from_mhz": k}

    def restore(self):
        self.cl.dac(S.DAC1, VR_I=float(self.vr0["VR_I"]), VR_Q=float(self.vr0["VR_Q"]))

    # ---- the state now ----
    def observe(self, cen, a_ref, side0=None, gate_s=0.01):
        cl = self.cl
        g = cl.gate(seconds=gate_s)
        di, dq = cl.adc("I") - cen["adc_i0"], cl.adc("Q") - cen["adc_q0"]
        det = cl.detectors()["volts"]
        vc = cl.adc("VC")
        e = {k: g[k]["edges"] for k in ("CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN")}
        side = 1 if di > 0 else -1
        locked = e["CMP_I"] < 50 and abs(di) > 0.5 * a_ref and abs(dq) < 0.35 * a_ref
        state = "locked" if locked else ("beating" if e["CMP_I"] > 200 else "other")
        if locked and side0 is not None and side != side0:
            state = "slipped"
        return {"state": state, "side": side, "di": di, "dq": dq, "vc": vc, "edges": e, "log_q": det["LOG_Q"],
                "peak_q": det["PEAK_Q"], "cmp_i_duty": g["CMP_I"]["duty"]}

    def seq_once(self, steps):
        cl = self.cl
        cl.seq_program(steps, loop=False)
        cl.seq_run()
        total = sum(s[0] for s in steps) * cl.t_clk
        time.sleep(total + 0.02)
        for _ in range(50):
            if not cl.seq_state()["running"]:
                break
            time.sleep(0.02)

    # ---- detect ----
    def detect(self):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                for dd in (0, 6, 9):
                    dsa = min(31.75, reg + dd)
                    lk = self.lock_at(mhz, dsa, fresh=(dd == 0))
                    if lk is None:
                        continue
                    cen, side, a, _ = lk
                    rows = [dict(self.observe(cen, a), kind="locked")]
                    vc_lock = rows[0]["vc"]
                    for off in (2, 5, 20, 50, -5, -20):        # beating: the loop held off the lock
                        self.cl.ctrl(loop_hold=1)
                        self.set_vc(vc_lock + off * 1e3 / self.kv(mhz))
                        time.sleep(0.1)
                        rows.append(dict(self.observe(cen, a), kind="beat %+d kHz" % off))
                    self.tx(False)
                    time.sleep(0.1)
                    rows.append(dict(self.observe(cen, a), kind="no signal (TX muted)"))
                    self.tx(True)
                    for k in (-30, -40, -60, 30, 40, 60):       # false locks, if any, from far releases
                        info = self.trial(mhz, S.V_MID, LT.VC_LOCK + k * 1e3 / self.kv(mhz), dsa)
                        o = self.observe(cen, a)
                        if info["state"] in ("false", "locked"):
                            rows.append(dict(o, kind="release %+d kHz: %s" % (k, info["state"])))
                        self.cl.ctrl(loop_hold=1)
                    for r in rows:
                        r.update(mhz=mhz, dsa=dsa, a_leg=a)
                        out["rows"].append(r)
                        print("%d DSA %5.2f %-26s %-8s CMP_I %5d win %5d |dI| %.3f |dQ| %.3f LOG_Q %.3f PEAK_Q %.3f VC %.3f" % (
                            mhz, dsa, r["kind"], r["state"], r["edges"]["CMP_I"], sum(r["edges"].values()) - r["edges"]["CMP_I"],
                            abs(r["di"]), abs(r["dq"]), r["log_q"], r["peak_q"], r["vc"]), flush=True)
                save("detect_partial", out)
        finally:
            self.done("detect", out, "what tells locked from false-locked, beating and no signal")
        return out

    # ---- dropouts ----
    def drop(self, durs=(1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.03, 0.1, 0.3, 1.0), reps=5):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                for dd in (0, 6):
                    dsa = min(31.75, reg + dd)
                    lk = self.lock_at(mhz, dsa, fresh=(dd == 0))
                    if lk is None:
                        continue
                    cen, side, a, _ = lk
                    for hold in (0, 1):
                        for T in durs:
                            res = {"locked": 0, "slipped": 0, "lost": 0}
                            for _ in range(reps):
                                o0 = self.observe(cen, a)
                                if o0["state"] != "locked":
                                    lk = self.acquire0(mhz, dsa, cen)
                                    if lk is None:
                                        break
                                    o0 = self.observe(cen, a)
                                clk = max(1, int(T / self.cl.t_clk))
                                self.seq_once([(int(1e-3 / self.cl.t_clk), {"tx_dis": 0, "loop_hold": 0, "tr_a": 1}),
                                               (clk, {"tx_dis": 1, "loop_hold": hold, "tr_a": 1}),
                                               (int(1e-3 / self.cl.t_clk), {"tx_dis": 0, "loop_hold": 0, "tr_a": 1})])
                                self.cl.ctrl(tx_dis=0, loop_hold=0)
                                time.sleep(0.3)
                                o = self.observe(cen, a, side0=o0["side"])
                                res["locked" if o["state"] == "locked" else ("slipped" if o["state"] == "slipped" else "lost")] += 1
                            row = {"mhz": mhz, "dsa": dsa, "a_leg": a, "hold": hold, "dur_s": T, **res}
                            out["rows"].append(row)
                            print("%d DSA %5.2f %s dropout %8.6f s: same %d slipped %d lost %d" % (
                                mhz, dsa, "held " if hold else "free ", T, res["locked"], res["slipped"], res["lost"]), flush=True)
                    save("drop_partial", out)
        finally:
            self.done("drop", out, "dropouts (the TX muted by the sequencer, 1 us - 1 s), the loop free or held")
        return out

    # ---- fades ----
    def fade(self, depths=(3, 6, 10, 15, 20, 25), durs=(0.01, 0.1, 1.0), reps=3):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                lk = self.lock_at(mhz, reg, fresh=True)
                if lk is None:
                    continue
                cen, side, a, _ = lk
                for depth in depths:
                    for T in durs:
                        res = {"locked": 0, "slipped": 0, "lost": 0}
                        for _ in range(reps):
                            o0 = self.observe(cen, a)
                            if o0["state"] != "locked":
                                if self.acquire0(mhz, reg, cen) is None:
                                    break
                                o0 = self.observe(cen, a)
                            self.cl.dsa(float(min(31.75, reg + depth)))
                            time.sleep(T)
                            self.cl.dsa(float(reg))
                            time.sleep(0.3)
                            o = self.observe(cen, a, side0=o0["side"])
                            res["locked" if o["state"] == "locked" else ("slipped" if o["state"] == "slipped" else "lost")] += 1
                        row = {"mhz": mhz, "dsa": reg, "a_leg": a, "depth_db": depth, "to_dsa": min(31.75, reg + depth), "dur_s": T, **res}
                        out["rows"].append(row)
                        print("%d fade %2d dB (to DSA %5.2f) for %5.2f s: same %d slipped %d lost %d" % (
                            mhz, depth, row["to_dsa"], T, res["locked"], res["slipped"], res["lost"]), flush=True)
                save("fade_partial", out)
        finally:
            self.done("fade", out, "fades: the DSA stepped 3-25 dB for 10 ms - 1 s and back")
        return out

    # ---- a CW interferer stronger than the pilot ----
    def pilot_lock(self, mhz, dsa, rho, cen):
        self.set_null(mhz, pilot=rho)
        self.cl.hold_point(0, 0)
        lk = self.acquire0(mhz, dsa, cen)
        return lk

    def cw(self, mhz=5000, dsa=17.0, rhos=(0.5, 0.35, 0.25), periods=(2, 5, 10, 25, 100, 250, 1000, 2500),
           run_s=1.0, reps=3):
        cl = self.cl
        out = {"mhz": mhz, "dsa": dsa, "steady": [], "bursts": []}
        self.scope_iq(vdiv=0.1)
        try:
            self.tx(False)
            self.center(mhz)
            cen = self.centres()
            pts = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            for rho in rhos:
                lk = self.pilot_lock(mhz, dsa, rho, cen)
                if lk is None:
                    out["steady"].append({"rho": rho, "error": "no pilot lock"})
                    print("rho %.2f: no lock on the pilot" % rho, flush=True)
                    continue
                ap = abs(lk["frame"]["di"])
                print("rho %.2f (C/I %+.1f dB): locked on the pilot, its leg %.3f V" % (rho, 20 * math.log10(rho), ap), flush=True)
                for p in periods:
                    for back in (False, True):
                        res = {"locked": 0, "slipped": 0, "lost": 0, "dq_during": [], "di_during": []}
                        for _ in range(reps):
                            o0 = self.observe(cen, ap)
                            if o0["state"] != "locked":
                                if self.pilot_lock(mhz, dsa, rho, cen) is None:
                                    break
                                o0 = self.observe(cen, ap)
                            cl.tx_points(point_code(0, 0), [point_code(i, q) for i, q in (pts if not back else pts[::-1])])
                            cl.events(period=p, width=p, count=0, n=4, source="count")
                            cl.tx_go()
                            time.sleep(0.3)
                            res["dq_during"].append(cl.adc("Q") - cen["adc_q0"])
                            res["di_during"].append(cl.adc("I") - cen["adc_i0"])
                            time.sleep(max(0.0, run_s - 0.3))
                            cl.tx_stop()
                            cl.hold_point(0, 0)
                            time.sleep(0.3)
                            o = self.observe(cen, ap, side0=o0["side"])
                            res["locked" if o["state"] == "locked" else ("slipped" if o["state"] == "slipped" else "lost")] += 1
                        f_off = 100e6 / (4 * p) * (-1 if back else 1)
                        row = {"rho": rho, "ci_db": 20 * math.log10(rho), "period": p, "f_off_hz": f_off, "a_pilot": ap, **res}
                        out["steady"].append(row)
                        print("  interferer %+9.0f Hz, I/C %+.1f dB, %.0f s: same %d slipped %d lost %d; during: dI %s dQ %s" % (
                            f_off, -20 * math.log10(rho), run_s, res["locked"], res["slipped"], res["lost"],
                            ["%+.3f" % x for x in res["di_during"]], ["%+.3f" % x for x in res["dq_during"]]), flush=True)
                save("cw_partial", out)
            # bursts: the interferer gated by the sequencer (on T_on, off T_off, repeated), the loop free or held in them
            rho = rhos[1] if len(rhos) > 1 else rhos[0]
            for p in (5, 100, 1000):
                for t_on, t_off in ((1e-4, 1e-3), (1e-3, 4e-3), (5e-3, 5e-3)):
                    for hold in (0, 1):
                        res = {"locked": 0, "slipped": 0, "lost": 0}
                        for _ in range(reps):
                            lk = None
                            o0 = None
                            for _try in range(2):
                                o0 = self.observe(cen, 0.01) if o0 is None else o0
                                lk = self.pilot_lock(mhz, dsa, rho, cen)
                                if lk:
                                    break
                            if not lk:
                                break
                            ap = abs(lk["frame"]["di"])
                            o0 = self.observe(cen, ap)
                            cl.tx_points(point_code(0, 0), [point_code(i, q) for i, q in pts])
                            cl.events(period=p, width=p, count=0, n=4, source="count", gated=True)
                            cl.seq_program([(int(t_on / cl.t_clk), {"tx_gate": 1, "loop_hold": hold, "tx_dis": 0, "tr_a": 1}),
                                            (int(t_off / cl.t_clk), {"tx_gate": 0, "loop_hold": 0, "tx_dis": 0, "tr_a": 1})], loop=True)
                            cl.tx_go()
                            cl.seq_run()
                            time.sleep(run_s)
                            cl.seq_stop()
                            cl.tx_stop()
                            cl.hold_point(0, 0)
                            cl.ctrl(loop_hold=0, tx_dis=0)
                            time.sleep(0.3)
                            o = self.observe(cen, ap, side0=o0["side"])
                            res["locked" if o["state"] == "locked" else ("slipped" if o["state"] == "slipped" else "lost")] += 1
                        row = {"rho": rho, "period": p, "f_off_hz": 100e6 / (4 * p), "t_on": t_on, "t_off": t_off, "hold": hold, **res}
                        out["bursts"].append(row)
                        print("  bursts %+9.0f Hz, I/C %+.1f dB, %.1f ms on / %.1f ms off, %s: same %d slipped %d lost %d" % (
                            100e6 / (4 * p), -20 * math.log10(rho), t_on * 1e3, t_off * 1e3, "held in them" if hold else "free",
                            res["locked"], res["slipped"], res["lost"]), flush=True)
                save("cw_partial", out)
        finally:
            try:
                cl.seq_stop()
            except Exception:                                    # noqa: BLE001
                pass
            self.done("cw", out, "a CW interferer (the ladder rotating, amplitude a) against a weak pilot (VR, rho a): steady and in bursts, the loop free or held")
        return out

    # ---- the weak end ----
    def slips(self, watch_s=30.0):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                self.lock_at(mhz, reg, fresh=True)
                cen = self._cen[mhz]
                for dsa in [float(x) for x in np.arange(reg, 31.76, 2.0)] + [31.75]:
                    lk = self.acquire0(mhz, dsa, cen)
                    if lk is None:
                        out["rows"].append({"mhz": mhz, "dsa": dsa, "error": "no lock"})
                        print("%d DSA %.2f: no lock" % (mhz, dsa), flush=True)
                        continue
                    a = abs(lk["frame"]["di"])
                    side = lk["side"]
                    t0, n, ev = time.time(), 0, {"slipped": 0, "lost": 0}
                    while time.time() - t0 < watch_s:
                        o = self.observe(cen, a, side0=side, gate_s=0.005)
                        n += 1
                        if o["state"] == "slipped":
                            ev["slipped"] += 1
                            side = o["side"]
                        elif o["state"] != "locked":
                            ev["lost"] += 1
                            lk = self.acquire0(mhz, dsa, cen)
                            if lk is None:
                                break
                            side = lk["side"]
                    row = {"mhz": mhz, "dsa": dsa, "a_leg": a, "watched_s": time.time() - t0, "looks": n, **ev}
                    out["rows"].append(row)
                    print("%d DSA %5.2f leg %.3f V: %.0f s watched (%d looks): slipped %d, lost %d" % (
                        mhz, dsa, a, row["watched_s"], n, ev["slipped"], ev["lost"]), flush=True)
                save("slips_partial", out)
        finally:
            self.done("slips", out, "the weak end: the lock watched 30 s at each DSA")
        return out

    # ---- recovery ----
    def recover_once(self, mhz, dsa, cen, a, budget_s=20.0):
        """firmware-style: hold, centre the integrator, release from above the lock (the unlocked push at 5.0 GHz runs
        VC down), then from below, widening; check the lock each time"""
        t0 = time.time()
        tries = []
        for k in (10, 20, -5, 30, 5, -10, 40):
            if time.time() - t0 > budget_s:
                break
            info = self.trial(mhz, S.V_MID, LT.VC_LOCK + k * 1e3 / self.kv(mhz), dsa)
            o = self.observe(cen, a)
            tries.append({"start_khz": k, "state": info["state"], "obs": o["state"]})
            if info["state"] == "locked" and o["state"] == "locked":
                return {"ok": True, "t_s": time.time() - t0, "tries": tries}
            self.cl.ctrl(loop_hold=1)
        return {"ok": False, "t_s": time.time() - t0, "tries": tries}

    def recover(self, reps=8):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                for dd in (0, 6):
                    dsa = min(31.75, reg + dd)
                    lk = self.lock_at(mhz, dsa, fresh=(dd == 0))
                    if lk is None:
                        continue
                    cen, side, a, _ = lk
                    for kick in (0.1, 0.3, -0.3):
                        for _ in range(reps):
                            o0 = self.observe(cen, a)
                            v0 = self.cl.dac_volts()["VC_OFF"]
                            self.cl.dac(S.DAC1, VC_OFF=float(min(3.2, max(0.1, v0 + kick))))
                            time.sleep(0.5)
                            self.cl.dac(S.DAC1, VC_OFF=float(v0))
                            time.sleep(0.5)
                            o1 = self.observe(cen, a, side0=o0["side"])
                            if o1["state"] == "locked":
                                r = {"ok": True, "t_s": 0.0, "tries": [], "survived": True}
                            else:
                                r = self.recover_once(mhz, dsa, cen, a)
                                r["survived"] = False
                            r.update(mhz=mhz, dsa=dsa, kick_v=kick, kick_khz=kick * self.kv(mhz) / 1e3, after_kick=o1["state"])
                            out["rows"].append(r)
                            print("%d DSA %5.2f kick %+.1f V (%+.0f kHz): after it %s; %s in %.1f s (%d tries)" % (
                                mhz, dsa, kick, r["kick_khz"], o1["state"], "recovered" if r["ok"] else "NOT recovered", r["t_s"],
                                len(r["tries"])), flush=True)
                save("recover_partial", out)
        finally:
            self.done("recover", out, "loss forced by a VC_OFF kick; a firmware-style recovery's time and success")
        return out

    # ---- false locks ----
    def falselock(self, offs=tuple(range(-60, 61, 5))):
        out = {"rows": []}
        self.scope_iq(vdiv=0.1)
        try:
            for mhz in (5000, 5200):
                self.set_null(mhz)
                reg = self.regulated_dsa(mhz)
                for dd in (0, 6):
                    dsa = min(31.75, reg + dd)
                    lk = self.lock_at(mhz, dsa, fresh=(dd == 0))
                    if lk is None:
                        continue
                    cen, side, a, _ = lk
                    for k in offs:
                        if k == 0:
                            continue
                        info = self.trial(mhz, S.V_MID, LT.VC_LOCK + k * 1e3 / self.kv(mhz), dsa)
                        o = self.observe(cen, a)
                        r = {"mhz": mhz, "dsa": dsa, "a_leg": a, "start_khz": k, "trial": info["state"], **o}
                        out["rows"].append(r)
                        print("%d DSA %5.2f from %+3d kHz: %-10s -> %-8s VC %.3f CMP_I %5d |dI| %.3f LOG_Q %.3f PEAK_Q %.3f" % (
                            mhz, dsa, k, info["state"], o["state"], o["vc"], o["edges"]["CMP_I"], abs(o["di"]), o["log_q"],
                            o["peak_q"]), flush=True)
                        self.cl.ctrl(loop_hold=1)
                save("falselock_partial", out)
        finally:
            self.done("falselock", out, "releases from -60 to +60 kHz: where the loop ends and what the detectors say")
        return out

    def done(self, name, out, text):
        try:
            self.cl.seq_stop()
        except Exception:                                        # noqa: BLE001
            pass
        self.restore()
        self.cleanup()
        path = save(name, out)
        self.b.record("verdict", test="locklab_%s" % name, ok=None, file=path, text=text)
        print(path, flush=True)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="+", choices=["detect", "drop", "fade", "cw", "slips", "recover", "falselock"])
    a = ap.parse_args(argv)
    L = Lab()
    for s in a.sections:
        print("==== %s %s" % (s, time.strftime("%H:%M:%S")), flush=True)
        try:
            getattr(L, s)()
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            print("==== %s FAILED: %s" % (s, e), flush=True)
            try:
                L.restore()
                L.cleanup()
            except Exception:                                    # noqa: BLE001
                pass


if __name__ == "__main__":
    main(sys.argv[1:])
