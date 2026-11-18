"""The driven null (REVB 66, BRINGUP_LOG 4.73 / 4.82): the VR_Q offset from each board's zero-ladder null that takes the
quadrature out of its carrier when its I ladder is driven, measured over the SMA cables (40 dB pads, no antennas) on
the receiving board's scope, per board and per centre frequency.

Per (frequency, link): the link up (linkd's search), the receiver's scope on its I MON / Q MON / CMP I MON triggered by
the sender's TRIG A (twoscope.py's cabling); at the lock's level and at a level 9 dB stronger (the leg about 2.8 x), the
sender's VR_Q stepped -45 ... +45 mV from the zero-ladder null (the FPV-antenna null table) with the idle (1, 0) held
and A1's flip (-1, 0) sent 1-in-1000 for 200 ns: the flip's Q plateau (60-180 ns after CMP I's edge) per step.  Fitted
as Q = 2 x (the receiver's offset) + k(d) x leg with k linear in d: the sender's term's zero d* is the driven null.
Then at the lock's level the whole 3 x 3 ladder constellation on the scope (the eight points from the idle) and A3 by
the decoder (events_point: windows, gaps, the right fraction), once at the zero-ladder null and once at the driven null.
Records data/twoboard/drivennull_<stamp>.json / .npz / .jsonl; the boards quiet and the sender's VR back at the end.

    python3 drivennull.py [--mhz 4800 5000 5200 5400] [--links AB BA] [--shots 5] [--steps -45 -30 -15 0 15 30 45]
"""
import json
import os
import sys
import time

import numpy as np

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import costaslink as C                                    # noqa: E402
import scope_e                                            # noqa: E402
import twoscope as TS                                     # noqa: E402

LAT_NS = {"AB": 5.8, "BA": 10.0}                          # the mark to CMP I over the cables (4.82): t0 when CMP I does not move
POINTS = [(-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1), (0, 0)]   # the ladder's 3 x 3 grid from the idle (1, 0)
VR_CEIL = 0.55


def args_list(name, default, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name) + 1
    out = []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(cast(sys.argv[i]))
        i += 1
    return out


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def flip_shot(L, rs, nshots, keeper, lat, base, **meta):
    """the flip (-1, 0) as 1-in-1000 events of 200 ns, nshots on the receiver's scope: the medians of shot_numbers"""
    L.events_on((-1, 0), 20, 1000, idle=(1, 0))
    time.sleep(0.05)
    got = TS.shots(rs, 1, TS.MARK_V, "rising", nshots, (1, 2, 3, 4))
    L.events_off()
    L.hold((1, 0))
    rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
    nums = [TS.shot_numbers(g, base, lat) for g in got]
    keeper.keep(got, point=[-1, 0], base=base, **meta)
    r = {"n": len(got)}
    for k in ("i_plateau", "q_plateau", "q_spike_min", "q_spike_max", "q_ret_min", "q_ret_max", "i_rise", "cmp_edge_t", "mark_t", "i_pre", "q_pre"):
        r[k] = TS.med(nums, k)
    return r


def point_shot(L, rs, pt, nshots, keeper, lat, base, **meta):
    L.events_on(pt, 20, 1000, idle=(1, 0))
    time.sleep(0.05)
    got = TS.shots(rs, 1, TS.MARK_V, "rising", nshots, (1, 2, 3, 4))
    L.events_off()
    L.hold((1, 0))
    rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
    nums = [TS.shot_numbers(g, base, lat) for g in got]
    keeper.keep(got, point=list(pt), base=base, **meta)
    r = {"point": list(pt), "n": len(got), "rx_point": [pt[0], pt[1]]}
    for k in ("i_plateau", "q_plateau", "i_spike_min", "i_spike_max", "q_spike_min", "q_spike_max", "i_ret_min", "i_ret_max",
              "q_ret_min", "q_ret_max", "i_cross_t", "q_cross_t", "i_rise", "q_rise", "cmp_edge_t"):
        r[k] = TS.med(nums, k)
    r["cmp_moved"] = sum(1 for x in nums if x["cmp_edge_t"] is not None)
    return r


