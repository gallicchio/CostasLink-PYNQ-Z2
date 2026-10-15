"""The copper laid by plan before the router, and what the router is told.  Called by gen/board.py.

In the order CLAUDE_PCB.md section 5 gives (ground and power planes, the critical lines, the
fan-outs, each block's own routing, then the rest):

  1. the supply pours on In2 and the ground fills (supply_pours, ground_fills);
  2. the two RF chains and the switch's three lines as straight grounded-coplanar tracks
     (sim/rf_lines.py) with a fence of ground vias either side (rf_lines_by_plan, fence);
  3. the LO pairs, the demodulator's I/Q pairs into their amplifiers, the slow pairs and the
     couplers' monitor ports as straight 0.2 mm lines on the top layer, pad to pad through the
     series parts the placement put on the line, each segment checked with exact geometry and
     left to the router where it is not clear (pair_lines_by_plan);
  4. a grid of ground vias in every exposed pad and a short tie from each ground pin into it
     (ep_vias, ep_ties);
  5. for every fine-pitch chip: its short local nets first, then a planned fan-out, each
     signal and supply pin a stub, a straight line and a via of its own, the vias of a side
     evenly spaced so the lines spread like a fan (fan, after OWLternating Current); the
     chip's area is then a keep-out for everything else on the top layer;
  6. a via beside every remaining ground pad and every decoupling capacitor's rail pad;
  7. the router: the RF leftovers and baseband on top, the rails on any layer, the slow
     signals underneath, ground last; then rip-up and reroute of what was walled in (repair),
     the unused fan-out vias taken out (prune), and the rails widened where there is room.

Everything is computed from the pads' positions on the board, so it follows gen/placement.py.
"""
import math, os, time
import pcbnew
import board_info as BI
import placement as PL
import routing as RT
import router as RR
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sim"))
import rf_lines

# the signal nets' order (see autoroute): 0 is shortest first; the seed the board was last finished with is
# kept here so the build reproduces it; COSTASLINK_ROUTE_SEED overrides it for trials (Response 15)
ROUTE_SEED = int(os.environ.get("COSTASLINK_ROUTE_SEED", "0"))
# Response 15's two fixes for nets walled in near their own pads (CLAUDE_PCB.md section 5): join every short
# connection of a signal net first (NEAR_REACH mm, pad to pad; 0: off), and keep In2 for the signals where
# no supply needs a pour (DIG_POUR_SHRINK) at IN2_SIG_COST a millimetre.  The environment overrides them for trials.
# Trials of the four combinations (Response 15, with the GND fix): nets in pieces after the repair 2 (near
# only), 3 (near + In2 at 3), 1 (all three: only GND, which the fills join), 3 (neither).
NEAR_REACH = float(os.environ.get("COSTASLINK_NEAR", "5"))
DIG_POUR_SHRINK = int(os.environ.get("COSTASLINK_DIG_SHRINK", "1"))
IN2_SIG_COST = float(os.environ.get("COSTASLINK_IN2_COST", "3.0"))

RF_W, RF_GAP = rf_lines.RF_W, rf_lines.RF_GAP
FENCE_PITCH = 1.2                      # ground vias along an RF line, both sides (lambda/10 in the dielectric at 5.8 GHz is 2.5 mm)
FENCE_OFF = RF_W / 2 + RF_GAP + 0.45   # the fence's centre line from the track's: the via's pad clears the coplanar gap
BB_W = 0.2                             # baseband pairs
# the PAIR_PATHS that carry 5.8 GHz: the LO pairs and the couplers' ports, 50 ohm lines like the RF chains
# (they were BB_W, 57-60 ohm: the design review)
RF_PAIRS = ("RX LO +", "RX LO -", "TX LO +", "TX LO -", "RF +", "RF -", "RX MON", "TX MON", "RX ISO", "TX ISO")
LO_PAIRS = ("RX LO +", "RX LO -", "TX LO +", "TX LO -")
SIG_W = 0.15
FAN_W = 0.15                           # a fan-out line
PWR_W = 0.2                            # the rails' links to their pours (the pours carry the current; a wider
PWR5_W = 0.3                           # track cannot leave a 0.5 mm pad: route at the pad's width, CLAUDE_PCB.md section 5)
RAILS_3V3 = (0.4, 0.3)                 # what the rails are widened to afterwards, where there is room
RAILS_5V = (0.8, 0.4, 0.3)


class Pads:
    """(ref, pad number) -> (x, y, net, size), net -> [(ref, num)], each part's centre and DNP flag,
    from the board."""

    def __init__(self, board, B):
        self.xy, self.net, self.of, self.size, self.centre, self.dnp, self.layer, self.fp = {}, {}, {}, {}, {}, {}, {}, {}
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            self.fp[ref] = str(fp.GetFPID().GetLibItemName())
            self.centre[ref] = B(fp.GetPosition())
            self.dnp[ref] = bool(fp.IsDNP())
            self.layer[ref] = 2 if fp.GetLayer() == pcbnew.B_Cu else 0
            for p in fp.Pads():
                key = (ref, p.GetNumber())
                if key in self.xy:
                    continue
                self.xy[key] = B(p.GetPosition())
                self.net[key] = p.GetNetname()
                bb = p.GetBoundingBox()
                self.size[key] = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))
                self.of.setdefault(p.GetNetname(), []).append(key)


# ---------------------------------------------------------------------------------------------
# the RF paths: each a list of (ref, pad) in order; the parts between are found by walking the
# nets through the two-terminal parts that lie on the line
RF_PATHS = [
    ("RX chain", ("J101", "1"), ("T101", "1")),          # SMA -> LNA -> DSA -> GB1 -> GB2 -> coupler -> balun
    ("TX chain", ("U201", "16"), ("J202", "1")),         # modulator -> GB -> pad -> coupler -> SMA
    ("ANT", ("J401", "1"), ("U401", "3")),
    ("SW TX", ("U401", "5"), ("J402", "1")),
    ("SW RX", ("U401", "8"), ("J403", "1")),
]
# the pairs and monitor lines laid straight at BB_W on the top layer, pad to pad through the
# series parts on the line (an L where a straight segment is not clear; the router where neither is)
PAIR_PATHS = [
    # P to LOIN and N to LOIP: the pins face each other (sheets 1 and 2, gen/placement.LO_LINKS)
    ("RX LO +", ("U115", "12"), ("U104", "10")), ("RX LO -", ("U115", "13"), ("U104", "9")),
    ("TX LO +", ("U203", "12"), ("U201", "4")), ("TX LO -", ("U203", "13"), ("U201", "3")),
    ("I hi", ("U104", "3"), ("U105", "2")), ("I lo", ("U104", "4"), ("U105", "3")),
    ("Q hi", ("U104", "16"), ("U106", "2")), ("Q lo", ("U104", "15"), ("U106", "3")),
    ("I slow +", ("U105", "10"), ("U501", "2")), ("I slow -", ("U105", "11"), ("U501", "3")),
    ("Q slow +", ("U106", "10"), ("U502", "2")), ("Q slow -", ("U106", "11"), ("U502", "3")),
    ("RF +", ("T101", "2"), ("U104", "22")), ("RF -", ("T101", "3"), ("U104", "21")),      # the balun's pair, through a DC block each (Prompt 31)
    ("RX MON", ("CP101", "3"), ("J102", "1")), ("TX MON", ("CP201", "3"), ("J201", "1")),
    ("RX ISO", ("CP101", "4"), ("R103", "1")), ("TX ISO", ("CP201", "4"), ("R213", "1")),
]
# (the LO monitor pins, RFOUTB, are fanned out like any signal: a via on a monitor line is fine,
# and their blocks cannot stand beside the LO pair's at 0.5 mm pitch)


def tap_paths(pads):
    """A planned line from every U.FL or MMCX tap's centre pad to the series part on it (a U.FL's
    centre pad has one way out, between its two ground pads; an MMCX's centre pin leaves along an
    axis between two legs, 0.9 mm apart; the router was walled off both)."""
    out = []
    for (ref, num), net in pads.net.items():
        if not (ref.startswith("J") and num == "1" and net and not net.startswith("unconnected")):
            continue
        if not ("U.FL" in pads.fp.get(ref, "") or "MMCX" in pads.fp.get(ref, "")):
            continue                                      # an SMA's centre pin, a header
        others = [k for k in pads.of[net] if k != (ref, num)]
        if len(others) == 1 and others[0][0][0] in "RC":
            out.append((ref + " tap", (ref, num), others[0]))
    return out
