# CostasLink-PYNQ-Z2 rev A design review -- GPT-5.6Terra

## Verdict

**Do not order as-is.** The deciding issue is not KiCad connectivity: the 5.8 GHz CPWG and
two PCB quarter-wave couplers are deliberately ordered with *no impedance control*, despite the
project RF rule requiring it and the release allowing +/-20% geometry. The Costas filter is also
designed with a differential detector gain although U110 supplies one single-ended FDA output, so
the fitted loop is about 2.05 kHz and zeta = 0.484, rather than the claimed 3 kHz and zeta =
0.707. Correct and rebuild/recheck those two items before ordering. The T/R-plus-PA use case needs
an explicit safe hardware configuration; the other findings are pre-order release/gate work, not
evidence that the architecture should be abandoned.

## Findings

| Rank | Severity | Finding and location | Consequence if wrong | Fix | Confirmed by |
|---:|---|---|---|---|---|
| 1 | Would cost a respin | **The RF order waives impedance control.** [`mfg/release/ORDER_SETTINGS.md`](../mfg/release/ORDER_SETTINGS.md) requests "No requirement" while [`sim/rf_lines.py`](../sim/rf_lines.py) designs 0.29 mm / 0.25 mm CPWG and [`gen/sch_blocks.py`](../gen/sch_blocks.py) places two 7.3 mm PCB coupled-line couplers (CP101, CP201). | The RF input/output match, launches, and especially coupling/directivity are not held to their assumed impedance. DRC can pass while the 5.8 GHz radio does not. | Obtain the fabricator's controlled CPWG geometry/coupon for this stack, select impedance control, revise RF/coupler geometry if required, then rebuild DRC and release. | Order settings, RF source, copper renders, `CLAUDE_PCB.md` sections 13--14; independent corner calculation: 43.58--56.75 ohm for the release's stated +/-20% geometry. |
| 2 | Would cost a respin or RF rework | **The Costas detector gain is twice the implemented value.** U110 selects Q_P or Q_N, but [`sim/budget.py`](../sim/budget.py):341--350 assigns the full differential fast-arm peak to `Kd`. The PI filter is U112; fitted R126/R127 are 20 kOhm/750 Ohm. | The fitted outer loop is fn = 2.053 kHz, zeta = 0.484, not the claimed 3 kHz / 0.707. Pull-in, static-error, and hold claims are consequently false. | Use Kd = 0.1233 V/rad (one arm), not 0.2466 V/rad. For 3 kHz/zeta = 0.707 with 100 nF, fit R126 = 9.37 kOhm (9.53 k E96 or 10 k E24) and retain R127 = 750 Ohm; update assertions, sheet note, plan, and bring-up limits. | Re-derived from `sim/budget.py`, U110/U111/U112 in [`gen/sch_rx.py`](../gen/sch_rx.py), and `costas_gain_check.txt` in this directory. |
| 3 | Would risk damage and invalidate a field test | **The one-antenna switch path is not safe with the documented external PA.** U401/J401/J402/J403 carry the HMC536 path. The HMC536 is P0.1 = +27 dBm minimum / +29 dBm typical at 3 V control and 26 dB minimum isolation; the model operates the PA at +29.8 dBm. U101's stated RF-input absolute maximum is +1 dBm. | A typical leak is +2.8 dBm and a minimum-isolation leak is +3.8 dBm at the LNA, above its absolute maximum; the PA also drives the switch past its guaranteed P0.1 dB. | Make PA plus one-antenna operation impossible until a suitably rated switch and limiter/protection precede U101, or enforce/document a separate-antenna PA topology and <= +27 dBm at SW TX/ANT. Correct silk: P0.1 dB is not an absolute-safe limit. | HMC536 datasheet Table 1; [`sim/budget.py`](../sim/budget.py) section 2b; [`PLAN.md`](../PLAN.md) sections 14 and 18. |
| 4 | Would cost an assembly/debug day | **No board-local fiducials are present.** The release says the board carries "no rails or fiducials of its own" and relies on removable JLCPCB rails. The board/generator place no `FID*` footprint. | This violates `CLAUDE_PCB.md` section 5 and verification gate 15. Panel fiducials can work, but they are not the specified global/local marks for a 120 mm board with QFNs. | Add three global fiducials inside the outline, clear of edge connectors, plus local marks if JLCPCB requires them for the fine-pitch QFNs. Add layer markers, regenerate, and verify mask/paste/placement. | [`mfg/release/ORDER_SETTINGS.md`](../mfg/release/ORDER_SETTINGS.md), [`mfg/make_release.py`](../mfg/make_release.py), board source/render, `CLAUDE_PCB.md` section 5 and gate 15. |
| 5 | Would cost a bring-up/debug day | **The documented warning-clean gateware lint gate fails.** [`gateware/Makefile`](../gateware/Makefile) promises `lint: clean`, but `make lint` fails on `uart_cmd.v`'s `REP_HEX`/`rep_hex` similar-name warning and `rx_engine.v:99,114` writing shared loop variable `i` in two `always @*` blocks. | The claim that first gateware is checked is false for the supplied toolchain, and the shared procedural variable is unnecessarily simulator-dependent. | Rename the report register and give the priority encoders independent loop indices; run `make lint sim sim-engines sim-axil sim-driver` clean in a private copy and retain the log. | Private-copy test in `gateware-test.txt`; source locations above. |

