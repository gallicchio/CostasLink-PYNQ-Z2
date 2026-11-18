#!/usr/bin/env python3 -I
"""Measurements on the committed board (board.pkl from parse_board.py).  Board frame: mm from the
bottom-left corner, y up (the gerbers' and the CPL's frame).  Prints a long text report."""
import pickle, math, sys, os, re, collections
from shapely.geometry import Polygon, LineString, Point, MultiPolygon, box
from shapely.ops import unary_union
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
D = pickle.load(open(os.path.join(HERE, 'board.pkl'), 'rb'))
fps, segs, vias, zones, gr = D['fps'], D['segs'], D['vias'], D['zones'], D['gr']
FP = {f['ref']: f for f in fps}
W, H = 120.0, 100.0

# the RF line geometry (sim/rf_lines.py, copied)
RF_W, RF_GAP, FENCE_OFF, FENCE_PITCH = 0.29, 0.25, 0.29 / 2 + 0.25 + 0.45, 1.2
Hd, ER, T = 0.2104, 4.4, 0.035


def ellipk_ratio(k):
    kp = math.sqrt(1 - k * k)
    if k <= 1 / math.sqrt(2):
        return math.pi / math.log(2 * (1 + math.sqrt(kp)) / (1 - math.sqrt(kp)))
    return math.log(2 * (1 + math.sqrt(k)) / (1 - math.sqrt(k))) / math.pi


def cpwg_z0(w, s, h=Hd, er=ER, t=T):
    d = 1.25 * t / math.pi * (1 + math.log(4 * math.pi * w / t)) if t > 0 else 0
    w = w + d; s = s - d
    k = w / (w + 2 * s)
    k1 = math.tanh(math.pi * w / (4 * h)) / math.tanh(math.pi * (w + 2 * s) / (4 * h))
    K = ellipk_ratio(k); K1 = ellipk_ratio(k1)
    eeff = (1 + er * K1 / K) / (1 + K1 / K)
    return 60 * math.pi / math.sqrt(eeff) / (K + K1), eeff


Z0, EEFF = cpwg_z0(RF_W, RF_GAP)
QW = 299.792458 / 5.8 / math.sqrt(EEFF) / 4
LAM = 299.792458 / 5.8 / math.sqrt(EEFF)
print("CPWG %.2f/%.2f: Z0 %.1f ohm, eeff %.2f, lambda %.1f mm, lambda/8 %.2f mm, lambda/10 %.2f mm, quarter wave %.2f mm" % (RF_W, RF_GAP, Z0, EEFF, LAM, LAM / 8, LAM / 10, QW))
for w in (0.2, 0.25, 0.29, 0.35):
    print("   w %.2f gap %.2f: %.1f ohm" % (w, RF_GAP, cpwg_z0(w, RF_GAP)[0]))

# net classes
NC = {}
for line in open(os.path.join(HERE, 'netclasses.txt')):
    k, v = line.split(' ', 1)
    NC[k] = eval(v)
RFN = set(NC['RF']); LON = set(NC['LO'])


def pads_of(net):
    return [(f['ref'], p) for f in fps for p in f['pads'] if p['net'] == net]


# pad polygons
def pad_poly(f, p):
    x, y = p['xy']; sx, sy = p['size']
    a = math.radians(p['angle'])
    # board frame is y-up; KiCad's pad angle is CCW in the y-down page frame, so CW here: use -a
    pts = [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]
    out = []
    for px, py in pts:
        rx = px * math.cos(-a) - py * math.sin(-a)
        ry = px * math.sin(-a) + py * math.cos(-a)
        out.append((x + rx, y + ry))
    if p['shape'] == 'circle':
        return Point(x, y).buffer(sx / 2)
    return Polygon(out)


ALLPADS = [(f, p, pad_poly(f, p)) for f in fps for p in f['pads']]
PADS_F = [(f, p, g) for f, p, g in ALLPADS if 'F.Cu' in p['layers'] or '*.Cu' in p['layers']]
PADS_B = [(f, p, g) for f, p, g in ALLPADS if 'B.Cu' in p['layers'] or '*.Cu' in p['layers']]


def seg_line(s):
    return LineString([s['a'], s['b']])


def seg_len(s):
    return math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1])


# zone polygons
def zone_union(name_pred, layer):
    polys = []
    for z in zones:
        if name_pred(z):
            for fl, pts in z['filled']:
                if fl == layer and len(pts) >= 3:
                    pg = Polygon(pts)
                    if not pg.is_valid:
                        pg = pg.buffer(0)
                    polys.append(pg)
    return unary_union(polys) if polys else Polygon()


IN1 = zone_union(lambda z: z['net'] == 'GND' and 'In1.Cu' in z['layers'], 'In1.Cu')
GND_F = zone_union(lambda z: z['net'] == 'GND' and 'F.Cu' in z['layers'], 'F.Cu')
GND_B = zone_union(lambda z: z['net'] == 'GND' and 'B.Cu' in z['layers'], 'B.Cu')
GND_IN2 = zone_union(lambda z: z['net'] == 'GND' and 'In2.Cu' in z['layers'], 'In2.Cu')
POURS = {z['net']: zone_union(lambda zz, n=z['net']: zz['net'] == n and 'In2.Cu' in zz['layers'], 'In2.Cu') for z in zones if z['net'].startswith('+')}
print("\nIn1 GND plane: %d polygon(s), area %.0f mm2 of %.0f (%.1f %%)" % (len(IN1.geoms) if hasattr(IN1, 'geoms') else 1, IN1.area, W * H, 100 * IN1.area / (W * H)))
for n, pg in POURS.items():
    print("In2 pour %-12s area %.0f mm2, bounds %s" % (n, pg.area, tuple(round(v, 1) for v in pg.bounds)))
