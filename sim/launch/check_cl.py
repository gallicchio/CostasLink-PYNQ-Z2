#!/usr/bin/env python3
"""Is the signal net isolated from ground in the mesh openEMS builds for launch_cl.py?  The study's
check_model.py on this model: run the real rasteriser (--debug-PEC) and flood-fill the PEC edges from the pad's
centre; reaching the pour means a short the geometry did not intend (a Yee cell bridging a gap).

    em-env python check_cl.py        checks the as-plotted, designed and candidate geometries
"""
import os, shutil, tempfile
from collections import deque
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy
from CSXCAD import ContinuousStructure
from openEMS import openEMS
import launch_cl as LM


def pec_nodes(**geo):
    sp = tempfile.mkdtemp(prefix="pec_cl_")
    FDTD = openEMS(NrTS=10, EndCriteria=1e-2)
    FDTD.SetGaussExcite(6e9, 6e9)
    FDTD.SetBoundaryCond(["PML_8"] * 6)
    CSX = ContinuousStructure()
    FDTD.SetCSX(CSX)
    mesh = CSX.GetGrid()
    mesh.SetDeltaUnit(LM.UNIT)
    LM.build(CSX, FDTD, mesh, **geo)
    FDTD.Run(sp, cleanup=True, verbose=0, setup_only=True, debug_PEC=True)
    rd = vtk.vtkXMLPolyDataReader()
    rd.SetFileName(os.path.join(sp, "PEC_dump.vtp"))
    rd.Update()
    out = rd.GetOutput()
    p = vtk_to_numpy(out.GetPoints().GetData()) * 1e3
    lines = vtk_to_numpy(out.GetLines().GetData()).reshape(-1, 3)[:, 1:]
    shutil.rmtree(sp, ignore_errors=True)
    return p, lines


def check(tag, **geo):
    p, lines = pec_nodes(**geo)
    adj = {}
    for a, b in lines:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    nearest = lambda x, y, z: int(np.argmin(np.sum((p - np.array([x, y, z])) ** 2, axis=1)))
    start = nearest(0.0, 0.0, LM.Z_F)
    goal = nearest(0.0, 0.92 * p[:, 1].max(), LM.Z_F)
    par = {start: None}
    q = deque([start])
    while q:
        n = q.popleft()
        if n == goal:
            break
        for m in adj.get(n, ()):
            if m not in par:
                par[m] = n
                q.append(m)
    shorted = goal in par
    # and the signal must reach the far end of the line (the pad stack is connected through the barrel)
    far = nearest(0.9 * p[:, 0].max(), 0.0, LM.Z_F)
    print("%-50s PEC edges %6d; signal net %6d nodes; %s; line's far end %s"
          % (tag, len(lines), len(par), "SHORTED TO THE POUR" if shorted else "isolated from the pour: OK",
             "reached" if far in par else "NOT reached"))
    return (not shorted) and (far in par)


if __name__ == "__main__":
    import sweep_cl as SW
    mk = {k: v for k, v in SW.SWEEP.items() if k != "nrts"}
    ok = True
    for tag, geo in (("build 36 as plotted", SW.AS_PLOTTED_36), ("build 37 as designed", SW.DESIGN_37), ("candidate", SW.CANDIDATE),
                     ("candidate, inner pads kept", dict(SW.CANDIDATE, inner_pads=True))):
        ok &= check(tag, **geo, **mk)
    raise SystemExit(0 if ok else 1)
