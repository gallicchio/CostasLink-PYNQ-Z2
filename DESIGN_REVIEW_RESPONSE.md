# CostasLink-PYNQ-Z2 rev A: the response to the design review

Prompt 18 (2026-10-11).  Four reviewers worked from DESIGN_REVIEW_PROMPT.md on build 17 (commit
504cfe3):

* GPT-5.6Terra
* Gemini 3.8 Flash
* Grok 4.7
* Kimi K3

Their reports are in `design_review/<name>/`.  `design_review/Claude/` is the author's own early
review, from before the brief.

I checked every finding against the datasheet text in `build/txt/`, the shipped board and the
budget before accepting it.  Where reviewers disagreed, the datasheet's numbers settled it, not the
majority.  REVA_CHANGES.md entries 8-20 list the changes; build 18 has them all.

## 1. What changed

| change | found by | how it was checked |
|---|---|---|
| **The LO pairs were crossed and 4× unequal: P now goes to LOIN, N to LOIP; the pairs are mirror images, their legs equal and gated** | KimiK3 | A segment dump of build 17: RX legs 2.06 + 8.06 + 8.02 mm against 41.95 + 1.55 + 14.42 mm.  The cause: U115.12 (P, x 25.1) faces U104.10 (LOIN, x 25.1), not LOIP (x 24.6).  Build 18: RX 10.76 / 10.76 mm, TX 11.76 / 11.76 mm |
| **The RF and LO net classes bound no net; the CPWG gap is now 0.25 mm** | Gemini3.8Flash, KimiK3 | Build 17's project file: 0 nets in either class.  A scratch refill with the nets bound gave 0.250 mm and DRC 0 |
| **Paddle vias: 3 × 3 at 0.8 mm; vias in the SKY65404's paddle and the three ADL5611 tabs** | Grok4.7, KimiK3 | Counted on build 17: U104 and U201 had 4, U101 0, the tabs 0.  Build 18: 9 in each 2.6 mm paddle, 11 in the four small ones |
| **Kd is half the budget's: R126 20 k → 10 k** | GPT-5.6Terra (first, with the fitted numbers), Grok4.7, KimiK3 | U110 selects Q_P or Q_N against V_MID.  Fitted: fn 2.05 kHz, ζ 0.48.  Now: fn 2.9 kHz, ζ 0.68 |
| **The ADL5375's N-side bias divider: 5.1 k / 1 k → 4.7 k / 750 Ω** | Gemini3.8Flash (first), Grok4.7, KimiK3 | The ADL5375's Table 1: 41 µA out of each baseband pin.  0.61 V became 0.507 V, against the ladders' 0.510 V |
| **I/Q SLOW MON moved ahead of the 4.8 MHz pole** | KimiK3 | CLAUDE_PCB.md section 9.  Behind the 1 k, a 50 Ω scope moved the pole and dragged the comparator's input |
| **C320, 100 µF polymer, on +5V_IN** | KimiK3 | CLAUDE_PCB.md section 15.  Its 0.1 Ω ESR is about √(L/C) of a USB cable against the 22 µF pair |
| **Three fiducials and the copper layer numbers** | GPT-5.6Terra, KimiK3 | CLAUDE_PCB.md section 5 and gate 15.  Netless graphics, as the ECP5 board does them |
| **The SW TX limit +29 → +25 dBm; ANT +27 dBm** | GPT-5.6Terra, Grok4.7 | HMC536, 5-6 GHz row: isolation 27 dB min, P0.1dB 27 dBm min at 3 V control |
| **The budget's inputs** (ADL5611 5.8 GHz row: P1dB 12.8 dBm, NF 6.0 dB; the THS4541's guaranteed CM limit; the 5 V drop at maxima; the 33 Ω in the RX latency) | Grok4.7, KimiK3, Gemini3.8Flash | Each is now an assertion in sim/budget.py |
| **The Verilator 5.051 lint failures** | GPT-5.6Terra, KimiK3 | Lint clean on 5.049.  The SIMILARNAME and the shared loop variable are gone; all sims pass |
| **50 Ω width (0.29 mm) for the couplers' port lines where it fits** | KimiK3 | — |
| **Documents:** PLAN.md (loop, pull-in, integer-N steps, the CM table, 3 × ADL5611, the switch's guaranteed numbers, the 5 V path); BRINGUP.md (supply and +5V_RF ≥ 4.85 V; power order; the DSA before judging lock; the summing nodes; TRIG IN into 50 Ω; the field list: the PA and the switch, exposure, arrestors, heat, the second harmonic); sheet notes | all four | — |

## 2. Each reviewer's findings

### GPT-5.6Terra

1. **"The RF order waives impedance control: would cost a respin."**  *Not a respin; the order
   setting stays.*  JLCPCB holds width and spacing to ±20 % without it.  GPT's own extremes give
   43.6-56.8 Ω.  The lines are a few mm to 20 mm long.  At the worst corner a step costs about
   0.1 dB, and the couplers' coupling moves 1-2 dB on taps that bring-up calibrates.  (Gemini3.8Flash,
   Grok4.7 and KimiK3 reached the same conclusion.)  JLCPCB's help pages describe a free standard
   impedance control at ±20 % ([User Guide to the JLCPCB Impedance
   Calculator](https://jlcpcb.com/help/article/User-Guide-to-the-JLCPCB-Impedance-Calculator)).  If
   the order form shows no surcharge and accepts a one-line target (50 Ω CPWG, 0.29 / 0.25 mm on L1
   over L2), choose it on the order day.  It is insurance, not a fix.
2. **Kd counts both legs.**  *Fixed* (section 1).  GPT gave the fitted fn and ζ to three digits,
   and its 9.53 k matches the budget's 9.4 k.
3. **The PA through the HMC536 is unsafe.**  *Fixed on the silkscreen* (+25 dBm without a limiter)
   *and in BRINGUP.md.*  The arithmetic used the guaranteed numbers.  The budget had already said
   "wants a limiter" but never put the limit where the cable goes.
4. **No board fiducials.**  *Fixed.*
5. **The lint gate is red.**  *Fixed.*

### Gemini 3.8 Flash

1. **The 5 V drop: +5V_RF under 4.75 V from a sagging power bank.**  *Documented and gated.*  The
   budget now asserts ≥ 4.85 V from a 5.10 V supply at the maxima (PTC 70 mΩ R1max, FET 60 mΩ, bead
   45 mΩ: 0.21 V).  BRINGUP.md asks for 5.1-5.25 V and a measurement.  Gemini's 80 mΩ for the PTC is
   above its datasheet's R1max (70 mΩ, the most it reads an hour after a trip); the conclusion
   stands.
2. **The netclass patterns bind nothing.**  *Fixed.*  This was Gemini's best finding, and real.
3. **LNA burnout with a PA and whips on one board.**  *Documented* (BRINGUP.md stage 5).
4. **The loop's gain follows the level.**  *Documented* (set the DSA before judging lock).  Already
   in PLAN.md section 10.1 as a risk; now an instruction too.
5. **VN_0V5's lift.**  *Fixed.*  Gemini was first.
6. **"Confirmed correct" items** (the balun, TCXO pin 1, TX_EN, the OR-ing, the timing).  TCXO pin 1
   is checked against the rendered datasheet page: pad 1 is "E/D or N.C.", so PLAN.md's open
   question is closed.  But see below: one of Gemini's confirmations was false.
7. **Section 4.** Exposure, ESD and lightning, and cable strain: *documented.*  Gemini's 4.0 m is the
   far-field formula for the 2 W module at its P1dB into the dish.  Inside the dish's 14 m near
   field the right frame is Grok4.7's 4P/A, which says nobody in the beam at all (BRINGUP.md).
8. **Rejected: "LO lines symmetric, length matched within 0.1 mm"** (Gemini section 3.2).  This is
   false: the RX legs were 18.1 and 57.9 mm.  It was reported as verified, about exactly the defect
   KimiK3 found.  Likewise "standard etch tolerance ±0.02 mm" has no source.

### Grok 4.7

1. **The 5 V path from a USB source.**  *Gated and documented* (as Gemini's #1, with the bead
   included and the PTC's R1max right).
2. **The summing nodes 130 mV under the guaranteed limit, 17 mV at VS = 5.25 V.**  *Checked and
   put in the budget.*  Grok is right that the sheet quoted the typical 1.2 V where the guaranteed
   figure is 1.3 V.  The worst corner is 1.94 V against 2.0 V at the highest +5V_RF the input path
   delivers (5.15 V, after the drop at the start-up current).  It passes with 61 mV.  Grok's 17 mV
   assumed 5.25 V at the chip itself.  BRINGUP.md stage 3 measures the nodes, and the DNP 1.5 k on
   ADJ is the remedy.
3. **Paddle vias.**  *Fixed.*  Grok was first.
4. **The P1dB row.**  *Fixed:* the 5.8 GHz row (12.8 dBm).  The QPSK corners sit exactly at it, and
   PLAN.md section 18 already priced that as 1 dB on a corner; the budget now asserts it.
5. **VN_0V5.**  *Fixed* (confirmed Gemini's number).
6. **The window comparators read high until the AD5696R is written.**  *Documented* (BRINGUP.md
   stage 1.5: write the thresholds before enabling the receiver; power order).  This one was unique
   to Grok and is a real trap for the first event counts.
7. **The PTC derates to about 1.3 A at 85 °C.**  *Documented* for the field box.  Also unique.
8. **Kd.**  *Fixed* (with GPT and Kimi).
9. **The PA through the switch.**  *Fixed* (with GPT).
10. **Section 6.**
    * WiFi: already PLAN.md section 11's scan.
    * The latency's meaning at a fixed DSA level: right, and docs/TRAJECTORIES.md now shows the
      dependence on the threshold and the SNR.
    * The summing-node pad: for rev B, if the needle measurement is ambiguous.
    * Cable strain: *documented.*
    * The second harmonic: *documented* (measure before the PA).

### Kimi K3

1. **The LO pairs, 10 mm against 44-46 mm a leg.**  *Fixed:* the biggest defect any reviewer found.
   Kimi measured it from the copper, which none of the others did.  Its root cause, that the pins
   do not face each other, is in section 1 above.
2. **Kd.**  *Fixed.*
3. **The slow MON taps behind the pole.**  *Fixed.*  Unique to Kimi.
4. **Lint.**  *Fixed.*
5. **Back-feeding an unpowered host, about 11.6 mA a pin.**  *Documented* (the power order).  A bus
   switch or larger series resistors are a rev B question; 233 Ω already limits the current.
6. **No damped bulk on the input.**  *Fixed* (C320).
7. **"1 Hz steps" is not implemented.**  *The text is fixed* (25 MHz integer-N; the fractional
   re-centre is open: REVA_CHANGES 20).
   * **Rejected: the APR argument**, that the VCXO's guaranteed ±50 ppm falls short of a needed
     ~305 kHz.  The absolute pull range already includes the VCXO's own tolerance, temperature
     and ageing.  What it must cover is the far transmitter's TCXO (±2.5 ppm) plus the receiver's
     reference error: 29 kHz against 290 kHz.
8. **Netclasses.**  *Fixed* (confirmed Gemini's finding).
9. **Paddle vias.**  *Fixed* (confirmed Grok's finding).
10. **Fiducials and layer markers.**  *Fixed.*
11. **VN_0V5.**  *Fixed.*
12. **TRIG IN with JP202 fitted halves a Hi-Z generator.**  *Documented.*
13. **The ADL5380's two tables.**  *Settled in the budget:* both values are checked against the
    guaranteed limit.  The sheet now prints one statement.
14. **The P1dB row.**  *Fixed.*
15. **Impedance control.**  *As GPT's #1:* order-day insurance.
16. **The monitor lines' width.**  *Fixed where it fits.*
17. **Document drift.**  *Fixed in PLAN.md*, and in the release counts as the release rewrites them.
    QUESTIONS.md item 1 is superseded.  CONSIGNMENT.md is not touched: the author has not asked for
    its update, and its "three reels" goes with that rewrite.

Section 4's other points:

* The amateur mode should enforce the identification in gateware: a good rev-A gateware item, not
  a board change.
* The 25 MHz harmonic lands on the carrier: right; it is a constant I/Q offset the trims take.
* The TRIG IN → TX_Q1 two-driver hazard with the DNP 0 Ω fitted: the driver should check CTRL[8].
  Also a gateware and driver note.

**Rejected:** several cross-references in Kimi's "other reviewers" section name things that do not
exist: a U207, "Grok B3/B4 bit 31", a 1.8 V serial flash, a "fink 2450".  Its own first draft's
"4 m" exposure figure, which it withdrew.

## 3. How useful each reviewer was

1. **KimiK3: the most useful.**
   * It found the board's worst defect, the crossed LO pairs, by parsing the copper.  The others
     either did not look or, in Gemini's case, said it was fine.
   * Five more real findings were Kimi's alone: the slow taps, the bulk capacitor, the 1 Hz text,
     the monitor-line widths and TRIG IN into 50 Ω.
   * It verified other reviewers' findings with arithmetic of its own, and its severity column was
     honest.
   * Its faults: invented cross-references in the reconciliation, and one wrong argument (the APR).
     Read its report for its findings, not for its citations.
2. **Grok 4.7: the most accurate, and close behind.**
   * Every number checked out, and its severities were the best calibrated.
   * It was first on the paddle vias, and the only reviewer to see the window comparators' power-up
     state and the PTC's derating.
   * Its near-field frame for the RF exposure is the right one.
   * It missed the LO pairs, though it measured the paddles beside them, and its 17 mV corner used
     5.25 V at the chip rather than at the plug.
3. **GPT-5.6Terra: the sharpest single catch, the narrowest review.**
   * The Kd error is a factor of two in the loop's natural frequency.  GPT stated it with the fitted
     fn and ζ and the right resistor.
   * Its PA and switch arithmetic used the guaranteed numbers.
   * It ran the testbenches.
   * Five findings in all, and it rated a cosmetic order option as a respin.
4. **Gemini 3.8 Flash: one important catch, too much false confidence.**
   * The netclass binding was a real defect no one else had found first, and it was first on the
     VN_0V5 lift.
   * But half its table is "confirmed correct" items.  One of them, the LO pairs "matched within
     0.1 mm", was the board's worst defect.
   * Several numbers had no source.
   * A reviewer who verifies wrongly costs more than one who does not verify, because the false
     confirmation is believed.

Together they were worth far more than any one of them.  The three that agreed on Kd, the two that
agreed on the paddle vias and the netclasses, and the one that measured the LO copper each moved
the board.

## 4. Still open

* The fractional-N re-centre in the driver (REVA_CHANGES 20).
* The amateur-mode identification enforced in gateware; the driver's CTRL[8] check for the
  FPGA-free trigger path.
* Impedance control on the order day, if free (section 2, GPT's #1).
* The CPL rotations: deferred to the order day, as before.
* Rev B candidates: a summing-node test pad; an RF ESD protector at the LNA's input; a limiter
  footprint ahead of the LNA; an I-window pair for B2 (PLAN.md section 18).
