"""Two boards over the dishes: the test infrastructure (Jason, 2026-11-04: 'Build the infrastructure to test this with all
relevant parameters varied.  Test it over the whole band.  Test it in and out of the wifi interference.  Test it with all
of your constellations.  Test it by varying the Comparator thresholds and other things you can control and tweak.')

The cabling (BRINGUP_LOG 4.59): each board TX ANT -> SW TX, SW RX -> RX ANT, ANT -> its 10 m cable -> its dish; the
dishes across the RACON room (139.75 ns SMA to SMA); the DSA875 on an FPV antenna near the beam (wifimon.py).  Every
call goes to the boards' own servers (netbus) by name; linkd's setup and recover run here, on the laptop, against the
receiving board's server (linkd.LinkD with a proxy whose _pll and _dsa_db are kept here).

Roles
  Link(tx, rx, mhz)   a one-way link: the sender's TX synthesizer on mhz with its output null, its RX synthesizer parked
                      700 MHz away (REVB 57: the RX synthesizer's beat modulates the carrier), TR_A 0; the receiver's RX
                      synthesizer on mhz, its TX synthesizer parked and muted (TX_DIS), TR_A 1.  up() runs linkd's setup
                      (the receiver's middles and comparator centres with the sender muted, then the sender's carrier),
                      frame() the lock's side (0 or 180 degrees: the sender's points are flipped to match, so the
                      receiver always sees the nominal constellation).
  Loop(node, mhz)     one board on its own carrier through its switch block's SW TX -> SW RX leak (25 dB, REVB 55:
                      about -17 dBm at RX ANT), the other board muted with both synthesizers parked: the prover's
                      turnaround (LATENCY.md's single-board loopback, without a cable change).

Experiments (each one record per point, every parameter in it, the link's state: received dBm, VC, the leg, the DSA)
  prbs     a PRBS on one comparator across the boards: CONSTS (BPSK on CMP_I, on-off on IP / IN, a Q bit on QP, ...);
           the window thresholds (a fraction of the leg), CMP_I's trim (I_OFF_F), the symbol period, the polynomial, the
           timing recovery's gain and polarity mode, the level (the receiver's DSA)
  events   'idle to 1-in-N': the sender's events every N clocks, `width` long, one message at a time; the receiver's
           decoder table cut to that message, so a decision is a right one; the event-to-event histogram (missed events
           as doubled intervals, false ones short); the idle's false events a second
  prover   Loop: loopback_turnaround (the counter: n, miss, min / mean / max) and captures (each reply checked on the
           ladder pins and as received) per scheme, path (fast, sync), reply function (the XOR masks and the 9
           derangements of 4), window fraction, level, decision delay, first edge
  band     the link up at each frequency of a list, each direction: the level, a reduced prbs and events set; and the
           loopback turnaround there
Records: bringup/data/twoboard/<cmd>_<time>.jsonl (gitignored: the summaries go to BRINGUP_LOG).  Each carries
'wifi': the 20 MHz channels inside the receiver's +-94 MHz band and whether the carrier sits on one.

    COSTAS_BENCH_CONFIG=bringup/bench_config_laptop.json python3 bringup/twoboard.py check
    ... twoboard.py prbs --dir BA AB --mhz 5200            (one factor at a time about the baseline; --grid for 2D)
    ... twoboard.py events --dir BA --mhz 5200
    ... twoboard.py prover --board B --mhz 5200
    ... twoboard.py band --dir BA AB --mhz 4400 4600 ... --prover
"""
import argparse
import itertools
import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import bench  # noqa: E402,F401  (puts the drivers on the path)
from netbus import RemoteCostasLink, RemoteError  # noqa: E402
import costaslink as C  # noqa: E402
import linkd  # noqa: E402

DATA = os.path.join(HERE, "data", "twoboard")
os.makedirs(DATA, exist_ok=True)
linkd.CAL_FILE = os.path.join(DATA, "windows_laptop.json")       # never beside the repository's driver
HOSTS = {"A": "192.168.2.99", "B": "192.168.2.98"}
# each board's TX output null (VR_I, VR_Q) by frequency, measured on the DSA875 at TX ANT (BRINGUP_LOG 4.55, 4.58)
VR_NULL = {"A": {5200: (0.2482, 0.2712)}, "B": {5200: (0.2343, 0.2609)}}
TX_ANT_NULL = {b: dict(t) for b, t in VR_NULL.items()}      # measured on the analyzer at TX ANT itself
NULL_FILE = os.path.join(DATA, "vr_null.json")         # `twoboard.py nulls`: each board's null by frequency, on the FPV
try:
    for _b, _t in json.load(open(NULL_FILE)).items():
        for _f, _r in _t.items():
            if _r.get("vr") and (float(_f) not in TX_ANT_NULL[_b] or _r.get("prefer")):
                VR_NULL[_b][float(_f)] = tuple(_r["vr"])
except (OSError, ValueError, KeyError):
    pass
PARK_MHZ = 700.0                       # an unused synthesizer this far from the link's carrier (REVB 57)
LINK_CFG = {"leg_target": 0.15, "window_frac": 0.5, "v_t2": 2.9, "dsa_min": 6.0}
# the 5 GHz WiFi channels (20 MHz) and the ones seen here (the laptop's `iw` / `nmcli`, 2026-11-04 16:50)
WIFI_CH = {c: 5000 + 5 * c for c in list(range(36, 66, 4)) + list(range(100, 146, 4)) + list(range(149, 166, 4))}
WIFI_SEEN = {36: "AP Claremont-ETC", 64: "the laptop (40 MHz, 60+64)", 60: "the laptop (40 MHz, 60+64)", 100: "eduroam",
             108: "Claremont-WPA/ETC", 132: "Claremont-WPA/Guest", 149: "Nile-*"}


def wifi_tag(mhz):
    """the channels inside the receiver's +-94 MHz band, the one under the carrier, and the ones seen here"""
    near = {c: f for c, f in WIFI_CH.items() if abs(f - mhz) <= 94 + 10}
    on = [c for c, f in WIFI_CH.items() if abs(f - mhz) < 10]
    return {"in_band": sorted(near), "on": on, "seen_in_band": sorted(c for c in near if c in WIFI_SEEN),
            "seen_on": [c for c in on if c in WIFI_SEEN]}


def park(mhz):
    """an unused synthesizer's frequency: PARK_MHZ away, on the 25 MHz grid (integer-N), inside 3000-6000"""
    f = mhz + PARK_MHZ if mhz + PARK_MHZ <= 6000 else mhz - PARK_MHZ
    return float(25 * round(f / 25.0))


class Log:
    def __init__(self, cmd):
        self.path = os.path.join(DATA, "%s_%s.jsonl" % (cmd, time.strftime("%Y%m%d_%H%M%S")))
        self.f = open(self.path, "a")
        print("records:", self.path, flush=True)

    def __call__(self, **kw):
        kw.setdefault("t", round(time.time(), 3))
        self.f.write(json.dumps(kw, default=_js) + "\n")
        self.f.flush()