print("GND top fill: %d pieces, %.0f mm2; GND bottom: %d pieces, %.0f mm2; GND In2: %d pieces %.0f mm2" % (
    len(GND_F.geoms) if hasattr(GND_F, 'geoms') else 1, GND_F.area, len(GND_B.geoms) if hasattr(GND_B, 'geoms') else 1, GND_B.area,
    len(GND_IN2.geoms) if hasattr(GND_IN2, 'geoms') else 1, GND_IN2.area))

# ------------------------------------------------------------------ 1. RF nets
print("\n" + "=" * 100 + "\n1. RF AND LO NETS: tracks, widths, layers, vias, stubs, In1 under them, CPWG gap, fence")
GNDV = [v for v in vias if v['net'] == 'GND']
GNDV_pts = [Point(v['xy']) for v in GNDV]
OTHV = [v for v in vias if v['net'] != 'GND']


def net_tracks(net):
    return [s for s in segs if s['net'] == net]


def stubs(net):
    """Dangling track ends of a net: an endpoint shared by one segment only and inside no pad of the net."""
    ss = net_tracks(net)
    ends = collections.Counter()
    for s in ss:
        for e in (s['a'], s['b']):
            ends[(round(e[0], 3), round(e[1], 3))] += 1
    padp = [g for f, p, g in ALLPADS if p['net'] == net]
    vp = [Point(v['xy']) for v in vias if v['net'] == net]
    out = []
    for e, c in ends.items():
        if c == 1 and not any(g.buffer(0.01).contains(Point(e)) for g in padp) and not any(q.distance(Point(e)) < 0.01 for q in vp):
            # also not touching the middle of another segment of the net
            if not any(seg_line(s).distance(Point(e)) < 0.01 and (round(s['a'][0], 3), round(s['a'][1], 3)) != e and (round(s['b'][0], 3), round(s['b'][1], 3)) != e for s in ss):
                out.append(e)
    return out


RFLINES = []   # (net, seg) of F.Cu segments at RF width on RF/LO nets
summary = []
for net in sorted(RFN | LON, key=lambda n: (n in LON, n)):
    ss = net_tracks(net)
    if not ss:
        print("  %-40s NO TRACKS (pads: %s)" % (net, [r + '.' + p['num'] for r, p in pads_of(net)]))
        continue
    widths = collections.Counter((s['layer'], s['w']) for s in ss)
    L = {}
    for s in ss:
        L[(s['layer'], s['w'])] = L.get((s['layer'], s['w']), 0) + seg_len(s)
    vv = [v for v in vias if v['net'] == net]
    st = stubs(net)
    cls = 'LO' if net in LON else 'RF'
    pads = [r + '.' + p['num'] for r, p in pads_of(net)]
    print("  %-3s %-34s pads %-34s %s%s%s" % (cls, net, ' '.join(pads), '  '.join('%s w%.2f %.2fmm' % (k[0], k[1], v) for k, v in sorted(L.items())),
                                             '  VIAS %d' % len(vv) if vv else '', '  STUBS %s' % st if st else ''))
    for s in ss:
        if s['layer'] == 'F.Cu':
            RFLINES.append((net, s))

# In1 plane under every RF/LO F.Cu segment; CPWG gap to the top ground; non-GND vias beside the line
print("\n-- In1 ground under the RF/LO lines (the line plus its two 0.25 mm gaps plus 0.3 mm): any missing copper")
tot_missing = 0
for net, s in RFLINES:
    if seg_len(s) < 0.05:
        continue
    foot = seg_line(s).buffer(s['w'] / 2 + RF_GAP + 0.3, cap_style=2)
    miss = foot.difference(IN1)
    if miss.area > 0.02:
        tot_missing += miss.area
        c = miss.centroid
        near = [v for v in OTHV if Point(v['xy']).distance(seg_line(s)) < 1.2]
        nearpads = [f['ref'] + '.' + p['num'] for f, p, g in ALLPADS if p['kind'] == 'thru_hole' and p['net'] != 'GND' and g.distance(seg_line(s)) < 1.2]
        print("   %-34s seg (%.2f,%.2f)-(%.2f,%.2f) w%.2f: In1 missing %.2f mm2 at (%.1f,%.1f); vias beside: %s; THT pads: %s" % (
            net, *s['a'], *s['b'], s['w'], miss.area, c.x, c.y, ['%s(%.1f,%.1f)' % (v['net'][:18], *v['xy']) for v in near], nearpads))
print("   total In1 copper missing under RF/LO footprints: %.2f mm2" % tot_missing)

print("\n-- CPWG gap: the top GND fill's distance from each RF/LO line's edge (should be 0.25); and whether coplanar ground is there at all")
gap_stats = []
for net, s in RFLINES:
    if seg_len(s) < 0.3:
        continue
    ln = seg_line(s)
    core = ln.buffer(s['w'] / 2, cap_style=2)
    d = core.distance(GND_F)
    # coplanar ground presence: fraction of the band [edge+gap, edge+gap+0.3] on each side that is GND fill
    side_cov = []
    for sgn in (1, -1):
        off = ln.parallel_offset(s['w'] / 2 + RF_GAP + 0.15, 'left' if sgn > 0 else 'right')
        if off.is_empty:
            side_cov.append(float('nan')); continue
        band = off.buffer(0.15, cap_style=2)
        side_cov.append(band.intersection(GND_F).area / band.area if band.area else float('nan'))
    gap_stats.append((net, s, d, side_cov))
bad = [(n, s, d, c) for n, s, d, c in gap_stats if d < 0.24 or min(c) < 0.6]
print("   %d segments >= 0.3 mm; min fill distance %.3f, max %.3f" % (len(gap_stats), min(g[2] for g in gap_stats), max(g[2] for g in gap_stats)))
for n, s, d, c in sorted(bad, key=lambda t: t[2]):
    print("   %-34s (%.2f,%.2f)-(%.2f,%.2f) w%.2f L%.2f: fill at %.3f mm; coplanar GND coverage L %.0f%% R %.0f%%" % (n, *s['a'], *s['b'], s['w'], seg_len(s), d, 100 * c[0], 100 * c[1]))

