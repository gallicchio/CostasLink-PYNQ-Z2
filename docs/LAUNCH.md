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

### 4.1 What was built, what is designed, what the study's lessons add (the SWEEP mesh, 1.1-1.7 M cells, 20-35 min a solve)

| geometry | antipad | pad | taper | pad clearance | B.Cu clearance | S11 at 5.8 GHz | reflected | loss per launch | worst S11 4-6 GHz | shunt C | TDR dip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| build 36 as plotted (antipad 1.8, planes 0.9 mm off the pin) | 1.8 | 2.0 | 0.0 | 0.25 | 0.25 | **-0.7 dB** | **85 %** | 8.01 dB | -0.6 dB | 2.09 pF | 27 Ω |
| build 36 but no pin below the board | 1.8 | 2.0 | 0.0 | 0.25 | 0.25 | **-0.8 dB** | **82 %** | 7.28 dB | -0.7 dB | 1.96 pF | 29 Ω |
| build 37 as designed (2.2 mm voids, line meets the pad) | 4.4 | 2.0 | 0.0 | 0.25 | 1.2 | **-5.4 dB** | **29 %** | 1.11 dB | -5.1 dB | 0.64 pF | 71 Ω |
| 37 + pad clearance 0.9 | 4.4 | 2.0 | 0.0 | 0.9 | 1.2 | **-7.1 dB** | **19 %** | 0.44 dB | -6.7 dB | 0.49 pF | 69 Ω |
| 37 + clearance 0.9 + taper 1.0 | 4.4 | 2.0 | 1.0 | 0.9 | 1.2 | **-7.1 dB** | **19 %** | 0.45 dB | -6.7 dB | 0.58 pF | 69 Ω |
| candidate: clearance 0.9, taper 1.0, pad 1.85 | 4.4 | 1.85 | 1.0 | 0.9 | 1.2 | **-7.6 dB** | **17 %** | 0.37 dB | -7.2 dB | 0.55 pF | 69 Ω |

Three things to read off it.  **Build 36's launch, as its gerbers had it, reflected 85 % of the power** and lost
8 dB per launch: far worse than the study's as-built (70 %), because on this stack the barrel crosses a 1.065 mm
core 0.25 mm from the plane's edge (2.1 pF, a 27 Ω dip).  Two launches on the TX chain alone would have cost
16 dB.  **The 2.2 mm voids of build 37 take that to 29 %** (1.1 dB) — the single change worth most.  **The study's
pad clearance (0.9 mm from the pad to the top pour instead of the CPWG's 0.25) is the next lever**, 29 → 19 %
(0.67 dB): the pour hugging a 2 mm pad over a 0.21 mm prepreg is the capacitance.  The taper is worth nothing
here (the line is already 0.29 mm wide against a 2 mm pad) and the smaller pad 2 %.  The protruding pin, which the
study found worth 2 dB on its stack, is worth 0.7 dB of the 8 here (its stub is 1.9 mm, not 2.4, and the launch
is dominated by the barrel).

The candidate (voids 4.4 mm, pad 1.85 mm with a 1.0 mm taper, 0.9 mm pad clearance, B.Cu 1.2 mm off the pad)
sits at **17 % reflected, 0.37 dB** per launch at 5.8 GHz and −7.2 dB worst over 4-6 GHz, with 0.55 pF of shunt
capacitance: the same figures the study's optimised launch gives on its own stack (20-22 %, 0.54 pF), which that
study's V3 test board then measured at −12.7 to −15.1 dB (3-5 %), the model running pessimistic above 5 GHz.

### 4.2 The antipad, the clearances, the bounds and the mesh

@@RESULTS2@@

## 5. What went into the board

(the antipad / clearance sweep is running; the decision and the rebuilt gerbers follow it)

## 6. Reproducing

```bash
cd sim/launch
em-env python check_cl.py                    # the rasterised metal: isolated, connected
NPAR=6 NTHREAD=4 em-env python sweep_cl.py asbuilt design antipad clear bound converge   # ~1-2 h on 32 cores
python3 tools/launch_check.py mfg/release/gerbers   # the gate the release runs
```

`em-env` is the study's openEMS environment (`~/.local/bin/em-env`: openEMS 0.37, CSXCAD, scikit-rf).  The
cached solves are in `sim/launch/cache/` (not in git); `sim/launch/out/*.csv` are the tables above.
