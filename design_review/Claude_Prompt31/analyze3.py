#!/usr/bin/env python3 -I
"""Third pass: the widest path (bottleneck) of the 5 V feeds through copper; the slot's via; vias in pads; paste on EPs."""
import pickle, math, os, collections, heapq
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
D = pickle.load(open(os.path.join(HERE, 'board.pkl'), 'rb'))
fps, segs, vias, zones = D['fps'], D['segs'], D['vias'], D['zones']
FP = {f['ref']: f for f in fps}
LAYERS = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']


def pad_poly(f, p):
    x, y = p['xy']; sx, sy = p['size']
    a = math.radians(p['angle'])
    if p['shape'] == 'circle':
        return Point(x, y).buffer(sx / 2)
    pts = [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]
    return Polygon([(x + px * math.cos(-a) - py * math.sin(-a), y + px * math.sin(-a) + py * math.cos(-a)) for px, py in pts])


def zone_polys(net, layer):
    out = []
    for z in zones:
        if z['net'] == net and layer in z['layers']:
            for fl, pts in z['filled']:
                if fl == layer and len(pts) >= 3:
                    pg = Polygon(pts)
                    if not pg.is_valid:
                        pg = pg.buffer(0)
                    out += list(pg.geoms) if pg.geom_type == 'MultiPolygon' else [pg]
    return out


def items_of(net):
    items = []
    for f in fps:
        for p in f['pads']:
            if p['net'] == net:
                lay = LAYERS if p['kind'] == 'thru_hole' else [l for l in LAYERS if l in p['layers']]
                items.append(dict(kind='pad', name='%s.%s' % (f['ref'], p['num']), layers=lay, g=pad_poly(f, p), w=9.0, xy=p['xy']))
    for s in segs:
        if s['net'] == net:
            items.append(dict(kind='track', name='%s w%.2f' % (s['layer'], s['w']), layers=[s['layer']], g=LineString([s['a'], s['b']]).buffer(s['w'] / 2, cap_style=1), w=s['w'],
                              xy=((s['a'][0] + s['b'][0]) / 2, (s['a'][1] + s['b'][1]) / 2), L=math.hypot(s['b'][0] - s['a'][0], s['b'][1] - s['a'][1])))
    for v in vias:
        if v['net'] == net:
            items.append(dict(kind='via', name='via', layers=LAYERS, g=Point(v['xy']).buffer(v['size'] / 2), w=0.45, xy=v['xy']))
    for L in LAYERS:
        for pg in zone_polys(net, L):
            items.append(dict(kind='fill', name='fill ' + L, layers=[L], g=pg, w=9.0, xy=(pg.centroid.x, pg.centroid.y), area=pg.area))
    adj = collections.defaultdict(set)
    for L in LAYERS:
        idx = [i for i, it in enumerate(items) if L in it['layers']]
        geoms = [items[i]['g'] for i in idx]
        tree = STRtree(geoms)
        byid = {id(g): i for g, i in zip(geoms, idx)}
        for k, i in enumerate(idx):
            for g in tree.query(geoms[k]):
                j = byid[id(g)]
                if j != i and geoms[k].intersects(g):
                    adj[i].add(j); adj[j].add(i)
    return items, adj


def widest_path(items, adj, src, dst):
    """max over paths of min item width; a via counts 0.45 (one via ~ a 0.45 mm track for current: 0.25 mm drill, 25 um plating = 20 um x 0.785 mm = like a 0.45 x 35 um track)."""
    best = {src: 9.0}
    prev = {}
    pq = [(-9.0, src)]
    while pq:
        w, i = heapq.heappop(pq)
        w = -w
        if i == dst:
            break
        if w < best.get(i, 0):
            continue
        for j in adj[i]:
            nw = min(w, items[j]['w'])
            if nw > best.get(j, 0):
                best[j] = nw; prev[j] = i
                heapq.heappush(pq, (-nw, j))
    if dst not in best:
        return None, []
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return best[dst], path[::-1]


def find(items, name):
    return next(i for i, it in enumerate(items) if it['name'] == name)


