#!/usr/bin/env python3 -I
"""Second pass: true copper connectivity of GND and the supply nets (pads, tracks, vias, fill pieces, pours),
the pours' bottlenecks from their real sources, real split crossings, via pairs, the ADL5611 tabs, silk sizes."""
import pickle, math, os, re, collections
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
from shapely.strtree import STRtree
import numpy as np
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
D = pickle.load(open(os.path.join(HERE, 'board.pkl'), 'rb'))
fps, segs, vias, zones, gr = D['fps'], D['segs'], D['vias'], D['zones'], D['gr']
FP = {f['ref']: f for f in fps}
LAYERS = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']


def pad_poly(f, p):
    x, y = p['xy']; sx, sy = p['size']
    a = math.radians(p['angle'])
    if p['shape'] == 'circle':
        return Point(x, y).buffer(sx / 2)
    pts = [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]
    return Polygon([(x + px * math.cos(-a) - py * math.sin(-a), y + px * math.sin(-a) + py * math.cos(-a)) for px, py in pts])


def seg_line(s):
    return LineString([s['a'], s['b']])


def zone_polys(net, layer):
    out = []
    for z in zones:
        if z['net'] == net and layer in z['layers']:
            for fl, pts in z['filled']:
                if fl == layer and len(pts) >= 3:
                    pg = Polygon(pts)
                    if not pg.is_valid:
                        pg = pg.buffer(0)
                    if pg.geom_type == 'MultiPolygon':
                        out += list(pg.geoms)
                    else:
                        out.append(pg)
    return out


class UF:
    def __init__(s, n):
        s.p = list(range(n))

    def f(s, i):
        while s.p[i] != i:
            s.p[i] = s.p[s.p[i]]; i = s.p[i]
        return i

    def u(s, a, b):
        a, b = s.f(a), s.f(b)
        if a != b:
            s.p[a] = b


def connectivity(net):
    """Items of one net with geometry per layer; union-find by intersection.  Returns items, uf."""
    items = []   # (kind, name, layers(list), geom)
    for f in fps:
        for p in f['pads']:
            if p['net'] != net:
                continue
            g = pad_poly(f, p)
            if p['kind'] == 'thru_hole':
                lay = LAYERS
            else:
                lay = [l for l in LAYERS if l in p['layers']]
            items.append(('pad', '%s.%s' % (f['ref'], p['num']), lay, g))
    for s in segs:
        if s['net'] == net:
            items.append(('track', '', [s['layer']], seg_line(s).buffer(s['w'] / 2, cap_style=1)))
    for v in vias:
        if v['net'] == net:
            items.append(('via', '', LAYERS, Point(v['xy']).buffer(v['size'] / 2)))
    for L in LAYERS:
        for pg in zone_polys(net, L):
            items.append(('fill', L, [L], pg))
    uf = UF(len(items))
    for L in LAYERS:
        idx = [i for i, it in enumerate(items) if L in it[2]]
        geoms = [items[i][3] for i in idx]
        tree = STRtree(geoms)
        for k, i in enumerate(idx):
            for g in tree.query(geoms[k]):
                j = idx[geoms.index(g)] if False else None
            # shapely 1.8: query returns geometries; map by id
        # slower but safe: index map by id()
        byid = {id(g): i for g, i in zip(geoms, idx)}
        for k, i in enumerate(idx):
            for g in tree.query(geoms[k]):
                j = byid[id(g)]
                if j > i and geoms[k].intersects(g):
                    uf.u(i, j)
    return items, uf


def report_net(net, show_pads=True):
    items, uf = connectivity(net)
    clusters = collections.defaultdict(list)
    for i, it in enumerate(items):
        clusters[uf.f(i)].append(it)
    big = max(clusters.values(), key=lambda c: sum(1 for it in c if it[0] == 'pad'))
    npads = sum(1 for it in items if it[0] == 'pad')
    print("  %-14s %d items, %d pads, %d clusters; the main cluster has %d pads" % (net, len(items), npads, len(clusters), sum(1 for it in big if it[0] == 'pad')))
    for key, c in clusters.items():
        if c is big:
            continue
        pads = [it[1] for it in c if it[0] == 'pad']
        kinds = collections.Counter(it[0] for it in c)
        if pads or kinds.get('via'):
            g = unary_union([it[3] for it in c])
            print("     SEPARATE cluster: pads %s, %s, at (%.1f,%.1f) area %.2f mm2" % (pads, dict(kinds), g.centroid.x, g.centroid.y, g.area))
    return items, uf, clusters, big


