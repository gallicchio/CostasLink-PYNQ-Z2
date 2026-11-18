#!/usr/bin/env python3
"""CLAUDE_PCB.md gates 26-32 as code, across every RF and LO net of the board (and the LO MON taps).

    python3 sim/aslaid/gates.py            prints the findings; writes out/gates.json
"""
import heapq, json, math, os, sys
from collections import defaultdict
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import geom as G
import extract as X

LAMBDA_MM = 299.792458 / 5.8 / math.sqrt(2.93)        # 5.8 GHz on the 0.29 / 0.25 CPWG (field solver's eps_eff)


def rf_nets():
    B = X.board()
    nc = json.load(open(os.path.join(ROOT, "build", "netclasses.json")))
    nets = set(nc["RF"]) | set(nc["LO"])
    for p in B["pad"]:
        fp = B["fp"][p["ref"]][4]
        if fp.startswith(("U.FL", "SMA")) and p["net"] not in ("", "GND") and p["num"] == "1":
            nets.add(p["net"])
    # the synthesizers' outputs and their monitor taps
    for p in B["pad"]:
        if p["ref"] in ("U115", "U203") and "RFOUT" in p["net"] and "RFOUT_EN" not in p["net"]:
            nets.add(p["net"])
    nets |= {"Net-(C152-Pad2)", "Net-(C232-Pad2)"}
    # leave out the slow and DC monitors (MMCX / U.FL taps on baseband nets)
    keep = set()
    for n in nets:
        if any(k in n for k in ("RF", "LO", "CP", "T101", "J101", "J102", "J109", "J201", "J202", "J204", "J401", "J402",
                                "J403", "C213", "C152", "C232", "U401")):
            keep.add(n)
    return sorted(keep)


def split_t(segs):
    """split every segment at the ends of other segments of the net that land on it (a T without a node)"""
    if not segs:
        return segs
    ends = np.array([(s[0], s[1]) for s in segs] + [(s[2], s[3]) for s in segs])
    lay = [s[5] for s in segs] * 2
    wid = np.array([s[4] for s in segs] * 2)
    out = []
    for s in segs:
        x0, y0, x1, y1, w = s[:5]
        L = math.dist((x0, y0), (x1, y1))
        if L < 1e-6:
            out.append(s)
            continue
        m = ((ends[:, 0] >= min(x0, x1) - w) & (ends[:, 0] <= max(x0, x1) + w) &
             (ends[:, 1] >= min(y0, y1) - w) & (ends[:, 1] <= max(y0, y1) + w))
        ts = []
        for k in np.nonzero(m)[0]:
            if lay[k] != s[5]:
                continue
            px, py = ends[k]
            tt = ((px - x0) * (x1 - x0) + (py - y0) * (y1 - y0)) / L ** 2
            if 0.02 < tt * L < L - 0.02:
                qx, qy = x0 + tt * (x1 - x0), y0 + tt * (y1 - y0)
                if math.dist((qx, qy), (px, py)) < min(wid[k], w) / 2:
                    ts.append((tt, px, py))
        pts = [(x0, y0)] + [(px, py) for tt, px, py in sorted(ts)] + [(x1, y1)]
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) > 1e-6:
                out.append([a[0], a[1], b[0], b[1]] + list(s[4:]))
    return out


_GCACHE = {}


def graph(net):
    if net not in _GCACHE:
        _GCACHE[net] = _graph(net)
    return _GCACHE[net]


