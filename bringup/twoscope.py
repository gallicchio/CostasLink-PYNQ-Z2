"""The two scopes (A on board A's monitors, B on board B's; BRINGUP_LOG 4.74's cabling) checked against the boards, then
every scheme's constellation on each receiver with the decoder's own view beside it, then the flip against the level.
BRINGUP_LOG 4.75 (2026-11-06): every check passed on both scopes; the mark reaches CMP I 4-5 ns later over the FPV pair
and 144 ns later over the dishes; B's transmitter leaks 13-17 % into quadrature with its I ladder driven, A's 3 %; B's
receiver carries a +25 mV Q offset (the flipped point's Q, a constant 2 x the offset), A's none.

Per link (B -> A on scope A, A -> B on scope B), at the lock's level:
  1. cabling: the idle (1, 0), the flip (-1, 0) and (legs over 80 mV) the carrier null (0, 0) held while the receiver's
     ADC, its comparator state and both scopes' DC levels are read: I MON / Q MON x21 against the ADC, CMP I MON against
     CMP_I, the ladder's flip against the ADC's; then the flip as events while the receiver's scope triggers on the
     sender's TRIG A (ch1): the mark's height and width, the mark-to-CMP-I latency, the I arm's crossing against CMP I's
     edge.
  2. constellations: per scheme, events_point (the decoder: windows, tables, the right fraction per message), then each
     message's events held on while the receiver's scope captures the mark, I, Q and CMP I (n shots): the plateau, the
     spike and the return of I and Q per point, as mV at the arm, relative to the idle's ADC position.
  3. the flip against the level (A1 at the lock's DSA, then --levels): the Q plateau against the leg; fitted by
     twoscope_fig.py as 2 x (the receiver's Q offset) + (the sender's leak) x leg.
Saves data/twoboard/twoscope_<stamp>.json / .npz and records to data/twoboard/twoscope_<stamp>.jsonl; the boards quiet
and the scopes back in AUTO at the end.  The pages: python3 twoscope_fig.py twoscope_<stamp>.

    python3 twoscope.py [--mhz 5400] [--links BA AB] [--schemes A1 A1w A2 A3 A4 B1 B2] [--shots 8] [--levels 7.75 4]
                        [--no-decoder]

The scopes: each input through a 50 ohm feed-through (the SDS1000X-E is 1 Mohm only); the arms through their 1 k taps
read 1/21 of the arm.  An offset is kept in divisions across a scale change, so a scale is always set with its offset
(both scopes clipped once, 11-06 12:10); I gets a scale for 2.6 legs (the flip and its overshoot), Q for 1.8 (the
corners and the spike).
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import costaslink as C                                    # noqa: E402
import scope_e                                            # noqa: E402  (open_scope by serial)

GAIN = 21.0                                               # the 1 k tap into 50 ohm: x21 to the arm
NOMINAL = 1.65 / GAIN                                     # an arm's centre at the scope
TDIV = 100e-9
PRE = 200e-9                                              # the screen starts this long before the trigger
DELAY = -(7 * TDIV - PRE)                                 # this firmware: a positive TRDL puts the trigger after the centre
SCALES = [0.002, 0.005, 0.01, 0.02, 0.05]
CH = {1: "TRIG A", 2: "I MON", 3: "Q MON", 4: "CMP I MON"}
MARK_V, CMP_V = 0.85, 0.15                                # the mark's and the comparator's thresholds at the scope
OUT = T.DATA


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


# ---------------------------------------------------------------------------------------------------------------------
# the scopes
# ---------------------------------------------------------------------------------------------------------------------
def single(s, timeout=3.0):
    s.w("TRMD SINGLE")
    try:
        return s.wait_stop(timeout)
    except TimeoutError:
        return False


def wave(s, ch):
    """(t, v) of a channel's last acquisition, t in seconds with the trigger at 0"""
    t, v, info = s.waveform(ch)
    return t - 2 * DELAY, v


