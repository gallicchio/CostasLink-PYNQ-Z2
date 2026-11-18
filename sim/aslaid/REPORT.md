# CostasLink-PYNQ-Z2 rev A simulated as laid out (2026-10-29, overnight)

CLAUDE_PCB.md §14's "Simulate the circuit the copper makes", run on the board as built. Each RF and LO path is extracted from
`hardware/CostasLink-PYNQ-Z2.kicad_pcb` and compared port to port with the vendors' circuits placed at the pins. The models
are anchored on board A's bench measurements. The supply planes are modelled as cavities, and CLAUDE_PCB.md gates 26-32 run
as code. The ICs come from their datasheets; no Touchstone files were fetched. openEMS was not run: test A below settles the
main question more cheaply.

| file | what |
|---|---|
| `extract.py` | the board file to a circuit. Every track of the chosen nets becomes a transmission line, sampled every 0.1 mm with its own width, gap and reference. Junctions become nodes, so a branch is a stub. Pads become nodes carrying their capacitance to the plane under them, vias become inductances, and every passive keeps its model and ground return |
| `xsec.py` | 2D finite-difference cross-sections: each line's Z0 and eps_eff, and the even and odd modes of the printed couplers (`line_table.json`, `coupler_modes.json`) |
| `circuit.py`, `devices.py` | a nodal frequency-domain solver, and the ICs and parts from their datasheets (`adl5611_sparams.json`) |
| `sections.py` | each passive section between two pins, with 50 ohm at its ends |
| `paths.py [rx\|tx\|lo\|all]` | the paths as laid out, against the vendors' circuits, against the bench |
| `pdn.py` | the In2 islands as cavities, and the transmitter's coupling into the receiver through +5V_RF |
| `gates.py` | gates 26-32 across the 53 RF and LO nets (`out/gates.txt`, `out/gates.json`) |
| `plots.py` | `out/rx_chain.png`, `rx_ant_s11.png`, `tx_chain.png`, `lo_mon.png`, `leak.png` |

## The model against the bench

