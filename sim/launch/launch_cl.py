#!/usr/bin/env python3
"""
The CostasLink SMA launch in openEMS (3D FDTD): the SyzygyRadioDrivers launch model
(SMABridgeTestAnalysis/fieldsolver/launch_model.py, MODEL_REV 7, validated against the V1 and V3 test boards)
re-targeted to this board's stack-up and connector.  Prompt 33, 2026-10-14.

What differs from the study's model, and why:

* **Stack-up: JLCPCB JLC04161H-7628, four layers.**  F.Cu 35 um, 7628 prepreg 0.2104 mm (er 4.4 at 5.8 GHz,
  sim/rf_lines.py), In1 17.5 um, core 1.065 mm (er 4.6), In2, prepreg 0.2104, B.Cu: 1.6 mm.  Two inner planes
  instead of four, a 1.065 mm core instead of two 0.55 mm ones: the barrel crosses more dielectric with
  fewer plane edges, so the antipad optimum has to be found again rather than copied (the study's was a
  plateau at 4.2-4.6 mm on its stack).
* **Connector: Bat Wireless BWSMA-KWE-Z001** (datasheets/BWSMA-KWE-Z001_C496551.pdf, page 6): a right-angle
  jack whose PCB pins are vertical: centre pin 0.9 mm round, four 0.9 mm square legs at (+-2.55, +-2.55); the
  pins stand 3.5 mm below the seating face, so 1.9 mm of pin hangs under a 1.6 mm board.  JLCPCB's land
  pattern (the footprint in use): centre hole 1.3 mm in a 2.0 mm pad, legs 1.6 mm holes in 2.2 mm pads.  The
  jack's coax runs horizontally above the board and turns down into the pin inside the body; that bend is the
  maker's, and the model feeds the pin from a vertical 50 ohm coax (1.27 / 4.1 mm PTFE) the way the study
  does, which is the part of the launch the PCB controls.
* **The line: this board's CPWG**, 0.29 mm wide with 0.25 mm gaps to the top pour (49.8 ohm with the copper
  thickness, sim/rf_lines.py).  The FDTD's copper is a zero-thickness sheet, which puts the same line a few
  ohms high; the MSL port reads its own Z_ref and the S-parameters are referenced to 50 ohm, so the
  launch's reflection is what is reported, not the port's small mismatch.

Knobs, as the study's: antipad (the void diameter on In1 and In2), pad_od, taper_len, fcu_clear (the pad's
clearance to the top pour), trace_gap (the CPWG gap), bcu_clear (the B.Cu pour's clearance from the pad
edge), inner_pads (remove_unused_layers no/yes), pin_below, legs_below, solder_h.  Everything in mm.
"""
import os
import shutil
import tempfile
import numpy as np
from CSXCAD import ContinuousStructure
from openEMS import openEMS

MODEL_REV = 1
UNIT = 1e-3
HERE = os.path.dirname(os.path.abspath(__file__))
EPS0 = 8.8541878128e-12
C0 = 2.99792458e8

# ---- the stack, bottom up: each plane sits on the face that bounds its dielectric (zero-thickness copper)
T_PREPREG, T_CORE = 0.2104, 1.065
ER_PREPREG, TD_PREPREG = 4.4, 0.02
ER_CORE, TD_CORE = 4.6, 0.02
Z_B = 0.0
Z_IN2 = Z_B + T_PREPREG
Z_IN1 = Z_IN2 + T_CORE
Z_F = Z_IN1 + T_PREPREG
BOARD_T = 1.6                                    # with the copper; the model spans Z_F - Z_B = 1.4858
PLANES = [("In1.Cu", Z_IN1), ("In2.Cu", Z_IN2)]
SLABS = [(Z_IN1, Z_F, ER_PREPREG, TD_PREPREG), (Z_IN2, Z_IN1, ER_CORE, TD_CORE), (Z_B, Z_IN2, ER_PREPREG, TD_PREPREG)]

