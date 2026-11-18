"""Three bits an event: the A8 and B3 schemes (costaslink.SCHEMES, 2026-11-06: the ladders' whole 3 x 3 grid, eight
messages, the four windows deciding) by the decoder on both links, with the receiver's scope on the points (twoscope's
constellation stage: the I / Q paths from the idle to each of the eight and back); and the carrier gap's effect on the
loop (drivennull.py 21:03: the (0, 0) point from the full idle, 200 ns of no carrier 1-in-1000, put both receivers'
loops on the other side): the lock's side after 0.5 s of gaps at several rates and widths.
Records data/twoboard/n8_<stamp>.json / .npz / .jsonl.

    python3 n8test.py [--mhz 4800] [--links AB BA] [--shots 6]
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

LAT_NS = {"AB": 5.8, "BA": 10.0}


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


def flip_capture(L, rs, keeper, pt, period, width, seconds, cycle_tag):
    """the receiver's scope on a slow timebase, triggered by its own I arm falling through the centre (the lock changing
    side) while the events run: how the side changes (a slew over the loop's ~100 us, or a jump)"""
    leg = L.leg()
    L.hold((1, 0))
    time.sleep(0.1)
    dc = TS.scope_dc(rs, (2, 3))
    base = {2: dc[2]["dc"], 3: dc[3]["dc"]}
    sc = max(0.005, min(0.05, 1.2 * leg / TS.GAIN / 4))
    rs.timebase(scale=200e-6, delay=0.0)
    rs.channel(2, scale=sc, offset=-(base[2] - leg / TS.GAIN))       # the centre (no carrier / the other side) mid-screen
    rs.channel(3, scale=sc, offset=-base[3])
    time.sleep(0.2)
    # the level half a leg below the centre: the events themselves take I to the centre (I = 0 for (0, q)), only a
    # change of side takes it past
    rs.trigger(source=2, level=base[2] - 1.5 * leg / TS.GAIN, slope="falling", mode="normal")
    rs.arm()                                              # TRMD SINGLE (the lab driver's, no ARM)
    time.sleep(0.3)
    L.events_on(pt, width, period, idle=(1, 0))
    time.sleep(seconds)
    L.events_off()
    L.hold((1, 0))
    got = None
    try:
        if rs.wait_stop(0.5):
            got = {ch: TS.wave(rs, ch) for ch in (2, 3)}
    except Exception as e:                                # noqa: BLE001
        T.say("   flip capture: %r" % (e,))
    r = {"triggered": got is not None, "leg_mv": 1e3 * leg}
    if got:
        t, v = got[2]
        d = TS.GAIN * (v - base[2]) * 1e3
        r["i_first_mv"] = float(np.median(d[:200]))
        r["i_last_mv"] = float(np.median(d[-200:]))
        # the time I takes from +0.8 leg to -0.8 leg
        lg = 1e3 * leg
        a = TS.cross(t * 1e6, d, 0.8 * lg, False)
        b = TS.cross(t * 1e6, d, -0.8 * lg, False, after=a)
        r["slew_us"] = (b - a) if a is not None and b is not None else None
        keeper.keep([got], stage="flipcap", link=L.name, mhz=L.mhz, point=list(pt), base=base, leg=leg, side=L.s, period=period, width=width, tag=cycle_tag)
        T.say("   flip capture (%s every %d, %d clk): I %+.0f -> %+.0f mV across the screen, +0.8 to -0.8 leg in %s us" % (
            pt, period, width, r["i_first_mv"], r["i_last_mv"], "%.1f" % r["slew_us"] if r["slew_us"] is not None else "-"))
    else:
        T.say("   flip capture (%s every %d, %d clk): the scope did not trigger (no side change in %.1f s)" % (pt, period, width, seconds))
    TS.scope_setup(rs)
    time.sleep(0.2)
    L.ensure()
    return r


def gap_test(L, log, rs=None, keeper=None):
    """the loop's side after carrier gaps: the (0, 0) point from the idle (1, 0) as events of `width` clocks every `period`
    for `seconds`; and the plain flip (-1, 0) the same way as the control"""
    out = []
    if rs is not None:
        for pt, period, width in (((0, 0), 1000, 20), ((0, 0), 1000, 20), ((0, -1), 1000, 20), ((0, 1), 100, 20)):
            try:
                r = flip_capture(L, rs, keeper, pt, period, width, 1.0, "gap")
            except T.LinkDown:
                raise
            except Exception as e:                        # noqa: BLE001
                T.say("   flip capture %s: %r" % (pt, e))
                r = {"error": repr(e)[:200]}
                try:
                    TS.scope_setup(rs)
                except Exception:                         # noqa: BLE001
                    pass
                L.ensure()
            r.update(point=list(pt), period=period, width=width, kind="flipcap")
            out.append(r)
            log(label="n8 flipcap", tag="flipcap", state=L.state(), **r)
    # first a counted number of gaps: 1, 2, 3, 10, 100, 1000 (does one gap flip the side, and is it once per gap?)
    for count in (1, 1, 1, 2, 2, 3, 3, 10, 100, 1001):
        L.ensure()
        s0 = L.s
        L.hold((1, 0))
        time.sleep(0.05)
        o0 = L.ld.observe()
        t = L.tx.cl
        t.events(period=1000, width=20, count=count, source="fixed", n=1)    # the mode first (4.84): in hold mode the
        t.tx_points(L.pt(1, 0), [L.pt(0, 0)])                                   # points' write put (0, 0) out for ms
        t.tx_msg(0)
        t.tx_go()
        time.sleep(0.02 + count * 1e-5)
        t.tx_stop()
        L.hold((1, 0))
        time.sleep(0.05)
        o1 = L.ld.observe()
        flipped = o1["di"] * o0["di"] < 0 and abs(o1["di"]) > 0.005
        r = {"point": [0, 0], "period": 1000, "width": 20, "count": count, "gaps": count, "side_before": s0, "di_before": o0["di"], "dq_before": o0["dq"],
             "di_after": o1["di"], "dq_after": o1["dq"], "locked_after": bool(o1["locked"]), "flipped": bool(flipped), "vc_before": o0["vc"], "vc_after": o1["vc"]}
        out.append(r)
        T.say("   %4d gap(s) of 200 ns: side %+d, I %+.3f -> %+.3f, VC %.4f -> %.4f: %s" % (
            count, s0, o0["di"], o1["di"], o0["vc"], o1["vc"], "FLIPPED" if flipped else ("lost" if not o1["locked"] else "kept")))
        log(label="n8 gap", tag="gap", state=L.state(), **r)
    for pt, period, width, seconds in ((( 0, 0), 1000, 20, 0.5), ((0, 0), 1000, 20, 0.5), ((0, 0), 100000, 20, 1.0), ((0, 0), 10000, 20, 0.5),
                                       ((0, 0), 1000, 5, 0.5), ((0, 0), 1000, 50, 0.5), ((0, 0), 1000, 200, 0.5), ((-1, 0), 1000, 20, 0.5),
                                       ((-1, 0), 1000, 200, 0.5), ((0, 1), 1000, 20, 0.5), ((0, -1), 1000, 20, 0.5), ((-1, 1), 1000, 20, 0.5),
                                       ((-1, -1), 1000, 20, 0.5), ((1, 1), 1000, 20, 0.5), ((0, 1), 100, 20, 0.5), ((0, 0), 1000, 20, 0.5)):
        st = L.ensure()
        s0 = L.s
        L.hold((1, 0))
        time.sleep(0.05)
        o0 = L.ld.observe()
        L.events_on(pt, width, period, idle=(1, 0))
        time.sleep(seconds)
        L.events_off()
        L.hold((1, 0))
        time.sleep(0.05)
        o1 = L.ld.observe()                                # the idle sent on the old side: a negative I means the side changed
        flipped = o1["di"] * o0["di"] < 0 and abs(o1["di"]) > 0.005
        n_gaps = seconds * L.tx.clk_mhz * 1e6 / period
        r = {"point": list(pt), "period": period, "width": width, "seconds": seconds, "gaps": int(n_gaps), "side_before": s0,
             "di_before": o0["di"], "dq_before": o0["dq"], "di_after": o1["di"], "dq_after": o1["dq"], "locked_after": bool(o1["locked"]),
             "flipped": bool(flipped)}
        out.append(r)
        T.say("   gaps %-7s %3d clk every %6d, %.1f s (%6d events): side %+d, I %+.3f -> %+.3f: %s" % (
            "(%d,%d)" % tuple(pt), width, period, seconds, int(n_gaps), s0, o0["di"], o1["di"], "FLIPPED" if flipped else ("lost" if not o1["locked"] else "kept")))
        log(label="n8 gap", tag="gap", state=L.state(), **r)
        L.ensure()                                         # back on a known side for the next trial
    return out


def main():
    mhzs = args_list("--mhz", [4800.0], float)
    links = args_list("--links", ["AB", "BA"])
    nshots = arg("--shots", 6)
    schemes = args_list("--schemes", ["A8", "B3", "A3", "B1"])
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("n8")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "gain": TS.GAIN, "runs": []}
    t0 = time.time()
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            TS.scope_setup(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for mhz in mhzs:
            for lk in links:
                L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz)
                rs, ts = scopes[L.rx.name], scopes[L.tx.name]
                rec = {"link": lk, "mhz": mhz}
                out["runs"].append(rec)
                T.say("==== %s at %g MHz, %.0f min in" % (lk, mhz, (time.time() - t0) / 60))
                try:
                    if not L.up():
                        rec["error"] = "no link"
                        continue
                    rec["lock"] = dict(L.info, side=L.s)
                    log(label="n8 setup", tag="setup", state=L.state(), **L.info)
                    L.tx.cl.triggers(width=10, a="tx_event")
                    L.rx.cl.triggers(width=10, a="tx_event")
                    T.say("---- the carrier gap and the loop's side")
                    rec["gaps"] = gap_test(L, log, rs, keeper)
                    T.say("---- A8 and B3 by the decoder, with the scope on every point")
                    rec["constellations"] = TS.constellation(L, rs, ts, schemes, nshots, keeper, log, True, LAT_NS.get(lk, 8.0))
                    for row in rec["constellations"]:
                        d = row.get("decoder") or {}
                        if "error" in d or "per_msg" not in d:
                            T.say("   %s: %s" % (row["scheme"], d.get("error")))
                            continue
                        T.say("   %s: right %s, min %.4f, idle false %.0f/s, gaps %s, dead %s, vectors %s" % (
                            row["scheme"], ["%.4f" % r["right_frac"] for m, r in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))],
                            d.get("right_frac_min") or 0, d.get("idle_false_per_s") or 0, d.get("gaps_mv"), (d.get("rx_info") or {}).get("dead_windows"),
                            (d.get("rx_info") or {}).get("vectors")))
                    # A8 at the decoder's other knobs: the first-edge decision and a longer delay
                    rec["A8_knobs"] = {}
                    for key, over in (("delay 40", {"delay": 40}), ("first_edge", {"first_edge": True}), ("width 5", {"width": 5}), ("period 100", {"period": 100})):
                        try:
                            d = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A8", **over))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            d = {"error": repr(e)[:200]}
                            L.ensure()
                        rec["A8_knobs"][key] = {k: d.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "gaps_mv", "error")}
                        T.say("   A8 %-10s: %s" % (key, d.get("error") or "right %s, min %.4f, idle false %.0f/s" % (
                            ["%.4f" % r["right_frac"] for m, r in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))], d["right_frac_min"], d.get("idle_false_per_s") or 0)))
                        log(label="n8 A8 %s" % key, tag="events", params=dict(T.EVENTS_BASE, scheme="A8", **over), state=L.state(), **d)
                except T.LinkDown as e:
                    T.say("%s: %s" % (lk, e))
                    rec["error"] = str(e)
                except Exception as e:                    # noqa: BLE001
                    import traceback
                    T.say("%s: %r\n%s" % (lk, e, traceback.format_exc()))
                    rec["error"] = repr(e)[:300]
                finally:
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
        json.dump(out, open(os.path.join(T.DATA, "n8_%s.json" % stamp), "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(os.path.join(T.DATA, "n8_%s.npz" % stamp), meta=json.dumps(keeper.meta), **keeper.arr)
        T.say("saved %s (%d captures); %.0f min" % (os.path.join(T.DATA, "n8_%s" % stamp), keeper.k, (time.time() - t0) / 60))
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
