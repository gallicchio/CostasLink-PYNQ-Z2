# Design review wanted: CostasLink-PYNQ-Z2 rev A, the last look before it is ordered

**Nothing you say in the chat will be read or kept: your review exists only as a file.  Before anything else, find
your own directory in `CostasLink-PYNQ-Z2/` (§0.1) and write `DESIGN_REVIEW_<YourName>.md` inside it, with your
verdict and findings table first.  Then fill it in as you go.  Writing into that directory is required, and it is
not a change to the project.  Everything else in the tree is read-only to you, and git is off limits (§0).**

**You are asked to break this design.**  It is a 5.8 GHz link board that plugs onto a PYNQ-Z2.  Its author has been
through fifteen rounds of design and self-review with one LLM, so the obvious faults are gone.  The ones left are the
kind that survive self-review: assumptions everybody in the room already agreed with.  A fresh, blunt reader is worth
more now than another careful pass by the same eyes.

Be opinionated and specific.  "Do not order this because X", with a number, is worth more than twenty notes about
style.  If you think the architecture is wrong, say so and say what you would do instead.  If you approve of
something, say what you checked; a review that approves everything cannot be told from one that read nothing.

**Look past the questions below.**  §3 lists what the author is least sure of.  §4 asks for the problems nobody
thought to ask about, and those are often the ones that cost the most.  Nothing has been fabricated.  Changing
anything costs only time, and "start over" is an acceptable conclusion if you can say why.

---

## 0. Ground rules: where to work and what not to touch

Several reviewers read this working tree at the same time.  The author reads every report side by side, and the
author's own KiCad or build may be using the project while you work.  Other people use the git repository.  So:

1. **One directory is yours, in `CostasLink-PYNQ-Z2/`, and everything you produce goes in it.**  The author made
   them empty:
   - `design_review_Gemini3.8Flash/`
   - `design_review_GPT-5.6Terra/`
   - `design_review_Grok4.6/`
   - `design_review_KimiK3/`

   A reviewer not on that list makes `design_review_<YourName>/` beside them.  Name the report
   `DESIGN_REVIEW_<YourName>.md`, after the directory, so `design_review_KimiK3/DESIGN_REVIEW_KimiK3.md`.  Notes,
   scratch scripts, extracted text, renders, DRC and ERC reports, copies of files you annotate: there and nowhere
   else.
2. **Do not modify, move, delete or create any file outside your directory.**  That means:
   - not the sheets, the board or anything else in `hardware/`;
   - not `mfg/release/`, the Python (`gen/`, `tools/`, `sim/`, `mfg/`), `gateware/` or `build/`;
   - not the markdown, not `CLAUDE_PCB.md` one level up;
   - not another reviewer's directory, and not `design_review_Claude/`.

   Other reviewers are reading those files right now, and a changed file silently invalidates their work and the
   author's.
3. **To try a change, or to run anything that writes, copy the project into your own directory first and work on
   the copy.**  From `CostasLink-PYNQ-Z2/`:
   ```bash
   D=design_review_<YourName>; mkdir -p $D
   rsync -a --exclude build --exclude datasheets --exclude 'design_review_*' --exclude __pycache__ \
         --exclude '*.lck' --exclude '*-backups' ./ $D/repo/
   ```
   That is about 50 MB.  Read the datasheets and the build products in place: they are read-only to you, not hidden.
   In the copy:
   - `python3 build.py` remakes everything, from the budget to the board and its DRC, in about 10 minutes, most of
     it the router (measured in such a copy: the same 3784 tracks and 1054 vias, DRC 0).
   - `python3 mfg/make_release.py` remakes the release; it needs `build/` from a full build first.
   - `cd gateware && make lint sim sim-engines sim-axil sim-driver` runs the gateware's tests.
   - `vivado -mode batch -source pynq/build.tcl`, from `gateware/`, builds the PYNQ overlay in about 3 minutes.

   All of these are harmless in your copy and forbidden in the shared tree.