print("\n-- Via fence: GND vias in the band %.2f +- 0.3 mm beside each RF/LO segment longer than 2 mm; largest gap along the line" % FENCE_OFF)
for net, s in RFLINES:
    Ls = seg_len(s)
    if Ls < 2.0:
        continue
    ln = seg_line(s)
    ux, uy = (s['b'][0] - s['a'][0]) / Ls, (s['b'][1] - s['a'][1]) / Ls
    res = []
    for sgn in (1, -1):
        ts = []
        for v in GNDV:
            x, y = v['xy']
            rx, ry = x - s['a'][0], y - s['a'][1]
            t = rx * ux + ry * uy
            n_ = -rx * uy + ry * ux
            if -0.3 <= t <= Ls + 0.3 and abs(n_ * sgn - FENCE_OFF) <= 0.35:
                ts.append(t)
        ts.sort()
        gaps = [b - a for a, b in zip([0] + ts, ts + [Ls])] if ts else [Ls]
        res.append((len(ts), max(gaps)))
    flag = ' <-- gap > lambda/10 (%.1f)' % (LAM / 10) if max(r[1] for r in res) > LAM / 10 else ''
    print("   %-34s (%.1f,%.1f)-(%.1f,%.1f) L%5.2f: left %2d vias max gap %.2f, right %2d vias max gap %.2f%s" % (net, *s['a'], *s['b'], Ls, res[0][0], res[0][1], res[1][0], res[1][1], flag))

# non-GND vias near RF lines (In1 hole + coupling)
print("\n-- Vias of other nets within 1.0 mm of an RF/LO line's centre")
for net, s in RFLINES:
    ln = seg_line(s)
    for v in OTHV:
        if v['net'] != net and ln.distance(Point(v['xy'])) < 1.0:
            print("   %-34s line (%.1f,%.1f)-(%.1f,%.1f): via %s at (%.2f,%.2f) %.2f mm away" % (net, *s['a'], *s['b'], v['net'], *v['xy'], ln.distance(Point(v['xy']))))

# other nets' top tracks within the CPWG gap (crossing the coplanar gap region)
print("\n-- Other nets' F.Cu tracks within 0.6 mm of an RF/LO line (inside the coplanar ground region)")
seen = set()
for net, s in RFLINES:
    ln = seg_line(s)
    for o in segs:
        if o['layer'] != 'F.Cu' or o['net'] == net or o['net'] in RFN or o['net'] in LON or o['net'] == 'GND':
            continue
        d = ln.distance(seg_line(o)) - s['w'] / 2 - o['w'] / 2
        if d < 0.6:
            key = (net, o['net'])
            if key in seen:
                continue
            seen.add(key)
            print("   %-34s vs %-30s edge gap %.2f mm near (%.1f,%.1f)" % (net, o['net'], d, *o['a']))

# ------------------------------------------------------------------ LO legs
print("\n-- LO legs: the three nets of each leg and their track lengths (F.Cu), pad-to-pad through the DC blocks")


def walk_chain(start_ref, start_num, stop_ref, stop_num):
    """pads along a path: at each net take the two-terminal part whose far end nears the stop."""
    padxy = {(f['ref'], p['num']): p['xy'] for f in fps for p in f['pads']}
    padnet = {(f['ref'], p['num']): p['net'] for f in fps for p in f['pads']}
    of = collections.defaultdict(list)
    for k, n in padnet.items():
        of[n].append(k)
    cur = (start_ref, start_num); chain = [cur]; seen = {cur}
    sx, sy = padxy[(stop_ref, stop_num)]
    for _ in range(20):
        net = padnet[cur]
        best = None
        for k in of[net]:
            if k in seen or k == cur:
                continue
            if k == (stop_ref, stop_num):
                chain.append(k); return chain
            nums = [n for (r, n) in padxy if r == k[0]]
            if len(nums) != 2 or k[0][0] not in 'CRL' or FP[k[0]]['dnp']:
                continue
            far = (k[0], [n for n in nums if n != k[1]][0])
            fnet = padnet[far]
            if fnet == 'GND' or (fnet or '').startswith('+'):
                continue
            d = math.hypot(padxy[far][0] - sx, padxy[far][1] - sy)
            if best is None or d < best[0]:
                best = (d, k, far)
        if best is None:
            return chain
        chain += [best[1], best[2]]; seen.update([best[1], best[2]]); cur = best[2]
    return chain


padnet = {(f['ref'], p['num']): p['net'] for f in fps for p in f['pads']}
padxy = {(f['ref'], p['num']): p['xy'] for f in fps for p in f['pads']}
legs = {"RX LO +": (("U115", "12"), ("U104", "10")), "RX LO -": (("U115", "13"), ("U104", "9")),
        "TX LO +": (("U203", "12"), ("U201", "4")), "TX LO -": (("U203", "13"), ("U201", "3"))}
leglen = {}
for name, (a, b) in legs.items():
    ch = walk_chain(*a, *b)
    nets = []
    for k in ch[0::2]:
        nets.append(padnet[k])
    tot = 0.0
    parts = []
    for n in nets:
        l = sum(seg_len(s) for s in net_tracks(n))
        tot += l
        parts.append("%s %.2f" % (n.split('/')[-1], l))
    # straight-line pad-to-pad distances through the chain
    geo = sum(math.hypot(padxy[q][0] - padxy[p][0], padxy[q][1] - padxy[p][1]) for p, q in zip(ch[0::2], ch[1::2]))
    leglen[name] = tot
    print("   %-8s %s: tracks %.2f mm (%s); pad-to-pad straight %.2f mm" % (name, ' -> '.join('%s.%s' % k for k in ch), tot, ', '.join(parts), geo))