# three-pin parts the walk passes straight through: (ref prefix or exact) -> {in pad: out pad}
THROUGH = {"U101": {"3": "4", "4": "3"}, "U102": {"5": "14", "14": "5"}, "U103": {"1": "3", "3": "1"},
           "U117": {"1": "3", "3": "1"}, "U202": {"1": "3", "3": "1"}, "CP101": {"1": "2", "2": "1"}, "CP201": {"1": "2", "2": "1"}}


def walk(pads, start, stop):
    """The pads along an RF path from `start` to `stop`: at each net take the two-terminal part
    (or the chip in THROUGH) whose far end gets nearer the stop."""
    out = [start]
    seen = {start}
    cur = start
    sx, sy = pads.xy[stop]
    for _ in range(40):
        net = pads.net[cur]
        best = None
        for ref, num in pads.of[net]:
            if (ref, num) == cur or (ref, num) in seen:
                continue
            if (ref, num) == stop:
                best = [(ref, num)]
                break
            if ref in THROUGH and num in THROUGH[ref]:
                far = (ref, THROUGH[ref][num])
            else:
                nums = [n for (r, n) in pads.xy if r == ref]
                if len(nums) != 2 or ref[0] not in "CR" or pads.dnp.get(ref):
                    continue
                far = (ref, [n for n in nums if n != num][0])
                fnet = pads.net[far]
                if fnet == "GND" or fnet.startswith("+"):
                    continue                       # a shunt off the line, not the line
            d = math.hypot(pads.xy[far][0] - sx, pads.xy[far][1] - sy)
            if best is None or d < best[0]:
                best = (d, (ref, num), far)
        if best is None:
            raise SystemExit("routes: RF walk from %s stuck at %s" % (start, cur))
        # a part whose far end is on the stop's own net beats the nearest (a monitor's series
        # resistor sat nearer the slow stage than the slow stage's own resistor: Response 9)
        for ref, num in pads.of[net]:
            if (ref, num) == cur or (ref, num) in seen or len(best) == 1:
                continue
            nums = [n for (r, n) in pads.xy if r == ref]
            if len(nums) == 2 and ref[0] in "CR" and not pads.dnp.get(ref):
                far = (ref, [n for n in nums if n != num][0])
                if stop in pads.of.get(pads.net[far], []):
                    best = (0.0, (ref, num), far)
                    break
        if len(best) == 1:
            out.append(best[0])
            return out
        _, near, far = best
        out += [near, far]
        seen.update([near, far])
        cur = far
    raise SystemExit("routes: RF walk from %s did not reach %s" % (start, stop))


NECK_W, NECK_L = 0.25, 0.6             # into a pad narrower than NARROW: the pad's own width for NECK_L along its axis
NARROW = 0.45


PIN_RUN = 1.4                          # a planned line's straight run out of a fine-pitch chip's pin before it may
                                       # turn: a diagonal from the pad's tip seals the pins beside it (Response 9)


def neck(pads, key, run=None):
    """For a narrow pad (a QFN or MSOP pin, the LNA's), the point NECK_L (or `run`) outside it along
    its axis, away from its part's centre; None for a pad wide enough to take the RF track."""
    w, h = pads.size[key]
    if min(w, h) >= NARROW:
        return None
    x, y = pads.xy[key]
    cx, cy = pads.centre[key[0]]
    dx, dy = x - cx, y - cy
    if abs(dx) >= abs(dy):
        d = (1.0 if dx >= 0 else -1.0, 0.0)
    else:
        d = (0.0, 1.0 if dy >= 0 else -1.0)
    L = run if run is not None else NECK_L
    return (x + d[0] * L, y + d[1] * L), min(NECK_W, min(w, h))


def fine_pin(pads, key):
    return key[0].startswith("U") and sum(1 for k in pads.xy if k[0] == key[0]) >= 16


def rf_lines_by_plan(R, pads):
    """Each RF path: straight tracks between consecutive pads of one net (pad to pad), with a neck
    into every fine-pitch pin (a 0.29 mm track beside 0.25 mm pads at 0.5 mm pitch touches their neighbours), and
    the via fence along every segment longer than a pitch.  Returns the nets laid."""
    laid = set()
    fences = []
    for name, start, stop in RF_PATHS:
        chain = walk(pads, start, stop)
        for a, b in zip(chain[0::2], chain[1::2]):
            net = pads.net[a]
            pa, pb = pads.xy[a], pads.xy[b]
            na, nb = neck(pads, a), neck(pads, b)
            if na:
                R.track(net, 0, pa, na[0], na[1]); pa = na[0]
            if nb:
                R.track(net, 0, pb, nb[0], nb[1]); pb = nb[0]
            if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 1e-6:
                continue
            R.track(net, 0, pa, pb, RF_W)
            laid.add(net)
            # no fence via within 1.5 mm of a coupler's end: its coupled-port pad and the stub out
            # of it live there
            keep = [pads.xy[k] for k in (a, b) if k[0].startswith("CP")]
            fences.append((pa, pb, keep))
    return laid, fences


def fence(R, segs, avoid):
    """Ground vias either side of each segment at FENCE_PITCH, skipping spots the grid says are
    taken (pads, other vias)."""
    n = 0
    for (x0, y0), (x1, y1), keep in segs:
        L = math.hypot(x1 - x0, y1 - y0)
        if L < FENCE_PITCH:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        k = int(L / FENCE_PITCH)
        for i in range(k + 1):
            t = (L - k * FENCE_PITCH) / 2 + i * FENCE_PITCH
            for s in (1, -1):
                x, y = x0 + ux * t + s * nx * FENCE_OFF, y0 + uy * t + s * ny * FENCE_OFF
                if avoid(x, y) or any(math.hypot(x - kx, y - ky) < 1.5 for kx, ky in keep):
                    continue
                R.via("GND", x, y)
                n += 1
    return n


def via_free(R):
    """A test the fence uses: may a via go at (x, y)?"""
    vg = [R.g.g[(L, "via")] for L in range(3)]

    def ok(x, y):
        if not (1.2 < x < PL.BOARD["w"] - 1.2 and 1.2 < y < PL.BOARD["h"] - 1.2):
            return True
        # the via's centre and the cells round it (a position between grid nodes rounds by 0.05 mm)
        return any(R.g.novia[k] or any(v[k] for v in vg) for k in R.g._disc(x, y, 0.11))
    return ok


def rf_stubs(R, pads):
    """A stub straight out of every narrow RF pin of a chip (the LO pins, the synthesizers' four
    outputs) before anything else is laid, so that each keeps its own lane and no line of a
    neighbour can cut in front of it.  Returns the pads stubbed."""
    done = set()
    for key in sorted(RF_PINS):
        if key not in pads.xy or not key[0].startswith("U"):
            continue
        n = neck(pads, key, PIN_RUN if fine_pin(pads, key) else None)
        if n is None:
            continue
        net = pads.net[key]
        if not net or net.startswith("unconnected"):
            continue
        pa = pads.xy[key]
        copper = local_copper(R, 0, (pa[0] - 3, pa[1] - 3, pa[0] + 3, pa[1] + 3))
        if _clear_of(copper, net, pa, n[0], BB_W / 2 + RR.CLEAR):
            R.track(net, 0, pa, n[0], BB_W)
            done.add(key)
    R.stubbed = done
    return len(done)


def _corners(qa, qb, ua, ub, prefer_b):
    """The two L corners between the stub ends, the one that extends the finer pin's own axis
    first (an L whose first leg runs along a chip's pin row cuts in front of the pins beside it)."""
    c1, c2 = (qa[0], qb[1]), (qb[0], qa[1])
    along_a = c1 if ua and ua[1] else c2                              # extends a's axis
    along_b = c2 if ub and ub[1] else c1                              # extends b's axis
    first = along_b if (prefer_b and ub) or not ua else along_a
    return [first, c2 if first == c1 else c1]                         # both, always