4. **Do not touch git.**  No `add`, `commit`, `stash`, `checkout`, `restore`, `reset`, `clean`, `branch`, `mv` or
   `rm`.  Read-only commands (`git status`, `git log`, `git diff`, `git show`) are fine.
   - You start on `master` with a clean working tree: the commit that added this brief holds the whole project.
   - When you finish, `git status` must show nothing but your own directory; the author checks.
   - The project's history before that commit is `CLAUDE_CODE_CHAT.md` (§6).
   - The author commits the reviews when they are collected.
5. **Do not run anything that writes into the shared tree.**
   - The writers: `build.py` (any step), every `gen/*.py`, `tools/sch_check.py`, `tools/pcb_check.py`,
     `tools/label_check.py`, `tools/render_sch.py`, `tools/render_pcb.py`, `sim/constellations.py`,
     `sim/link_rates.py` and `sim/budget.py --json`, `mfg/make_release.py`, `mfg/cost_estimate.py`,
     `gateware/max2871_regs.py --verilog`, `gateware/regmap.py --vh`, `gateware/gen_xdc.py` (it takes no options:
     even `--help` rewrites the constraint files), the gateware's `make` (it writes `build/gateware_scratch/`), and
     `tools/jlc_query.py` (a part's JLCPCB stock and price: it appends to `tools/jlc_cache.json`, so run it in your
     copy).
   - KiCad: do not open the shared project in the GUI, which writes lock files and `.kicad_prl` beside it; open your
     copy.  Never run `kicad-cli` with `--save-board` or `--refill-zones`, or with `-o` outside your directory.
   - The readers you may run in place, output redirected into your directory, are in §6.
6. **Form your own findings before you read anyone else's.**
   - `design_review_Claude/` is the author's own self-review of an early build (2026-10-09, Response 9).
     `CLAUDE_CODE_CHAT.md`, `PLAN.md` and `REVA_CHANGES.md` are the author's account.  Read them whenever you like,
     but do not let them set your list.
   - Once your report is drafted, read the other reviewers' directories if they have anything in them, and add a
     last section: what you agree with, what you dispute (with the datasheet number or the measurement that settles
     it), and what everybody missed.  Where reviewers disagree, settle it with numbers, not by majority.
7. **Write the report as you go**, in case the session dies.
   - First: the verdict, order or do not order, in one paragraph.
   - Then the findings table, ranked by what it would cost to be wrong, with a "confirmed by" column naming what you
     actually ran or read.
   - Then the detail.  Numbers beat adjectives.