for pair in (("RX LO +", "RX LO -"), ("TX LO +", "TX LO -")):
    d = abs(leglen[pair[0]] - leglen[pair[1]])
    print("   %s/%s skew %.3f mm = %.1f deg at 5.8 GHz (%.1f ps)" % (pair[0], pair[1], d, 360 * d / LAM, d / LAM / 5.8e9 * 1e12))

# ------------------------------------------------------------------ couplers
print("\n-- Couplers CP101/CP201: copper length vs quarter wave %.2f mm" % QW)
for ref in ("CP101", "CP201"):
    f = FP[ref]
    lines = [g for g in f['graphics'] if g['layer'] == 'F.Cu' and g['kind'] == 'fp_line']
    for g in lines:
        print("   %s line (%.2f,%.2f)-(%.2f,%.2f) w%.2f L%.2f" % (ref, *g['a'], *g['b'], g['w'], math.hypot(g['b'][0] - g['a'][0], g['b'][1] - g['a'][1])))
    for p in f['pads']:
        print("   %s pad %s at (%.2f,%.2f) %sx%s net %s" % (ref, p['num'], *p['xy'], p['size'][0], p['size'][1], p['net']))
    # the gap between the two lines and whether GND fill intrudes between them
    if len(lines) == 2:
        l1, l2 = seg_line({'a': lines[0]['a'], 'b': lines[0]['b']}), seg_line({'a': lines[1]['a'], 'b': lines[1]['b']})
        gap = l1.distance(l2) - lines[0]['w'] / 2 - lines[1]['w'] / 2
        between = l1.buffer(l1.distance(l2) / 2 + 0.01, cap_style=2).intersection(l2.buffer(l1.distance(l2) / 2 + 0.01, cap_style=2))
        print("   %s edge gap between the lines %.3f mm; GND fill between them %.3f mm2" % (ref, gap, between.intersection(GND_F).area))

# ------------------------------------------------------------------ T101
print("\n-- T101 (the balun as committed) and the balanced pair into U104 pins 21/22")
f = FP['T101']
print("   T101 %s at (%.2f,%.2f) rot %s" % (f['name'], *f['xy'], f['angle']))
for p in f['pads']:
    tr = [s for s in segs if s['net'] == p['net'] and (Point(s['a']).distance(Point(p['xy'])) < 0.6 or Point(s['b']).distance(Point(p['xy'])) < 0.6)]
    print("   pad %s (%.2f,%.2f) %.2fx%.2f net %-28s tracks into it: %s" % (p['num'], *p['xy'], *p['size'], p['net'], ['%s w%.2f L%.2f' % (s['layer'], s['w'], seg_len(s)) for s in tr]))
for num in ("21", "22", "9", "10"):
    p = next(p for p in FP['U104']['pads'] if p['num'] == num)
    print("   U104.%s (%.2f,%.2f) net %s tracks %.2f mm" % (num, *p['xy'], p['net'], sum(seg_len(s) for s in net_tracks(p['net']))))

# ------------------------------------------------------------------ 2. grounding and power
print("\n" + "=" * 100 + "\n2. GROUNDING AND POWER")
# every GND pad: is there a GND via within reach through copper?  approximation: nearest GND via distance and whether the pad's
# connected top-copper piece (pad + fill piece + tracks) holds a GND via
print("-- GND SMD pads with no GND via within 1.5 mm (centre to centre)")
cnt = 0
for f, p, g in ALLPADS:
    if p['net'] != 'GND' or p['kind'] != 'smd':
        continue
    dmin = min(q.distance(Point(p['xy'])) for q in GNDV_pts)
    if dmin > 1.5:
        cnt += 1
        print("   %s.%s at (%.2f,%.2f) size %.2fx%.2f: nearest GND via %.2f mm" % (f['ref'], p['num'], *p['xy'], *p['size'], dmin))
print("   %d such pads" % cnt)

# R125.2 (route_report: GND 'walled in')
for f, p, g in ALLPADS:
    if f['ref'] == 'R125':
        d = min(q.distance(Point(p['xy'])) for q in GNDV_pts)
        tr = [s for s in segs if seg_line(s).distance(g) < 0.01 and s['net'] == p['net']]
        inF = g.intersects(GND_F)
        print("   R125.%s net %s at (%.2f,%.2f): nearest GND via %.2f, tracks %d, touches top GND fill: %s" % (p['num'], p['net'], *p['xy'], d, len(tr), inF))

# islands: GND fill pieces that contain no GND via or GND pad
print("-- Top/bottom GND fill pieces with no GND via and no GND pad in them (islands); and pieces with a pad but no via")
for nm, U, padlist in (("F.Cu", GND_F, PADS_F), ("B.Cu", GND_B, PADS_B), ("In2", GND_IN2, [])):
    geoms = list(U.geoms) if hasattr(U, 'geoms') else [U]
    nov = nopad = 0
    for pg in geoms:
        hasv = any(pg.intersects(q.buffer(0.3)) for q in GNDV_pts)
        hasp = any(pg.intersects(g) for f, p, g in padlist if p['net'] == 'GND')
        if not hasv and not hasp:
            nov += 1
            print("   %s island %.2f mm2 at (%.1f,%.1f): no GND via, no GND pad" % (nm, pg.area, pg.centroid.x, pg.centroid.y))
        elif not hasv:
            nopad += 1
            pads_in = [f['ref'] + '.' + p['num'] for f, p, g in padlist if p['net'] == 'GND' and pg.intersects(g)]
            print("   %s piece %.2f mm2 at (%.1f,%.1f): GND pads %s but NO via in the piece" % (nm, pg.area, pg.centroid.x, pg.centroid.y, pads_in[:8]))
    print("   %s: %d pieces, %d islands, %d via-less pieces with pads" % (nm, len(geoms), nov, nopad))

