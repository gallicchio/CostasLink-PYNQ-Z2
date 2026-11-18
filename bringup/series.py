"""Three parameter series over the cables, each a step at a time with the receiver's scope on the analog I and Q and the
decoder beside it (Jason, 2026-11-06: 'varying parameters a bit at a time ... a series of plots'):
  1. the receiver's step attenuator (the DSA, 0.25 dB steps; here 3 dB steps from 12 dB under the lock's setting to 15 dB
     over it): per level the leg, the flip and A3's four corners on the scope, A3 and B1 by the decoder (B1's pilot set
     up at that level), the PRBS bpsk at 50 clocks a bit;
  2. the event's width (2 ... 500 clocks of 10 ns) at the lock's level: the flip and the (1, 1) corner on the scope (the
     arms' rise and the loop's pull during a long event), A3 by the decoder at that width;
  3. the event rate (one in 50 ... 20 000 clocks, 200 ns events): the idle's position on the ADC and the scope while the
     events run (the loop's average pull), A3 by the decoder at that rate.
Records data/twoboard/series_<stamp>.json / .npz / .jsonl; the pages: series_fig.py.

    python3 series.py [--mhz 4800] [--links AB BA] [--shots 4] [--skip dsa|width|period ...]
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
import scope_e                                            # noqa: E402
import twoscope as TS                                     # noqa: E402
import drivennull as DN                                   # noqa: E402  (point_shot, flip_shot)

LAT_NS = {"AB": 5.8, "BA": 10.0}
DSA_STEPS = [-12, -9, -6, -3, 0, 3, 6, 9, 12, 15, 18]
WIDTHS = [2, 5, 10, 20, 50, 100, 200, 500]
PERIODS = [50, 100, 200, 500, 1000, 5000, 20000]
A3_PTS = [(-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]


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


def dec_brief(d):
    if "error" in d or "per_msg" not in d:
        return "error %s" % d.get("error")
    return "right %s, idle false %.0f/s, gaps %s%s" % (
        "/".join("%.4g" % (100 * min(1.0, r["right_frac"])) for m, r in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))) + " %",
        d.get("idle_false_per_s") or 0, d.get("gaps_mv"), ", dead %s" % d["rx_info"]["dead_windows"] if (d.get("rx_info") or {}).get("dead_windows") else "")


def trim(d):
    return {k: d.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "leg", "gaps_mv", "thresholds", "levels", "error", "pilot", "side_at_level")} | \
        {"dead": (d.get("rx_info") or {}).get("dead_windows")}


def scope_points(L, rs, pts, nshots, keeper, lat, width=20, period=1000, **meta):
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    TS.centre(rs)
    bb = TS.scope_dc(rs, (2, 3))
    base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
    rows = []
    for pt in pts:
        s0 = L.recheck_side()
        L.events_on(pt, width, period, idle=(1, 0))
        time.sleep(0.05)
        got = TS.shots(rs, 1, TS.MARK_V, "rising", nshots, (1, 2, 3, 4))
        L.events_off()
        L.hold((1, 0))
        rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
        nums = [TS.shot_numbers(g, base, lat) for g in got]
        keeper.keep(got, point=list(pt), base=base, leg=leg, width=width, period=period, side=s0, **meta)
        r = {"point": list(pt), "n": len(got), "side": s0}
        for k in ("i_plateau", "q_plateau", "i_spike_min", "i_spike_max", "q_spike_min", "q_spike_max", "i_ret_min", "i_ret_max", "q_ret_min",
                  "q_ret_max", "i_cross_t", "q_cross_t", "i_rise", "q_rise", "cmp_edge_t", "cmp_width", "mark_width"):
            r[k] = TS.med(nums, k)
        # the excursion inside the event for short events: the extreme of I and Q from t0 to t0 + 10 ns x width + 30 ns
        ex = {"i": [], "q": []}
        for g in got:
            t4, v4 = g[4]
            t4 = t4 * 1e9
            r0 = nums[0]["t0"]
            for ch, nm in ((2, "i"), (3, "q")):
                t, v = g[ch]
                t = t * 1e9
                d = TS.GAIN * (v - base[ch]) * 1e3
                d = d - float(np.median(d[(t > -150) & (t < -20)]))
                w = (t > r0) & (t < r0 + 10 * width + 30)
                if w.any():
                    ex[nm].append(float(d[w][np.argmax(np.abs(d[w]))]))
        r["i_extreme"] = float(np.median(ex["i"])) if ex["i"] else None
        r["q_extreme"] = float(np.median(ex["q"])) if ex["q"] else None
        rows.append(r)
    return leg, rows


def main():
    mhz = arg("--mhz", 4800.0)
    links = args_list("--links", ["AB", "BA"])
    nshots = arg("--shots", 4)
    skip = set(args_list("--skip", []))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("series")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "mhz": mhz, "gain": TS.GAIN, "links": {}}
    t_start = time.time()
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            TS.scope_setup(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for lk in links:
            L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz)
            rs = scopes[L.rx.name]
            rec = {"link": lk, "mhz": mhz, "dsa": [], "width": [], "period": []}
            out["links"][lk] = rec
            lat = LAT_NS.get(lk, 8.0)
            T.say("==== %s at %g MHz, %.0f min in" % (lk, mhz, (time.time() - t_start) / 60))
            try:
                if not L.up():
                    rec["error"] = "no link"
                    continue
                rec["lock"] = dict(L.info, side=L.s)
                log(label="series setup", tag="setup", state=L.state(), **L.info)
                L.tx.cl.triggers(width=10, a="tx_event")
                L.rx.cl.triggers(width=10, a="tx_event")
                lock_dsa = L.info.get("dsa", L.rx.cl._dsa_db)
                # ---- 1. the step attenuator ----
                if "dsa" not in skip:
                    T.say("---- 1. the DSA from %.2f: %s dB about the lock's" % (lock_dsa, DSA_STEPS))
                    for step in DSA_STEPS:
                        dsa = min(31.75, max(0.0, lock_dsa + step))
                        if rec["dsa"] and abs(dsa - rec["dsa"][-1]["dsa"]) < 0.1:
                            continue
                        L.rx.cl.dsa(dsa)
                        time.sleep(0.05)
                        side = L.recheck_side()
                        row = {"step": step, "dsa": dsa, "side": side}
                        if side is None:
                            T.say("   DSA %5.2f (%+d): nothing locked at this level" % (dsa, step))
                            row["locked"] = False
                            L.rx.cl.dsa(lock_dsa)
                            time.sleep(0.05)
                            st = L.ensure()
                            row["back_at_lock"] = st
                            rec["dsa"].append(row)
                            log(label="series dsa", tag="dsa", state=L.state(), **row)
                            continue
                        row["locked"] = True
                        leg, pts = scope_points(L, rs, A3_PTS, nshots, keeper, lat, stage="dsa", link=lk, mhz=mhz, dsa=dsa, step=step)
                        row["leg_mv"] = 1e3 * leg
                        row["points"] = pts
                        T.say("   DSA %5.2f (%+3d) leg %4.0f mV side %+d: flip I %+5.0f Q %+4.0f (%+.3f); corners %s" % (
                            dsa, step, 1e3 * leg, side, pts[0]["i_plateau"] or 0, pts[0]["q_plateau"] or 0, (pts[0]["q_plateau"] or 0) / (1e3 * leg),
                            " ".join("(%d,%d) %+.0f,%+.0f" % (p["point"][0], p["point"][1], p["i_plateau"] or 0, p["q_plateau"] or 0) for p in pts[1:])))
                        L.rx.cl.dsa(lock_dsa)                 # events_point / prbs_point check the lock at the link's level, then set dsa=
                        time.sleep(0.05)
                        L.recheck_side()
                        for sc in ("A3", "B1"):
                            try:
                                d = T.events_point(L, **dict(T.EVENTS_BASE, scheme=sc, dsa=dsa))
                            except T.LinkDown:
                                raise
                            except Exception as e:        # noqa: BLE001
                                d = {"error": repr(e)[:200]}
                                L.ensure()
                            row[sc] = trim(d)
                            T.say("   DSA %5.2f %s: %s%s" % (dsa, sc, dec_brief(d), (", pilot %.0f mV rho %.2f" % (1e3 * d["pilot"]["rho"] * d["pilot"]["a"], d["pilot"]["rho"]))
                                                             if d.get("pilot") and d["pilot"].get("rho") else ""))
                        try:
                            p = T.prbs_point(L, **dict(T.PRBS_BASE, period=50, dsa=dsa))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            p = {"error": repr(e)[:200]}
                            L.ensure()
                        row["prbs50"] = {k: p.get(k) for k in ("ber", "bits", "mismatches", "error", "side_at_level")}
                        T.say("   DSA %5.2f prbs bpsk P50: BER %s over %s bits%s" % (dsa, p.get("ber"), p.get("bits"), " error %s" % p["error"] if p.get("error") else ""))
                        rec["dsa"].append(row)
                        log(label="series dsa", tag="dsa", state=L.state(), **{k: v for k, v in row.items() if k not in ("A3", "B1")},
                            A3={k: v for k, v in row["A3"].items() if k != "levels"}, B1={k: v for k, v in row["B1"].items() if k != "levels"})
                    L.rx.cl.dsa(lock_dsa)
                    time.sleep(0.05)
                    L.ensure()
                # ---- 2. the event's width ----
                if "width" not in skip:
                    T.say("---- 2. the event's width at the lock's level: %s clocks" % WIDTHS)
                    for w in WIDTHS:
                        period = 1000 if w <= 200 else 5000
                        L.ensure()
                        leg, pts = scope_points(L, rs, [(-1, 0), (1, 1)], nshots, keeper, lat, width=w, period=period, stage="width", link=lk, mhz=mhz)
                        row = {"width": w, "period": period, "leg_mv": 1e3 * leg, "points": pts}
                        try:
                            d = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A3", width=w, period=period, count=5000))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            d = {"error": repr(e)[:200]}
                            L.ensure()
                        row["A3"] = trim(d)
                        T.say("   width %3d clk (%4.0f ns): flip I %+5.0f Q %+4.0f (extreme %+.0f/%+.0f), (1,1) I %+4.0f Q %+4.0f (extreme %+.0f/%+.0f), I rise %s ns; A3 %s" % (
                            w, 10 * w, pts[0]["i_plateau"] or 0, pts[0]["q_plateau"] or 0, pts[0]["i_extreme"] or 0, pts[0]["q_extreme"] or 0,
                            pts[1]["i_plateau"] or 0, pts[1]["q_plateau"] or 0, pts[1]["i_extreme"] or 0, pts[1]["q_extreme"] or 0,
                            "%.1f" % pts[0]["i_rise"] if pts[0]["i_rise"] else "-", dec_brief(d)))
                        rec["width"].append(row)
                        log(label="series width", tag="width", state=L.state(), **{k: v for k, v in row.items() if k != "A3"}, A3={k: v for k, v in row["A3"].items() if k != "levels"})
                # ---- 3. the event rate ----
                if "period" not in skip:
                    T.say("---- 3. the event rate at the lock's level: one in %s clocks" % PERIODS)
                    for per in PERIODS:
                        L.ensure()
                        L.hold((1, 0))
                        time.sleep(0.1)
                        o0 = L.ld.observe()
                        dc0 = TS.scope_dc(rs, (2, 3))
                        row = {"period": per, "width": 20, "duty": 20.0 / per, "idle_di": o0["di"], "idle_dq": o0["dq"]}
                        # the idle while the corner events run, on the ADC (the loop's average position) and the scope's median
                        for pt in ((1, 1), (-1, -1)):
                            L.events_on(pt, 20, per, idle=(1, 0))
                            time.sleep(0.3)
                            o = L.ld.observe()
                            dc = TS.scope_dc(rs, (2, 3))
                            L.events_off()
                            L.hold((1, 0))
                            row["during_%d_%d" % pt] = {"di": o["di"], "dq": o["dq"], "vc": o["vc"], "locked": bool(o["locked"]),
                                                        "scope_i_mv": 1e3 * TS.GAIN * (dc[2]["dc"] - dc0[2]["dc"]), "scope_q_mv": 1e3 * TS.GAIN * (dc[3]["dc"] - dc0[3]["dc"])}
                        count = min(20000, max(2000, int(2e5 / max(1, per) * 100)))
                        try:
                            d = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A3", period=per, count=min(20000, count)))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            d = {"error": repr(e)[:200]}
                            L.ensure()
                        row["A3"] = trim(d)
                        d11, dmm = row["during_1_1"], row["during_-1_-1"]
                        T.say("   one in %5d (duty %5.1f %%): the idle during (1,1) events ADC dI %+.4f dQ %+.4f (scope I %+.0f Q %+.0f mV), during (-1,-1) dI %+.4f dQ %+.4f (I %+.0f Q %+.0f); A3 %s" % (
                            per, 100 * 20.0 / per, d11["di"] - o0["di"], d11["dq"] - o0["dq"], d11["scope_i_mv"], d11["scope_q_mv"],
                            dmm["di"] - o0["di"], dmm["dq"] - o0["dq"], dmm["scope_i_mv"], dmm["scope_q_mv"], dec_brief(d)))
                        rec["period"].append(row)
                        log(label="series period", tag="period", state=L.state(), **{k: v for k, v in row.items() if k != "A3"}, A3={k: v for k, v in row["A3"].items() if k != "levels"})
            except T.LinkDown as e:
                T.say("%s: %s" % (lk, e))
                rec["error"] = str(e)
            except Exception as e:                        # noqa: BLE001
                import traceback
                T.say("%s: %r\n%s" % (lk, e, traceback.format_exc()))
                rec["error"] = repr(e)[:300]
            finally:
                for n in ("A", "B"):
                    try:
                        nodes[n].quiet()
                    except Exception as e:                # noqa: BLE001
                        T.say("quiet %s: %r" % (n, e))
    finally:
        for n, s in scopes.items():
            try:
                s.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
                s.run()
                s.close()
            except Exception as e:                        # noqa: BLE001
                T.say("scope %s: %r" % (n, e))
        json.dump(out, open(os.path.join(T.DATA, "series_%s.json" % stamp), "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(os.path.join(T.DATA, "series_%s.npz" % stamp), meta=json.dumps(keeper.meta), **keeper.arr)
        T.say("saved %s (%d captures); %.0f min" % (os.path.join(T.DATA, "series_%s" % stamp), keeper.k, (time.time() - t_start) / 60))
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
