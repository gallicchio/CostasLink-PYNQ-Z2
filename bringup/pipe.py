"""Where the ~80 ns between the comparators and the decision pulse goes, on the receiver's scope (ch1 the sender's mark
at the tee, ch4 TRIG B), per link over the cables:
  sources  TRIG B as the sign comparator's edges ('cmp_i': the sampler's output re-emitted), the event detection
           ('rx_event') and the decision ('rx_decision'), the flip sent, 8 shots each: three points along the pipeline
  hist     60 shots of mark -> decision at the flip (A8, delay 8): the spread is the 100 MHz word clock's phase
  modes    the settled decision (settle 2 / 4) and the first-edge decision (A1 / A2) against the fixed delay, on the scope
  frac     A8 by the decoder at delays 6 and 8 with the windows at 0.3 / 0.4 / 0.5 of the gap, and delay 7 with 10^5 events
    python3 pipe.py [--links AB BA]   ->  data/twoboard/pipe_<stamp>.json / .npz"""
import json
import os
import sys
import time

import numpy as np

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twoboard as T                                      # noqa: E402
import costaslink as C                                    # noqa: E402
import scope_e                                            # noqa: E402
import twoscope as TS                                     # noqa: E402
import wirecheck as W                                     # noqa: E402
import night2 as N2                                       # noqa: E402


def arm(L, name, delay, settle=0, first_edge=False, frac=0.4):
    s = C.SCHEMES[name]
    th, lv, gaps = T.scheme_windows(L, s, frac)
    iv, lut, sexp, info = T.rx_tables(L, s, first_edge)
    rx = L.rx.cl
    rx.rx_config(iv, s.mask, lut, sexp, delay=delay, quiet=4, confirm=6, window=100, first_edge=first_edge, settle=settle, ref="tx")
    rx.rx_clear()
    rx.rx_enable(True)
    return s, gaps


def shots_at(L, rs, keeper, pt, nshots, lat, base, **meta):
    side = L.recheck_side()
    L.events_on(pt, 20, 1000, idle=(1, 0))
    time.sleep(0.05)
    got = TS.shots(rs, 1, TS.MARK_V, "rising", nshots, (1, 2, 3, 4))
    L.events_off()
    rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
    nums = [W.shot_nums(g, base, lat) for g in got]
    keeper.keep(got, point=list(pt), base=base, side=side, link=L.name, **meta)
    vals = [x["mark_to_dec"] for x in nums if x.get("mark_to_dec") is not None]
    r = {"point": list(pt), "n": len(got), "side": side, "mark_to_dec_all": vals,
         "mark_to_dec": float(np.median(vals)) if vals else None, "mark_to_dec_min": float(min(vals)) if vals else None,
         "mark_to_dec_max": float(max(vals)) if vals else None, "trigb_high": TS.med(nums, "trigb_high"),
         "i_plateau": TS.med(nums, "i_plateau"), "q_plateau": TS.med(nums, "q_plateau")}
    r.update(meta)
    return r


def say_row(label, r):
    T.say("   %-34s (%+d,%+d): mark -> ch4 %s ns (%s .. %s, %d of %d)" % (
        label, r["point"][0], r["point"][1], "%.1f" % r["mark_to_dec"] if r["mark_to_dec"] is not None else "NONE",
        "%.1f" % r["mark_to_dec_min"] if r["mark_to_dec_min"] is not None else "-", "%.1f" % r["mark_to_dec_max"] if r["mark_to_dec_max"] is not None else "-",
        len(r["mark_to_dec_all"]), r["n"]))