def describe(items, path):
    out = []
    for i in path:
        it = items[i]
        if it['kind'] == 'track':
            out.append('%s %.1fmm' % (it['name'], it['L']))
        elif it['kind'] == 'fill':
            out.append('%s %.0fmm2' % (it['name'], it['area']))
        elif it['kind'] == 'via':
            out.append('via(%.1f,%.1f)' % it['xy'])
        else:
            out.append(it['name'])
    # compress runs of equal names
    comp = []
    for o in out:
        if comp and comp[-1][0] == o:
            comp[-1][1] += 1
        else:
            comp.append([o, 1])
    return ' > '.join(o if n == 1 else '%s x%d' % (o, n) for o, n in comp)


print("=" * 100 + "\nWIDEST PATH (the bottleneck width, mm) of the supply feeds through copper")
for net, src, dsts in (("+5V_RF", "FB301.2", ["U104.6", "U104.13", "U104.24", "U201.18", "U201.24", "L103.1", "L104.1", "L201.1", "U507.5", "C304.1", "C303.1"]),
                       ("+5V_IN", "Q301.2", ["FB301.1", "U303.1", "U304.1", "U305.1", "U301.1", "U302.1", "Q302.2", "C320.1"]),
                       ("+5V_RF", "FB301.2", ["fill In2.Cu"]),
                       ("+5V_HDR", "J302.2", ["JP301.1", "JP301.2", "R303.1"]),
                       ("+3V3_PLL_RX", "U302.5", ["U115.17", "U115.6", "U115.28"]), ("+3V3_PLL_TX", "U301.5", ["U203.17", "U203.6", "U203.28"]),
                       ("+3V3_ANA", "U303.5", ["U105.5", "U106.5", "U501.5", "U502.5", "U102.2"]), ("+3V3_DIG", "U304.5", ["U605.1", "U107.5", "U601.6", "U113.5"]),
                       ("+3V3_OSC", "U305.5", ["Y101.4", "Y201.4"])):
    items, adj = items_of(net)
    try:
        s = find(items, src)
    except StopIteration:
        print("  %s: no pad %s; pads: %s" % (net, src, sorted({it['name'] for it in items if it['kind'] == 'pad'})[:20])); continue
    for d in dsts:
        try:
            t = find(items, d)
        except StopIteration:
            continue
        w, path = widest_path(items, adj, s, t)
        if w is None:
            print("  %-12s %s -> %s: NO PATH" % (net, src, d)); continue
        print("  %-12s %-8s -> %-8s bottleneck %.2f mm: %s" % (net, src, d, w, describe(items, path)[:400]))

# Q301/Q302 pins
for ref in ("Q301", "Q302", "F301", "F302", "FB301", "JP301", "J301"):
    f = FP.get(ref)
    if f:
        print("   %s %s pads %s" % (ref, f['props'].get('Value'), [(p['num'], (p['net'] or '')[:22]) for p in f['pads']]))

# ------------------------------------------------------------------ H304 slot vs via, precisely
print("\n" + "=" * 100 + "\nH304 slot (5.2 x 3.2 oval) to the nearest copper")
f = FP['H304']
p = f['pads'][0]
a = math.radians(p['angle'])
cx, cy = p['xy']
L_, W_ = 5.2, 3.2
# oval along x in the footprint frame, rotated by the pad angle
ax = (math.cos(-a), math.sin(-a))
seg = LineString([(cx - ax[0] * (L_ - W_) / 2, cy - ax[1] * (L_ - W_) / 2), (cx + ax[0] * (L_ - W_) / 2, cy + ax[1] * (L_ - W_) / 2)])
slot = seg.buffer(W_ / 2)
for v in vias:
    d = slot.distance(Point(v['xy'])) - v['size'] / 2
    if d < 0.6:
        print("   via %s at (%.2f,%.2f): copper edge %.3f mm from the slot's wall; drill wall %.3f" % (v['net'][:20], *v['xy'], d, slot.distance(Point(v['xy'])) - v['drill'] / 2))
