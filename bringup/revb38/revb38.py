"""revb38.py: where the receiver's corner error lives (REVB 38: with the B210 sending exact states, Q 7-15 % smaller on
the idle's side of I, the corners not symmetric about their centre), with what the bench can vary from here, the B210
cabled as for 4.31 (its antenna beside the board's; the board's TX muted and its loop locked to the B210):

  A  the corners at 1.41, 0.71, 0.35 and 0.18 of the idle's amplitude (scope): an error that is a fixed fraction is
     geometric; one that grows with amplitude is a nonlinearity; one that shrinks is an offset
  B  the corners 0.5, 2, 3.5 us wide in a 4 us period, and 20 us wide in 40 (scope): the share of transition samples
     in the clusters, and the loop's pull per corner, both change with the width; the receiver's own error does not
  C  the same at three amplitudes on the comparators' plateaus (rxcal: duty steps, no transitions, no scope)
  D  the LNA's level against the demodulator's: the B210 +6 dB and the DSA +6 dB (the same leg at the demodulator,
     the LNA 6 dB hotter), then -6: an error that follows the LNA's level is the RF chain's

Everything is restored after.  Output: bringup/data/board_A/b210link/revb38_5200_<stamp>.json
"""
import json
import os
import sys
import time

B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")   # bringup/
sys.path.insert(0, B)
os.chdir(B)
import numpy as np                                   # noqa: E402
import b210link as BL                                # noqa: E402
import soak                                          # noqa: E402

C4 = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def scaled(s):
    return [(s * a, s * b) for a, b in C4]


def summary(label, r):
    """the corner rows of an rx_scope result in one line each"""
    for name, p in (r.get("patterns") or {}).items():
        if "q_over_i" in p:
            qi = p["corner_q_mv"]
            print("  %-14s %-9s |I| %s |Q| %s  Q/I %.3f  deg %s  Q(+I)/Q(-I) %.3f  shares %s" % (
                label, name, p["corner_i_mv"], qi, p["q_over_i"], p["corner_deg"],
                (qi[0] + qi[1]) / (qi[2] + qi[3]), p["shares"]), flush=True)


L = BL.Link()
mhz = 5200
t = time.time()
note = soak.post("/api/note", {"text": "REVB 38 on the B210 (revb38.py): the board's loop held, its TX muted and the board "
                                       "locked to the B210's exact states at several amplitudes, widths and levels; "
                                       "linkd and the self-test stand by",
                               "kind": "intervention", "source": "revb38.py", "t_start": t, "t_end": t + 2400,
                               "b210": {"kind": "link", "what": ["revb38"]}})
out = {"what": "revb38", "t0": t}
try:
    out["offset"] = L.offset(mhz)
    delta = out["offset"]["delta_hz"]
    L._delta, L._gain = delta, 80
    st = L.lock_ext(mhz, delta, gain=80, rate=4e6)
    if st is None:
        raise SystemExit("no lock to the B210")
    out["lock"] = {k: st[k] for k in ("dsa", "a", "side", "vc")}
    print("lock", out["lock"], flush=True)

    # A: the amplitude series, 2 us wide
    r = L.rx_scope(mhz, st, only=["idle", "corners", "small"],
                   extra={"quarter": (scaled(0.25), 1), "eighth": (scaled(0.125), 1)})
    out["A_amplitude"] = r
    summary("A 2us", r)

    # B: the width series (the transition share, the loop's pull per corner)
    for name, (per, wid, tdiv) in {"B_w0p5us": (4e-6, 0.5e-6, 5e-6), "B_w3p5us": (4e-6, 3.5e-6, 5e-6),
                                   "B_w20us": (40e-6, 20e-6, 50e-6)}.items():
        r = L.rx_scope(mhz, st, period_s=per, width_s=wid, tdiv=tdiv, only=["idle", "corners"])
        out[name] = r
        summary(name, r)

    # C: the comparators' plateaus at three amplitudes (and the axes and the flip as before)
    L.RX_PATTERNS = {"corners": C4, "small": scaled(0.5), "quarter": scaled(0.25), "axes": [(0, 1), (0, -1)],
                     "flip": [(-1, 0)]}
    out["C_rxcal"] = L.rx_accuracy(mhz, st)

    # D: the LNA's level against the demodulator's
    d0, g0 = float(st["dsa"]), 80.0
    for dg in (+6.0, -6.0):
        if not (6.0 <= d0 + dg <= 31.75):
            out["D_lna_%+d" % int(dg)] = {"skipped": "DSA %.2f out of range" % (d0 + dg)}
            continue
        L.stream.u.set_tx_gain(g0 + dg, 0)
        L.stream.gain = g0 + dg
        L.cl.dsa(d0 + dg)
        time.sleep(0.8)
        o = L.observe(st["cen"], st["a"])
        row = {"gain": g0 + dg, "dsa": d0 + dg, "observe": {k: o[k] for k in ("state", "di", "vc")}}
        print("D %+d dB: B210 gain %.0f, DSA %.2f: %s, leg %.3f" % (dg, g0 + dg, d0 + dg, o["state"], abs(o["di"])), flush=True)
        if o["state"] == "locked":
            r = L.rx_scope(mhz, dict(st, a=abs(o["di"])), only=["idle", "corners"])
            row["scope"] = r
            summary("D %+d dB" % int(dg), r)
        out["D_lna_%+d" % int(dg)] = row
        L.stream.u.set_tx_gain(g0, 0)
        L.stream.gain = g0
        L.cl.dsa(d0)
        time.sleep(0.8)
finally:
    try:
        L.cl.dac(BL.S.DAC2, V_T2=BL.S.V_MID)
        L.restore()
        L.cleanup()
    except Exception as e:                           # noqa: BLE001
        print("restore:", e, flush=True)
    if note.get("id"):
        soak.post("/api/note", {"id": note["id"], "end": True})
    out["t1"] = time.time()
    print(BL.save("revb38_%d" % mhz, out), flush=True)