8. **Cite exactly**: a file and line, a sheet and reference designator, a board coordinate (millimetres from the
   board's top-left corner, as `build/placement.json` gives them), a datasheet page or table.

---

## 1. What the board is for

**The link.**  Quantum position verification wants a classical link between two stations whose latency is the speed
of light plus as little electronics as possible.  The link is idle almost all the time and carries one or two bits at
an unpredictable moment.

**The idea.**  The transmitter sends an unmodulated 5.8 GHz carrier all the time, and the receiver's Costas loop
tracks it continuously.  A bit is a brief departure of the constellation point from the idle point.  The receiver
decides it with fast comparators on the demodulated I and Q arms, straight into the FPGA: no loop, no filter
narrower than 100 MHz, and no software in the data path.

**The board.**  One board is both ends of a link; two boards talk to each other.  On it:
- **Receiver:** SKY65404 LNA, PE43711 DSA, two ADL5611 gain blocks, a balun, an ADL5380 IQ demodulator.  Its LO is a
  MAX2871 referenced to a 25 MHz VCXO, which the Costas loop steers, so the whole synthesizer is the loop's VCO.
- **Arms:** THS4541 fully differential amplifiers at gain 4 (100 MHz).
- **Fast comparators:** a TLV3601 on sign(I), and four TLV3603 window comparators (I and Q, both sides, each against
  its own 16-bit AD5696R threshold).
- **Slow path:** a second ×20 stage with a 4.8 MHz pole and three more comparators, which confirms or vetoes each
  fast decision about 37 ns later.
- **Transmitter:** an ADL5375-05 IQ modulator, driven by two 2-bit resistor ladders from four FPGA pins, then an
  ADL5611.
- **The rest:** an optional HMC536 antenna switch for one-antenna time division; trigger SMAs (TRIG A, TRIG B,
  TRIG IN); a dozen U.FL and MMCX monitor taps; two MCP4728 DACs for references and trims; an ADS1115 ADC for the
  loop's state; USB-C power.
- **Host:** a PYNQ-Z2 (Zynq-7020) through its 40-pin Raspberry Pi header.  An Icepi Zero (ECP5) is the alternative
  host.

| quantity | value | source |
|---|---|---|
| carrier | 5.8 GHz (5.2 GHz for the other direction), integer-N from 25 MHz | `gateware/max2871_regs.py`, PLAN.md §3 |
| TX output | +9.8 dBm at the SMA | `sim/budget.py` |
| electronics latency, FPGA pin to FPGA register | 22.7 ns on the PYNQ-Z2 (8.8 ns of it the PYNQ's 200 Ω header resistors); 13.9 ns on the Icepi Zero | PLAN.md §3 |
| fast-path floor | -81 dBm at the antenna; the slow path -107 dBm | PLAN.md §3 |
| Costas loop | fn 3 kHz, ζ 0.7; VCXO ±100 ppm = ±580 kHz at 5.8 GHz | PLAN.md §3 |
| power | 1.34 A from 5 V (6.7 W) | PLAN.md §3 |
| schemes | BPSK flip, Q step, QPSK corners round a full idle, a weak pilot at 45° with the four corners, ... | PLAN.md §18 |

**Read first:** `PLAN.md` §1-§3 (the idea, the block diagram, the numbers), §13 (protocols and range), §15 (the two
decision paths) and §18 (the constellation from first principles).  `docs/images/block_*.svg` are the annotated block
diagrams.

## 2. The state of the board, and the claim you are asked to break

The build under review is from 2026-10-10 at 20:01.

**The board:**
- 120 × 100 mm, 4 layers, JLCPCB's JLC04161H-7628 stack, ENIG.  L1 carries RF and signals, L2 is unbroken ground,
  L3 the supply pours, L4 signals under a ground fill.
- 382 parts on seven schematic sheets: the root, power and header, receiver and Costas loop, transmitter and
  triggers, antenna switch, slow path, window comparators.
- 3784 tracks, 1054 vias.

**The author's claims:**
- ERC 0.  DRC 0 at every severity: 0 violations, 0 unconnected, schematic parity 0.  The connector-label check 0.
- `mfg/make_release.py` passes every gate, with a cost estimate:
  - JLCPCB about $777-792 with duty and shipping (5 boards, 2 assembled on the top side only).
  - Digi-Key about $150 for the three consigned parts.

**The author's question to you: is this board ready to order, apart from the two order-day items in §7?**

**What changed most recently, and so is least reviewed** (`CLAUDE_CODE_CHAT.md`, Responses 14-15):
- **The measurement package** (Response 14): sheet 7's four window comparators and their 16-bit DAC; a fast Q-arm
  trim; the loop-hold switch rewired to V_MID; a trigger path that bypasses the FPGA (a DNP 0 Ω from TRIG IN to
  TX_Q1); TRIG IN MON; TR_B made on the board from TR_A.
- **Silkscreen:** connector labels by rows.  The router's root cause (875 mm of ground track laid before routing) was
  found and fixed.
- **The gateware** (Response 15, `gateware/`): one Verilog core for both hosts, and a Python driver.  It is tested
  only in simulation; no board exists yet.
- **TX_EN** (Response 15, `REVA_CHANGES.md` 2): header pin 24 went from TX_DIS (high = mute, 100 k pull-down) to
  TX_EN (high = transmit).  A 74LVC1G04 (U206) drives the ADL5375's DSOP, with a 1 k pull-down on TX_EN.  The old
  board transmitted whenever no gateware drove the pin.  100 k pull-downs (R314-R318) were added on the
  synthesizers' and the DSA's latch enables and on the trigger buffer's inputs.
- **J302** (Response 15, at the author's request): the 2×20 socket is now hand-soldered at home, so JLCPCB's order
  is one-sided.

## 3. What to attack, ranked by what it would cost to be wrong

These are the author's own least-confident points, stated plainly so you do not have to dig for them.

1. **The concept against its purpose.**  Is a carrier-always-on Costas link with comparator decisions the right
   answer for a latency-critical QPV link, against the alternatives (an ADC and a matched filter, OOK with a fast
   detector, an off-the-shelf 5.8 GHz modem)?  Does 22.7 ns of electronics, 8.8 ns of it the PYNQ's header
   resistors, make the PYNQ-Z2 the wrong host for rev A?  The author thinks rev B belongs on an on-board ECP5.  Does
   the data path still work with real multipath, real phase noise, and the loop's static phase error?
2. **5.8 GHz on this layout.**
   - The 50 Ω lines are 0.29 mm coplanar waveguide with 0.25 mm gaps over the L2 ground (`sim/rf_lines.py`).
   - The two -20 dB couplers (CP101, CP201) are drawn in copper, not bought.
   - The balun's land pattern and orientation; the LO routing from each MAX2871 to its mixer.
   - Isolation between this board's own transmitter and receiver, 600 MHz apart, with one or two antennas.
   - The ground stitching along the lines; the SMA and MMCX launches.

   Open the copper (§6) and check the lines' geometry against the stack, not against the code that drew them.
3. **The Costas loop.**  The PI filter (OPA2388); the sign switch (SN74LVC1G3157) and the jumpers JP101, JP102 and
   JP103; the VCXO's pull and the FPGA's re-centring of the RX synthesizer; the loop's lock point with a weak pilot;
   the hold switch (TS5A3159) and its leakage; the 180° ambiguity.  Will it lock on the first power-up?  If not, what
   will the bring-up plan (`BRINGUP.md` stage 3) show?
4. **The fast decision path.**
   - The arms' common-mode shift (the demodulator's 3.2 V into a 3.3 V FDA through 1.2 k shunts).
   - The comparators' thresholds, offsets and hysteresis options against the 249 mV signal.
   - The window comparators' power-up state: the AD5696R starts at mid-scale, below the arms' centre, so every
     window reads high until the FPGA writes it.
   - The 33 Ω series lines and the 453 Ω scope taps; the PYNQ's 200 Ω on every header pin.

   Does each comparator see the signal the budget says, with the margin it says?
5. **The slow path** (sheet 6): ×20 after ×4, its offsets, its threshold V_T2, and whether "confirm or veto 37 ns
   later" holds at the levels where it is needed.
6. **The transmitter.**
   - The 2-bit ladders through the PYNQ's 200 Ω into the ADL5375-05's baseband inputs, which are biased at 0.5 V:
     the levels, their accuracy, and the carrier null through VR_I and VR_Q.
   - The new TX_EN inverter and pull-downs: are they right, and is anything else still unsafe while the host is off,
     configuring, or loading another overlay?
   - The station identification: the gateware keys TX_DIS in Morse every 10 minutes.
7. **Power.**
   - USB-C 5 V at 1.34 A, a PTC, P-FET ideal diodes on two inputs (USB-C, and the header's 5 V through JP301), four
     TPS7A20 and an LP5907.
   - Back-feeding the PYNQ through pull-ups or the header 5 V when one board is powered and the other is not.
   - The regulators' heat, and USB-C PD power banks in the field.
8. **The gateware and its driver** (`gateware/README.md`, `gateware/driver/`).
   - Does the core do what BRINGUP.md needs?
   - Are the register bus's read latency, the ISERDESE2 sampling at 800 Ms/s (400 MHz DDR from the PS's FCLK0
     through a clock wizard) and the decoder's pipeline right?
   - Would you trust its latency numbers to the sample?  It has run only in simulation.
9. **Manufacturing.**
   - Three parts are consigned from Digi-Key (`mfg/release/CONSIGNMENT.md`, written before JLCPCB's August 2026
     overseas process; see §7).
   - J302 is hand-soldered; through-hole SMAs and headers are on the top side.
   - Thin stock: the HMC536 had 5 in stock against 2 needed, the AD5696R 7, the TLV3603 16.
   - Do the BOM, the CPL and the footprints agree with each other and with the parts' drawings
     (`mfg/release/FOOTPRINT_CHECK.txt`, `PLACEMENT_CHECKS.txt`)?
10. **The method.**  There is no hand-drawn schematic and no hand-placed layout.  `gen/` emits every sheet, places
    every part and routes every track (`build.py`).  It buys reproducibility and design rules as code.  It costs
    nudging a part in the GUI, and it means a reviewer must read Python to learn why the board looks as it does.
    Tell the author if the trade is wrong, and **look at the actual copper**: "passes DRC" is not "well routed".

## 4. Beyond the list: problems nobody asked about

The author would rather hear about a problem nobody thought of than have the list above confirmed.  Spend real time
here.  Starting points, not limits:

- **Safety and the law.**
  - RF exposure with the 2 W PA module behind a 24 or 30 dBi dish: the EIRP, and the distance a person must keep.
  - The amateur 5 cm band's rules (identification every 10 minutes, power) against ISM / UNII operation.
  - Anything that could transmit unattended, or out of band if a synthesizer is misprogrammed.
- **The field.**
  - ESD and lightning on 10 m antenna cables to panels on a hill.
  - Sun and heat in an enclosure; condensation.
  - Power banks sagging at 1.34 A.
  - Mechanical strain from SMA cables on a board that rides 8 mm above the PYNQ on a header.
- **Interference.**
  - The board's own clocks: the 25 MHz references and their harmonics, the FPGA's I/O, the switching of the ladders.
  - Two boards' synthesizers 600 MHz apart.
  - WiFi in the 5 GHz band; the slow path as the veto.
- **The experiment's validity.**
  - Does the measured latency mean what the plan says it means?
  - Is the calibration (BRINGUP.md stage 4.2: three distances, the slope is c) sound?
  - Can the FPGA's time stamps (1.25 ns samples) support the claims?
- **Bring-up.**
  - Is there a failure that `BRINGUP.md` would not find, or would find only after something burns?
  - Is anything unprobeable?
- **The documents.**  Anything in `PLAN.md`, `BRINGUP.md`, the sheet notes or the silkscreen that is wrong or
  misleading.  The notes are claims, not evidence.
- **The supply chain and the order.**  Anything that would make JLCPCB's engineers stop the order, or make the
  assembled board differ from the files.

## 5. The standard: `CLAUDE_PCB.md`

The author holds every board to `../CLAUDE_PCB.md`, at the top of the repository: about 2200 lines of lessons from
earlier boards, in sixteen sections.

| § | topic |
|---|---|
| 1 | how the author works |
| 2 | build system |
| 3 | parts and JLCPCB |
| 4 | schematics |
| 5 | placement and routing |
| 6 | silkscreen |
| 7 | mechanical |
| 8 | manufacturing package |
| 9 | bring-up |
| 10 | verification gates |
| 11 | KiCad quirks |
| 12 | choosing components |
| 13 | fast digital |
| 14 | RF |
| 15 | power and magnetics |
| 16 | boards for children (not this board) |

**Read it, and check this board against every rule that applies.**  Where the board breaks a rule, quote the rule
with its section, and say where and by how much.  §10 lists gates; say which ones the build does not run, and run
them in your copy.  Where you think a rule itself is wrong, or missing, say so: the file is read by every future
board.

It is in the working tree and may hold uncommitted changes; read the working copy, not `git show`.

## 6. Where things are, and the tools

Everything the build makes is in the tree, so nothing has to be built to review it.  Run these from
`CostasLink-PYNQ-Z2/`, output into your directory.  KiCad 10.0.6 is the extracted AppImage
`~/.local/kicad10/AppDir/AppRun`; `kicad-cli` is its subcommand and is not on `PATH`.  The FPGA tools are the OSS CAD
Suite (`~/openfpga/oss-cad-suite/bin`) and Vivado 2024.1 (`~/Downloads/Xilinx/Vivado/2024.1/settings64.sh`).

```bash
D=design_review_<YourName>
K=~/.local/kicad10/AppDir/AppRun
# KiCad's own checks and pictures: read the shipped file (NO --save-board, NO --refill-zones; that is the copper the
# Gerbers came from)
$K kicad-cli pcb drc --severity-all --schematic-parity --format json -o $D/drc.json hardware/CostasLink-PYNQ-Z2.kicad_pcb
$K kicad-cli sch erc --severity-all --format json -o $D/erc.json hardware/CostasLink-PYNQ-Z2.kicad_sch
$K kicad-cli pcb render --side top -o $D/top.png hardware/CostasLink-PYNQ-Z2.kicad_pcb       # --side bottom too
$K kicad-cli pcb export svg --layers F.Cu,F.SilkS,F.Mask,Edge.Cuts --mode-single -o $D/front.svg hardware/CostasLink-PYNQ-Z2.kicad_pcb
$K kicad-cli pcb export svg --layers In1.Cu,Edge.Cuts --mode-single -o $D/in1.svg hardware/CostasLink-PYNQ-Z2.kicad_pcb  # In2.Cu, B.Cu likewise
$K kicad-cli sch export pdf -o $D/schematic.pdf hardware/CostasLink-PYNQ-Z2.kicad_sch     # or read docs/images/
# the project's readers (they only print; redirect)
python3 tools/net_check.py > $D/net_check.txt              # power nets with pin counts, one-pin nets, the signal paths walked
python3 tools/sch_where.py rx 455 209 10                   # what is drawn near a point of a sheet (sheets: rx, tx, pwr)
python3 sim/budget.py > $D/budget.txt                      # every number of PLAN.md section 3, computed and asserted
python3 sim/rf_lines.py > $D/rf_lines.txt                  # the 50 ohm line geometry on the stack
python3 gateware/max2871_regs.py 5800 5200                 # the synthesizers' register words, decoded
python3 gateware/regmap.py --md                            # the gateware's register map
pdftotext -layout datasheets/<file>.pdf $D/<file>.txt      # or read build/txt/, the PDFs already as text
```

**The files:**
- **`README.md`**: the status in one paragraph and a map of the tree.  **Start here**, then `PLAN.md` (1100 lines;
  the table of contents is its `##` headings).
- **`BRINGUP.md`**: what to have on the bench, and six stages from first power to two hills, each with its pass
  condition and the dead-on-arrival risk it retires.
- **`REVA_CHANGES.md`**: what writing the gateware found about the board.  `PLAN.md` §11: the author's open questions.
- **`CLAUDE_CODE_CHAT.md`**: every prompt and response, every decision and every mistake (2250 lines).  Search it;
  you are not expected to read it through.
- **`hardware/`**:
  - the seven `.kicad_sch` sheets and the `.kicad_pcb` with its zones filled;
  - `hardware/checks/`: `netlist.net`, `drc.json`, `erc.json`, `labels.json`;
  - `hardware/lib/`: the project's own symbols and footprints.
- **`gen/`**: the generator.
  - `pins.py`: the header map, the one source of truth.
  - `parts.py`: every part, with its LCSC code and why it was chosen.
  - `sch_*.py`: the circuits, with the notes printed on the sheets.
  - `placement.py`: where everything is, and why.
  - `routes.py`, `routing.py`, `router.py`, `tidy.py`: the copper.
  - `silk*.py`, `label_rows.py`: the silkscreen.
- **`sim/`**: `budget.py`, `rf_lines.py`, `link_rates.py`, `constellations.py`: the arithmetic behind every number.
- **`mfg/release/`**: what would be uploaded:
  - the Gerbers (zip and folder), `BOM_JLCPCB.csv`, the CPL;
  - `PLACEMENT_CHECKS.txt`, `FOOTPRINT_CHECK.txt`, `COST_ESTIMATE.md`, `ORDER_SETTINGS.md`, `CONSIGNMENT.md`;
  - `hand_solder_bom.csv`, `excluded_from_assembly.csv`, the assembly drawings.
- **`build/`**:
  - `build/placement.json`, `build/route_report.json`, `build/budget.json`;
  - `build/txt/`: the datasheets as text.
- **`docs/images/`**: the schematic as PDF and as a PNG per sheet, the block diagrams, and `board_top.png`,
  `board_bottom.png`, `board_placement.png`: the board as built.  `build/view/` (untracked) has the other copper
  renders the build makes.
- **`datasheets/`**: 48 PDFs (tracked while the repository is private).  The small logic and discrete parts' datasheets (74LVC1G04, 74LVC1G17, 2N7002,
  AO3401A, the PTC, the TVS, the ferrite bead) are not there: fetch them into your own directory.
- **`gateware/`**:
  - `README.md`: architecture, register map, timing, tests;
  - `costaslink_core.v` and its blocks;
  - `costaslink_pynq.v` with `pynq/build.tcl` (Vivado); `top_icepi.v` (the Icepi Zero);
  - `driver/costaslink.py`, with `driver/test_sim.py` to run it against the RTL;
  - the overlay's reports are in `build/pynq/` (`timing_summary.rpt`, `utilization.rpt`).

## 7. Known open items (do not spend time rediscovering these)

- **CPL rotations.**  30 part numbers' CPL rotations are predicted, not yet read off JLCPCB's placement preview.
  The author reads them on the day of the order; do not spend effort on them.
- **`mfg/release/CONSIGNMENT.md` is out of date.**  It describes JLCPCB's older consignment flow (posting the parts
  yourself to Shenzhen).  JLCPCB's overseas process since 2026-08-12 is: register and get approval first, pay a
  refundable duty and VAT deposit and a 2 % handling fee, then ship to its Hong Kong warehouse (CLAUDE_CODE_CHAT.md,
  Response 16).  The file is known to be out of date.  Comments on the consignment plan itself are welcome.
