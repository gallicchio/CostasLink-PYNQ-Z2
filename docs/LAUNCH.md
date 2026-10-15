# The SMA launches at 5.8 GHz, in the gerbers and in a field solver (Prompt 33, 2026-10-14)

Jason: "Are the connectors going to reflect 5.8 GHz?  We did a whole study in the SYZYGY board because some
KiCad defaults were not right ... Make sure that all 5-6 GHz connectors have proper capacitance and inductance
*in the gerbers*."  And: "There are several SMA test boards within the SYZYGY directory where we did 3D EM
simulations.  Make sure that these launches are not going to cause us issues like our test boards did.  In the
end, your simulations matched the latest SMA test board well enough.  I'd rather spend design time and
simulation time here to get it right."

## 1. What the gerbers said before this

`tools/launch_check.py` reads the plotted copper layers (not the board file: a DRC rule the fill never applied
is exactly the kind of thing that only the gerbers show).  On build 36's release:

| | In1 | In2 | B.Cu | F.Cu |
|---|---|---|---|---|
| copper nearest each SMA's centre pin | 0.90 mm | 0.90 mm | 1.25 mm (the pad ring + 0.25) | the 2.0 mm pad, the pour 0.25 mm off it |
| pad flash at the pin | none (Prompt 31's `remove_unused_layers` worked) | none | the 2.0 mm ring | the 2.0 mm pad |

So the inner planes stood 0.90 mm from the pin — a 1.8 mm antipad, *smaller* than the 2.5 mm the board review
had measured, because the "SMA launch antipad" DRC rule meant to hold them 1.35 mm off (Prompt 31) had a
property in its condition that never matched, and the fill fell back to the hole-to-copper clearance.  The
2.0 mm top pad sat over In1 at 0.21 mm (about 0.4 pF on its own).  The 5.8 GHz U.FL taps' centre pads and the
ADL5611s' 1.3 x 0.9 mm RF pads had In1 directly under them.

## 2. What the SyzygyRadioDrivers study found, and what carries over

`../SyzygyRadioDrivers/SMABridgeTestAnalysis/` (FIELD_SOLVER.md, V3_TEST_BOARD.md): a vertical through-hole SMA
on JLCPCB's 6-layer JLC06161H-3313 stack, modelled in openEMS (3D FDTD) and checked against two test boards on
a VNA.  Its as-built launch reflected 70 % of the power at 5.8 GHz; four changes that cost nothing to
fabricate took that to 20 %: the signal pad on F.Cu and B.Cu only (`remove_unused_layers`), the inner
antipad opened to 4.0-4.6 mm (a plateau; 5.0 turns over because the launch loses the ground it references),
a smaller pad (1.95 mm) with a 1.0 mm taper to the line, and the pad's clearance to the top pour 0.9 mm
instead of the netclass gap.  The pin that protrudes below the board is an open stub worth a further 2 dB
and stays (cutting it is a lab option, not a build instruction); the B.Cu pour's clearance from the pad is
the only lever on it, and it saturates at 1.2 mm.  The V3 test board's optimised lines measured
S11 −12.7 to −15.1 dB at 5.8 GHz (3-5 % reflected) with the launch at 55-57 Ω on the TDR.

What carries over to this board unchanged: the pad on the outer layers only, the taper, the pad clearance,
the B.Cu clearance, and the principle that the antipad has an interior optimum.  What does not: the numbers.
This board is a 4-layer JLC04161H-7628 stack (0.21 mm prepreg over a 1.065 mm core, two planes instead of
four), and the connector is Bat Wireless' BWSMA-KWE-Z001, a right-angle jack with vertical pins (0.9 mm centre
pin in JLCPCB's 1.3 mm hole and 2.0 mm pad, four 0.9 mm square legs at ±2.55 mm in 1.6 mm holes; the pins
stand 1.9 mm proud of the 1.6 mm board).  The barrel crosses more dielectric with fewer plane edges, so the
optimum is found again rather than copied.

## 3. The model