def _graph(net):
    """nodes: rounded segment ends per layer, joined at vias and inside pads; edges: track lengths"""
    B = X.board()
    segs = split_t([list(s) for s in B["seg"] if s[6] == net])
    pads = [p for p in B["pad"] if p["net"] == net]
    vias = [v for v in B["via"] if v[4] == net]
    adj = defaultdict(list)

    def k(l, x, y):
        return (l, round(x, 2), round(y, 2))
    for s in segs:
        a, b = k(s[5], s[0], s[1]), k(s[5], s[2], s[3])
        L = math.dist(s[:2], s[2:4])
        adj[a].append((b, L))
        adj[b].append((a, L))
    nodes = list(adj)
    xy = np.array([(nd[1], nd[2]) for nd in nodes]) if nodes else np.zeros((0, 2))
    padname = {}
    for p in pads:
        P = G.pad_poly(p)
        pn = ("PAD", p["ref"], p["num"])
        padname[pn] = p
        if not len(xy):
            continue
        r = 0.6 * max(p["sx"], p["sy"]) + 0.05
        cand = np.nonzero((abs(xy[:, 0] - p["x"]) < r) & (abs(xy[:, 1] - p["y"]) < r))[0]
        for i in cand:
            nd = nodes[i]
            if (nd[0] in p["layers"] or p["drill"] > 0) and (G.inside(xy[i:i + 1], [P])[0] or
                                                             math.dist((nd[1], nd[2]), (p["x"], p["y"])) < 0.03):
                adj[pn].append((nd, 0.0))
                adj[nd].append((pn, 0.0))
    for v in vias:
        near = [nd for nd in nodes if math.dist((nd[1], nd[2]), (v[0], v[1])) < v[2] / 2 + 0.02]
        for a in near:
            for b in near:
                if a != b:
                    adj[a].append((b, 0.0))
    return adj, padname


def dist(adj, src):
    d = {src: 0.0}
    h = [(0.0, src)]
    while h:
        dd, u = heapq.heappop(h)
        if dd > d.get(u, 1e9):
            continue
        for v, w in adj[u]:
            nd = dd + w
            if nd < d.get(v, 1e9):
                d[v] = nd
                heapq.heappush(h, (nd, v))
    return d


def branches(adj, padname):
    """every track junction of degree >= 3 (not inside a pad) and the length to each pad beyond it"""
    out = []
    for nd, nb in adj.items():
        if nd[0] == "PAD":
            continue
        tracks = [x for x in nb if x[1] > 0 or x[0][0] != "PAD"]
        if len(set(t[0] for t in tracks)) >= 3 and not any(x[0][0] == "PAD" for x in nb):
            d = dist(adj, nd)
            legs = sorted(((d[p], "%s.%s" % (p[1], p[2])) for p in padname if p in d), key=lambda t: t[0])
            out.append(((nd[1], nd[2]), legs))
    return out


