#!/usr/bin/env python3
"""Reproduce one cached point of the SyzygyRadioDrivers launch study with its own code, as the anchor that this
machine and environment give the same answer the study's document rests on: OPTIMISED, antipad 4.2, the SWEEP
mesh (out/sweep_final.csv: s11_58 -7.13 dB, il_58 -0.43 dB, C 0.54 pF).  Run with em-env from the study's
fieldsolver directory on sys.path; writes anchor.json beside this file."""
import os, sys, json, time
import numpy as np
FS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "SyzygyRadioDrivers", "SMABridgeTestAnalysis", "fieldsolver")
sys.path.insert(0, os.path.abspath(FS))
os.chdir(os.path.abspath(FS))
import launch_model as LM, sweep_launch as SW
from analyze_launch import deembed
from measured import launch_lumped_fit
geo = dict(SW.OPTIMISED); geo["antipad"] = 4.2
t0 = time.time()
r = LM.run(threads=int(os.environ.get("NTHREAD", "6")), verbose=0, **geo, **SW.SWEEP)
f, s11, s21 = r["f"], r["s11"], r["s21"]
s11d, s21d = deembed(f, s11, s21)
i = int(np.argmin(abs(f - 5.8e9)))
fit = launch_lumped_fit(f, s11d, s21d)
out = dict(s11_58=20*np.log10(abs(s11d[i])), il_58=20*np.log10(abs(s21d[i])), C_pF=fit["C_pF"], L_nH=fit["L_nH"],
           ncells=r["ncells"], seconds=time.time()-t0, reference=dict(s11_58=-7.13, il_58=-0.43, C_pF=0.54))
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "anchor.json"), "w"), indent=1)
print(out)
