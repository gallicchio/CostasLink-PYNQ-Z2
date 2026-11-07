"""The night of 11-07 over the cables (50 dB pads; the sender's mark into the receiver's TRIG IN through a tee at the
scope's ch1; TRIG B = the decision pulse on ch4): the one-way latency to the decision, on the scope and in the gateware.
  lat    per link at the lock's level: each scheme at its shortest delay and at 16, the gateware's reference -> decision
         histogram (1.25 ns) and the scope's mark -> TRIG B on every message point
  level  per link: the DSA stepped about the lock's (-6 .. +22 dB, legs 360 -> 15 mV): A8 at delays 6 / 10 / 16, A3, A2,
         A1 by the gateware, the PRBS, and the scope on three A8 points at delay 6
  long   per link: A8 at delay 6 with a million events a message (period 1000) and ten million (period 100)
  cycle  every --every min until --until: both boards quiet, each link's lock, A8 / A3 by the gateware with the
         TRIG IN reference, the PRBS, the scope's mark -> decision on two points
    python3 night2.py [--stages lat level long cycle] [--every 10] [--until 09:00] [--mhz_ab 4800 --mhz_ba 5000]
records: data/twoboard/night2_<stamp>.json (rewritten after every stage and cycle) and .npz (the scope shots)"""
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
import wirecheck as W                                     # noqa: E402  (scope_setup2, arm_decoder, shot_nums, LAT_NS)
import soak_night as SN                                   # noqa: E402  (quiet_readings)

LAT_PLAN = [("A8", 6), ("A8", 8), ("A8", 16), ("A3", 6), ("A3", 16), ("A2", 2), ("A2", 16), ("A1", 2), ("A1", 16)]
LEVEL_STEPS = [-6, -3, 0, 3, 6, 10, 14, 18, 22]
LEVEL_SCOPE_PTS = [(-1, 0), (0, 1), (-1, 1)]
CYCLE_SCOPE_PTS = [(-1, 0), (0, 1)]


def arg(name, default, cast=float):
    return cast(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def args_list(name, default):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name) + 1
    out = []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(sys.argv[i])
        i += 1
    return out or default


def gw_point(L, log, sc, delay, tag, **over):
    """events_point with the TRIG IN reference: the right fractions and the gateware's own latency histograms"""
    p = dict(dict(T.EVENTS_BASE, scheme=sc, delay=delay, ref="tx"), **over)
    try:
        d = T.events_point(L, **p)
    except T.LinkDown:
        raise
    except Exception as e:                                # noqa: BLE001
        d = {"error": repr(e)[:200]}
        L.ensure()
    r = {k: d.get(k) for k in ("right_frac_min", "right_frac_mean", "idle_false_per_s", "arrival_p50_ns", "arrival_min_ns", "arrival_max_ns",
                               "decision_p50_ns", "decision_p999_ns", "decision_max_ns", "error", "leg", "gaps_mv", "side_at_level")}
    pm = d.get("per_msg") or {}
    r["per_msg"] = {}
    for m, row in pm.items():
        rd = row.get("ref_to_decision") or {}
        re_ = row.get("ref_to_event") or {}
        r["per_msg"][m] = {"right_frac": row.get("right_frac"), "dec_p50": rd.get("p50_ns"), "dec_p99": rd.get("p99_ns"), "dec_p999": rd.get("p999_ns"),
                           "dec_min": rd.get("min_ns"), "dec_max": rd.get("max_ns"), "dec_n": rd.get("n"), "ev_p50": re_.get("p50_ns"), "ev_min": re_.get("min_ns"),
                           "ev_max": re_.get("max_ns"), "refs": (rd.get("stats") or {}).get("refs"), "missed": (rd.get("stats") or {}).get("missed"),
                           "lat_clocks": rd.get("LAT_trig_to_cmp_i_clocks"), "dec_bins": rd.get("bins")}
    r.update(scheme=sc, params=p, tag=tag)
    if d.get("error"):
        T.say("   %-3s delay %-2d %s: %s" % (sc, delay, tag, d["error"]))
    else:
        T.say("   %-3s delay %-2d %s: right %s, min %.4f, false %.0f/s" % (
            sc, delay, tag, " ".join("%.4f" % rr["right_frac"] for m, rr in sorted(pm.items(), key=lambda kv: int(kv[0]))), d["right_frac_min"],
            d.get("idle_false_per_s") or 0))
    log(label="night2 %s %s d%d" % (tag, sc, delay), tag="events", params=p, state=L.state(), **{k: v for k, v in d.items() if k != "per_msg"})
    return r


