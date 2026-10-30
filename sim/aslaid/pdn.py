#!/usr/bin/env python3
"""The supply planes as cavities, and the transmitter's leak into the receiver through +5V_RF.

    python3 sim/aslaid/pdn.py

Each In2 island is meshed at 0.5 mm: a node a cell, its capacitance to the ground planes on either side (In1
1.065 mm above; the B.Cu ground pour 0.21 mm below wherever it is filled), the inductance of a square between
cells, the dielectric's loss.  Every capacitor on the island hangs off the cell of its via (ESL + its vias,
1.0 nH, and its ESR).  The three ADL5611 bias chokes go into the cells of their vias.  The TX gain block's
output drives its choke; the plane carries it to the receive chokes, which put it on the receive line after
the DSA.  Compared with the bench's leak at RX MON.
"""
import json, math, os, sys
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import geom as G
import extract as X
import devices as D
import circuit as C

MU0, E0 = 4e-7 * math.pi, 8.854187817e-12
D_CORE, D_PP = 1.065e-3, 0.2104e-3
ER_CORE = 4.6
TAND = 0.02
DX = 0.5            # mm
L_CAP_LOOP = 1.0e-9     # a capacitor's ESL and its two vias between the plane and ground


def island_cells(net):
    B = X.board()
    polys = B["fill"][("In2.Cu", net)]
    allp = np.vstack(polys)
    x0, y0 = allp.min(0)
    x1, y1 = allp.max(0)
    xs = np.arange(x0 + DX / 2, x1, DX)
    ys = np.arange(y0 + DX / 2, y1, DX)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.c_[gx.ravel(), gy.ravel()]
    ins = G.inside(pts, polys)
    bcu = G.inside(pts, B["fill"][("B.Cu", "GND")])
    return xs, ys, ins.reshape(gy.shape), bcu.reshape(gy.shape)


def build(net):
    xs, ys, ins, bcu = island_cells(net)
    idx = -np.ones(ins.shape, int)
    idx[ins] = np.arange(ins.sum())
    n = int(ins.sum())
    a = (DX * 1e-3) ** 2
    cpp = np.where(bcu[ins], E0 * ER_CORE * a / D_CORE + E0 * 4.4 * a / D_PP, E0 * ER_CORE * a / D_CORE)
    deff = np.where(bcu, D_CORE * D_PP / (D_CORE + D_PP), D_CORE)
    edges = []
    J, I = np.nonzero(ins)
    for dj, di in ((0, 1), (1, 0)):
        jn, inn = J + dj, I + di
        ok = (jn < ins.shape[0]) & (inn < ins.shape[1])
        jn, inn, j0, i0 = jn[ok], inn[ok], J[ok], I[ok]
        m = ins[jn, inn]
        for a1, b1, c1, d1 in zip(j0[m], i0[m], jn[m], inn[m]):
            edges.append((idx[a1, b1], idx[c1, d1], 0.5 * (deff[a1, b1] + deff[c1, d1])))
    return dict(xs=xs, ys=ys, ins=ins, idx=idx, n=n, cpp=cpp, edges=np.array(edges), net=net)


def cell_of(m, x, y):
    i = int(round((x - m["xs"][0]) / DX))
    j = int(round((y - m["ys"][0]) / DX))
    best, bd = None, 1e9
    for dj in range(-3, 4):
        for di in range(-3, 4):
            jj, ii = j + dj, i + di
            if 0 <= jj < m["ins"].shape[0] and 0 <= ii < m["ins"].shape[1] and m["ins"][jj, ii]:
                d = math.hypot(m["xs"][ii] - x, m["ys"][jj] - y)
                if d < bd:
                    best, bd = m["idx"][jj, ii], d
    return best


def taps(net):
    """the parts on the island: each capacitor and each choke with the via that takes its pad to the plane"""
    B = X.board()
    vias = [(v[0], v[1]) for v in B["via"] if v[4] == net]
    out = []
    for p in B["pad"]:
        if p["net"] != net or p["ref"][0] not in "CLUFR" or p["drill"] > 0:
            continue
        if not vias:
            continue
        d = [math.hypot(vx - p["x"], vy - p["y"]) for vx, vy in vias]
        k = int(np.argmin(d))
        row = B["bom"].get(p["ref"])
        out.append(dict(ref=p["ref"], num=p["num"], x=p["x"], y=p["y"], via=vias[k], via_d=d[k],
                        value=row[0] if row else None))
    return out


def solve(m, f, inj, loads):
    """inj: {cell: current}; loads: [(cell, Z)]; returns the cells' voltages"""
    w = 2 * math.pi * f
    n = m["n"]
    rs = math.sqrt(math.pi * f * MU0 / 5.8e7)
    e = m["edges"]
    ze = 1j * w * MU0 * e[:, 2] + 2 * rs * 1.4         # a square: the inductance and both planes' resistance
    ye = 1.0 / ze
    rows = np.r_[e[:, 0], e[:, 1], e[:, 0], e[:, 1]].astype(int)
    cols = np.r_[e[:, 1], e[:, 0], e[:, 0], e[:, 1]].astype(int)
    vals = np.r_[-ye, -ye, ye, ye]
    Y = sp.coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    Y = Y + sp.diags(1j * w * m["cpp"] * (1 - 1j * TAND))
    dl = np.zeros(n, complex)
    for c, z in loads:
        dl[c] += 1.0 / z
    Y = Y + sp.diags(dl)
    I = np.zeros(n, complex)
    for c, cur in inj.items():
        I[c] += cur
    return spla.spsolve(Y.tocsc(), I)


