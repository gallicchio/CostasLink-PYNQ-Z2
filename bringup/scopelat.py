"""The one-way latency on the scope's own clock (QPV_TIMING_REVIEW 6a row 3, LATENCY.md check c): the sender's TRIG OUT A
(J205, silkscreen TRIG A) on scope ch1 and the receiver's CMP I MON (J103) on ch4, both through 50 ohm feed-through
terminators (2026-11-05 15:50: B's TRIG A and A's CMP I MON, the link B -> A over the dishes at 5200).  The sender sends A1's
events (its carrier flipped from idle (1,0) to (-1,0), or the other way) W clocks wide every N clocks, TRIG A marking each;
the scope triggers on ch1's rise and the script takes ch4's first edge after it: the time from the event's mark to the
sign comparator's output, on neither board's sampler.  Against the TRIG IN reference's 132.5 ns (A1, 13:26: B's TRIG A into
A's TRIG IN, the RX engine's own 1.25 ns samples) it calibrates the TRIG path's offset; against the dishes' 139.75 ns
(4.43) it splits the rest between the two boards.

    COSTAS_BENCH_CONFIG=bringup/bench_config_laptop.json python3 bringup/scopelat.py [--tx B --rx A --mhz 5200] [--n 100]
    ... --quick          the base point only
    ... --plan FILE      a JSON list of points instead of the built-in sweep
    ... --report FILE..  no boards: a table of the records

Each point: n single-shot captures; per capture the latency ch1's 50 % rise to ch4's 50 % edge (both interpolated between
1 GSa/s samples), the edge's polarity, and the event's width on ch4 (its second edge).  Records to data/twoboard/scopelat_*.jsonl
(every latency kept), the first capture of each point to data/twoboard/scopelat_*_<k>.npz.  The scope's ch2 and ch3 are
switched off for the sample rate (one ADC per channel pair; the 50 ohm loads on A's I MON and Q MON stay, REVB 34) and put
back; the scope is left running.  Needs the boards to itself.  Mind the cable lengths: a difference of 1 m between the ch1
and ch4 leads is 5 ns of the answer (--skew-ns, ch4's lead minus ch1's, is subtracted).
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import scope_e                                      # noqa: E402
import twoboard as T                                # noqa: E402

DEBUG = 0
TDIVS = [20e-9, 50e-9, 100e-9, 200e-9, 500e-9, 1e-6, 2e-6]
PRE_NS = 150.0                                      # before the trigger on the screen


def screen_for(w_clocks, clk_mhz):
    """(tdiv, delay) so the screen runs from -PRE_NS to the event's end plus a margin"""
    post = 350.0 + w_clocks * 1e3 / clk_mhz
    span = (PRE_NS + post) * 1e-9
    tdiv = next((d for d in TDIVS if 14 * d >= span), TDIVS[-1])
    return tdiv, -(7 * tdiv - PRE_NS * 1e-9)


def single(s, timeout=5.0):
    """one triggered acquisition: TRMD SINGLE and wait for 'Stop'.  Not the driver's arm() (TRMD SINGLE then ARM): on this
    firmware ARM gives records without a trigger (16:05: 4 of 6 captures with no TRIG A pulse in them, the records fresh each
    time), where SINGLE alone, or NORM then STOP, triggered on every pulse 12 of 12 times."""
    s.w("TRMD SINGLE")
    return s.wait_stop(timeout)


def wave(s, ch, delay):
    """the driver's t has the trigger `delay` before the screen centre; on this firmware (8.1.6.1.26, 15:55) a positive TRDL
    puts the trigger `delay` after the centre (ch1's rise at +399 ns on a 50 ns/div screen with TRDL 200 ns), so t is
    moved by 2 * delay to put the trigger at 0"""
    t, v, info = s.waveform(ch)
    return t - 2 * delay, v, info


