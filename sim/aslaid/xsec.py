#!/usr/bin/env python3
"""Quasi-static cross-sections by finite differences (Laplace in 2D, uniform grid): the per-unit-length
capacitance with and without the dielectric gives Z0 and eps_eff of a line, and the even and odd modes of a
coupled pair (the printed -20 dB couplers).  JLC04161H-7628: L1 copper (35 um) on 0.2104 mm of 7628 (er 4.4)
over the L2 ground plane; coplanar ground pours on L1 at the given gap; air above (solder mask left out:
it lowers Z0 by about 1-2 ohm).

    python3 sim/aslaid/xsec.py        prints the board's line widths and the couplers against the formula
"""
import math, os, sys
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

E0 = 8.854187817e-12
C0 = 299792458.0
H, ER, T = 0.2104, 4.4, 0.035


def solve(traces, gaps_to_ground, h=H, er=ER, t=T, dx=0.00875, xspan=None, ytop=None, eps_on=True):
    """traces: list of (x_left, x_right, potential); ground pours on L1 beyond gaps_to_ground (x of the pour's inner
    edges, (xl, xr)) or None for no coplanar ground.  Returns the charge on each trace per unit length (C/m) for
    the given potentials."""
    xl_min = min(a for a, b, v in traces)
    xr_max = max(b for a, b, v in traces)
    if xspan is None:
        xspan = (xl_min - 2.5, xr_max + 2.5)
    if ytop is None:
        ytop = h + t + 2.0
    nx = int(round((xspan[1] - xspan[0]) / dx)) + 1
    ny = int(round(ytop / dx)) + 1
    xs = xspan[0] + dx * np.arange(nx)
    ys = dx * np.arange(ny)
    jh = int(round(h / dx))                 # node row of the dielectric's top surface
    jt = jh + max(1, int(round(t / dx)))    # copper top
    fixed = np.zeros((ny, nx), bool)
    val = np.zeros((ny, nx))
    owner = -np.ones((ny, nx), int)
    fixed[0, :] = True                      # the plane
    fixed[-1, :] = True                     # far top wall (grounded, far away)
    fixed[:, 0] = fixed[:, -1] = True       # side walls
    for k, (a, b, v) in enumerate(traces):
        ia, ib = np.searchsorted(xs, a - 1e-9), np.searchsorted(xs, b + 1e-9) - 1
        fixed[jh:jt + 1, ia:ib + 1] = True
        val[jh:jt + 1, ia:ib + 1] = v
        owner[jh:jt + 1, ia:ib + 1] = k
    if gaps_to_ground is not None:
        gl, gr = gaps_to_ground
        fixed[jh:jt + 1, xs <= gl + 1e-9] = True
        fixed[jh:jt + 1, xs >= gr - 1e-9] = True
    # permittivity per cell (cell (j, i) spans rows j..j+1, cols i..i+1)
    epc = np.ones((ny - 1, nx - 1))
    if eps_on:
        epc[:jh, :] = er
    # edge permittivities
    ex = np.ones((ny, nx - 1))              # between (j, i) and (j, i+1): cells (j-1, i) and (j, i)
    ex[1:-1, :] = 0.5 * (epc[:-1, :] + epc[1:, :])
    ex[0, :] = epc[0, :]
    ex[-1, :] = epc[-1, :]
    ey = np.ones((ny - 1, nx))              # between (j, i) and (j+1, i): cells (j, i-1) and (j, i)
    ey[:, 1:-1] = 0.5 * (epc[:, :-1] + epc[:, 1:])
    ey[:, 0] = epc[:, 0]
    ey[:, -1] = epc[:, -1]
    idx = -np.ones((ny, nx), int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    n = free.sum()
    rows, cols, data = [], [], []
    b = np.zeros(n)
    J, I = np.nonzero(free)
    diag = np.zeros(n)
    for dj, di, w in ((0, 1, ex[J, I]), (0, -1, ex[J, I - 1]), (1, 0, ey[J, I]), (-1, 0, ey[J - 1, I])):
        jn, inn = J + dj, I + di
        diag += w
        nb = idx[jn, inn]
        m = nb >= 0
        rows.append(idx[J, I][m]); cols.append(nb[m]); data.append(-w[m])
        b[idx[J, I][~m]] += w[~m] * val[jn[~m], inn[~m]]
    rows.append(idx[J, I]); cols.append(idx[J, I]); data.append(diag)
    A = sp.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))
    V = val.copy()
    V[free] = spla.spsolve(A, b)
    # charge on each trace: flux out of its nodes into free neighbours
    q = np.zeros(len(traces))
    for k in range(len(traces)):
        jj, ii = np.nonzero(owner == k)
        for dj, di in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            jn, inn = jj + dj, ii + di
            m = owner[jn, inn] != k
            if di == 1:
                w = ex[jj, ii]
            elif di == -1:
                w = ex[jj, ii - 1]
            elif dj == 1:
                w = ey[jj, ii]
            else:
                w = ey[jj - 1, ii]
            q[k] += (E0 * w[m] * (V[jj[m], ii[m]] - V[jn[m], inn[m]])).sum()
    return q


def line(w, s, h=H, er=ER, coplanar=True):
    """a single line: Z0 and eps_eff (coplanar=False: microstrip)"""
    tr = [(-w / 2, w / 2, 1.0)]
    g = (-w / 2 - s, w / 2 + s) if coplanar else None
    c = solve(tr, g, h, er)[0]
    c0 = solve(tr, g, h, er, eps_on=False)[0]
    return 1.0 / (C0 * math.sqrt(c * c0)), c / c0


def pair(w, s_between, g_out, h=H, er=ER):
    """two lines w wide, s_between apart, the pours g_out off their outer edges: Z0e, Z0o, eps_e, eps_o"""
    xa = -s_between / 2 - w
    tr_e = [(xa, xa + w, 1.0), (s_between / 2, s_between / 2 + w, 1.0)]
    tr_o = [(xa, xa + w, 1.0), (s_between / 2, s_between / 2 + w, -1.0)]
    g = (xa - g_out, s_between / 2 + w + g_out)
    out = []
    for tr in (tr_e, tr_o):
        c = solve(tr, g, h, er)[0]
        c0 = solve(tr, g, h, er, eps_on=False)[0]
        out.append((1.0 / (C0 * math.sqrt(c * c0)), c / c0))
    (ze, ee), (zo, eo) = out
    return ze, zo, ee, eo


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import rf_lines as R
    print("width  gap   FD Z0  eps   | formula Z0 eps")
    for w in (0.15, 0.20, 0.25, 0.29):
        z, e = line(w, 0.25)
        zf, ef = R.cpwg_z0(w, 0.25)
        print("%.2f  0.25  %5.1f %5.2f | %5.1f %5.2f" % (w, z, e, zf, ef))
    for w in (0.15, 0.20, 0.29):
        z, e = line(w, 0.25, coplanar=False)
        print("%.2f  none  %5.1f %5.2f (microstrip)" % (w, z, e))
    ze, zo, ee, eo = pair(0.29, 0.25, 0.25)
    k = (ze - zo) / (ze + zo)
    print("coupler 0.29 / 0.25 gap: Z0e %.1f Z0o %.1f eps_e %.3f eps_o %.3f  k %.4f = %.1f dB at the quarter wave"
          % (ze, zo, ee, eo, k, 20 * math.log10(k)))