def _js(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return repr(x)


def say(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Proxy:
    """a board's remote CostasLink, with the synthesizers' and the DSA's settings kept here (the server hides names
    that start with _) and a remote ValueError raised as one (linkd's rice_fit fallback catches it)"""
    def __init__(self, r):
        self.r, self._pll, self._dsa_db = r, {}, 31.75

    def pll_tune(self, which, f, f_pfd=25.0, cp=None, lo_mon=None):
        if f_pfd == 25.0 and abs(f / 25.0 - round(f / 25.0)) > 1e-9:    # off the 25 MHz grid: R = 5 (every 5 MHz), cp 15
            f_pfd, cp = 5.0, 15
        self._pll[which] = (float(f), f_pfd, cp)
        return self.r.pll_tune(which, float(f), f_pfd=f_pfd, cp=cp)

    def dsa(self, db):
        self._dsa_db = float(db)
        return self.r.dsa(float(db))

    def __getattr__(self, n):
        v = getattr(self.r, n)
        if not callable(v):
            return v

        def call(*a, **k):
            try:
                return v(*a, **k)
            except RemoteError as e:
                if str(e).startswith("ValueError"):
                    raise ValueError(str(e))
                raise
        return call


class _Srv:
    def __init__(self, cl):
        self.cl, self.last = cl, {"t": time.time()}


class Node:
    def __init__(self, name):
        self.name = name
        self.cl = Proxy(RemoteCostasLink(HOSTS[name], 5800))
        self.clk_mhz = self.cl.clk_mhz
        self.ser = self.cl.ser

    def vr(self, mhz):
        """the nearest measured output null (and how far it is from mhz)"""
        t = VR_NULL[self.name]
        f = min(t, key=lambda k: abs(k - mhz))
        return t[f], abs(f - mhz)

    def send(self, mhz, muted=True):
        cl = self.cl
        cl.safe()
        cl.pll_tune(0, mhz)
        cl.pll_tune(1, park(mhz))
        (vi, vq), _ = self.vr(mhz)
        cl.dac(VR_I=vi, VR_Q=vq)
        cl.hold_point(1, 0)
        cl.ctrl(tr_a=0, tx_dis=1 if muted else 0)

    def quiet(self):
        """muted, both synthesizers parked away from everything the other board does (the safe state)"""
        self.cl.safe()

    def idle(self, point=(1, 0)):
        self.cl.tx_stop()
        self.cl.hold_point(*point)


CMP_OF = {"QP": "CMP_QP", "QN": "CMP_QN", "IP": "CMP_IP", "IN": "CMP_IN"}


def _level(rcl, w, duty_target=0.5, lo=0.85, hi=2.45, steps=13, seconds=0.005):
    """the threshold at which window comparator w's duty crosses duty_target (its input's level, as it sees it):
    above the level the comparator is low (QP / IP compare their arm's leg above V_MID; QN / IN the inverted leg)"""
    name = CMP_OF[w]

    def duty(v):
        rcl.threshold(w, v)
        return rcl.gate(seconds=seconds, inputs=(name,))[name]["duty"]
    d_lo, d_hi = duty(lo), duty(hi)
    if not (d_lo > duty_target > d_hi):
        return None
    for _ in range(steps):
        mid = 0.5 * (lo + hi)
        if duty(mid) > duty_target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def cal_windows(ctx, W=20, N=500):
    """each window comparator's centre and full step in its own terms, from the carrier: IP / IN at (1, 0) and
    (-1, 0); QP / QN at the idle (Q = 0) and at Q = +-a as events W of every N clocks (a held corner would turn the
    loop 45 degrees; events of 2 us began turning it too, and read the Q step at half its size: 200 ns, as the
    schemes' own), bisected for half their duty.  ctx.wcal = {w: (centre, on_level)}; returns the levels"""
    rcl = ctx.rx_cl()
    lv = {}
    ctx.hold((1, 0))
    time.sleep(0.03)
    for w in ("IP", "IN", "QP", "QN"):
        lv[(w, "+I")] = _level(rcl, w)
    ctx.hold((-1, 0))
    time.sleep(0.05)
    for w in ("IP", "IN"):
        lv[(w, "-I")] = _level(rcl, w)
    for w, pt in (("QP", (1, 1)), ("QN", (1, -1))):
        ctx.events_on(pt, W, N)
        time.sleep(0.02)
        lv[(w, "step")] = _level(rcl, w, duty_target=0.5 * W / N)
        ctx.events_off()
    ctx.hold((1, 0))
    time.sleep(0.03)
    wc = {}
    if lv[("IP", "+I")] is not None and lv[("IP", "-I")] is not None:
        wc["IP"] = (0.5 * (lv[("IP", "+I")] + lv[("IP", "-I")]), lv[("IP", "+I")])
    if lv[("IN", "+I")] is not None and lv[("IN", "-I")] is not None:
        wc["IN"] = (0.5 * (lv[("IN", "+I")] + lv[("IN", "-I")]), lv[("IN", "-I")])
    for w in ("QP", "QN"):
        if lv[(w, "+I")] is not None and lv[(w, "step")] is not None:
            wc[w] = (lv[(w, "+I")], lv[(w, "step")])
    ctx.wcal, ctx.wcal_dsa = wc, (rcl._dsa_db, getattr(ctx, "s", 1))
    return {"%s %s" % k: (None if v is None else round(v, 4)) for k, v in lv.items()}


WIN_INDEX = {"QP": 1, "QN": 2, "IP": 3, "IN": 4}     # a window's place in Scheme.fast()'s vector (CMP_NAMES' order)


def point_levels(ctx, idle, pts, W=20, N=500):
    """each window comparator's level at the scheme's idle (held) and at each point in pts (as events W of every N clocks
    from that idle, as the schemes send them), in the comparator's own terms: the received constellation, with the lock's
    rotation, the arms' offsets, the mirror and the pilot all in it.  {point: {w: volts}}"""
    rcl = ctx.rx_cl()
    ctx.hold(idle)
    time.sleep(0.05)
    base = {w: _level(rcl, w) for w in CMP_OF}
    lv = {tuple(idle): base}
    d = W / float(N)
    for p in pts:
        ctx.events_on(p, W, N, idle=idle)
        time.sleep(0.02)
        row = {}
        for w in CMP_OF:
            b = base[w]
            hi = _level(rcl, w, duty_target=0.5 * d)            # where the events reach above the idle
            lo = _level(rcl, w, duty_target=1.0 - 0.5 * d)      # where they reach below it
            if b is None:
                row[w] = None
            elif hi is not None and hi > b + 0.003:
                row[w] = hi
            elif lo is not None and lo < b - 0.003:
                row[w] = lo
            else:
                row[w] = b
        ctx.events_off()
        ctx.hold(idle)
        time.sleep(0.02)
        lv[tuple(p)] = row
    return lv


def scheme_windows(ctx, s, frac=0.5):
    """the four windows for scheme s from its received constellation (point_levels, kept per scheme and DSA): each between
    the highest level among the points that must leave it quiet and the lowest among those that must fire it, frac of the
    way across that gap (0.5 the middle; low frac is near the quiet points, so it fires early).  A window no point fires
    sits above them all.  Returns (thresholds, levels, gaps)."""
    rcl = ctx.rx_cl()
    key = (s.name, rcl._dsa_db, getattr(ctx, "s", 1))     # per lock side: the Q offsets flip with it (REVB 41, 4.62)
    cache = getattr(ctx, "slev", None)
    if cache is None:
        cache = ctx.slev = {}
    if key not in cache:
        # a pilot idle (0.2 of a point) is pulled round by the events themselves (each kind its own way: B1's (1, 0)
        # read on -I at 4 % duty, 2026-11-04 18:24), so its points are measured at 0.4 %
        cache[key] = point_levels(ctx, s.idle, s.msgs, N=5000 if s.pilot is not None else 500)
    lv = cache[key]
    model = {tuple(s.idle): s.fast(s.rx_idle_point())}
    for m in s.msgs:
        model[tuple(m)] = s.fast(s.rx_point(m))
    th, gaps = {}, {}
    for w, j in WIN_INDEX.items():
        on = [lv[p][w] for p in model if model[p][j] == 1 and lv[p][w] is not None]
        off = [lv[p][w] for p in model if model[p][j] == 0 and lv[p][w] is not None]
        if on and off:
            lo, hi = max(off), min(on)
            v = lo + frac * (hi - lo) if hi > lo else 0.5 * (sum(on) / len(on) + sum(off) / len(off))
            gaps[w] = round(1e3 * (hi - lo), 1)               # mV; negative: the points overlap on this comparator
        elif off:
            v = max(off) + 0.05
            gaps[w] = None
        elif on:
            v = min(on) - 0.05
            gaps[w] = None
        else:
            continue
        v = min(2.499, max(0.0, v))
        rcl.threshold(w, v)
        th[w] = round(v, 4)
    ctx.last_th = dict(th)
    return th, {"%s,%s" % p: {w: (None if x is None else round(x, 4)) for w, x in r.items()} for p, r in lv.items()}, gaps


def rx_tables(ctx, s, first_edge=False, seconds=0.01, margin_v=0.004):
    """the decoder's idle vector, table and slow expectations for scheme s as this receiver actually sees it.  The idle:
    the five comparators gated at the scheme's idle (the pilot's, for B1 / B2 / A4).  The table: each message's vector from
    the measured constellation (point_levels, kept by scheme_windows) against the thresholds set, a window within margin_v
    of its threshold taken both ways, CMP_I from the point's I sign against the idle's; vectors two messages share, or the
    idle's, are left invalid.  Without a measured constellation (or for first-edge decisions) the scheme's own table, the
    180-degree twin when CMP_I reads the other way at the idle.  Returns (idle_vector, lut, slow_exp, info); info has
    'owners' {vector: message} for the fast path's table."""
    rcl = ctx.rx_cl()
    ctx.hold(s.idle)
    time.sleep(0.05)
    g = rcl.gate(seconds=seconds, inputs=tuple(C.CMP_NAMES))
    vec = sum((1 if g[n]["duty"] > 0.5 else 0) << k for k, n in enumerate(C.CMP_NAMES))
    nominal = s.idle_vector()
    info = {"measured": vec, "nominal": nominal, "duty": {n: round(g[n]["duty"], 3) for n in C.CMP_NAMES}}
    th = getattr(ctx, "last_th", None)
    lv = (getattr(ctx, "slev", None) or {}).get((s.name, rcl._dsa_db, getattr(ctx, "s", 1)))
    if first_edge or not th or not lv:
        use = s
        if (vec ^ nominal) & 1:
            use, info["twin"] = s.twin(), True
        if (use.idle_vector() ^ vec) & 0x1E:
            info["idle_mismatch"] = [n for k, n in enumerate(C.CMP_NAMES) if k and (vec >> k) & 1 != (use.idle_vector() >> k) & 1]
        lut = use.lut(first_edge)
        info["owners"] = {v: (e & 7) for v, e in enumerate(lut) if e & 8}
        info["source"] = "nominal"
        return use.idle_vector(), lut, use.slow_exp(), info
    i_idle = s.rx_idle_point()[0]
    cmp_i_idle = vec & 1
    # a window whose level barely moves across the scheme's points carries nothing (board A's IP at the dish level: 9 mV
    # between (1, 0) and (-1, 0) against IN's 350, BRINGUP_LOG 4.63-4.64): it is taken both ways in every vector
    pts_all = [tuple(s.idle)] + [tuple(m) for m in s.msgs]
    dead = set()
    for w in WIN_INDEX:
        vals = [lv[p][w] for p in pts_all if p in lv and lv[p].get(w) is not None]
        if len(vals) >= 2 and max(vals) - min(vals) < 5 * margin_v:
            dead.add(w)
    info["dead_windows"] = sorted(dead)
    owners, clash = {}, set()
    for m, pt in enumerate(s.msgs):
        bits = []
        pi = s.rx_point(pt)[0]
        if abs(pi) < 1e-9 or abs(i_idle) < 1e-9:
            bits.append((0, 1))
        else:
            bits.append((cmp_i_idle,) if (pi > 0) == (i_idle > 0) else (1 - cmp_i_idle,))
        levels = lv.get(tuple(pt)) or {}
        for w, k in WIN_INDEX.items():
            if w in dead or w not in th or levels.get(w) is None:
                bits.append((0, 1))
            elif abs(levels[w] - th[w]) < margin_v:
                bits.append((0, 1))
            else:
                bits.append((1,) if levels[w] > th[w] else (0,))
        for combo in itertools.product(*bits):
            v = sum(b << k for k, b in enumerate(combo))
            if v == vec:
                continue
            if v in owners and owners[v] != m:
                clash.add(v)
            owners[v] = m
    for v in clash:
        owners.pop(v, None)
    lut = [(8 | owners[v]) if v in owners else 0 for v in range(32)]
    info.update(source="measured", owners=owners, clashes=sorted(clash),
                vectors={str(m): sorted(v for v, mm in owners.items() if mm == m) for m in range(s.n)})
    return vec, lut, 0, info


def _cut(lut, m):
    """a table with only message m valid: a decision is then a right one"""
    return [(e if (e & 8) and (e & 7) == m else 0) for e in lut]


def set_windows(ctx, frac, which=("QP", "QN", "IP", "IN")):
    """each window at its centre + frac x (its on level - its centre), calibrated at this DSA (again if it changed);
    linkd's rule (the ADC's leg from its fitted centre) where a comparator would not calibrate"""
    rcl = ctx.rx_cl()
    if getattr(ctx, "wcal", None) is None or getattr(ctx, "wcal_dsa", None) != (rcl._dsa_db, getattr(ctx, "s", 1)):
        ctx.wcal_levels = cal_windows(ctx)
    th = {}
    leg = None
    for w in which:
        if w in ctx.wcal:
            c, on = ctx.wcal[w]
            v = c + frac * (on - c)
        else:
            leg = leg if leg is not None else ctx.leg()
            v = ctx.ld.cen[w] + frac * leg
        v = min(2.499, max(0.0, v))
        rcl.threshold(w, v)
        th[w] = round(v, 4)
    return th


class LinkDown(Exception):
    """a link whose recovery and setup both failed inside a point: its remaining points are abandoned (at 5500 MHz A -> B
    locked with a 47 mV leg, too weak for the lock test, and every point then re-ran setup for 3 minutes, 2026-11-05 02:40)"""


class Link:
    """a one-way link tx -> rx at mhz, set up and kept by linkd's own code run here"""
    def __init__(self, tx, rx, mhz, cfg=None):
        self.tx, self.rx, self.mhz = tx, rx, float(mhz)
        self.cfg = dict(LINK_CFG, tx_mhz=park(mhz), rx_mhz=float(mhz))
        self.cfg.update(cfg or {})                   # a duplex pair keeps the sender's own TX synthesizer (tx_mhz) and null
        path = os.path.join(DATA, "cfg_%s_rx_%d.json" % (rx.name, int(mhz)))
        json.dump(self.cfg, open(path, "w"))
        self.ld = linkd.LinkD(_Srv(rx.cl), config=path)
        self._orig_release = self.ld.release_at
        self.ld.release_at = self._release_at
        self._carrier = False
        self.s = 1                                   # the lock's side: +1 (0 degrees) or -1 (180)
        self.info = {}

    @property
    def name(self):
        return "%s%s" % (self.tx.name, self.rx.name)

    def _release_at(self, vc, pll, dsa, tx_dis, settle_s=1.5):
        if not self._carrier:                        # the receiver's middles and centres taken without the carrier
            self.tx.idle((1, 0))
            self.tx.cl.ctrl(tx_dis=0)
            self._carrier = True
        return self._orig_release(vc, pll, dsa, 1, settle_s)    # the receiver's own TX stays muted

    def up(self, tries=3):
        for k in range(tries):
            self.tx.send(self.mhz, muted=True)
            self.rx.cl.safe()
            self.rx.cl.ctrl(tr_a=1)
            self._carrier = False
            t0 = time.time()
            ok = self.ld.setup(self.cfg)
            self.info = {"ok": ok, "setup_s": round(time.time() - t0, 1), "dsa": self.rx.cl._dsa_db, "leg": self.ld.leg,
                         "vc_lock": self.ld.vc_lock, "i0": self.ld.i0, "q0": self.ld.q0, "cen": self.ld.cen, "try": k}
            if ok:
                self.frame()
                self.wcal = None
                self.slev = None
                say("%s at %g MHz: locked in %.0f s, DSA %.2f, leg %.1f mV, VC %.4f, side %+d" % (
                    self.name, self.mhz, self.info["setup_s"], self.info["dsa"], 1e3 * self.ld.leg, self.ld.vc_lock, self.s))
                return True
            say("%s at %g MHz: setup found no lock (try %d)" % (self.name, self.mhz, k + 1))
        return False

    def frame(self):
        self.tx.idle((1, 0))
        time.sleep(0.05)
        o = self.ld.observe()
        self.s = 1 if o["di"] > 0 else -1
        self.info["side"] = self.s
        return self.s

    def txp(self, i, q):
        """the sender's point for the point the receiver should see at (i, q): rev A's I arm is inverted (REVB 9), so a
        receiver sees the sent point reflected (I -> -I) and then turned by its lock; linkd locks the idle on +-I, so the
        receiver sees (s I, -s Q) (measured 2026-11-04 17:30: the Q steps went the other way under a plain 180)"""
        return (self.s * i, -self.s * q)

    def pt(self, i, q):
        """the sender's ladder code for the point the receiver should see at (i, q)"""
        return C.point_code(*self.txp(i, q))

    def look(self):
        """the idle carrier for a moment: the lock, the level, the leg"""
        self.tx.idle((self.s, 0))
        time.sleep(0.03)
        o = self.ld.observe()
        r = self.rx.cl.received_dBm() if o["locked"] else None
        return {"locked": bool(o["locked"]), "di": o["di"], "dq": o["dq"], "vc": o["vc"], "received_dbm": r,
                "dsa": self.rx.cl._dsa_db}

    def ensure(self):
        s = self.look()
        if s["locked"] and abs(s["di"]) > 0.01:       # locked on either side (the side is in self.s; the points are mapped)
            side = self.s * (1 if s["di"] > 0 else -1)   # look() sent (s, 0): a negative I means the side has changed
            if side != self.s:
                say("%s: the lock is on the other side (%+d)" % (self.name, side))
                self.s = side
                self.wcal = self.slev = None
            return s
        ok, starts = self.ld.recover()
        say("%s: lock lost (%s); recover %s (%d starts)" % (self.name, s, ok, starts))
        if not ok:
            if not self.up(tries=1):
                raise LinkDown("%s at %g MHz: no lock after recover and setup" % (self.name, self.mhz))
        else:
            self.frame()
        return self.look()

    def leg(self):
        """the idle's I deflection now (the ADC; the windows scale with it)"""
        self.tx.idle((self.s, 0))
        time.sleep(0.03)
        return abs(sum(self.rx.cl.adc("I") for _ in range(4)) / 4.0 - self.ld.i0)

    def recheck_side(self):
        """after a level change (the DSA): the loop may have re-locked on the other side; the idle sent on the current
        side reads negative then.  Returns the side, or None when nothing is locked at this level."""
        self.tx.idle((self.s, 0))
        time.sleep(0.05)
        o = self.ld.observe()
        if abs(o["di"]) < 0.005:
            return None
        if o["di"] < 0:
            self.s = -self.s
            self.wcal = self.slev = None
            say("%s: the side changed with the level (%+d)" % (self.name, self.s))
        return self.s

    def windows(self, frac, leg=None, which=("QP", "QN", "IP", "IN")):
        return set_windows(self, frac, which)

    # the calibration's hooks
    def rx_cl(self):
        return self.rx.cl

    def hold(self, p):
        self.tx.idle(self.txp(*p))

    def events_on(self, p, W, N, idle=(1, 0)):
        t = self.tx.cl
        t.tx_points(self.pt(*idle), [self.pt(*p)])
        t.tx_msg(0)
        t.events(period=N, width=W, count=10000000, source="fixed", n=1)     # count 0 sends none
        t.tx_go()

    def events_off(self):
        self.tx.cl.tx_stop()
        self.hold((1, 0))

    def state(self):
        return {"link": self.name, "mhz": self.mhz, "rx_dsa": self.rx.cl._dsa_db, "side": self.s, "wifi": wifi_tag(self.mhz),
                "vr_from_mhz_off": self.tx.vr(self.mhz)[1]}


# ---------------------------------------------------------------------------------------------------------------------
# prbs: a PRBS on one comparator across the boards
# ---------------------------------------------------------------------------------------------------------------------
# name: (point for bit 0, point for bit 1, the comparator checked, the windows it uses)
CONSTS = {
    "bpsk":    ((1, 0), (-1, 0), "I", ()),          # sign(I): A1's flip as a bitstream
    "ook_ip":  ((1, 0), (0, 0), "IP", ("IP",)),     # the carrier on / nulled, on IP's window
    "ook_in":  ((-1, 0), (0, 0), "IN", ("IN",)),    # the same on the other side of I
    "ask_ip":  ((1, 0), (-1, 0), "IP", ("IP",)),    # BPSK's flip decided on IP's window (A1w as a bitstream)
    "qbit":    ((1, 1), (1, -1), "QP", ("QP",)),    # the Q step about a full I (A2 / A3's Q bit)
    "q_ook":   ((1, 0), (1, 1), "QP", ("QP",)),     # Q on / off beside a full I
}


def prbs_point(link, const="bpsk", period=50, poly=15, gain=4, one_pol=None, phase_frac=None, frac=0.5, ioff=None,
               seconds=1.0, dsa=None):
    tx, rx = link.tx.cl, link.rx.cl
    p0, p1, src, wins = CONSTS[const]
    out = {"exp": "prbs", "const": const, "period": period, "poly": poly, "gain": gain, "one_pol": one_pol,
           "phase_frac": phase_frac, "frac": frac, "ioff": ioff, "seconds": seconds}
    rx.dsa(link.info.get("dsa", rx._dsa_db))         # the lock checked at the link's own level (a weak leg reads as lost)
    st = link.ensure()
    out["look"] = st
    if not st["locked"]:
        out["error"] = "no lock"
        return out
    if wins:
        out["thresholds"] = link.windows(frac, None, wins)
        out["wcal"] = link.wcal
    if dsa is not None:                              # then the point's own level, the windows scaled with the leg
        rx.dsa(dsa)
        time.sleep(0.05)
        out["side_at_level"] = link.recheck_side()
        if wins:
            out["thresholds"] = set_windows(link, frac, wins)
    leg = link.leg()
    out["leg"] = leg
    ioff0 = None
    if ioff is not None:
        ioff0 = rx.dac_volts().get("I_OFF_F", C.V_MID)
        rx.dac(C.DAC2, I_OFF_F=float(ioff))
    phase = None if phase_frac is None else int(phase_frac * period * link.rx.ser)
    tx.tx_timing(period=period)
    rx.tx_timing(period=period)                     # the check's symbol length is the checker's own TX_PERIOD
    tx.tx_points(link.pt(1, 0), [link.pt(*p0), link.pt(*p1)])
    tx.tx_prbs(poly)
    tx.tx_mode("prbs", n=2)
    tx.tx_go()
    time.sleep(0.02)
    try:
        tries = {}
        for inv in (False, True):
            rx.ber_config(poly, phase, invert=inv, cdr=True, gain=gain, period=period, one_pol=one_pol, src=src)
            time.sleep(0.15)
            rx.ber_config(poly, phase, invert=inv, enable=False, cdr=True, gain=gain, period=period, one_pol=one_pol, src=src)
            tries[inv] = rx.ber()
        inv = min(tries, key=lambda k: (tries[k]["mismatches"] / tries[k]["bits"]) if tries[k]["bits"] else 9)
        rx.ber_config(poly, phase, invert=inv, cdr=True, gain=gain, period=period, one_pol=one_pol, src=src)
        time.sleep(seconds)
        rx.ber_config(poly, phase, invert=inv, enable=False, cdr=True, gain=gain, period=period, one_pol=one_pol, src=src)
        r = rx.ber()
        cdr = rx.cdr_state()
    finally:
        tx.tx_stop()
        link.tx.idle((link.s, 0))
        if ioff0 is not None:
            rx.dac(C.DAC2, I_OFF_F=float(ioff0))
        if dsa is not None:
            rx.dsa(link.info.get("dsa", rx._dsa_db))
    out.update(invert=inv, bits=r["bits"], mismatches=r["mismatches"], errors=r["mismatches"] / 3.0,
               ber=r["ber"], ber_tries={str(k): v["mismatches"] / v["bits"] if v["bits"] else None for k, v in tries.items()},
               cdr=cdr, mbaud=link.tx.clk_mhz / period, bits_expected=seconds * link.tx.clk_mhz * 1e6 / period)
    return out


PRBS_BASE = {"const": "bpsk", "period": 50, "poly": 15, "gain": 4, "one_pol": None, "phase_frac": None, "frac": 0.5,
             "ioff": None, "seconds": 1.0, "dsa": None}
PRBS_OFAT = {
    "period": [5, 8, 10, 15, 20, 25, 33, 50, 100, 200, 500, 1000],
    "poly": [7, 9, 15, 23, 31],
    "gain": [1, 2, 3, 4, 5, 6, 8],
    "one_pol": [False, True],
    "phase_frac": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
    "dsa": [0, 2, 4, 6, 7.75, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 31.75],
}
# per constellation: the window thresholds (frac of the leg); for bpsk CMP_I's trim (I_OFF_F, volts about mid-scale)
PRBS_FRACS = [-0.6, -0.4, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2]
CONST_FRAC = {"ook_ip": 0.5, "ook_in": 0.5, "q_ook": 0.5, "ask_ip": 0.0, "qbit": 0.0}   # each one's natural place
PRBS_IOFFS = [0.0, 0.3, 0.8, 1.2, 1.45, 1.55, 1.6, 1.65, 1.7, 1.75, 1.85, 2.1, 2.5, 3.0, 3.3]


def prbs_plan(consts=None, quick=False):
    """one factor at a time about the baseline, for each constellation; the threshold for each; a 2D frac x DSA grid
    for the window constellations"""
    pts = []
    consts = consts or list(CONSTS)
    for c in consts:
        base = dict(PRBS_BASE, const=c, frac=CONST_FRAC.get(c, 0.5))
        pts.append(dict(base, tag="base"))
        for k, vals in PRBS_OFAT.items():
            if quick:
                vals = vals[::3]
            for v in vals:
                pts.append(dict(base, tag="ofat_" + k, **{k: v}))
        if CONSTS[c][3]:
            for f in (PRBS_FRACS[::2] if quick else PRBS_FRACS):
                pts.append(dict(base, tag="ofat_frac", frac=f))
            if not quick:
                for f, d in itertools.product([0.2, 0.35, 0.5, 0.65, 0.8], [0, 7.75, 14, 20, 26]):
                    pts.append(dict(base, tag="grid_frac_dsa", frac=f, dsa=d))
        else:
            for v in (PRBS_IOFFS[::2] if quick else PRBS_IOFFS):
                pts.append(dict(base, tag="ofat_ioff", ioff=v))
    return pts


# ---------------------------------------------------------------------------------------------------------------------
# the pilot (B1, B2, A4): a weak carrier at the idle, made by offsetting VR from the null
# ---------------------------------------------------------------------------------------------------------------------
def _sender(ctx):
    """(the sending board's CostasLink, the receiver's observe, the null) for a Link or a Loop"""
    if isinstance(ctx, Link):
        return ctx.tx.cl, ctx.ld.observe, ctx.tx.vr(ctx.mhz)[0]
    return ctx.node.cl, ctx.ld.observe, ctx.node.vr(ctx.mhz)[0]


def pilot_cal(ctx, rho=C.RHO, angle=0, d0=0.08, tries=10):
    """the VR offsets from the null that leave a pilot of rho x the axis point's amplitude along TX (1, 0) (angle 0: B1)
    or TX (1, 1) (angle 45: B2, A4), as the receiver measures it with its loop running: locked on the full point first,
    then the point (0, 0) with the offsets, the loop staying on the same side if the pilot is in phase with the point.
    At 45 degrees both relative signs of the VR_Q offset are tried (VR's Q may run either way against the ladder's: one
    sign reached only 0.17 at 330 mV, 2026-11-04 18:18) and the one with the smaller offset kept.
    Returns {"vr": (VR_I, VR_Q), "rho": measured, "trace": [...]}; the sender left at (0, 0) with the pilot."""
    cl, observe, (vi0, vq0) = _sender(ctx)
    full = ctx.txp(1, 0) if angle == 0 else ctx.txp(1, 1)
    cl.dac(VR_I=vi0, VR_Q=vq0)
    cl.hold_point(*full)
    time.sleep(0.1)
    o = observe()
    a = abs(o["di"]) / (1.0 if angle == 0 else math.sqrt(2))      # the axis point's amplitude
    sgn_full = 1 if o["di"] > 0 else -1
    trace = [("full", full, o["di"], o["dq"])]

    def search(ux, uy, sign=1.0):
        """the offset d along (ux, uy) that leaves a pilot of rho: the loop locks the pilot on whichever side it likes
        (board A put it at -I for either sign of the offset, 2026-11-05 00:10), so the size |r| is what converges and
        the side is measured afterwards by the caller (recheck_side_on_idle)"""
        d, got = d0, None
        for _ in range(tries):
            vi, vq = vi0 + sign * d * ux, vq0 + sign * d * uy
            if not (0.0 <= vi <= 0.55 and 0.0 <= vq <= 0.55):
                break
            cl.hold_point(*full)
            time.sleep(0.05)
            cl.dac(VR_I=vi, VR_Q=vq)
            cl.hold_point(0, 0)
            time.sleep(0.15)
            o = observe()
            r = o["di"] * sgn_full / a if a else 0.0
            trace.append((round(d, 4), sign, round(vi, 4), round(vq, 4), o["di"], o["dq"], round(r, 3)))
            if abs(r) < 0.05:                        # too weak for the loop to hold (30 mV read 0, 2026-11-04 18:15)
                d *= 1.6
                continue
            got = (vi, vq, r, d)
            if abs(abs(r) - rho) <= 0.03:
                break
            d = d * rho / abs(r)
        return got

    if angle == 0:
        ux, uy = ctx.txp(1.0, 0.0)
        cands = [search(ux, uy)]
    else:
        ux, uy = ctx.txp(1 / math.sqrt(2), 1 / math.sqrt(2))
        cands = [search(ux, uy), search(ux, -uy)]
    cands = [c for c in cands if c is not None and abs(abs(c[2]) - rho) <= 0.06]
    if not cands:
        cl.dac(VR_I=vi0, VR_Q=vq0)
        cl.hold_point(*ctx.txp(1, 0))
        return {"vr": None, "rho": None, "trace": trace, "a": a}
    got = min(cands, key=lambda c: c[3])
    cl.hold_point(*full)
    time.sleep(0.05)
    cl.dac(VR_I=got[0], VR_Q=got[1])
    cl.hold_point(0, 0)
    time.sleep(0.1)
    return {"vr": (round(got[0], 4), round(got[1], 4)), "rho": abs(got[2]), "pilot_side_vs_full": 1 if got[2] > 0 else -1,
            "trace": trace, "a": a, "angle": angle}


def recheck_side_on_idle(ctx, s):
    """for a pilot scheme, after the pilot is set: the loop may have put the pilot on the other side from the full point
    it was mapped for; the idle (0, 0) with the pilot sent, the receiver's I sign says.  The side is flipped and the
    windows and tables re-measured on it (their caches are per side)."""
    ctx.hold(s.idle)
    time.sleep(0.1)
    o = ctx.ld.observe()
    if abs(o["di"]) < 0.004:
        return None
    if o["di"] < 0:
        ctx.s = -ctx.s
        ctx.wcal = ctx.slev = None
        say("%s: the pilot sits on the other side: side %+d" % (ctx.name, ctx.s))
    return ctx.s


# ---------------------------------------------------------------------------------------------------------------------
# events: idle to 1-in-N across the boards
# ---------------------------------------------------------------------------------------------------------------------
EVENT_SCHEMES = ["A3", "A2", "A1", "A1w", "B1", "B2", "A4"]   # B1 / B2 / A4 with the pilot (pilot_cal)


def _lut_only(s, m, first_edge):
    """the scheme's decoder table with only message m valid: a decision is then a right one"""
    return [(e if (e & 8) and (e & 7) == m else 0) for e in s.lut(first_edge)]


def events_point(link, scheme="A3", msg=None, period=1000, width=20, count=20000, first_edge=False, delay=16, quiet=4,
                 confirm=6, window=100, settle=0, frac=0.4, dsa=None, idle_s=0.5, ref="tx"):
    """`count` events of each message (or of `msg`), every `period` clocks, `width` long; per message: the events seen,
    the right decisions, the event-to-event histogram's peaks; and the idle's false events in idle_s.
    ref 'trig_in' (QPV_TIMING_REVIEW 6a row 3: a lead from the sender's TRIG OUT A, J205, to the receiver's TRIG IN, J207):
    the sender's TX events mark TRIG OUT A, the receiver takes TRIG IN's rise as its reference, and the reference-to-event
    and reference-to-decision counters and 1.25 ns histograms (and the LAT register, TRIG IN to CMP_I) measure the one-way
    timing across the boards; JP203 sums TRIG IN into the receiver's Q ladder, harmless while its TX is muted."""
    tx, rx = link.tx.cl, link.rx.cl
    s = C.SCHEMES[scheme]
    out = {"exp": "events", "scheme": scheme, "period": period, "width": width, "count": count, "first_edge": first_edge,
           "delay": delay, "quiet": quiet, "confirm": confirm, "window": window, "settle": settle, "frac": frac, "ref": ref}
    ts = 1e3 / (link.rx.clk_mhz * link.rx.ser)
    if ref == "trig_in":
        tx.triggers(width=10, a="tx_event")
    rx.dsa(link.info.get("dsa", rx._dsa_db))
    st = link.ensure()
    out["look"] = st
    if not st["locked"]:
        out["error"] = "no lock"
        return out
    if dsa is not None:
        rx.dsa(dsa)
        time.sleep(0.05)
        out["side_at_level"] = link.recheck_side()
    leg = link.leg()
    out["leg"] = leg
    if s.pilot is not None:                          # B1, B2, A4: the idle is a weak pilot, made with VR (pilot_cal)
        pc = pilot_cal(link, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            link.tx.cl.dac(VR_I=link.tx.vr(link.mhz)[0][0], VR_Q=link.tx.vr(link.mhz)[0][1])
            return out
        out["side_on_pilot"] = recheck_side_on_idle(link, s)
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(link, s, frac)    # from the received constellation
    idle = link.pt(*s.idle)
    link.hold(s.idle)                                # the scheme's own idle for the false-event count
    time.sleep(0.05)
    n_samp = period * link.rx.ser
    shift = max(0, int(math.ceil(math.log2(2.6 * n_samp / 1024.0))))
    rows = {}
    try:
        # the idle alone: false events a second
        iv, lut_full, sexp, out["rx_info"] = rx_tables(link, s, first_edge)
        tx.tx_points(idle, [link.pt(*p) for p in s.msgs])
        rx.rx_config(iv, s.mask, lut_full, sexp, delay=delay, quiet=quiet, confirm=confirm, window=window,
                     first_edge=first_edge, settle=settle, ref=ref)
        rx.rx_clear()
        time.sleep(idle_s)
        rx.rx_enable(False)
        q = rx.rx_stats()
        out["idle_false_per_s"] = q["events"] / idle_s
        hists = ["event_to_event"] + (["ref_to_event", "ref_to_decision"] if ref == "trig_in" else [])
        for m in ([msg] if msg is not None else range(s.n)):
            r = {}
            for what in hists:
                rx.rx_config(iv, s.mask, _cut(lut_full, m), sexp, delay=delay, quiet=quiet,
                             confirm=confirm, window=window, first_edge=first_edge, settle=settle, ref=ref)
                rx.hist_config(what, shift if what == "event_to_event" else 0)
                rx.rx_clear()
                tx.tx_points(idle, [link.pt(*p) for p in s.msgs])    # hold_point (the looks) rewrites them
                tx.tx_msg(m)
                tx.events(period=period, width=width, count=count, source="fixed", n=s.n)
                tx.tx_go()
                time.sleep(count * period / (link.tx.clk_mhz * 1e6) + 0.05)
                rx.rx_enable(False)
                q = rx.rx_stats()
                h = rx.histogram()
                tx.tx_stop()
                if what == "event_to_event":
                    b0 = int(round(n_samp / 2 ** shift))
                    near = lambda c, w=3: sum(h[max(0, c - w):c + w + 1])    # noqa: E731
                    r.update({"events": q["events"], "decided": q["decided"], "confirm": q["confirm"], "veto": q["veto"],
                              "right_frac": q["decided"] / count, "extra": q["events"] - count,
                              "intervals_1N": near(b0), "intervals_2N": near(2 * b0), "intervals_short": sum(h[:max(0, b0 - 4)]),
                              "intervals_other": sum(h) - near(b0) - near(2 * b0) - sum(h[:max(0, b0 - 4)]), "hist_shift": shift})
                else:
                    hs = _hist_summary(h, 0, ts)
                    hs["stats"] = {k: q.get(k) for k in ("refs", "missed", "false", "lat_n", "lat_min", "lat_max", "lat_mean")}
                    hs["lat_min_ns"] = q["lat_min"] * ts if q["lat_n"] else None
                    hs["lat_max_ns"] = q["lat_max"] * ts if q["lat_n"] else None
                    hs["lat_mean_ns"] = q["lat_mean"] * ts if q["lat_n"] else None
                    lat = rx.rd("LAT")
                    hs["LAT_trig_to_cmp_i_clocks"] = (lat & 0xFFFF) if (lat >> 16) & 1 else None
                    r[what] = hs
            rows[str(m)] = r
    finally:
        tx.tx_stop()
        if s.pilot is not None:
            (vi0, vq0), _ = link.tx.vr(link.mhz)
            tx.dac(VR_I=vi0, VR_Q=vq0)
        link.tx.idle((link.s, 0))
        rx.rx_enable(True)
        if dsa is not None:
            rx.dsa(link.info.get("dsa", rx._dsa_db))
    out["per_msg"] = rows
    out["right_frac_min"] = min(r["right_frac"] for r in rows.values())
    out["right_frac_mean"] = sum(r["right_frac"] for r in rows.values()) / len(rows)
    if ref == "trig_in":
        ev = [r["ref_to_event"] for r in rows.values() if r.get("ref_to_event", {}).get("n")]
        de = [r["ref_to_decision"] for r in rows.values() if r.get("ref_to_decision", {}).get("n")]
        if ev:
            out.update(arrival_p50_ns=sum(e["p50_ns"] for e in ev) / len(ev), arrival_min_ns=min(e["min_ns"] for e in ev),
                       arrival_max_ns=max(e["max_ns"] for e in ev))
        if de:
            out.update(decision_p50_ns=sum(d["p50_ns"] for d in de) / len(de), decision_p999_ns=max(d["p999_ns"] for d in de),
                       decision_max_ns=max(d["max_ns"] for d in de))
    return out


EVENTS_BASE = {"scheme": "A3", "period": 1000, "width": 20, "count": 20000, "first_edge": False, "delay": 16, "quiet": 4,
               "confirm": 6, "window": 100, "settle": 0, "frac": 0.4, "dsa": None}
EVENTS_OFAT = {
    "period": [50, 100, 200, 500, 1000, 5000, 20000],
    "width": [2, 5, 10, 20, 40, 100],
    "delay": [2, 4, 8, 12, 16, 24, 32, 48],
    "first_edge": [False, True],
    "quiet": [1, 2, 4, 8, 16],
    "settle": [0, 2, 4, 8],
    "frac": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "dsa": [0, 4, 7.75, 12, 16, 20, 24, 28],
}


def events_plan(schemes=None, quick=False):
    pts = []
    for sc in schemes or EVENT_SCHEMES:
        base = dict(EVENTS_BASE, scheme=sc)
        pts.append(dict(base, tag="base"))
        for k, vals in EVENTS_OFAT.items():
            for v in (vals[::2] if quick else vals):
                p = dict(base, tag="ofat_" + k, **{k: v})
                p["count"] = min(p["count"], max(2000, int(2e6 / p["period"])))    # about 20 ms of events at least
                pts.append(p)
        if not quick:
            for f, d in itertools.product([0.2, 0.3, 0.4, 0.55, 0.7], [0, 7.75, 14, 20, 26]):
                pts.append(dict(base, tag="grid_frac_dsa", frac=f, dsa=d))
    return pts


# ---------------------------------------------------------------------------------------------------------------------
# prover: one board's turnaround, in loopback through its switch block
# ---------------------------------------------------------------------------------------------------------------------
class Loop:
    """node on its own carrier at mhz (TX and RX synthesizers both there), the other board quiet with both parked"""
    def __init__(self, node, other, mhz, tr_a=1):
        self.node, self.other, self.mhz, self.tr_a = node, other, float(mhz), tr_a
        (vi, vq), _ = node.vr(mhz)
        self.cfg = dict(LINK_CFG, mhz=float(mhz), vr={"VR_I": vi, "VR_Q": vq})
        path = os.path.join(DATA, "cfg_%s_loop_%d.json" % (node.name, int(mhz)))
        json.dump(self.cfg, open(path, "w"))
        self.ld = linkd.LinkD(_Srv(node.cl), config=path)
        self.s = 1
        self.info = {}

    @property
    def name(self):
        return "%s loop" % self.node.name

    def up(self, tries=6):
        o = self.other.cl
        o.safe()
        o.pll_tune(0, park(self.mhz))
        o.pll_tune(1, park(self.mhz))
        for k in range(tries):
            cl = self.node.cl
            cl.safe()
            cl.ctrl(tr_a=self.tr_a)
            t0 = time.time()
            ok = self.ld.setup(self.cfg)
            cl.ctrl(tr_a=self.tr_a)
            if not ok:
                say("%s: setup found no lock (try %d)" % (self.name, k + 1))
                continue
            cl.hold_point(1, 0)
            time.sleep(0.05)
            o_ = self.ld.observe()
            self.s = 1 if o_["di"] > 0 else -1
            self.info = {"ok": ok, "setup_s": round(time.time() - t0, 1), "dsa": cl._dsa_db, "leg": self.ld.leg,
                         "vc_lock": self.ld.vc_lock, "cen": self.ld.cen, "side": self.s, "try": k}
            self.wcal = None
            self.slev = None
            say("%s at %g MHz: locked in %.0f s, DSA %.2f, leg %.1f mV, side %+d" % (
                self.name, self.mhz, self.info["setup_s"], cl._dsa_db, 1e3 * self.ld.leg, self.s))
            return True                               # either side: the points are mapped (txp), the table nominal
        return False

    def leg(self):
        cl = self.node.cl
        self.hold((1, 0))
        time.sleep(0.03)
        return abs(sum(cl.adc("I") for _ in range(4)) / 4.0 - self.ld.i0)

    def recheck_side(self):
        self.hold((1, 0))
        time.sleep(0.05)
        o = self.ld.observe()
        if abs(o["di"]) < 0.005:
            return None
        if o["di"] < 0:
            self.s = -self.s
            self.wcal = self.slev = None
            say("%s: the side changed with the level (%+d)" % (self.name, self.s))
        return self.s

    def windows(self, frac, leg=None):
        return set_windows(self, frac)

    def rx_cl(self):
        return self.node.cl

    def txp(self, i, q):
        return (self.s * i, -self.s * q)             # as Link.txp: the board's own TX through its own inverted I arm

    def pt(self, i, q):
        return C.point_code(*self.txp(i, q))

    def hold(self, p):
        self.node.cl.tx_stop()
        self.node.cl.hold_point(*self.txp(*p))

    def events_on(self, p, W, N, idle=(1, 0)):
        t = self.node.cl
        t.tx_points(self.pt(*idle), [self.pt(*p)])
        t.tx_msg(0)
        t.events(period=N, width=W, count=10000000, source="fixed", n=1)     # count 0 sends none
        t.tx_go()

    def events_off(self):
        self.hold((1, 0))

    def ensure(self):
        self.hold((1, 0))
        time.sleep(0.03)
        o = self.ld.observe()
        if o["locked"] and abs(o["di"]) > 0.01:       # either side
            side = self.s * (1 if o["di"] > 0 else -1)   # hold((1, 0)) sent (s, 0)
            if side != self.s:
                say("%s: the lock is on the other side (%+d)" % (self.name, side))
                self.s = side
            return True
        ok, _ = self.ld.recover()
        if ok:
            self.node.cl.hold_point(1, 0)                 # raw (1, 0): the sign of I is the side itself
            time.sleep(0.05)
            s_new = 1 if self.ld.observe()["di"] > 0 else -1
            if s_new != self.s:
                say("%s: the lock came back on the other side (%+d)" % (self.name, s_new))
            self.s = s_new
            return True
        if not self.up(tries=2):
            raise LinkDown("%s at %g MHz: no lock after recover and setup" % (self.name, self.mhz))
        return True

    def state(self):
        return {"link": self.name, "mhz": self.mhz, "dsa": self.node.cl._dsa_db, "tr_a": self.tr_a, "side": self.s,
                "wifi": wifi_tag(self.mhz)}


def reply_maps(n):
    """every reply function without a fixed point (a fixed point answers with no change, which nothing can time):
    the XOR masks first, then the rest of the derangements (n = 4: 3 masks, 9 derangements)"""
    if n == 2:
        return {"xor1": [1, 0]}
    if n != 4:
        return {"next": [(k + 1) % n for k in range(n)]}
    maps = {"xor%d" % m: [k ^ m for k in range(4)] for m in (1, 2, 3)}
    for p in itertools.permutations(range(4)):
        if all(p[k] != k for k in range(4)) and list(p) not in maps.values():
            maps["perm" + "".join(map(str, p))] = list(p)
    return maps


def _vec(cap, i, mask=0x1F):
    return sum(cap[nm][i] << b for b, nm in enumerate(C.CMP_NAMES)) & mask


def _code_map(ctx):
    """nominal ladder code -> the code the board must send for the receiver to see it (the mirror, txp)"""
    return {C.point_code(i, q): ctx.pt(i, q) for i in (-1, 0, 1) for q in (-1, 0, 1)}


def _fast_load(cl, entries, mode="oneshot", clocks=1, arm_on="tx"):
    """the driver's fast_config by registers (its table's integer keys do not survive the network's JSON)"""
    use, words = 0, [0, 0, 0, 0]
    for v, pt in entries.items():
        use |= 1 << v
        words[v >> 3] |= (pt & 0xF) << (4 * (v & 7))
    cl.wr("FP_CTRL", 2)
    for k in range(4):
        cl.wr("FP_MAP%d" % k, words[k])
    cl.wr("FP_USE", use)
    cl.wr("FP_TIME", max(1, int(clocks)))
    cl.wr("FP_CTRL", {"oneshot": 0, "ring": 1}[mode] << 2 | {None: 0, "tx": 1 << 3, "rx": 1 << 4}[arm_on])
    t0 = time.time()
    while cl.rd("FP_CTRL") & (1 << 5):              # the tables shift into their LUTs
        if time.time() - t0 > 1.0:
            raise TimeoutError("FP_CTRL still loading")
        time.sleep(0.001)


def _loop_arm(loop, s, path, rmap, first_edge, delay, reply_width, fp_clocks, quiet=4, confirm=6, window=100, settle=0):
    """the driver's _turnaround_setup with the points mapped: the sender's codes txp'd, the receiver's table nominal"""
    cl = loop.node.cl
    cl.tx_stop()
    cl.tx_points(loop.pt(*s.idle), [loop.pt(*m) for m in s.msgs])
    iv, lut, sexp, loop.rx_info = rx_tables(loop, s, first_edge)
    cl.tx_points(loop.pt(*s.idle), [loop.pt(*m) for m in s.msgs])
    cl.rx_config(iv, s.mask, lut, sexp, delay=delay, quiet=quiet, confirm=confirm, window=window, first_edge=first_edge,
                 settle=settle)
    if path == "sync":
        cl.fast_off()
        cl.reply_config(list(rmap), width=reply_width, once=True, rearm="tx")
    elif path == "fast":
        cl.reply_off()
        cm = _code_map(loop)
        owners = (getattr(loop, "rx_info", None) or {}).get("owners") or {}
        ent = {v: cm[C.point_code(*s.msgs[rmap[k]])] for v, k in owners.items() if k in range(len(rmap))}
        _fast_load(cl, ent, "oneshot", fp_clocks, "tx")
    else:
        raise ValueError("path: 'sync' or 'fast'")


def loop_turnaround(loop, s, path, rmap, count=5000, period=1000, width=20, first_edge=False, delay=16, reply_width=40,
                    fp_clocks=1, guard=8, window=50, mask=0x1E):
    """the driver's loopback_turnaround, from here (stimulus 'tx': this board's events, messages counted round)"""
    cl = loop.node.cl
    _loop_arm(loop, s, path, rmap, first_edge, delay, reply_width, fp_clocks)
    cl.turnaround_config(mask=mask, guard=guard, window=window)
    cl.rx_clear()
    cl.events(period=period, width=width, count=count, n=s.n)
    cl.tx_go()
    time.sleep((period * count + 200) / (loop.node.clk_mhz * 1e6) + 0.02)
    st = cl.turnaround_stats()
    st["rx"] = cl.rx_stats()
    st["reply"] = cl.reply_stat() if path == "sync" else cl.fast_state()
    return st


def loop_captures(loop, s, path, rmap, msgs, first_edge=False, delay=16, width=20, reply_width=40, fp_clocks=1, post=256,
                  guard=8, mask=0x1E):
    """one stimulus per challenge in msgs, each captured (the comparators and the ladder pads, sample by sample) with
    its times; the reply path armed once (it re-arms on each of this board's TX events)"""
    cl = loop.node.cl
    _loop_arm(loop, s, path, rmap, first_edge, delay, reply_width, fp_clocks)
    out = []
    for msg in msgs:
        cl.tx_msg(msg)
        cl.events(period=1000, width=width, count=1, source="fixed", n=s.n)
        cap = cl.capture("tx_event", post=post, start={"__method__": "tx_go"})
        r = C.CostasLink.turnaround_from_capture(None, cap, guard=guard, mask=mask)
        r["capture"] = cap
        r["msg_sent"] = msg
        out.append(r)
    return out


def check_capture(s, cap, reply_map, loop=None):
    """the stimulus and the reply on the ladder pins, and the reply as received (the settled vector after the second
    arrival), against the scheme and the reply function"""
    c = cap["capture"]
    pins = c.get("TX_PINS")
    out = {k: cap.get(k) for k in ("t1", "t3", "turnaround_ns", "ref_to_arrival_ns", "fpga_ns", "loop_ns", "loop2_ns")}
    codes = {(loop.pt(*p) if loop is not None else C.point_code(*p)): k for k, p in enumerate(s.msgs)}
    if pins is not None and cap.get("t0p") is not None and cap.get("t2") is not None:
        lag = c.get("tx_pins_lag", 0)
        t0 = c["trigger_sample"]
        a0, a2 = t0 + cap["t0p"] + lag, t0 + cap["t2"] + lag
        seg = pins[a0:a2] or [pins[min(len(pins) - 1, a0)]]
        stim = max(set(seg), key=seg.count)                        # the code held from the stimulus to the reply
        seg2 = [x for x in pins[a2:a2 + 8] if x != stim] or [pins[min(len(pins) - 1, a2)]]
        rep = max(set(seg2), key=seg2.count)                       # the reply's code over its first clock
        out["msg_sent"] = cap.get("msg_sent")
        k = codes.get(stim)
        out.update(stim_code=stim, reply_code=rep, stim_msg=k, reply_msg=codes.get(rep))
        out["reply_right_pins"] = (k is not None and codes.get(rep) == reply_map[k])
    if cap.get("t3") is not None:
        t0 = c["trigger_sample"]
        i = min(len(c["CMP_I"]) - 1, t0 + cap["t3"] + 12)
        own = C.CostasLink.vector_owners(s, first_edge=False)
        v = _vec(c, i)
        out["rx_vector"] = v
        out["rx_msg"] = own.get(v)
        if out.get("stim_msg") is not None:
            out["reply_right_rx"] = own.get(v) == reply_map[out["stim_msg"]]
    return out


def prover_point(loop, scheme="A3", path="fast", reply="xor1", count=5000, period=1000, width=20, first_edge=False,
                 delay=16, reply_width=40, fp_clocks=1, guard=8, window=50, mask=0x1E, frac=0.4, dsa=None, caps=2):
    cl = loop.node.cl
    s = C.SCHEMES[scheme]
    maps = reply_maps(s.n)
    rmap = maps.get(reply, list(maps.values())[0])
    out = {"exp": "prover", "scheme": scheme, "path": path, "reply": reply, "reply_map": rmap, "count": count,
           "period": period, "width": width, "first_edge": first_edge, "delay": delay, "reply_width": reply_width,
           "fp_clocks": fp_clocks, "guard": guard, "window": window, "mask": mask, "frac": frac}
    cl.dsa(loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    if dsa is not None:
        cl.dsa(dsa)
        time.sleep(0.05)
        out["side_at_level"] = loop.recheck_side()
    leg = loop.leg()
    out["leg"] = leg
    if s.pilot is not None:
        pc = pilot_cal(loop, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
            return out
        out["side_on_pilot"] = recheck_side_on_idle(loop, s)
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(loop, s, frac)
    try:
        st = loop_turnaround(loop, s, path, rmap, count=count, period=period, width=width, first_edge=first_edge,
                             delay=delay, reply_width=reply_width, fp_clocks=fp_clocks, guard=guard, window=window, mask=mask)
        out["stats"] = {k: st.get(k) for k in ("n", "miss", "min", "max", "mean", "min_ns", "mean_ns", "max_ns", "arrivals",
                                               "sample_ns", "last_ref_to_arrival")}
        out["rx"] = st.get("rx")
        out["reply_state"] = st.get("reply")
        caps_ = loop_captures(loop, s, path, rmap, [j % s.n for j in range(caps)], first_edge=first_edge, delay=delay,
                              width=width, reply_width=reply_width, fp_clocks=fp_clocks, guard=guard, mask=mask)
        cs = [check_capture(s, cap, rmap, loop) for cap in caps_]
        out["captures"] = cs
        good = [c for c in cs if c.get("turnaround_ns") is not None]
        out["cap_turn_ns"] = sorted(c["turnaround_ns"] for c in good)
        out["cap_right_pins"] = sum(1 for c in cs if c.get("reply_right_pins"))
        out["cap_right_rx"] = sum(1 for c in cs if c.get("reply_right_rx"))
        out["cap_fpga_ns"] = sorted(c["fpga_ns"] for c in cs if c.get("fpga_ns") is not None)
        out["cap_loop_ns"] = sorted(c["loop_ns"] for c in cs if c.get("loop_ns") is not None)
    finally:
        cl.reply_off()
        cl.fast_off()
        cl.wr("RT_CFG", 0)
        cl.tx_stop()
        if s.pilot is not None:
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
        loop.hold((1, 0))
        if dsa is not None:
            cl.dsa(loop.info.get("dsa", cl._dsa_db))
    return out


PROVER_BASE = {"scheme": "A3", "path": "fast", "reply": "xor1", "count": 5000, "period": 1000, "width": 20,
               "first_edge": False, "delay": 16, "reply_width": 40, "fp_clocks": 1, "frac": 0.4, "dsa": None}
PROVER_OFAT = {
    "path": ["fast", "sync"],
    "frac": [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6],
    "delay": [2, 4, 8, 12, 16, 24],
    "first_edge": [False, True],
    "fp_clocks": [1, 2, 4, 8],
    "width": [10, 20, 40, 80],
    "dsa": [16, 20, 24, 26, 28, 30, 31.75],
}
PROVER_SCHEMES = ["A3", "A2", "B1", "B2"]   # A1 / A1w have one message: no reply can differ from its stimulus


def prover_plan(schemes=None, quick=False):
    pts = []
    for sc in schemes or PROVER_SCHEMES:
        s = C.SCHEMES[sc]
        for path in ("fast", "sync"):
            base = dict(PROVER_BASE, scheme=sc, path=path)
            for rname in reply_maps(s.n):                       # every reply function, both paths
                pts.append(dict(base, tag="reply", reply=rname, caps=s.n))       # one capture a challenge
            for k, vals in PROVER_OFAT.items():
                if k == "path":
                    continue
                for v in (vals[::2] if quick else vals):
                    pts.append(dict(base, tag="ofat_" + k, **{k: v}))
    return pts


# ---------------------------------------------------------------------------------------------------------------------
# the runner
# ---------------------------------------------------------------------------------------------------------------------
def run_points(log, ctx, fn, pts, label):
    n = len(pts)
    t0 = time.time()
    for k, p in enumerate(pts):
        tag = p.pop("tag", None)
        try:
            r = fn(ctx, **p)
        except LinkDown as e:
            log(label=label, tag=tag, params=p, state=ctx.state(), error="link down: " + str(e))
            say("%s: %s: the remaining %d points abandoned" % (label, e, n - k - 1))
            return
        except Exception as e:                                  # noqa: BLE001  (one bad point must not end the night)
            r = {"error": repr(e)[:300], "tb": traceback.format_exc()[-800:]}
            say("%s %d/%d %s: %r" % (label, k + 1, n, p, e))
            try:
                ctx.ensure()
            except LinkDown as e2:
                log(label=label, tag=tag, params=p, state=ctx.state(), error="link down: " + str(e2), **r)
                say("%s: %s: the remaining %d points abandoned" % (label, e2, n - k - 1))
                return
            except Exception as e2:                             # noqa: BLE001
                say("ensure after the error: %r" % (e2,))
        log(label=label, tag=tag, params=p, state=ctx.state(), **r)
        if (k + 1) % 20 == 0 or k + 1 == n:
            say("%s: %d of %d points, %.0f s" % (label, k + 1, n, time.time() - t0))


def summary_line(r):
    if r.get("exp") == "prbs":
        return "%s P%d: %s errors / %.3g bits" % (r["const"], r["period"], r.get("errors"), r.get("bits") or 0)
    return ""


def cmd_check(a, log):
    nodes = {n: Node(n) for n in ("A", "B")}
    for d in a.dir:
        tx, rx = nodes[d[0]], nodes[d[1]]
        for mhz in a.mhz:
            L = Link(tx, rx, mhz)
            ok = L.up()
            log(label="check", exp="setup", state=L.state(), **L.info)
            if not ok:
                continue
            for c in ("bpsk", "ook_ip", "qbit"):
                r = prbs_point(L, const=c, period=50, seconds=1.0)
                log(label="check", state=L.state(), **r)
                say("%s %g MHz %s: BER %s (%d bits)" % (L.name, mhz, c, r.get("ber"), r.get("bits") or 0))
            r = events_point(L, scheme="A3", count=5000)
            log(label="check", state=L.state(), **r)
            say("%s %g MHz A3 events: right %s, idle false %.1f/s" % (L.name, mhz, [round(x["right_frac"], 4) for x in r.get("per_msg", {}).values()],
                                                                      r.get("idle_false_per_s") or 0))
            tx.quiet()
    for n in ("A", "B"):
        lp = Loop(nodes[n], nodes["B" if n == "A" else "A"], a.mhz[0])
        if lp.up():
            log(label="check", exp="loop_setup", state=lp.state(), **lp.info)
            for path in ("fast", "sync"):
                r = prover_point(lp, scheme="A3", path=path, caps=4)
                log(label="check", state=lp.state(), **r)
                say("%s A3 %s: n %s miss %s, %.2f / %.2f / %.2f ns; captures right %s/%s pins, %s rx" % (
                    lp.name, path, (r.get("stats") or {}).get("n"), (r.get("stats") or {}).get("miss"),
                    (r.get("stats") or {}).get("min_ns") or 0, (r.get("stats") or {}).get("mean_ns") or 0,
                    (r.get("stats") or {}).get("max_ns") or 0, r.get("cap_right_pins"), len(r.get("captures") or []),
                    r.get("cap_right_rx")))
        nodes[n].quiet()


def cmd_prbs(a, log):
    nodes = {n: Node(n) for n in ("A", "B")}
    for mhz in a.mhz:
        for d in a.dir:
            L = Link(nodes[d[0]], nodes[d[1]], mhz)
            if not L.up():
                log(label="prbs", exp="setup", state=L.state(), **L.info)
                continue
            log(label="prbs", exp="setup", state=L.state(), **L.info)
            run_points(log, L, prbs_point, prbs_plan(a.const, a.quick), "prbs %s %g" % (L.name, mhz))
            L.tx.quiet()


def cmd_events(a, log):
    nodes = {n: Node(n) for n in ("A", "B")}
    for mhz in a.mhz:
        for d in a.dir:
            L = Link(nodes[d[0]], nodes[d[1]], mhz)
            if not L.up():
                log(label="events", exp="setup", state=L.state(), **L.info)
                continue
            log(label="events", exp="setup", state=L.state(), **L.info)
            pts = events_plan(a.scheme, a.quick)
            if getattr(a, "ref", "tx") != "tx":
                for p_ in pts:
                    p_["ref"] = a.ref
            run_points(log, L, events_point, pts, "events %s %g" % (L.name, mhz))
            L.tx.quiet()


def cmd_prover(a, log):
    nodes = {n: Node(n) for n in ("A", "B")}
    for mhz in a.mhz:
        for b in a.board:
            lp = Loop(nodes[b], nodes["B" if b == "A" else "A"], mhz, tr_a=a.tr_a)
            if not lp.up():
                log(label="prover", exp="loop_setup", state=lp.state(), ok=False)
                continue
            log(label="prover", exp="loop_setup", state=lp.state(), **lp.info)
            run_points(log, lp, prover_point, prover_plan(a.scheme, a.quick), "prover %s %g" % (b, mhz))
            nodes[b].quiet()


def cmd_band(a, log):
    """each frequency, each direction: the link up, its level, a reduced prbs / events set; the loopback there"""
    nodes = {n: Node(n) for n in ("A", "B")}
    prbs_pts = [dict(PRBS_BASE, const=c, frac=CONST_FRAC.get(c, 0.5), tag="band") for c in CONSTS] + \
        [dict(PRBS_BASE, period=p, tag="band_period") for p in (10, 20, 100)] + \
        [dict(PRBS_BASE, const="ook_ip", frac=f, tag="band_frac") for f in (0.2, 0.35, 0.65, 0.8)]
    ev_pts = [dict(EVENTS_BASE, scheme=sc, tag="band") for sc in EVENT_SCHEMES] + \
        [dict(EVENTS_BASE, frac=f, tag="band_frac") for f in (0.2, 0.3, 0.55)]
    for mhz in a.mhz:
        for d in a.dir:
            L = Link(nodes[d[0]], nodes[d[1]], mhz)
            ok = L.up(tries=2)
            log(label="band", exp="setup", state=L.state(), **L.info)
            if not ok:
                L.tx.quiet()
                continue
            look = L.look()
            log(label="band", exp="level", state=L.state(), **look)
            run_points(log, L, prbs_point, [dict(p) for p in prbs_pts], "band prbs %s %g" % (L.name, mhz))
            run_points(log, L, events_point, [dict(p) for p in ev_pts], "band events %s %g" % (L.name, mhz))
            L.tx.quiet()
        if a.prover:
            for b in ("A", "B"):
                lp = Loop(nodes[b], nodes["B" if b == "A" else "A"], mhz)
                if not lp.up(tries=4):
                    log(label="band", exp="loop_setup", state=lp.state(), ok=False)
                    continue
                log(label="band", exp="loop_setup", state=lp.state(), **lp.info)
                pts = [dict(PROVER_BASE, path=p, tag="band") for p in ("fast", "sync")] + \
                    [dict(PROVER_BASE, frac=f, tag="band_frac") for f in (0.2, 0.3)]
                run_points(log, lp, prover_point, pts, "band prover %s %g" % (b, mhz))
                nodes[b].quiet()


def open_sa(tries=3):
    """the DSA875 on USB, with a USBTMC device clear and another try when its first read times out (an interrupted
    sweep leaves a half-finished message in the endpoint: 2026-11-04 22:07, two campaigns dead at their first line)"""
    import scpi_link
    from rigol_DSA875 import DSA875, usbtmc_node, USB_VENDOR, USB_PRODUCT
    node = usbtmc_node(USB_VENDOR, USB_PRODUCT)
    last = None
    for k in range(tries):
        try:
            return DSA875(usb=node)
        except Exception as e:                                  # noqa: BLE001
            last = e
            say("the analyzer did not answer (%r): a device clear, try %d" % (e, k + 2))
            try:
                L = scpi_link.Link(usb=node, idn=None, timeout=5)
                L.clear()
                L.close()
            except Exception as e2:                             # noqa: BLE001
                say("  the clear failed: %r" % (e2,))
            time.sleep(2)
    raise last


def null_fpv(node, other, mhz, sa, start=None, att=0, ref=-40.0):
    """the board's TX output null at mhz found on the DSA875's FPV antenna (the carrier over the air, near the beam): the
    other board quiet with both synthesizers parked, this one's TX on mhz (its RX synthesizer parked, REVB 57), TR_A 0;
    the carrier (1, 0) found, then the null (0, 0) with VR_I, VR_Q on grids (6 mV over +-24, 1.5 over +-6, 0.75 over
    +-1.5) about `start` (the nearest null known), never above 0.55 V.  The analyzer's floor at 0 dB, 1 kHz is about
    -110 dBm, so a -50 dBm carrier's null is read to about -60 dBc."""
    import numpy as np
    o, cl = other.cl, node.cl
    o.safe()
    o.pll_tune(0, park(mhz))
    o.pll_tune(1, park(mhz))
    cl.safe()
    cl.pll_tune(0, mhz)
    cl.pll_tune(1, park(mhz))
    time.sleep(0.3)
    (vi0, vq0) = start or node.vr(mhz)[0]
    cl.dac(VR_I=vi0, VR_Q=vq0)
    cl.hold_point(1, 0)
    cl.ctrl(tr_a=0, tx_dis=0)
    time.sleep(0.1)
    sa.w(":SENSe:DETector:FUNCtion POSitive")
    sa.amplitude(attenuation=att, ref_level=ref)

    def peak(center, span, rbw):
        sa.frequency(center=center, span=span)
        sa.bandwidth(rbw=rbw, vbw=rbw)
        f, y = sa.trace(binary=True)
        k = int(np.argmax(y))
        return float(f[k]), float(y[k]), float(np.median(y))
    fc, pc, _ = peak(mhz * 1e6, 400e3, 3e3)
    fc, pc, floor_c = peak(fc, 20e3, 1e3)
    out = {"mhz": mhz, "board": node.name, "fc": fc, "carrier_dbm": pc, "start": (vi0, vq0), "locked": cl.pll_locked()}
    cl.hold_point(0, 0)
    time.sleep(0.05)

    def meas(vi, vq):
        if not (0.0 <= vi <= 0.55 and 0.0 <= vq <= 0.55):
            return 99.0
        cl.dac(VR_I=vi, VR_Q=vq)
        time.sleep(0.02)
        return peak(fc, 20e3, 1e3)[1]
    best = (vi0, vq0, meas(vi0, vq0))
    out["at_start_dbm"] = best[2]
    try:
        for step, half in ((0.006, 0.024), (0.0015, 0.006), (0.00075, 0.0015)):
            ci, cq = best[0], best[1]
            n = int(round(half / step))
            for di in range(-n, n + 1):
                for dq in range(-n, n + 1):
                    vi, vq = ci + di * step, cq + dq * step
                    p = meas(vi, vq)
                    if p < best[2]:
                        best = (vi, vq, p)
        rep = [meas(best[0], best[1]) for _ in range(4)]
        _, _, floor_n = peak(fc, 20e3, 1e3)
    finally:
        cl.dac(VR_I=vi0, VR_Q=vq0)
        cl.safe()
    out.update(vr=(round(best[0], 4), round(best[1], 4)), null_dbm=float(np.median(rep)), repeat=rep,
               depth_dbc=float(np.median(rep)) - pc, floor_dbm=floor_n, at_floor=float(np.median(rep)) - floor_n < 3.0)
    return out


def cmd_nulls(a, log):
    """each board's null at each frequency on the FPV antenna (the WiFi monitor must be stopped: one analyzer)"""
    sa = getattr(a, "sa", None) or open_sa()
    nodes = {n: Node(n) for n in ("A", "B")}
    try:
        table = json.load(open(NULL_FILE))
    except (OSError, ValueError):
        table = {}
    try:
        for b in a.board:
            for mhz in a.mhz:
                if str(float(mhz)) in table.get(b, {}) and not getattr(a, "redo", False):
                    continue
                r = null_fpv(nodes[b], nodes["B" if b == "A" else "A"], mhz, sa)
                log(label="nulls", exp="null_fpv", **r)
                say("%s %g MHz: carrier %.1f dBm, null %.1f dBm (%.1f dBc%s) at VR %.4f / %.4f (start %.4f / %.4f: %.1f dBm)" % (
                    b, mhz, r["carrier_dbm"], r["null_dbm"], r["depth_dbc"], ", at the floor" if r["at_floor"] else "",
                    r["vr"][0], r["vr"][1], r["start"][0], r["start"][1], r["at_start_dbm"]))
                table.setdefault(b, {})[str(float(mhz))] = {"vr": r["vr"], "depth_dbc": r["depth_dbc"], "carrier_dbm": r["carrier_dbm"],
                                                           "at_floor": r["at_floor"], "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                                           "method": "FPV antenna on the DSA875"}
                table[b][str(float(mhz))]["note"] = ("A's FPV view is its own board's radiation as much as its dish (the ripple, "
                                                     "13 dB p-p at 64 ns): possibly biased (3.7 mV in I at 5200 against TX ANT)"
                                                     if b == "A" else "B's FPV view is mostly its dish path (-13 dB local): "
                                                     "within 1.5 mV of TX ANT at 5200")
                json.dump(table, open(NULL_FILE, "w"), indent=1)
                if float(mhz) not in TX_ANT_NULL.get(b, {}):    # the TX ANT nulls stay where they were measured
                    VR_NULL[b][float(mhz)] = tuple(r["vr"])
    finally:
        sa.amplitude(attenuation=30, ref_level=20)
        sa.w(":SENSe:FREQuency:SPAN:FULL")
        sa.bandwidth(rbw="auto", vbw="auto")
        sa.run()


class WifiThread:
    """wifimon.py's monitor in this process, on the same clock as the tests: the DSA875 on the FPV antenna, 5.10-5.35 GHz
    (or about the link's carrier, +-150 MHz), every sweep, one record each 10 s (each 20 MHz channel's maximum with
    the link's own +-12 MHz left out, the band's excursions with their times); paused while a null sweep has the
    analyzer (pause() / resume())"""
    def __init__(self, sa, path, att=0, ref=-40.0):
        import threading
        self.sa, self.path, self.att, self.ref = sa, path, att, ref
        self.run_ev = threading.Event()
        self.run_ev.set()
        self.idle = threading.Event()
        self.stop = False
        self.carrier_mhz = 5200.0
        self.th = threading.Thread(target=self._loop, daemon=True)

    def start(self):
        self.th.start()
        return self

    def pause(self):
        self.run_ev.clear()
        self.idle.wait(30)

    def resume(self):
        self.idle.clear()
        self.run_ev.set()

    def _loop(self):
        import numpy as np
        f_out = open(self.path, "a")
        while not self.stop:
            if not self.run_ev.is_set():
                self.idle.set()
                self.run_ev.wait(1.0)
                continue
            try:
                fc = self.carrier_mhz * 1e6
                lo, hi = max(4.2e9, min(5.10e9, fc - 150e6)), max(5.35e9, fc + 150e6)
                self.sa.w(":SENSe:DETector:FUNCtion POSitive")
                self.sa.amplitude(attenuation=self.att, ref_level=self.ref)
                self.sa.frequency(start=lo, stop=hi)
                self.sa.bandwidth(rbw=1e6, vbw=1e6)
                t0 = time.time()
                chmax, carriers, events, n, floor, bmax = {}, [], [], 0, None, (-200.0, None)
                while time.time() - t0 < 10.0 and self.run_ev.is_set() and not self.stop:
                    f, y = self.sa.trace(binary=True)
                    f, y = np.asarray(f), np.asarray(y)
                    n += 1
                    near = np.abs(f - fc) < 2e6
                    if near.any():
                        carriers.append(float(y[near].max()))
                    m = np.abs(f - fc) < 12e6
                    for c, cf in WIFI_CH.items():
                        sel = (np.abs(f - cf * 1e6) <= 10e6) & ~m
                        if sel.any():
                            chmax[c] = max(chmax.get(c, -200.0), float(y[sel].max()))
                    band = (np.abs(f - fc) <= 94e6) & ~m
                    if band.any():
                        yb, fb = y[band], f[band]
                        fl = float(np.median(yb))
                        floor = fl if floor is None else min(floor, fl)
                        k = int(np.argmax(yb))
                        if yb[k] > bmax[0]:
                            bmax = (float(yb[k]), float(fb[k]))
                        if yb[k] > fl + 10 and len(events) < 12:
                            events.append((round(time.time(), 2), round(float(fb[k]) / 1e6, 1), round(float(yb[k]), 1)))
                f_out.write(json.dumps({"t": round(t0, 1), "kind": "s", "sweeps": n, "carrier_mhz": self.carrier_mhz,
                                        "carrier": round(float(np.median(carriers)), 1) if carriers else None,
                                        "floor": None if floor is None else round(floor, 1),
                                        "band_max": (round(bmax[0], 1), round(bmax[1] / 1e6, 1) if bmax[1] else None),
                                        "ch": {c: round(v, 1) for c, v in chmax.items()}, "events": events}) + "\n")
                f_out.flush()
            except Exception as e:                              # noqa: BLE001
                f_out.write(json.dumps({"t": round(time.time(), 1), "kind": "error", "error": repr(e)[:200]}) + "\n")
                f_out.flush()
                time.sleep(5)
        self.idle.set()


def soak(log, link, minutes=10.0, period=50, cond=None):
    """B -> A style: PRBS15 as BPSK every `period` clocks, the receiver's check 1 s at a time, a look at the idle
    carrier every minute, linkd's recover on a loss; each window logged with its time (for the WiFi records)"""
    t_end = time.time() + minutes * 60
    st = link.ensure()
    tx, rx = link.tx.cl, link.rx.cl
    rx.tx_timing(period=period)
    from costaslink import point_code as pc_  # noqa: F401

    def start_prbs():
        tx.tx_timing(period=period)
        tx.tx_points(link.pt(1, 0), [link.pt(1, 0), link.pt(-1, 0)])
        tx.tx_prbs(15)
        tx.tx_mode("prbs", n=2)
        tx.tx_go()

    def win(inv, secs):
        rx.ber_config(15, cdr=True, period=period, invert=inv, enable=True)
        time.sleep(secs)
        rx.ber_config(15, cdr=True, period=period, invert=inv, enable=False)
        return rx.ber()

    start_prbs()
    time.sleep(0.05)
    tr = {inv: win(inv, 0.3) for inv in (False, True)}
    inv = min(tr, key=lambda k: tr[k]["mismatches"] / max(1, tr[k]["bits"]))
    t_look = time.time()
    bits = errs = 0
    try:
        while time.time() < t_end:
            r = win(inv, 1.0)
            bits += r["bits"]
            errs += r["mismatches"] / 3.0
            log(label="soak", exp="soak_w", state=link.state(), bits=r["bits"], mm=r["mismatches"], invert=inv, cond=cond)
            frac = r["mismatches"] / max(1, r["bits"])
            if frac > 0.9 or time.time() - t_look > 60 or frac > 0.05:
                tx.tx_stop()
                look = link.ensure()
                d = rx.detectors()
                log(label="soak", exp="soak_look", state=link.state(), log_dbm=d.get("log_dbm"), cond=cond, **look)
                rx.tx_timing(period=period)
                start_prbs()
                time.sleep(0.05)
                tr = {inv_: win(inv_, 0.3) for inv_ in (False, True)}
                inv = min(tr, key=lambda k: tr[k]["mismatches"] / max(1, tr[k]["bits"]))
                t_look = time.time()
    finally:
        tx.tx_stop()
        link.tx.idle((link.s, 0))
    say("soak %s %.0f min (%s): %.3g bits, %.0f errors, BER %.2g" % (link.name, minutes, cond, bits, errs, errs / bits if bits else 0))
    return bits, errs


def _rand_params(rng, base, ofat, extra=None, keep=0.5):
    p = dict(base)
    for k, vals in ofat.items():
        if rng.random() > keep:
            p[k] = rng.choice(vals)
    for k, vals in (extra or {}).items():
        if rng.random() > keep:
            p[k] = rng.choice(vals)
    return p


def cmd_campaign(a, log):
    """until a.until: the nulls over the band (the analyzer's), the WiFi monitor from then on, the full sweeps at 5200, the
    band, full sweeps at 5400 / 4800 / 5800, then random sessions (a frequency, a direction, every parameter drawn
    jointly) with a 10-minute soak at 5200 every hour"""
    import random
    rng = random.Random(a.seed)
    t_end = time.mktime(time.strptime(a.until, "%Y-%m-%d %H:%M"))
    sa = None if a.no_wifi else open_sa()
    wifi = WifiThread(sa, os.path.join(DATA, "wifi_%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))) if sa else None
    nodes = {n: Node(n) for n in ("A", "B")}

    def left():
        return t_end - time.time()

    def step(name, fn, **kw):
        if left() <= 0:
            return
        b = argparse.Namespace(**dict(vars(a), **kw))
        say("campaign: %s %s" % (name, kw))
        log(label="campaign", exp="step", step=name, kw=kw)
        try:
            fn(b, log)
        except Exception as e:                                  # noqa: BLE001
            say("campaign: %s failed: %r" % (name, e))
            log(label="campaign", exp="step_error", step=name, error=repr(e)[:300], tb=traceback.format_exc()[-1200:])
    if not a.skip_nulls and sa:
        step("nulls", cmd_nulls, board=["B", "A"], mhz=a.band, sa=sa)
    if wifi:
        wifi.start()
    want = a.steps or ["timing", "events5200", "prbs5200", "band", "5400", "4800", "5800"]
    try:
        if "timing" in want:
            step("timing", cmd_timing, board=a.timing_boards, mhz=[5200.0], scheme=None)
        if "events5200" in want:
            step("events 5200", cmd_events, dir=["BA", "AB"], mhz=[5200.0])
        if "prbs5200" in want:
            step("prbs 5200", cmd_prbs, dir=["BA", "AB"], mhz=[5200.0])
        if "band" in want:
            step("band", cmd_band, dir=["BA", "AB"], mhz=a.band, prover=True)
        for f in (5400.0, 4800.0, 5800.0):
            if "%g" % f not in want:
                continue
            if wifi:
                wifi.carrier_mhz = f
            step("events %g" % f, cmd_events, dir=["BA", "AB"], mhz=[f], quick=True)
            step("prbs %g" % f, cmd_prbs, dir=["BA", "AB"], mhz=[f], quick=True)
            step("prover %g" % f, cmd_prover, board=["B", "A"], mhz=[f], quick=True)
        t_soak = 0.0
        while left() > 600:
            if time.time() - t_soak > 3600:
                if wifi:
                    wifi.carrier_mhz = 5200.0
                L = Link(nodes["B"], nodes["A"], 5200.0)
                if L.up():
                    try:                                        # the analyzer sweeping, then not (its own emission?)
                        if wifi:
                            soak(log, L, minutes=5.0, cond="analyzer sweeping")
                            wifi.pause()
                            soak(log, L, minutes=5.0, cond="analyzer paused")
                        else:
                            soak(log, L, minutes=10.0, cond="no analyzer")
                    except Exception as e:                      # noqa: BLE001
                        log(label="campaign", exp="soak_error", error=repr(e)[:300])
                    finally:
                        if wifi:
                            wifi.resume()
                nodes["B"].quiet()
                t_soak = time.time()
            mhz = float(rng.choice(a.band))
            if wifi:
                wifi.carrier_mhz = mhz
            d = rng.choice(["BA", "AB"])
            L = Link(nodes[d[0]], nodes[d[1]], mhz)
            log(label="random", exp="session", mhz=mhz, link=d)
            if L.up(tries=2):
                log(label="random", exp="setup", state=L.state(), **L.info)
                pts = []
                for _ in range(25):
                    c = rng.choice(list(CONSTS))
                    pts.append(_rand_params(rng, dict(PRBS_BASE, const=c, frac=CONST_FRAC.get(c, 0.5)), PRBS_OFAT,
                                            {"frac": PRBS_FRACS} if CONSTS[c][3] else {"ioff": PRBS_IOFFS}))
                run_points(log, L, prbs_point, [dict(p, tag="random") for p in pts], "random prbs %s %g" % (d, mhz))
                pts = []
                for _ in range(15):
                    pts.append(_rand_params(rng, dict(EVENTS_BASE, scheme=rng.choice(EVENT_SCHEMES)), EVENTS_OFAT))
                for p in pts:
                    p["width"] = min(p["width"], max(1, p["period"] // 3))
                    p["count"] = min(20000, max(2000, int(2e6 / p["period"])))
                run_points(log, L, events_point, [dict(p, tag="random") for p in pts], "random events %s %g" % (d, mhz))
            L.tx.quiet()
            if left() <= 600:
                break
            b = rng.choice(["A", "B"])
            lp = Loop(nodes[b], nodes["B" if b == "A" else "A"], mhz)
            if lp.up(tries=3):
                log(label="random", exp="loop_setup", state=lp.state(), **lp.info)
                pts = []
                for _ in range(12):
                    sc = rng.choice(PROVER_SCHEMES)
                    p = _rand_params(rng, dict(PROVER_BASE, scheme=sc), PROVER_OFAT,
                                     {"reply": list(reply_maps(C.SCHEMES[sc].n))})
                    p["width"] = max(p["width"], 10)
                    pts.append(dict(p, tag="random"))
                run_points(log, lp, prover_point, pts, "random prover %s %g" % (b, mhz))
            nodes[b].quiet()
    finally:
        if wifi:
            wifi.stop = True
            wifi.run_ev.set()
            wifi.th.join(30) if wifi.th.is_alive() else None
        if sa:
            try:
                sa.amplitude(attenuation=30, ref_level=20)
                sa.w(":SENSe:FREQuency:SPAN:FULL")
                sa.bandwidth(rbw="auto", vbw="auto")
                sa.run()
            except Exception as e:                              # noqa: BLE001
                say("the analyzer at the end: %r" % (e,))


def ripple(tx, rx, sa, f0=5200.0, half=50.0, step=1.0, f_pfd=1.0):
    """two paths of different delay ripple a level against frequency with period 1 / (their delay difference): the
    sender's carrier stepped f0 +- half in `step` MHz (integer-N at f_pfd), the receiver's RX synthesizer fixed at f0 (its
    log detector, the +-94 MHz band, no lock needed: the carrier falls inside it), the FPV antenna on the DSA875 at each
    step.  Returns the levels and, for each, the delay spectrum of the detrended linear power (|FFT| over frequency)"""
    import numpy as np
    tx.cl.safe()
    rx.cl.safe()
    rx.cl.pll_tune(0, park(f0))
    rx.cl.pll_tune(1, f0)
    rx.cl.ctrl(tr_a=1, tx_dis=1)
    rx.cl.dsa(21.75)
    tx.cl.pll_tune(1, park(f0))
    (vi, vq), _ = tx.vr(f0)
    tx.cl.dac(VR_I=vi, VR_Q=vq)
    tx.cl.hold_point(1, 0)
    tx.cl.ctrl(tr_a=0, tx_dis=0)
    sa.w(":SENSe:DETector:FUNCtion POSitive")
    sa.amplitude(attenuation=0, ref_level=-40)
    sa.bandwidth(rbw=3e3, vbw=3e3)
    rows = []
    try:
        for f in np.arange(f0 - half, f0 + half + 1e-9, step):
            tx.cl.pll_tune(0, float(f), f_pfd=f_pfd, cp=15 if f_pfd < 25 else None)   # cp 15: the loop's gain at a low PFD
            time.sleep(0.05)
            lk = tx.cl.pll_locked()["tx"]
            sa.frequency(center=float(f) * 1e6, span=300e3)
            fr, y = sa.trace(binary=True)
            k = int(np.argmax(y))
            d = rx.cl.detectors()
            rows.append({"mhz": float(f), "locked": lk, "fpv_dbm": float(y[k]), "fpv_hz": float(fr[k]),
                         "log_dbm": d.get("log_dbm"), "peak_dbm": d.get("peak_dbm")})
    finally:
        tx.cl.safe()
        rx.cl.safe()
    out = {"tx": tx.name, "rx": rx.name, "f0": f0, "step": step, "rows": rows}
    for key in ("fpv_dbm", "log_dbm"):
        v = np.array([r[key] if r[key] is not None else np.nan for r in rows], float)
        f = np.array([r["mhz"] for r in rows])
        ok = np.isfinite(v)
        if ok.sum() < 10:
            continue
        pw = 10 ** (v[ok] / 10)
        c = np.polyfit(f[ok] - f0, pw, 3)
        res = pw / np.polyval(c, f[ok] - f0) - 1.0                 # the ripple, a fraction of the smooth level
        n = 1 << int(np.ceil(np.log2(len(res) * 4)))
        spec = np.abs(np.fft.rfft(res * np.hanning(len(res)), n))
        tau = np.fft.rfftfreq(n, d=step * 1e6) * 1e9               # ns
        sel = tau > 15                                              # below one period across the span is the trend
        kk = int(np.argmax(spec[sel]))
        out[key + "_ripple_pp_db"] = float(10 * np.log10((1 + res.max()) / max(1e-6, 1 + res.min())))
        out[key + "_delay_ns"] = float(tau[sel][kk])
        out[key + "_delay_strength"] = float(spec[sel][kk] / max(1e-12, spec[sel].mean()))
        out[key + "_spectrum"] = [(round(float(t), 1), round(float(x), 4)) for t, x in zip(tau, spec) if t <= 400][::2]
    return out


def cmd_ripple(a, log):
    sa = getattr(a, "sa", None) or open_sa()
    nodes = {n: Node(n) for n in ("A", "B")}
    try:
        for d in a.dir:
            r = ripple(nodes[d[0]], nodes[d[1]], sa, f0=a.mhz[0])
            log(label="ripple", exp="ripple", **r)
            say("%s at %g +- 50 MHz: FPV ripple %.1f dB p-p, strongest delay %.0f ns (x%.1f the mean); %s's log detector ripple "
                "%.1f dB p-p, strongest delay %.0f ns (x%.1f)" % (d, a.mhz[0], r.get("fpv_dbm_ripple_pp_db", 0), r.get("fpv_dbm_delay_ns", 0),
                r.get("fpv_dbm_delay_strength", 0), d[1], r.get("log_dbm_ripple_pp_db", 0), r.get("log_dbm_delay_ns", 0), r.get("log_dbm_delay_strength", 0)))
    finally:
        sa.amplitude(attenuation=30, ref_level=20)
        sa.w(":SENSe:FREQuency:SPAN:FULL")
        sa.bandwidth(rbw="auto", vbw="auto")
        sa.run()


# ---------------------------------------------------------------------------------------------------------------------
# timing (QPV_TIMING_REVIEW.md section 5, T1-T4): in loopback, on the board's own clock
# ---------------------------------------------------------------------------------------------------------------------
class _LoopLink:
    """a Loop seen as a Link (the same board sends and receives), for prbs_point"""
    def __init__(self, loop):
        self.loop, self.tx, self.rx, self.mhz = loop, loop.node, loop.node, loop.mhz

    def __getattr__(self, n):
        return getattr(self.loop, n)

    def ensure(self):
        ok = self.loop.ensure()
        o = self.loop.ld.observe()
        return {"locked": bool(ok and o["locked"]), "di": o["di"], "dq": o["dq"], "vc": o["vc"],
                "received_dbm": self.loop.node.cl.received_dBm() if ok else None, "dsa": self.loop.node.cl._dsa_db}

    def look(self):
        return self.ensure()

    def windows(self, frac, leg=None, which=("QP", "QN", "IP", "IN")):
        return set_windows(self.loop, frac, which)


def _hist_summary(h, shift, ts_ns):
    """a histogram's bins (2^shift samples each) -> count, p50 / p99 / p99.9 / max in ns, and the bins (first 1000)"""
    n = sum(h[:-1])
    out = {"n": n, "overflow": h[-1]}
    if not n:
        return out
    acc, q = 0, {0.5: None, 0.99: None, 0.999: None}
    for k, c in enumerate(h[:-1]):
        acc += c
        for f in q:
            if q[f] is None and acc >= f * n:
                q[f] = k
    last = max(k for k, c in enumerate(h[:-1]) if c)
    first = min(k for k, c in enumerate(h[:-1]) if c)
    w = (2 ** shift) * ts_ns
    out.update(p50_ns=q[0.5] * w, p99_ns=q[0.99] * w, p999_ns=q[0.999] * w, max_ns=last * w, min_ns=first * w, bin_ns=w,
               bins=[(k, c) for k, c in enumerate(h[:-1]) if c][:400])
    return out


def evtiming_point(loop, scheme="A3", period=1000, width=20, count=20000, first_edge=False, delay=16, quiet=4,
                   confirm=6, window=100, settle=0, frac=0.5, dsa=None, idle_s=0.5):
    """T1: idle-to-1-in-N timing in loopback: per message, the RX engine's reference (this board's own TX event) to the
    event and to the decision, as counters and 1.25 ns histograms; the confusion matrix row (right / wrong); the idle's
    false rate"""
    cl = loop.node.cl
    s = C.SCHEMES[scheme]
    out = {"exp": "evtiming", "scheme": scheme, "period": period, "width": width, "count": count, "first_edge": first_edge,
           "delay": delay, "quiet": quiet, "confirm": confirm, "window": window, "settle": settle, "frac": frac}
    cl.dsa(loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    if dsa is not None:
        cl.dsa(dsa)
        time.sleep(0.05)
        out["side_at_level"] = loop.recheck_side()
    if s.pilot is not None:
        pc = pilot_cal(loop, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
            return out
        out["side_on_pilot"] = recheck_side_on_idle(loop, s)
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(loop, s, frac)
    ts = 1e3 / (loop.node.clk_mhz * loop.node.ser)                  # ns a sample
    rows = {}
    try:
        cl.tx_stop()
        cl.tx_points(loop.pt(*s.idle), [loop.pt(*m) for m in s.msgs])
        iv, lut, sexp, out["rx_info"] = rx_tables(loop, s, first_edge)
        cl.tx_points(loop.pt(*s.idle), [loop.pt(*m) for m in s.msgs])
        loop.hold(s.idle)
        cl.rx_config(iv, s.mask, lut, sexp, delay=delay, quiet=quiet, confirm=confirm, window=window, first_edge=first_edge,
                     settle=settle)
        cl.rx_clear()
        time.sleep(idle_s)
        cl.rx_enable(False)
        out["idle_false_per_s"] = cl.rx_stats()["events"] / idle_s
        for m in range(s.n):
            r = {}
            for what in ("ref_to_event", "ref_to_decision"):
                cl.rx_config(iv, s.mask, lut, sexp, delay=delay, quiet=quiet, confirm=confirm, window=window,
                             first_edge=first_edge, settle=settle)
                cl.hist_config(what, 0)
                cl.rx_clear()
                cl.tx_points(loop.pt(*s.idle), [loop.pt(*mm) for mm in s.msgs])
                cl.tx_msg(m)
                cl.events(period=period, width=width, count=count, source="fixed", n=s.n)
                cl.tx_go()
                time.sleep(count * period / (loop.node.clk_mhz * 1e6) + 0.05)
                cl.rx_enable(False)
                q = cl.rx_stats()
                h = cl.histogram()
                cm = cl.confusion()
                cl.tx_stop()
                loop.hold(s.idle)
                r[what] = _hist_summary(h, 0, ts)
                r[what]["stats"] = {k: q.get(k) for k in ("events", "decided", "false", "missed", "refs", "lat_n", "lat_min",
                                                           "lat_max", "lat_mean")}
                r[what]["lat_min_ns"] = q["lat_min"] * ts if q["lat_n"] else None
                r[what]["lat_max_ns"] = q["lat_max"] * ts if q["lat_n"] else None
                r[what]["lat_mean_ns"] = q["lat_mean"] * ts if q["lat_n"] else None
                r[what]["right"] = cm[m][m]
                r[what]["wrong"] = sum(cm[m]) - cm[m][m]
            rows[str(m)] = r
    finally:
        cl.tx_stop()
        if s.pilot is not None:
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
        loop.hold((1, 0))
        cl.rx_enable(True)
        if dsa is not None:
            cl.dsa(loop.info.get("dsa", cl._dsa_db))
    out["per_msg"] = rows
    dec = [r["ref_to_decision"] for r in rows.values() if r["ref_to_decision"].get("n")]
    if dec:
        out["decision_p50_ns"] = sum(d["p50_ns"] for d in dec) / len(dec)
        out["decision_p999_ns"] = max(d["p999_ns"] for d in dec)
        out["decision_max_ns"] = max(d["max_ns"] for d in dec)
    out["right_frac_min"] = min(r["ref_to_decision"]["right"] / count for r in rows.values()) if rows else None
    return out


EVT_BASE = {"scheme": "A3", "period": 1000, "width": 20, "count": 20000, "first_edge": False, "delay": 16, "quiet": 4,
            "confirm": 6, "window": 100, "settle": 0, "frac": 0.5, "dsa": None}
EVT_OFAT = {"delay": [2, 4, 8, 12, 16, 24, 32, 48], "settle": [2, 4, 8], "first_edge": [True],
            "frac": [0.2, 0.35, 0.5, 0.65, 0.8], "dsa": [16, 20, 24, 28, 31.75], "width": [5, 10, 40]}
EVT_SCHEMES = ["A3", "A2", "A1", "A1w", "B1", "B2"]


def evtiming_plan(schemes=None, quick=False):
    pts = []
    for sc in schemes or EVT_SCHEMES:
        base = dict(EVT_BASE, scheme=sc)
        pts.append(dict(base, tag="base"))
        for k, vals in EVT_OFAT.items():
            for v in (vals[::2] if quick else vals):
                pts.append(dict(base, tag="ofat_" + k, **{k: v}))
    return pts


def bitlat_point(loop, period=50, dsa=None, phases=(0.1, 0.3, 0.5, 0.7, 0.9), ioff=None, seconds=0.5):
    """T2: the bitstream's latency in loopback: during PRBS15 as BPSK every `period` clocks, one capture holds the ladder
    pins and CMP_I sample by sample: the lag at which CMP_I's sign best matches the ladder's I bit is the pins-to-comparator
    latency (1.25 ns samples); the BER at each sampling phase (the eye)"""
    import numpy as np
    cl = loop.node.cl
    L = _LoopLink(loop)
    out = {"exp": "bitlat", "period": period, "mbaud": loop.node.clk_mhz / period, "phases": list(phases)}
    cl.dsa(loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    if dsa is not None:
        cl.dsa(dsa)
        time.sleep(0.05)
    try:
        cl.tx_timing(period=period)
        cl.tx_points(loop.pt(1, 0), [loop.pt(1, 0), loop.pt(-1, 0)])
        cl.tx_prbs(15)
        cl.tx_mode("prbs", n=2)
        cl.tx_go()
        time.sleep(0.02)
        cap = cl.capture("any_change", post=cl.cap_info()["depth"] // 2)
        cl.tx_stop()
        loop.hold((1, 0))
        pins = np.array(cap["TX_PINS"], int)
        lag0 = cap.get("tx_pins_lag", 0)
        ib = np.where((pins & 3) == 3, 1.0, np.where((pins & 3) == 0, -1.0, 0.0))     # the I level's sign on the pins
        ci = np.array(cap["CMP_I"], float) * 2 - 1
        v = cap["valid_from"]
        ib, ci = ib[v:], ci[v:]
        n = len(ib)
        best = None
        corr = []
        for lag in range(0, 120):
            c = float(np.dot(ib[:n - lag], ci[lag:])) / max(1, n - lag)
            corr.append(round(c, 4))
            if best is None or abs(c) > abs(best[1]):
                best = (lag, c)
        ts = 1e3 / (loop.node.clk_mhz * loop.node.ser)
        out.update(lag_samples=best[0] - lag0, lag_ns=(best[0] - lag0) * ts, corr=best[1], corr_by_lag=corr,
                   samples=int(n), symbols=int(n / (period * loop.node.ser)))
        # the half-maximum points of the correlation peak: the edge's rise as the receiver sees it
        a = np.abs(np.array(corr))
        k = int(np.argmax(a))
        half = a[k] / 2
        lo = k
        while lo > 0 and a[lo] > half:
            lo -= 1
        hi = k
        while hi < len(a) - 1 and a[hi] > half:
            hi += 1
        out["corr_halfwidth_ns"] = (hi - lo) * ts
    finally:
        cl.tx_stop()
        loop.hold((1, 0))
    eye = {}
    for ph in phases:
        r = prbs_point(L, const="bpsk", period=period, phase_frac=ph, seconds=seconds, dsa=dsa)
        eye[str(ph)] = {"ber": r.get("ber"), "bits": r.get("bits"), "errors": r.get("errors")}
    out["eye"] = eye
    out["open_phases"] = sum(1 for e in eye.values() if e["ber"] is not None and e["ber"] < 1e-3)
    if dsa is not None:
        cl.dsa(loop.info.get("dsa", cl._dsa_db))
    return out


BITLAT_PERIODS = [1, 2, 3, 4, 5, 8, 10, 20, 50, 200]


def prover_dist_point(loop, scheme="A3", path="fast", reply="xor1", frac=0.5, per_challenge=16, first_edge=False,
                      delay=16, reply_width=40, fp_clocks=1, guards=(8, 12, 16, 24), mask=0x1E, width=20):
    """T3: the prover's turnaround as a distribution: `per_challenge` captures of each challenge (the turnaround and the
    FPGA's share per (challenge, reply)), and the counter with its guard swept"""
    cl = loop.node.cl
    s = C.SCHEMES[scheme]
    rmap = reply_maps(s.n).get(reply, list(reply_maps(s.n).values())[0])
    out = {"exp": "prover_dist", "scheme": scheme, "path": path, "reply": reply, "reply_map": rmap, "frac": frac,
           "first_edge": first_edge, "delay": delay, "reply_width": reply_width, "fp_clocks": fp_clocks, "width": width}
    cl.dsa(loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    if s.pilot is not None:
        pc = pilot_cal(loop, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
            return out
        out["side_on_pilot"] = recheck_side_on_idle(loop, s)
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(loop, s, frac)
    try:
        out["counter_by_guard"] = {}
        for g in guards:
            st = loop_turnaround(loop, s, path, rmap, count=5000, period=1000, width=width, first_edge=first_edge,
                                 delay=delay, reply_width=reply_width, fp_clocks=fp_clocks, guard=g, window=50, mask=mask)
            out["counter_by_guard"][str(g)] = {k: st.get(k) for k in ("n", "miss", "min_ns", "mean_ns", "max_ns")}
            out["counter_by_guard"][str(g)]["false"] = (st.get("rx") or {}).get("false")
        msgs = [m for m in range(s.n) for _ in range(per_challenge)]
        caps = loop_captures(loop, s, path, rmap, msgs, first_edge=first_edge, delay=delay, width=width,
                             reply_width=reply_width, fp_clocks=fp_clocks, guard=8, mask=mask)
        per = {}
        for cap in caps:
            c = check_capture(s, cap, rmap, loop)
            m = c.get("msg_sent")
            d = per.setdefault(str(m), {"turn_ns": [], "fpga_ns": [], "loop_ns": [], "right_rx": 0, "right_pins": 0, "n": 0})
            d["n"] += 1
            if c.get("turnaround_ns") is not None:
                d["turn_ns"].append(c["turnaround_ns"])
            if c.get("fpga_ns") is not None:
                d["fpga_ns"].append(c["fpga_ns"])
            if c.get("loop_ns") is not None:
                d["loop_ns"].append(c["loop_ns"])
            d["right_rx"] += bool(c.get("reply_right_rx"))
            d["right_pins"] += bool(c.get("reply_right_pins"))
        for m, d in per.items():
            for k in ("turn_ns", "fpga_ns", "loop_ns"):
                v = sorted(d[k])
                d[k + "_stats"] = ({"n": len(v), "min": v[0], "p50": v[len(v) // 2], "max": v[-1],
                                    "mean": sum(v) / len(v)} if v else None)
        out["per_challenge"] = per
        allt = sorted(t for d in per.values() for t in d["turn_ns"])
        if allt:
            out["turn_all"] = {"n": len(allt), "min": allt[0], "p50": allt[len(allt) // 2], "p99": allt[min(len(allt) - 1, int(0.99 * len(allt)))],
                               "max": allt[-1], "mean": sum(allt) / len(allt)}
        out["right_rx"] = sum(d["right_rx"] for d in per.values())
        out["captures_n"] = sum(d["n"] for d in per.values())
    finally:
        cl.reply_off()
        cl.fast_off()
        cl.wr("RT_CFG", 0)
        cl.tx_stop()
        if s.pilot is not None:
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
        loop.hold((1, 0))
    return out


def prover_prbs_point(loop, scheme="A3", path="fast", reply="xor1", frac=0.5, count=20000, period=1000, width=20,
                      decide_at=36, fp_hold=8, reply_width=40, first_edge=False, mask=0x1E):
    """T4: every challenge against every reply: the challenges chosen by the TX's PRBS, the reply map fixed; on the fast
    path the reply is held `fp_hold` clocks and the RX engine decides `decide_at` samples after the event, when the
    comparators show the reply: the confusion matrix [challenge][decoded] is the reply as received.  On the sync path the
    RX engine's decision is what makes the reply, so its matrix is the challenge's decode (the reply follows the map by
    construction); the reply_stat counts the replies"""
    cl = loop.node.cl
    s = C.SCHEMES[scheme]
    rmap = reply_maps(s.n).get(reply, list(reply_maps(s.n).values())[0])
    out = {"exp": "prover_prbs", "scheme": scheme, "path": path, "reply": reply, "reply_map": rmap, "frac": frac,
           "count": count, "decide_at": decide_at, "fp_hold": fp_hold, "reply_width": reply_width}
    cl.dsa(loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    if s.pilot is not None:
        pc = pilot_cal(loop, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
            return out
        out["side_on_pilot"] = recheck_side_on_idle(loop, s)
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(loop, s, frac)
    try:
        delay = decide_at if path == "fast" else 16
        _loop_arm(loop, s, path, rmap, first_edge, delay, reply_width, fp_hold)
        cl.turnaround_config(mask=mask, guard=8, window=50)
        cl.rx_clear()
        cl.events(period=period, width=width, count=count, source="prbs", n=s.n)
        cl.tx_go()
        time.sleep(count * period / (loop.node.clk_mhz * 1e6) + 0.05)
        cl.rx_enable(False)
        q = cl.rx_stats()
        cm = cl.confusion()
        st = cl.turnaround_stats()
        rs = cl.reply_stat() if path == "sync" else cl.fast_state()
        cl.tx_stop()
        loop.hold((1, 0))
        m4 = [row[:s.n] for row in cm[:s.n]]
        out["confusion"] = m4
        tot = sum(sum(r) for r in m4)
        if path == "fast":
            right = sum(m4[k][rmap[k]] for k in range(s.n))
            out["reply_right_frac"] = right / tot if tot else None
            out["per_challenge_right"] = [m4[k][rmap[k]] / sum(m4[k]) if sum(m4[k]) else None for k in range(s.n)]
        else:
            right = sum(m4[k][k] for k in range(s.n))
            out["decode_right_frac"] = right / tot if tot else None
            out["per_challenge_right"] = [m4[k][k] / sum(m4[k]) if sum(m4[k]) else None for k in range(s.n)]
        out["decided"], out["false"], out["refs"] = q.get("decided"), q.get("false"), q.get("refs")
        out["counter"] = {k: st.get(k) for k in ("n", "miss", "min_ns", "mean_ns", "max_ns")}
        out["reply_state"] = rs
    finally:
        cl.reply_off()
        cl.fast_off()
        cl.wr("RT_CFG", 0)
        cl.tx_stop()
        if s.pilot is not None:
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
        loop.hold((1, 0))
        cl.rx_enable(True)
    return out


def cmd_timing(a, log):
    """T1-T4 on each board in loopback"""
    nodes = {n: Node(n) for n in ("A", "B")}
    for mhz in a.mhz:
        for b in a.board:
            lp = Loop(nodes[b], nodes["B" if b == "A" else "A"], mhz)
            if not lp.up(tries=4):
                log(label="timing", exp="loop_setup", state=lp.state(), ok=False)
                continue
            log(label="timing", exp="loop_setup", state=lp.state(), **lp.info)
            # T3 first (the headline), then T4, T1, T2
            pts = []
            for sc in ("A2", "A3", "B2", "B1"):
                maps = list(reply_maps(C.SCHEMES[sc].n))
                for r in (maps[:3] if C.SCHEMES[sc].n == 4 else maps[:1]):
                    pts.append(dict(scheme=sc, path="fast", reply=r, tag="dist"))
                pts.append(dict(scheme=sc, path="sync", reply=maps[0], tag="dist"))
            run_points(log, lp, prover_dist_point, pts, "timing dist %s %g" % (b, mhz))
            pts = []
            for sc in ("A3", "B2", "B1", "A2"):
                for r in reply_maps(C.SCHEMES[sc].n):
                    pts.append(dict(scheme=sc, path="fast", reply=r, tag="prbs_map"))
                pts.append(dict(scheme=sc, path="sync", reply="xor1" if C.SCHEMES[sc].n == 4 else "xor1", tag="prbs_map"))
            for d in (28, 32, 44, 56):
                pts.append(dict(scheme="A3", path="fast", reply="xor1", decide_at=d, tag="ofat_decide_at"))
            run_points(log, lp, prover_prbs_point, pts, "timing prbs-map %s %g" % (b, mhz))
            run_points(log, lp, evtiming_point, evtiming_plan(a.scheme, a.quick), "timing events %s %g" % (b, mhz))
            pts = [dict(period=P, tag="rate") for P in BITLAT_PERIODS] + \
                  [dict(period=P, dsa=d, tag="rate_dsa") for P in (5, 20, 50) for d in (16, 22, 31.75)]
            run_points(log, lp, bitlat_point, pts, "timing bitlat %s %g" % (b, mhz))
            nodes[b].quiet()


def cmd_night(a, log):
    """the whole program, one thing on the boards at a time: the prover on each board; events and prbs both ways at
    the first frequency; the band (both ways, the loopback at each); events and prbs again at 5400 MHz (the WiFi gap)"""
    mhz0 = a.mhz[0]
    pilots = ["B1", "B2", "A4"]
    every = {"proverB": ("prover", dict(board=["B"], mhz=[mhz0])),
             "proverA": ("prover", dict(board=["A"], mhz=[mhz0])),
             "pilotB": ("prover", dict(board=["B"], mhz=[mhz0], scheme=["B1", "B2"])),
             "events": ("events", dict(dir=["BA", "AB"], mhz=[mhz0])),
             "prbs": ("prbs", dict(dir=["BA", "AB"], mhz=[mhz0])),
             "band": ("band", dict(dir=["BA", "AB"], mhz=a.band, prover=True)),
             "events5400": ("events", dict(dir=["BA", "AB"], mhz=[5400.0], quick=True)),
             "prbs5400": ("prbs", dict(dir=["BA", "AB"], mhz=[5400.0], quick=True)),
             "pilots_events": ("events", dict(dir=["BA", "AB"], mhz=[mhz0], scheme=pilots))}
    steps = [every[n] for n in (a.steps or ["proverB", "proverA", "events", "prbs", "band", "events5400", "prbs5400"])]
    for name, kw in steps:
        b = argparse.Namespace(**dict(vars(a), **kw))
        say("night: %s %s" % (name, kw))
        log(label="night", exp="step", step=name, kw=kw)
        try:
            {"prover": cmd_prover, "events": cmd_events, "prbs": cmd_prbs, "band": cmd_band}[name](b, log)
        except Exception as e:                                  # noqa: BLE001
            say("night: %s failed: %r" % (name, e))
            log(label="night", exp="step_error", step=name, error=repr(e)[:300], tb=traceback.format_exc()[-1200:])


BAND = [4400, 4600, 4800, 5000, 5100, 5150, 5180, 5200, 5240, 5300, 5320, 5400, 5450, 5500, 5540, 5600, 5700, 5745,
        5800, 5850, 5900, 6000]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["check", "prbs", "events", "prover", "band", "night", "nulls", "campaign", "ripple",
                                    "timing"])
    ap.add_argument("--until", default=None, help="campaign: 'YYYY-MM-DD HH:MM' (local time)")
    ap.add_argument("--seed", type=int, default=20261104, help="campaign: the random sessions' seed")
    ap.add_argument("--skip-nulls", action="store_true", help="campaign: the null table as it is")
    ap.add_argument("--no-wifi", action="store_true", help="campaign: without the analyzer (no WiFi monitor, no nulls)")
    ap.add_argument("--redo", action="store_true", help="nulls: measure again the frequencies already in the table")
    ap.add_argument("--timing-boards", nargs="+", default=["B", "A"], help="campaign: the boards for the timing step")
    ap.add_argument("--ref", choices=["tx", "trig_in"], default="tx", help="events: the receiver's reference ('trig_in': the "
                    "sender's TRIG OUT A on a lead to the receiver's TRIG IN: the timing across the boards)")
    ap.add_argument("--band", type=float, nargs="+", default=[float(f) for f in BAND], help="night: the band's frequencies")
    ap.add_argument("--steps", nargs="+", default=None, help="night: proverB proverA pilotB events prbs band events5400 "
                    "prbs5400 pilots_events (default proverB proverA events prbs band events5400 prbs5400); campaign: "
                    "timing events5200 prbs5200 band 5400 4800 5800 (default all), then the random sessions")
    ap.add_argument("--dir", nargs="+", default=["BA"], help="links, sender then receiver: BA, AB")
    ap.add_argument("--board", nargs="+", default=["B"], help="prover: the board(s) in loopback")
    ap.add_argument("--mhz", type=float, nargs="+", default=[5200.0])
    ap.add_argument("--const", nargs="+", default=None, help="prbs: the constellations (default all of CONSTS)")
    ap.add_argument("--scheme", nargs="+", default=None, help="events / prover: the schemes")
    ap.add_argument("--quick", action="store_true", help="every other value of each factor, no 2D grids")
    ap.add_argument("--prover", action="store_true", help="band: the loopback turnaround at each frequency too")
    ap.add_argument("--tr-a", type=int, default=1, help="prover: the board's T/R switch in loopback (0 or 1)")
    a = ap.parse_args(argv)
    log = Log(a.cmd)
    open(os.path.join(DATA, "twoboard.pid"), "w").write(str(os.getpid()))
    nodes_quiet = []
    try:
        {"check": cmd_check, "prbs": cmd_prbs, "events": cmd_events, "prover": cmd_prover, "band": cmd_band,
         "night": cmd_night, "nulls": cmd_nulls, "campaign": cmd_campaign, "ripple": cmd_ripple,
         "timing": cmd_timing}[a.cmd](a, log)
    finally:
        for n in ("A", "B"):
            try:
                Node(n).quiet()
                nodes_quiet.append(n)
            except Exception as e:                             # noqa: BLE001
                say("quiet %s: %r" % (n, e))
        say("done; %s quiet (TX muted, loop held, receive)" % nodes_quiet)


if __name__ == "__main__":
    main()