print("=" * 100 + "\nA. COPPER CONNECTIVITY by net (pads + tracks + vias + fills; a pad outside the main cluster is unconnected)")
for net in ["GND", "+5V_RF", "+5V_IN", "+5V_HDR", "+3V3_ANA", "+3V3_DIG", "+3V3_PLL_RX", "+3V3_PLL_TX", "+3V3_OSC"]:
    report_net(net)
# all other nets: pads clusters (no fills)
print("\n-- every other net: pads in more than one cluster")
nets = sorted({p['net'] for f in fps for p in f['pads'] if p['net'] and not p['net'].startswith('unconnected')})
bad = 0
for net in nets:
    if net == 'GND' or net.startswith('+'):
        continue
    items, uf = connectivity(net)
    roots = {uf.f(i) for i, it in enumerate(items) if it[0] == 'pad'}
    if len(roots) > 1:
        bad += 1
        groups = collections.defaultdict(list)
        for i, it in enumerate(items):
            if it[0] == 'pad':
                groups[uf.f(i)].append(it[1])
        print("   %-40s %d pieces: %s" % (net, len(roots), list(groups.values())))
print("   %d nets in pieces" % bad)

# ------------------------------------------------------------------ pours' bottleneck from the real source
print("\n" + "=" * 100 + "\nB. POURS: narrowest width from the source to each via of the net")
POURS = {z['net']: unary_union(zone_polys(z['net'], 'In2.Cu')) for z in zones if z['net'].startswith('+')}
padxy = {(f['ref'], p['num']): p['xy'] for f in fps for p in f['pads']}
padnet = {(f['ref'], p['num']): p['net'] for f in fps for p in f['pads']}


def bottleneck(pour, src_pts, dst_pts, res=0.1):
    minx, miny, maxx, maxy = pour.bounds
    nx, ny = int((maxx - minx) / res) + 3, int((maxy - miny) / res) + 3
    mask = np.zeros((ny, nx), bool)
    xs = minx + (np.arange(nx)) * res - res
    ys = miny + (np.arange(ny)) * res - res
    for j, y in enumerate(ys):
        row = LineString([(minx - res, y), (maxx + res, y)]).intersection(pour)
        if row.is_empty:
            continue
        parts = list(row.geoms) if hasattr(row, 'geoms') else [row]
        for part in parts:
            x0, x1 = part.bounds[0], part.bounds[2]
            i0, i1 = int(round((x0 - xs[0]) / res)), int(round((x1 - xs[0]) / res))
            mask[j, max(0, i0):min(nx, i1 + 1)] = True
    dist = ndimage.distance_transform_edt(mask) * res

    def cell(pt):
        return (int(round((pt[1] - ys[0]) / res)), int(round((pt[0] - xs[0]) / res)))

    def inside(c):
        return 0 <= c[0] < ny and 0 <= c[1] < nx and mask[c]
    srcs = [cell(s) for s in src_pts if inside(cell(s))]
    out = {}
    for name, pt in dst_pts:
        c = cell(pt)
        if not inside(c):
            out[name] = None; continue
        lo, hi = 0.0, float(dist.max())
        for _ in range(12):
            mid = (lo + hi) / 2
            lab, n = ndimage.label(dist >= mid)
            if any(lab[s] and lab[s] == lab[c] for s in srcs):
                lo = mid
            else:
                hi = mid
        out[name] = 2 * lo
    return out, srcs


