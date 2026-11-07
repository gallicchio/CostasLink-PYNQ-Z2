"""The 11-07 afternoon wiring checked, per link: the lock at the new pads (50 dB), the sender's mark into the receiver's
TRIG IN (the gateware's reference -> decision histogram at A8, delay 6), and on the receiver's scope ch1 (the mark at the
tee, 1 Mohm), ch4 (TRIG B = the decision pulse) and the arms.
    python3 wirecheck.py [--links AB BA]"""
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

LAT_NS = {"AB": 10.0, "BA": 5.8}                          # the cables swapped 11-07: the longer (2 m) is A -> B now


def scope_setup2(s, scale=0.005):
    """ch1 the mark at a 1 Mohm tee (1.7 V step, 3.3 V after the open end's reflection), ch4 TRIG B (1.7 V into the
    feed-through, or 3.3 V without one)"""
    s.timebase(scale=TS.TDIV, delay=TS.DELAY)
    s.channel(1, on=True, scale=1.0, offset=-1.5, coupling="DC", probe=1)
    s.channel(2, on=True, scale=scale, offset=-TS.NOMINAL, coupling="DC", probe=1)
    s.channel(3, on=True, scale=scale, offset=-TS.NOMINAL, coupling="DC", probe=1)
    s.channel(4, on=True, scale=1.0, offset=-1.5, coupling="DC", probe=1)
    s.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")


def arm_decoder(L, name, delay, frac=0.4):
    s = C.SCHEMES[name]
    th, lv, gaps = T.scheme_windows(L, s, frac)
    iv, lut, sexp, info = T.rx_tables(L, s, False)
    rx = L.rx.cl
    rx.rx_config(iv, s.mask, lut, sexp, delay=delay, quiet=4, confirm=6, window=100, first_edge=False, settle=0, ref="trig_in")
    rx.rx_clear()
    rx.rx_enable(True)
    return s, info, gaps


def shot_nums(g, base, lat):
    t1, v1 = g[1]
    t1 = t1 * 1e9
    r = {"mark_high": float(v1.max()), "mark_t": TS.cross(t1, v1, TS.MARK_V, True)}
    t4, v4 = g[4]
    t4 = t4 * 1e9
    pre4 = float(np.median(v4[(t4 > -150) & (t4 < -20)]))
    hi4 = float(v4.max())
    r["trigb_low"], r["trigb_high"] = pre4, hi4
    r["dec_t"] = TS.cross(t4, v4, pre4 + (hi4 - pre4) / 2, True, after=-20) if hi4 - pre4 > 0.5 else None
    r["mark_to_dec"] = (r["dec_t"] - r["mark_t"]) if (r["dec_t"] is not None and r["mark_t"] is not None) else None
    t0 = (r["mark_t"] or 0.0) + lat
    for ch, nm in ((2, "i"), (3, "q")):
        t, v = g[ch]
        t = t * 1e9
        d = TS.GAIN * (v - base[ch]) * 1e3
        d = d - float(np.median(d[(t > -150) & (t < -20)]))
        pl = d[(t > t0 + 60) & (t < t0 + 180)]
        r[nm + "_plateau"] = float(np.median(pl)) if len(pl) else None
    return r


