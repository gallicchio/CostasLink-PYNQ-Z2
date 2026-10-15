#!/usr/bin/env python3
"""Drive launch_cl.py over the CostasLink launch's design space, several solves at a time (the study's
sweep_launch.py pattern: openEMS is memory-bandwidth bound, so 7 jobs of 4 threads use 32 cores).

    em-env python sweep_cl.py <sweep> [...]     sweeps: asbuilt, design, antipad, clear, bound, converge, all

Results are cached per geometry in cache/<key>.npz (keyed by MODEL_REV) and tabulated in out/<sweep>.csv.
"""
import csv, hashlib, os, sys, time
from multiprocessing import Pool
import numpy as np
import launch_cl as LM

HERE = os.path.dirname(os.path.abspath(__file__))
OUT, CACHE = os.path.join(HERE, "out"), os.path.join(HERE, "cache")
SWEEP = dict(res_trace=0.050, res_fine=0.130, nz_prepreg=7, nz_core=7, nrts=55000, res_far=0.50, res_coax=0.30,
             win=3.6, x_trace=6.0, coax_len=4.5)
FINE = dict(res_trace=0.035, res_fine=0.090, nz_prepreg=9, nz_core=9, nrts=90000, res_far=0.40, res_coax=0.25,
            win=4.0, x_trace=7.0, coax_len=5.0)
NPAR = int(os.environ.get("NPAR", 7))
NTHREAD = int(os.environ.get("NTHREAD", 4))

# the geometries that matter
AS_PLOTTED_36 = dict(antipad=1.8, bcu_clear=0.25, fcu_clear=0.25, trace_gap=0.25, taper_len=0.0, pad_od=2.0)   # build 36's gerbers
DESIGN_37 = dict(antipad=4.4, bcu_clear=1.2, fcu_clear=0.25, trace_gap=0.25, taper_len=0.0, pad_od=2.0)        # the rule areas
CANDIDATE = dict(antipad=4.4, bcu_clear=1.2, fcu_clear=0.9, trace_gap=0.25, taper_len=1.0, pad_od=1.85)        # the study's lessons applied


def key_of(geo, mesh):
    items = sorted({**geo, **mesh}.items())
    s = "rev%d_" % LM.MODEL_REV + "_".join("%s%s" % (k, v) for k, v in items)
    return s if len(s) < 180 else s[:140] + "_" + hashlib.sha1(s.encode()).hexdigest()[:12]


def one(job):
    tag, geo, mesh = job["tag"], job["geo"], job["mesh"]
    key = key_of(geo, mesh)
    path = os.path.join(CACHE, key + ".npz")
    if os.path.exists(path):
        d = np.load(path, allow_pickle=True)
        r = dict(f=d["f"], s11=d["s11"], s21=d["s21"], z_msl=d["z_msl"], ncells=int(d["ncells"]), ext=d["ext"].item())
        return tag, geo, LM.metrics(r), 0.0
    t0 = time.time()
    r = LM.run(threads=NTHREAD, verbose=0, **geo, **mesh)
    os.makedirs(CACHE, exist_ok=True)
    np.savez(path, f=r["f"], s11=r["s11"], s21=r["s21"], z_msl=r["z_msl"], ncells=r["ncells"], ext=np.array(r["ext"], dtype=object), key=key)
    return tag, geo, LM.metrics(r), time.time() - t0


def jobs_for(name):
    J = []
    def add(tag, mesh=SWEEP, **geo):
        J.append(dict(tag=tag, geo=geo, mesh=mesh))
    if name in ("asbuilt", "all"):
        add("build 36 as plotted (antipad 1.8, planes 0.9 mm off the pin)", **AS_PLOTTED_36)
        add("build 36 but no pin below the board", **dict(AS_PLOTTED_36, pin_below=0, legs_below=0, solder_h=0))
    if name in ("design", "all"):
        add("build 37 as designed (2.2 mm voids, line meets the pad)", **DESIGN_37)
        add("37 + pad clearance 0.9", **dict(DESIGN_37, fcu_clear=0.9))
        add("37 + clearance 0.9 + taper 1.0", **dict(DESIGN_37, fcu_clear=0.9, taper_len=1.0))
        add("candidate: clearance 0.9, taper 1.0, pad 1.85", **CANDIDATE)
    if name in ("antipad", "all"):
        for d in (3.4, 4.0, 4.8, 5.2):
            add("candidate, antipad %.1f" % d, **dict(CANDIDATE, antipad=d))
    if name in ("clear", "all"):
        for c in (0.6, 2.0):
            add("candidate, B.Cu clearance %.1f" % c, **dict(CANDIDATE, bcu_clear=c))
        add("candidate, pad clearance 1.3", **dict(CANDIDATE, fcu_clear=1.3))
        add("candidate, pad 2.0", **dict(CANDIDATE, pad_od=2.0))
    if name in ("bound", "all"):
        add("candidate, no pin below (bound)", **dict(CANDIDATE, pin_below=0, legs_below=0, solder_h=0))
        add("candidate, inner pads kept (remove_unused_layers no)", **dict(CANDIDATE, inner_pads=True))
    if name in ("converge", "all"):
        add("candidate, fine mesh", mesh=FINE, **CANDIDATE)
    return J


def main(names):
    os.makedirs(OUT, exist_ok=True)
    for name in names:
        J = jobs_for(name)
        print("%s: %d job(s), %d at a time x %d threads" % (name, len(J), NPAR, NTHREAD), flush=True)
        with Pool(NPAR) as pool:
            res = pool.map(one, J)
        rows = []
        for tag, geo, m, secs in res:
            print("  %-56s S11(5.8) %6.2f dB  IL %5.2f dB  refl %4.0f %%  worst S11 4-6 GHz %6.2f  C %5.2f pF  L %5.2f nH  Zmin %5.1f  Zmsl %5.1f  %4.0f s"
                  % (tag, m["s11_58"], m["il_58"], 100 * m["refl_58"], m["s11_worst_46"], m["C_pF"], m["L_nH"], m["z_tdr_min"], m["z_msl_58"], secs), flush=True)
            rows.append(dict(tag=tag, **{k: geo.get(k, "") for k in ("antipad", "pad_od", "taper_len", "fcu_clear", "trace_gap", "bcu_clear", "inner_pads", "pin_below")}, **m, seconds=round(secs)))
        with open(os.path.join(OUT, name + ".csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main(sys.argv[1:] or ["all"])