# exposed pads: via grid
print("-- Exposed pads: GND vias inside each (and the pad's size)")
for f, p, g in ALLPADS:
    if p['kind'] == 'smd' and min(p['size']) >= 1.2 and p['net'] == 'GND' and 'F.Cu' in p['layers']:
        n = sum(1 for q in GNDV_pts if g.contains(q))
        print("   %-6s pad %s %.2fx%.2f at (%.2f,%.2f): %d GND vias inside" % (f['ref'], p['num'], *p['size'], *p['xy'], n))

# +5V_RF pour: bottleneck width between the source and each load via
print("-- +5V_RF pour: narrowest width on the way from its source to each via of the net (0.1 mm raster)")
from scipy import ndimage


def bottleneck(pour, src_pts, dst_pts, res=0.1):
    minx, miny, maxx, maxy = pour.bounds
    nx, ny = int((maxx - minx) / res) + 3, int((maxy - miny) / res) + 3
    mask = np.zeros((ny, nx), bool)
    # rasterize: sample cell centres
    from shapely import speedups
    from shapely.prepared import prep
    pp = prep(pour)
    xs = minx + (np.arange(nx) + 0.5) * res - res
    ys = miny + (np.arange(ny) + 0.5) * res - res
    for j, y in enumerate(ys):
        row = LineString([(minx - res, y), (maxx + res, y)]).intersection(pour)
        if row.is_empty:
            continue
        parts = list(row.geoms) if hasattr(row, 'geoms') else [row]
        for part in parts:
            x0, x1 = part.bounds[0], part.bounds[2]
            i0, i1 = int((x0 - xs[0]) / res + 0.5), int((x1 - xs[0]) / res + 0.5)
            mask[j, max(0, i0):min(nx, i1 + 1)] = True
    dist = ndimage.distance_transform_edt(mask) * res   # distance to the pour's edge, mm
    def cell(pt):
        return (int((pt[1] - ys[0]) / res + 0.5), int((pt[0] - xs[0]) / res + 0.5))
    out = {}
    for name, pt in dst_pts:
        c = cell(pt)
        if not (0 <= c[0] < ny and 0 <= c[1] < nx) or not mask[c]:
            out[name] = None; continue
        lo, hi = 0.0, float(dist.max())
        for _ in range(14):
            mid = (lo + hi) / 2
            lab, n = ndimage.label(dist >= mid)
            ok = any(0 <= cell(s)[0] < ny and 0 <= cell(s)[1] < nx and lab[cell(s)] and lab[cell(s)] == lab[c] for s in src_pts)
            if ok:
                lo = mid
            else:
                hi = mid
        out[name] = 2 * lo
    return out


for net in ("+5V_RF", "+3V3_ANA", "+3V3_DIG", "+5V_IN"):
    pour = POURS.get(net)
    if pour is None:
        continue
    vv = [v for v in vias if v['net'] == net]
    pp = pads_of(net)
    # the source: the regulator's output pad (U30x) or the fuse/FET for +5V
    src_refs = sorted({r for r, p in pp if r.startswith('U3') or r.startswith('Q3') or r.startswith('F3') or r.startswith('J3')})
    src_pts = [v['xy'] for v in vv if min(math.hypot(v['xy'][0] - padxy[(r, p['num'])][0], v['xy'][1] - padxy[(r, p['num'])][1]) for r, p in pp if r in src_refs) < 3.0] if src_refs else []
    print("   %s: %d vias, %d pads; parts %s; source refs %s; %d source vias" % (net, len(vv), len(pp), sorted({r for r, p in pp}), src_refs, len(src_pts)))
    if not src_pts:
        continue
    dst = [("via(%.1f,%.1f)" % v['xy'], v['xy']) for v in vv]
    bn = bottleneck(pour, src_pts, dst)
    worst = sorted(((w if w is not None else -1), n) for n, w in bn.items())[:6]
    print("      narrowest path widths (worst 6): %s" % ', '.join('%s %.2f mm' % (n, w) for w, n in worst))
    outside = [n for n, w in bn.items() if w is None]
    if outside:
        print("      vias NOT over the pour: %s" % outside)

# via counts per supply net and their current
print("-- Supply nets: vias, and the tracks' widths")
for net in sorted({s['net'] for s in segs if s['net'].startswith('+')}):
    ss = net_tracks(net)
    wd = collections.Counter(s['w'] for s in ss)
    vv = [v for v in vias if v['net'] == net]
    print("   %-14s %3d vias, tracks %s" % (net, len(vv), dict(sorted(wd.items()))))

# ------------------------------------------------------------------ 3. decoupling
print("\n" + "=" * 100 + "\n3. DECOUPLING: each supply pin of the RF chips, synthesizers, FDAs: the nearest capacitor on that net")
CHIPS = ["U101", "U102", "U103", "U117", "U202", "U201", "U104", "U115", "U203", "U105", "U106", "U501", "U502", "U401", "U107", "U503", "U504", "U505", "U601", "U602", "U603", "U604", "Y101", "Y201", "U507", "U112", "U508"]
for ref in CHIPS:
    f = FP.get(ref)
    if not f:
        continue
    for p in f['pads']:
        n = p['net'] or ''
        if not (n.startswith('+') or n.startswith('VC')) and not re.search('V(CC|DD|POS|PS|SS)|VBUS', n):
            continue
        caps = [(math.hypot(q['xy'][0] - p['xy'][0], q['xy'][1] - p['xy'][1]), g['ref'], g['props'].get('Value', ''), q) for g in fps if g['ref'].startswith('C') for q in g['pads'] if q['net'] == n]
        caps.sort()
        if not caps:
            print("   %s.%s %-14s NO CAPACITOR on this net" % (ref, p['num'], n)); continue
        d, cref, val, q = caps[0]
        other = next(qq for qq in FP[cref]['pads'] if qq['num'] != q['num'])
        dv = min(x.distance(Point(other['xy'])) for x in GNDV_pts) if other['net'] == 'GND' else float('nan')
        # track length from pin to cap: approximate by the net's tracks touching both
        small = [c for c in caps if c[0] < 2.5]
        print("   %-5s.%-3s %-14s nearest %-5s %-7s %.2f mm (other pad %s, GND via %.2f mm); caps within 2.5 mm: %s" % (ref, p['num'], n, cref, val, d, other['net'], dv, ['%s %s %.1f' % (c[1], c[2], c[0]) for c in small]))