# ---- the connector and the footprint
SMA = dict(drill_signal=1.3, pad_od=2.0, post_xy=2.55, post_drill=1.6, post_pad_od=2.2)
PIN = dict(d=0.9, below_face=3.5, chamfer=0.1, d_tip=0.7, leg_w=0.9, leg_xy=2.55)
PIN_EXPOSED = PIN["below_face"] - BOARD_T          # 1.9 mm of pin under the board
COAX = dict(d_inner=1.27, d_outer=4.10, er_ptfe=2.05)
SOLDER = dict(h=0.40, r=None)
LINE = dict(w=0.29, gap=0.25)

P_SUB, P_PLANE, P_VOID = 1, 5, 20
P_PORT, P_GAP, P_METAL, P_VIA = 40, 45, 50, 55
NPML = 8


def kappa(er, tand, f):
    return 2 * np.pi * f * EPS0 * er * tand


def circle(r, n=64, cx=0.0, cy=0.0):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.vstack([cx + r * np.cos(a), cy + r * np.sin(a)])


def uniq(v, tol):
    v = np.array(sorted(float(x) for x in v))
    keep = [v[0]]
    for x in v[1:]:
        if x - keep[-1] > tol:
            keep.append(x)
    return keep


def build(CSX, FDTD, mesh,
          antipad=1.8, pad_od=SMA["pad_od"], drill=SMA["drill_signal"],
          taper_len=0.0, taper_w_end=None, taper_w_start=None,
          trace_w=LINE["w"], fcu_clear=LINE["gap"], trace_gap=LINE["gap"],
          posts=True, inner_pads=False, flange_relief=0.10,
          fence_x0=2.6, fence_y=0.845, fence_pitch=1.2, fence_d=0.45,
          antipad_per_layer=None, bcu_pad=True, bcu_clear=None, barrel=True,
          pin_below=PIN_EXPOSED, pin_d=PIN["d"], pin_chamfer=PIN["chamfer"], pin_d_tip=PIN["d_tip"],
          legs_below=PIN_EXPOSED, leg_w=PIN["leg_w"],
          solder_h=SOLDER["h"], solder_r=SOLDER["r"], solder_steps=4,
          win=4.0, x_trace=8.0, coax_len=6.0,
          f0=6e9, res_trace=0.035, res_fine=0.09, res_far=0.40, res_coax=0.25, nz_prepreg=9, nz_core=9):
    """Lay down geometry and mesh.  Returns (port1, port2, extents).  A taper_len of 0 means the line meets
    the pad's edge directly, as the board does today (a 0.25 mm neck for 0.6 mm; drawn here as the line)."""
    if taper_w_end is None:
        taper_w_end = trace_w
    if taper_w_start is None:
        taper_w_start = pad_od
    if bcu_clear is None:
        bcu_clear = fcu_clear
    tl = max(taper_len, 0.02)                      # a zero taper is a 0.02 mm step: the line at the pad edge
    pad_uni = (NPML + 2) * res_far
    x_lo = -win - 1.0 - pad_uni
    x_hi = x_trace + pad_uni
    y_half = win + 1.0 + pad_uni
    z_air_bot = min(Z_B - 0.5, Z_B - max(pin_below, legs_below) - 0.8)
    z_bot = z_air_bot - (NPML + 2) * res_far
    z_top = Z_F + coax_len

    pec = CSX.AddMetal("PEC")
    void = CSX.AddMaterial("void", epsilon=1.0)
    aps = antipad_per_layer or {}

    for i, (zl, zh, er, td) in enumerate(SLABS):
        m = CSX.AddMaterial("FR4_%d" % i, epsilon=er, kappa=kappa(er, td, f0))
        m.AddBox([x_lo, -y_half, zl], [x_hi, y_half, zh], priority=P_SUB)

    taper_xy = np.array([[0.0, tl, tl, 0.0],
                         [-taper_w_start / 2, -taper_w_end / 2, taper_w_end / 2, taper_w_start / 2]])

    def clearance_poly(x_end, w_end):
        return np.array(
            [[0.0, tl, x_end, x_end, tl, 0.0],
             [-(pad_od / 2 + fcu_clear), -(taper_w_end / 2 + fcu_clear), -w_end,
              w_end, taper_w_end / 2 + fcu_clear, pad_od / 2 + fcu_clear]])

    def lay_pad(z, with_trace, void_dia):
        if void_dia > 0:
            void.AddCylinder([0, 0, z - 1e-4], [0, 0, z + 1e-4], radius=void_dia / 2, priority=P_VOID)
        if with_trace:
            void.AddLinPoly(clearance_poly(x_hi, ych), norm_dir="z", elevation=z - 1e-4, length=2e-4, priority=P_VOID)
            pec.AddPolygon(circle(pad_od / 2), norm_dir="z", elevation=z, priority=P_METAL)
            pec.AddPolygon(taper_xy, norm_dir="z", elevation=z, priority=P_METAL)
            pec.AddBox([tl, -trace_w / 2, z], [x_hi, trace_w / 2, z], priority=P_METAL)
        elif inner_pads:
            void.AddLinPoly(clearance_poly(tl + fcu_clear, taper_w_end / 2 + fcu_clear),
                            norm_dir="z", elevation=z - 1e-4, length=2e-4, priority=P_VOID)
            pec.AddPolygon(circle(pad_od / 2), norm_dir="z", elevation=z, priority=P_METAL)
            pec.AddPolygon(taper_xy, norm_dir="z", elevation=z, priority=P_METAL)

    ych = max(taper_w_end, trace_w) / 2 + trace_gap
    floor = pad_od + 0.15 if inner_pads else drill + 0.15

    for name, z in PLANES:
        pec.AddBox([x_lo, -y_half, z], [x_hi, y_half, z], priority=P_PLANE)
        ap_here = aps.get(name, antipad)
        lay_pad(z, False, max(ap_here, floor) if ap_here > 0 else 0.0)

    pec.AddBox([x_lo, -y_half, Z_B], [x_hi, y_half, Z_B], priority=P_PLANE)
    if bcu_clear > 0:
        void.AddCylinder([0, 0, Z_B - 1e-4], [0, 0, Z_B + 1e-4], radius=pad_od / 2 + bcu_clear, priority=P_VOID)
    if bcu_pad:
        if inner_pads:
            void.AddLinPoly(clearance_poly(tl + fcu_clear, taper_w_end / 2 + fcu_clear),
                            norm_dir="z", elevation=Z_B - 1e-4, length=2e-4, priority=P_VOID)
        pec.AddPolygon(circle(pad_od / 2), norm_dir="z", elevation=Z_B, priority=P_METAL)
        if inner_pads:
            pec.AddPolygon(taper_xy, norm_dir="z", elevation=Z_B, priority=P_METAL)

    pec.AddBox([x_lo, -y_half, Z_F], [x_hi, y_half, Z_F], priority=P_PLANE)
    lay_pad(Z_F, True, pad_od + 2 * fcu_clear)
    x_g = 1.90
    w_g = ((pad_od / 2 + trace_gap) + ((taper_w_end / 2 + trace_gap) - (pad_od / 2 + trace_gap)) * min(x_g / tl, 1.0))
    void_gap = CSX.AddMaterial("flange_gap", epsilon=1.0)
    void_gap.AddLinPoly(np.array([[x_g, tl, x_hi, x_hi, tl, x_g],
                                  [-w_g, -(taper_w_end / 2 + trace_gap), -ych, ych, taper_w_end / 2 + trace_gap, w_g]]),
                        norm_dir="z", elevation=Z_F - 1e-4, length=flange_relief + 1e-4, priority=P_GAP)

    if barrel:
        pec.AddCylinder([0, 0, Z_B], [0, 0, Z_F], radius=drill / 2, priority=P_VIA)
    p = SMA["post_xy"]
    if posts:
        for sx in (-1, 1):
            for sy in (-1, 1):
                pec.AddCylinder([sx * p, sy * p, Z_B], [sx * p, sy * p, Z_F], radius=SMA["post_drill"] / 2, priority=P_VIA)
    if pin_below > 0:
        z_tip = Z_B - pin_below
        z_ch = max(min(z_tip + pin_chamfer, Z_B), z_tip)
        pec.AddCylinder([0, 0, Z_B], [0, 0, z_ch], radius=pin_d / 2, priority=P_VIA)
        if z_ch > z_tip:
            pec.AddCylinder([0, 0, z_ch], [0, 0, z_tip], radius=pin_d_tip / 2, priority=P_VIA)
    if legs_below > 0 and posts:
        for sx in (-1, 1):
            for sy in (-1, 1):
                pec.AddBox([sx * p - leg_w / 2, sy * p - leg_w / 2, Z_B - legs_below],
                           [sx * p + leg_w / 2, sy * p + leg_w / 2, Z_B], priority=P_VIA)
    r_sol = (solder_r if solder_r else pad_od / 2) if solder_h > 0 else 0.0
    if solder_h > 0 and r_sol > pin_d / 2:
        for k in range(solder_steps):
            zt = Z_B - solder_h * k / solder_steps
            zb = Z_B - solder_h * (k + 1) / solder_steps
            rk = r_sol + (pin_d / 2 - r_sol) * (k + 0.5) / solder_steps
            pec.AddCylinder([0, 0, zt], [0, 0, zb], radius=rk, priority=P_VIA)

    # this board's via fence along the CPWG: 0.45 mm vias at +-0.845 mm from the line's centre, every 1.2 mm
    fence_xy = []
    if fence_x0:
        for xv in np.arange(fence_x0, x_hi - 0.2, fence_pitch):
            for sy in (-1, 1):
                pec.AddBox([xv - fence_d / 2, sy * fence_y - fence_d / 2, Z_B],
                           [xv + fence_d / 2, sy * fence_y + fence_d / 2, Z_F], priority=P_VIA)
                fence_xy += [xv - fence_d / 2, xv + fence_d / 2]

    r_i, r_o = COAX["d_inner"] / 2, COAX["d_outer"] / 2
    r_os = r_o + 0.35
    ptfe = CSX.AddMaterial("PTFE", epsilon=COAX["er_ptfe"])
    ptfe.AddCylinder([0, 0, Z_F], [0, 0, z_top], radius=r_o, priority=P_SUB + 1)

    # ---- mesh
    zl = [Z_B, Z_IN2, Z_IN1, Z_F]
    for a, b, n in ((Z_B, Z_IN2, nz_prepreg), (Z_IN2, Z_IN1, nz_core), (Z_IN1, Z_F, nz_prepreg)):
        zl += list(np.linspace(a, b, n))
    zl += [Z_F + flange_relief, Z_F + 2 * flange_relief]
    zl += list(np.arange(z_top, Z_F + 1.3 - 1e-9, -res_coax))
    zl += [z_air_bot, z_bot]
    if pin_below > 0:
        zl += [Z_B - pin_below, Z_B - pin_below + pin_chamfer]
        zl += list(np.arange(Z_B, Z_B - pin_below - 1e-9, -res_fine))
    if legs_below > 0:
        zl += [Z_B - legs_below]
    if solder_h > 0:
        zl += [Z_B - solder_h * k / solder_steps for k in range(solder_steps + 1)]
    zl += list(np.arange(z_air_bot, z_bot - 1e-9, -res_far))
    mesh.AddLine("z", uniq(zl, 0.008))
    mesh.SmoothMeshLines("z", res_coax, ratio=1.45)
    mesh.SmoothMeshLines("z", res_far, ratio=1.45)

    r_feat = [drill / 2, pad_od / 2, antipad / 2, pad_od / 2 + fcu_clear, floor / 2, r_o, r_os] + [aps.get(n, antipad) / 2 for n in aps]
    if pin_below > 0:
        r_feat += [pin_d / 2, pin_d_tip / 2]
    if r_sol > pin_d / 2:
        r_feat += [r_sol]
    r_feat += [pad_od / 2 + bcu_clear]
    feat = [0.0, tl, tl + fcu_clear] + [s * r for r in r_feat for s in (-1, 1)]
    feat += [s * p + q for s in (-1, 1) for q in (-SMA["post_drill"] / 2, SMA["post_drill"] / 2)]
    if legs_below > 0:
        feat += [s * p + q for s in (-1, 1) for q in (-leg_w / 2, leg_w / 2)]
    feat += fence_xy
    ytr = [0.0]
    for e in (trace_w / 2, -trace_w / 2):
        sgn = 1.0 if e > 0 else -1.0
        ytr += [e - sgn * res_trace / 3.0, e + sgn * 2.0 * res_trace / 3.0]
    mesh.AddLine("y", sorted(ytr))
    mesh.SmoothMeshLines("y", res_trace, ratio=1.0001)
    mesh.AddLine("x", uniq([v for v in feat if abs(v) <= 0.9], 0.02))
    mesh.SmoothMeshLines("x", res_trace, ratio=1.0001)
    for ny in ("x", "y"):
        mesh.AddLine(ny, uniq([v for v in feat if abs(v) <= win] + [-win, win], 0.02))
        mesh.SmoothMeshLines(ny, res_fine, ratio=1.25)
    if fence_xy:
        mesh.AddLine("x", uniq([v for v in fence_xy if x_lo < v < x_hi], 0.02))
    mesh.AddLine("x", list(np.arange(x_hi, x_hi - pad_uni - 1e-9, -res_far)) + list(np.arange(x_lo, x_lo + pad_uni + 1e-9, res_far)))
    mesh.AddLine("y", list(np.arange(y_half, y_half - pad_uni - 1e-9, -res_far)) + list(np.arange(-y_half, -y_half + pad_uni + 1e-9, res_far)))
    for ny in ("x", "y"):
        mesh.SmoothMeshLines(ny, res_far, ratio=1.3)

    z_meas1 = z_top - (NPML + 3) * res_coax
    port1 = FDTD.AddCoaxialPort(1, pec, None, [0, 0, z_top], [0, 0, Z_F], "z", r_i, r_o, r_os, excite_amp=1,
                                FeedShift=(NPML + 1) * res_coax, MeasPlaneShift=z_top - z_meas1, priority=P_PORT)
    msl_x0 = tl + 1.0
    port2 = FDTD.AddMSLPort(2, pec, [x_hi, -trace_w / 2, Z_F], [msl_x0, trace_w / 2, Z_IN1], "x", "z",
                            MeasPlaneShift=x_hi - x_trace + 0.5, priority=P_METAL)
    # de-embedding lengths: port 1's plane sits z_meas1 - Z_F above the board's face (the port starts at z_top, its
    # MeasPlaneShift is measured from there); port 2's plane sits at x_trace - 0.5 from the pin, tl of it the taper
    return port1, port2, dict(z_top=z_top, z_bot=z_bot, x_lo=x_lo, x_hi=x_hi, y_half=y_half, z_meas1=z_meas1,
                              l_coax_mm=z_meas1 - Z_F, l_msl_mm=x_trace - 0.5 - tl)


