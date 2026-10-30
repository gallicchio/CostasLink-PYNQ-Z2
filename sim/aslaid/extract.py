"""From the written board to a circuit: every track of the chosen nets as a transmission line (its own width,
gap and reference plane, sampled every 0.1 mm), every junction a node (so a branch is a stub), every pad a
node with its capacitance to the plane under it, every via an inductance, every passive between its pads with
its model and its ground return.  ICs and ports are added by the caller at the pads' nodes ("P:U101.3").
"""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "sim"))
import geom as G
import circuit as C
import devices as D
import rf_lines as RL

H1 = 0.2104                 # L1 to In1
H2 = 0.2104 + 1.065         # L1 to In2 (through In1's void)
HB = 1.6
EPS = 8.854187817e-12
ER = 4.4

_B = None
EXTRA_GND = {}          # ref -> extra ground inductance (H), for the sensitivity sweeps


def board():
    global _B
    if _B is None:
        _B = G.load()
        _B["gnd_vias"] = np.array([(v[0], v[1]) for v in _B["via"] if v[4] == "GND"] +
                                  [(p["x"], p["y"]) for p in _B["pad"] if p["net"] == "GND" and p["drill"] > 0])
        bom = {}
        import csv
        for row in csv.reader(open(os.path.join(ROOT, "mfg", "release", "BOM_JLCPCB.csv"))):
            if len(row) >= 4:
                for r in row[1].split(","):
                    bom[r.strip()] = row
        _B["bom"] = bom
    return _B


# ---- the line table: Z0 and eps_eff from the 2D field solver, cached ----
_TAB = None
WIDTHS = [0.15, 0.2, 0.25, 0.29, 0.35, 0.4, 0.5, 0.6]
GAPS = [0.15, 0.2, 0.25, 0.3, 0.4, 0.6, 1.0, 9.0]       # 9 = no coplanar ground (microstrip)


def table():
    global _TAB
    if _TAB is not None:
        return _TAB
    path = os.path.join(HERE, "line_table.json")
    if os.path.exists(path):
        _TAB = json.load(open(path))
        return _TAB
    import xsec as X
    rows = []
    for w in WIDTHS:
        for g in GAPS:
            z, e = X.line(w, g, coplanar=g < 5)
            rows.append((w, g, z, e))
            print("table w %.2f gap %.2f: %.1f ohm eps %.2f" % (w, g, z, e), flush=True)
    _TAB = {"rows": rows, "note": "xsec.py, dx 8.75 um, no solder mask"}
    json.dump(_TAB, open(path, "w"), indent=0)
    return _TAB


def z0_eeff(w, gap, h=H1):
    """Z0, eps_eff for width w and gap (to the L1 pour) over a plane h below"""
    if abs(h - H1) > 1e-3:
        z, e = RL.microstrip_z0(w, h=h, er=4.5)
        return z, e
    rows = table()["rows"]
    g = min(max(gap, GAPS[0]), GAPS[-1]) if gap < 3 else 9.0
    ws = sorted(set(r[0] for r in rows))
    w = min(max(w, ws[0]), ws[-1])
    # bilinear in (w, log gap)
    def at(wv, gv):
        for r in rows:
            if abs(r[0] - wv) < 1e-9 and abs(r[1] - gv) < 1e-9:
                return r[2], r[3]
    wl = max(x for x in ws if x <= w + 1e-12)
    wh = min(x for x in ws if x >= w - 1e-12)
    gl = max(x for x in GAPS if x <= g + 1e-12)
    gh = min(x for x in GAPS if x >= g - 1e-12)
    tw = 0 if wh == wl else (w - wl) / (wh - wl)
    tg = 0 if gh == gl else (math.log(g) - math.log(gl)) / (math.log(gh) - math.log(gl))
    z = e = 0.0
    for wv, a in ((wl, 1 - tw), (wh, tw)):
        for gv, b in ((gl, 1 - tg), (gh, tg)):
            zz, ee = at(wv, gv)
            z += a * b * zz
            e += a * b * ee
    return z, e


# ---- geometry helpers ----
def fills(layer, net=None):
    B = board()
    out = []
    for (l, n), P in B["fill"].items():
        if l == layer and (net is None or n == net):
            out += P
    return out