def pair_lines_by_plan(R, pads):
    """PAIR_PATHS as straight BB_W tracks on the top layer: out of each fine-pitch pad along its
    axis first (a line that leaves a 0.25 mm pad at an angle grazes the pin beside it), then
    straight to the far end, or an L through either corner when the straight line is not clear;
    each segment checked exactly against the copper already there.  A line that fits no way is
    left to the router and named with what was in its way.  Returns (segments laid, left)."""
    laid, left = 0, []
    for name, start, stop in PAIR_PATHS + tap_paths(pads):
        if start not in pads.xy or stop not in pads.xy:
            left.append("%s: no such pad" % name)
            continue
        try:
            chain = walk(pads, start, stop)
        except SystemExit as e:
            left.append("%s: %s" % (name, e))
            continue
        for a, b in zip(chain[0::2], chain[1::2]):
            net = pads.net[a]
            pa, pb = pads.xy[a], pads.xy[b]
            if math.hypot(pb[0] - pa[0], pb[1] - pa[1]) < 1e-6:
                continue
            box = (min(pa[0], pb[0]) - 3, min(pa[1], pb[1]) - 3, max(pa[0], pb[0]) + 3, max(pa[1], pb[1]) + 3)
            copper = local_copper(R, 0, box)
            # a 50 ohm line where 0.29 mm fits, else 0.2 mm (the RX coupler's isolated port had no room: build 18)
            for width in ((RF_W, BB_W) if name in RF_PAIRS else (BB_W,)):
                need = width / 2 + RR.CLEAR
                why = []
                ok = lambda p, q: _clear_of(copper, net, p, q, need, why) and _keep_free(R, 0, p, q)
                # the stubs: NECK_L straight out of a narrow pad, along its axis (a coupler's own copper
                # ends inside its pads and is not in the way of a stub out of one)
                stubbed = getattr(R, "stubbed", set())
                own = [c for c in copper if not (c[4].startswith("copper ") and c[4].split()[1] in (a[0], b[0]))]

                def stub_of(key, pk):
                    """The run out of the pad: the fan band's depth at a fine pin if that is clear, else
                    the short neck; None for a wide pad."""
                    for run in ((PIN_RUN, 0.9, NECK_L) if fine_pin(pads, key) else (None,)):
                        n = neck(pads, key, run)
                        if n is None:
                            return None, pk
                        if key in stubbed or (_clear_of(own, net, pk, n[0], need, why) and _keep_free(R, 0, pk, n[0])):
                            return n, n[0]
                    return False, pk
                na, qa = stub_of(a, pa)
                nb, qb = stub_of(b, pb)
                stubs = [(pa, qa, a[0])] if na and a not in stubbed else []
                stubs += [(pb, qb, b[0])] if nb and b not in stubbed else []
                if na is False or nb is False:
                    pts = None
                    continue
                pts = None
                if ok(qa, qb):
                    pts = [qa, qb]
                else:
                    ua = (qa[0] - pa[0], qa[1] - pa[1]) if na else None
                    ub = (qb[0] - pb[0], qb[1] - pb[1]) if nb else None
                    nb_pins = sum(1 for k in pads.xy if k[0] == b[0])
                    na_pins = sum(1 for k in pads.xy if k[0] == a[0])
                    for c in _corners(qa, qb, ua, ub, nb_pins >= na_pins):
                        why = []
                        if ok(qa, c) and ok(c, qb):
                            pts = [qa, c, qb]
                            break
                if pts is not None:
                    break
            if pts is None:
                left.append("%s: %s.%s -> %s.%s (%s)" % (name, a[0], a[1], b[0], b[1], ", ".join(sorted(set(why))[:6])))
                continue
            for p, q, _ in stubs:
                R.track(net, 0, p, q, min(width, NECK_W) if name in RF_PAIRS else BB_W)   # a pin's own width out of it
            R.polyline(net, 0, pts, width)
            laid += 1
        if name in LO_PAIRS:
            laid += choke_stubs(R, pads, chain, left, name)
    return laid, left


def choke_stubs(R, pads, chain, left, name):
    """Each LO leg's pull-up choke (gen/placement.lo_blocks stands it beside its leg's
    synthesizer-side block, outboard): a straight stub from its pad to that block's pad, laid
    with the leg so both legs carry the same stub."""
    n = 0
    for key in chain:
        net = pads.net[key]
        for other in pads.of[net]:
            if other[0][0] != "L" or other in chain:
                continue
            near = min((k for k in chain if pads.net[k] == net), key=lambda k: math.hypot(pads.xy[k][0] - pads.xy[other][0],
                                                                                       pads.xy[k][1] - pads.xy[other][1]))
            if near != key:
                continue
            a, b = pads.xy[other], pads.xy[key]
            box = (min(a[0], b[0]) - 3, min(a[1], b[1]) - 3, max(a[0], b[0]) + 3, max(a[1], b[1]) + 3)
            why = []
            if _clear_of(local_copper(R, 0, box), net, a, b, CHOKE_W / 2 + RR.CLEAR, why) and _keep_free(R, 0, a, b):
                R.track(net, 0, a, b, CHOKE_W)
                n += 1
            else:
                left.append("%s: the choke %s.%s -> %s.%s (%s)" % (name, other[0], other[1], key[0], key[1], ", ".join(sorted(set(why)))))
    return n


CHOKE_W = 0.25                         # an LO pull-up choke's stub to its line


# ---------------------------------------------------------------------------------------------
# the supply pours on In2 (board mm), each a polygon; a via of the net inside it joins it
IN2_POURS = {
    "+5V_RF": [(2.0, 10.0), (88.0, 10.0), (88.0, 54.0), (66.5, 54.0), (66.5, 43.5), (45.5, 43.5), (45.5, 54.0), (2.0, 54.0)],
    "+3V3_PLL_TX": [(46.0, 44.0), (66.0, 44.0), (66.0, 61.0), (46.0, 61.0)],          # under the TX synthesizer
    "+3V3_ANA": [(2.0, 54.5), (45.5, 54.5), (45.5, 90.0), (34.5, 90.0), (34.5, 63.5), (15.5, 63.5), (15.5, 90.0), (2.0, 90.0)],
    "+3V3_PLL_RX": [(16.0, 64.0), (34.0, 64.0), (34.0, 90.0), (16.0, 90.0)],          # under the RX synthesizer
    "+3V3_DIG": ([(46.0, 76.0), (88.0, 76.0), (88.0, 90.0), (46.0, 90.0)] if DIG_POUR_SHRINK else
                 [(66.5, 54.5), (88.0, 54.5), (88.0, 90.0), (46.0, 90.0), (46.0, 61.5), (66.5, 61.5)]),
    "+5V_IN": [(89.0, 22.0), (118.0, 22.0), (118.0, 92.0), (89.0, 92.0)],              # the power corner
}


def supply_pours(R):
    for net, poly in IN2_POURS.items():
        R.zone(net, pcbnew.In2_Cu, poly, priority=2 if "PLL" in net else 1, clearance=0.2, min_width=0.25, item=True,
               name=net + " In2", block_vias=False)
        RT.PLANES[net] = list(poly)                 # the real outline: routing.inside_margin keeps off its edges


# The RF launches' voids (Prompt 32: "make sure that all 5-6 GHz connectors have proper capacitance and
# inductance in the gerbers").  Measured in build 36's gerbers: the SMA centre pins' rings were gone from the
# inner layers (Prompt 31) but the planes came to 0.90 mm of the pin, a 1.8 mm antipad, because the DRC rule
# meant to hold them off never matched; and the 2.0 mm top pad sat over In1 at 0.21 mm (about 0.4 pF).  A
# rule area that forbids copper fill is explicit and lands in the gerbers whatever the DRC engine thinks:
#   - each 5.8 GHz SMA: a circle of LAUNCH_R round the centre pin on In1, In2 and B.Cu.  The coax through
#     the board is then 60/sqrt(4.4) ln(4.4/1.3) = 35 ohm over 1.6 mm (0.065 lambda): |Gamma| about 0.15,
#     14-16 dB return loss, 0.1 dB; the ground legs' pads (inner edge 2.5 mm from the centre) cap the radius;
#   - the 5.8 GHz U.FL taps' centre pads and the ADL5611s' 1.3 x 0.9 mm RF pads: In1 relieved under the pad
#     with VOID_MARGIN round it, so the pad sees In2 at 1.3 mm instead of In1 at 0.21 (0.04 pF for 0.2;
#     "ground relief", ADI's own evaluation boards).  Not the 0402 blocks (0.03 pF), the balun or the
#     couplers' 0.29 mm pads.
from rf_launch import LAUNCH_SMAS, LAUNCH_R, RELIEF_PADS, VOID_MARGIN      # shared with tools/launch_check.py