for s in segs:
    d = slot.distance(LineString([s['a'], s['b']])) - s['w'] / 2
    if d < 0.6:
        print("   track %s %s w%.2f: copper %.3f mm from the slot's wall" % (s['net'][:20], s['layer'], s['w'], d))
for L in LAYERS:
    for net in ('GND', '+3V3_PLL_RX', '+5V_RF', '+3V3_DIG', '+3V3_ANA'):
        for pg in zone_polys(net, L):
            d = slot.distance(pg)
            if d < 0.6:
                print("   fill %s %s: %.3f mm from the slot's wall" % (net, L, d))
for ref in ("H301", "H302", "H303"):
    f = FP[ref]; c = Point(f['xy'])
    dmin = 9
    what = ''
    for L in LAYERS:
        for net in ('GND',):
            for pg in zone_polys(net, L):
                d = pg.distance(c) - 1.6
                if d < dmin:
                    dmin, what = d, 'fill %s %s' % (net, L)
    for v in vias:
        d = Point(v['xy']).distance(c) - 1.6 - v['size'] / 2
        if d < dmin:
            dmin, what = d, 'via ' + v['net']
    print("   %s: nearest copper %.2f mm from the hole wall (%s)" % (ref, dmin, what))

# ------------------------------------------------------------------ vias inside SMD pads (not EPs) and under 0402s
print("\n" + "=" * 100 + "\nVIAS inside SMD pads (via-in-pad) other than exposed pads; and vias whose copper touches a pad of another net")
for f in fps:
    for p in f['pads']:
        if p['kind'] != 'smd':
            continue
        g = pad_poly(f, p)
        for v in vias:
            d = g.distance(Point(v['xy']))
            if d < v['size'] / 2:
                big = min(p['size']) >= 1.2
                if v['net'] == p['net'] and big:
                    continue
                print("   %s.%s (%s, %.2fx%.2f) net %s: via %s at (%.2f,%.2f) overlaps by %.2f mm%s" % (f['ref'], p['num'], f['name'][:20], *p['size'], (p['net'] or '')[:16], v['net'][:16], *v['xy'], v['size'] / 2 - d, '' if v['net'] == p['net'] else '  OTHER NET'))

# ------------------------------------------------------------------ paste on the exposed pads
print("\n" + "=" * 100 + "\nPASTE on exposed pads (F.Paste pads inside each EP)")
for f in fps:
    eps = [p for p in f['pads'] if p['kind'] == 'smd' and min(p['size']) >= 1.2 and 'F.Cu' in p['layers']]
    for ep in eps:
        paste = [q for q in f['pads'] if 'F.Paste' in q['layers'] and q['num'] == ep['num']]
        area = sum(q['size'][0] * q['size'][1] for q in paste if 'F.Cu' not in q['layers']) or (ep['size'][0] * ep['size'][1] if 'F.Paste' in ep['layers'] else 0)
        print("   %-6s pad %s %.2fx%.2f: paste-only pads %d, paste area %.2f mm2 = %.0f %% of the pad%s" % (f['ref'], ep['num'], *ep['size'], len([q for q in paste if 'F.Cu' not in q['layers']]), area, 100 * area / (ep['size'][0] * ep['size'][1]), '' if area else '  NO PASTE'))

print("\n-- +5V_RF In2 tracks and the vias off the pour near FB301")
for s_ in segs:
    if s_['net'] == '+5V_RF' and s_['layer'] == 'In2.Cu':
        print("   In2 w%.2f (%.2f,%.2f)-(%.2f,%.2f) L%.2f" % (s_['w'], *s_['a'], *s_['b'], math.hypot(s_['b'][0]-s_['a'][0], s_['b'][1]-s_['a'][1])))
for v in vias:
    if v['net'] == '+5V_RF' and v['xy'][0] > 85:
        print("   via +5V_RF at (%.2f,%.2f)" % v['xy'])
for s_ in segs:
    if s_['net'] == '+5V_RF' and s_['a'][0] > 85:
        print("   %s w%.2f (%.2f,%.2f)-(%.2f,%.2f)" % (s_['layer'], s_['w'], *s_['a'], *s_['b']))