- **RX ANT to RX MON, 5.0-5.85 GHz** (the part of the night's maps that follows the DSA):
  - **As extracted, with nothing fitted:** right at 5.0 GHz (10.4 dB against 9.2), but 22 dB too high at 5.8.
  - **With one parameter fitted:** C102's ground return, 0.59 nH where the extractor gave 0.14.

    | GHz | 5.0 | 5.3 | 5.5 | 5.7 | 5.8 | 5.85 |
    |---|---:|---:|---:|---:|---:|---:|
    | model (dB) | 7.6 | 2.0 | -0.9 | -5.5 | -10.9 | -16.0 |
    | bench (dB) | 9.2 | 1.3 | -5.8 | -14.4 | -14.0 | -17.2 |

    That is within 3-6 dB at 5.0-5.5 and 5.85 GHz, and 3-9 dB off at 5.7-5.8. The fitted model also has the main path at
    about -10 dB at 6.0 GHz, as the DSA 0 / 31.75 readings imply, recovering above 6.1 GHz, which agrees with the
    TX-muted noise hump at 6.47-6.8 GHz.
- **LO RX MON:** -9.5 dBm modelled, -8.7 measured, nothing fitted.
- **TX chain:** the trend matches the vendors' circuits with one offset, the drive 3.1 dB under the datasheet's 1 V p-p. The
  layout costs 1-2 dB at 5.8 GHz.
- **Not explained:**
  - LO TX MON's 115.6 mm route loses 10-15 dB more above 4 GHz than the model gives;
  - the transmitter's leak into the receiver (finding 5).

## Findings, ranked

1. **C102's branch resonance** (REVB 8).
   - **Geometry:** the 0.5 pF sits 4.0 mm of track from RF_IN (48 degrees at 5.8 GHz), on a 1.8 mm, 64.7 ohm branch.
   - **Mechanism:** the branch and the capacitor's mount (0.3 nH ESL, 0.6 nH ground) series-resonate at 5.9 GHz.
   - **Cost:** about 25 dB at 5.8 GHz.
   - **Predictions:** lifting C102 gives back about 25 dB there. RX ANT's S11 reads about -0.8 dB at 5.8 GHz now, and about
     -7 dB with C102 lifted.
2. **0402 pads on the 0.21 mm prepreg are capacitors**, about 0.077 pF each to In1. Even with C102 lifted they cost about
   2 dB at 5.8 GHz and about 8 dB at 5.0, through the ADL5611s' poor match (S11 -4.8 dB, S22 -9.4 dB).
3. **Interstage ripple remains after C102 is lifted:** the chain stays 4-15 dB under the vendors' circuits between 4.8 and
   5.6 GHz. Its size is more trustworthy than its frequencies, because the ADL5611 table is referenced to its evaluation
   board's SMAs.
4. **The LNA's VCC pin sees 2.6 nH at 5.8 GHz,** against 1.0 nH in Skyworks' circuit, plus a parallel resonance of about
   240 ohm near 4 GHz. Its effect on the gain is unknown without a model of the die.
5. **The leak is not the +5V_RF plane** (revises REVB 10).
   - **Why:** that island sits 0.21 mm over the B.Cu ground pour, so it is low-impedance: about 1 ohm between the chokes'
     vias.
   - **The choke path, modelled:** -72 to -87 dBm at RX MON. That is 20-40 dB under the bench and the wrong shape against
     frequency.
   - **Left to test:** radiation from the TX lead, the jacks and the attenuators; the thinly stitched top pour; the
     modulator's own supply currents (not modelled).
6. **Synthesizer outputs.**
   - RFOUTB's 27 nH pull-ups sit 9-12 mm from the pins, on branches with vias, on B.Cu over the PLL supply islands.
     RFOUTA's sit 3.6 mm from theirs.
   - At APWR 1 (-1 dBm a side) the LO drive is -2.4 dBm into the ADL5380 and -1.0 dBm into the ADL5375; both datasheets
     test at 0 dBm.
7. **The lines are about 54 ohm, not 50.** The field solve gives 53.7 ohm where `sim/rf_lines.py`'s closed form gave 49.8.
   The couplers' quarter wave lands at 5.97 GHz, and their directivity is poor (even and odd eps_eff 3.20 / 2.73).
8. **The gates (55 FAIL lines, `out/gates.txt`):**
   - every RF shunt part's ground via is 0.47-0.51 mm from its pad's edge;
   - all 11 chokes and pull-ups reach a plane via before any capacitor; the nearest capacitor is 1.9-13.6 mm away;
   - +5V_RF serves both chains;
   - the coupler taps, J204's route and the RFOUTB nets are unfenced, or referenced to a supply plane;
   - L101 is 6.9 mm from J101 and L401 is 5.4 mm from J401;
   - no capacitor of 1 nF or less is reachable by track within 2 mm of any RF IC's supply pin.

## Tests for Monday, the non-invasive ones first

| test | what | the cabling | what it shows |
|---|---|---|---|
| A | S11 at RX ANT on the 8720ES, the board powered and unpowered | the VNA's port 1 to RX ANT | above -2 dB over 5.5-6.1 GHz, with a sharp feature near 5.9 GHz: confirms finding 1 without touching a part |
| B | the leak: TX on; TX ANT and RX ANT each on a 50 ohm load, no lead between them; RX MON and I/Q at DSA 31.75 | two loads; the analyzer on RX MON | if it stays, it is on the board; if it falls 20 dB or more, it was the lead and the jacks |
| C | LO RX MON swept over 3-6.5 GHz | the analyzer on LO RX MON | the model's peak near 3.8 GHz and its null near 4.3 |
| D | TX ANT against the TX synthesizer's RFOUTA power, -4 to +5 dBm | software only | how much of the TX shortfall is the LO drive |
| E | the I/Q beat's amplitude against the RX RFOUTA power | software only | the same for the receiver |
| F | S21 from RX ANT to RX MON on the VNA, DSA 0 and 31.75 | the VNA on RX ANT and RX MON | the chain without the leak |
| G | then lift C102, and repeat A and the map | | +25 dB at 5.8 GHz predicted |

## Proposed REVB rows

- **8 (update):** the resonance is modelled; tests A and G confirm it.
- **10 (revise):** the plane path is 20-40 dB too weak to be the leak; test B finds where it is.
- **11 (new):** the 0402 pads' capacitance. Void In1 under the RF passives' pads, use 0201 parts, or use fewer DC blocks.
- **12 (new):** the MAX2871 pull-ups at the pins, with the outputs on F.Cu over ground; and the LO drive levels.
- **13 (new):** the LNA's VCC network: L102 on pin 6, the 100 nF on its far pad, a via in the pad.
- **14 (new):** the CPWG width from a field solver, and the coupler's length from its own eps_eff.

## Proposed for CLAUDE_PCB.md

- Count the pads' capacitance on a thin dielectric.
- Take a CPWG's width from a field solver, not a closed form.
- Find where a vendor's S-parameters are referenced (an evaluation board's SMAs are not the pins).
- Fit at most one parameter, and say which.
- Model a plane before blaming it.
