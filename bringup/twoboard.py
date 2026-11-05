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
    return mhz + PARK_MHZ if mhz + PARK_MHZ <= 6000 else mhz - PARK_MHZ


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
    ctx.wcal, ctx.wcal_dsa = wc, rcl._dsa_db
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
    key = (s.name, rcl._dsa_db)
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
    return th, {"%s,%s" % p: {w: (None if x is None else round(x, 4)) for w, x in r.items()} for p, r in lv.items()}, gaps


def set_windows(ctx, frac, which=("QP", "QN", "IP", "IN")):
    """each window at its centre + frac x (its on level - its centre), calibrated at this DSA (again if it changed);
    linkd's rule (the ADC's leg from its fitted centre) where a comparator would not calibrate"""
    rcl = ctx.rx_cl()
    if getattr(ctx, "wcal", None) is None or getattr(ctx, "wcal_dsa", None) != rcl._dsa_db:
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


class Link:
    """a one-way link tx -> rx at mhz, set up and kept by linkd's own code run here"""
    def __init__(self, tx, rx, mhz, cfg=None):
        self.tx, self.rx, self.mhz = tx, rx, float(mhz)
        self.cfg = dict(LINK_CFG, tx_mhz=park(mhz), rx_mhz=float(mhz), **(cfg or {}))
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
        if s["locked"] and s["di"] * 1 > 0.01:
            return s
        ok, starts = self.ld.recover()
        say("%s: lock lost (%s); recover %s (%d starts)" % (self.name, s, ok, starts))
        if not ok:
            self.up()
        else:
            self.frame()
        return self.look()

    def leg(self):
        """the idle's I deflection now (the ADC; the windows scale with it)"""
        self.tx.idle((self.s, 0))
        time.sleep(0.03)
        return abs(sum(self.rx.cl.adc("I") for _ in range(4)) / 4.0 - self.ld.i0)

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
    rx.dsa(dsa if dsa is not None else link.info.get("dsa", rx._dsa_db))     # a DSA point must not outlive itself
    st = link.ensure()
    out["look"] = st
    if not st["locked"]:
        out["error"] = "no lock"
        return out
    leg = link.leg()
    out["leg"] = leg
    if wins:
        out["thresholds"] = link.windows(frac, leg, wins)
        out["wcal"] = link.wcal
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

    def search(ux, uy):
        sign, d, got = 1.0, d0, None
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
            # 30 mV (about 0.07 a by the slope 0.0024 a / mV) was too weak for the loop to stay on (it read 0 every
            # time, 2026-11-04 18:15), so the search starts near rho; only a clear reading on the other side flips it
            if r < -0.05:
                sign = -sign
                continue
            if r < 0.05:
                d *= 1.6
                continue
            got = (vi, vq, r, d)
            if abs(r - rho) <= 0.03:
                break
            d = d * rho / r
        return got

    if angle == 0:
        ux, uy = ctx.txp(1.0, 0.0)
        cands = [search(ux, uy)]
    else:
        ux, uy = ctx.txp(1 / math.sqrt(2), 1 / math.sqrt(2))
        cands = [search(ux, uy), search(ux, -uy)]
    cands = [c for c in cands if c is not None and abs(c[2] - rho) <= 0.06]
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
    return {"vr": (round(got[0], 4), round(got[1], 4)), "rho": got[2], "trace": trace, "a": a, "angle": angle}


# ---------------------------------------------------------------------------------------------------------------------
# events: idle to 1-in-N across the boards
# ---------------------------------------------------------------------------------------------------------------------
EVENT_SCHEMES = ["A3", "A2", "A1", "A1w", "B1", "B2", "A4"]   # B1 / B2 / A4 with the pilot (pilot_cal)


def _lut_only(s, m, first_edge):
    """the scheme's decoder table with only message m valid: a decision is then a right one"""
    return [(e if (e & 8) and (e & 7) == m else 0) for e in s.lut(first_edge)]


