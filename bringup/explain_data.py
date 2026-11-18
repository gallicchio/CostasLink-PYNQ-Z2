#!/usr/bin/env python3
"""explain_data.py: the numbers behind the loss-of-lock explainer, gathered into one JSON: the model (loopmodel.py)
and the bench's measurements of 2026-10-30 (BRINGUP_LOG 4.3-4.5, explain_tests.py).

    python3 bringup/explain_data.py OUT.json
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import loopmodel as M                                # noqa: E402

D = os.path.join(HERE, "data", "board_A")


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(D, pattern)))
    return json.load(open(fs[-1])) if fs else None


def ic_db(gain):
    """the B210's gain step to interferer over carrier at the board's receiver (BRINGUP_LOG 4.0: -6.4 dB at 70, +3.2
    at 80, +11.4 at 89.75, about 0.96 dB a step between; +-3 dB)"""
    if gain is None:
        return None
    if gain >= 89.7:
        return 11.4
    return round(-6.4 + 0.96 * (gain - 70), 1)


def main(out_path):
    out = {"tau_ns": M.TAU * 1e9}
    # 1. the detector's characteristic
    th = np.linspace(-np.pi, np.pi, 145)
    out["scurve"] = []
    for fb, rdbs in ((0.1e6, (None, -6, 0, 6)), (20e6, (None, -6, 0, 3))):
        for rdb in rdbs:
            r = 0.0 if rdb is None else 10 ** (rdb / 20)
            s = M.S(th, r, fb)
            out["scurve"].append({"fb_mhz": fb / 1e6, "r_db": rdb, "theta_deg": np.round(np.degrees(th), 2).tolist(),
                                  "s": np.round(s, 4).tolist()})
    # 2. restoring force and push against r
    out["forces"] = []
    for fb in (0.1e6, 5e6, 20e6):
        rows = []
        for rdb in np.arange(-12, 18.01, 0.5):
            restore, push, z, _, _ = M.restoring_and_push(10 ** (rdb / 20), fb)
            rows.append([round(float(rdb), 2), round(float(restore), 4), round(float(abs(push)), 4), bool(z)])
        out["forces"].append({"fb_mhz": fb / 1e6, "rows": rows})
    # 3. the drag threshold against the interferer's offset: the model, and the bench
    fbs = np.logspace(np.log10(0.05e6), np.log10(50e6), 40)
    out["threshold_model"] = [[round(float(f / 1e6), 4), M.threshold_db(f)] for f in fbs]
    meas = []
    dec = latest("weekend/decide_5200_*.json")
    if dec:
        a = dec["a_leg"]
        by = {}
        for r in dec["runs"]:
            if r["kind"] != "cw" or "during" not in r:
                continue
            by.setdefault(r["x"], []).append((r["gain"], abs(r["during"]["di"]) < 0.5 * a))
        for x, v in sorted(by.items()):
            g = next((g for g, lost in v if lost), None)
            top = max(gg for gg, _ in v)
            meas.append({"set": "round 1 (CW above, DSA 13.75)", "fb_mhz": x, "side": "above",
                         "db": ic_db(g) if g else ic_db(top), "censored": g is None})
    pull = latest("weekend/pull_5200_*.json")
    if pull:
        by = {}
        for r in pull["runs"]:
            if "lost_during" not in r:
                continue
            by.setdefault(r["off_mhz"], []).append((r["gain"], all(r["lost_during"])))
        for off, v in sorted(by.items()):
            g = next((g for g, lost in v if lost), None)
            top = max(gg for gg, _ in v)
            meas.append({"set": "pull test (DSA 17.75)", "fb_mhz": abs(off), "side": "above" if off > 0 else "below",
                         "db": ic_db(g) if g else ic_db(top), "censored": g is None})
    out["threshold_meas"] = meas
    # 4. the drag in time
    drag = latest("explain/explain_drag_*.json") or latest("explain/explain_drag_partial_*.json")
    if drag:
        kv = drag["kv_hz_per_v"]
        out["drag"] = []
        for r in drag["runs"]:
            if "rows" not in r:
                continue
            vc0 = np.median([x[1] for x in r["rows"][:20]])
            out["drag"].append({"off_mhz": r["off_mhz"], "gain": r["gain"], "ic_db": ic_db(r["gain"]), "hold": r["hold"],
                                "t_cw": round(r["t_cw"], 3), "cw_s": r["cw_s"], "t_release": r["t_release"],
                                "after": r["after"]["state"],
                                "t": [round(x[0], 3) for x in r["rows"]],
                                "khz": [round((x[1] - vc0) * kv / 1e3, 1) for x in r["rows"]]})
    # 5. the restoring force measured: the largest sudden step survived
    po = latest("explain/explain_pullout_*.json") or latest("explain/explain_pullout_partial_*.json")
    if po:
        out["pullout"] = [{"gain": r["gain"], "ic_db": ic_db(r["gain"]), "plus": r["held_khz"].get("+"),
                           "minus": r["held_khz"].get("-")} for r in po["rows"] if "held_khz" in r]
        restore0, _, _, _, _ = M.restoring_and_push(0.0, 1e6)
        out["pullout_model"] = [[round(float(rdb), 2), round(float(M.restoring_and_push(10 ** (rdb / 20), 1e6)[0] / restore0), 4)]
                                for rdb in np.arange(-12, 13.01, 0.5)]
    # 6. the hold
    ph = latest("weekend/pullhold_5200_*.json")
    if ph and pull:
        dragged = [r for r in pull["runs"] if r.get("lost_during") and all(r["lost_during"])]
        out["hold"] = {"free_dragged": len(dragged), "free_back": sum(1 for r in dragged if r.get("t_back") is not None),
                       "held": len(ph["runs"]), "held_back": sum(1 for r in ph["runs"] if r.get("t_back") is not None),
                       "held_slipped": sum(1 for r in ph["runs"] if r.get("after") == "slipped"),
                       "held_t_back_max": max((r["t_back"] for r in ph["runs"] if r.get("t_back")), default=None)}
    with open(out_path, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(out_path, os.path.getsize(out_path), "bytes")
    for k in ("threshold_meas", "pullout", "hold"):
        print(k, json.dumps(out.get(k))[:600])


if __name__ == "__main__":
    main(sys.argv[1])