def lat_probe(L, log, tag, reads=80, pt=(-1, 0)):
    """the LAT register (TRIG IN's rise to the next CMP_I edge, in clocks of 10 ns, the last event's) read `reads` times
    while the flip's events run at 1 in 1000.  Over these cables TRIG IN rises after the event's leading edge, so the
    count runs to the event's trailing edge (18 clocks for a 200 ns event: 11-07 wirecheck); the reading is a check of
    that order, not an arrival time"""
    rx = L.rx.cl
    L.events_on(pt, 20, 1000, idle=(1, 0))
    time.sleep(0.05)
    vals = []
    for _ in range(reads):
        v = rx.rd("LAT")
        if (v >> 16) & 1:
            vals.append(v & 0xFFFF)
    L.events_off()
    r = {"which": tag, "point": list(pt), "reads": reads, "valid": len(vals)}
    if vals:
        a = np.array(vals, float) * 10.0
        r.update(lat_ns_p50=float(np.median(a)), lat_ns_min=float(a.min()), lat_ns_max=float(a.max()), lat_ns_mean=float(a.mean()),
                 counts={int(k): int(c) for k, c in zip(*np.unique(np.array(vals), return_counts=True))})
        T.say("   LAT (TRIG IN -> the next CMP_I edge) %s: %d valid of %d reads, p50 %.0f ns, %.0f .. %.0f" % (tag, len(vals), reads, r["lat_ns_p50"], r["lat_ns_min"], r["lat_ns_max"]))
    else:
        T.say("   LAT %s: no valid reading in %d reads" % (tag, reads))
    log(label="night2 LAT %s" % tag, tag="lat", state=L.state(), **r)
    return r


def scope_points(L, rs, keeper, sc, delay, pts, nshots, lat, settle=0, **meta):
    """the decoder armed for scheme sc at `delay` (or the settled decision, `settle` samples, `delay` the cap); each
    point sent as events: mark -> TRIG B on the scope, the arms"""
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    TS.centre(rs)
    bb = TS.scope_dc(rs, (2, 3))
    base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
    s, info, gaps = W.arm_decoder(L, sc, delay, settle=settle)
    rows = []
    for pt in pts:
        side = L.recheck_side()
        L.events_on(pt, 20, 1000, idle=(1, 0))
        time.sleep(0.05)
        got = TS.shots(rs, 1, TS.MARK_V, "rising", nshots, (1, 2, 3, 4))
        L.events_off()
        rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
        nums = [W.shot_nums(g, base, lat) for g in got]
        keeper.keep(got, point=list(pt), base=base, leg=leg, scheme=sc, delay=delay, settle=settle, side=side, link=L.name, **meta)
        r = {"point": list(pt), "n": len(got), "side": side, "leg_mv": 1e3 * leg}
        for k in ("mark_high", "trigb_high", "mark_to_dec", "i_plateau", "q_plateau"):
            vals = [x[k] for x in nums if x.get(k) is not None]
            r[k] = float(np.median(vals)) if vals else None
            if k == "mark_to_dec":
                r["mark_to_dec_n"] = len(vals)
                r["mark_to_dec_min"] = float(min(vals)) if vals else None
                r["mark_to_dec_max"] = float(max(vals)) if vals else None
        rows.append(r)
        T.say("   scope %s d%d%s (%+d,%+d): mark -> decision %s ns (%s..%s, %d of %d), I %s, Q %s mV" % (
            sc, delay, " settle %d" % settle if settle else "", pt[0], pt[1], "%.1f" % r["mark_to_dec"] if r["mark_to_dec"] is not None else "NONE",
            "%.1f" % r["mark_to_dec_min"] if r["mark_to_dec_min"] is not None else "-", "%.1f" % r["mark_to_dec_max"] if r["mark_to_dec_max"] is not None else "-",
            r["mark_to_dec_n"], len(got), "%.0f" % r["i_plateau"] if r["i_plateau"] is not None else "-", "%.0f" % r["q_plateau"] if r["q_plateau"] is not None else "-"))
    L.rx.cl.rx_enable(True)
    return {"leg_mv": 1e3 * leg, "scheme": sc, "delay": delay, "settle": settle, "gaps_mv": gaps, "rows": rows}


def link_up(L, log, rs):
    if not L.up():
        raise T.LinkDown("%s: no lock" % L.name)
    L.tx.cl.triggers(width=10, a="tx_event")
    L.rx.cl.triggers(width=10, a="tx_event", b="rx_decision")
    W.scope_setup2(rs)
    log(label="night2 setup", tag="setup", state=L.state(), **L.info)
    return dict(L.info, side=L.s)