SOURCES = {"+5V_RF": ["FB301"], "+3V3_ANA": ["U303"], "+3V3_DIG": ["U304"], "+3V3_PLL_RX": ["U302"], "+3V3_PLL_TX": ["U301"], "+5V_IN": ["Q301", "Q302", "J301", "F301"]}
for net, pour in POURS.items():
    vv = [v for v in vias if v['net'] == net]
    srefs = SOURCES.get(net, [])
    spads = [padxy[k] for k, n in padnet.items() if n == net and k[0] in srefs]
    # the source vias: the vias of the net nearest each source pad (within 6 mm), plus any via the source pad's track reaches
    src = []
    for sp in spads:
        near = sorted(vv, key=lambda v: math.hypot(v['xy'][0] - sp[0], v['xy'][1] - sp[1]))[:3]
        src += [v['xy'] for v in near if math.hypot(v['xy'][0] - sp[0], v['xy'][1] - sp[1]) < 8]
    print("  %-12s pour area %.0f mm2, %d vias, source pads %s at %s -> %d source vias %s" % (net, pour.area, len(vv), srefs, [tuple(round(c, 1) for c in s) for s in spads], len(src), [tuple(round(c, 1) for c in s) for s in src]))
    if not src:
        continue
    bn, srcs = bottleneck(pour, src, [("(%.1f,%.1f)" % v['xy'], v['xy']) for v in vv])
    over = {n: w for n, w in bn.items() if w is not None}
    notover = [n for n, w in bn.items() if w is None]
    worst = sorted(over.items(), key=lambda t: t[1])[:8]
    print("     %d vias over the pour; narrowest widths: %s" % (len(over), ', '.join('%s %.1f' % (n, w) for n, w in worst)))
    print("     %d vias NOT over the pour (fed by tracks): %s" % (len(notover), notover[:12]))

# where does each load of +5V_RF get its current: via over the pour or tracks?
print("\n-- +5V_RF: the big loads' supply pins and how they reach the pour")
for ref, pins in (("U104", ("6", "13", "24")), ("U201", ("18", "24")), ("L103", ("1", "2")), ("L104", ("1", "2")), ("L201", ("1", "2")), ("FB301", ("1", "2"))):
    for num in pins:
        k = (ref, num)
        if padnet.get(k) != '+5V_RF':
            continue
        xy = padxy[k]
        vv = sorted([v for v in vias if v['net'] == '+5V_RF'], key=lambda v: math.hypot(v['xy'][0] - xy[0], v['xy'][1] - xy[1]))[:2]
        tr = [s for s in segs if s['net'] == '+5V_RF' and seg_line(s).distance(Point(xy)) < 0.4]
        print("   %s.%s at (%.1f,%.1f): nearest +5V_RF vias %s; tracks at the pad: %s" % (ref, num, *xy, [(round(v['xy'][0], 1), round(v['xy'][1], 1), 'over pour' if POURS['+5V_RF'].contains(Point(v['xy'])) else 'NOT over pour') for v in vv], [(s['layer'], s['w']) for s in tr]))

# the +5V_HDR and +5V_IN paths: width and length of each track
print("\n-- +5V_HDR / +5V_IN / +5V_RF tracks: length by width and layer")
for net in ("+5V_HDR", "+5V_IN", "+5V_RF"):
    L = collections.Counter()
    for s in segs:
        if s['net'] == net:
            L[(s['layer'], s['w'])] += math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1])
    print("   %-8s %s" % (net, ', '.join('%s w%.2f %.1f mm' % (k[0], k[1], v) for k, v in sorted(L.items()))))
    print("          pads: %s" % sorted({k[0] for k, n in padnet.items() if n == net}))

# ------------------------------------------------------------------ real split crossings
print("\n" + "=" * 100 + "\nC. B.Cu tracks crossing from one In2 region to another (pour to pour / pour to GND fill), per net")
IN2 = [(n, pg) for n, pg in POURS.items()] + [("GND_In2", unary_union(zone_polys('GND', 'In2.Cu')))]
tree_regions = [(n, pg) for n, pg in IN2]