def shots(s, src, level, slope, n, chans):
    """n single acquisitions triggered on `src`; each {ch: (t, v)}"""
    out, misses = [], 0
    t0 = time.time()
    s.trigger(source=src, level=level, slope=slope, mode="normal")
    time.sleep(0.2)
    while len(out) < n and misses < 3 and time.time() - t0 < 60:
        if not single(s, 3.0):
            misses += 1
            continue
        misses = 0
        out.append({ch: wave(s, ch) for ch in chans})
    return out


def scope_setup(s, scale=0.005):
    s.timebase(scale=TDIV, delay=DELAY)
    s.channel(1, on=True, scale=0.5, offset=-0.85, coupling="DC", probe=1)
    s.channel(2, on=True, scale=scale, offset=-NOMINAL, coupling="DC", probe=1)
    s.channel(3, on=True, scale=scale, offset=-NOMINAL, coupling="DC", probe=1)
    s.channel(4, on=True, scale=0.1, offset=-0.15, coupling="DC", probe=1)
    s.trigger(source=1, level=MARK_V, slope="rising", mode="auto")


def scope_dc(s, chans=(1, 2, 3, 4), n=1):
    """one AUTO acquisition: each channel's median (V at the scope), its max and min"""
    out = {}
    for _ in range(n):
        s.acquire_now()
        for ch in chans:
            t, v, info = s.waveform(ch)
            out.setdefault(ch, []).append((float(np.median(v)), float(v.max()), float(v.min())))
    s.run()
    return {ch: {"dc": float(np.median([r[0] for r in rows])), "max": max(r[1] for r in rows), "min": min(r[2] for r in rows)}
            for ch, rows in out.items()}


def arm_scales(leg):
    """(I's, Q's) V/div: the flip swings I by 2 legs (plus the overshoot), the corners swing Q by 1.4 legs (plus the
    spike); each must fit in the 4 divisions below / above the centred idle"""
    need_i, need_q = 2.6 * leg / GAIN / 4, 1.8 * leg / GAIN / 4
    si = next((x for x in SCALES if x >= need_i), SCALES[-1])
    sq = next((x for x in SCALES if x >= need_q), SCALES[-1])
    return si, sq


def set_arms(s, leg):
    """ch2 / ch3 at the scales the leg needs, the offset set with the scale"""
    si, sq = arm_scales(leg)
    s.channel(2, scale=si, offset=-NOMINAL)
    s.channel(3, scale=sq, offset=-NOMINAL)
    time.sleep(0.3)
    return si, sq


def centre(s, chans=(2, 3)):
    """ch2 / ch3 centred on their DC (the trace in the middle of the screen); returns the DC read after centring.
    A DC more than 30 mV from the nominal cannot be an arm (1.65 +- 0.6 V): the channel is left at the nominal."""
    dc = scope_dc(s, chans)
    for ch in chans:
        if abs(dc[ch]["dc"] - NOMINAL) < 0.03:
            s.channel(ch, offset=-dc[ch]["dc"])
        else:
            T.say("   scope ch%d reads %.4f V: not an arm's level; left at the nominal offset" % (ch, dc[ch]["dc"]))
            s.channel(ch, offset=-NOMINAL)
    time.sleep(0.3)
    return {ch: scope_dc(s, (ch,))[ch]["dc"] for ch in chans}


# ---------------------------------------------------------------------------------------------------------------------
# a shot's numbers
# ---------------------------------------------------------------------------------------------------------------------
def cross(t, v, level, rising=None, after=None):
    """the first time v crosses level (rising / falling / either) after `after` (ns), by linear interpolation"""
    m = np.ones(len(t), bool) if after is None else (t >= after)
    idx = np.where(m)[0]
    if len(idx) < 2:
        return None
    a, b = v[idx[:-1]], v[idx[1:]]
    if rising is True:
        hit = (a < level) & (b >= level)
    elif rising is False:
        hit = (a >= level) & (b < level)
    else:
        hit = ((a < level) & (b >= level)) | ((a >= level) & (b < level))
    k = np.where(hit)[0]
    if not len(k):
        return None
    i = idx[k[0]]
    f = (level - v[i]) / (v[i + 1] - v[i]) if v[i + 1] != v[i] else 0.0
    return float(t[i] + f * (t[i + 1] - t[i]))