def run(sim_path=None, keep=False, threads=0, verbose=0, f_max=12e9, nrts=60000, end_crit=1e-4, nfreq=1601, **geo):
    sim_path = sim_path or tempfile.mkdtemp(prefix="oems_cl_")
    os.makedirs(sim_path, exist_ok=True)
    FDTD = openEMS(NrTS=nrts, EndCriteria=end_crit)
    FDTD.SetGaussExcite(f_max / 2, f_max / 2)
    FDTD.SetBoundaryCond(["PML_%d" % NPML] * 6)
    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(UNIT)
    p1, p2, ext = build(CSX, FDTD, mesh, f0=f_max / 2, **geo)
    nx, ny, nz = (len(mesh.GetLines(a)) for a in "xyz")
    FDTD.Run(sim_path, cleanup=True, numThreads=threads, verbose=verbose)
    f = np.linspace(10e6, f_max, nfreq)
    p1.CalcPort(sim_path, f)
    z_coax = np.array(p1.Z_ref, dtype=complex)
    p1.CalcPort(sim_path, f, ref_impedance=50)
    p2.CalcPort(sim_path, f)
    z_msl = np.array(p2.Z_ref, dtype=complex)
    p2.CalcPort(sim_path, f, ref_impedance=50)
    out = dict(f=f, s11=p1.uf_ref / p1.uf_inc, s21=p2.uf_ref / p1.uf_inc, z_coax=z_coax, z_msl=z_msl,
               grid=(nx, ny, nz), ncells=nx * ny * nz, sim_path=sim_path, geo=dict(geo), ext=ext)
    if not keep:
        shutil.rmtree(sim_path, ignore_errors=True)
    return out