def stage_lat(L, rs, keeper, log, nshots=6):
    rec = {"lock": link_up(L, log, rs), "gw": [], "scope": []}
    rec["LAT"] = lat_probe(L, log, "lat")
    T.say("---- lat: each scheme at its shortest delay and at 16 by the decoder")
    for sc, dl in LAT_PLAN:
        rec["gw"].append(gw_point(L, log, sc, dl, "lat"))
    T.say("---- lat: the scope's mark -> TRIG B on every point")
    for sc, dl in LAT_PLAN:
        if dl == 16 and sc != "A8":
            continue
        s = C.SCHEMES[sc]
        rec["scope"].append(scope_points(L, rs, keeper, sc, dl, list(s.msgs), nshots, W.LAT_NS[L.name], stage="lat"))
    return rec


def stage_level(L, rs, keeper, log, nshots=6):
    rec = {"lock": link_up(L, log, rs), "levels": []}
    lock_dsa = L.info["dsa"]
    for step in LEVEL_STEPS:
        dsa = min(31.75, max(0.0, lock_dsa + step))
        if step and dsa == lock_dsa:
            continue
        L.rx.cl.dsa(lock_dsa)
        L.ensure()
        L.rx.cl.dsa(dsa)
        time.sleep(0.05)
        side = L.recheck_side()
        if side is None:
            T.say("---- level %+d dB (DSA %.2f): no lock at this level" % (step, dsa))
            rec["levels"].append({"step": step, "dsa": dsa, "error": "no lock"})
            continue
        leg = L.leg()
        T.say("---- level %+d dB (DSA %.2f): leg %.0f mV, side %+d" % (step, dsa, 1e3 * leg, side))
        lv = {"step": step, "dsa": dsa, "leg_mv": 1e3 * leg, "side": side, "gw": [], "scope": None}
        for sc, dl in (("A8", 6), ("A8", 10), ("A8", 16), ("A3", 6), ("A2", 2), ("A1", 2)):
            L.rx.cl.dsa(lock_dsa)                                           # events_point checks the lock at the link's level, then sets dsa=
            lv["gw"].append(gw_point(L, log, sc, dl, "level%+d" % step, dsa=dsa))
        try:
            L.rx.cl.dsa(lock_dsa)
            p = T.prbs_point(L, **dict(T.PRBS_BASE, period=50, seconds=3.0, dsa=dsa))
            lv["prbs50"] = {k: p.get(k) for k in ("ber", "bits", "mismatches", "error")}
            T.say("   prbs P50 3 s: BER %s over %s bits" % (p.get("ber"), p.get("bits")))
        except T.LinkDown:
            raise
        except Exception as e:                            # noqa: BLE001
            lv["prbs50"] = {"error": repr(e)[:200]}
        L.rx.cl.dsa(dsa)
        time.sleep(0.05)
        if L.recheck_side() is not None:
            lv["LAT"] = lat_probe(L, log, "level%+d" % step)
            lv["scope"] = scope_points(L, rs, keeper, "A8", 6, LEVEL_SCOPE_PTS, nshots, W.LAT_NS[L.name], stage="level", step=step, dsa=dsa)
        rec["levels"].append(lv)
    L.rx.cl.dsa(lock_dsa)
    L.ensure()
    return rec


def stage_long(L, rs, log):
    rec = {"lock": link_up(L, log, rs), "runs": []}
    T.say("---- long: A8 at delay 6, a million events a message at period 1000")
    rec["runs"].append(gw_point(L, log, "A8", 6, "long1M", count=1000000, ref="tx"))
    T.say("---- long: A8 at delay 6, ten million events a message at period 100")
    rec["runs"].append(gw_point(L, log, "A8", 6, "long10M", count=10000000, period=100, ref="tx"))
    return rec


def cycle_link(L, rs, keeper, log, cycle):
    rec = {"lock": link_up(L, log, rs)}
    rec["A8"] = gw_point(L, log, "A8", 8, "cycle%d" % cycle)       # delay 8: the robust minimum (4.88); 6 is marginal on (-1, +1)
    rec["A3"] = gw_point(L, log, "A3", 8, "cycle%d" % cycle)
    rec["settle"] = [gw_point(L, log, "A8", 16, "cycle%d" % cycle, settle=k) for k in (2, 4, 6)]   # the settled decision's right fraction
    try:
        p = T.prbs_point(L, **dict(T.PRBS_BASE, period=20, seconds=5.0))
        rec["prbs20"] = {k: p.get(k) for k in ("ber", "bits", "mismatches", "error")}
        T.say("   prbs P20 5 s: BER %s over %s bits (%s mismatches)" % (p.get("ber"), p.get("bits"), p.get("mismatches")))
    except T.LinkDown:
        raise
    except Exception as e:                                # noqa: BLE001
        rec["prbs20"] = {"error": repr(e)[:200]}
    rec["LAT"] = lat_probe(L, log, "cycle%d" % cycle, reads=40)
    rec["scope"] = scope_points(L, rs, keeper, "A8", 8, CYCLE_SCOPE_PTS, 4, W.LAT_NS[L.name], stage="cycle", cycle=cycle)
    rec["scope_settle2"] = scope_points(L, rs, keeper, "A8", 16, CYCLE_SCOPE_PTS, 4, W.LAT_NS[L.name], settle=2, stage="cycle", cycle=cycle)
    return rec