def events_point(link, scheme="A3", msg=None, period=1000, width=20, count=20000, first_edge=False, delay=16, quiet=4,
                 confirm=6, window=100, settle=0, frac=0.4, dsa=None, idle_s=0.5):
    """`count` events of each message (or of `msg`), every `period` clocks, `width` long; per message: the events seen,
    the right decisions, the event-to-event histogram's peaks; and the idle's false events in idle_s"""
    tx, rx = link.tx.cl, link.rx.cl
    s = C.SCHEMES[scheme]
    out = {"exp": "events", "scheme": scheme, "period": period, "width": width, "count": count, "first_edge": first_edge,
           "delay": delay, "quiet": quiet, "confirm": confirm, "window": window, "settle": settle, "frac": frac}
    rx.dsa(dsa if dsa is not None else link.info.get("dsa", rx._dsa_db))
    st = link.ensure()
    out["look"] = st
    if not st["locked"]:
        out["error"] = "no lock"
        return out
    leg = link.leg()
    out["leg"] = leg
    if s.pilot is not None:                          # B1, B2, A4: the idle is a weak pilot, made with VR (pilot_cal)
        pc = pilot_cal(link, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            link.tx.cl.dac(VR_I=link.tx.vr(link.mhz)[0][0], VR_Q=link.tx.vr(link.mhz)[0][1])
            return out
    out["thresholds"], out["levels"], out["gaps_mv"] = scheme_windows(link, s, frac)    # from the received constellation
    idle = link.pt(*s.idle)
    link.hold(s.idle)                                # the scheme's own idle for the false-event count
    time.sleep(0.05)
    n_samp = period * link.rx.ser
    shift = max(0, int(math.ceil(math.log2(2.6 * n_samp / 1024.0))))
    rows = {}
    try:
        # the idle alone: false events a second
        rx.rx_config(s.idle_vector(), s.mask, s.lut(first_edge), s.slow_exp(), delay=delay, quiet=quiet, confirm=confirm,
                     window=window, first_edge=first_edge, settle=settle)
        rx.rx_clear()
        time.sleep(idle_s)
        rx.rx_enable(False)
        q = rx.rx_stats()
        out["idle_false_per_s"] = q["events"] / idle_s
        for m in ([msg] if msg is not None else range(s.n)):
            rx.rx_config(s.idle_vector(), s.mask, _lut_only(s, m, first_edge), s.slow_exp(), delay=delay, quiet=quiet,
                         confirm=confirm, window=window, first_edge=first_edge, settle=settle)
            rx.hist_config("event_to_event", shift)
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
            b0 = int(round(n_samp / 2 ** shift))
            near = lambda c, w=3: sum(h[max(0, c - w):c + w + 1])    # noqa: E731
            r = {"events": q["events"], "decided": q["decided"], "confirm": q["confirm"], "veto": q["veto"],
                 "right_frac": q["decided"] / count, "extra": q["events"] - count,
                 "intervals_1N": near(b0), "intervals_2N": near(2 * b0), "intervals_short": sum(h[:max(0, b0 - 4)]),
                 "intervals_other": sum(h) - near(b0) - near(2 * b0) - sum(h[:max(0, b0 - 4)]), "hist_shift": shift}
            rows[str(m)] = r
    finally:
        tx.tx_stop()
        if s.pilot is not None:
            (vi0, vq0), _ = link.tx.vr(link.mhz)
            tx.dac(VR_I=vi0, VR_Q=vq0)
        link.tx.idle((link.s, 0))
        rx.rx_enable(True)
    out["per_msg"] = rows
    out["right_frac_min"] = min(r["right_frac"] for r in rows.values())
    out["right_frac_mean"] = sum(r["right_frac"] for r in rows.values()) / len(rows)
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
        if o["locked"] and o["di"] > 0.01:
            return True
        ok, _ = self.ld.recover()
        if ok:
            self.node.cl.hold_point(1, 0)
            time.sleep(0.05)
            self.s = 1 if self.ld.observe()["di"] > 0 else -1
            self.wcal = None
            return True
        return self.up()

    def state(self):
        return {"link": self.name, "mhz": self.mhz, "dsa": self.node.cl._dsa_db, "tr_a": self.tr_a, "wifi": wifi_tag(self.mhz)}


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
    cl.rx_config(s.idle_vector(), s.mask, s.lut(first_edge), s.slow_exp(), delay=delay, quiet=quiet, confirm=confirm,
                 window=window, first_edge=first_edge, settle=settle)
    if path == "sync":
        cl.fast_off()
        cl.reply_config(list(rmap), width=reply_width, once=True, rearm="tx")
    elif path == "fast":
        cl.reply_off()
        cm = _code_map(loop)
        ent = {v: cm[code] for v, code in C.CostasLink.fast_reply_entries(s, rmap, first_edge).items()}
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
    cl.dsa(dsa if dsa is not None else loop.info.get("dsa", cl._dsa_db))
    if not loop.ensure():
        out["error"] = "no lock"
        return out
    leg = loop.leg()
    out["leg"] = leg
    if s.pilot is not None:
        pc = pilot_cal(loop, angle=0 if abs(s.pilot[1]) < 1e-9 else 45)
        out["pilot"] = pc
        if pc["vr"] is None:
            out["error"] = "no pilot"
            cl.dac(VR_I=loop.cfg["vr"]["VR_I"], VR_Q=loop.cfg["vr"]["VR_Q"])
            return out
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
        except Exception as e:                                  # noqa: BLE001  (one bad point must not end the night)
            r = {"error": repr(e)[:300], "tb": traceback.format_exc()[-800:]}
            say("%s %d/%d %s: %r" % (label, k + 1, n, p, e))
            try:
                ctx.ensure()
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
            run_points(log, L, events_point, events_plan(a.scheme, a.quick), "events %s %g" % (L.name, mhz))
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
    ap.add_argument("cmd", choices=["check", "prbs", "events", "prover", "band", "night"])
    ap.add_argument("--band", type=float, nargs="+", default=[float(f) for f in BAND], help="night: the band's frequencies")
    ap.add_argument("--steps", nargs="+", default=None, help="night: proverB proverA pilotB events prbs band events5400 "
                    "prbs5400 pilots_events (default proverB proverA events prbs band events5400 prbs5400)")
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
         "night": cmd_night}[a.cmd](a, log)
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