def cross(t, v, lo, hi, after=None, rising=None):
    """the first 50 % crossing of v between the levels lo and hi after time `after`, linearly interpolated; (time, +1/-1)"""
    mid = 0.5 * (lo + hi)
    k0 = 0 if after is None else int(np.searchsorted(t, after))
    a = v[k0:] > mid
    if rising is True:
        idx = np.flatnonzero(~a[:-1] & a[1:])
    elif rising is False:
        idx = np.flatnonzero(a[:-1] & ~a[1:])
    else:
        idx = np.flatnonzero(a[:-1] != a[1:])
    if not len(idx):
        return None, 0
    k = k0 + idx[0]
    v0, v1 = v[k], v[k + 1]
    f = (mid - v0) / (v1 - v0) if v1 != v0 else 0.5
    return float(t[k] + f * (t[k + 1] - t[k])), (1 if v1 > v0 else -1)


def analyse(t1, v1, t4, v4):
    """ch1's rise, ch4's first edge after it and its return: latency, polarity, width (ns)"""
    r = {}
    pre1 = v1[t1 < -30e-9]
    lo1 = float(np.median(pre1)) if len(pre1) else float(v1.min())
    hi1 = float(np.percentile(v1, 98))
    tr, _ = cross(t1, v1, lo1, hi1, rising=True)
    if tr is None:
        return {"error": "no rise on ch1", "ch1_lo": lo1, "ch1_hi": hi1}
    base4 = float(np.median(v4[t4 < tr]))             # the comparator before the event
    dev = v4 - base4
    k = int(np.argmax(np.abs(dev)))
    step = float(dev[k])                               # the event's level, as the largest excursion
    r.update(ch1_lo=lo1, ch1_hi=hi1, ch1_rise_ns=tr * 1e9, ch4_base=base4, ch4_step=step)
    noise = float(np.std(v4[t4 < tr])) if np.sum(t4 < tr) > 4 else 0.0
    r["ch4_noise"] = noise
    r["ch4_n_pre"] = int(np.sum(t4 < tr))
    if abs(step) < max(8 * noise, 0.03):
        r["error"] = "no edge on ch4"
        return r
    te, pol = cross(t4, v4, base4, base4 + step, after=tr, rising=(step > 0))
    if te is None:
        r["error"] = "no edge on ch4 after the mark"
        return r
    r["latency_ns"] = (te - tr) * 1e9
    r["polarity"] = pol
    tb, _ = cross(t4, v4, base4, base4 + step, after=te + 2e-9, rising=(step < 0))
    r["width_ns"] = None if tb is None else (tb - te) * 1e9
    return r


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else None