def rf_voids(R, pads):
    """Rule areas (no copper fill) round the SMA launches on the inner and back layers and under the RF pads
    on In1 (above).  Returns the count."""
    import math
    n = 0
    for ref in LAUNCH_SMAS:
        if (ref, "1") not in pads.xy:
            continue
        cx, cy = pads.xy[(ref, "1")]
        pts = [(cx + LAUNCH_R * math.cos(2 * math.pi * k / 48), cy + LAUNCH_R * math.sin(2 * math.pi * k / 48)) for k in range(48)]
        for layer in (pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            R.void(layer, pts, name="launch %s" % ref)
            n += 1
    for ref, num in RELIEF_PADS:
        if (ref, num) not in pads.xy:
            continue
        cx, cy = pads.xy[(ref, num)]
        w, h = pads.size[(ref, num)] if hasattr(pads, "size") and (ref, num) in pads.size else (1.3, 1.0)
        hw, hh = w / 2 + VOID_MARGIN, h / 2 + VOID_MARGIN
        R.void(pcbnew.In1_Cu, [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)], name="relief %s.%s" % (ref, num))
        n += 1
    print("copper: %d RF launch voids (rule areas without copper fill)" % n, flush=True)
    return n


def ground_fills(R):
    """GND on In1 (solid) and as fills on F.Cu, In2 and B.Cu, filled last by gen/board.py.

    The top, In1 and In2 ground joins every pad SOLIDLY (Prompt 32, from the SyzygyRadioBoard checklist): a
    thermal relief's four spokes are inductors at 5.8 GHz, and the balun's ground pad, the ESD shunts, the
    49.9 ohm loads, the LNA's ground pins and the SMAs' legs all return RF through them.  Reflow does not
    care; the one part soldered at home, the socket on the back, keeps thermal reliefs on every layer by its
    own pads' setting (gen/footprints.rpi_socket), and the back fill stays thermal."""
    W, H = PL.BOARD["w"], PL.BOARD["h"]
    whole = [(0, 0), (W, 0), (W, H), (0, H)]
    R.zone("GND", pcbnew.In1_Cu, whole, priority=0, clearance=0.2, min_width=0.2, item=False, name="GND plane", connect="solid")
    R.zone("GND", pcbnew.In2_Cu, whole, priority=0, clearance=0.2, min_width=0.25, item=False, name="GND In2", connect="solid")
    R.zone("GND", pcbnew.F_Cu, whole, priority=0, clearance=0.2, min_width=0.25, item=False, name="GND top", connect="solid")
    R.zone("GND", pcbnew.B_Cu, whole, priority=0, clearance=0.2, min_width=0.25, item=False, name="GND bottom")


# ---------------------------------------------------------------------------------------------
# exact geometry for the planned lines (a grid judges a line at any angle only to within its pitch)
def local_copper(R, L_, box):
    """The copper on grid layer L_ (pads as their bounding boxes, tracks, vias) inside `box`
    (board mm), for exact clearance checks of planned lines: [(net, kind, shape, bbox, what)].
    Zones are left out: a fill backs off round whatever is laid in it."""
    lid = RT.LAYERS[L_]
    bx0, by0, bx1, by1 = box
    out = []

    def bbox(x0, y0, x1, y1):
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def near(b):
        return b[0] <= bx1 and b[2] >= bx0 and b[1] <= by1 and b[3] >= by0

    for fp in R.board.GetFootprints():
        for p in fp.Pads():
            if not p.IsOnLayer(lid):
                continue
            bb = p.GetBoundingBox()
            x0, y0 = R.B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
            x1, y1 = R.B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
            b = bbox(x0, y0, x1, y1)
            if near(b):
                out.append((p.GetNetname(), "rect", b, b, "%s.%s" % (fp.GetReference(), p.GetNumber())))
        for it in fp.GraphicalItems():
            if it.GetClass() == "PCB_SHAPE" and it.GetLayer() == lid and it.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                a, c = R.B(it.GetStart()), R.B(it.GetEnd())
                hw = pcbnew.ToMM(it.GetWidth()) / 2
                b = (min(a[0], c[0]) - hw, min(a[1], c[1]) - hw, max(a[0], c[0]) + hw, max(a[1], c[1]) + hw)
                if near(b):
                    for net, p0, p1 in RT.copper_split(fp, a, c, R.B):
                        bb2 = (min(p0[0], p1[0]) - hw, min(p0[1], p1[1]) - hw, max(p0[0], p1[0]) + hw, max(p0[1], p1[1]) + hw)
                        out.append((net, "seg", (p0, p1, hw), bb2, "copper " + fp.GetReference()))
    for t in R.board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            x, y = R.B(t.GetPosition())
            r = pcbnew.ToMM(t.GetWidth(lid)) / 2
            b = (x - r, y - r, x + r, y + r)
            if near(b):
                out.append((t.GetNetname(), "disc", (x, y, r), b, "via"))
        elif t.GetLayer() == lid:
            a, c = R.B(t.GetStart()), R.B(t.GetEnd())
            hw = pcbnew.ToMM(t.GetWidth()) / 2
            b = (min(a[0], c[0]) - hw, min(a[1], c[1]) - hw, max(a[0], c[0]) + hw, max(a[1], c[1]) + hw)
            if near(b):
                out.append((t.GetNetname(), "seg", (a, c, hw), b, "track"))
    return out


def _clear_of(copper, net, a, b, need, why=None):
    """Is the segment a-b (its centre line) at least `need` from every copper of another
    net in `copper` (local_copper())?  `why`: a list to collect what is in the way."""
    sx0, sy0 = min(a[0], b[0]) - need, min(a[1], b[1]) - need
    sx1, sy1 = max(a[0], b[0]) + need, max(a[1], b[1]) + need
    for n, kind, sh, bb, what in copper:
        if n == net or bb[0] > sx1 or bb[2] < sx0 or bb[1] > sy1 or bb[3] < sy0:
            continue
        if kind == "disc":
            d = _pt_seg((sh[0], sh[1]), a, b) - sh[2]
        elif kind == "seg":
            d = _seg_seg(a, b, sh[0], sh[1]) - sh[2]
        else:
            pts = [(sh[0], sh[1]), (sh[2], sh[1]), (sh[2], sh[3]), (sh[0], sh[3])]
            if RT.point_in_poly(a[0], a[1], pts) or RT.point_in_poly(b[0], b[1], pts):
                d = 0.0
            else:
                d = min(_seg_seg(a, b, pts[i - 1], pts[i]) for i in range(len(pts)))
        if d < need:
            if why is None:
                return False
            why.append("%s %s" % (what, n.split("/")[-1]))
    return not why


def _keep_free(R, L, a, b):
    kl = R.g.keep[L]
    return not any(kl[k] for k in R.g.shape_cells(("seg", a[0], a[1], b[0], b[1], 0.0), RR.PITCH * 0.51))


def _via_free(R, copper, net, x, y):
    """A via of `net` at (x, y): clear of other nets' copper on every layer (exact), and
    where the grid allows a drill (not too near another) inside the board."""
    if not (1.0 <= x < R.g.w - 1.0 and 1.0 <= y < R.g.h - 1.0):
        return False
    k = R.g.k(x, y)
    if R.g.novia[k]:
        return False
    need = RT.VIA[0] / 2 + RR.CLEAR
    return all(_clear_of(copper[L], net, (x, y), (x, y), need) for L in range(RR.NL))


def _pt_seg(p, a, b):
    return RT.pt_seg(p, a, b)


def _seg_seg(p, q, a, b):
    def side(o, x, y):
        return (x[0] - o[0]) * (y[1] - o[1]) - (x[1] - o[1]) * (y[0] - o[0])
    if side(p, q, a) * side(p, q, b) < 0 and side(a, b, p) * side(a, b, q) < 0:
        return 0.0
    return min(_pt_seg(p, a, b), _pt_seg(q, a, b), _pt_seg(a, p, q), _pt_seg(b, p, q))