def linfit(xs, ys):
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    if len(xs) < 2:
        return None, None
    m, b = np.polyfit(xs, ys, 1)
    return float(m), float(b)


def scan(L, rs, vq0, vi0, steps, nshots, keeper, lat, dsa, log, mhz):
    """the flip's Q plateau against the sender's VR_Q offset at one level"""
    L.rx.cl.dsa(dsa)
    time.sleep(0.05)
    side = L.recheck_side()
    if side is None:
        T.say("   DSA %.2f: nothing locked at this level" % dsa)
        return {"dsa": dsa, "locked": False, "rows": []}
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    b = TS.centre(rs)
    out = {"dsa": dsa, "locked": True, "side": side, "leg_mv": 1e3 * leg, "rows": []}
    for d in steps:
        vq = vq0 + d / 1e3
        if not (0.0 <= vq <= VR_CEIL):
            continue
        L.tx.cl.dac(VR_I=vi0, VR_Q=vq)
        L.hold((1, 0))
        time.sleep(0.1)
        s2 = L.recheck_side()
        if s2 is None:
            T.say("   d %+d mV: the lock went; skipped" % d)
            continue
        if s2 != side:
            side = s2
            T.say("   d %+d mV: the side changed to %+d" % (d, side))
        bb = TS.scope_dc(rs, (2, 3))
        base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
        r = flip_shot(L, rs, nshots, keeper, lat, base, stage="scan", link=L.name, mhz=mhz, dsa=dsa, d_mv=d, vr_q=vq, leg=leg, side=side)
        r.update(d_mv=d, vr_q=round(vq, 4), side=side, leg_mv=1e3 * leg)
        r["q_frac"] = (r["q_plateau"] or 0) / (1e3 * leg)
        out["rows"].append(r)
        T.say("   DSA %5.2f leg %4.0f mV side %+d VR_Q %+3d mV (%.4f V): flip I %+5.0f, Q plateau %+5.0f mV (%+.3f of the leg), spike %+.0f/%+.0f, return %+.0f/%+.0f" % (
            dsa, 1e3 * leg, side, d, vq, r["i_plateau"] or 0, r["q_plateau"] or 0, r["q_frac"], r["q_spike_min"] or 0, r["q_spike_max"] or 0,
            r["q_ret_min"] or 0, r["q_ret_max"] or 0))
        log(label="drivennull scan", tag="scan", state=L.state(), **r)
    L.tx.cl.dac(VR_I=vi0, VR_Q=vq0)
    L.hold((1, 0))
    time.sleep(0.1)
    rows = [r for r in out["rows"] if r["q_plateau"] is not None]
    m, b0 = linfit([r["d_mv"] for r in rows], [r["q_plateau"] for r in rows])
    out["fit"] = {"slope_mv_per_mv": m, "intercept_mv": b0, "zero_mv": (-b0 / m) if m else None}
    if m:
        T.say("   fit at %.0f mV: %.3f mV of Q per mV of VR_Q, %+.1f mV at the null, zero at %+.1f mV" % (1e3 * leg, m, b0, -b0 / m))
    return out