def run_link(L, rs, keeper, log):
    rec = {"lock": N2.link_up(L, log, rs)}
    lat = W.LAT_NS[L.name]
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    TS.centre(rs)
    bb = TS.scope_dc(rs, (2, 3))
    base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
    rec["leg_mv"] = 1e3 * leg
    # 1. three points along the pipeline
    T.say("---- sources: TRIG B as cmp_i / rx_event / rx_decision, the flip, A8 at delay 8")
    rec["sources"] = []
    arm(L, "A8", 8)
    for src in ("cmp_i", "rx_event", "rx_decision"):
        L.rx.cl.triggers(width=10, a="tx_event", b=src, b_rising_only=False)
        for pt in ((-1, 0), (0, 1)):
            r = shots_at(L, rs, keeper, pt, 8, lat, base, stage="sources", trigb=src, scheme="A8", delay=8)
            rec["sources"].append(r)
            say_row("TRIG B = %s" % src, r)
    L.rx.cl.triggers(width=10, a="tx_event", b="rx_decision")
    # 2. the spread: 60 shots at the flip
    T.say("---- hist: 60 shots of mark -> decision at the flip, A8 delay 8")
    rec["hist"] = shots_at(L, rs, keeper, (-1, 0), 60, lat, base, stage="hist", trigb="rx_decision", scheme="A8", delay=8)
    say_row("60 shots, A8 d8", rec["hist"])
    a = np.array(rec["hist"]["mark_to_dec_all"])
    if len(a):
        T.say("   spread: p10 %.1f, p50 %.1f, p90 %.1f ns; std %.2f" % (np.percentile(a, 10), np.median(a), np.percentile(a, 90), a.std()))
    # 3. the decision modes on the scope
    T.say("---- modes: the settled decision and the first-edge decision on the scope")
    rec["modes"] = []
    for name, delay, settle, fe, pts in (("A8", 16, 2, False, [(-1, 0), (0, 1), (-1, 1)]), ("A8", 16, 4, False, [(-1, 0), (0, 1), (-1, 1)]),
                                         ("A8", 8, 0, False, [(-1, 0), (0, 1), (-1, 1)]), ("A3", 8, 0, False, [(-1, 1)]), ("A3", 16, 2, False, [(-1, 1)]),
                                         ("A1", 2, 0, False, [(-1, 0)]), ("A1", 2, 0, True, [(-1, 0)]), ("A2", 2, 0, False, [(1, 1)]), ("A2", 2, 0, True, [(1, 1)])):
        try:
            arm(L, name, delay, settle=settle, first_edge=fe)
        except Exception as e:                            # noqa: BLE001
            T.say("   %s delay %d settle %d first_edge %s: %r" % (name, delay, settle, fe, e))
            L.ensure()
            continue
        for pt in pts:
            r = shots_at(L, rs, keeper, pt, 6, lat, base, stage="modes", trigb="rx_decision", scheme=name, delay=delay, settle=settle, first_edge=fe)
            rec["modes"].append(r)
            say_row("%s d%d%s%s" % (name, delay, " settle %d" % settle if settle else "", " first_edge" if fe else ""), r)
    L.rx.cl.rx_enable(True)
    # 4. by the decoder: the window fraction at the marginal delay, and delay 7 with 10^5 events
    T.say("---- frac: A8 at delays 6 and 8 with the windows at 0.3 / 0.4 / 0.5; delay 7 with 10^5 events")
    rec["frac"] = []
    for frac in (0.3, 0.4, 0.5):
        for dl in (6, 8):
            rec["frac"].append(N2.gw_point(L, log, "A8", dl, "frac%.1f" % frac, frac=frac))
    rec["frac"].append(N2.gw_point(L, log, "A8", 7, "d7", count=100000))
    rec["frac"].append(N2.gw_point(L, log, "A3", 7, "d7", count=100000))
    rec["frac"].append(N2.gw_point(L, log, "A8", 8, "d8_1e5", count=100000))
    return rec


def main():
    links = sys.argv[sys.argv.index("--links") + 1:] if "--links" in sys.argv else ["AB", "BA"]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("pipe")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "gain": TS.GAIN, "lat_ns": W.LAT_NS, "runs": {}}
    path = os.path.join(T.DATA, "pipe_%s" % stamp)
    t0 = time.time()
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            W.scope_setup2(scopes[n])
        for lk in links:
            L = T.Link(nodes[lk[0]], nodes[lk[1]], 4800.0)
            rs = scopes[L.rx.name]
            T.say("==== %s at 4800, %.0f min in" % (lk, (time.time() - t0) / 60))
            try:
                out["runs"][lk] = run_link(L, rs, keeper, log)
            except T.LinkDown as e:
                T.say("%s: %s" % (lk, e))
                out["runs"][lk] = {"error": str(e)}
            except Exception as e:                        # noqa: BLE001
                import traceback
                T.say("%s: %r\n%s" % (lk, e, traceback.format_exc()))
                out["runs"][lk] = {"error": repr(e)[:300]}
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
        json.dump(out, open(path + ".json", "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(path + ".npz", meta=json.dumps(keeper.meta), **keeper.arr)
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("saved %s (%d captures); %.0f min; done, both quiet" % (path, keeper.k, (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