def shot_numbers(g, base, lat_ns=None):
    """g: {ch: (t, v)}; base: {2: V, 3: V} the idle's DC; the mark, the arms' deltas (mV at the arm) in windows after the
    event's arrival (CMP I's edge when it moves, else the mark + lat_ns)"""
    t1, v1 = g[1]
    t1 = t1 * 1e9
    r = {"mark_high": float(v1.max()), "mark_t": cross(t1, v1, MARK_V, True)}
    r["mark_width"] = None
    if r["mark_t"] is not None:
        fall = cross(t1, v1, MARK_V, False, after=r["mark_t"])
        r["mark_width"] = None if fall is None else fall - r["mark_t"]
    t4, v4 = g[4]
    t4 = t4 * 1e9
    pre4 = float(np.median(v4[(t4 > -150) & (t4 < -20)]))
    r["cmp_idle"] = int(pre4 > CMP_V)
    r["cmp_edge_t"] = cross(t4, v4, CMP_V, not r["cmp_idle"], after=-20)
    if r["cmp_edge_t"] is not None:
        back = cross(t4, v4, CMP_V, bool(r["cmp_idle"]), after=r["cmp_edge_t"] + 5)
        r["cmp_width"] = None if back is None else back - r["cmp_edge_t"]
    t0 = r["cmp_edge_t"] if r["cmp_edge_t"] is not None else ((r["mark_t"] or 0.0) + (lat_ns or 0.0))
    r["t0"] = t0
    for ch, nm in ((2, "i"), (3, "q")):
        t, v = g[ch]
        t = t * 1e9
        d = GAIN * (v - base[ch]) * 1e3
        pre = float(np.median(d[(t > -150) & (t < -20)]))
        d = d - pre
        sel = lambda a, b: d[(t > t0 + a) & (t < t0 + b)]                                  # noqa: E731
        pl = sel(60, 180)
        r[nm + "_pre"] = pre                                                                # the idle against the centring (drift)
        r[nm + "_plateau"] = float(np.median(pl)) if len(pl) else None
        r[nm + "_spike_min"] = float(sel(0, 40).min()) if len(sel(0, 40)) else None
        r[nm + "_spike_max"] = float(sel(0, 40).max()) if len(sel(0, 40)) else None
        r[nm + "_ret_min"] = float(sel(200, 260).min()) if len(sel(200, 260)) else None
        r[nm + "_ret_max"] = float(sel(200, 260).max()) if len(sel(200, 260)) else None
        if r[nm + "_plateau"] is not None and abs(r[nm + "_plateau"]) > 10:
            half = r[nm + "_plateau"] / 2
            r[nm + "_cross_t"] = cross(t, d, half, r[nm + "_plateau"] > 0, after=-20)      # the arm's half-way time
            r[nm + "_rise"] = None
            a = cross(t, d, 0.1 * r[nm + "_plateau"], r[nm + "_plateau"] > 0, after=-20)
            b = cross(t, d, 0.9 * r[nm + "_plateau"], r[nm + "_plateau"] > 0, after=-20)
            if a is not None and b is not None:
                r[nm + "_rise"] = b - a
        else:
            r[nm + "_cross_t"] = r[nm + "_rise"] = None
    return r


def med(rows, key):
    xs = [r[key] for r in rows if r.get(key) is not None]
    return float(np.median(xs)) if xs else None


# ---------------------------------------------------------------------------------------------------------------------
# the stages
# ---------------------------------------------------------------------------------------------------------------------
class Keeper:
    def __init__(self):
        self.arr, self.meta, self.k = {}, [], 0

    def keep(self, got, **extra):
        for g in got:
            for ch, (t, v) in g.items():
                self.arr["t%d_%d" % (ch, self.k)] = t.astype(np.float32)
                self.arr["v%d_%d" % (ch, self.k)] = v.astype(np.float32)
            self.meta.append(dict(extra, k=self.k))
            self.k += 1