def main():
    stages = args_list("--stages", ["lat", "level", "long", "cycle"])
    every = arg("--every", 10.0)
    until = arg("--until", "09:00", str)
    mhz = {"AB": arg("--mhz_ab", 4800.0), "BA": arg("--mhz_ba", 5000.0)}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("night2")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "gain": TS.GAIN, "mhz": mhz, "lat_ns": W.LAT_NS, "stages": {}, "cycles": []}
    path = os.path.join(T.DATA, "night2_%s" % stamp)
    t0 = time.time()

    def save():
        json.dump(out, open(path + ".json", "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(path + ".npz", meta=json.dumps(keeper.meta), **keeper.arr)

    def quiet_all():
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))

    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            W.scope_setup2(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for st in [s for s in stages if s != "cycle"]:
            out["stages"][st] = {}
            for lk in ("AB", "BA"):
                L = T.Link(nodes[lk[0]], nodes[lk[1]], 4800.0)
                rs = scopes[L.rx.name]
                T.say("==== %s: %s at 4800, %.0f min in" % (st, lk, (time.time() - t0) / 60))
                try:
                    fn = {"lat": lambda: stage_lat(L, rs, keeper, log), "level": lambda: stage_level(L, rs, keeper, log),
                          "long": lambda: stage_long(L, rs, log)}[st]
                    out["stages"][st][lk] = fn()
                except T.LinkDown as e:
                    T.say("%s: %s" % (lk, e))
                    out["stages"][st][lk] = {"error": str(e)}
                except Exception as e:                    # noqa: BLE001
                    import traceback
                    T.say("%s: %r\n%s" % (lk, e, traceback.format_exc()))
                    out["stages"][st][lk] = {"error": repr(e)[:300]}
                finally:
                    quiet_all()
                    save()
        if "cycle" in stages:
            hh, mm = (int(x) for x in until.split(":"))
            end = time.localtime()
            end_t = time.mktime((end.tm_year, end.tm_mon, end.tm_mday, hh, mm, 0, 0, 0, -1))
            if end_t < time.time():
                end_t += 86400
            cycle = 0
            while time.time() < end_t:
                t_cycle = time.time()
                cyc = {"cycle": cycle, "t": t_cycle, "when": time.strftime("%H:%M:%S"), "links": {}}
                T.say("==== cycle %d at %s, %.1f h in" % (cycle, cyc["when"], (t_cycle - t0) / 3600))
                try:
                    cyc["quiet"] = SN.quiet_readings(nodes, log)
                except Exception as e:                    # noqa: BLE001
                    T.say("quiet readings: %r" % (e,))
                for lk in ("AB", "BA"):
                    L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz[lk])
                    rs = scopes[L.rx.name]
                    try:
                        cyc["links"][lk] = cycle_link(L, rs, keeper, log, cycle)
                    except T.LinkDown as e:
                        T.say("   %s: %s" % (lk, e))
                        cyc["links"][lk] = {"error": str(e)}
                    except Exception as e:                # noqa: BLE001
                        import traceback
                        T.say("   %s: %r\n%s" % (lk, e, traceback.format_exc()))
                        cyc["links"][lk] = {"error": repr(e)[:300]}
                    finally:
                        quiet_all()
                out["cycles"].append(cyc)
                save()
                cycle += 1
                wait = max(0.0, every * 60 - (time.time() - t_cycle))
                T.say("   cycle took %.0f s; sleeping %.0f s" % (time.time() - t_cycle, wait))
                if time.time() + wait > end_t:
                    break
                time.sleep(wait)
    finally:
        for n, s in scopes.items():
            try:
                s.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
                s.run()
                s.close()
            except Exception as e:                        # noqa: BLE001
                T.say("scope %s: %r" % (n, e))
        save()
        quiet_all()
        T.say("saved %s (%d captures); %.0f min; done, both quiet" % (path, keeper.k, (time.time() - t0) / 60))


if __name__ == "__main__":
    main()
