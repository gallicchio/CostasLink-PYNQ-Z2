#!/usr/bin/env python3
"""weekend.py: board A over the air, the USRP B210 as interferer, rounds of sweeps repeated until --hours run out
(Jason, 2026-10-30 15:00: "If you have ideas for real sweeps to run of every possible thing that might inform use of
this revA board or modifications for a revB board, do those"; the office's WiFi will be all but absent: the antennas
face a concrete wall).  The bench as ota.py's: four antennas within 30-40 cm, the board's link at 5.2 GHz at DSA ~14,
the B210 reaching -23 to +11 dB of the carrier there (BRINGUP_LOG 4.0).

    python3 bringup/weekend.py baseline           once: the schemes, the BER against the rate, the ring, over the air
    python3 bringup/weekend.py rounds --hours H [--pieces ...] [--first ...]
                                                  repeated: per carrier (5200, 5000, 5500)
        decide    the decisions under interference: CW 0.1 / 1 / 5 / 20 MHz off and 8 MHz noise at 20 / 100 % duty, the
                  B210's gain in steps around the thresholds; at each A3 (20 000 PRBS events: right, wrong, false,
                  missed, confirmed / vetoed with V_T2 2.9 V and the carrier nulled), the BPSK BER at 25 Mbaud in
                  segments, LOG_Q / PEAK_Q, the lock after
        capture   a CW near the carrier (-50..+50 kHz, the B210's own LO leak parked 2 MHz away): the lock during (VC:
                  does the loop go to the interferer?) and after
        pulses    10 us every 1 ms and 100 us every 10 ms at full power: the lock, A3's errors
        pull      a CW 0.1-40 MHz above and below the carrier, gain 74-89.75: is the loop dragged off (VC, the I leg),
                  and does it come back by itself when the CW stops, how fast (added after round 1: BRINGUP_LOG 4.3)
        pullhold  pull's worst cases with the loop held (LOOP_HOLD) through the CW: what an interference hold saves
        pullauto  pull's dragging cases with the gateware's interference hold on (ID version 5)
        iholdcheck the interference hold on through A3's events, BPSK data and quiet: it must not trigger
        segcheck  the BPSK BER's 50 ms segments with nothing sent, each with the lock read before and after
        eye       CMP_I against the TX's own pins during PRBS at 50 and 25 Mbaud: the latency, the eye, the rising and
                  falling edges' places in the symbol; then timing-recovered segments with the recovery's state
                  (BRINGUP_LOG 4.9: at 5.0 GHz some recovered segments read random bits)
        b210cdr   the B210's BPSK at 1 and 2 Mbaud through the board's timing recovery (ID version 4): the BER, and
                  the two clocks' offset round by round (cdr_tests.py)
        quiet     an hour of the lock watched with nothing sent (drift, the board's own stability)

Each piece writes bringup/data/board_A/weekend/<piece>_<mhz>_<time>.json; a verdict per round.  The board is left
muted, held, DSA 31.75, the trims restored between pieces; the B210 silent.
"""
import argparse
import json
import math
import os
import sys
import threading
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ota as O                                      # noqa: E402
import linktests as LT                               # noqa: E402
import stages as S                                   # noqa: E402
from costaslink import point_code                    # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "weekend")
CARRIERS = (5200, 5000, 5500)


def circ_mean(pos, L):
    """the circular mean of places in a symbol of L samples, wrapped into [-L/2, L/2)"""
    if len(pos) == 0:
        return None
    a = np.asarray(pos, dtype=float) * 2 * np.pi / L
    m = math.atan2(np.mean(np.sin(a)), np.mean(np.cos(a))) * L / (2 * np.pi)
    return float((m + L / 2) % L - L / 2)