# ---------------------------------------------------------------------------------------------
# exposed pads: the ground pins tied into the paddle
def ep_ties(R, pads, width=0.2):
    """From every ground pin of a chip with an exposed pad, a short tie into the paddle: straight
    in past the pad's tip, then to the nearest point 0.3 mm inside the paddle (a corner pin is not
    opposite the paddle, and a straight diagonal from it would graze the pin beside it).  Each tie
    is checked exactly against the other nets' pads; one that does not fit is left to the router
    and named.  Returns (ties, left)."""
    n, left = 0, []
    for ref, shape in R.ep_shape.items():
        _, cx, cy, hw, hh, ang = shape
        copper = local_copper(R, 0, (cx - 5, cy - 5, cx + 5, cy + 5))
        need = width / 2 + RR.CLEAR
        for (r, num), xy in pads.xy.items():
            if r != ref or pads.net[(r, num)] != "GND":
                continue
            w, h = pads.size[(r, num)]
            if min(w, h) >= 1.5:
                continue                              # the paddle itself
            px, py = xy
            dx, dy = px - cx, py - cy
            if abs(dx) >= abs(dy):
                u = (-1.0 if dx > 0 else 1.0, 0.0)    # inward
                tip = w / 2
            else:
                u = (0.0, -1.0 if dy > 0 else 1.0)
                tip = h / 2
            a = (px + u[0] * (tip + 0.1), py + u[1] * (tip + 0.1))
            tx = min(max(px, cx - hw + 0.3), cx + hw - 0.3)      # a corner pin: clamped to the paddle
            ty = min(max(py, cy - hh + 0.3), cy + hh - 0.3)
            if u[0]:
                tx = cx - hw + 0.3 if u[0] > 0 else cx + hw - 0.3   # the paddle's near edge, 0.3 inside
            else:
                ty = cy - hh + 0.3 if u[1] > 0 else cy + hh - 0.3
            b = (tx, ty)
            if _clear_of(copper, "GND", (px, py), a, need) and _clear_of(copper, "GND", a, b, need):
                R.polyline("GND", 0, [(px, py), a, b], width)
                n += 1
            else:
                left.append("%s.%s" % (r, num))
    return n, left


# ---------------------------------------------------------------------------------------------
# the fan-outs (OWLternating Current's gen/routes.py, 2026-10-09)
def is_rail(net):
    return net == "GND" or net.startswith("+") or net.endswith("VBUS")


def span(R, net):
    pts = [R.pads.xy[k] for k in R.pads.of.get(net, [])]
    if len(pts) < 2:
        return 0.0
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (max(xs) - min(xs)) + (max(ys) - min(ys))


def route_power(R, net, widths, **kw):
    """Join a net's pieces at the first width that fits each, then narrower; the last
    try searches four times as far."""
    ok = False
    for k, w in enumerate(widths):
        if k == len(widths) - 1:
            kw = dict(kw, max_pop=min(1500000, 3 * kw.get("max_pop", 500000)))
            kw.pop("bbox_margin", None)
        n0 = len(R.failed)
        ok = R.route_net(net, w, **kw)
        if ok:
            R.failed = [f for f in R.failed if f[0] != net]
            break
        if k < len(widths) - 1:
            R.failed = R.failed[:n0]
    return ok


def local_first(R, ref, reach=8.0):
    """A chip's short local nets (a feedback resistor, a loop-filter capacitor), routed before
    its fan-out, on the top layer without a via when they can: the fan's vias would otherwise
    wall them in.  Returns how many it joined."""
    n = 0
    nets = {R.pads.net[k] for k in R.pads.xy if k[0] == ref}
    for net in sorted((m for m in nets if m), key=lambda m: span(R, m)):
        if is_rail(net) or net.startswith("unconnected") or not R.unrouted(net) or span(R, net) > reach:
            continue
        n0 = len(R.failed)
        ok = R.route_net(net, BB_W, layers=(0,), allow_via=False, max_pop=200000) or \
            R.route_net(net, SIG_W, layers=(0,), allow_via=False, max_pop=200000)
        if not ok:
            R.failed = R.failed[:n0]
            ok = route_power(R, net, (BB_W, SIG_W), layer_cost=TOP, bbox_margin=10.0)
        if ok:
            n += 1
        else:
            print("   %s: local net %s left in pieces before the fan-out" % (ref, net.split("/")[-1]))
    return n


# a fan's own clearances, exact: track to track, track to via, via to via (0.15 mm
# rule plus 0.02 mm), for a 0.15 mm track and a 0.45 mm via
FAN_TT, FAN_TV, FAN_VV = 0.32, 0.47, 0.62


def fan(R, ref, width=FAN_W, no_fan=()):
    """A planned fan-out for a fine-pitch chip: each signal and supply pin a short straight stub,
    then a straight line out to a via of its own, the vias of a side evenly spaced in one
    row or two staggered rows (_fan_pattern), so the lines spread like a fan and none
    crosses another.  The pattern's own clearances are exact; against everything else
    the copper already there decides (exact too: a planned line is at any angle, which a
    grid can only judge to within its pitch); the pattern that serves the most pins is
    drawn, then one for each run of pins it left out.  The router then starts each net
    from its via, with every layer to choose from.  Pins in `no_fan` (the RF ones, which
    must not see a via), ground pins of a chip with a paddle, no-connects and pins whose
    net is already whole are left out.  Returns how many pins it fanned out."""
    fp = next(f for f in R.board.GetFootprints() if f.GetReference() == ref)
    L_ = 2 if fp.GetLayer() == pcbnew.B_Cu else 0
    xs = [xy for (r, num), xy in R.pads.xy.items() if r == ref]
    cx, cy = sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs)
    has_ep = ref in R.ep_refs
    sides = {}
    for p in fp.Pads():
        net = p.GetNetname()
        num = p.GetNumber()
        if not net or net.startswith("unconnected") or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        if (ref, num) in no_fan or (net == "GND" and has_ep):
            continue
        if not R.unrouted(net):
            continue                                  # whole already (local_first, or laid by plan)
        bb = p.GetBoundingBox()
        x0, y0 = R.B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
        x1, y1 = R.B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
        if (x1 - x0) >= 1.5 and (y1 - y0) >= 1.5:
            continue                                  # the exposed pad
        px, py = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = px - cx, py - cy
        if abs(dx) > abs(dy):
            u, tip = ((1.0 if dx > 0 else -1.0), 0.0), (x1 - x0) / 2
        else:
            u, tip = (0.0, (1.0 if dy > 0 else -1.0)), (y1 - y0) / 2
        t = (-u[1], u[0])                             # along the side
        sides.setdefault(u, []).append(((px - cx) * t[0] + (py - cy) * t[1], (px, py), tip, net, num))
    allpads = sorted(pcbnew.ToMM(p.GetPosition().x) for p in fp.Pads())
    pitch = min((b - a for a, b in zip(allpads, allpads[1:]) if b - a > 0.2), default=0.5)
    copper = {}

    def legal(u, pin, vhs, memo):
        """Is this spot (place along the side, depth, straight run) one where the pin's
        stub, line and via are clear of everything already on the board?  Memoised per pin."""
        if vhs in memo:
            return memo[vhs]
        s0, (px, py), tip, net, num = pin
        t = (-u[1], u[0])
        at = lambda hh, s: (px + u[0] * hh + t[0] * (s - s0), py + u[1] * hh + t[1] * (s - s0))
        a = tip + 0.25
        need = width / 2 + RR.CLEAR
        if "stub" not in memo:
            memo["stub"] = _clear_of(copper[L_], net, at(tip, s0), at(a, s0), need)
        if not memo["stub"]:
            memo[vhs] = False
            return False
        v, h, st = vhs
        if ("st", st) not in memo:
            memo[("st", st)] = _clear_of(copper[L_], net, at(a, s0), at(a + st, s0), need) \
                and _keep_free(R, L_, at(a, s0), at(a + st, s0))
        ok = memo[("st", st)] and _via_free(R, copper, net, *at(h, v)) and _keep_free(R, L_, at(a + st, s0), at(h, v)) \
            and _clear_of(copper[L_], net, at(a + st, s0), at(h, v), need)
        memo[vhs] = ok
        return ok

    def choose(u, pins):
        """The cheapest pattern for these pins that the board allows for the most of
        them: (pins it cannot serve, pattern, which it serves), or None.  Patterns are
        tried cheapest first and a pattern is abandoned as soon as it fails more pins
        than the best so far, so a side that fits takes a few hundred checks, not a
        million."""
        nonlocal copper
        copper = {L: local_copper(R, L, (cx - 12, cy - 12, cx + 12, cy + 12)) for L in range(RR.NL)}
        memos = [{} for _ in pins]
        best = None
        for pat in _fan_patterns(pins):
            geo = _fan_pattern(pins, *pat[1:])
            if geo is None:
                continue
            fails, ok = 0, []
            for i, vhs in enumerate(geo):
                good = legal(u, pins[i], vhs, memos[i])
                ok.append(good)
                if not good:
                    fails += 1
                    if best is not None and fails >= best[0]:
                        break
            if len(ok) < len(geo):
                continue
            if best is None or fails < best[0]:
                best = (fails, geo, ok)
                if not fails:
                    break
        return best

    def group(u, pins):
        """The cheapest pattern for these pins that the board allows for the most of
        them, drawn; returns the pins it left out."""
        best = choose(u, pins)
        if best is None:
            return list(pins)
        _, geo, ok = best
        t = (-u[1], u[0])
        need = width / 2 + RR.CLEAR
        left = []
        for pin, (v, h, st), fine in zip(pins, geo, ok):
            s0, (px, py), tip, net, num = pin
            at = lambda hh, s: (px + u[0] * hh + t[0] * (s - s0), py + u[1] * hh + t[1] * (s - s0))
            a = tip + 0.25
            if fine:
                R.polyline(net, L_, [(px, py), at(a + st, s0), at(h, v)], width)
                R.via(net, *at(h, v))
                continue
            clear = lambda p, q: _clear_of(copper[L_], net, p, q, need) and _keep_free(R, L_, p, q)
            if not clear(at(tip, s0), at(a, s0)):
                left.append(pin)
                continue
            # no via where the pattern puts it: the empty slot between its neighbours'
            # vias is twice as wide as a via, room for the line to go on through it to
            # a via further out
            on = None
            if clear(at(a, s0), at(a + st, s0)) and clear(at(a + st, s0), at(h, v)):
                on = next(((d, dv) for d in (0.4, 0.8, 1.2, 1.6, 2.0, 2.5, 3.0, 3.5, 4.0) for dv in (0.0, 0.2, -0.2, 0.4, -0.4)
                           if _via_free(R, copper, net, *at(h + d, v + dv)) and clear(at(h, v), at(h + d, v + dv))), None)
            if on:
                d, dv = on
                R.polyline(net, L_, [(px, py), at(a + st, s0), at(h, v), at(h + d, v + dv)], width)
                R.via(net, *at(h + d, v + dv))
                continue
            if os.environ.get("FAN_WHY"):
                why = []
                for p_, q_ in ((at(a, s0), at(a + st, s0)), (at(a + st, s0), at(h, v)), (at(h, v), at(h, v))):
                    _clear_of(copper[L_], net, p_, q_, need, why)
                for L in range(RR.NL):
                    _clear_of(copper[L], net, at(h, v), at(h, v), RT.VIA[0] / 2 + RR.CLEAR, why)
                print("   why %s.%s (%s): %s" % (ref, num, net.split("/")[-1], ", ".join(sorted(set(why))) or "the grid (keep, edge or drill)"))
            # else the line still holds the pin's place in the fan as far as it is clear
            # (its neighbours lean over a gap), and the router takes the net on from its end
            pts = [(px, py), at(a, s0)]
            f = next((f for f in (1.0, 0.75, 0.5, 0.25) if clear(at(a, s0), at(a + st * f, s0))), 0.0) if st else 0.0
            if f:
                pts.append(at(a + st * f, s0))
            if f == 1.0:
                g = next((g for g in (1.0, 0.8, 0.6, 0.4, 0.2)
                          if clear(at(a + st, s0), at(a + st + (h - a - st) * g, s0 + (v - s0) * g))), 0.0)
                if g:
                    pts.append(at(a + st + (h - a - st) * g, s0 + (v - s0) * g))
            R.polyline(net, L_, pts, width)
            R.__dict__.setdefault("partial", []).append("%s.%s" % (ref, num))
        return left

    def runs(pins, gap):
        """The pins in runs of neighbours (no gap wider than `gap` along the side)."""
        out = [[pins[0]]]
        for p0, p1 in zip(pins, pins[1:]):
            if p1[0] - p0[0] > gap:
                out.append([])
            out[-1].append(p1)
        return out

    def fan_part(u, pins):
        """A pattern for these pins; those it leaves out, a pattern for each run of them
        between the pins it served, until a run gets nothing."""
        left = group(u, pins)
        if not left or len(left) == len(pins):
            return left
        return [p for run in runs(left, 1.5 * pitch) for p in fan_part(u, run)]

    done, missed = 0, []
    for u, pins in sorted(sides.items()):
        pins.sort()
        # a side's pins in groups wherever two or more pins between them take no part
        # (ground, no-connects): each group its own fan, the gap kept clear
        left = [p for run in runs(pins, 2.5 * pitch) for p in fan_part(u, run)]
        missed += left
        done += len(pins) - len(left)
    for s0, xy, tip, net, num in missed:
        R.__dict__.setdefault("unfanned", []).append(net)
    part = [w for w in R.__dict__.pop("partial", []) if w.startswith(ref + ".")]
    if part:
        print("   %s: fan-out lines without a via for %s" % (ref, " ".join(part)))
    if missed:
        print("   %s: no fan-out for %s" % (ref, " ".join("%s.%s" % (ref, p[4]) for p in missed)))
    return done - len(part)