`sim/launch/launch_cl.py` is the study's `launch_model.py` (MODEL_REV 7) with this board's stack and connector
substituted and nothing else changed: zero-thickness PEC planes on the faces that bound each dielectric, the
antipads as vacuum cylinders of higher priority than the planes, a 50 Ω PTFE coax port feeding the pin from
above (the right-angle jack's own bend is the maker's; the PCB side is what is modelled), the plated barrel,
the four legs, the pin and legs below the board, a solder cone on the B.Cu pad, the CPWG line (0.29 mm, 0.25
gaps) with this board's via fence (0.45 mm vias at ±0.845 mm every 1.2 mm), PML on all six faces, and the
study's mesh rules (thirds-rule lines on the strip edges, graded air above the strip).  `sim/launch/check_cl.py`
flood-fills openEMS's own rasterised metal first: on every geometry below the signal net is isolated from the
pour and reaches the far end of the line.  `sim/launch/sweep_cl.py` runs the sweeps six solves at a time and
caches each geometry; the metrics (de-embedded to the board's face and the pad's edge, a shunt-C / series-L
fit, a step TDR) are the study's.

**The anchor.**  Before trusting it on our geometry, the study's own optimised point (its stack, its
connector, antipad 4.2, its SWEEP mesh) was re-run here with the study's code: S11 −7.135 dB and insertion loss 0.426 dB at 5.8 GHz on 2.046 M cells, against the study's cached −7.13 dB / 0.43 dB on the same cell count (`sim/launch/anchor/anchor.json`): this machine and environment give the study's answer.  (Its 0.54 pF fit is on the raw port S-parameters; the 0.68 pF here is the same fit after de-embedding to the board's face, which is the convention the tables below use.)

## 4. Results

### 4.1 What was built, what is designed, what the study's lessons add (the SWEEP mesh, 1.1-2.0 M cells, 20-45 min a solve)

The loss column is the **mismatch loss** implied by |S11|, −10·log10(1 − |S11|²), a lower bound on the launch's
loss: openEMS's line port is not passive on this mesh (|S11|² + |S21|² = 1.09 at 5.8 GHz on the SWEEP mesh, 1.02
on the FINE one), so the raw |S21| would flatter every row by 0.1-0.4 dB.  |S11| is what the study validated.

| geometry | antipad | pad | taper | pad clearance | B.Cu clearance | S11 at 5.8 GHz | reflected | mismatch loss | worst S11 4-6 GHz | shunt C | series L | TDR dip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| build 36 as plotted (antipad 1.8, planes 0.9 mm off the pin) | 1.8 | 2.0 | 0.0 | 0.25 | 0.25 | **-0.7 dB** | **85 %** | 8.2 dB | -0.6 dB | 2.09 pF | 0.0 nH | 27 Ω |
| build 36 but no pin below the board | 1.8 | 2.0 | 0.0 | 0.25 | 0.25 | **-0.8 dB** | **82 %** | 7.5 dB | -0.7 dB | 1.96 pF | 0.0 nH | 29 Ω |
| build 37 as designed (2.2 mm voids, line meets the pad) | 4.4 | 2.0 | 0.0 | 0.25 | 1.2 | **-5.4 dB** | **29 %** | 1.5 dB | -5.1 dB | 0.64 pF | 0.1 nH | 71 Ω |
| 37 + pad clearance 0.9 **(build 38)** | 4.4 | 2.0 | 0.0 | 0.9 | 1.2 | **-7.1 dB** | **19 %** | 0.92 dB | -6.7 dB | 0.49 pF | 0.2 nH | 69 Ω |
| 37 + clearance 0.9 + taper 1.0 | 4.4 | 2.0 | 1.0 | 0.9 | 1.2 | **-7.1 dB** | **19 %** | 0.94 dB | -6.7 dB | 0.58 pF | 0.5 nH | 69 Ω |
| candidate: clearance 0.9, taper 1.0, pad 1.85 | 4.4 | 1.85 | 1.0 | 0.9 | 1.2 | **-7.6 dB** | **17 %** | 0.81 dB | -7.2 dB | 0.55 pF | 0.5 nH | 69 Ω |

Three things to read off it.  **Build 36's launch, as its gerbers had it, reflected 85 % of the power**, 8 dB
of mismatch loss per launch: far worse than the study's as-built (70 %), because on this stack the barrel
crosses a 1.065 mm core 0.25 mm from the plane's edge (2.1 pF, a 27 Ω dip).  Two launches on the TX chain alone
would have cost 16 dB.  **The 2.2 mm voids of build 37 take that to 29 %** (1.5 dB), the single change worth
most.  **The study's pad clearance (0.9 mm from the pad to the top pour instead of the CPWG's 0.25) is the next
lever**, 29 → 19 % (0.6 dB): the pour hugging a 2 mm pad over a 0.21 mm prepreg is the capacitance.  The taper
is worth nothing here (the line is already 0.29 mm wide against a 2 mm pad) and the smaller pad 2 %.  The
protruding pin, which the study found worth 2 dB on its stack, is worth 0.7 dB of the 8 on build 36 (its stub
is 1.9 mm, not 2.4, and that launch was dominated by the barrel).

