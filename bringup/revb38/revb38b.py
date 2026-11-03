"""revb38b.py: the second REVB 38 campaign (after revb38.py: A and C valid, B's seeds wrong, D's attribute wrong):
  B  the corners 0.5 / 2 / 3.5 us wide in 4 us, and 20 in 40 (the clustering's seeds now follow the width): the loop's
     pull per corner grows with the width, the receiver's own term does not
  D  the B210 +6 dB with the DSA +6 dB (the same leg at the demodulator, the LNA 6 dB hotter), then -6
  E  the I arm's DC shifted with I_OFF_F (DAC2) and the Q arm's with Q_OFF_F (DAC1), the corners measured at each:
     a Q gain that follows I's DC at the arm is the arms' (or their shared reference); one that stays is the
     demodulator's
Everything restored; the DAC codes put back.  Output: bringup/data/board_A/b210link/revb38b_5200_<stamp>.json
"""
import os
import sys
import time

B = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")   # bringup/
sys.path.insert(0, B)
os.chdir(B)
import numpy as np                                   # noqa: E402
import b210link as BL                                # noqa: E402
import soak                                          # noqa: E402
import costaslink as CL                              # noqa: E402

C4 = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def phys(p):
    c = np.array(p["centres_mv"], dtype=float)
    idle, cs = c[0], c[1:]
    m = cs.mean(axis=0)
    rel = cs - m
    Qn = [abs(q) for i, q in rel if i < 0]
    Qp = [abs(q) for i, q in rel if i > 0]
    Ip = [abs(i) for i, q in rel if q > 0]
    In = [abs(i) for i, q in rel if q < 0]
    return {"corners_mv": rel.round(1).tolist(), "idle_mv": (idle - m).round(1).tolist(),
            "Q_at_Ineg_over_Ipos": round(float(np.mean(Qn) / np.mean(Qp)), 4) if Qn and Qp else None,
            "I_at_Qpos_over_Qneg": round(float(np.mean(Ip) / np.mean(In)), 4) if Ip and In else None,
            "shares": p["shares"]}


def say(label, r):
    for name, p in (r.get("patterns") or {}).items():
        if "q_over_i" in p:
            f = phys(p)
            print("  %-16s %-8s Q(I<0)/Q(I>0) %s  I(Q>0)/I(Q<0) %s  idle %s  shares %s" % (
                label, name, f["Q_at_Ineg_over_Ipos"], f["I_at_Qpos_over_Qneg"], f["idle_mv"], f["shares"]), flush=True)
            p["phys"] = f


L = BL.Link()
mhz = 5200
t = time.time()
note = soak.post("/api/note", {"text": "REVB 38 on the B210, second campaign (revb38b.py): the corners' widths, the LNA's "
                                       "level against the demodulator's, the arms' offsets moved; the board's TX muted, "
                                       "its loop locked to the B210; linkd and the self-test stand by",
                               "kind": "intervention", "source": "revb38b.py", "t_start": t, "t_end": t + 2400,
                               "b210": {"kind": "link", "what": ["revb38b"]}})
out = {"what": "revb38b", "t0": t}
try:
    out["offset"] = L.offset(mhz)
    delta = out["offset"]["delta_hz"]
    L._delta, L._gain = delta, 80
    st = L.lock_ext(mhz, delta, gain=80, rate=4e6)
    if st is None:
        raise SystemExit("no lock to the B210")
    out["lock"] = {k: st[k] for k in ("dsa", "a", "side", "vc")}
    print("lock", out["lock"], flush=True)

    # B: the width series
    for name, (per, wid, tdiv) in {"B_w0p5us": (4e-6, 0.5e-6, 5e-6), "B_w2us": (4e-6, 2e-6, 5e-6),
                                   "B_w3p5us": (4e-6, 3.5e-6, 5e-6), "B_w20us": (40e-6, 20e-6, 50e-6)}.items():
        r = L.rx_scope(mhz, st, period_s=per, width_s=wid, tdiv=tdiv, only=["idle", "corners"])
        out[name] = r
        say(name, r)

    # D: the LNA's level against the demodulator's
    d0, g0 = float(st["dsa"]), 80.0
    for dg in (+6.0, -6.0):
        key = "D_lna_%+d" % int(dg)
        if not (6.0 <= d0 + dg <= 31.75):
            out[key] = {"skipped": "DSA %.2f out of range" % (d0 + dg)}
            continue
        L.stream.b.u.set_tx_gain(g0 + dg, 0)
        L.stream.gain = g0 + dg
        L.cl.dsa(d0 + dg)
        time.sleep(0.8)
        o = L.observe(st["cen"], st["a"])
        row = {"gain": g0 + dg, "dsa": d0 + dg, "observe": {k: o[k] for k in ("state", "di", "vc")}}
        print("D %+d dB: B210 gain %.0f, DSA %.2f: %s, leg %.3f" % (dg, g0 + dg, d0 + dg, o["state"], abs(o["di"])), flush=True)
        if o["state"] == "locked":
            r = L.rx_scope(mhz, dict(st, a=abs(o["di"])), only=["idle", "corners"])
            row["scope"] = r
            say(key, r)
        out[key] = row
        L.stream.b.u.set_tx_gain(g0, 0)
        L.stream.gain = g0
        L.cl.dsa(d0)
        time.sleep(0.8)

    # E: the arms' offsets moved (DAC codes; the idle's place on the scope says how far the arm moved)
    codes = {"DAC1": list(L.cl._dac[BL.S.DAC1]), "DAC2": list(L.cl._dac[BL.S.DAC2])}
    out["dac_codes_before"] = codes
    for chan, which, name in (("I_OFF_F", BL.S.DAC2, "DAC2"), ("Q_OFF_F", BL.S.DAC1, "DAC1")):
        idx = (CL.DAC2_CH if name == "DAC2" else CL.DAC1_CH)[chan]
        c0 = codes[name][idx]
        for dc in (-400, +400):
            c1 = max(0, min(4095, c0 + dc))
            L.cl.dac(which, **{"code_" + chan: c1})
            time.sleep(0.5)
            o = L.observe(st["cen"], st["a"])
            key = "E_%s_%+d" % (chan, dc)
            row = {"code": c1, "code0": c0, "observe": {k: o[k] for k in ("state", "di", "vc")}}
            print("E %s code %d (%+d): %s, di %.3f" % (chan, c1, dc, o["state"], o["di"]), flush=True)
            if o["state"] == "locked":
                r = L.rx_scope(mhz, st, only=["idle", "corners"])
                row["scope"] = r
                say(key, r)
            out[key] = row
            L.cl.dac(which, **{"code_" + chan: c0})
            time.sleep(0.5)
finally:
    try:
        for which, name in ((BL.S.DAC1, "DAC1"), (BL.S.DAC2, "DAC2")):
            if "dac_codes_before" in out:
                names = CL.DAC1_CH if name == "DAC1" else CL.DAC2_CH
                L.cl.dac(which, **{"code_" + k: out["dac_codes_before"][name][i] for k, i in names.items()})
        L.cl.dac(BL.S.DAC2, V_T2=BL.S.V_MID)
        L.restore()
        L.cleanup()
    except Exception as e:                           # noqa: BLE001
        print("restore:", e, flush=True)
    if note.get("id"):
        soak.post("/api/note", {"id": note["id"], "end": True})
    out["t1"] = time.time()
    print(BL.save("revb38b_%d" % mhz, out), flush=True)