def region(pt):
    P = Point(pt)
    for n, pg in tree_regions:
        if pg.contains(P):
            return n
    return None


def real_crossings(net):
    """along each B.Cu segment: the sequence of regions; count A -> (gap) -> B with A != B, and gaps longer than 0.8 mm"""
    n = 0; det = []
    for s in segs:
        if s['net'] != net or s['layer'] != 'B.Cu':
            continue
        L = math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1])
        k = max(2, int(L / 0.1) + 1)
        seq = []
        for i in range(k + 1):
            t = i / k
            pt = (s['a'][0] + t * (s['b'][0] - s['a'][0]), s['a'][1] + t * (s['b'][1] - s['a'][1]))
            seq.append((region(pt), pt))
        last = None; gap = 0
        for r, pt in seq:
            if r is None:
                gap += 1; continue
            if last is not None and r != last:
                n += 1; det.append((last, r, pt))
            elif last is not None and r == last and gap * 0.1 > 0.8:
                n += 1; det.append((last, 'gap %.1f mm' % (gap * 0.1), pt))
            last = r; gap = 0
    return n, det


rank = []
for net in nets:
    if net == 'GND' or net.startswith('+'):
        continue
    c, det = real_crossings(net)
    if c:
        rank.append((c, net, det))
rank.sort(key=lambda t: -t[0])
print("  %d nets with real crossings, %d crossings in all" % (len(rank), sum(r[0] for r in rank)))
for c, net, det in rank[:30]:
    print("  %2d  %-45s %s" % (c, net[:45], '; '.join('%s>%s(%.0f,%.0f)' % (a[:7], b[:7], *pt) for a, b, pt in det[:5])))
print("-- the comparator outputs' nets (through the 33R) specifically")
for ref in ("R120", "R134", "R221", "R222", "R519", "R520", "R521", "R603", "R607", "R611", "R615"):
    for p in FP[ref]['pads']:
        c, det = real_crossings(p['net'])
        Lb = sum(math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1]) for s in segs if s['net'] == p['net'] and s['layer'] == 'B.Cu')
        Lt = sum(math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1]) for s in segs if s['net'] == p['net'])
        print("   %s.%s %-32s total %5.1f mm, B.Cu %5.1f mm, real crossings %d: %s" % (ref, p['num'], p['net'][:32], Lt, Lb, c, '; '.join('%s>%s' % (a[:7], b[:7]) for a, b, pt in det[:6])))

# ------------------------------------------------------------------ via pairs, nets
print("\n" + "=" * 100 + "\nD. VIA PAIRS closer than 0.6 mm centre to centre (wall = c-c minus 0.25 drill)")
from scipy.spatial import cKDTree
vp = np.array([v['xy'] for v in vias])
tree = cKDTree(vp)
for i, j in sorted(tree.query_pairs(0.6)):
    d = math.hypot(*(vp[i] - vp[j]))
    print("   %.3f mm wall %.3f  %s / %s at (%.2f,%.2f)" % (d, d - 0.25, vias[i]['net'][:24], vias[j]['net'][:24], *vp[i]))
# via to THT hole
tht = [(f['ref'] + '.' + p['num'], p['xy'], p['drill'][0] if p['drill'] else 0) for f in fps for p in f['pads'] if p['kind'] in ('thru_hole', 'np_thru_hole') and p['drill']]
print("-- via drill to component hole walls under 0.3 mm")
for name, xy, dr in tht:
    dd, idx = tree.query(xy, k=3)
    for d_, i_ in zip(dd, idx):
        wall = d_ - dr / 2 - 0.125
        if wall < 0.3:
            print("   %s (drill %.2f) to via %s: wall %.3f mm" % (name, dr, vias[i_]['net'][:20], wall))