## Detail

### 1. RF fabrication is not controlled

The design uses a 0.29 mm trace / 0.25 mm gap CPWG geometry on the selected
JLC04161H-7628 stack. The order pins the stack but selects **Impedance Control: No requirement**
and says the non-controlled process permits +/-20% width and spacing. The internal closed-form
model gives:

| Geometry | Calculated Z0 |
|---|---:|
| 0.29 mm / 0.25 mm nominal | 49.75 ohm |
| 0.23 mm trace / 0.30 mm gap | 56.75 ohm |
| 0.35 mm trace / 0.20 mm gap | 43.58 ohm |

The simple tracks may tolerate a few ohms. The two coupled-line structures do not merely carry
a short signal: their 7.3 mm quarter-wave lengths and gap set coupling, directivity, and
through-line match. The source validates its formula against JLCPCB's published *microstrip*
width, not a JLCPCB-controlled CPWG or coupled-line result. This is exactly where the board's RF
rule requires the fabricator's geometry and impedance control.

### 2. The Costas loop calculation counts both differential outputs

At the regulated -20 dBm demodulator level, the budget calculates 176 mV rms differential at the
fast-arm outputs, or 246.638 mV peak. That is valid for the TLV3601 inputs, which compare both
outputs. It is not the Costas detector voltage: JP101/JP102 feed U110's B1/B2 with Q_P/Q_N and
U110 selects one output. ERR is therefore a selected leg around V_MID, with a small-angle slope
of 123.319 mV/rad.

With fitted R126 = 20 kOhm, R127 = 750 Ohm, and C = 100 nF:

```text
Kd                0.123319 V/rad
Ko                2.70e6 rad/s/V
fn                2.053 kHz
zeta              0.484
```

The script instead assigns `Kd = vcmp_rms * 1.414` and calculates the target from the
differential amplitude. Its calculated R1 is 18.9 kOhm, while the fitted BOM is 20 kOhm, so the
claimed nominal is not the fitted nominal even before the factor-of-two correction. A 9.53 kOhm
R126 and the existing 750 Ohm R127 restore the stated target.

### 3. The PA and T/R switch cannot be combined as documented

The range model configures the external PA for +29.8 dBm output. HMC536's guaranteed P0.1 dB is
only +27 dBm at the selected control voltage and its guaranteed RFC-to-off-port isolation is
26 dB. Thus:

```text
Switch off-port leak: +29.8 dBm - 26 dB = +3.8 dBm
```