# ------------------------------------------------------------------ 4. signal integrity
print("\n" + "=" * 100 + "\n4. COMPARATOR OUTPUTS AND OTHER SIGNALS: lengths, layers, vias, In2 pour-boundary crossings under B.Cu")
IN2_ALL = [(n, pg) for n, pg in POURS.items()] + [("GND_In2", GND_IN2)]


def in2_region(pt):
    P = Point(pt)
    for n, pg in IN2_ALL:
        if pg.contains(P):
            return n
    return None


def crossings(ss):
    """for B.Cu segments: how many times the reference under the line changes region (pour to pour, or over a gap)"""
    n = 0; detail = []
    for s in ss:
        if s['layer'] != 'B.Cu':
            continue
        L = seg_len(s)
        k = max(2, int(L / 0.2) + 1)
        prev = None
        for i in range(k + 1):
            t = i / k
            pt = (s['a'][0] + t * (s['b'][0] - s['a'][0]), s['a'][1] + t * (s['b'][1] - s['a'][1]))
            r = in2_region(pt)
            if prev is not None and r != prev and not (r is None and prev is None):
                if r is not None or prev is not None:
                    n += 1; detail.append((prev, r, pt))
            prev = r
    return n, detail


def net_report(net, label=''):
    ss = net_tracks(net)
    L = collections.Counter()
    for s in ss:
        L[s['layer']] += seg_len(s)
    vv = [v for v in vias if v['net'] == net]
    nc, det = crossings(ss)
    pads = [r + '.' + p['num'] for r, p in pads_of(net)]
    # In1 holes under F.Cu segments
    missing = 0.0
    for s in ss:
        if s['layer'] == 'F.Cu' and seg_len(s) > 0.05:
            missing += seg_line(s).buffer(s['w'] / 2 + 0.2, cap_style=2).difference(IN1).area
    print("   %-30s %-26s %s vias %d, total %.1f mm; In2 boundary crossings under B.Cu: %d; In1 missing under F.Cu %.2f mm2%s" % (
        net.split('/')[-1][:30], ' '.join(pads)[:26], ' '.join('%s %.1f' % (k, v) for k, v in sorted(L.items())), len(vv), sum(L.values()), nc, missing, label))
    for prev, r, pt in det[:6]:
        print("        crosses %s -> %s at (%.1f,%.1f)" % (prev, r, *pt))


print("-- The 33 ohm series resistors' nets (comparator outputs to the header)")
for ref in ("R120", "R134", "R221", "R222", "R519", "R520", "R521", "R603", "R607", "R611", "R615"):
    f = FP.get(ref)
    if not f:
        continue
    for p in f['pads']:
        net_report(p['net'], '   [%s.%s]' % (ref, p['num']))
print("-- SPI / I2C / trigger / LE / CE lines")
for net in sorted({s['net'] for s in segs}):
    if re.search('SPI|SDA|SCL|I2C|TRIG|LE$|LE_|_CE|MUX|LD|CS', net):
        net_report(net)
print("-- All signal nets on B.Cu: In2 boundary crossings, ranked")
rank = []
for net in sorted({s['net'] for s in segs}):
    if net == 'GND' or net.startswith('+'):
        continue
    nc, det = crossings(net_tracks(net))
    if nc:
        rank.append((nc, net))
rank.sort(reverse=True)
print("   %d nets cross an In2 boundary under a B.Cu track; total crossings %d" % (len(rank), sum(r[0] for r in rank)))
for nc, net in rank[:25]:
    print("   %2d  %s" % (nc, net))

# ------------------------------------------------------------------ 5. JLCPCB capability
print("\n" + "=" * 100 + "\n5. JLCPCB CAPABILITY")
wd = collections.Counter(s['w'] for s in segs)
print("-- track widths: %s" % dict(sorted(wd.items())))
vd = collections.Counter((v['size'], v['drill']) for v in vias)
print("-- vias (diameter, drill): %s; annular ring %.3f mm" % (dict(vd), min((s - d) / 2 for s, d in vd)))
th = collections.Counter((f['ref'][:1], p['shape'], tuple(p['size']), tuple(p['drill']) if p['drill'] else None) for f in fps for p in f['pads'] if p['kind'] in ('thru_hole', 'np_thru_hole'))
print("-- through-hole pads: ")
for k, v in sorted(th.items(), key=lambda t: -t[1]):
    print("   %s x%d" % (k, v))