def constellation(L, rs, nshots, keeper, lat, log, mhz, tag):
    """the eight ladder points from the idle (1, 0) on the receiver's scope, and A3 by the decoder"""
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    TS.centre(rs)
    bb = TS.scope_dc(rs, (2, 3))
    base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
    o = L.ld.observe()
    out = {"which": tag, "leg_mv": 1e3 * leg, "side": L.s, "idle": {"di": o["di"], "dq": o["dq"]}, "points": [], "side_changes": []}
    for pt in POINTS:
        # the lock's side before each point (the (0, 0) point, 200 ns of no carrier 1-in-1000, flipped both receivers'
        # loops to the other side at 21:03 / 21:04): a change re-bases the scope on the idle as it now sits
        s_before = L.recheck_side()
        if s_before is None:
            L.ensure()
            s_before = L.s
        if s_before != out["side"] or (out["side_changes"] and out["side_changes"][-1][1] != s_before):
            out["side_changes"].append([list(pt), s_before, "before"])
            T.say("   the side is %+d before %s: re-based" % (s_before, pt))
            TS.set_arms(rs, leg)
            L.hold((1, 0))
            time.sleep(0.1)
            TS.centre(rs)
            bb = TS.scope_dc(rs, (2, 3))
            base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
        r = point_shot(L, rs, pt, nshots, keeper, lat, base, stage="constellation", link=L.name, mhz=mhz, which=tag, leg=leg, side=s_before)
        r["side"] = s_before
        s_after = L.recheck_side()
        r["side_after"] = s_after
        if s_after is not None and s_after != s_before:
            out["side_changes"].append([list(pt), s_after, "after"])
            T.say("   the side changed to %+d during the %s events" % (s_after, pt))
        out["points"].append(r)
        T.say("   %-4s %-8s I %+5.0f Q %+5.0f mV (%.2f, %.2f of the leg), spike I %+.0f/%+.0f Q %+.0f/%+.0f, CMP moved %d/%d" % (
            tag, "(%d,%d)" % tuple(pt), r["i_plateau"] or 0, r["q_plateau"] or 0, (r["i_plateau"] or 0) / (1e3 * leg), (r["q_plateau"] or 0) / (1e3 * leg),
            r["i_spike_min"] or 0, r["i_spike_max"] or 0, r["q_spike_min"] or 0, r["q_spike_max"] or 0, r["cmp_moved"], r["n"]))
    try:
        L.slev = None                                     # the sweep's levels belong to this VR setting
        dec = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A3"))
    except T.LinkDown:
        raise
    except Exception as e:                                # noqa: BLE001
        dec = {"error": repr(e)[:200]}
        L.ensure()
    out["A3"] = {k: dec.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "leg", "gaps_mv", "thresholds", "levels", "error")}
    out["A3"]["dead"] = (dec.get("rx_info") or {}).get("dead_windows")
    if "error" not in dec:
        T.say("   %-4s A3 by the decoder: right %s, idle false %.0f/s, gaps %s, dead %s" % (
            tag, {m: round(r["right_frac"], 4) for m, r in dec["per_msg"].items()}, dec.get("idle_false_per_s") or 0, dec.get("gaps_mv"), out["A3"]["dead"]))
    else:
        T.say("   %-4s A3 by the decoder: %s" % (tag, dec["error"]))
    log(label="drivennull constellation", tag="constellation", state=L.state(), **{k: v for k, v in out.items() if k != "A3"},
        A3={k: v for k, v in out["A3"].items() if k != "levels"})
    L.ensure()
    return out