# ------------------------------------------------------------------ ADL5611 tabs
print("\n" + "=" * 100 + "\nE. ADL5611 (SOT-89) tabs: the custom pad polygon, GND vias in it and within 1 mm of it")
GNDV = [Point(v['xy']) for v in vias if v['net'] == 'GND']
for ref in ("U103", "U117", "U202"):
    f = FP[ref]
    a = math.radians(f['angle'])
    # the custom polygon in footprint coords: x 0.7375..3.8625 from the anchor at (-1.8625, 0) at pad angle 180 -> x from -1.125 to 2.0, y +-0.8665
    # pad at (-1.8625, 0) rotated 180: primitives are in the pad's frame, rotated by the pad's angle (180): x -> -x.  So absolute fp x = -1.8625 - (0.7375..3.8625) = -2.6..-5.725?  That cannot be (the body is 4.5 wide).
    # read both interpretations and report which lies under the body (|x| <= 2.5)
    for sign in (1, -1):
        pts = [(-1.8625 + sign * x, y) for x, y in ((3.8625, 0.8665), (0.7375, 0.8665), (0.7375, -0.8665), (3.8625, -0.8665))]
        abs_pts = [(f['xy'][0] + px * math.cos(-a) - py * math.sin(-a), f['xy'][1] + px * math.sin(-a) + py * math.cos(-a)) for px, py in pts]
        pg = Polygon(abs_pts)
        n_in = sum(1 for q in GNDV if pg.contains(q))
        n_near = sum(1 for q in GNDV if pg.distance(q) < 1.0)
        print("   %s tab polygon (sign %+d): x %.2f..%.2f (fp frame) -> board (%.1f,%.1f)-(%.1f,%.1f): %d GND vias inside, %d within 1 mm" % (
            ref, sign, min(p[0] for p in pts), max(p[0] for p in pts), *pg.bounds, n_in, n_near))
    leads = [p for p in f['pads']]
    print("   %s pads: %s" % (ref, [(p['num'], tuple(round(c, 2) for c in p['xy']), p['net'][:14]) for p in leads]))
    # nearest GND vias to the tab centre (pad 2's position)
    p2 = next(p for p in f['pads'] if p['num'] == '2')
    ds = sorted(q.distance(Point(p2['xy'])) for q in GNDV)[:6]
    print("   %s nearest GND vias to the pad-2 anchor: %s" % (ref, [round(d, 2) for d in ds]))

# ------------------------------------------------------------------ silk text sizes
print("\n" + "=" * 100 + "\nF. SILK text sizes (height, thickness) histogram, F.SilkS and B.SilkS")
hist = collections.Counter()
for f in fps:
    for t in f['texts']:
        if t['layer'] in ('F.SilkS', 'B.SilkS') and t['size']:
            hist[(t['layer'], t['size'][1], t['thick'])] += 1
for g in gr:
    if g['kind'] == 'text' and g['layer'] in ('F.SilkS', 'B.SilkS'):
        hist[(g['layer'], g['size'][1], g['thick'])] += 1
for k, v in sorted(hist.items()):
    print("   %s h%.2f t%s: %d" % (k[0], k[1], k[2], v))
# B.SilkS texts: mirrored?  list a few
print("-- B.SilkS texts: %s" % [g['text'][:30] for g in gr if g['kind'] == 'text' and g['layer'] == 'B.SilkS'][:12])

# ------------------------------------------------------------------ T101 / TDK fit
print("\n" + "=" * 100 + "\nG. The balun's neighbourhood: copper within 1.5 mm of T101's centre (for the TDK 1.0x0.5 swap)")
c = Point(FP['T101']['xy'])
for f in fps:
    for p in f['pads']:
        if f['ref'] != 'T101' and pad_poly(f, p).distance(c) < 1.6:
            print("   pad %s.%s net %s at (%.2f,%.2f) size %s" % (f['ref'], p['num'], p['net'][:20], *p['xy'], p['size']))
for v in vias:
    if Point(v['xy']).distance(c) < 1.6:
        print("   via %s at (%.2f,%.2f)" % (v['net'][:20], *v['xy']))
for s in segs:
    if seg_line(s).distance(c) < 1.6:
        print("   track %s %s w%.2f (%.2f,%.2f)-(%.2f,%.2f)" % (s['net'][:20], s['layer'], s['w'], *s['a'], *s['b']))