def local_polys(polys, x0, y0, x1, y1):
    return [P for P in polys if not (P[:, 0].max() < x0 or P[:, 0].min() > x1 or P[:, 1].max() < y0 or P[:, 1].min() > y1)]


def ref_at(pts, layer):
    """per point: (h to the nearest plane under it, the plane's net)"""
    order = {"F.Cu": [("In1.Cu", H1), ("In2.Cu", H2), ("B.Cu", HB)],
             "B.Cu": [("In2.Cu", H1), ("In1.Cu", H2), ("F.Cu", HB)],
             "In1.Cu": [("F.Cu", H1), ("In2.Cu", 1.065)],
             "In2.Cu": [("B.Cu", H1), ("In1.Cu", 1.065)]}[layer]
    x0, y0 = pts.min(0) - 1
    x1, y1 = pts.max(0) + 1
    out = [(None, None)] * len(pts)
    left = np.ones(len(pts), bool)
    for lay, h in order:
        B = board()
        for (l, n), P in B["fill"].items():
            if l != lay:
                continue
            Pl = local_polys(P, x0, y0, x1, y1)
            if not Pl:
                continue
            ins = G.inside(pts, Pl) & left
            for i in np.nonzero(ins)[0]:
                out[i] = (h, n)
            left &= ~ins
        if not left.any():
            break
    return out


def gnd_return_L(p):
    """the inductance from a ground pad to the In1 plane: vias in the pad, else through the pour to the
    nearest vias (0.264 nH a square at 0.21 mm over the plane), else through its track"""
    B = board()
    gv = B["gnd_vias"]
    P = G.pad_poly(p)
    inpad = G.inside(gv, [P]).sum() if len(gv) else 0
    lvia = 0.09e-9
    if inpad:
        return lvia / inpad, "%d via(s) in the pad" % inpad
    d = np.sqrt(((gv - (p["x"], p["y"])) ** 2).sum(1))
    half = 0.5 * max(p["sx"], p["sy"])
    near = np.sort(d)[:3]
    W = max(0.25, min(p["sx"], p["sy"]))
    paths = [0.264e-9 * max(dd - half, 0.05) / W + lvia for dd in near]
    L = 1.0 / sum(1.0 / x for x in paths)
    return L, "pour to vias %.2f/%.2f/%.2f mm off (centre)" % tuple(near)


def pad_cap(p, h):
    a = p["sx"] * p["sy"] * (math.pi / 4 if p["shape"] == "circle" else 1.0)
    return EPS * ER * 1.2 * a * 1e-6 / (h * 1e-3)


