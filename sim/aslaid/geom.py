"""Load the board file into flat lists (tracks, vias, pads, zone fills) for the layout checks in this directory."""
import math, os, sys, collections
import numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT + "/tools")
from sexp import parse, kids, kid, val, num, head

PCB = ROOT + "/hardware/CostasLink-PYNQ-Z2.kicad_pcb"


def netname(node):
    n = kid(node, "net")
    if n is None:
        return ""
    return val(n, 2) if len(n) > 2 else val(n)


def load(pcb=PCB):
    doc = parse(open(pcb, encoding="utf-8").read())[0]
    B = {"seg": [], "via": [], "pad": [], "fill": collections.defaultdict(list), "fp": {}}
    for s in kids(doc, "segment"):
        a, b = kid(s, "start"), kid(s, "end")
        B["seg"].append((num(a, 1), num(a, 2), num(b, 1), num(b, 2), num(kid(s, "width"), 1), val(kid(s, "layer")), netname(s)))
    for s in kids(doc, "arc"):
        a, m, b = kid(s, "start"), kid(s, "mid"), kid(s, "end")
        pts = [(num(a, 1), num(a, 2)), (num(m, 1), num(m, 2)), (num(b, 1), num(b, 2))]
        for p, q in zip(pts, pts[1:]):
            B["seg"].append((p[0], p[1], q[0], q[1], num(kid(s, "width"), 1), val(kid(s, "layer")), netname(s)))
    for v in kids(doc, "via"):
        at = kid(v, "at")
        L = kid(v, "layers")
        B["via"].append((num(at, 1), num(at, 2), num(kid(v, "size"), 1), num(kid(v, "drill"), 1), netname(v),
                         tuple(val(L, i) for i in range(1, len(L)))))
    for fp in kids(doc, "footprint"):
        ref = next((val(p, 2) for p in kids(fp, "property") if val(p) == "Reference"), "?")
        value = next((val(p, 2) for p in kids(fp, "property") if val(p) == "Value"), "?")
        at = kid(fp, "at")
        fx, fy = num(at, 1), num(at, 2)
        rot = num(at, 3) if len(at) > 3 else 0.0
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        B["fp"][ref] = (fx, fy, rot, value, val(fp), val(kid(fp, "layer")))
        for pad in kids(fp, "pad"):
            pat = kid(pad, "at")
            dx, dy = num(pat, 1), num(pat, 2)
            ang = num(pat, 3) if len(pat) > 3 else 0.0
            sz = kid(pad, "size")
            L = kid(pad, "layers")
            lays = tuple(val(L, i) for i in range(1, len(L)))
            dr = kid(pad, "drill")
            B["pad"].append(dict(ref=ref, num=val(pad, 1), x=fx + dx * c + dy * s, y=fy - dx * s + dy * c,
                                 sx=num(sz, 1), sy=num(sz, 2), ang=ang, shape=val(pad, 3), kind=val(pad, 2),
                                 layers=lays, net=netname(pad), drill=num(dr, 1) if dr is not None and len(dr) > 1 and val(dr, 1) != "oval" else 0.0))
    for z in kids(doc, "zone"):
        net = netname(z)
        for f in kids(z, "filled_polygon"):
            lay = val(kid(f, "layer"))
            pts = np.array([(num(p, 1), num(p, 2)) for p in kids(kid(f, "pts"), "xy")])
            B["fill"][(lay, net)].append(pts)
    return B


def pad_poly(p, n=16):
    """the pad's outline as an array of points (rects and roundrects as rects, circles/ovals approximated)"""
    sx, sy = p["sx"] / 2, p["sy"] / 2
    if p["shape"] in ("circle",):
        t = np.linspace(0, 2 * np.pi, n, endpoint=False)
        pts = np.c_[sx * np.cos(t), sx * np.sin(t)]
    else:
        pts = np.array([(-sx, -sy), (sx, -sy), (sx, sy), (-sx, sy)])
    a = math.radians(p["ang"])
    c, s = math.cos(a), math.sin(a)
    # KiCad: y down, angle counter-clockwise on screen
    R = np.array([[c, s], [-s, c]])
    return pts @ R.T + (p["x"], p["y"])


def edges(polys, box=None):
    """all polygon edges as an (n, 4) array, optionally only those touching box (x0, y0, x1, y1)"""
    out = []
    for P in polys:
        Q = np.roll(P, -1, axis=0)
        E = np.c_[P, Q]
        if box is not None:
            x0, y0, x1, y1 = box
            m = ~((np.maximum(E[:, 0], E[:, 2]) < x0) | (np.minimum(E[:, 0], E[:, 2]) > x1) |
                  (np.maximum(E[:, 1], E[:, 3]) < y0) | (np.minimum(E[:, 1], E[:, 3]) > y1))
            E = E[m]
        out.append(E)
    return np.vstack(out) if out else np.zeros((0, 4))


def dist_to_edges(pts, E):
    """distance from each point to the nearest edge"""
    if len(E) == 0:
        return np.full(len(pts), np.inf)
    ax, ay, bx, by = E[:, 0], E[:, 1], E[:, 2], E[:, 3]
    dx, dy = bx - ax, by - ay
    L2 = np.maximum(dx * dx + dy * dy, 1e-12)
    out = np.empty(len(pts))
    for i, (px, py) in enumerate(pts):
        t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
        qx, qy = ax + t * dx - px, ay + t * dy - py
        out[i] = np.sqrt((qx * qx + qy * qy).min())
    return out


def inside(pts, polys):
    """even-odd point in polygon against a set of (fractured) filled polygons"""
    res = np.zeros(len(pts), bool)
    for P in polys:
        x, y = P[:, 0], P[:, 1]
        xn, yn = np.roll(x, -1), np.roll(y, -1)
        for i, (px, py) in enumerate(pts):
            c = ((y > py) != (yn > py)) & (px < (xn - x) * (py - y) / np.where(yn - y == 0, 1e-12, yn - y) + x)
            if c.sum() % 2:
                res[i] = True
    return res