def deembed(f, s11, s21, l_coax_mm, l_msl_mm, eps_msl=None):
    """Rotate the port planes back to the board's face and the pad's edge (the study's analyze_launch.deembed)."""
    eps_msl = eps_msl or 3.0
    b1 = 2 * np.pi * f * np.sqrt(COAX["er_ptfe"]) / C0 * (l_coax_mm * 1e-3)
    b2 = 2 * np.pi * f * np.sqrt(eps_msl) / C0 * (l_msl_mm * 1e-3)
    return s11 * np.exp(2j * b1), s21 * np.exp(1j * (b1 + b2))


def lumped_fit(f, s11, s21, fmax=8e9, z0=50.0):
    """Shunt C / series L / delay fit of a single launch (the study's measured.launch_lumped_fit)."""
    from scipy.optimize import least_squares
    m = f <= fmax
    fm, s11m, s21m = f[m], s11[m], s21[m]
    w = 2 * np.pi * fm

    def model(p):
        C, L, tau = p
        A = np.zeros((len(fm), 2, 2), complex); A[:, 0, 0] = 1; A[:, 1, 1] = 1; A[:, 1, 0] = 1j * w * C * 1e-12
        B = np.zeros_like(A); B[:, 0, 0] = 1; B[:, 1, 1] = 1; B[:, 0, 1] = 1j * w * L * 1e-9
        M = A @ B
        ph = np.exp(-1j * w * tau * 1e-12)
        a, b, c, d = M[:, 0, 0], M[:, 0, 1], M[:, 1, 0], M[:, 1, 1]
        den = a + b / z0 + c * z0 + d
        return ((a + b / z0 - c * z0 - d) / den, 2 * ph / den)

    def resid(p):
        e11, e21 = model(p)
        return np.concatenate([np.abs(e11 - s11m), np.abs(e21 - s21m)])
    r = least_squares(resid, [0.5, 1.0, 20.0], bounds=([0.0, 0.0, 0.0], [8.0, 10.0, 300.0]))
    return dict(C_pF=r.x[0], L_nH=r.x[1], tau_ps=r.x[2], rms=float(np.sqrt(np.mean(r.fun ** 2))))