def plane_copper_check(R, gnd_vias):
    """GND and the poured rails before the router: each pad its own stub and via, so on the signal
    layers only short stubs.  Prints each one's track length per layer and flags a long run (more
    than 3 mm) or no ground vias at all: Response 15 found 875 mm of top-layer GND, laid by a
    helper that routed GND whole before the vias existed (CLAUDE_PCB.md section 5)."""
    for net in ["GND"] + list(IN2_POURS):
        per, longest = {}, (0.0, None)
        for i in R.by_net.get(net, []):
            it = R.items[i]
            if it.what != "track" or not it.seg:
                continue
            L, a, b, w = it.seg
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            per[L] = per.get(L, 0.0) + d
            if d > longest[0]:
                longest = (d, (L, a, b))
        if not per:
            continue
        flag = "  LONG RUN %.1f mm on %s from (%.1f, %.1f)" % (longest[0], RR.LAYERS[longest[1][0]], *longest[1][1]) \
            if longest[0] > 3.0 else ""
        print("   plane copper %-12s %s%s" % (net.split("/")[-1], "  ".join("%s %.0f mm" % (RR.LAYERS[L], v)
                                                                       for L, v in sorted(per.items())), flag), flush=True)
    if not gnd_vias:
        print("   plane copper: NO ground vias beside the passives: something joined the ground pads first", flush=True)


def route_unfanned(R):
    """The few pins the fan-outs left out (a capacitor straight in front of them), routed
    whole at once while the board round them is still empty.  Not ground or a supply: their
    pads get a via of their own into the plane or the pour (Router.fanout, next), and routing
    GND "whole" here, before those vias existed, joined every bare ground pad on the board
    to every other by tracks on the top: 875 mm of them, which walled in the loop block
    (Response 15)."""
    for net in R.__dict__.pop("unfanned", []):
        if is_rail(net):
            continue
        if R.unrouted(net) and not route_power(R, net, (SIG_W,), layer_cost=TOP):
            print("   %s left in pieces (its pin has no fan-out)" % net.split("/")[-1])


def _fan_patterns(pins):
    """The fan patterns to try for one side, cheapest (most compact) first: (cost, rows,
    via spacing along the side, depth of the first row past the pads, sideways shift,
    straight run out of the pins before the lines lean).  Besides the shifts round the
    middle, a row with its first or last via straight out of its pin (something beside
    that end of the side)."""
    out = []
    n = len(pins)
    for rows, Ps in ((2, (0.5, 0.55, 0.65)), (1, (0.65, 0.72, 0.8))):
        for P in Ps:
            half = (pins[0][0] + pins[-1][0]) / 2
            ends = tuple(round(e + d, 3) for e in (pins[0][0] - (half - (n - 1) / 2.0 * P), pins[-1][0] - (half + (n - 1) / 2.0 * P))
                         for d in (0.0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3, 0.4, -0.4))
            for i in range(4, 20):
                h0 = i * 0.2
                for shift in (0.0, 0.4, -0.4, 0.8, -0.8) + ends:
                    for st in (0.0, 0.8, 1.6, 2.4):
                        if st + 0.6 > h0:
                            continue
                        out.append((h0 + (0.3 if rows == 2 else 0.0) + 0.4 * abs(shift) + (P - 0.5) + 0.1 * st,
                                    rows, P, h0, shift, st))
    out.sort()
    return out


