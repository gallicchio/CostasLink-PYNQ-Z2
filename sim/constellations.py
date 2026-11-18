#!/usr/bin/env python3
"""Idle plus N messages, decided by comparators within the first symbol: which constellation,
which comparators, how much SNR, and when the bits are known (Jason, Prompt 10 and his two notes
after it: "a wonderful, perhaps even optimal, solution that was arrived at through first-principles
thinking").

    python3 sim/constellations.py              the tables
    python3 sim/constellations.py --json F     also the numbers, and docs/images/constellations.png

The argument, in five steps (PLAN.md section 18 says it in words):

1. The two error rates are not alike.  The link idles nearly all the time, so noise that carries
   the idle point over a threshold is a false event, and it happens at Rice's rate
   nu(u) = nu0 exp(-u^2 / 2) for a threshold u sigma from the idle point, nu0 = the arm filter's
   rms frequency (= fc for two Butterworth poles).  One false event an hour at 94 MHz needs
   u = 7.3 sigma.  A wrong message can only happen when a message is sent: 1e-4 of them needs
   3.7 sigma.  So the idle should sit about 1.5 times farther from every message than the messages
   sit from each other, and a threshold between idle and a message belongs 7.3 sigma from the idle,
   not halfway.  Where the noise is unknown, the FPGA finds that place by counting: a comparator
   and a counter measure their own false-event rate (CFAR, as radar sets its thresholds).
2. The arm filter carries the signal from the idle point to the message in a straight line,
   r(t) = s0 + g(t) (s_k - s0), g the filter's step response, so every margin grows linearly in g.
   A bit is known when its last margin reaches its z.  For a threshold placed from the idle point
   (CFAR) or a line THROUGH the idle point, that happens at g* proportional to 1/SNR: early in the
   rise when the signal is strong.  A line through the ORIGIN (sign(I), a phase comparator) is
   crossed at a fixed fraction of the way whatever the SNR (a half for a 180 degree flip): that
   bit comes half a rise late even in the lab.
3. What limits the transmitter decides the shape.  The departures from the idle point are what
   count, and how long they can be depends on the limit.  Under an ENVELOPE limit (an amplifier at
   its P1dB) the best layouts for N <= 5 keep the idle on the rim at full amplitude and send the
   messages across the circle (N = 4: messages near +-90 degrees and at 180 +- 27: Jason's "+"
   with its centre point, the one nearest the idle, split into two on the far side); for N >= 6 a
   weak pilot at the centre with N-PSK round it is best, and the cost stays flat to N = 8 because the
   false-alarm margin, not the spacing, sets it.  Under a PER-AXIS limit (this board alone: the
   ladders and the ADL5375's input range bound I and Q separately) the corners are 3 dB stronger
   than the axis points, and a search of every subset of the ladders' 3 x 3 grid finds:
4. A weak pilot sent at 45 degrees with the four corners as the messages.  The receiver's loop
   locks the pilot onto +I, which turns the corners onto +I, -I, +Q and -Q at the corners' full
   amplitude: one CFAR window comparator per message and nothing else, the event and both bits on
   the same edge, 18.2 dB of SNR (the axis point's, in 100 MHz) against 20.9 dB for the plan's
   corners-around-a-full-idle, whose I bit comes half a rise late.  The best any comparator layout
   does on that grid is 17.7 dB (the idle on a corner, lines through it, an event comparator per
   message; 18.2 dB with one): 0.1 to 0.5 dB for weighted, AC-coupled comparators is not worth having.  Rev A's transmitter makes this already (the pilot
   from the VR_I / VR_Q trims); rev A's receiver has the Q window but only sign(I), so rev A gets
   the 1-bit half of it (pilot at 45 degrees, messages at TX (-1, 1) and (1, -1), QP / QN) at
   17.7 dB, and rev B adds an I window pair.
5. The detection bandwidth should follow the SNR (a sequential test, CUSUM, is the optimum and a
   matched low-pass is close to it): in the lab the 94 MHz arm wastes bandwidth; at the range limit
   it is right.  The board's fast and slow paths are two points on that curve.

Everything is in units of sigma, the noise per quadrature behind the arm filter.  The decision
amplitude-to-sigma ratio of a point is a = sqrt(snr), snr = P / (kTF B) in the arm's 100 MHz
(Response 10 measured this with an RF-level simulation; sim/link_rates.py had sqrt(2 snr)).
"""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUD = json.load(open(os.path.join(ROOT, "build", "budget.json")))

FC = BUD["fda_bw_MHz"] * 1e6          # the fast arm: the THS4541 at gain 4, two poles
NU0 = FC                              # Rice: two Butterworth poles have rms frequency fc
FA_RATE = 1.0 / 3600.0                # false events a second: one an hour
PMSG = 1e-4                           # wrong messages per message sent
RHO_PILOT = 0.05                      # the weak pilot, -26 dBc of the axis amplitude
VPK_CMP = BUD["vcmp_rms"] * math.sqrt(2)   # the axis point's peak at a comparator at the DSA's regulated level
GB_P1DB = 12.8                        # ADL5611 output P1dB at 5800 MHz (build/txt/ADL5611.txt): the corners' level when the
CORNER_COMP_dB = 1.0                  # axis point is +9.8 dBm, so a scheme with corners loses about 1 dB there