- **`PLAN.md` §11's open questions:**
  - fitting the HMC536 on both assembled boards;
  - the campus channel (ISM or UNII-2C, after a scan).

  The LNA module's numbers are assumed until BRINGUP.md stage 5 measures them.  The licence is settled (W3JQ).
- **The silkscreen.**  The build log's 65 silkscreen "problems" are block and chip labels touching pads; JLCPCB clips
  silk on pads.  Two connector limits are left off on record: J208 (TRIG IN MON) and J502 (Q SLOW MON), with the
  reasons in `hardware/checks/labels.json`.
- **GND.**  `build/route_report.json` lists GND as "unrouted 1": the router leaves the pads that the pours join.  DRC
  counts 0 unconnected.
- **The gateware.**
  - The Icepi Zero's 100 MHz closes on five placement seeds of seven, and `make pnr-icepi` tries seeds until one
    passes.
  - The ECP5 IDDRX1F's sample order is from Lattice's documentation, not simulated.  BRINGUP.md stage 0.5 checks it
    on the bench.
  - The whitened stream (scrambler and Gardner timing) is not written; the BER check reads CMP_I only.
- **The board's history.**  `REVA_CHANGES.md` entries 4-7 were looked at and left as they are, with the reasons.
- **Rev B** belongs elsewhere: the comparator lab with the ECP5 on board (PLAN.md and CLAUDE_CODE_CHAT.md, Responses
  11-13).  Do not propose rev B features unless the finding changes a rev A decision.

## 8. What would be most useful back

All of it in `design_review_<YourName>/DESIGN_REVIEW_<YourName>.md`:

1. **The verdict in one paragraph:** order it, or not, and the one thing that decides it.
2. **The findings table:** severity (would kill the board / would cost a respin / would cost a day / cosmetic), the
   finding, where (file and line, sheet and designator, board coordinates), the evidence (datasheet page, number,
   measurement), what you ran or read to confirm it, and the fix.  Ranked by the cost of being wrong.
3. **Your answers on §3**, item by item: the arithmetic, not the adjective.  Say which items you did not get to.
4. **§4:** what nobody asked about.
5. **The CLAUDE_PCB.md check (§5):** the rules this board breaks, the gates the build does not run with their
   results, and the rules you would change or add.
6. **What you checked and found right,** briefly, so the author knows what was covered.
7. **Last, after your own draft:** the other reviewers' findings you agree with, the ones you dispute and why, and
   what everybody missed.