def capture_point(s, link, p, n, skew_ns, stamp, k, log):
    """p: dict(w, period, dsa, flip ('down': idle (1,0) -> (-1,0), 'up': the other way)); n captures"""
    tx, rx = link.tx.cl, link.rx.cl
    out = {"exp": "scopelat", "when": time.strftime("%Y-%m-%d %H:%M:%S"), "k": k, "skew_ns": skew_ns, **p}
    rx.dsa(link.info.get("dsa", rx._dsa_db))
    st = link.ensure()
    out["look"] = st
    if not st["locked"]:
        out["error"] = "no lock"
        return out
    if p.get("dsa") is not None:
        rx.dsa(p["dsa"])
        time.sleep(0.05)
        out["side_at_level"] = link.recheck_side()
    out["leg"] = link.leg()
    out["rx_dsa"] = rx._dsa_db
    tx.triggers(width=10, a="tx_event")
    idle, pt = ((1, 0), (-1, 0)) if p.get("flip", "down") == "down" else ((-1, 0), (1, 0))
    tdiv, delay = screen_for(p["w"], link.tx.clk_mhz)
    s.timebase(scale=tdiv, delay=delay)
    s.trigger(source=1, level=0.85, slope="rising", mode="single")
    link.events_on(pt, p["w"], p["period"], idle=idle)
    time.sleep(0.1)
    lat, pol, wid, errs, first = [], [], [], {}, None
    try:
        for i in range(n):
            try:
                single(s)
            except TimeoutError:
                errs["no trigger"] = errs.get("no trigger", 0) + 1
                continue
            t1, v1, i1 = wave(s, 1, delay)
            t4, v4, i4 = wave(s, 4, delay)
            if first is None:
                first = {"t1": t1, "v1": v1, "t4": t4, "v4": v4, "info": json.dumps({"1": i1, "4": i4})}
                out["sample_rate"] = i1["sample_rate"]
                out["tdiv"] = tdiv
            a = analyse(t1, v1, t4, v4)
            if DEBUG:
                print("   cap %d: %s" % (i, {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in a.items()}), flush=True)
                if "error" in a and DEBUG > 1:
                    np.savez_compressed(os.path.join(T.DATA, "scopelat_%s_%d_cap%d.npz" % (stamp, k, i)), t1=t1, v1=v1, t4=t4, v4=v4)
            if "error" in a:
                errs[a["error"]] = errs.get(a["error"], 0) + 1
                continue
            lat.append(a["latency_ns"] - skew_ns)
            pol.append(a["polarity"])
            if a["width_ns"] is not None:
                wid.append(a["width_ns"])
            if i == 0:
                out["first"] = {kk: a[kk] for kk in ("ch1_lo", "ch1_hi", "ch1_rise_ns", "ch4_base", "ch4_step")}
    finally:
        link.events_off()
        if p.get("dsa") is not None:
            rx.dsa(link.info.get("dsa", rx._dsa_db))
    if first is not None:
        np.savez_compressed(os.path.join(T.DATA, "scopelat_%s_%d.npz" % (stamp, k)), **first)
    lat = np.array(lat)
    out.update(n=int(len(lat)), errors=errs, latencies_ns=[round(float(x), 2) for x in lat],
               polarity_up=int(sum(1 for x in pol if x > 0)), polarity_down=int(sum(1 for x in pol if x < 0)))
    if len(lat):
        out.update(p50_ns=pct(lat, 50), mean_ns=float(lat.mean()), std_ns=float(lat.std()), min_ns=float(lat.min()),
                   max_ns=float(lat.max()), p1_ns=pct(lat, 1), p99_ns=pct(lat, 99))
    if len(wid):
        w = np.array(wid)
        out.update(width_p50_ns=pct(w, 50), width_min_ns=float(w.min()), width_max_ns=float(w.max()))
    log(state=link.state(), **out)
    print("%s k%d %s: n %d, latency p50 %s mean %s std %s min %s max %s ns; width p50 %s; polarity +%d/-%d; errors %s; leg %s" % (
        time.strftime("%H:%M:%S"), k, {kk: p[kk] for kk in ("w", "period", "dsa", "flip") if kk in p}, out["n"],
        _f(out.get("p50_ns")), _f(out.get("mean_ns")), _f(out.get("std_ns")), _f(out.get("min_ns")), _f(out.get("max_ns")),
        _f(out.get("width_p50_ns")), out["polarity_up"], out["polarity_down"], errs or "none",
        _f(None if out.get("leg") is None else out["leg"] * 1e3)), flush=True)
    return out


def _f(x):
    return "-" if x is None else ("%.2f" % x if isinstance(x, float) else str(x))


def plan(quick=False):
    base = {"w": 20, "period": 1000, "dsa": None, "flip": "down"}
    pts = [dict(base, tag="base")]
    if quick:
        return pts
    pts.append(dict(base, tag="flip", flip="up"))
    for d in (0, 4, 7.75, 12, 16, 20, 24, 28):
        pts.append(dict(base, tag="dsa", dsa=d))
    for w in (2, 5, 10, 40, 100):
        pts.append(dict(base, tag="w", w=w))
    for per in (100, 300, 10000):
        pts.append(dict(base, tag="period", period=per))
    pts.append(dict(base, tag="base_again"))
    return pts