def main():
    mhzs = args_list("--mhz", [4800.0, 5000.0, 5200.0, 5400.0], float)
    links = args_list("--links", ["AB", "BA"])
    nshots = arg("--shots", 5)
    steps = args_list("--steps", [-45, -30, -15, 0, 15, 30, 45], float)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("drivennull")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "gain": TS.GAIN, "steps_mv": steps, "runs": []}
    t_start = time.time()
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            TS.scope_setup(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for mhz in mhzs:
            for lk in links:
                L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz)
                rs = scopes[L.rx.name]
                rec = {"link": lk, "sender": lk[0], "mhz": mhz}
                out["runs"].append(rec)
                T.say("==== %s at %g MHz, %.0f min in: the sender %s's driven null on receiver %s's scope" % (lk, mhz, (time.time() - t_start) / 60, lk[0], lk[1]))
                try:
                    if not L.up():
                        rec["error"] = "no link"
                        log(label="drivennull setup", tag="setup", state=L.state(), error="no link", **L.info)
                        continue
                    rec["lock"] = dict(L.info, side=L.s)
                    log(label="drivennull setup", tag="setup", state=L.state(), **L.info)
                    L.tx.cl.triggers(width=10, a="tx_event")
                    L.rx.cl.triggers(width=10, a="tx_event")
                    (vi0, vq0), off = L.tx.vr(mhz)
                    rec["null"] = {"vr": [vi0, vq0], "from_mhz": off}
                    lat = LAT_NS.get(lk, 8.0)
                    lock_dsa = L.info.get("dsa", L.rx.cl._dsa_db)
                    rec["scans"] = []
                    for dsa in (lock_dsa, max(0.0, lock_dsa - 9.0)):
                        if rec["scans"] and abs(dsa - rec["scans"][-1]["dsa"]) < 0.1:
                            continue
                        rec["scans"].append(scan(L, rs, vq0, vi0, steps, nshots, keeper, lat, dsa, log, mhz))
                    L.rx.cl.dsa(lock_dsa)
                    time.sleep(0.05)
                    L.recheck_side()
                    # the two-level fit: Q = 2 off + k(d) leg, k linear in d: the sender's zero
                    good = [s for s in rec["scans"] if s.get("locked") and s.get("fit", {}).get("slope_mv_per_mv")]
                    rec["driven"] = None
                    if len(good) >= 2:
                        (s1, s2) = good[0], good[1]
                        l1, l2 = s1["leg_mv"], s2["leg_mv"]
                        ds = sorted(set(r["d_mv"] for r in s1["rows"]) & set(r["d_mv"] for r in s2["rows"]))
                        ks, offs = [], []
                        for d in ds:
                            q1 = next(r["q_plateau"] for r in s1["rows"] if r["d_mv"] == d)
                            q2 = next(r["q_plateau"] for r in s2["rows"] if r["d_mv"] == d)
                            if q1 is None or q2 is None or abs(l2 - l1) < 20:
                                continue
                            k = (q2 - q1) / (l2 - l1)
                            ks.append((d, k))
                            offs.append((q1 - k * l1) / 2)
                        if len(ks) >= 2:
                            m, b0 = linfit([d for d, k in ks], [k for d, k in ks])
                            dstar = -b0 / m if m else None
                            rec["driven"] = {"d_mv": dstar, "vr_q": None if dstar is None else round(vq0 + dstar / 1e3, 4), "vr_i": vi0,
                                             "k_at_null": b0, "k_per_mv": m, "rx_offset_mv": float(np.median(offs)), "legs_mv": [l1, l2],
                                             "k_by_d": ks, "zero_per_level_mv": [s["fit"]["zero_mv"] for s in good]}
                            T.say("   the sender's term: k = %+.4f of the leg at the null, %+.5f per mV of VR_Q; zero at d* = %+.1f mV (VR_Q %.4f V); "
                                  "the receiver's own Q offset %+.1f mV; per-level zeros %s" % (
                                      b0, m, dstar if dstar is not None else float("nan"), vq0 + (dstar or 0) / 1e3, float(np.median(offs)),
                                      ["%+.1f" % s["fit"]["zero_mv"] for s in good if s["fit"]["zero_mv"] is not None]))
                    if rec["driven"] is None and good:
                        z = good[0]["fit"]["zero_mv"]
                        rec["driven"] = {"d_mv": z, "vr_q": None if z is None else round(vq0 + z / 1e3, 4), "vr_i": vi0, "one_level": True,
                                         "legs_mv": [good[0]["leg_mv"]]}
                        T.say("   one level only: zero at d* = %+.1f mV" % (z if z is not None else float("nan")))
                    # the constellations: at the zero-ladder null, then at the driven null
                    L.ensure()
                    rec["constellations"] = {}
                    T.say("---- the 3 x 3 constellation and A3 at the zero-ladder null (VR_Q %.4f)" % vq0)
                    L.tx.cl.dac(VR_I=vi0, VR_Q=vq0)
                    rec["constellations"]["null"] = constellation(L, rs, nshots, keeper, lat, log, mhz, "null")
                    dd = (rec["driven"] or {}).get("d_mv")
                    if dd is not None and 0.0 <= vq0 + dd / 1e3 <= VR_CEIL:
                        vqd = vq0 + dd / 1e3
                        T.say("---- the same at the driven null (VR_Q %.4f, %+.1f mV)" % (vqd, dd))
                        L.tx.cl.dac(VR_I=vi0, VR_Q=vqd)
                        L.hold((1, 0))
                        time.sleep(0.1)
                        L.ensure()
                        L.slev = None
                        rec["constellations"]["driven"] = constellation(L, rs, nshots, keeper, lat, log, mhz, "driven")
                        # the flip once more at the driven null, as the check
                        TS.set_arms(rs, L.leg())
                        L.hold((1, 0))
                        time.sleep(0.1)
                        bb = TS.scope_dc(rs, (2, 3))
                        chk = flip_shot(L, rs, nshots, keeper, lat, {2: bb[2]["dc"], 3: bb[3]["dc"]}, stage="check", link=lk, mhz=mhz, d_mv=dd, leg=L.leg(), side=L.s)
                        rec["check_at_driven"] = chk
                        T.say("   the flip at the driven null: Q plateau %+.0f mV (%+.3f of the leg)" % (chk["q_plateau"] or 0, (chk["q_plateau"] or 0) / (rec["constellations"]["driven"]["leg_mv"] or 1)))
                    L.tx.cl.dac(VR_I=vi0, VR_Q=vq0)
                except T.LinkDown as e:
                    T.say("%s: %s" % (lk, e))
                    rec["error"] = str(e)
                except Exception as e:                    # noqa: BLE001
                    import traceback
                    T.say("%s: %r\n%s" % (lk, e, traceback.format_exc()))
                    rec["error"] = repr(e)[:300]
                finally:
                    try:
                        (vi0, vq0), _ = nodes[lk[0]].vr(mhz)
                        nodes[lk[0]].cl.dac(VR_I=vi0, VR_Q=vq0)
                    except Exception as e:                # noqa: BLE001
                        T.say("VR restore %s: %r" % (lk[0], e))
                    for n in ("A", "B"):
                        try:
                            nodes[n].quiet()
                        except Exception as e:            # noqa: BLE001
                            T.say("quiet %s: %r" % (n, e))
    finally:
        for n, s in scopes.items():
            try:
                s.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
                s.run()
                s.close()
            except Exception as e:                        # noqa: BLE001
                T.say("scope %s: %r" % (n, e))
        json.dump(out, open(os.path.join(T.DATA, "drivennull_%s.json" % stamp), "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(os.path.join(T.DATA, "drivennull_%s.npz" % stamp), meta=json.dumps(keeper.meta), **keeper.arr)
        T.say("saved %s (%d captures); %.0f min" % (os.path.join(T.DATA, "drivennull_%s" % stamp), keeper.k, (time.time() - t_start) / 60))
        T.say("==== summary: the driven null per sender and frequency")
        for rec in out["runs"]:
            d = rec.get("driven") or {}
            lock = rec.get("lock") or {}
            T.say("%s sends at %g: %s" % (rec["sender"], rec["mhz"], rec.get("error") or
                  "null VR_Q %.4f -> driven %s (d* %s mV; k %s of the leg at the null; rx offset %s mV; legs %s; lock DSA %.2f leg %.0f mV side %+d)" % (
                      rec["null"]["vr"][1], d.get("vr_q"), "%+.1f" % d["d_mv"] if d.get("d_mv") is not None else "?",
                      "%+.3f" % d["k_at_null"] if d.get("k_at_null") is not None else "?",
                      "%+.1f" % d["rx_offset_mv"] if d.get("rx_offset_mv") is not None else "?",
                      ["%.0f" % x for x in d.get("legs_mv", [])], lock.get("dsa", 0), 1e3 * (lock.get("leg") or 0), lock.get("side", 0))))
            for tag, c in (rec.get("constellations") or {}).items():
                a3 = c.get("A3") or {}
                T.say("   %-6s A3 right %s, gaps %s, dead %s; the flip's Q %s of the leg" % (
                    tag, "%.4f" % a3["right_frac_min"] if a3.get("right_frac_min") is not None else a3.get("error"), a3.get("gaps_mv"), a3.get("dead"),
                    "%+.3f" % ((next((p["q_plateau"] for p in c["points"] if p["point"] == [-1, 0]), 0) or 0) / c["leg_mv"])))
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
