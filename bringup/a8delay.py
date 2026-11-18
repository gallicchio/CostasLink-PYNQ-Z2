"""The shortest decision delay that still decodes every message, per scheme, over the cables: A8 (3 bits an event), A3
(2 bits), A2 / A1 (1 bit) against RX_DELAY (samples of 1.25 ns after the first comparator fires), the settled decision
(ID 11: decide once the vector has held `settle` samples, RX_DELAY the cap), and the shortest event width at the shortest
delay.  First the counted carrier-gap trials with the register order fixed (n8test.gap_test, no scope).
    python3 a8delay.py [--mhz 4800] [--links AB BA]   ->  data/twoboard/a8delay_<stamp>.json"""
import json
import os
import sys
import time

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import twoboard as T                                      # noqa: E402
import n8test as N8                                       # noqa: E402

PLAN = [("A8", {"delay": d}) for d in (16, 12, 10, 8, 6, 4, 2)] + \
       [("A3", {"delay": d}) for d in (12, 8, 6, 4, 2)] + \
       [("A2", {"delay": d}) for d in (4, 2)] + [("A1", {"delay": d}) for d in (4, 2)] + \
       [("A8", {"settle": s}) for s in (2, 4, 6, 8)] + [("A3", {"settle": s}) for s in (2, 6)]


def arg(name, default, cast=float):
    if name in sys.argv:
        return cast(sys.argv[sys.argv.index(name) + 1])
    return default


def args_list(name, default, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name) + 1
    out = []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(cast(sys.argv[i]))
        i += 1
    return out or default


def one(L, log, sc, over, tag):
    p = dict(T.EVENTS_BASE, scheme=sc, **over)
    try:
        d = T.events_point(L, **p)
    except T.LinkDown:
        raise
    except Exception as e:                                # noqa: BLE001
        d = {"error": repr(e)[:200]}
        L.ensure()
    r = {k: d.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "gaps_mv", "error", "leg", "rx_info")}
    r.update(scheme=sc, params=p, tag=tag)
    knob = ", ".join("%s %s" % kv for kv in over.items())
    if d.get("error") or "per_msg" not in d:
        T.say("   %-3s %-10s: %s" % (sc, knob, d.get("error")))
    else:
        T.say("   %-3s %-10s: right %s, min %.4f, idle false %.0f/s" % (
            sc, knob, " ".join("%.4f" % rr["right_frac"] for m, rr in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))),
            d["right_frac_min"], d.get("idle_false_per_s") or 0))
    log(label="a8delay %s %s" % (sc, knob), tag="events", params=p, state=L.state(), **d)
    return r


def main():
    mhz = arg("--mhz", 4800.0)
    links = args_list("--links", ["AB", "BA"])
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("a8delay")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    out = {"stamp": stamp, "mhz": mhz, "runs": []}
    t0 = time.time()
    try:
        for lk in links:
            L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz)
            rec = {"link": lk, "mhz": mhz, "points": []}
            out["runs"].append(rec)
            T.say("==== %s at %g MHz, %.0f min in" % (lk, mhz, (time.time() - t0) / 60))
            try:
                if not L.up():
                    rec["error"] = "no link"
                    continue
                rec["lock"] = dict(L.info, side=L.s)
                log(label="a8delay setup", tag="setup", state=L.state(), **L.info)
                T.say("---- the counted carrier gaps, the mode written before the points")
                rec["gaps"] = N8.gap_test(L, log)
                T.say("---- the decision delay, the settled decision")
                for sc, over in PLAN:
                    rec["points"].append(one(L, log, sc, over, "delay"))
                good = sorted(r["params"]["delay"] for r in rec["points"] if r["scheme"] == "A8" and not r["params"].get("settle")
                              and (r.get("right_frac_min") or 0) >= 0.9999)
                dmin = good[0] if good else 16
                rec["a8_min_delay"] = dmin
                T.say("---- the shortest event at A8's shortest delay %d (%.2f ns)" % (dmin, 1.25 * dmin))
                for w in (2, 3, 5):
                    rec["points"].append(one(L, log, "A8", {"delay": dmin, "width": w}, "width"))
                T.say("---- A8 at delay %d repeated with 10x the events" % dmin)
                rec["points"].append(one(L, log, "A8", {"delay": dmin, "count": 200000}, "long"))
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
        json.dump(out, open(os.path.join(T.DATA, "a8delay_%s.json" % stamp), "w"), indent=1, default=str)
        T.say("saved %s; %.0f min" % (os.path.join(T.DATA, "a8delay_%s" % stamp), (time.time() - t0) / 60))
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