def static(L, rs, ts, label, point, null=False):
    """a point held: the receiver's ADC, comparator and both scopes' DC"""
    if null:
        (vi0, vq0), _ = L.tx.vr(L.mhz)
        L.tx.cl.dac(VR_I=vi0, VR_Q=vq0)
        L.tx.cl.hold_point(0, 0)
    else:
        L.hold(point)
    time.sleep(0.15)
    o = L.ld.observe()
    adc = L.rx.cl.adc_all()
    cmp_ = L.rx.cl.cmp_state()
    row = {"label": label, "point": point, "di": o["di"], "dq": o["dq"], "vc": o["vc"], "locked": bool(o["locked"]),
           "adc": adc, "cmp_i": cmp_["CMP_I"], "rx_scope": scope_dc(rs), "tx_scope": scope_dc(ts)}
    row["i_scope"] = GAIN * row["rx_scope"][2]["dc"]
    row["q_scope"] = GAIN * row["rx_scope"][3]["dc"]
    row["cmp_scope"] = int(row["rx_scope"][4]["dc"] > CMP_V)
    T.say("   %-5s di %+.3f dq %+.3f | ADC I %.3f Q %.3f CMP_I %d | scope %s: I %.3f Q %.3f CMP %d TRIG %.2f | scope %s: ch1 max %.2f I %.3f Q %.3f CMP %.2f" % (
        label, o["di"], o["dq"], adc["I"], adc["Q"], cmp_["CMP_I"], L.rx.name, row["i_scope"], row["q_scope"], row["cmp_scope"],
        row["rx_scope"][1]["max"], L.tx.name, row["tx_scope"][1]["max"], GAIN * row["tx_scope"][2]["dc"], GAIN * row["tx_scope"][3]["dc"],
        row["tx_scope"][4]["dc"]))
    return row