# hole to hole, via to via
vpts = np.array([v['xy'] for v in vias])
from scipy.spatial import cKDTree
tree = cKDTree(vpts)
pairs = tree.query_pairs(0.6)
md = min(math.hypot(*(vpts[i] - vpts[j])) for i, j in pairs) if pairs else None
print("-- closest via pair (centre to centre): %.3f mm -> wall %.3f mm; %d pairs under 0.6 mm" % (md, md - 0.25, len(pairs)) if md else "-- no via pairs under 0.6 mm")
# min pad-to-pad mask dam for fine-pitch
print("-- mask dams between neighbouring pads of fine-pitch parts (pad_to_mask_clearance 0): pitch - pad width")
seen = set()
for f in fps:
    sm = [p for p in f['pads'] if p['kind'] == 'smd' and min(p['size']) < 0.45]
    if len(sm) < 4 or f['name'] in seen:
        continue
    seen.add(f['name'])
    dmin = 9
    for i, p in enumerate(sm):
        for q in sm[i + 1:]:
            d = pad_poly(f, p).distance(pad_poly(f, q))
            if d > 0.01:
                dmin = min(dmin, d)
    print("   %-45s %s: min pad edge gap %.3f mm" % (f['name'], f['ref'], dmin))
# copper to edge
outline = box(0, 0, W, H)
print("-- copper nearest the board edge (pads and tracks, outer layers)")
worst = []
for f, p, g in ALLPADS:
    d = min(g.bounds[0], g.bounds[1], W - g.bounds[2], H - g.bounds[3])
    worst.append((d, f['ref'] + '.' + p['num'], p['xy']))
for s in segs:
    g = seg_line(s).buffer(s['w'] / 2)
    d = min(g.bounds[0], g.bounds[1], W - g.bounds[2], H - g.bounds[3])
    worst.append((d, 'track ' + s['net'][:20] + ' ' + s['layer'], s['a']))
worst.sort()
for d, what, xy in worst[:10]:
    print("   %.3f mm  %s at (%.2f,%.2f)" % (d, what, *xy))
for nm, U in (("GND_F", GND_F), ("GND_B", GND_B), ("In1", IN1), ("GND_In2", GND_IN2)):
    b = U.bounds
    print("   fill %s bounds (%.2f,%.2f)-(%.2f,%.2f): edge margin %.2f" % (nm, *b, min(b[0], b[1], W - b[2], H - b[3])))
for n, pg in POURS.items():
    b = pg.bounds
    print("   pour %s bounds (%.2f,%.2f)-(%.2f,%.2f): edge margin %.2f" % (n, *b, min(b[0], b[1], W - b[2], H - b[3])))

# fiducials, holes
print("-- fiducials and holes")
for f in fps:
    if 'Fiducial' in f['name'] or f['ref'].startswith('H'):
        for p in f['pads']:
            print("   %-6s %-32s pad %s %s at (%.2f,%.2f) size %s drill %s layers %s" % (f['ref'], f['name'], p['num'], p['kind'], *p['xy'], p['size'], p['drill'], p['layers'][:2]))
        if f['ref'].startswith('H'):
            near = [(s['net'], s['layer']) for s in segs if seg_line(s).distance(Point(f['xy'])) < 2.2]
            nv = [v['net'] for v in vias if Point(v['xy']).distance(Point(f['xy'])) < 2.2]
            print("      copper within 2.2 mm of %s centre: tracks %s vias %s" % (f['ref'], near[:5], nv[:5]))

# J302 vs the PYNQ formula
print("-- J302 socket (back): pin 1 and pin 2, 39, 40 positions")
f = FP['J302']
for p in f['pads']:
    if p['num'] in ('1', '2', '39', '40'):
        print("   J302.%s at (%.2f,%.2f) size %s drill %s shape %s" % (p['num'], *p['xy'], p['size'], p['drill'], p['shape']))
print("   J302 layer %s angle %s; the PYNQ formula: pin1 (53.78, 7.50 from bottom) pin2 (53.78, 4.96) [placement.py frame y down: 92.5 / 95.04]" % (f['layer'], f['angle']))
# copper under the socket on top (the socket's insulator is on the back, so top copper there is fine) -- what's on the bottom near the pins
pins = [g for ff, p, g in ALLPADS if ff['ref'] == 'J302']
sock = unary_union(pins).convex_hull.buffer(1.0)
bot_parts = [ff['ref'] for ff in fps if ff['layer'] == 'B.Cu' and ff['ref'] != 'J302']
print("   parts on the back: %s; top-side parts whose pads lie within the socket's footprint: %s" % (bot_parts, sorted({ff['ref'] for ff, p, g in ALLPADS if ff['ref'] != 'J302' and ff['layer'] == 'F.Cu' and g.intersects(sock)})))

# ------------------------------------------------------------------ 7. silkscreen over pads
print("\n" + "=" * 100 + "\n7. SILKSCREEN over pads (text boxes at 0.85 x size per character; lines by their stroke)")


def text_box(t):
    s = t['text']
    if not t['size']:
        return None
    n = len(str(s))
    w = 0.85 * t['size'][0] * n + 0.1
    h = t['size'][1] + 0.1
    a = math.radians(t['angle'])
    cx, cy = t['xy']
    pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    return Polygon([(cx + px * math.cos(a) - py * math.sin(a), cy + px * math.sin(a) + py * math.cos(a)) for px, py in pts])


silk = []
for f in fps:
    for t in f['texts']:
        if t['layer'] == 'F.SilkS' and t['text'] and t['text'] != '${REFERENCE}':
            silk.append(('text', f['ref'] + ':' + t['text'], text_box(t)))
        elif t['layer'] == 'F.SilkS' and t['text'] == '${REFERENCE}':
            tt = dict(t); tt['text'] = f['ref']
            silk.append(('text', f['ref'] + ':' + f['ref'], text_box(tt)))
    for g in f['graphics']:
        if g['layer'] == 'F.SilkS':
            if g['kind'] == 'fp_line':
                silk.append(('line', f['ref'], LineString([g['a'], g['b']]).buffer(g['w'] / 2)))
            elif g['kind'] == 'fp_rect':
                silk.append(('rect', f['ref'], box(min(g['a'][0], g['b'][0]), min(g['a'][1], g['b'][1]), max(g['a'][0], g['b'][0]), max(g['a'][1], g['b'][1])).exterior.buffer(g['w'] / 2)))
            elif g['kind'] == 'circle':
                silk.append(('circle', f['ref'], Point(g['a']).buffer(g['r'] + g['w'] / 2)))
