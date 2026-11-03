"""revb38c.py: the third REVB 38 campaign: is the corner error the loop's own motion?  The corners (2 us and 3.5 us wide
in 4 us) measured with the loop free and with the loop HELD (LOOP_HOLD: the phase frozen, so a corner's I x Q cannot
move the VCXO); held, each capture is clustered on its own (five single captures, the loop released between them, so
a held phase's drift cannot smear pooled clusters).  Output: bringup/data/board_A/b210link/revb38c_5200_<stamp>.json
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
            "shares": p["shares"], "spread": p["spread_mv"]}


L = BL.Link()
mhz = 5200
t = time.time()
note = soak.post("/api/note", {"text": "REVB 38 on the B210, third campaign (revb38c.py): the corners with the loop free and "
                                       "held; the board's TX muted, its loop locked to the B210; linkd and the self-test "
                                       "stand by",
                               "kind": "intervention", "source": "revb38c.py", "t_start": t, "t_end": t + 1800,
                               "b210": {"kind": "link", "what": ["revb38c"]}})
out = {"what": "revb38c", "t0": t, "runs": []}
try:
    out["offset"] = L.offset(mhz)
    delta = out["offset"]["delta_hz"]
    L._delta, L._gain = delta, 80
    st = L.lock_ext(mhz, delta, gain=80, rate=4e6)
    if st is None:
        raise SystemExit("no lock to the B210")
    out["lock"] = {k: st[k] for k in ("dsa", "a", "side", "vc")}
    print("lock", out["lock"], flush=True)
    for wid in (2e-6, 3.5e-6):
        for held in (False, True):
            reps = 5 if held else 2
            for k in range(reps):
                if held:
                    L.cl.ctrl(loop_hold=1, tx_dis=1)
                    time.sleep(0.05)
                try:
                    r = L.rx_scope(mhz, st, period_s=4e-6, width_s=wid, tdiv=5e-6, caps=1 if held else 5,
                                   only=["idle", "corners"])
                finally:
                    if held:
                        L.cl.ctrl(loop_hold=0, tx_dis=1)
                        time.sleep(0.4)
                p = r["patterns"].get("corners", {})
                f = phys(p) if "centres_mv" in p else None
                o = L.observe(st["cen"], st["a"])
                row = {"width_s": wid, "held": held, "rep": k, "phys": f, "scope": r,
                       "after": {kk: o[kk] for kk in ("state", "di", "vc")}}
                out["runs"].append(row)
                print("  width %.1f us %-4s rep %d: Q(I<0)/Q(I>0) %s  I(Q>0)/I(Q<0) %s  idle %s  shares %s  spread %s; after %s" % (
                    wid * 1e6, "held" if held else "free", k, f and f["Q_at_Ineg_over_Ipos"], f and f["I_at_Qpos_over_Qneg"],
                    f and f["idle_mv"], f and f["shares"], f and f["spread"], o["state"]), flush=True)
finally:
    try:
        L.cl.ctrl(loop_hold=0, tx_dis=1)
        L.cl.dac(BL.S.DAC2, V_T2=BL.S.V_MID)
        L.restore()
        L.cleanup()
    except Exception as e:                           # noqa: BLE001
        print("restore:", e, flush=True)
    if note.get("id"):
        soak.post("/api/note", {"id": note["id"], "end": True})
    out["t1"] = time.time()
    print(BL.save("revb38c_%d" % mhz, out), flush=True)