def main():
    links = sys.argv[sys.argv.index("--links") + 1:] if "--links" in sys.argv else ["AB", "BA"]
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    out = {"stamp": time.strftime("%Y%m%d_%H%M%S"), "runs": []}
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            scope_setup2(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for lk in links:
            L = T.Link(nodes[lk[0]], nodes[lk[1]], 4800.0)
            rs = scopes[L.rx.name]
            rec = {"link": lk}
            out["runs"].append(rec)
            T.say("==== %s at 4800" % lk)
            try:
                if not L.up():
                    T.say("   %s: NO LOCK at the new pads" % lk)
                    rec["error"] = "no lock"
                    continue
                rec["lock"] = dict(L.info, side=L.s)
                L.tx.cl.triggers(width=10, a="tx_event")
                L.rx.cl.triggers(width=10, a="tx_event", b="rx_decision")
                # 1. the gateware's own reference: the sender's mark into TRIG IN
                d = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A8", delay=6, ref="trig_in"))
                rec["a8_trigin"] = {k: d.get(k) for k in ("right_frac_min", "idle_false_per_s", "arrival_p50_ns", "arrival_min_ns", "arrival_max_ns",
                                                           "decision_p50_ns", "decision_p999_ns", "decision_max_ns", "error")}
                pm = d.get("per_msg") or {}
                refs = {m: (r.get("ref_to_decision") or {}).get("stats", {}) for m, r in pm.items()}
                rec["a8_trigin"]["per_msg_refs"] = {m: {k: s.get(k) for k in ("refs", "missed", "false", "lat_n")} for m, s in refs.items()}
                rec["a8_trigin"]["LAT_clocks"] = {m: (r.get("ref_to_decision") or {}).get("LAT_trig_to_cmp_i_clocks") for m, r in pm.items()}
                if d.get("error"):
                    T.say("   A8 at delay 6 with the TRIG IN reference: %s" % d["error"])
                else:
                    n_ref = sum((s.get("refs") or 0) for s in refs.values())
                    T.say("   A8 delay 6, TRIG IN as the reference: right min %.4f; refs seen %d (of %d events sent); arrival p50 %s ns "
                          "(min %s, max %s); decision p50 %s ns, p99.9 %s, max %s; LAT TRIG IN -> CMP_I %s clocks" % (
                              d["right_frac_min"], n_ref, 8 * 20000 * 3, d.get("arrival_p50_ns"), d.get("arrival_min_ns"), d.get("arrival_max_ns"),
                              d.get("decision_p50_ns"), d.get("decision_p999_ns"), d.get("decision_max_ns"), rec["a8_trigin"]["LAT_clocks"]))
                    if not n_ref:
                        T.say("   >>> TRIG IN sees no marks on %s: check the tee / cable from %s's TRIG A to %s's TRIG IN (J207)" % (L.rx.name, L.tx.name, L.rx.name))
                # 2. the scope: the mark at the tee, TRIG B's decision pulse, the arms
                leg = L.leg()
                TS.set_arms(rs, leg)
                L.hold((1, 0))
                time.sleep(0.1)
                TS.centre(rs)
                bb = TS.scope_dc(rs, (1, 2, 3, 4))
                base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
                T.say("   scope %s quiet: ch1 %.3f V, ch4 %.3f V, I arm %.4f, Q arm %.4f V" % (L.rx.name, bb[1]["dc"], bb[4]["dc"], bb[2]["dc"], bb[3]["dc"]))
                sch, info, gaps = arm_decoder(L, "A8", 6)
                rec["scope"] = []
                for pt in ((-1, 0), (0, 1), (-1, 1), (0, 0)):
                    L.recheck_side()
                    L.events_on(pt, 20, 1000, idle=(1, 0))
                    time.sleep(0.05)
                    got = TS.shots(rs, 1, TS.MARK_V, "rising", 4, (1, 2, 3, 4))
                    L.events_off()
                    rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
                    nums = [shot_nums(g, base, LAT_NS[lk]) for g in got]
                    r = {"point": list(pt), "n": len(got)}
                    for k in ("mark_high", "trigb_high", "trigb_low", "mark_to_dec", "i_plateau", "q_plateau"):
                        vals = [x[k] for x in nums if x.get(k) is not None]
                        r[k] = float(np.median(vals)) if vals else None
                        if k == "mark_to_dec" and vals:
                            r["mark_to_dec_min"], r["mark_to_dec_max"] = float(min(vals)), float(max(vals))
                    rec["scope"].append(r)
                    T.say("   (%+d,%+d): %d shots, mark high %s V, TRIG B %s -> %s V, mark -> decision %s ns (%s .. %s), I %s mV, Q %s mV" % (
                        pt[0], pt[1], len(got), "%.2f" % r["mark_high"] if r["mark_high"] is not None else "-",
                        "%.2f" % r["trigb_low"] if r["trigb_low"] is not None else "-", "%.2f" % r["trigb_high"] if r["trigb_high"] is not None else "-",
                        "%.1f" % r["mark_to_dec"] if r["mark_to_dec"] is not None else "NONE", "%.1f" % r.get("mark_to_dec_min", 0) if r.get("mark_to_dec") is not None else "-",
                        "%.1f" % r.get("mark_to_dec_max", 0) if r.get("mark_to_dec") is not None else "-",
                        "%.0f" % r["i_plateau"] if r["i_plateau"] is not None else "-", "%.0f" % r["q_plateau"] if r["q_plateau"] is not None else "-"))
                if not any(x.get("mark_to_dec") is not None for x in rec["scope"]):
                    T.say("   >>> no decision pulse on scope %s ch4: check the lead from %s's TRIG B (J206) to scope ch4" % (L.rx.name, L.rx.name))
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
        json.dump(out, open(os.path.join(T.DATA, "wirecheck_%s.json" % out["stamp"]), "w"), indent=1, default=str)
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