for g in gr:
    if g['layer'] == 'F.SilkS':
        if g['kind'] == 'text':
            # gr_text: justification
            tb = text_box(g)
            just = g.get('just')
            if tb is not None and just:
                w = tb.bounds[2] - tb.bounds[0]; h = tb.bounds[3] - tb.bounds[1]
                dx = dy = 0
                if 'left' in just:
                    dx = w / 2
                if 'right' in just:
                    dx = -w / 2
                if 'top' in just:
                    dy = -h / 2
                if 'bottom' in just:
                    dy = h / 2
                from shapely.affinity import translate
                tb = translate(tb, dx, dy)
            silk.append(('gtext', g['text'][:20], tb))
        elif g['kind'] in ('gr_line', 'gr_rect'):
            silk.append(('gline', '', LineString([g['a'], g['b']]).buffer(g['w'] / 2)))
nsilk = len(silk)
hits = []
for kind, who, poly in silk:
    if poly is None:
        continue
    for f, p, g in PADS_F:
        if poly.intersects(g.buffer(0.1)):
            if kind in ('line', 'rect', 'circle') and who == f['ref']:
                pass
            hits.append((kind, who, f['ref'] + '.' + p['num'], round(poly.intersection(g.buffer(0.1)).area, 3)))
print("   %d silk items; %d overlaps with a pad+0.1 mm:" % (nsilk, len(hits)))
for h_ in hits:
    print("   %s %s over %s (%.3f mm2)" % h_)
# every connector named on the silk?
conns = [f['ref'] for f in fps if f['ref'][0] == 'J' or f['ref'][:2] == 'JP' or f['ref'][:2] == 'TP']
texts_all = ' '.join(str(t[1]) for t in silk if t[0] in ('text', 'gtext'))
print("-- connectors whose designator does not appear in any silk text: %s" % [c for c in conns if c not in texts_all])

# ------------------------------------------------------------------ 8. thermal
print("\n" + "=" * 100 + "\n8. THERMAL: the ADL5611 tabs, the regulators")
for ref in ("U103", "U117", "U202"):
    f = FP[ref]
    for p in f['pads']:
        n = sum(1 for q in GNDV_pts if pad_poly(f, p).buffer(0.05).contains(q))
        print("   %s pad %s net %-22s %.2fx%.2f at (%.2f,%.2f): %d GND vias in it; shape %s" % (ref, p['num'], p['net'], *p['size'], *p['xy'], n, p['shape']))
    # polygon pads: the pad's own primitives are not parsed; look at the top GND fill contact
for ref in ("U301", "U302", "U303", "U304", "U305"):
    f = FP[ref]
    print("   %s %s at (%.1f,%.1f) %s" % (ref, f['props'].get('Value'), *f['xy'], [(p['num'], p['net']) for p in f['pads']]))
    for p in f['pads']:
        if p['net'] == 'GND':
            d = min(q.distance(Point(p['xy'])) for q in GNDV_pts)
            print("      GND pad %s: nearest GND via %.2f mm" % (p['num'], d))

# ------------------------------------------------------------------ 6. the release package
print("\n" + "=" * 100 + "\n6. RELEASE: board footprints vs BOM and CPL")
import csv
REL = './mfg/release/'
bom = list(csv.DictReader(open(REL + 'BOM_JLCPCB.csv')))
bomrefs = {}
for row in bom:
    for r in row['Designator'].split(','):
        bomrefs[r.strip()] = row['LCSC']
cpl = list(csv.DictReader(open(REL + 'CostasLink-PYNQ-Z2_cpl_jlcpcb_upload.csv')))
cplrefs = {r['Designator']: r for r in cpl}
excl = {r['Designator'] for r in csv.DictReader(open(REL + 'excluded_from_assembly.csv'))}
boardrefs = {f['ref']: f for f in fps}
print("   board %d footprints; BOM %d lines, %d refs; CPL %d rows; excluded %d" % (len(fps), len(bom), len(bomrefs), len(cpl), len(excl)))
print("   BOM refs not in CPL: %s" % sorted(set(bomrefs) - set(cplrefs)))
print("   CPL refs not in BOM: %s" % sorted(set(cplrefs) - set(bomrefs)))
print("   board refs in neither BOM nor excluded: %s" % sorted(set(boardrefs) - set(bomrefs) - excl))
print("   BOM refs not on board: %s" % sorted(set(bomrefs) - set(boardrefs)))
print("   DNP on board but in BOM: %s" % sorted(r for r in bomrefs if boardrefs.get(r, {}).get('dnp')))
print("   LCSC per BOM line unique: %s" % (len({row['LCSC'] for row in bom}) == len(bom)))
# LCSC on board vs BOM
mism = [(r, boardrefs[r]['props'].get('LCSC'), c) for r, c in bomrefs.items() if r in boardrefs and boardrefs[r]['props'].get('LCSC') not in (None, '', c)]
print("   LCSC differs board vs BOM: %s" % mism[:10])
# CPL position vs board (native frame) for a few; and all rows
off = []
for r, row in cplrefs.items():
    f = boardrefs.get(r)
    if not f:
        continue
    x = float(row['Mid X'].replace('mm', '')); y = float(row['Mid Y'].replace('mm', ''))
    d = math.hypot(x - f['xy'][0], y - f['xy'][1])
    off.append((d, r, row['Layer'], row['Rotation'], f['angle']))
off.sort(reverse=True)
print("   CPL offsets from the board's footprint origin (largest 8; the datum moves are intended): %s" % [(round(d, 3), r, l) for d, r, l, rr, fa in off[:8]])
print("   CPL layers: %s" % collections.Counter(r['Layer'] for r in cpl))