def modes(m, k=40):
    """the island's lowest cavity modes with open (magnetic-wall) edges: the Neumann Laplacian on the cells"""
    n = m["n"]
    e = m["edges"].astype(int)
    A = sp.coo_matrix((np.r_[-np.ones(len(e)), -np.ones(len(e))], (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
    deg = -np.asarray(A.sum(1)).ravel()
    L = A + sp.diags(deg)
    vals = spla.eigsh(L.tocsc(), k=min(k, n - 2), sigma=-1e-3, which="LM", return_eigenvectors=False)
    kk = np.sqrt(np.clip(np.sort(vals), 0, None)) / (DX * 1e-3)
    return kk * 299792458.0 / (2 * math.pi * math.sqrt(ER_CORE))


def run():
    out = {}
    B = X.board()
    nets = sorted(set(n for (l, n) in B["fill"] if l == "In2.Cu" and n != "GND"))
    # every island's modes in 4.5-6.5 GHz
    for net in nets:
        m = build(net)
        try:
            fm = modes(m, 60)
        except Exception as ex:                                   # noqa: BLE001
            fm = []
        tp = taps(net)
        out[net] = dict(cells=m["n"], area_mm2=m["n"] * DX * DX, modes_ghz=[round(x / 1e9, 3) for x in fm],
                        caps=len([t for t in tp if t["ref"].startswith("C")]), parts=sorted(set(t["ref"] for t in tp)))
        inband = [x / 1e9 for x in fm if 4.9e9 <= x <= 5.95e9]
        print("%-12s %6.0f mm2, %2d capacitors; %d modes below %.1f GHz computed, %d in 4.9-5.95 GHz: %s"
              % (net, m["n"] * DX * DX, out[net]["caps"], len(fm), fm[-1] / 1e9 if len(fm) else 0, len(inband),
                 ", ".join("%.2f" % x for x in inband[:12])))
    # the leak through +5V_RF
    net = "+5V_RF"
    m = build(net)
    tp = taps(net)
    loads = []
    ch = {}
    for t in tp:
        c = cell_of(m, *t["via"])
        if c is None:
            continue
        if t["ref"].startswith("C") and t["value"]:
            zc = D.part_z(t["ref"], t["value"], "0402")[0]
            loads.append((c, lambda f, zc=zc: zc(f) + 1j * 2 * math.pi * f * (L_CAP_LOOP - 0.3e-9)))
        if t["ref"] in ("L103", "L104", "L201"):
            ch[t["ref"]] = c
    zch = D.part_z("L103", "43nH", "0603")[0]
    fs = np.arange(4.0e9, 7.0001e9, 0.02e9)
    rows = []
    meas_tx = {}
    for fn in ("map_20261029_163008.json", "mapfine_20261029_173239.json"):
        for r in json.load(open(os.path.join(ROOT, "bringup", "data", "board_A", "overnight", fn))):
            meas_tx[r["mhz"]] = r["tx_ant_dbm"]
    for f in fs:
        zl = [(c, z(f)) for c, z in loads]
        # the plane seen through each choke's via (1.0 nH)
        lv = 1j * 2 * math.pi * f * 1.0e-9
        # TX: the gain block's output (TX ANT + 1.5 dB of coupler, launch and lines), 50 ohm: its voltage amplitude
        p_tx = meas_tx[min(meas_tx, key=lambda k: abs(k - f / 1e6))] + 1.5
        v_tx = math.sqrt(2 * 50 * 1e-3 * 10 ** (p_tx / 10))
        i_in = v_tx / (zch(f) + lv)
        # the receive chokes load the plane too: the choke, its via, the receive line (25 ohm: the line both ways)
        zrx = zch(f) + lv + 25.0
        V = solve(m, f, {ch["L201"]: i_in}, zl + [(ch["L103"], zrx), (ch["L104"], zrx)])
        z21 = {k: V[ch[k]] / i_in for k in ("L103", "L104")}
        # each receive choke puts V / zrx into the line's 25 ohm
        vinj = {k: V[ch[k]] / zrx * 25.0 for k in ("L103", "L104")}
        # to RX MON: L103 is at U103's output (then U117's gain), L104 at U117's output; CP101's coupling 20.2 dB
        g117 = abs(D.adl5611_s(f)[1, 0])
        v_cp = vinj["L103"] * g117 + vinj["L104"]              # coherent sum, phases as the model has them
        p_mon = 10 * math.log10(abs(v_cp) ** 2 / 100 / 1e-3) - 20.2
        p_mon_103 = 10 * math.log10(abs(vinj["L103"] * g117) ** 2 / 100 / 1e-3) - 20.2
        p_mon_104 = 10 * math.log10(abs(vinj["L104"]) ** 2 / 100 / 1e-3) - 20.2
        rows.append(dict(f=f / 1e9, p_tx=p_tx, z21_103=abs(z21["L103"]), z21_104=abs(z21["L104"]),
                         p_rxmon=p_mon, p_103=p_mon_103, p_104=p_mon_104))
    out["leak"] = rows
    json.dump(out, open(os.path.join(HERE, "out", "pdn.json"), "w"))
    meas = {5.0: -53, 5.3: -53.4, 5.5: -53.1, 5.6: -57.2, 5.7: -73.4, 5.8: -69.2, 5.85: -61.2, 5.9: -51.2, 5.95: -47.3, 6.0: -45.7}
    print("leak through +5V_RF into RX MON (model, coherent sum of the two receive chokes) against the bench (DSA 31.75):")
    for f in sorted(meas):
        r = min(rows, key=lambda q: abs(q["f"] - f))
        print("  %.2f GHz: |Z21| %.1f / %.1f ohm; model %6.1f dBm (L103 %6.1f, L104 %6.1f); measured %6.1f" %
              (f, r["z21_103"], r["z21_104"], r["p_rxmon"], r["p_103"], r["p_104"], meas[f]))
    return out


if __name__ == "__main__":
    run()