def _fan_pattern(pins, rows, P, h0, shift, st, dh=0.55):
    """Each pin's via (place along the side, depth) and straight run for one pattern:
    vias evenly spaced `P` apart, centred on the pins (plus `shift`), in one row `h0`
    past the pads or two staggered rows (lines to the second pass between the first's
    vias); each line straight out of its pin for `st` (through a gap between capacitors
    at the pins' own pitch), then leaning to its via.  None if a line leans more than 35
    degrees or the pattern's own copper is too close anywhere."""
    n = len(pins)
    centre = (pins[0][0] + pins[-1][0]) / 2 + shift
    geo, parts = [], []
    for i, (s0, xy, tip, net, num) in enumerate(pins):
        a = tip + 0.25
        v = centre + (i - (n - 1) / 2.0) * P
        h = tip + h0 + (dh if rows == 2 and i % 2 else 0.0)
        if abs(v - s0) > 0.7 * (h - a - st) + 1e-9:
            return None
        v, h = round(v, 4), round(h, 4)
        geo.append((v, h, st))
        parts.append(([((s0, tip), (s0, a + st)), ((s0, a + st), (v, h))], (v, h)))
    for i in range(n):
        for j in range(i + 1, min(n, i + 3)):
            (si, vi), (sj, vj) = parts[i], parts[j]
            if math.hypot(vi[0] - vj[0], vi[1] - vj[1]) < FAN_VV:
                return None
            if any(_pt_seg(vi, *sg) < FAN_TV for sg in sj) or any(_pt_seg(vj, *sg) < FAN_TV for sg in si):
                return None
            if any(_seg_seg(a[0], a[1], b[0], b[1]) < FAN_TT for a in si for b in sj):
                return None
    return geo


def chip_keepout(R, pads, ref, inset=0.9):
    """No track of any other net on the top layer under a fine-pitch chip (inside its pin ring,
    between the pins and the paddle), and no via: only its own planned stubs and ties go there.
    The pins themselves stay out of it, or a pin with no fan-out is walled in at once."""
    xs = [xy for (r, num), xy in pads.xy.items() if r == ref]
    x0, x1 = min(p[0] for p in xs) + inset, max(p[0] for p in xs) - inset
    y0, y1 = min(p[1] for p in xs) + inset, max(p[1] for p in xs) - inset
    if x1 - x0 > 0.3 and y1 - y0 > 0.3:
        R.keepout(x0, y0, x1, y1, [pads.layer[ref]], via=True)


# ---------------------------------------------------------------------------------------------
# what the router does with each net
RF_PINS = {("J101", "1"), ("J202", "1"), ("J401", "1"), ("J402", "1"), ("J403", "1"),
           ("U104", "9"), ("U104", "10"), ("U201", "3"), ("U201", "4"), ("U115", "12"), ("U115", "13"),
           ("U203", "12"), ("U203", "13"), ("T101", "2"), ("T101", "3"), ("U104", "21"), ("U104", "22"),
           ("J109", "1"), ("J204", "1"), ("J102", "1"), ("J201", "1"), ("CP101", "3"), ("CP201", "3")}
BB_PINS = {("U104", "3"), ("U104", "4"), ("U104", "15"), ("U104", "16"), ("U105", "10"), ("U105", "11"), ("U106", "10"), ("U106", "11"),
           ("U501", "10"), ("U501", "11"), ("U502", "10"), ("U502", "11")}


def net_kind(pads, net):
    keys = pads.of.get(net, [])
    if net == "GND":
        return "gnd"
    if net.startswith("+5V") or net.endswith("VBUS"):
        return "pwr5"
    if net.startswith("+"):
        return "pwr"
    if any(k in RF_PINS for k in keys):
        return "rf"
    if any(k in BB_PINS for k in keys):
        return "bb"
    return "sig"


WIDTH = {"rf": RF_W, "bb": BB_W, "sig": SIG_W, "pwr": PWR_W, "pwr5": PWR5_W, "gnd": PWR_W}
TOP = {0: 1.0, 1: IN2_SIG_COST, 2: 2.0}   # layer costs: F.Cu first, B.Cu second, In2 (the supply pours) last
BOT = {0: 1.6, 1: IN2_SIG_COST, 2: 1.0}   # the slow signals go underneath: the top is the RF's and the eye's
ANY = {0: 1.4, 1: 1.0, 2: 1.2}            # the rails: In2 is where their pours are


IDENTITY_STRIP = (62.0, 55.5, 110.0, 63.5)     # board mm, B.Cu: the silkscreen identity goes here


def fine_chips(pads):
    """The chips that get a planned fan-out: every U with five or more pads (the QFNs, the
    FDAs, the MSOPs, the SC-70s and the SOT-23-5 regulators), the RF ones first."""
    count = {}
    for (ref, num) in pads.xy:
        count[ref] = count.get(ref, 0) + 1
    refs = [r for r, n in count.items() if r.startswith("U") and n >= 5]
    first = ["U104", "U201", "U115", "U203", "U102", "U105", "U106", "U501", "U502", "U401"]
    return [r for r in first if r in refs] + sorted(r for r in refs if r not in first)


CLASSES_JSON = os.path.join(BI.ROOT, "build", "netclasses.json")


def write_classes(pads):
    """The nets of the RF and LO net classes, by name, from the walks this file lays them by
    (gen/project.py binds them exactly: its name patterns had matched none of them, so the CPWG gap
    and the pair rule bound nothing: the design review), and each LO leg's nets in order for the
    skew gate (gen/board.lo_skew)."""
    import json
    rf, lo, legs = set(), set(), {}
    for name, start, stop in RF_PATHS + [p for p in PAIR_PATHS if p[0] in RF_PAIRS]:
        chain = walk(pads, start, stop)
        nets = [pads.net[k] for k in chain[0::2]]
        if name in LO_PAIRS:
            lo.update(nets)
            legs[name] = nets
        else:
            rf.update(nets)
    os.makedirs(os.path.dirname(CLASSES_JSON), exist_ok=True)
    json.dump({"RF": sorted(rf), "LO": sorted(lo), "lo_legs": legs}, open(CLASSES_JSON, "w"), indent=1)


def plan_and_route(R, pads, planned_only=False):
    """Everything from the pours to the last widened rail; returns a dict of counts."""
    out = {}
    write_classes(pads)
    R.keepout(*IDENTITY_STRIP, [2], via=True)     # the identity block on the back (gen/silk.bottom): no track or via under it, from the start
    for kb in PL.MARK_KEEP[:-1]:
        R.keepout(*kb, [0], via=True)            # a fiducial: bare laminate round its dot (gen/board.marks)
    R.keepout(*PL.MARK_KEEP[-1], [0, 1, 2], via=True)     # the layer numbers, on every layer
    supply_pours(R)
    laid, segs = rf_lines_by_plan(R, pads)
    out["rf_nets"] = len(laid)
    out["fence_vias"] = fence(R, segs, via_free(R))
    out["rf_stubs"] = rf_stubs(R, pads)
    npair, left = pair_lines_by_plan(R, pads)
    out["pair_segments"] = npair
    for l in left:
        print("   pair line left to the router: " + l)
    out["ep_vias"] = R.ep_vias()
    nt, left = ep_ties(R, pads)
    out["ep_ties"] = nt
    if left:
        print("   paddle ties left to the router: " + " ".join(left))
    fine = fine_chips(pads)
    nf = nl = 0
    t0 = time.time()
    # every chip's fan-out before any chip's local nets: a local net routed first ran along the
    # next chip's pin row and walled its pins in (Response 9); from its via a local net has every
    # layer to choose from and goes round
    for ref in fine:
        t = time.time()
        b = fan(R, ref, no_fan=RF_PINS)
        nf += b
        print("   %-5s %2d pins fanned %.0f s" % (ref, b, time.time() - t), flush=True)
    for ref in fine:
        nl += local_first(R, ref)
    route_unfanned(R)
    for ref in fine:
        chip_keepout(R, pads, ref)
    out["local_nets"], out["fanned_pins"] = nl, nf
    print("copper: %d RF nets by plan, %d fence vias, %d pair segments, %d paddle vias, %d paddle ties, %d local nets, %d pins fanned out (%.0f s)"
          % (out["rf_nets"], out["fence_vias"], npair, out["ep_vias"], nt, nl, nf, time.time() - t0), flush=True)
    out["gnd_vias"] = R.fanout("GND", reach=2.0, skip_refs=R.ep_refs)
    nr = 0
    for net in IN2_POURS:
        nr += R.fanout(net, reach=2.5, skip=("TP",))
    out["rail_vias"] = nr
    print("copper: %d ground vias and %d rail vias beside the passives" % (out["gnd_vias"], nr), flush=True)
    plane_copper_check(R, out["gnd_vias"])
    if planned_only:
        return out
    autoroute(R, pads)
    return out