def tdr(f, s11, n_fft=16384, rise_frac=0.7, z0=50.0):
    fmax = f[-1]
    df = fmax / (n_fft // 2)
    grid = np.arange(n_fft // 2 + 1) * df
    H = (np.interp(grid, f, s11.real) + 1j * np.interp(grid, f, s11.imag))
    H[0] = H[1].real
    w = np.ones_like(grid)
    e = grid > rise_frac * fmax
    w[e] = 0.5 * (1 + np.cos(np.pi * (grid[e] - rise_frac * fmax) / ((1 - rise_frac) * fmax)))
    step = np.cumsum(np.fft.irfft(H * w, n=n_fft))
    t = np.arange(n_fft) / (n_fft * df)
    with np.errstate(divide="ignore", invalid="ignore"):
        z = z0 * (1 + step) / (1 - step)
    return t, step, z


def metrics(r):
    f, s11, s21 = r["f"], r["s11"], r["s21"]
    ext = r["ext"]
    l_coax = ext["z_meas1"] - Z_F                 # (a cached run may carry the earlier, wrong l_coax_mm)
    s11d, s21d = deembed(f, s11, s21, l_coax, ext["l_msl_mm"])
    i58 = int(np.argmin(abs(f - 5.8e9)))
    band = (f >= 4e9) & (f <= 6e9)
    fit = lumped_fit(f, s11d, s21d)
    t, step, z = tdr(f, s11d)
    tw = (t > 0) & (t < 120e-12)
    return dict(s11_58=float(20 * np.log10(abs(s11d[i58]))), il_58=float(-20 * np.log10(abs(s21d[i58]))),
                refl_58=float(abs(s11d[i58]) ** 2), s11_worst_46=float(20 * np.log10(abs(s11d[band]).max())),
                il_worst_06=float((-20 * np.log10(abs(s21d[f <= 6e9]))).max()),
                z_tdr_min=float(np.nanmin(z[tw])) if tw.any() else float("nan"),
                C_pF=fit["C_pF"], L_nH=fit["L_nH"], fit_rms=fit["rms"], ncells=int(r["ncells"]),
                z_msl_58=float(r["z_msl"][i58].real))


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--antipad", type=float, default=1.8)
    ap.add_argument("--threads", type=int, default=6)
    a = ap.parse_args()
    r = run(threads=a.threads, antipad=a.antipad)
    print(json.dumps(metrics(r), indent=1))