# ---- the extraction ----
class UF:
    def __init__(self):
        self.p = {}

    def f(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def u(self, a, b):
        a, b = self.f(a), self.f(b)
        if a != b:
            # keep pad / named nodes as the representative
            if b.startswith("P:"):
                a, b = b, a
            self.p[b] = a


def extract(c, nets, skip_parts=(), supply_node=None, log=None, sample=0.1, ideal=(), no_padcap=False):
    """add the copper of `nets` to circuit c.  supply_node(net, x, y) -> node name for a part's pad on a
    supply net (or None to skip the part).  Returns a dict: node names of each pad, the lines (for reports),
    the parts added."""
    B = board()
    nets = set(nets)
    segs = [list(s) for s in B["seg"] if s[6] in nets]
    vias = [v for v in B["via"] if v[4] in nets]
    pads = [p for p in B["pad"] if p["net"] in nets and (p["layers"] and any("Cu" in l for l in p["layers"]))]
    # split segments at T-junctions
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(segs):
            for (xa, ya, xb, yb, w, l, n) in [tuple(t) for t in segs]:
                for (px, py) in ((xa, ya), (xb, yb)):
                    if l != s[5] or n != s[6]:
                        continue
                    x0, y0, x1, y1 = s[:4]
                    L = math.dist((x0, y0), (x1, y1))
                    if L < 1e-6:
                        continue
                    t = ((px - x0) * (x1 - x0) + (py - y0) * (y1 - y0)) / L ** 2
                    if 0.02 < t * L < L - 0.02:
                        qx, qy = x0 + t * (x1 - x0), y0 + t * (y1 - y0)
                        if math.dist((qx, qy), (px, py)) < min(w, s[4]) / 2:
                            segs[i] = [x0, y0, qx, qy, s[4], s[5], s[6]]
                            segs.append([qx, qy, x1, y1, s[4], s[5], s[6]])
                            changed = True
                            break
                if changed:
                    break
            if changed:
                break
    uf = UF()

    def key(l, x, y):
        return "%s@%.3f,%.3f" % (l, x, y)
    ends = []
    for s in segs:
        for (x, y) in ((s[0], s[1]), (s[2], s[3])):
            ends.append((s[5], x, y, s[4]))
    # merge coincident ends
    for i, (l, x, y, w) in enumerate(ends):
        for (l2, x2, y2, w2) in ends[i + 1:]:
            if l == l2 and math.dist((x, y), (x2, y2)) < 0.01:
                uf.u(key(l, x, y), key(l2, x2, y2))
    padnode = {}
    padpoly = []
    for p in pads:
        nm = "P:%s.%s" % (p["ref"], p["num"])
        if nm in padnode.values():
            nm = nm + "_%d" % len(padnode)
        padnode[id(p)] = nm
        uf.f(nm)
        padpoly.append((p, G.pad_poly(p), nm))
        for (l, x, y, w) in ends:
            if (l in p["layers"] or p["drill"] > 0) and (G.inside(np.array([[x, y]]), [padpoly[-1][1]])[0]
                                                         or math.dist((x, y), (p["x"], p["y"])) < 0.02):
                uf.u(nm, key(l, x, y))
    # pads of one part number joined (an exposed pad in pieces, an SMA's four legs) are one node already by net
    viainfo = []
    for k, v in enumerate(vias):
        vx, vy, size, drill, n, lays = v
        top, bot = "V%d:F" % k, "V%d:B" % k
        hit = set()
        for (l, x, y, w) in ends:
            if math.dist((x, y), (vx, vy)) < size / 2 + 0.01:
                uf.u(top if l == "F.Cu" else bot, key(l, x, y))
                hit.add(l)
        viainfo.append((top, bot, v, hit))
    # node names after merging
    def N(a):
        return uf.f(a)
    lines = []
    for s in segs:
        x0, y0, x1, y1, w, l, n = s
        L = math.dist((x0, y0), (x1, y1))
        if L < 1e-6:
            continue
        a, b = N(key(l, x0, y0)), N(key(l, x1, y1))
        k = max(1, int(math.ceil(L / sample)))
        t = (np.arange(k) + 0.5) / k
        pts = np.c_[x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]
        # samples inside the net's own pads are the pad's
        inp = np.zeros(len(pts), bool)
        for p, P, nm in padpoly:
            if l in p["layers"] or p["drill"] > 0:
                inp |= G.inside(pts, [P])
        refs = ref_at(pts, l)
        same = l
        bx0, by0 = pts.min(0) - 2
        bx1, by1 = pts.max(0) + 2
        E = G.edges(local_polys(fills(same, "GND"), bx0, by0, bx1, by1), (bx0, by0, bx1, by1))
        gaps = G.dist_to_edges(pts, E) - w / 2
        # walk the samples, a line section per run of the same reference
        seg_nodes = [a]
        cur = None
        run = []
        def flush(run, na, nb):
            if not run:
                return
            length = sample * len(run) * L / (sample * k)
            hs = [r[0] for r in run]
            h = max(set(hs), key=hs.count)
            gap = float(np.median([r[1] for r in run]))
            if h is None:
                # no plane under it on any layer: inside an SMA's launch void, which the launch's field-solved
                # fit (docs/LAUNCH.md) already covers: count it as the line it joins
                z, e = z0_eeff(w, 0.25, H1)
            else:
                z, e = z0_eeff(w, gap, h)
            C.add_tl(c, na, nb, z, e, length, w)
            lines.append(dict(net=n, layer=l, w=w, len=length, h=h, gap=gap, z0=z, eeff=e,
                              ref_net=max(set(r[2] for r in run), key=[r[2] for r in run].count)))
        runs = []
        for i in range(len(pts)):
            if inp[i]:
                continue
            h, rn = refs[i]
            tag = (h, rn)
            if cur is None or tag != cur:
                runs.append([])
                cur = tag
            runs[-1].append((h, gaps[i], rn))
        nodes = [a] + ["%s~%d_%d" % (n, len(lines), j) for j in range(len(runs) - 1)] + [b]
        if not runs:
            C.add_tl(c, a, b, 50.0, 3.0, 0.0)
        if n in ideal:
            c.y2(a, b, lambda f: 1e3)
            continue
        for j, r in enumerate(runs):
            flush(r, nodes[j], nodes[j + 1])
    # pads: capacitance to the plane under them
    for p, P, nm in padpoly:
        if p["drill"] > 0 or no_padcap or p["net"] in ideal:
            continue
        lay = "F.Cu" if "F.Cu" in p["layers"] else "B.Cu"
        h, rn = ref_at(np.array([[p["x"], p["y"]]]), lay)[0]
        cp = pad_cap(p, h or HB)
        c.y2(N(nm), "0", C.y_c(cp))
    # vias: barrel inductance, the reference change's return inductance
    for top, bot, v, hit in viainfo:
        vx, vy, size, drill, n, lays = v
        if len(hit) < 2:
            if hit:
                c.y2(N(top if "F.Cu" in hit else bot), "0", C.y_c(0.05e-12))   # a via stub: its pads' capacitance
            continue
        r = drill / 2
        lb = 0.2e-9 * 1.6 * (math.log(4 * 1.6 / drill) + 1)
        gv = board()["gnd_vias"]
        s = float(np.sort(np.sqrt(((gv - (vx, vy)) ** 2).sum(1)))[0]) if len(gv) else 5.0
        lret = 4e-7 * 1.065e-3 * math.log(max(s, 2 * r) / r)       # the return between In1 and In2 (two-via loop)
        ref2 = ref_at(np.array([[vx, vy]]), "B.Cu")[0][1]
        if ref2 not in (None, "GND"):
            lret += 1.0e-9                                           # In2 a supply plane: the return finds a capacitor
        c.z2(N(top), N(bot), C.z_l(lb + lret))
        c.notes.append("via %s at (%.2f, %.2f): barrel %.2f nH + return %.2f nH (In2 under it: %s)" % (n, vx, vy, lb * 1e9, lret * 1e9, ref2))
    # parts
    parts = []
    byref = {}
    for p in board()["pad"]:
        byref.setdefault(p["ref"], []).append(p)
    seen = set()
    for p in pads:
        ref = p["ref"]
        if ref in seen or ref in skip_parts or ref[0] not in "CLRF" or ref.startswith(("CP",)):
            continue
        seen.add(ref)
        pp = [q for q in byref[ref] if q["num"] in ("1", "2")]
        if len(pp) != 2:
            continue
        row = board()["bom"].get(ref)
        if row is None:
            parts.append((ref, "DNP: not fitted"))
            continue
        fx = board()["fp"][ref]
        zf, desc = D.part_z(ref, row[0], fx[4])
        ends2 = []
        for q in pp:
            if q["net"] in nets:
                ends2.append(N(padnode[id(q)]) if id(q) in padnode else None)
            elif q["net"] == "GND":
                Lg, why = gnd_return_L(q)
                Lg += EXTRA_GND.get(ref, 0.0)
                gn = "G:%s" % ref
                c.z2(gn, "0", C.z_l(Lg))
                ends2.append(gn)
                desc += "; ground %.2f nH (%s)" % (Lg * 1e9, why)
            else:
                sn = supply_node(q["net"], q["x"], q["y"], ref) if supply_node else None
                if sn is None:
                    ends2.append(None)
                else:
                    ends2.append(sn)
                    desc += "; to %s" % q["net"]
        if None in ends2:
            parts.append((ref, desc + " (one end not modelled: left out)"))
            continue
        c.z2(ends2[0], ends2[1], zf)
        parts.append((ref, desc))
    return dict(N=N, pad={("%s.%s" % (p["ref"], p["num"])): N(padnode[id(p)]) for p in pads}, lines=lines, parts=parts)