def cabling(L, rs, ts, nshots, keeper, log):
    out = {"stage": "cabling", "link": L.name, "mhz": L.mhz, "rows": [], "verdicts": []}
    L.tx.cl.triggers(width=10, a="tx_event")
    L.rx.cl.triggers(width=10, a="tx_event")               # the receiver's TRIG A (the sender's scope's ch1) marks nothing
    leg = L.leg()
    out["leg"] = leg
    out["scales"] = set_arms(rs, leg)
    set_arms(ts, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    out["rx_centred"] = centre(rs)
    out["tx_centred"] = centre(ts)
    rows = out["rows"]
    rows.append(static(L, rs, ts, "idle", (1, 0)))
    rows.append(static(L, rs, ts, "flip", (-1, 0)))
    if leg >= 0.08:                                       # the null unlocks the loop: a weak link may not come back (AB at 5400, 12:10)
        rows.append(static(L, rs, ts, "null", (0, 0), null=True))
        L.hold((1, 0))
        time.sleep(0.2)
        st = L.ensure()
        out["after_null"] = st
        rows.append(static(L, rs, ts, "idle2", (1, 0)))
    else:
        T.say("   the carrier null skipped: the leg %.0f mV is too weak to risk the lock" % (1e3 * leg))
    v = out["verdicts"]
    idle, flip = rows[0], rows[1]
    for nm, k, a in (("I MON", "i_scope", "I"), ("Q MON", "q_scope", "Q")):
        for r in rows[:3]:
            err = r[k] - r["adc"][a]
            v.append("%s at %s: scope x21 %.3f V, ADC %.3f V, off by %+.0f mV: %s" % (
                nm, r["label"], r[k], r["adc"][a], 1e3 * err, "ok" if abs(err) < 0.15 else "WRONG (the cable, the jack or the terminator)"))
    di_s, di_a = flip["i_scope"] - idle["i_scope"], flip["adc"]["I"] - idle["adc"]["I"]
    v.append("the flip's I step: scope %+.0f mV, ADC %+.0f mV (ratio %.2f): %s" % (
        1e3 * di_s, 1e3 * di_a, di_s / di_a if di_a else float("nan"),
        "ok (polarity and x21)" if di_a and 0.8 < di_s / di_a < 1.25 else "WRONG"))
    for r in (idle, flip):
        v.append("CMP I MON at %s: scope %.2f V -> %d, CMP_I %d: %s" % (
            r["label"], r["rx_scope"][4]["dc"], r["cmp_scope"], r["cmp_i"], "ok" if r["cmp_scope"] == r["cmp_i"] else "WRONG"))
    if idle["cmp_i"] == flip["cmp_i"]:
        v.append("CMP_I did not change between the idle and the flip: no flip seen by the comparator?")
    v.append("scope %s ch1 (board %s's TRIG A) while idle: max %.2f V (%s)" % (
        L.rx.name, L.tx.name, idle["rx_scope"][1]["max"], "quiet, ok" if idle["rx_scope"][1]["max"] < 0.3 else "marks or noise on it"))
    v.append("scope %s ch1 (board %s's TRIG A, no events there): max %.2f V (%s)" % (
        L.tx.name, L.rx.name, idle["tx_scope"][1]["max"], "quiet, ok" if idle["tx_scope"][1]["max"] < 0.3 else "something on it"))
    v.append("scope %s (the sender's own arms, no carrier at its receiver): I %.3f Q %.3f V, CMP %.2f V" % (
        L.tx.name, GAIN * idle["tx_scope"][2]["dc"], GAIN * idle["tx_scope"][3]["dc"], idle["tx_scope"][4]["dc"]))
    # the marks: the flip as events, the receiver's scope on the sender's TRIG A
    L.hold((1, 0))
    time.sleep(0.05)
    b = scope_dc(rs, (2, 3))
    base = {2: b[2]["dc"], 3: b[3]["dc"]}
    L.events_on((-1, 0), 20, 1000, idle=(1, 0))
    time.sleep(0.05)
    got = shots(rs, 1, MARK_V, "rising", nshots, (1, 2, 3, 4))
    tx_during = scope_dc(ts)
    L.events_off()
    L.hold((1, 0))
    rs.trigger(source=1, level=MARK_V, slope="rising", mode="auto")
    nums = [shot_numbers(g, base) for g in got]
    keeper.keep(got, stage="cabling", link=L.name, mhz=L.mhz, scheme="A1", m=0, point=[-1, 0], base=base, leg=leg, side=L.s)
    out["marks"] = {"n": len(got), "mark_high": med(nums, "mark_high"), "mark_t": med(nums, "mark_t"), "mark_width": med(nums, "mark_width"),
                    "cmp_edge_t": med(nums, "cmp_edge_t"), "cmp_width": med(nums, "cmp_width"), "i_cross_t": med(nums, "i_cross_t"),
                    "i_rise": med(nums, "i_rise"), "i_plateau": med(nums, "i_plateau"), "q_plateau": med(nums, "q_plateau"),
                    "q_spike_min": med(nums, "q_spike_min"), "tx_scope_during": tx_during,
                    "latency_ns": None, "cmp_delay_ns": None}
    mk = out["marks"]
    if mk["mark_t"] is not None and mk["cmp_edge_t"] is not None:
        mk["latency_ns"] = mk["cmp_edge_t"] - mk["mark_t"]
    if mk["i_cross_t"] is not None and mk["cmp_edge_t"] is not None:
        mk["cmp_delay_ns"] = mk["cmp_edge_t"] - mk["i_cross_t"]
    v.append("TRIG A on scope %s: %d of %d shots, the mark %.2f V high (%s), %.0f ns wide, at t %+.1f ns" % (
        L.rx.name, len(got), nshots, mk["mark_high"] or 0, "terminated, ok" if mk["mark_high"] and 1.2 < mk["mark_high"] < 2.2 else
        ("UNTERMINATED (3.3 V)" if (mk["mark_high"] or 0) > 2.6 else "no mark"), mk["mark_width"] or 0, mk["mark_t"] or 0))
    v.append("the mark to CMP I's edge: %s ns; the I arm's half-way to CMP I's edge: %s ns; I's 10-90 %% %s ns; the flip's I %s mV, Q %s mV (%.2f of the leg %.0f mV)" % (
        "%.1f" % mk["latency_ns"] if mk["latency_ns"] is not None else "-", "%.1f" % mk["cmp_delay_ns"] if mk["cmp_delay_ns"] is not None else "-",
        "%.1f" % mk["i_rise"] if mk["i_rise"] is not None else "-", "%.0f" % mk["i_plateau"] if mk["i_plateau"] is not None else "-",
        "%.0f" % mk["q_plateau"] if mk["q_plateau"] is not None else "-", (mk["q_plateau"] or 0) / (1e3 * leg) if leg else 0, 1e3 * leg))
    v.append("scope %s ch1 while the events ran (board %s's TRIG A): max %.2f V" % (L.tx.name, L.rx.name, tx_during[1]["max"]))
    for x in v:
        T.say("   " + x)
    log(label="twoscope cabling", tag="cabling", state=L.state(), **{k: val for k, val in out.items() if k != "rows"})
    return out


def constellation(L, rs, ts, schemes, nshots, keeper, log, want_decoder, lat_ns):
    out = []
    for sc in schemes:
        sch = C.SCHEMES[sc]
        row = {"stage": "constellation", "link": L.name, "mhz": L.mhz, "scheme": sc, "points": []}
        dec = None
        if want_decoder:
            try:
                dec = T.events_point(L, **dict(T.EVENTS_BASE, scheme=sc))
            except Exception as e:                        # noqa: BLE001
                T.say("%s: events_point %r" % (sc, e))
                dec = {"error": repr(e)[:200]}
                L.ensure()
            row["decoder"] = dec
            if "error" not in dec:
                T.say("%s %s: leg %.0f mV side %+d, right %s, idle false %.0f/s, dead %s" % (
                    L.name, sc, 1e3 * (dec.get("leg") or 0), L.s, {m: round(r["right_frac"], 3) for m, r in dec["per_msg"].items()},
                    dec.get("idle_false_per_s") or 0, (dec.get("rx_info") or {}).get("dead_windows")))
            else:
                T.say("%s %s: decoder %s" % (L.name, sc, dec["error"]))
        vr0 = None
        if sch.pilot is not None:
            pc = (dec or {}).get("pilot")
            if not pc or pc.get("vr") is None:
                pc = T.pilot_cal(L, angle=0 if abs(sch.pilot[1]) < 1e-9 else 45)
            row["pilot"] = {k: pc.get(k) for k in ("vr", "rho", "a", "pilot_side_vs_full", "angle")}
            if pc.get("vr") is None:
                T.say("   %s: no pilot; the points skipped" % sc)
                out.append(row)
                continue
            vr0 = L.tx.vr(L.mhz)[0]
            L.tx.cl.dac(VR_I=pc["vr"][0], VR_Q=pc["vr"][1])
            L.hold(sch.idle)
            time.sleep(0.1)
            row["pilot"]["side_on_pilot"] = T.recheck_side_on_idle(L, sch)
        L.hold(sch.idle)
        time.sleep(0.15)
        o = L.ld.observe()
        row["idle"] = {"di": o["di"], "dq": o["dq"], "locked": bool(o["locked"]), "side": L.s, "point": list(sch.idle),
                       "rx_point": [round(x, 3) for x in sch.rx_idle_point()]}
        b = scope_dc(rs, (2, 3, 4))
        base = {2: b[2]["dc"], 3: b[3]["dc"]}
        row["idle"]["cmp_scope"] = int(b[4]["dc"] > CMP_V)
        row["tx_scope"] = scope_dc(ts)
        leg = L.leg() if sch.pilot is None else (dec or {}).get("leg") or L.info.get("leg")
        row["leg"] = leg
        L.hold(sch.idle)
        time.sleep(0.05)
        for m, pt in enumerate(sch.msgs):
            rp = sch.rx_point(pt)
            L.events_on(pt, 20, 1000, idle=sch.idle)
            time.sleep(0.05)
            got = shots(rs, 1, MARK_V, "rising", nshots, (1, 2, 3, 4))
            L.events_off()
            L.hold(sch.idle)
            rs.trigger(source=1, level=MARK_V, slope="rising", mode="auto")
            nums = [shot_numbers(g, base, lat_ns) for g in got]
            keeper.keep(got, stage="constellation", link=L.name, mhz=L.mhz, scheme=sc, m=m, point=list(pt), base=base, leg=leg,
                        side=L.s, idle_di=o["di"], idle_dq=o["dq"], lat_ns=lat_ns)
            p = {"m": m, "point": list(pt), "rx_point": [round(x, 3) for x in rp], "n": len(got)}
            for k in ("mark_high", "mark_t", "cmp_edge_t", "cmp_width", "i_plateau", "q_plateau", "i_spike_min", "i_spike_max", "q_spike_min",
                      "q_spike_max", "i_ret_min", "i_ret_max", "q_ret_min", "q_ret_max", "i_cross_t", "q_cross_t", "i_rise", "q_rise"):
                p[k] = med(nums, k)
            p["cmp_moved"] = sum(1 for r in nums if r["cmp_edge_t"] is not None)
            p["abs_i_mv"] = 1e3 * o["di"] + (p["i_plateau"] or 0)
            p["abs_q_mv"] = 1e3 * o["dq"] + (p["q_plateau"] or 0)
            p["right_frac"] = (dec or {}).get("per_msg", {}).get(str(m), {}).get("right_frac") if dec and "error" not in dec else None
            row["points"].append(p)
            T.say("   %s %-8s %d shots: I %+5.0f Q %+5.0f mV at the plateau (abs %+5.0f, %+5.0f; expected %s x leg %.0f), spike I %+.0f/%+.0f Q %+.0f/%+.0f, CMP moved %d/%d at %s ns, right %s" % (
                sc, "(%g,%g)" % tuple(pt), len(got), p["i_plateau"] or 0, p["q_plateau"] or 0, p["abs_i_mv"], p["abs_q_mv"], p["rx_point"],
                1e3 * (leg or 0), p["i_spike_min"] or 0, p["i_spike_max"] or 0, p["q_spike_min"] or 0, p["q_spike_max"] or 0, p["cmp_moved"], len(got),
                "%.1f" % p["cmp_edge_t"] if p["cmp_edge_t"] is not None else "-", p["right_frac"]))
        if vr0 is not None:
            L.tx.cl.dac(VR_I=vr0[0], VR_Q=vr0[1])
        L.tx.idle((L.s, 0))
        time.sleep(0.1)
        L.ensure()
        log(label="twoscope constellation", tag="constellation", state=L.state(), **{k: v for k, v in row.items() if k != "decoder"},
            decoder_right={m: r["right_frac"] for m, r in (dec or {}).get("per_msg", {}).items()} if dec and "error" not in dec else None)
        out.append(row)
    return out


def flip_levels(L, rs, levels, nshots, keeper, log, lat_ns):
    out = []
    lock_dsa = L.info.get("dsa", L.rx.cl._dsa_db)
    for d in [lock_dsa] + [x for x in levels if abs(x - lock_dsa) > 0.1]:
        L.rx.cl.dsa(d)
        time.sleep(0.05)
        side = L.recheck_side()
        if side is None:
            T.say("   DSA %.2f: nothing locked at this level" % d)
            out.append({"dsa": d, "locked": False})
            continue
        leg = L.leg()
        set_arms(rs, leg)
        L.hold((1, 0))
        time.sleep(0.1)
        b = centre(rs)
        base = {2: b[2], 3: b[3]}
        L.events_on((-1, 0), 20, 1000, idle=(1, 0))
        time.sleep(0.05)
        got = shots(rs, 1, MARK_V, "rising", nshots, (1, 2, 3, 4))
        L.events_off()
        L.hold((1, 0))
        rs.trigger(source=1, level=MARK_V, slope="rising", mode="auto")
        nums = [shot_numbers(g, base, lat_ns) for g in got]
        keeper.keep(got, stage="levels", link=L.name, mhz=L.mhz, scheme="A1", m=0, point=[-1, 0], base=base, leg=leg, side=L.s, dsa=d)
        r = {"dsa": d, "locked": True, "side": side, "leg_mv": 1e3 * leg, "n": len(got)}
        for k in ("i_plateau", "q_plateau", "q_spike_min", "q_spike_max", "q_ret_max", "i_rise", "cmp_edge_t", "mark_t"):
            r[k] = med(nums, k)
        r["q_frac"] = (r["q_plateau"] or 0) / (1e3 * leg) if leg else None
        r["i_frac"] = (r["i_plateau"] or 0) / (1e3 * leg) if leg else None
        T.say("   DSA %5.2f leg %4.0f mV side %+d: the flip's I %+5.0f (%.2f of the leg), Q plateau %+5.0f mV (%+.3f of the leg), spike %+.0f / %+.0f, return %+.0f" % (
            d, 1e3 * leg, side, r["i_plateau"] or 0, r["i_frac"] or 0, r["q_plateau"] or 0, r["q_frac"] or 0, r["q_spike_min"] or 0, r["q_spike_max"] or 0, r["q_ret_max"] or 0))
        log(label="twoscope levels", tag="levels", state=L.state(), **r)
        out.append(r)
    L.rx.cl.dsa(lock_dsa)
    time.sleep(0.05)
    L.recheck_side()
    set_arms(rs, L.info.get("leg") or 0.15)
    return out


# ---------------------------------------------------------------------------------------------------------------------
def main():
    mhz = arg("--mhz", 5400.0)
    links = args_list("--links", ["BA", "AB"])
    schemes = args_list("--schemes", ["A1", "A1w", "A2", "A3", "A4", "B1", "B2"])
    nshots = arg("--shots", 8)
    levels = args_list("--levels", [7.75, 4.0], float)
    want_decoder = "--no-decoder" not in sys.argv
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("twoscope")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = Keeper()
    out = {"stamp": stamp, "mhz": mhz, "gain": GAIN, "links": {}}
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            scope_setup(scopes[n])
            T.say("scope %s: %s" % (n, scopes[n].idn))
        for lk in links:
            L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz)
            rs, ts = scopes[L.rx.name], scopes[L.tx.name]
            rec = {"link": lk, "mhz": mhz}
            out["links"][lk] = rec
            T.say("==== %s at %g MHz: receiver %s on scope %s, the sender's mark on its ch1" % (lk, mhz, L.rx.name, L.rx.name))
            try:
                if not L.up():
                    T.say("%s: no link" % lk)
                    rec["error"] = "no link"
                    log(label="twoscope setup", tag="setup", state=L.state(), error="no link", **L.info)
                    continue
                rec["lock"] = dict(L.info, side=L.s)
                log(label="twoscope setup", tag="setup", state=L.state(), **L.info)
                T.say("---- 1. cabling")
                rec["cabling"] = cabling(L, rs, ts, nshots, keeper, log)
                lat = rec["cabling"]["marks"].get("latency_ns")
                T.say("---- 2. constellations (%s), the event's arrival %s ns after the mark" % (" ".join(schemes), "%.1f" % lat if lat else "?"))
                rec["constellations"] = constellation(L, rs, ts, schemes, nshots, keeper, log, want_decoder, lat)
                T.say("---- 3. the flip against the level")
                rec["levels"] = flip_levels(L, rs, levels, nshots, keeper, log, lat)
            except T.LinkDown as e:
                T.say("%s: %s; the link's remaining stages abandoned" % (lk, e))
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
                s.trigger(source=1, level=MARK_V, slope="rising", mode="auto")
                s.run()
                s.close()
            except Exception as e:                        # noqa: BLE001
                T.say("scope %s: %r" % (n, e))
        json.dump(out, open(os.path.join(OUT, "twoscope_%s.json" % stamp), "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(os.path.join(OUT, "twoscope_%s.npz" % stamp), meta=json.dumps(keeper.meta), **keeper.arr)
        T.say("saved %s (%d captures)" % (os.path.join(OUT, "twoscope_%s" % stamp), keeper.k))
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