def Q(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def Qinv(p):
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        lo, hi = (mid, hi) if Q(mid) > p else (lo, mid)
    return (lo + hi) / 2.0


def z_fa(k=1, rate=FA_RATE, nu0=NU0):
    """sigma from the idle point for k comparators to give `rate` false events a second in all"""
    return math.sqrt(2.0 * math.log(k * nu0 / rate))


ZM = Qinv(PMSG)


def db(x):
    return 10.0 * math.log10(x)


# ---- the arm's step response: two Butterworth poles at FC ---------------------------------------
def g_of_t(t, fc=FC):
    w = 2 * math.pi * fc
    z = 1 / math.sqrt(2)
    wd = w * math.sqrt(1 - z * z)
    return 1 - math.exp(-z * w * t) * (math.cos(wd * t) + z / math.sqrt(1 - z * z) * math.sin(wd * t))


def t_of_g(g, fc=FC):
    """time (s) for the step response to reach g (before its 4 % overshoot)"""
    if g <= 0:
        return 0.0
    w = 2 * math.pi * fc
    lo, hi = 0.0, math.pi / (w * math.sqrt(0.5))
    if g >= 1:
        return hi
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if g_of_t(mid, fc) < g else (lo, mid)
    return (lo + hi) / 2


# ---- a scheme: an idle point, messages, comparators ------------------------------------------
# A comparator is a line with a normal n: it "fires" when <n, r> > threshold.  Its threshold is
#   cfar   z_FA from the idle point along n (an event detector; a DAC sets it, the FPGA servoes it)
#   origin through the origin (0): sign(I), sign(Q), a phase comparator (a resistor pair)
#   idle   through the idle point (a phase comparator on the arms after the idle is subtracted)
#   level  through a fixed fraction of the amplitude (a DAC that must follow the received level)
class Scheme:
    def __init__(self, key, name, idle, msgs, comps, board, note=""):
        self.key, self.name, self.note, self.board = key, name, note, board
        self.s0 = np.array(idle, float)
        self.msgs = {k: np.array(v, float) for k, v in msgs.items()}
        self.comps = comps

    def points(self):
        return [self.s0] + list(self.msgs.values())

    def scale(self, norm):
        """the factor that puts the scheme's largest point at 1: 'axis' = per-axis (the board's
        ladders and the ADL5375's input range), 'peak' = the envelope (an amplifier near P1dB)"""
        if norm == "axis":
            return 1.0 / max(max(abs(p[0]), abs(p[1])) for p in self.points())
        return 1.0 / max(np.hypot(*p) for p in self.points())

    def thr(self, c, a, zfa):
        n = np.array(c["n"], float) / np.hypot(*c["n"])
        if c["kind"] == "cfar":
            return n, a * n.dot(self.s0) + zfa
        if c["kind"] == "origin":
            return n, 0.0
        if c["kind"] == "idle":
            return n, a * n.dot(self.s0)
        return n, a * n.dot(np.array(c["p"], float))            # level

    def evaluate(self, a, norm="axis"):
        """a = the largest point's amplitude / sigma (in the chosen norm).  Returns per message the
        rise fractions at which the event and all its bits are reliable, or None if a is too low."""
        sc = self.scale(norm)
        s0 = self.s0 * sc
        pts = {k: v * sc for k, v in self.msgs.items()}
        ncfar = sum(1 for c in self.comps if c["kind"] == "cfar")
        zfa = z_fa(max(ncfar, 1))
        vals = {}
        for c in self.comps:
            n, th = self.thr(c, a, zfa)
            th = th if c["kind"] != "cfar" else a * n.dot(s0) + zfa
            if c["kind"] == "idle":
                th = a * n.dot(s0)
            vals[c["name"]] = (n, th)

        def v(name, p):
            n, th = vals[name]
            return a * n.dot(p) - th

        # each hypothesis's state per comparator: True/False, or None when it sits within z of the line
        state = {}
        for h, p in [("idle", s0)] + list(pts.items()):
            for c in self.comps:
                x = v(c["name"], p)
                need = zfa if h == "idle" else ZM
                state[(h, c["name"])] = None if abs(x) < need - 1e-9 else bool(x > 0)
        hyps = ["idle"] + list(pts)
        for i, h1 in enumerate(hyps):              # every pair must differ on some comparator
            for h2 in hyps[i + 1:]:
                if not any(state[(h1, c["name"])] is not None and state[(h2, c["name"])] is not None
                           and state[(h1, c["name"])] != state[(h2, c["name"])] for c in self.comps):
                    return None
        out = {}
        for k, p in pts.items():
            ge, gall = [], 0.0
            for c in self.comps:
                sk = state[(k, c["name"])]
                if sk is None:
                    continue
                if not any(state[(h, c["name"])] is not None and state[(h, c["name"])] != sk for h in hyps if h != k):
                    continue                                       # this comparator tells k from nothing
                sgn = 1 if sk else -1
                m0, m1 = sgn * v(c["name"], s0), sgn * v(c["name"], p)
                if m1 < ZM - 1e-9:
                    return None
                g = 0.0 if m0 >= ZM else (ZM - m0) / (m1 - m0)
                gall = max(gall, g)
                if sk and state[("idle", c["name"])] is False:
                    ge.append(g)                                  # an event comparator for k
            if not ge:
                return None
            out[k] = (min(ge), gall)
        return out

    def required(self, norm="axis"):
        lo, hi = 0.5, 400.0
        if self.evaluate(hi, norm) is None:
            return float("inf")
        for _ in range(80):
            mid = math.sqrt(lo * hi)
            r = self.evaluate(mid, norm)
            ok = r is not None and max(g for _, g in r.values()) <= 1.0 + 1e-9
            lo, hi = (lo, mid) if ok else (mid, hi)
        return hi


def C(name, n, kind, role="", p=None):
    return dict(name=name, n=n, kind=kind, role=role, p=p)


def ang(d):
    r = math.radians(d)
    return (math.cos(r), math.sin(r))


def line_normal(phi):
    """the normal of the line through the origin at angle phi (degrees), pointing counter-clockwise"""
    r = math.radians(phi)
    return (-math.sin(r), math.cos(r))


rho = RHO_PILOT
SCHEMES = [
    Scheme("A1", "BPSK flip, sign(I)", (1, 0), {"flip": (-1, 0)},
           [C("sign(I)", (-1, 0), "origin")], "rev A as built",
           "an event and no bit: the plan's BPSK row"),
    Scheme("A2", "1 bit: Q step, QP / QN at +-V_T", (1, 0), {"+Q": (1, 1), "-Q": (1, -1)},
           [C("QP", (0, 1), "cfar"), C("QN", (0, -1), "cfar")], "rev A as built",
           "the event and the bit from the same edge; V_T by the FPGA's false-event count"),
    Scheme("A3", "2 bits: corners (the plan's QPSK)", (1, 0), {"++": (1, 1), "+-": (1, -1), "-+": (-1, 1), "--": (-1, -1)},
           [C("QP", (0, 1), "cfar"), C("QN", (0, -1), "cfar"), C("sign(I)", (-1, 0), "origin")], "rev A as built",
           "QP / QN give the event and the Q bit; sign(I) gives the I bit at mid-rise"),
    Scheme("J1", "Jason's +, idle the right arm", (1, 0), {"0": (0, 0), "+Q": (0, 1), "-Q": (0, -1), "-I": (-1, 0)},
           [C("E", (-1, 0), "cfar"), C("L", (-1, 0), "level", p=(-0.5, 0)), C("QP", (0, 1), "level", p=(0, 0.5)),
            C("QN", (0, -1), "level", p=(0, -0.5))], "needs a second I threshold",
           "the centre point is the nearest to idle; the far arm is known at 3/4 of the rise"),
    Scheme("J2", "Jason's even circle: 5-PSK", (1, 0), {"%d" % d: ang(d) for d in (72, 144, 216, 288)},
           [C("E+", line_normal(36), "cfar"), C("E-", tuple(-x for x in line_normal(-36)), "cfar"),
            C("L108", line_normal(108), "origin"), C("L180", line_normal(180), "origin"), C("L252", line_normal(252), "origin")],
           "needs 5-level TX and phase comparators", "phase lines through the origin: the far messages are known late"),
    Scheme("B1", "weak pilot + 4 orthogonal", (rho, 0), {"+I": (1 + rho, 0), "-I": (-1 + rho, 0), "+Q": (rho, 1), "-Q": (rho, -1)},
           [C("IP", (1, 0), "cfar"), C("IN", (-1, 0), "cfar"), C("QP", (0, 1), "cfar"), C("QN", (0, -1), "cfar")],
           "rev A TX (the pilot by VR_I); rev B RX (+1 window comparator pair)",
           "each message moves only its own comparator: the event and both bits on one edge"),
    # in the TRANSMITTER's frame: the pilot along the diagonal; the receiver's loop turns it onto +I,
    # so its I and Q windows are these diagonal comparators
    Scheme("B2", "weak pilot at 45 deg + the 4 corners", (rho / math.sqrt(2), rho / math.sqrt(2)),
           {"++": (1, 1), "-+": (-1, 1), "--": (-1, -1), "+-": (1, -1)},
           [C("IP", (1, 1), "cfar"), C("QP", (-1, 1), "cfar"), C("IN", (-1, -1), "cfar"), C("QN", (1, -1), "cfar")],
           "rev A TX (the pilot by VR_I and VR_Q); rev B RX (+1 window pair); rev A RX does the +-Q half",
           "the loop turns the corners onto the receiver's axes: one window per message, all bits on one edge"),
    Scheme("A4", "1 bit: pilot at 45 deg, TX (-1,1) / (1,-1)", (rho / math.sqrt(2), rho / math.sqrt(2)),
           {"+Q": (-1, 1), "-Q": (1, -1)},
           [C("QP", (-1, 1), "cfar"), C("QN", (1, -1), "cfar")], "rev A as built",
           "the 1-bit half of B2: QP / QN with V_T by the false-event count"),
    Scheme("R4", "idle on a corner, lines through it", (1, 1), {"a": (-1, 0), "b": (-1, 1), "c": (0, -1), "d": (1, -1)},
           [C("E", (-1, -1), "cfar")]
           + [C("L%d" % i, (-math.sin(math.radians(b)), math.cos(math.radians(b))), "idle") for i, b in enumerate((193.3, 225.0, 256.7))],
           "rev A TX; rev B RX with AC-coupled, resistor-weighted comparators",
           "the best layout on the 3 x 3 grid (17.7 dB with an event comparator per message): no better than B2 in practice"),
]


# ---- the general optimum by search -----------------------------------------------------------
def ray_sep(u, v):
    """the best margin a line through the idle point can keep between departures u and v"""
    lu, lv = np.hypot(*u), np.hypot(*v)
    if lu < 1e-9 or lv < 1e-9:
        return 0.0
    c = np.clip(u.dot(v) / (lu * lv), -1, 1)
    th = math.acos(c)
    cr = abs(u[0] * v[1] - u[1] * v[0])
    s = np.hypot(*(u + v))
    best = cr / s if s > 1e-12 else min(lu, lv)
    if th > math.pi / 2:
        best = max(best, min(lu, -lv * math.cos(th)), min(lv, -lu * math.cos(th)))
    return best


def r_max(rho_, phi):
    """the longest departure from (rho_, 0) in direction phi inside the unit circle"""
    c = math.cos(phi)
    return -rho_ * c + math.sqrt(max(rho_ * rho_ * c * c - rho_ * rho_ + 1.0, 0.0))


def _unpack(x, N, rho_fixed):
    r0 = rho_fixed if rho_fixed is not None else x[0]
    k = 0 if rho_fixed is not None else 1
    deps = []
    for i in range(N):
        phi, f = x[k + 2 * i], x[k + 2 * i + 1]
        L = f * r_max(r0, phi)
        deps.append(np.array([L * math.cos(phi), L * math.sin(phi)]))
    return r0, deps


def _score(x, N, latency_aware, rho_fixed, zfa):
    r0, deps = _unpack(x, N, rho_fixed)
    t = min(np.hypot(*d) / (zfa + ZM) for d in deps)
    for i in range(N):
        for j in range(i + 1, N):
            sep = ray_sep(deps[i], deps[j]) if latency_aware else np.hypot(*(deps[i] - deps[j])) / 2
            t = min(t, sep / ZM)
    return -t


def optimum(N, latency_aware=True, rho_min=RHO_PILOT, rho_fixed=None, seed=0):
    """maximise the scale t such that every departure is >= t (zFA + zM) long and every pair is
    separated by >= t zM (a line through the idle point if latency_aware, else half the chord);
    returns the required peak amplitude / sigma, the idle's radius and the departures"""
    from scipy.optimize import differential_evolution
    zfa = z_fa(N)
    bounds = ([] if rho_fixed is not None else [(rho_min, 1.0)]) + [(0, 2 * math.pi), (0.3, 1.0)] * N
    res = differential_evolution(_score, bounds, args=(N, latency_aware, rho_fixed, zfa), seed=seed, maxiter=800,
                                 popsize=20, tol=1e-9, polish=True, workers=-1, updating="deferred")
    r0, deps = _unpack(res.x, N, rho_fixed)
    return 1.0 / -res.fun, r0, deps


def npsk_round_pilot(N, rho_=RHO_PILOT):
    """N departures from the pilot at equal angles, as long as the circle allows (the first one at 0)"""
    best = None
    for off in np.linspace(0, 2 * math.pi / N, 61):
        deps = [r_max(rho_, off + 2 * math.pi * k / N) * np.array([math.cos(off + 2 * math.pi * k / N), math.sin(off + 2 * math.pi * k / N)]) for k in range(N)]
        t = min(np.hypot(*d) / (z_fa(N) + ZM) for d in deps)
        for i in range(N):
            for j in range(i + 1, N):
                t = min(t, ray_sep(deps[i], deps[j]) / ZM)
        best = t if best is None or t > best else best
    return 1.0 / best


def comparators_round_pilot(N):
    """window comparators for N <= 4 (each message alone on its own); beyond, N event comparators
    and N lines through the pilot (a phase quantizer) to say which"""
    return N if N <= 4 else 2 * N


# ---- the range, from the budget's link equation ----------------------------------------------
def range_m(req_snr_dB, scenario):
    lam = 299792458.0 / BUD["f_Hz"]
    ant, cab = BUD["antennas"], BUD["cable_dB_per_m"]
    name, a, cable_m, margin, pa = scenario
    nf = BUD["nf_chain_dB"] + cable_m * cab
    noise = -174.0 + db(BUD["B_MHz"] * 1e6) + nf
    budget = BUD["tx_out_dBm"] + pa + 2 * ant[a] - 2 * cable_m * cab - margin - noise - req_snr_dB
    return lam / (4 * math.pi) * 10 ** (budget / 20.0)


def fmt_m(d):
    return "%.0f m" % d if d < 1000 else "%.1f km" % (d / 1e3)


def main(argv):
    out = {"zm": ZM, "fa_rate": FA_RATE, "pmsg": PMSG, "nu0_Hz": NU0, "fc_Hz": FC}
    print("== 1. The two error rates (arm filter %.0f MHz, two poles: Rice's nu0 = %.0f MHz)" % (FC / 1e6, NU0 / 1e6))
    print("   false events from an idle that crosses a threshold u sigma away, one comparator:")
    for lab, r in (("one a second", 1.0), ("one an hour", 1 / 3600.0), ("one a day", 1 / 86400.0)):
        print("     %-14s u = %.2f sigma" % (lab, z_fa(1, r)))
    for p in (1e-3, 1e-4, 1e-6):
        print("   a wrong message once in %-9s z = %.2f sigma" % ("%.0e" % (1 / p), Qinv(p)))
    print("   design point: %s false event a second (one an hour) and %.0e wrong messages: idle side %.2f sigma, message side %.2f"
          % ("%.1e" % FA_RATE, PMSG, z_fa(1), ZM))
    print("   so the idle wants %.2f sigma to every message and the messages %.2f to each other: a ratio of %.2f, not 1"
          % (z_fa(1) + ZM, 2 * ZM, (z_fa(1) + ZM) / (2 * ZM)))
    print("   (sim/link_rates.py's 'quiet' is 1e-4 per decision: at %.0e decisions a second that is %.0e false events a second)" % (NU0, NU0 * 1e-4))

    print("\n== 2. When the arm's output has risen to a fraction g of the way (two poles, %.0f MHz)" % (FC / 1e6))
    print("   " + "  ".join("g %.2f: %.2f ns" % (g, t_of_g(g) * 1e9) for g in (0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)))

    snr_lab = BUD["link_rows"][1][4]                 # 10 m, whips
    a_lab = 10 ** (snr_lab / 20.0)
    rows = [r for r in BUD["link_rows"] if abs(r[0] - 3000) < 1 and r[1] == 24.0]
    snr_far = min(r[4] for r in rows) if rows else 23.1
    a_far = 10 ** (snr_far / 20.0)
    print("\n== 3. The schemes (a = the largest point's amplitude / sigma; SNR = a^2 in the arm's 100 MHz)")
    print("   lab: 10 m, whips, SNR %.1f dB (a = %.0f); far: 3 km, panels, 10 m cables, SNR %.1f dB (a = %.1f)" % (snr_lab, a_lab, snr_far, a_far))
    print("   %-4s %-38s %-8s %-8s %-6s %-26s %-26s" % ("", "scheme", "SNR axis", "SNR peak", "comps", "lab: event / all bits, ns", "far: event / all bits, ns"))
    res = {}
    for s in SCHEMES:
        ra, rp = s.required("axis"), s.required("peak")
        lat = {}
        for tag, aa in (("lab", a_lab), ("far", a_far)):
            r = s.evaluate(aa * 1.0, "axis")
            if r is None or max(g for _, g in r.values()) > 1:
                lat[tag] = None
                continue
            ge = max(e for e, _ in r.values())
            gall = max(g for _, g in r.values())
            lat[tag] = (t_of_g(ge) * 1e9, t_of_g(gall) * 1e9)
        res[s.key] = dict(name=s.name, a_axis=ra, a_peak=rp, snr_axis_dB=20 * math.log10(ra), snr_peak_dB=20 * math.log10(rp),
                          comps=len(s.comps), lat=lat, board=s.board, note=s.note, N=len(s.msgs))
        f = lambda x: "-" if x is None else "%.2f / %.2f" % x
        print("   %-4s %-38s %5.1f dB %5.1f dB %4d   %-26s %-26s" % (s.key, s.name, 20 * math.log10(ra), 20 * math.log10(rp), len(s.comps), f(lat["lab"]), f(lat["far"])))
        print("        %s; %s" % (s.board, s.note))
    out["schemes"] = res

    print("\n== 4. The best any comparator layout can do, by search (peak-limited; SNR of the largest point)")
    print("   %-3s %-28s %-34s %-30s" % ("N", "static (late bits allowed)", "latency-aware (lines through idle)", "N-PSK round a -26 dBc pilot"))
    opt = {}
    for N in range(1, 9):
        a_s, r_s, _ = optimum(N, latency_aware=False, rho_min=0.0)
        a_l, r_l, deps = optimum(N, latency_aware=True, rho_min=RHO_PILOT)
        if a_l < a_s:                                  # a line through the idle is one choice of line: the search stalled
            a_s, r_s = a_l, r_l
        a_p = npsk_round_pilot(N)
        opt[N] = dict(static=a_s, static_idle=r_s, latency=a_l, latency_idle=r_l, pilot=a_p, pilot_comps=comparators_round_pilot(N),
                      deps=[list(map(float, d)) for d in deps])
        print("   %-3d %5.1f dB (idle at %.2f)       %5.1f dB (idle at %.2f)              %5.1f dB, %d comparators"
              % (N, 20 * math.log10(a_s), r_s, 20 * math.log10(a_l), r_l, 20 * math.log10(a_p), comparators_round_pilot(N)))
    out["optimum"] = opt

    print("\n== 5. Matching the arm's bandwidth to the SNR (B2: the event and both bits at g* = (zFA + zM) / (a L), L = sqrt 2 - rho)")
    mb = {}
    for tag, snr in (("lab", snr_lab), ("far", snr_far), ("limit", res["B2"]["snr_axis_dB"] + 1.0)):
        best = None
        for W in np.geomspace(5e6, 400e6, 200):
            aW = 10 ** (snr / 20.0) * math.sqrt(FC / W) * (math.sqrt(2) - RHO_PILOT)
            g = (z_fa(4, nu0=W) + ZM) / aW
            if g > 1:
                continue
            t = t_of_g(g, W)
            if best is None or t < best[1]:
                best = (W, t)
        a94 = 10 ** (snr / 20.0) * (math.sqrt(2) - RHO_PILOT)
        g94 = (z_fa(4) + ZM) / a94
        t94 = t_of_g(g94) if g94 <= 1 else float("nan")
        mb[tag] = dict(snr_dB=snr, W_best_MHz=best[0] / 1e6, t_best_ns=best[1] * 1e9, t94_ns=t94 * 1e9)
        print("   %-5s SNR %5.1f dB: the %.0f MHz arm decides %.2f ns into the rise; the best bandwidth, %.0f MHz, decides at %.2f ns"
              % (tag, snr, FC / 1e6, t94 * 1e9, best[0] / 1e6, best[1] * 1e9))
    out["matched_bandwidth"] = mb

    print("\n== 6. Range at the design point (free space; the budget's antennas, cables and margins)")
    print("   board alone: the axis point is +%.1f dBm; corners sit at the ADL5611's %.1f dBm P1dB (5.8 GHz), so a scheme with corners"
          % (BUD["tx_out_dBm"], GB_P1DB))
    print("   needs %.0f dB more; with the 2 W module its +%.0f dBm is the PEAK (3 dB under its P1dB) and the peak SNR counts"
          % (CORNER_COMP_dB, BUD["pa_module"]["out_dBm"]))
    scen = [("lab, whips, no cables, 10 dB indoor margin", "whip", 0.0, 10.0, 0.0),
            ("campus, 24 dBi panels, 10 m cables, 6 dB", "panel", 10.0, 6.0, 0.0),
            ("campus, panels, the 2 W module at +30 dBm", "panel", 10.0, 6.0, BUD["pa_module"]["out_dBm"] - BUD["tx_out_dBm"])]
    rng = {}
    for key in ("A1", "A2", "A3", "A4", "B1", "B2"):
        sch = [x for x in SCHEMES if x.key == key][0]
        corners = max(np.hypot(*q) for q in sch.points()) * sch.scale("axis") > 1.01
        req = res[key]["snr_axis_dB"] + (CORNER_COMP_dB if corners else 0.0)
        res[key]["snr_board_dB"] = req
        rng[key] = [range_m(req, sc) for sc in scen[:2]] + [range_m(res[key]["snr_peak_dB"], scen[2])]
        print("   %-4s %-34s needs %4.1f dB: %s" % (key, res[key]["name"], req, "; ".join("%s %s" % (sc[0].split(",")[0] + ("" if i == 0 else " " + ["", "", "+PA"][i]), fmt_m(d)) for i, (sc, d) in enumerate(zip(scen, rng[key])))))
    out["range_m"] = rng

    print("\n== 7. The comparators' own offset and hysteresis against the noise (TLV3601: offset 0.5 typ / 5 max mV, hysteresis 3 mV)")
    sig = {}
    for tag, aa in (("lab", a_lab), ("far", a_far)):
        s_mV = VPK_CMP * 1e3 / aa
        sig[tag] = s_mV
        print("   %-4s sigma at the comparator %.1f mV (the axis point %.0f mV at the DSA's regulated level): 5 mV offset = %.1f sigma, the CFAR threshold %.0f mV from idle"
              % (tag, s_mV, VPK_CMP * 1e3, 5.0 / s_mV, z_fa(4) * s_mV))
    out["sigma_mV"] = sig

    print("\n== 8. Holding the RX loop while this station transmits (TS5A3159 open: the 100 nF integrator holds VC)")
    Ko_Hz = BUD["loop_Ko"] / (2 * math.pi)
    hold = {}
    for lab, I in (("typical, 25 C (0.2 nA)", 0.2e-9), ("max, 25 C (2 nA)", 2e-9), ("max, -40..85 C (20 nA)", 20e-9)):
        dvdt = I / BUD["loop_C"]
        dfdt = dvdt * Ko_Hz
        T = math.sqrt(0.1 / (math.pi * dfdt))
        hold[lab] = dict(dVdt_mV_s=dvdt * 1e3, dfdt_Hz_s=dfdt, T_0p1rad_ms=T * 1e3)
        print("   leakage %-24s VC drifts %6.2f mV/s = %7.0f Hz/s at 5.8 GHz: the carrier phase is off by 0.1 rad after %.1f ms"
              % (lab, dvdt * 1e3, dfdt, T * 1e3))
    out["hold"] = hold

    print("\n== 9. What the scores leave out: the angle between the pilot and the messages (B2)")
    out["tolerances"] = tolerances(snr_lab, res["B2"]["snr_axis_dB"])

    if "--json" in argv:
        path = argv[argv.index("--json") + 1]
        json.dump(out, open(path, "w"), indent=1)
        figure(res, opt, a_lab)
    return 0



def tolerances(snr_lab, snr_need_b2):
    """What the scores above leave out: the angle between the pilot and the messages.  For B2 every
    message must move its own window only.  An angle error e projects a sin(e) of a message onto the
    neighbouring window.  Decoding the SETTLED comparator states needs that below z_FA - z_M; decoding
    the FIRST edge (the gateware time-stamps every edge) needs only that the neighbour stays under its
    threshold until the own comparator is reliable: tan(e) <= (z_FA - z_M) / (z_FA + z_M), whatever the
    SNR.  The angle error has three sources: the modulator's quadrature error (0.2 deg at 2.1 GHz in its
    datasheet), its carrier feedthrough (-15 dBc at 5.8 GHz before nulling: a vector added to the pilot
    turns it), and the loop's static phase error (a DC offset in the Q arm over the pilot's slope)."""
    out = {}
    zfa = z_fa(4)
    e_fe = math.degrees(math.atan((zfa - ZM) / (zfa + ZM)))
    print("   first-edge decoding tolerates %.0f deg of angle error at any SNR" % e_fe)
    for tag, snr in (("lab", snr_lab), ("at the limit", snr_need_b2)):
        a_dep = 10 ** (snr / 20.0) * math.sqrt(2)
        e_set = math.degrees(math.asin(min(1.0, (zfa - ZM) / a_dep)))
        print("   settled-state decoding, %-12s (a corner %.0f sigma from the pilot): %.1f deg" % (tag, a_dep, e_set))
        out["settled_" + tag] = e_set
    out["first_edge_deg"] = e_fe
    off_mV = 20.0                         # ADL5380 +-10 mV differential output offset x 4 = +-20 mV on one arm output
    # The loop holds ONE leg of Q against V_MID, so the slope the offset works against is half the differential
    # amplitude (the budget's Kd = a/2 per leg); review C of Prompt 31 caught the differential slope used here before,
    # which halved every static error (A3: 4.6 deg where it is 9.2).
    print("   the pilot's size against the loop's static phase error (a %.0f mV Q-arm offset: the ADL5380's +-10 mV x 4, one side, "
          "against half the pilot's amplitude: one leg)" % off_mV)
    print("   and against the modulator's feedthrough (the residual that turns the pilot by 5 deg):")
    rows = []
    for rho in (0.05, 0.1, 0.2, 0.3):
        pilot_mV = rho * VPK_CMP * 1e3
        e_loop = math.degrees(math.atan(off_mV / (pilot_mV / 2)))
        ft_dBc = 20 * math.log10(rho * math.sin(math.radians(5.0)))
        cost = 20 * math.log10(math.sqrt(2) / (math.sqrt(2) - rho))
        rows.append(dict(rho=rho, pilot_dBc=20 * math.log10(rho), e_loop=e_loop, ft_dBc=ft_dBc, cost_dB=cost))
        print("     pilot %5.1f dBc: slope %3.0f mV/rad on one leg, static error %4.1f deg; feedthrough nulled below %5.1f dBc; costs %.1f dB on the corner it points at"
              % (20 * math.log10(rho), pilot_mV / 2, e_loop, ft_dBc, cost))
    a3 = math.degrees(math.atan(off_mV / (VPK_CMP * 1e3 / 2)))
    print("   (the plan's full idle, A3: static error %.1f deg; sign(I) tolerates 45, and the false-event count absorbs the Q offset)" % a3)
    out["pilot_rows"] = rows
    out["a3_static_deg"] = a3
    return out

def figure(res, opt, a_lab):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 3, figsize=(15, 10))
    show = ["A3", "J1", "J2", "B2", "R4"]
    for ax, key in zip(axs.flat, show):
        s = [x for x in SCHEMES if x.key == key][0]
        sc = s.scale("axis")
        s0 = s.s0 * sc
        th = np.linspace(0, 2 * math.pi, 200)
        ax.plot(np.cos(th), np.sin(th), color="0.85", lw=0.8)
        ax.add_patch(plt.Rectangle((-1, -1), 2, 2, fill=False, ec="0.85", lw=0.8, ls="--"))
        a = res[key]["a_axis"]
        zfa = z_fa(max(1, sum(1 for c in s.comps if c["kind"] == "cfar")))
        for c in s.comps:
            n, thr = s.thr(c, a, zfa)
            if c["kind"] == "cfar":
                thr = a * n.dot(s0) + zfa
            elif c["kind"] == "idle":
                thr = a * n.dot(s0)
            d = np.array([-n[1], n[0]])
            p = n * thr / a
            seg = np.array([p - 3 * d, p + 3 * d])
            ax.plot(seg[:, 0], seg[:, 1], color="tab:red" if c["kind"] == "cfar" else "tab:blue", lw=1.0)
        for k, p in s.msgs.items():
            p = p * sc
            ax.annotate("", xy=p, xytext=s0, arrowprops=dict(arrowstyle="->", color="0.5", lw=0.8))
            ax.plot(*p, "o", color="black")
            ax.text(p[0] + 0.05, p[1] + 0.07, k, fontsize=9)
        ax.plot(*s0, "s", color="tab:green", ms=9)
        ax.text(s0[0] + 0.05, s0[1] - 0.15, "idle", color="tab:green", fontsize=9)
        lat = res[key]["lat"]["lab"]
        ax.set_title("%s: %s\nneeds %.1f dB (axis), %d comparators; lab: all bits at %s ns" % (key, s.name, res[key]["snr_axis_dB"], res[key]["comps"],
                     "-" if lat is None else "%.2f" % lat[1]), fontsize=10)
        ax.set_xlim(-1.4, 1.4); ax.set_ylim(-1.4, 1.4); ax.set_aspect("equal"); ax.axhline(0, color="0.9", lw=0.5); ax.axvline(0, color="0.9", lw=0.5)
        ax.set_xticks([]); ax.set_yticks([])
    # the curve panel, with the envelope-limited optimum for N = 4 drawn as an inset
    ax = axs.flat[5]
    Ns = sorted(opt)
    ax.plot(Ns, [20 * math.log10(opt[n]["static"]) for n in Ns], "o-", label="static optimum (bits may come late)")
    ax.plot(Ns, [20 * math.log10(opt[n]["latency"]) for n in Ns], "s-", label="latency-aware optimum")
    ax.plot(Ns, [20 * math.log10(opt[n]["pilot"]) for n in Ns], "^-", label="N-PSK round a -26 dBc pilot")
    ax.set_xlabel("messages N (plus idle)"); ax.set_ylabel("peak SNR needed in 100 MHz, dB")
    ax.set_title("one false event an hour, 1e-4 wrong messages", fontsize=10)
    ax.grid(alpha=0.3); ax.legend(fontsize=8, loc="center left")
    o = opt[4]
    r0 = o["latency_idle"]
    ins = ax.inset_axes([0.56, 0.04, 0.42, 0.45])
    th = np.linspace(0, 2 * math.pi, 200)
    ins.plot(np.cos(th), np.sin(th), color="0.8", lw=0.8)
    for d in o["deps"]:
        q = np.array([r0, 0]) + np.array(d)
        ins.annotate("", xy=q, xytext=(r0, 0), arrowprops=dict(arrowstyle="->", color="0.5", lw=0.7))
        ins.plot(*q, "o", color="black", ms=4)
    ins.plot(r0, 0, "s", color="tab:green", ms=6)
    ins.set_xlim(-1.2, 1.2); ins.set_ylim(-1.2, 1.2); ins.set_aspect("equal"); ins.set_xticks([]); ins.set_yticks([])
    ins.set_title("N = 4, envelope limit: %.1f dB" % (20 * math.log10(o["latency"])), fontsize=8)
    fig.suptitle("Idle + N messages decided by comparators: red = CFAR thresholds (set from the idle by the false-event count), blue = fixed lines", fontsize=11)
    fig.tight_layout()
    path = os.path.join(ROOT, "docs", "images", "constellations.png")
    fig.savefig(path, dpi=110)
    print("figure: docs/images/constellations.png")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