def autoroute(R, pads):
    R.freeze_vias()
    kinds = {net: net_kind(pads, net) for net in R.by_net if not net.startswith("<")}
    spec, order = {}, []

    def take(net, widths, **kw):
        spec[net] = (widths, kw)
        order.append(net)
        t = time.time()
        ok = route_power(R, net, widths, **kw)
        dt = time.time() - t
        if not ok or dt > 15:
            print("   %-32s %-4s %s  %.1f s" % (net.split("/")[-1][:32], kinds[net], "ok" if ok else "FAILED", dt), flush=True)
        return ok

    t0 = time.time()
    if NEAR_REACH:
        nj, tried = join_near(R, kinds, NEAR_REACH)
        print("router: %d short connections joined first (of %d within %.1f mm)" % (nj, tried, NEAR_REACH), flush=True)
    rf = [n for n, k in kinds.items() if k == "rf" and R.unrouted(n)]
    POP = 400000                                  # a routable connection takes far fewer steps; a walled-in one is found sooner
    for net in rf:
        # the LO pairs and the monitor stubs leave 0.5 mm QFN pads: 0.2 mm, on the top layer if it can
        n0 = len(R.failed)
        if R.route_net(net, BB_W, layers=(0,), allow_via=False, max_pop=POP):
            spec[net] = ((BB_W,), dict(layer_cost=TOP, max_pop=POP)); order.append(net)
            continue
        R.failed = R.failed[:n0]
        take(net, (BB_W, SIG_W), layer_cost=TOP, max_pop=POP)
    for net in [n for n, k in kinds.items() if k == "bb" and R.unrouted(n)]:
        take(net, (BB_W, SIG_W), layer_cost=TOP, max_pop=POP)
    for net in [n for n, k in kinds.items() if k == "pwr5" and R.unrouted(n)]:
        take(net, (PWR5_W, PWR_W), layer_cost=ANY, max_pop=3 * POP)
    for net in [n for n, k in kinds.items() if k == "pwr" and R.unrouted(n)]:
        take(net, (PWR_W, SIG_W), layer_cost=ANY, max_pop=3 * POP)
    # the SPI bus first (Response 14): shortest-first left the board-wide lines to the end, after the
    # synthesizers' clock pins were walled in (SPI_SCLK failed in four builds of five).  Routing the
    # synthesizers' latches and MUX lines first too (Response 15) only walled in three other nets.
    first = ("/SPI_SCLK", "/SPI_SDATA")
    # ROUTE_SEED perturbs the shortest-first order by up to 15 % a net (0: none).  The board is near what
    # the router can finish, and which nets get walled in moves with any small change; trying a few orders
    # side by side and keeping the seed that finishes is faster than nudging parts (Response 15)
    import random
    rng = random.Random(ROUTE_SEED)
    jitter = {n: (rng.uniform(0.85, 1.15) if ROUTE_SEED else 1.0) for n in sorted(kinds)}
    for net in sorted([n for n, k in kinds.items() if k == "sig" and R.unrouted(n)],
                      key=lambda n: (first.index("/" + n.split("/")[-1]) if n.endswith(first) else len(first),
                                     span(R, n) * jitter[n])):
        take(net, (SIG_W,), layer_cost=BOT, bbox_margin=20.0, max_pop=3 * POP)
    if R.unrouted("GND"):
        R.route_net("GND", SIG_W, layers=(0,), allow_via=False, max_pop=60000)     # the fill reaches the rest
    def in_pieces():
        return sum(1 for n in R.by_net if not n.startswith("<") and R.unrouted(n))
    print("router: %d nets in %.0f s; %d in pieces before the repair" % (len(order), time.time() - t0, in_pieces()), flush=True)
    repair(R, spec, order)
    if in_pieces():
        # a wider rip-up for what is left (Response 15): twelve walls, two levels down
        print("router: %d in pieces; the wider repair" % in_pieces(), flush=True)
        repair(R, spec, order, rounds=2, most=12, depth=2)
    R.failed = [f for f in R.failed if R.unrouted(f[0])]
    print("router: %d in pieces after the repair" % in_pieces(), flush=True)
    nv = nt = 0
    for net in list(R.by_net):
        if net.startswith("<"):
            continue
        v, t = R.prune(net)
        nv += v; nt += t
    print("router: %d in pieces after the pruning" % in_pieces(), flush=True)
    wide = 0
    fine = set(fine_chips(pads))
    pins = [xy for (ref, num), xy in pads.xy.items() if ref in fine]
    for net, k in kinds.items():
        if k == "pwr5":
            wide += R.fatten(net, RAILS_5V, keep_narrow=pins)[0]
        elif k == "pwr":
            wide += R.fatten(net, RAILS_3V3, keep_narrow=pins)[0]
    print("router: %d in pieces after the widening" % in_pieces(), flush=True)
    ns = 0
    for net in list(R.by_net):
        if not net.startswith("<") and net != "GND":
            ns += R.sweep(net)
    print("router: %d unused vias and %d loose tracks removed, %d rail tracks widened, %d loose ends swept; %d in pieces"
          % (nv, nt, wide, ns, in_pieces()), flush=True)


def join_near(R, kinds, reach):
    """Every connection of a signal net whose pads lie within `reach` of each other, shortest first,
    before any net is routed whole (Response 15).  A net is routed whole in the order of its span, so a
    board-wide net's 2 mm hop from a pin to its capacitor waited for the long nets, and they had fenced
    the pad in on the top and filled the layer underneath: VC's U112.7 to C156, the PI node's R126 to
    R127.  Each pair is searched only round itself; the top layer without a via first."""
    cands = []
    for net, k in kinds.items():
        if k not in ("sig", "bb") or not R.unrouted(net):
            continue
        pts = [(rp, xy) for g in R.groups(net) for rp, xy in R.pad_points(g).items()]
        for i, (a, pa) in enumerate(pts):
            for b, pb in pts[i + 1:]:
                d = math.hypot(pa[0] - pb[0], pa[1] - pb[1])
                if d <= reach:
                    cands.append((d, net, a, b))
    cands.sort()
    joined = 0
    for d, net, a, b in cands:
        groups = R.groups(net)
        ga = next((g for g in groups if a in R.pad_points(g)), None)
        gb = next((g for g in groups if b in R.pad_points(g)), None)
        if ga is None or gb is None or ga is gb:
            continue
        w = BB_W if kinds[net] == "bb" else SIG_W
        if R.route_between(net, ga, gb, w, layers=(0,), allow_via=False, max_pop=40000, margin=1.0) or \
                R.route_between(net, ga, gb, w, layer_cost=BOT, max_pop=80000, margin=2.0):
            joined += 1
    return joined, len(cands)


def repair(R, spec, order, rounds=2, most=6, depth=1):
    """Rip-up and reroute.  For each net still in pieces: route it again to see the
    pocket its search was walled into, take out the router's copper of the nets (`most`
    at most) that bound the pocket, route the walled-in net first and then those, in
    their first order; a net that ends in pieces then gets the same, `depth` levels
    down.  Kept if fewer of the nets touched end in pieces than before; otherwise every
    one of them gets its old copper back, exactly."""
    rank = {n: i for i, n in enumerate(order)}
    tried = set()

    def attempt(net, depth, saved, was):
        widths, kw = spec[net]
        R.region.pop(net, None)
        if route_power(R, net, widths, **kw):
            return [net]
        cls, region = R.region.get(net, (None, None))
        walls = [n for n in R.walls(net, cls, region) if n in spec and n not in saved][:most] if region else []
        if not walls or (net, tuple(walls)) in tried:
            return [net]
        tried.add((net, tuple(walls)))
        for n in walls:
            saved[n] = R.routed_copper(n)
            was[n] = R.unrouted(n) > 0
            R.rip(n)
        group = [net] + sorted(walls, key=rank.get)
        for n in group:
            widths, kw = spec[n]
            route_power(R, n, widths, **kw)
        touched = list(group)
        if depth > 0:
            for n in group:
                if R.unrouted(n):
                    touched += attempt(n, depth - 1, saved, was)
        return touched

    for rnd in range(rounds):
        fixed = 0
        for net in [n for n in order if R.unrouted(n)]:
            if not R.unrouted(net):
                continue
            t = time.time()
            saved, was = {net: R.routed_copper(net)}, {net: True}
            nfail = len(R.failed)
            attempt(net, depth, saved, was)
            before = sum(1 for n in saved if was[n])
            after = sum(1 for n in saved if R.unrouted(n))
            if after < before:
                fixed += before - after
                verdict = "kept"
            else:
                for n in saved:
                    R.rip(n)
                    R.restore(n, saved[n])
                R.failed = R.failed[:nfail]
                verdict = "undone"
            if len(saved) > 1:
                print("   repair %s: ripped %s; %d -> %d in pieces, %s (%.0f s)"
                      % (net.split("/")[-1], " ".join(n.split("/")[-1] for n in saved if n != net), before, after,
                         verdict, time.time() - t), flush=True)
        if not fixed:
            break