def eye_fold(c, p, max_lag=400):
    """one capture taken during PRBS BPSK of p clocks a symbol: CMP_I folded against the TX's own I pins (the
    capture reads the ladder pads back sample for sample).  The latency (samples from the pins' readback to CMP_I) is
    the lag of best agreement; the TX's symbol boundary is the phase its transitions share; place 0 is that boundary
    plus the latency.  Returns the eye (per place in the symbol, the fraction of symbols CMP_I reads right), the
    rising and falling edges' histograms over the places and their circular means, and where ber_cdr.v would sample:
    its loop sets the frame's start at the mean of all edges (wrapped) and samples half a symbol later; with the
    rising and falling edges apart it has a second stable point half a symbol away, sampling between them (a
    simulation of ber_cdr.v with the rising edges 6 samples late: 6 of 24 restarts at 50 Mbaud read random bits)"""
    ser = len(c["CMP_I"]) // max(1, len(c["words"]))
    L = p * ser
    v0 = c["valid_from"] * ser
    x = np.array(c["CMP_I"][v0:], dtype=np.int64)
    d = (np.array(c["TX_PINS"][v0:]) & 3 == point_code(1, 0) & 3).astype(np.int64)
    n = len(x)
    if n < 4 * max_lag:
        return {"error": "short capture (%d samples)" % n}
    m = n - max_lag
    xs, ds = 2 * x - 1, 2 * d - 1
    corr = np.array([np.dot(xs[k:k + m], ds[:m]) for k in range(max_lag)]) / m
    lag = int(np.argmax(np.abs(corr)))
    inv = bool(corr[lag] < 0)
    tt = np.nonzero(np.diff(d))[0] + 1
    if len(tt) < 10:
        return {"error": "the TX pins hardly moved (%d transitions)" % len(tt)}
    phi = int(np.argmax(np.bincount(tt % L, minlength=L)))
    starts = np.arange(phi, m - L, L)
    want = (1 - d[starts]) if inv else d[starts]
    eye = [float(np.mean(x[starts + lag + k] == want)) for k in range(L)]
    rt = np.nonzero(np.diff(x))[0] + 1
    rising = x[rt] == 1
    place = (rt - lag - phi) % L
    rise_h = np.bincount(place[rising], minlength=L)
    fall_h = np.bincount(place[~rising], minlength=L)
    mr, mf, ma = circ_mean(place[rising], L), circ_mean(place[~rising], L), circ_mean(place, L)
    true_pt = int(round(ma + L / 2)) % L if ma is not None else None
    false_pt = int(round(ma)) % L if ma is not None else None
    return {"samples": n, "period": p, "L": L, "lag": lag, "inverted": inv, "agreement": float(abs(corr[lag])),
            "tx_phase": phi, "tx_edges": int(len(tt)), "rx_edges": int(len(rt)), "eye": [round(e, 4) for e in eye],
            "open": int(sum(e >= 0.999 for e in eye)), "rise_hist": rise_h.tolist(), "fall_hist": fall_h.tolist(),
            "rise_mean": mr, "fall_mean": mf, "skew": (None if mr is None or mf is None else (mr - mf + L / 2) % L - L / 2),
            "cdr_point": true_pt, "eye_at_cdr": eye[true_pt] if true_pt is not None else None,
            "false_point": false_pt, "eye_at_false": eye[false_pt] if false_pt is not None else None}


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, LT.O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class Weekend(O.OTA):
    def bg(self, fn, *a, **k):
        t = threading.Thread(target=fn, args=a, kwargs=k, daemon=True)
        t.start()
        return t

    def ready(self, mhz):
        """null the carrier, lock with a regulated leg, the windows at 0.5 a, V_T2 2.9 V (3.8g); returns the state"""
        self.set_null(mhz)
        cen, best = self.lock_ota(mhz, target=0.15)
        if best is None:
            return None
        dsa, a, lk = best
        self.thresholds(cen, a, 0.5)
        self.cl.dac(S.DAC2, V_T2=2.9)
        return {"cen": cen, "dsa": dsa, "a": a, "side": lk["side"]}

    def relock(self, mhz, st):
        o = self.observe(st["cen"], st["a"])
        if o["state"] in ("locked", "slipped"):
            st["side"] = o["side"]
            return True
        r = self.recover_once(mhz, st["dsa"], st["cen"], st["a"])
        if r["ok"]:
            st["side"] = self.observe(st["cen"], st["a"])["side"]
        return r["ok"]

    def interferer(self, kind, mhz, x, gain, seconds):
        if kind == "cw":
            return self.bg(self.bb.tone, mhz + x, gain=gain, seconds=seconds)
        on_ms = 1.0 if x < 1 else 5.0
        off_ms = on_ms * (1 - x) / x if x < 1 else 0.0
        return self.bg(self.bb.bursts, mhz, gain=gain, bw_mhz=8.0, on_ms=on_ms, off_ms=off_ms, seconds=seconds)

    # ---- the decisions under interference ----
    def decide(self, mhz, kinds=(("cw", 0.1), ("cw", 1.0), ("cw", 5.0), ("cw", 20.0), ("noise", 0.2), ("noise", 1.0)),
               gains=(0, 60, 65, 70, 72, 74, 76, 78, 80, 83, 86, 89.75)):
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"])
        ph, scan, width = self.best_phase(st["side"], 4, seconds=0.02)
        out["ber_phase"] = ph
        for kind, x in kinds:
            for g in gains:
                if not self.relock(mhz, st):
                    out["runs"].append({"kind": kind, "x": x, "gain": g, "error": "no lock"})
                    break
                th = self.interferer(kind, mhz, x, g, 4.0) if g > 0 else None
                time.sleep(0.5)
                o = self.observe(st["cen"], st["a"], side0=st["side"])
                a3 = self.scheme_run("A3", st["side"], count=20000)
                ber = self.segs(st["side"], 4, ph, n=5, seconds=0.05)
                if th:
                    th.join(timeout=8)
                time.sleep(0.3)
                after = self.observe(st["cen"], st["a"], side0=st["side"])
                row = {"kind": kind, "x": x, "gain": g, "during": o, "after": after,
                       "a3": {k: a3[k] for k in ("events", "decided", "right", "symbol_errors", "false", "missed", "confirm", "veto")},
                       "ber": {k: ber[k] for k in ("clean", "inverted", "beating", "partial", "bits", "err_bits_partial")}}
                out["runs"].append(row)
                print("%d %-5s %5.1f gain %5.2f: LOG_Q %.3f PEAK_Q %.3f | A3 %d sent, %d right, %d wrong, %d false, %d missed, %d confirmed, %d vetoed | BER segs %d clean %d bad | after %s" % (
                    mhz, kind, x, g, o["log_q"], o["peak_q"], a3["events"], a3["right"], a3["symbol_errors"], a3["false"],
                    a3["missed"], a3["confirm"], a3["veto"], ber["clean"], 5 - ber["clean"], after["state"]), flush=True)
                if after["state"] == "slipped":
                    st["side"] = after["side"]
            save("decide_partial", out)
        return out

    # ---- a CW near the carrier ----
    def capture(self, mhz, offs_khz=(-50, -30, -20, -10, -5, -2, 2, 5, 10, 20, 30, 50), gains=(70, 80, 89.75), park_mhz=2.0):
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"])
        vc0 = self.cl.adc("VC")
        for g in gains:
            for k in offs_khz:
                if not self.relock(mhz, st):
                    break
                vc_before = self.cl.adc("VC")
                th = self.bg(self.bb.tone, mhz + park_mhz, gain=g, seconds=3.0, offset_hz=k * 1e3 - park_mhz * 1e6, rate=5e6)
                time.sleep(1.0)
                o = self.observe(st["cen"], st["a"], side0=st["side"])
                vc_during = self.cl.adc("VC")
                th.join(timeout=6)
                time.sleep(0.4)
                after = self.observe(st["cen"], st["a"], side0=st["side"])
                row = {"gain": g, "off_khz": k, "during": o, "after": after, "vc_before": vc_before, "vc_during": vc_during,
                       "dvc_khz": (vc_during - vc_before) * self.kv(mhz) / 1e3}
                out["runs"].append(row)
                print("%d capture CW %+3d kHz gain %5.2f: during %s (VC moved %+.1f kHz, LOG_Q %.3f); after %s" % (
                    mhz, k, g, o["state"], row["dvc_khz"], o["log_q"], after["state"]), flush=True)
                if after["state"] == "slipped":
                    st["side"] = after["side"]
            save("capture_partial", out)
        out["vc0"] = vc0
        return out

    # ---- pulses ----
    def pulses(self, mhz, shapes=((10e-6, 1e-3), (100e-6, 10e-3), (1e-3, 20e-3)), gains=(80, 89.75), reps=3):
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        for t_on, t_per in shapes:
            for g in gains:
                for r in range(reps):
                    if not self.relock(mhz, st):
                        break
                    th = self.bg(self.bb.bursts, mhz, gain=g, bw_mhz=8.0, on_ms=t_on * 1e3, off_ms=(t_per - t_on) * 1e3, seconds=3.0)
                    time.sleep(0.5)
                    o = self.observe(st["cen"], st["a"], side0=st["side"])
                    a3 = self.scheme_run("A3", st["side"], count=20000)
                    th.join(timeout=6)
                    time.sleep(0.3)
                    after = self.observe(st["cen"], st["a"], side0=st["side"])
                    row = {"t_on": t_on, "t_per": t_per, "gain": g, "rep": r, "during": o, "after": after,
                           "a3": {k: a3[k] for k in ("events", "decided", "right", "symbol_errors", "false", "missed", "confirm", "veto")}}
                    out["runs"].append(row)
                    print("%d pulses %4.0f us every %4.1f ms gain %5.2f: PEAK_Q %.3f | A3 %d right, %d wrong, %d false, %d missed | after %s" % (
                        mhz, t_on * 1e6, t_per * 1e3, g, o["peak_q"], a3["right"], a3["symbol_errors"], a3["false"], a3["missed"],
                        after["state"]), flush=True)
                    if after["state"] == "slipped":
                        st["side"] = after["side"]
            save("pulses_partial", out)
        return out

    # ---- the pull: a strong CW above and below the carrier ----
    def pull(self, mhz, offs_mhz=(0.1, 0.3, 1.0, 2.0, 5.0, 10.0, 20.0, 40.0), gains=(74, 77, 80, 83, 86, 89.75), seconds=3.0,
             hold=False, auto=False):
        """the lock during a CW at +-offs_mhz and how it comes back (round 1's decide: a CW 5-20 MHz above at +1..+3 dB
        dragged VC to its rail, and the loop came back by itself, drifting down through the carrier; one dragged below
        would not): VC and the I leg's DC three times during (dragged off: I ~ 0 and VC away from the lock), then after
        the CW the lock polled for 3 s; t_back is the time to locked or slipped, None if it did not come back.  hold: the
        loop held (LOOP_HOLD) from 0.2 s before the CW to 0.2 s after it, a detector that knew (pullhold).  auto: the
        gateware's interference hold on (ID version 5, ihold.v) through the step, its holds counted (pullauto)"""
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"])
        for off in offs_mhz:
            for sgn in (1, -1):
                for g in gains:
                    if not self.relock(mhz, st):
                        out["runs"].append({"off_mhz": sgn * off, "gain": g, "error": "no lock"})
                        break
                    vc0 = self.cl.adc("VC")
                    if auto:
                        self.cl.rx_clear()
                        self.cl.ihold(True)
                    if hold:
                        self.cl.ctrl(loop_hold=1)
                        time.sleep(0.2)
                    th = self.bg(self.bb.tone, mhz + sgn * off, gain=g, seconds=seconds)
                    during = []
                    for _ in range(3):
                        time.sleep(0.6)
                        during.append(self.observe(st["cen"], st["a"], side0=st["side"]))
                    th.join(timeout=seconds + 4)
                    if hold:
                        time.sleep(0.2)
                        self.cl.ctrl(loop_hold=0)
                    t0, polls, t_back = time.time(), [], None
                    while time.time() - t0 < 3.0:
                        o = self.observe(st["cen"], st["a"], side0=st["side"])
                        polls.append((round(time.time() - t0, 3), o["state"], round(o["vc"], 3), round(o["di"], 4)))
                        if o["state"] in ("locked", "slipped"):
                            t_back = time.time() - t0
                            break
                    lost = [abs(d["di"]) < 0.5 * st["a"] for d in during]
                    ih = None
                    if auto:
                        ih = self.cl.ihold_state()
                        self.cl.ihold(False)
                    row = {"off_mhz": sgn * off, "gain": g, "hold": hold, "auto": auto, "ihold": ih, "vc0": vc0, "during": during, "lost_during": lost,
                           "dvc_khz": [(d["vc"] - vc0) * self.kv(mhz) / 1e3 for d in during], "polls": polls, "t_back": t_back,
                           "after": polls[-1][1] if polls else None}
                    out["runs"].append(row)
                    print("%d pull%s CW %+5.2f MHz gain %5.2f: during %s, VC %s kHz | back %s after %s s%s" % (
                        mhz, hold and " (held)" or auto and " (ihold)" or "", sgn * off, g, "/".join("lost" if x else d["state"] for x, d in zip(lost, during)),
                        "/".join("%+.0f" % x for x in row["dvc_khz"]), row["after"], t_back and "%.2f" % t_back,
                        ih and " | ihold: %d holds, %.2f s held" % (ih["holds"], ih["seconds"]) or ""), flush=True)
                    if row["after"] == "slipped":
                        st["side"] = -st["side"]
                    elif row["after"] == "locked":
                        st["side"] = polls[-1][3] > 0 and 1 or -1
                save("pull_partial", out)
        return out

    def pullhold(self, mhz):
        """pull's worst cases with the loop held through the CW: what an interference hold would save"""
        return self.pull(mhz, offs_mhz=(0.05, 1.0, 5.0, 20.0), gains=(80, 86, 89.75), hold=True)

    def pullauto(self, mhz):
        """pull's dragging cases with the gateware's interference hold on (ID version 5): does it catch them?"""
        if not getattr(self.cl, "ihold_ok", False):
            return {"mhz": mhz, "skipped": "this overlay has no interference hold"}
        return self.pull(mhz, offs_mhz=(1.0, 5.0, 10.0, 20.0, 40.0), gains=(80, 83, 86, 89.75), auto=True)

    def iholdcheck(self, mhz):
        """the interference hold must leave the link alone: on through A3's 20 000 events, 25 Mbaud BPSK and 20 s of
        quiet, its holds counted after each (none expected), A3's decisions compared with it off"""
        if not getattr(self.cl, "ihold_ok", False):
            return {"mhz": mhz, "skipped": "this overlay has no interference hold"}
        out = {"mhz": mhz}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        cl = self.cl
        keys = ("events", "decided", "right", "symbol_errors", "false", "missed")
        for on in (False, True):
            self.relock(mhz, st)
            cl.ihold(on)
            a3 = self.scheme_run("A3", st["side"], count=20000)
            out["a3_ihold_%s" % on] = {k: a3[k] for k in keys} | {"ihold": cl.ihold_state() if on else None}
        cl.rx_clear()
        b = self.segs(st["side"], 4, None, n=10, seconds=0.05)
        out["bpsk25"] = {k: b[k] for k in ("clean", "beating", "partial", "inverted", "bits")} | {"ihold": cl.ihold_state()}
        cl.rx_clear()
        time.sleep(20)
        out["quiet20s"] = cl.ihold_state()
        cl.ihold(False)
        print("%d ihold check: A3 off %s | on %s, holds %d | BPSK 25 Mbaud %d of 10 clean, holds %d | 20 s quiet: holds %d" % (
            mhz, {k: out["a3_ihold_False"][k] for k in ("right", "symbol_errors", "missed")},
            {k: out["a3_ihold_True"][k] for k in ("right", "symbol_errors", "missed")}, out["a3_ihold_True"]["ihold"]["holds"],
            out["bpsk25"]["clean"], out["bpsk25"]["ihold"]["holds"], out["quiet20s"]["holds"]), flush=True)
        return out

    # ---- the BPSK segments: why some come back random with nothing sent ----
    def segcheck(self, mhz, n=40, periods=(4, 2, 10)):
        """round 1's decide: at 25 Mbaud a third of the 50 ms segments read r ~ 1/6 (random, or half inverted) with the
        B210 silent and the loop locked; here each segment's rate with the lock (I, Q, VC, CMP_I) read before and after,
        and the phase scan repeated every 10 segments (has the eye moved?)"""
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"])
        for p in periods:
            ph, scan, width = self.best_phase(st["side"], p, seconds=0.02)
            row = {"period": p, "scans": [{"k": 0, "phase": ph, "scan": scan, "open": width}], "segs": []}
            for k in range(n if p == 4 else n // 4):
                if k and k % 10 == 0:
                    ph2, scan2, w2 = self.best_phase(st["side"], p, seconds=0.02)
                    row["scans"].append({"k": k, "phase": ph2, "scan": scan2, "open": w2})
                o0 = self.observe(st["cen"], st["a"], side0=st["side"])
                r = self.ber_once(st["side"], p, ph, 0.05)
                o1 = self.observe(st["cen"], st["a"], side0=st["side"])
                b, e = r["bits"] or 0, r["mismatches"] or 0
                row["segs"].append({"rate": e / 3.0 / b if b else None, "bits": b, "mism": e,
                                    "before": {x: o0[x] for x in ("state", "side", "di", "dq", "vc")} | {"cmp_i": o0["edges"]["CMP_I"]},
                                    "after": {x: o1[x] for x in ("state", "side", "di", "dq", "vc")} | {"cmp_i": o1["edges"]["CMP_I"]}})
                if o1["state"] == "slipped":
                    st["side"] = o1["side"]
            rates = [s["rate"] for s in row["segs"]]
            out["runs"].append(row)
            print("%d segcheck %.0f Mbaud at phase %d (open %d of %d; later phases %s): rates %s" % (
                mhz, 100.0 / p, ph, width, 8 * p, [s["phase"] for s in row["scans"][1:]],
                " ".join("0" if x == 0 else "%.3f" % x for x in rates)), flush=True)
            save("segcheck_partial", out)
        return out

    def eye(self, mhz, periods=(2, 4), caps=3, n_cdr=10):
        """BRINGUP_LOG 4.9: at 5.0 GHz some timing-recovered 25 / 50 Mbaud segments read exactly half their bits
        wrong, the loop unmoved.  Here CMP_I against the TX's own pins during PRBS15 BPSK (eye_fold: the eye, and
        the rising and falling edges apart), then n_cdr recovered segments of 50 ms, each with the recovery's state"""
        out = {"mhz": mhz, "runs": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        out.update(dsa=st["dsa"], a_leg=st["a"])
        cl = self.cl
        depth = cl.cap_info()["depth"]
        for p in periods:
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
            cl.tx_timing(period=p)
            cl.tx_prbs(15)
            cl.tx_mode("prbs", n=2)
            cl.tx_go()
            time.sleep(0.005)
            folds = []
            for _ in range(caps):
                cl.cap_arm("none", post=depth - 16)
                cl.cap_force()
                folds.append(eye_fold(cl.cap_read(timeout=2.0), p))
            cl.tx_stop()
            cl.hold_point(1, 0)
            o = self.observe(st["cen"], st["a"], side0=st["side"])
            segs = []
            for _ in range(n_cdr):
                r = self.ber_once(st["side"], p, 0, 0.05)
                b, e = r["bits"] or 0, r["mismatches"] or 0
                segs.append({"rate": e / 3.0 / b if b else None, "bits": b, "mism": e, "cdr_state": r.get("cdr_state")})
            row = {"period": p, "folds": folds, "lock": {x: o[x] for x in ("state", "side", "di", "dq", "vc")}, "segs": segs}
            out["runs"].append(row)
            f = [x for x in folds if "error" not in x]
            rnd = [s for s in segs if s["rate"] is not None and s["rate"] > 0.1]
            print("%d eye %.0f Mbaud: %s | recovered: %d of %d random (their last edge errors %s samples; the others' %s)" % (
                mhz, 100.0 / p, "; ".join("latency %d, open %d of %d, rise %+.1f fall %+.1f (skew %+.1f samples), eye %.3f at the recovery's point, %.3f at its false one"
                                          % (x["lag"], x["open"], x["L"], x["rise_mean"], x["fall_mean"], x["skew"], x["eye_at_cdr"], x["eye_at_false"]) for x in f[:1])
                or "no capture: %s" % [x.get("error") for x in folds],
                len(rnd), len(segs), [s["cdr_state"]["err_samples"] for s in rnd if s.get("cdr_state")],
                [s["cdr_state"]["err_samples"] for s in segs if s not in rnd and s.get("cdr_state")]), flush=True)
            save("eye_partial", out)
        return out

    # ---- once: the link over the air without interference ----
    def baseline(self):
        out = {"rows": []}
        for mhz in CARRIERS:
            st = self.ready(mhz)
            if st is None:
                out["rows"].append({"mhz": mhz, "error": "no lock"})
                continue
            row = {"mhz": mhz, "dsa": st["dsa"], "a_leg": st["a"], "schemes": {}, "ber": []}
            for name in ("A1", "A1w", "A2", "A3"):
                self.relock(mhz, st)
                s_ = self.scheme_run(name, st["side"], count=20000)
                row["schemes"][name] = {k: s_[k] for k in ("events", "decided", "right", "symbol_errors", "false", "missed",
                                                          "lat_min", "lat_max", "lat_mean", "sample_ns", "confirm", "veto")}
                lat = [s_[k] * s_["sample_ns"] for k in ("lat_min", "lat_mean", "lat_max")] if s_["lat_n"] else None
                print("%d %-3s: %d of %d right, %d wrong, %d false, %d missed; %s ns; confirmed %d vetoed %d" % (
                    mhz, name, s_["right"], s_["events"], s_["symbol_errors"], s_["false"], s_["missed"],
                    lat and "%.1f/%.1f/%.1f" % tuple(lat), s_["confirm"], s_["veto"]), flush=True)
            for p in (1, 2, 4, 10):
                self.relock(mhz, st)
                ph, scan, width = self.best_phase(st["side"], p, seconds=0.02)
                b = self.segs(st["side"], p, ph, n=10, seconds=0.05)
                row["ber"].append({"period": p, "phase": ph, "open": width, **{k: b[k] for k in ("clean", "inverted", "beating", "partial", "bits", "err_bits_partial")}})
                print("%d %5.1f Mbaud: open %d of %d phases; at %d: %d clean of 10 (%.0f errors in %d bits)" % (
                    mhz, 100.0 / p, width, 8 * p, ph, b["clean"], b["err_bits_partial"], b["bits"]), flush=True)
            out["rows"].append(row)
            self.restore()
            save("baseline_partial", out)
        return out

    def piece(self, name, fn, *a, **k):
        print("==== %s %s %s" % (name, a, time.strftime("%H:%M:%S")), flush=True)
        try:
            out = fn(*a, **k)
        except Exception as e:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            out = {"error": str(e)[:300]}
        finally:
            try:
                self.cl.dac(S.DAC2, V_T2=S.V_MID)
                self.restore()
                self.cleanup()
            except Exception:                                    # noqa: BLE001
                pass
        path = save("%s%s" % (name, "_%d" % a[0] if a else ""), out)
        self.b.record("verdict", test="weekend_%s" % name, ok=None, file=path, args=list(a))
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["baseline", "rounds"])
    ap.add_argument("--hours", type=float, default=60.0)
    ap.add_argument("--quiet-min", type=float, default=60.0)
    ap.add_argument("--pieces", nargs="*", default=["decide", "capture", "pulses", "pull", "pullhold", "pullauto", "iholdcheck", "segcheck", "eye",
                                                    "b210cdr"])
    ap.add_argument("--first", nargs="*", default=None, help="pieces run first in round 1 (at each carrier)")
    a = ap.parse_args(argv)
    try:
        import cdr_tests                             # the B210 link's pieces too (b210cdr); its class is a Weekend
        W = cdr_tests.CDR()
    except Exception as e:                           # noqa: BLE001
        print("cdr_tests not available (%s): the weekend's own pieces only" % e, flush=True)
        W = Weekend()
    if a.what == "baseline":
        W.piece("baseline", W.baseline)
        return
    t_end = time.time() + a.hours * 3600
    n = 0
    while time.time() < t_end:
        n += 1
        print("######## round %d %s" % (n, time.strftime("%a %H:%M")), flush=True)
        for mhz in CARRIERS:
            if time.time() > t_end:
                break
            if a.first and n == 1:
                for name in a.first:
                    W.piece(name, getattr(W, name), mhz)
            for name in a.pieces:
                if not (a.first and n == 1 and name in a.first):
                    W.piece(name, getattr(W, name), mhz)
        if time.time() < t_end:
            W.piece("quiet", W.soak, hours=min(a.quiet_min / 60.0, max(0.0, (t_end - time.time()) / 3600)), mhzs=list(CARRIERS),
                    rotate_s=a.quiet_min * 60 / len(CARRIERS))
        W.b.record("verdict", test="weekend_round", ok=None, round=n)
    try:
        W.b.sa_live()
    except Exception:                                            # noqa: BLE001
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