That reaches the receive port while the LNA remains attached, exceeding U101's +1 dBm absolute
maximum. The budget recognizes the same mechanism at a lower +27 dBm PA ("wants a limiter ahead
of the LNA"), but this board has no limiter, bypass routing, or interlock. Bare-board operation is
safe: +9.8 dBm - 26 dB = -16.2 dBm. The unsafe case is the advertised field configuration.

### 4. Manufacturing evidence and first firmware

The absence of local fiducials is explicit, not a missing render artifact. `gen/library.py`
vendors a fiducial footprint, yet neither placement nor board uses one. The release instead
depends on temporary assembly rails. Add production fiducials before the preview.

The four functional simulations passed in my private copy:

```text
make sim          PASS: tb_costaslink
make sim-engines  PASS: tb_engines
make sim-axil     PASS: tb_axil
make sim-driver   15 tests passed
```

This is useful behavioral coverage, but it does not make the combined verification target pass:
`make lint` fails before `make all` can be clean.

## Answers to the brief's review questions

### 3.1 Concept and purpose

For a rev-A experiment, a continuously tracked carrier and direct comparator event path are a
credible way to investigate the latency goal. An ADC/matched-filter path cannot win the stated
first-edge latency objective without converter/framing delay. The PYNQ header makes it a poor
final latency host, but its documented 8.8 ns penalty is acceptable for a prototype that also
compares the Icepi. The claimed 22.7 ns remains a component-model budget, not a measurement;
stage-3 loopback calibration is essential.

### 3.2 5.8 GHz layout

I inspected the top/bottom copper render and actual stack calculation. L1 RF corridors are over
L2, have close via fencing, avoid right angles, and connectors sit at the edges. Fresh KiCad DRC
has zero violations/unconnected/parity errors. The failure is fabrication specification, not an
obvious routing error: no manufacturer-controlled impedance or validated CPWG/coupler field result
supports the geometry being ordered.

### 3.3 Costas loop

The U110 polarity jumpers, U111 hold topology, loop/VC monitors, and V_MID reference are good
experimental provisions. The numeric detector-gain error is material and must be corrected.
Recalculate PLAN section 18's hold/pull-in claims from the revised loop values.

### 3.4 Fast path

The high-side common-mode concern was checked. With fitted 1 kOhm shunts, the budget derives
1.87 V summing nodes against the THS4541's 2.1 V high-input limit, leaving about 0.23 V at the
stated 3.8 V ADL5380 common mode. TLV3601/3 input range includes the 1.65 V arm outputs. This is
plausible but less margin than stale prose claims: PLAN section 15 still calls the shunts 1.2 kOhm
and receiver text says 1.73 V. Correct those documents and validate common mode over
supply/temperature in bring-up.

### 3.5 Slow path

The gain-20 second FDA, 1 kOhm/33 pF pole (4.8 MHz), 73 ns rise, and 37 ns half-rise delay agree
with the asserted budget. The slow path is correctly a confirmation/veto path, not a repair for a
compressed fast receiver. Its trims and monitor points are sufficient for the rev-A measurement.

### 3.6 Transmitter

TX_EN's inversion and 1 kOhm pull-down address the serious unpowered-host transmit state found
during gateware work. PYNQ DAC levels are 0.170/0.500/0.830 V; Icepi levels are
0.167/0.521/0.874 V. Both are in range, but Icepi needs its own VR_I/VR_Q calibration rather than
reuse PYNQ DAC codes. The existing null/trim procedure is the right mitigation.

### 3.7 Power

I traced both directions of the P-FET power ORing in `gen/sch_pwr.py`; USB VBUS correctly holds
the header-side FET off and header power holds the USB-side FET off. The computed 1.342 A input,
PTC/TVS, regulator dissipation, and RF-rail headroom are coherent with the specified 5.1 V supply.
The build does not independently run a copper-resistance/drop solver, so actual rail drop and
temperature remain stage-1 measurements.

### 3.8 Gateware and driver

Functional simulation/driver coverage passes, as listed above. `make lint` does not. I did not
independently rebuild the PYNQ timing report or ECP5 bitstream; run the clean combined target after
the lint repair and retain the reports with the released hardware revision.

### 3.9 Manufacturing

Fresh DRC/ERC, net walk, BOM/CPL format, top-only assembly plan, board render, release settings,
footprint report, and label report were read. DRC/ERC are zero. The remaining manufacturing
finding is missing local fiducials; the preview of the intentionally deferred rotations still must
happen on order day.

## `CLAUDE_PCB.md` check

| Requirement/gate | Result |
|---|---|
| Section 4 values asserted against fitted design | **Break:** Costas arithmetic uses the wrong detector amplitude and misses fitted R126 = 20 kOhm. |
| Section 5 / gate 15: local fiducials and layer markers | **Break:** no board-local fiducials are placed; no layer markers were found. |
| Section 10 gates 1--5 | **Pass:** fresh ERC and DRC/parity are zero; `net_check.py` completed successfully. |
| Section 10 gate 14 | **Break:** loop equation is asserted but does not match the one-leg detector circuit or fitted R1. |
| Section 10 gate 17 | **Partial:** release evidence is comprehensive, but no controlled-impedance callout/table and no on-board fiducials meet the stated upload-ready standard. |
| Section 9 firmware before ordering | **Partial:** functional simulations pass, but the mandatory lint command fails. |
| Sections 13--14 RF | **Break:** CPWG/coupler performance is calculated but not ordered as controlled impedance. |
| Section 15 power safety | **Partial:** low-power input is protected; PA plus U401 exceeds the switch guarantee and LNA limit. |

`build.py` intentionally does not invoke gateware lint/sim. It also does not perform an RF
EM/coupler validation or a shipped-board rail-drop calculation. These omissions need explicit
release gates or retained results.

## What I checked and found sound

- Independent KiCad 10.0.6 DRC: **0 violations, 0 unconnected, 0 schematic-parity errors**.
- Independent ERC: **0 violations** across all seven sheets.
- `tools/net_check.py`, `sim/budget.py`, `sim/rf_lines.py`, MAX2871 register decoding, and
  register-map generation completed successfully into this directory.
- The copper uses the intended four-layer topology: L2 is the immediate ground reference, RF
  paths are fenced, exposed pads have via arrays, and the current board has no apparent clearance
  or silkscreen catastrophe.
- Comparator common-mode and slow-path bandwidth arithmetic are consistent with stated device
  values.
- P-FET input ORing and TX_EN reset safety are materially improved and correctly documented.
- The functional gateware simulations pass in a private copy.
- The release package contains BOM/CPL variants, assembly drawings, gerbers, placement/footprint
  checks, order settings, and consignment instructions.

## Review method and limits

I read the brief, README, plan, bring-up procedure, rev-A changes, generated schematic sources,
budget/RF calculations, board/release outputs, gateware, critical datasheets, and applicable
`CLAUDE_PCB.md` sections before reading other reviews. I did not run `build.py`: the brief says all
review evidence is committed, and writers are forbidden in the shared project. All commands that
wrote output used this directory or its private `repo/` copy. RF layout has been inspected, not
VNA- or field-solver-measured; controlled fabrication and bench characterization are therefore
order conditions rather than claims of measured RF performance.

## Comparison with other reviews

### Claude's 2026-10-09 early-build review

This report is valuable but explicitly predates the completed copper/release and Response-15
changes. Its two blocking findings have been fixed in the build reviewed here:

| Earlier finding | Current evidence | Reconciliation |
|---|---|---|
| U112 was an OPA2187 outside its 3.3 V supply/common-mode range. | The current BOM and [`gen/sch_rx.py`](../gen/sch_rx.py) use OPA2388 at U112. | **Resolved.** OPA2388 is appropriate for the 3.3 V, V_MID = 1.65 V loop. |
| Header-only power back-fed USB VBUS and left Q302 on a body diode. | [`gen/sch_pwr.py`](../gen/sch_pwr.py) now has Q303 and the USB-gate topology that lifts the USB FET gate from +5V_HDR and pulls it down only when VBUS is present. | **Resolved.** I independently traced both supply directions. |
| The original 1.2 kOhm FDA shunts could violate the THS4541 high common-mode limit. | Current fitted value is 1 kOhm; the current budget derives 1.87 V at the summing node. | **Resolved electrically**, but stale 1.2 kOhm / 1.73 V prose remains and must be corrected. |
| Switch rest-state text and TS5A3159 hold topology were wrong. | Current [`gen/sch_ant.py`](../gen/sch_ant.py) derives TR_B through U402; current [`gen/sch_rx.py`](../gen/sch_rx.py) parks U111's NO port at V_MID. | **Resolved.** |

Claude's caution about real USB source/cable voltage remains a valid bring-up test. The current
plan now calls for 5.1 V at the board and measures the RF rail before RF operation; I did not
promote it to an order blocker. Its MAX2871 Kvco concern is not retained: the current 60 MHz/V
model is a deliberately conservative design value, and the first-order Costas loop issue above is
more direct and independently demonstrable.

### Grok4.7 and KimiK3

Both available reports are explicitly work-in-progress templates with no completed findings or
evidence to weigh.

### Findings not addressed by the available reports

The available reports do not assess the current build's waived impedance-control order, the
single-ended Costas detector-gain calculation, PA/T/R incompatibility, missing board-local
fiducials, or the present lint failure. Those remain the findings of this review.