def report(paths):
    """a markdown table of scopelat records"""
    rows = []
    for path in paths:
        for line in open(path):
            r = json.loads(line)
            if r.get("exp") == "scopelat":
                rows.append(r)
    print("| k | tag | flip | W clocks | period | DSA | leg mV | n | p50 ns | mean | std | min | max | p1 | p99 | width p50 | polarity +/- | errors |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %d/%d | %s |" % (
            r.get("k"), r.get("tag"), r.get("flip"), r.get("w"), r.get("period"), "link" if r.get("dsa") is None else r["dsa"],
            _f(None if r.get("leg") is None else r["leg"] * 1e3), r.get("n"), _f(r.get("p50_ns")), _f(r.get("mean_ns")),
            _f(r.get("std_ns")), _f(r.get("min_ns")), _f(r.get("max_ns")), _f(r.get("p1_ns")), _f(r.get("p99_ns")),
            _f(r.get("width_p50_ns")), r.get("polarity_up", 0), r.get("polarity_down", 0),
            ", ".join("%s %d" % kv for kv in (r.get("errors") or {}).items()) or (r.get("error") or "")))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tx", default="B")
    ap.add_argument("--rx", default="A")
    ap.add_argument("--mhz", type=float, default=5200.0)
    ap.add_argument("--n", type=int, default=100, help="captures a point")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--plan", default=None)
    ap.add_argument("--skew-ns", type=float, default=0.0, help="ch4's lead minus ch1's, subtracted")
    ap.add_argument("--note", default="")
    ap.add_argument("--debug", type=int, default=0, help="1: each capture's analysis; 2: and the failed captures' waveforms")
    ap.add_argument("--report", nargs="+", default=None, help="no boards: a table of these records")
    a = ap.parse_args(argv)
    if a.report:
        report(a.report)
        return 0
    global DEBUG
    DEBUG = a.debug
    pts = json.load(open(a.plan)) if a.plan else plan(a.quick)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("scopelat")
    txn, rxn = T.Node(a.tx), T.Node(a.rx)
    s = scope_e.open_scope()
    chan = {ch: s.channel(ch) for ch in (1, 2, 3, 4)}
    try:
        s.channel(2, on=False)
        s.channel(3, on=False)
        s.channel(1, on=True, scale=0.5, offset=-0.85, coupling="DC", probe=1)
        s.channel(4, on=True, scale=0.1, offset=0.0, coupling="DC", probe=1)
        link = T.Link(txn, rxn, a.mhz)
        if not link.up():
            print("no link %s at %g" % (link.name, a.mhz))
            return 1
        print("link %s at %g up: %s; %d points, %d captures each; note %r" % (link.name, a.mhz, link.state(), len(pts), a.n, a.note),
              flush=True)
        # a first look at ch4's levels: its scale from the step
        link.tx.cl.triggers(width=10, a="tx_event")
        link.events_on((-1, 0), 20, 1000)
        tdiv0, delay0 = screen_for(20, link.tx.clk_mhz)
        s.timebase(scale=tdiv0, delay=delay0)
        s.trigger(source=1, level=0.85, slope="rising", mode="single")
        time.sleep(0.1)
        single(s)
        t1, v1, i1 = wave(s, 1, delay0)
        t4, v4, i4 = wave(s, 4, delay0)
        link.events_off()
        lo, hi = float(np.percentile(v4, 2)), float(np.percentile(v4, 98))
        a0 = analyse(t1, v1, t4, v4)
        print("first look: ch1 %.2f to %.2f V, its rise at %s ns on the screen; ch4 %.3f to %.3f V (%.0f mV step); %.3g Sa/s, %d points;"
              " latency %s ns, width %s ns%s" % (float(np.percentile(v1, 2)), float(np.percentile(v1, 98)), _f(a0.get("ch1_rise_ns")),
                                                lo, hi, (hi - lo) * 1e3, i4["sample_rate"], i4["points"], _f(a0.get("latency_ns")),
                                                _f(a0.get("width_ns")), ("; " + a0["error"]) if "error" in a0 else ""), flush=True)
        if hi - lo > 0.02:
            vdiv = next((d for d in (0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0) if 6 * d >= (hi - lo) * 1.3), 1.0)
            s.channel(4, scale=vdiv, offset=-(lo + hi) / 2)
        for k, p in enumerate(pts):
            capture_point(s, link, p, a.n, a.skew_ns, stamp, k, log)
    finally:
        try:
            txn.quiet()
            rxn.quiet()
        except Exception as e:
            print("quiet:", e)
        for ch, c in chan.items():
            try:
                s.channel(ch, on=c["on"], scale=c["scale"], offset=c["offset"])
            except Exception:
                pass
        try:
            s.run()
        finally:
            s.close()
    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
