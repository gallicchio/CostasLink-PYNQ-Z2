"""revb38_analyze.py FILE.json: the corner error (REVB 38) across revb38.py's series, one table per question"""
import json
import sys

import numpy as np

d = json.load(open(sys.argv[1]))
print("lock", d.get("lock"), "offset", {k: d["offset"].get(k) for k in ("delta_hz", "ppm")} if d.get("offset") else None)


def corner_row(p, nominal):
    """from an rx_scope corner pattern: the asymmetry numbers.  nominal: the corners' amplitude as sent, in units of
    the idle (1.41 for the corners, 0.71 'small', ...)"""
    I, Q = np.array(p["corner_i_mv"]), np.array(p["corner_q_mv"])
    deg = np.array(p["corner_deg"])
    want = np.array([45.0, -45.0, 135.0, -135.0])
    ddeg = ((deg - want + 180) % 360) - 180
    # the corners as sent: (+,+), (+,-), (-,+), (-,-)
    r = np.hypot(I, Q)
    idle_r = p.get("idle_over_corner_i")
    return {
        "|I| mV": I.round(1).tolist(), "|Q| mV": Q.round(1).tolist(),
        "Q(+I)/Q(-I)": round(float((Q[0] + Q[1]) / (Q[2] + Q[3])), 4),
        "I(+Q)/I(-Q)": round(float((I[0] + I[2]) / (I[1] + I[3])), 4),
        "Q/I": p["q_over_i"], "deg off": ddeg.round(1).tolist(),
        "radius mV": r.round(1).tolist(), "radius/mean": (r / r.mean()).round(3).tolist(),
        "idle/|I|": idle_r, "shares": p["shares"], "spread mV": p["spread_mv"],
        "centres": p["centres_mv"],
    }


def scope_block(label, res, nominal_of):
    if not res or "patterns" not in res:
        print(label, "missing")
        return
    pats = res["patterns"]
    print("\n== %s (period %s, width %s; a = %.1f mV, side %s)" % (label, res.get("period_s"), res.get("width_s"),
                                                                1e3 * res.get("a", 0), res.get("side")))
    idle = pats.get("idle", {}).get("centres_mv")
    print("  idle at", idle)
    for name, p in pats.items():
        if "q_over_i" not in p:
            continue
        row = corner_row(p, nominal_of.get(name))
        print("  %-8s nominal %s x idle:" % (name, nominal_of.get(name)))
        for k, v in row.items():
            print("     %-12s %s" % (k, v))


NOM = {"corners": 1.41, "small": 0.71, "quarter": 0.35, "eighth": 0.18}
scope_block("A: amplitude series, 2 us", d.get("A_amplitude"), NOM)
for k in ("B_w0p5us", "B_w3p5us", "B_w20us"):
    scope_block("B: " + k, d.get(k), NOM)
for k in ("D_lna_+6", "D_lna_-6"):
    r = d.get(k)
    if not r:
        continue
    if "scope" in r:
        print("\n(D %s: B210 gain %s, DSA %s, observed %s)" % (k, r["gain"], r["dsa"], r["observe"]))
        scope_block("D: " + k, r["scope"], NOM)
    else:
        print("\n== D:", k, r)

# C: the comparators' plateaus: each window's duty steps per pattern (level in mV from the centre, share)
C = d.get("C_rxcal")
if C:
    print("\n== C: the comparators' plateaus (rxcal; levels in mV from each window's centre, x share of time)")
    for name, p in C.get("patterns", {}).items():
        if "steps_mv" not in p:
            print("  %-8s %s" % (name, p))
            continue
        print("  %-8s states %s; lock after: %s" % (name, p["states"], p["lock_after"].get("state")))
        for w in ("QP", "QN", "IP", "IN"):
            st = p["steps_mv"].get(w, [])
            print("     %s: %s" % (w, "  ".join("%+.1f x%.2f" % (m, h) for m, h in st)))

# the one-line verdicts
print("\n== across the series: Q(+I)/Q(-I) and the mean radius / nominal")
rows = []
for label, res in [("A corners 1.41", d.get("A_amplitude")), ]:
    pass
for blk, key in (("A", "A_amplitude"), ("B0.5", "B_w0p5us"), ("B3.5", "B_w3p5us"), ("B20", "B_w20us")):
    res = d.get(key)
    if not res:
        continue
    for name, p in res["patterns"].items():
        if "q_over_i" in p:
            I, Q = np.array(p["corner_i_mv"]), np.array(p["corner_q_mv"])
            rows.append((blk, name, NOM.get(name), round(float((Q[0] + Q[1]) / (Q[2] + Q[3])), 3),
                         round(float((I[0] + I[2]) / (I[1] + I[3])), 3), p["q_over_i"],
                         round(float(np.hypot(I, Q).mean() / (NOM.get(name, 1) * 1e3 * res["a"])), 3) if NOM.get(name) else None))
for k in ("D_lna_+6", "D_lna_-6"):
    r = d.get(k) or {}
    if "scope" in r:
        p = r["scope"]["patterns"].get("corners", {})
        if "q_over_i" in p:
            I, Q = np.array(p["corner_i_mv"]), np.array(p["corner_q_mv"])
            rows.append((k, "corners", 1.41, round(float((Q[0] + Q[1]) / (Q[2] + Q[3])), 3),
                         round(float((I[0] + I[2]) / (I[1] + I[3])), 3), p["q_over_i"], None))
print("  %-8s %-8s %-7s %-12s %-12s %-7s %s" % ("series", "pattern", "nominal", "Q(+I)/Q(-I)", "I(+Q)/I(-Q)", "Q/I", "radius/nominal"))
for r in rows:
    print("  %-8s %-8s %-7s %-12s %-12s %-7s %s" % r)