The candidate (voids 4.4 mm, pad 1.85 mm with a 1.0 mm taper, 0.9 mm pad clearance, B.Cu 1.2 mm off the pad)
sits at **17 % reflected, 0.8 dB** per launch at 5.8 GHz and −7.2 dB worst over 4-6 GHz, with 0.55 pF of shunt
capacitance: the same figures the study's optimised launch gives on its own stack (20-22 %, 0.54 pF), which that
study's V3 test board then measured at −12.7 to −15.1 dB (3-5 %), the model running pessimistic above 5 GHz.

### 4.2 The antipad, the clearances, the bounds and the mesh (the candidate varied one knob at a time)

| variation | S11 at 5.8 GHz | reflected | mismatch loss | worst S11 4-6 GHz | shunt C | series L | TDR dip | cells |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| antipad 3.4 | -6.2 dB | 24 % | 1.20 dB | -5.8 dB | 0.67 pF | 0.41 nH | 70.6 Ω | 2.0 M |
| antipad 4.0 | -7.2 dB | 19 % | 0.91 dB | -6.8 dB | 0.58 pF | 0.48 nH | 69.0 Ω | 1.9 M |
| **antipad 4.4 (the candidate; the board's 2.2 mm voids)** | -7.6 dB | 17 % | 0.81 dB | -7.2 dB | 0.55 pF | 0.52 nH | 69.3 Ω | 1.8 M |
| antipad 4.8 | -7.6 dB | 17 % | 0.82 dB | -7.2 dB | 0.54 pF | 0.55 nH | 68.5 Ω | 1.9 M |
| antipad 5.2 | -7.6 dB | 18 % | 0.84 dB | -7.1 dB | 0.54 pF | 0.57 nH | 68.6 Ω | 1.8 M |
| B.Cu clearance 0.6 (the pin's stub nearer the back pour) | -6.3 dB | 23 % | 1.15 dB | -5.9 dB | 0.65 pF | 0.51 nH | 70.5 Ω | 1.7 M |
| B.Cu clearance 2.0 | -7.7 dB | 17 % | 0.82 dB | -7.2 dB | 0.54 pF | 0.52 nH | 68.4 Ω | 1.7 M |
| pad clearance 1.3 (top pour) | -7.9 dB | 16 % | 0.77 dB | -7.5 dB | 0.54 pF | 0.56 nH | 67.9 Ω | 1.8 M |
| pad 2.0 with the taper | -7.1 dB | 19 % | 0.94 dB | -6.7 dB | 0.58 pF | 0.51 nH | 69.4 Ω | 1.6 M |
| **bound: no pin, legs or solder below the board** | -8.7 dB | 13 % | 0.62 dB | -8.3 dB | 0.48 pF | 0.50 nH | 67.3 Ω | 1.2 M |
| inner-layer rings kept (`remove_unused_layers no`) | -6.8 dB | 21 % | 1.01 dB | -6.4 dB | 0.60 pF | 0.52 nH | 69.9 Ω | 1.7 M |
| **the candidate on the FINE mesh** (convergence) | -8.3 dB | 15 % | 0.70 dB | -7.9 dB | 0.52 pF | 0.52 nH | 67.2 Ω | 3.7 M |
| **final (build 38): voids 4.4, pad 2.0, clearance 0.9, no taper** | -7.1 dB | 19 % | 0.93 dB | -6.7 dB | 0.49 pF | 0.19 nH | 69.3 Ω | 1.6 M |
| **final on the FINE mesh** | -7.9 dB | 16 % | 0.78 dB | -7.5 dB | 0.45 pF | 0.17 nH | 67.9 Ω | 3.7 M |
| final, the centre pin clipped to 0.3 mm under the board | -8.0 dB | 16 % | 0.75 dB | -7.6 dB | 0.43 pF | 0.19 nH | 68.2 Ω | 1.4 M |
| final but the 1.85 mm pad (no taper) | -7.5 dB | 18 % | 0.84 dB | -7.1 dB | 0.47 pF | 0.20 nH | 68.6 Ω | 1.6 M |

What it says.  **The antipad curve has its knee at 4.4 mm**: 3.4 → 4.0 → 4.4 mm is 24 → 19 → 17 %, and 4.8 and
5.2 mm give the same 17 %, so the 2.2 mm voids the board already has sit on the plateau, and a bigger hole in
the planes would only take ground away from the parts beside the SMA.  **The B.Cu clearance matters below
1.2 mm** (0.6 mm: 23 %) and not above it.  **The top pour's clearance is on its plateau at 0.9 mm** (1.3 mm:
one point better, within the mesh error).  **The pin stub under the board is what is left**: with no pin, legs
or solder below the board the same launch reflects 13 %, so 4 of the 17 points are the connector's own 1.9 mm
of pin and its legs, which the board cannot change (clipping the centre pin after soldering can: the row below).
**Keeping the inner-layer rings would cost 4 points** (21 %), which is what Prompt 31's `remove_unused_layers`
bought.  **The mesh**: the FINE mesh (3.7 M cells, twice the resolution in the launch and in the dielectric
stack) puts the candidate at 15 % instead of 17 %, so the SWEEP numbers are pessimistic by about 0.7 dB in
|S11|, in the same direction as the study's model against its measured test board.  The lumped fit is stable
across the sweep (0.5-0.6 pF; 0.5 nH with the study's taper, which is a 1 mm neck, 0.2 nH without): **the
capacitance and inductance in the gerbers** are those, against the 2.1 pF build 36 had (its fit needs no L: the
27 Ω dip is all capacitance).  The last four rows are the geometry that went into the board: 19 % on the SWEEP
mesh and **16 % on the FINE mesh**; clipping the centre pin to 0.3 mm after soldering is worth 3 points (the
stub is a capacitor against the back pour), and the 1.85 mm pad without its taper 1 point.

## 5. What went into the board (build 38)

| knob | value | where | why |
|---|---|---|---|
| voids on In1, In2 and B.Cu round each 5.8 GHz SMA pin | radius 2.2 mm (antipad 4.4) | `gen/rf_launch.LAUNCH_R` → rule areas from `gen/routes.rf_voids` | the knee of the antipad curve; already build 37's |
| the centre pad's clearance to the top pour | 0.9 mm | `LAUNCH_CLEAR` → an F.Cu rule area of radius 1.9 mm round each launch pin (`rf_voids`); not a pad property, which KiCad would apply to every SMA, layer and track | 29 → 19 %: the one lever left after the voids |
| the centre pad | 2.0 mm, JLCPCB's land pattern | `LAUNCH_PAD_OD` | 1.85 mm is worth 2 points, inside the mesh error, and takes the annulus on the 1.3 mm hole from 0.35 to 0.275 mm (JLCPCB's floor is 0.25) |
| a taper from the pad to the line | none | `LAUNCH_TAPER = 0` | worth nothing at 5.8 GHz against a 0.29 mm line; one custom pad fewer in the gerbers |
| the B.Cu pour's clearance to the pin stub | 1.2 mm | the same rule areas (2.2 mm) | on the plateau (0.6 mm costs 6 points) |
| the inner-layer rings | none | `remove_unused_layers yes` (Prompt 31) | 4 points |

The expected launch, by the model that ran 20 % pessimistic on the study's V3 test board: **−7.1 dB return loss at
5.8 GHz on the SWEEP mesh (19 % reflected, 0.9 dB), −7.9 dB (16 %, 0.8 dB) on the FINE mesh**, −6.7 dB worst over 4-6
GHz, 0.5 pF shunt and 0.2 nH series; five launches on the board, two in any one path.  Clipping the centre
pins to 0.3 mm under the board after assembly takes 3 points more (BRINGUP.md step 0); the 1.85 mm pad without
the taper would have taken 1, for an annulus at JLCPCB's floor, and was not taken.

What the release gate measures in build 38's gerbers (`tools/launch_check.py`, run by `mfg/make_release.py`):
no flash at any of the five pins on In1 or In2; the nearest In1, In2 and B.Cu copper 2.20 mm from each pin; the
nearest F.Cu pour 1.90 mm from each pin (the 1.0 mm pad radius and the 0.9 mm clearance); In1 clear to 0.65 mm
round each of the ten relieved pads.

## 6. Reproducing

```bash
cd sim/launch
em-env python check_cl.py                    # the rasterised metal: isolated, connected
NPAR=6 NTHREAD=4 em-env python sweep_cl.py asbuilt design antipad clear bound final converge   # ~3 h on 32 cores
python3 tools/launch_check.py mfg/release/gerbers   # the gate the release runs
```

`em-env` is the study's openEMS environment (`~/.local/bin/em-env`: openEMS 0.37, CSXCAD, scikit-rf).  The
cached solves are in `sim/launch/cache/` (not in git); `sim/launch/out/*.csv` are the tables above.