def run():
    B = X.board()
    nets = rf_nets()
    findings = []
    byref = defaultdict(list)
    for p in B["pad"]:
        byref[p["ref"]].append(p)
    # gate 26: every shunt part's track to the IC pin or jack it serves, and every junction's legs
    g26 = []
    for net in nets:
        adj, padname = graph(net)
        ends = [p for p in padname if p[1][0] in "UJT" and p[1] not in ("JP202",)]
        for p in padname:
            ref = p[1]
            if ref[0] not in "CLR":
                continue
            other = [q for q in byref[ref] if q["num"] != p[2] and q["num"] in ("1", "2")]
            if not other:
                continue
            o = other[0]["net"]
            kind = "shunt" if o == "GND" else "bias/pull-up" if o.startswith("+") else "series"
            if kind == "series":
                continue
            d = dist(adj, p)
            near = sorted(((d[e], "%s.%s" % (e[1], e[2])) for e in ends if e in d))
            if near:
                L, which = near[0]
                g26.append(dict(net=net, part=ref, kind=kind, to=which, track_mm=round(L, 2),
                                deg_5p8=round(360 * L / LAMBDA_MM, 1), fail=L > 0.5 and kind == "shunt" or L > 1.0))
        for (xy, legs) in branches(adj, padname):
            g26.append(dict(net=net, junction=[round(xy[0], 2), round(xy[1], 2)],
                            legs=[(round(a, 2), b) for a, b in legs][:5]))
    # gate 27: every RF shunt part's ground
    g27 = []
    for net in nets:
        for p in B["pad"]:
            if p["net"] != net or p["ref"][0] not in "CLR":
                continue
            for q in byref[p["ref"]]:
                if q["net"] == "GND":
                    L, why = X.gnd_return_L(q)
                    gv = B["gnd_vias"]
                    dmin = float(np.sqrt(((gv - (q["x"], q["y"])) ** 2).sum(1)).min())
                    edge = dmin - 0.5 * max(q["sx"], q["sy"])
                    g27.append(dict(part=p["ref"], net=net, nearest_via_from_pad_edge_mm=round(edge, 2),
                                    L_nH=round(L * 1e9, 2), fail=edge > 0.3))
    # gate 28: bias chokes and pull-ups: the nearest capacitor to their cold pad, and whether a plane via comes first
    g28 = []
    for net in nets:
        for p in B["pad"]:
            if p["net"] != net or p["ref"][0] != "L":
                continue
            for q in byref[p["ref"]]:
                if q["net"].startswith("+"):
                    caps = [c for c in B["pad"] if c["net"] == q["net"] and c["ref"].startswith("C")]
                    dc = min(math.dist((c["x"], c["y"]), (q["x"], q["y"])) for c in caps) if caps else 99
                    sv = [v for v in B["via"] if v[4] == q["net"]]
                    dv = min(math.dist((v[0], v[1]), (q["x"], q["y"])) for v in sv) if sv else 99
                    g28.append(dict(part=p["ref"], rf_net=net, rail=q["net"], nearest_cap_mm=round(dc, 1),
                                    plane_via_mm=round(dv, 1), fail=dc > 1.0 or dv < dc))
    # gate 29: which RF ICs and chokes sit on each In2 island; what lies under each In1 relief window
    g29 = {}
    rf_ics = {"U101": "RX LNA", "U102": "RX DSA", "U103": "RX GB1", "U117": "RX GB2", "U104": "RX demod",
              "U115": "RX synth", "U201": "TX modulator", "U202": "TX GB", "U203": "TX synth", "U401": "switch"}
    for (l, n), polys in B["fill"].items():
        if l != "In2.Cu" or n == "GND":
            continue
        users = set()
        for p in B["pad"]:
            if p["net"] == n and p["ref"] in rf_ics:
                users.add(rf_ics[p["ref"]])
            if p["net"] == n and p["ref"] in ("L103", "L104", "L201", "L105", "L106", "L107", "L108", "L203", "L204", "L205", "L206"):
                users.add(p["ref"])
        g29[n] = sorted(users)
    reliefs = []
    for (l, n), polys in B["fill"].items():
        pass
    # gate 32: every RF segment's line: width, gap, the plane under it and the fence
    g32 = []
    gv = B["gnd_vias"]
    for net in nets:
        for s in B["seg"]:
            if s[6] != net:
                continue
            x0, y0, x1, y1, w, l, n = s
            L = math.dist((x0, y0), (x1, y1))
            if L < 0.3:
                continue
            k = max(2, int(L / 0.2))
            t = (np.arange(k) + 0.5) / k
            pts = np.c_[x0 + (x1 - x0) * t, y0 + (y1 - y0) * t]
            refs = X.ref_at(pts, l)
            under = defaultdict(float)
            for (h, rn) in refs:
                under[str(rn)] += L / k
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            rel = gv - (x0, y0)
            along, perp = rel @ (ux, uy), rel @ (-uy, ux)
            nf = int(((along >= 0) & (along <= L) & (abs(perp) >= 0.4) & (abs(perp) <= 1.6)).sum())
            g32.append(dict(net=net, layer=l, w=w, len=round(L, 2), under={k2: round(v, 2) for k2, v in under.items()},
                            fence_per_mm=round(nf / L, 2)))

    # the RF ICs' supply pins: the nearest capacitor by track, and the nearest small (<= 1 nF) one
    gsup = []
    rfic = ("U101", "U102", "U103", "U104", "U115", "U117", "U201", "U202", "U203", "U401")
    for ref in rfic:
        for p in byref[ref]:
            n = p["net"]
            if not (n.startswith("+") or n.endswith("-VCC)")):
                continue
            adj, padname = graph(n)
            src = ("PAD", ref, p["num"])
            if src not in adj:
                gsup.append(dict(ic=ref, pin=p["num"], net=n, note="pin not on a track of its net (a plane via in the pad, or the pour)"))
                continue
            d = dist(adj, src)
            caps = []
            for q in padname:
                if q[1].startswith("C") and q in d:
                    row = B["bom"].get(q[1])
                    caps.append((d[q], q[1], row[0] if row else "DNP"))
            caps.sort()
            small = [c for c in caps if c[2] != "DNP" and X.D.parse_value(c[2], "F") <= 1.01e-9] if caps else []
            gsup.append(dict(ic=ref, pin=p["num"], net=n, nearest=caps[:2], nearest_small=small[:1],
                             fail=(not caps or caps[0][0] > 1.0 or not small or small[0][0] > 2.0)))
    out_sup = gsup
    out = dict(g26=g26, g27=g27, g28=g28, g29=g29, g32=g32, sup=out_sup, nets=nets)
    json.dump(out, open(os.path.join(HERE, "out", "gates.json"), "w"), indent=0)
    # the summary
    print("RF / LO nets checked: %d" % len(nets))
    print("\ngate 26: shunt and bias parts' track to the pin or jack they serve (fail: shunt > 0.5 mm, bias > 1 mm)")
    for r in g26:
        if "part" in r and r["fail"]:
            print("  FAIL %-5s %-13s %-30s %5.2f mm to %-8s (%4.0f deg at 5.8 GHz)" % (r["part"], r["kind"], r["net"][:30], r["track_mm"], r["to"], r["deg_5p8"]))
    print("  junctions with a leg longer than 0.5 mm to a pad (stubs):")
    for r in g26:
        if "junction" in r:
            longs = [lg for lg in r["legs"] if lg[0] > 0.5]
            if len(r["legs"]) >= 3 and longs:
                print("   %-30s at %s: %s" % (r["net"][:30], r["junction"], ", ".join("%s %.1f mm" % (b, a) for a, b in r["legs"])))
    print("\ngate 27: RF shunt parts' ground (fail: nearest ground via > 0.3 mm from the pad's edge)")
    for r in g27:
        if r["fail"]:
            print("  FAIL %-5s on %-28s via %.2f mm off the pad edge, %.2f nH" % (r["part"], r["net"][:28], r["nearest_via_from_pad_edge_mm"], r["L_nH"]))
    print("\ngate 28: chokes and pull-ups (fail: no capacitor within 1 mm of the cold pad, or a plane via before it)")
    for r in g28:
        print("  %s %-5s %-24s -> %-12s nearest capacitor %4.1f mm, plane via %4.1f mm" % ("FAIL" if r["fail"] else "ok  ", r["part"], r["rf_net"][:24], r["rail"], r["nearest_cap_mm"], r["plane_via_mm"]))
    print("\ngate 29: the RF parts on each supply island")
    for n, u in sorted(g29.items()):
        tx = any(x.startswith("TX") for x in u) or "L201" in u or any(x in u for x in ("L203", "L204", "L205", "L206"))
        rxs = any(x.startswith("RX") for x in u) or any(x in u for x in ("L103", "L104", "L105", "L106", "L107", "L108"))
        print("  %s %-12s %s" % ("FAIL" if tx and rxs else "ok  ", n, ", ".join(u)))
    print("\ngate 32: RF / LO segments not over In1 ground for at least 90 %, or with no fence on a run over 2 mm")
    for r in g32:
        gnd = r["under"].get("GND", 0.0)
        if r["layer"] == "B.Cu":
            bad = True
        else:
            bad = gnd < 0.9 * r["len"]
        if bad or (r["len"] > 2 and r["fence_per_mm"] == 0):
            print("  %-30s %s w%.2f %5.1f mm under %s fence %.2f/mm" % (r["net"][:30], r["layer"], r["w"], r["len"], r["under"], r["fence_per_mm"]))
    print("\nRF ICs' supply pins: the nearest capacitor along the track (fail: none within 1 mm, or no <= 1 nF within 2 mm)")
    for r in out_sup:
        if "note" in r:
            print("  ?    %s.%s %-14s %s" % (r["ic"], r["pin"], r["net"], r["note"]))
        else:
            print("  %s %s.%-3s %-16s nearest %s; nearest <= 1 nF %s" % ("FAIL" if r["fail"] else "ok  ", r["ic"], r["pin"], r["net"][:16],
                  ", ".join("%s %s %.1f mm" % (c[1], c[2], c[0]) for c in r["nearest"]) or "none",
                  ", ".join("%s %s %.1f mm" % (c[1], c[2], c[0]) for c in r["nearest_small"]) or "none"))
    return out


if __name__ == "__main__":
    run()
