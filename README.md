# CostasLink-PYNQ-Z2

A 5.8 GHz bidirectional link for quantum position verification that carries one or two bits from one
FPGA to another in the speed-of-light time plus about 23.5 ns of electronics, built to test three
modulations with one receiver: BPSK with a hardware Costas loop, FSK, and QPSK. It plugs onto a
PYNQ-Z2's Raspberry Pi header like `../GPSDO-PYNQ-Z2`. Two of them talk to each other.

**Status (2026-10-12, rev A, Prompt 30):** architecture and parts decided and
stock-checked, the schematic on seven sheets, ERC-clean, every symbol's pins audited against the
datasheets, every wire and every connector labelled with what is on it (`gen/levels.py`), the design
arithmetic asserted, the constraint files and the synthesizer register words generated, the first
gateware written and checked (`gateware/`), the annotated block diagrams drawn, the range model run,
the bring-up plan written ([`BRINGUP.md`](BRINGUP.md)), the board (120 x 100 mm, 4 layers) placed by
rule and by hand and routed by plan and router (PLAN.md §16), the JLCPCB release script written and its
gates passing on the board as it stands except DRC (`mfg/make_release.py`), the order costed (PLAN.md
§17), the review brief written ([`DESIGN_REVIEW_PROMPT.md`](DESIGN_REVIEW_PROMPT.md)).  Response 10 put
the five field ports on SMA and MMCX jacks, bound the header's interchangeable pins from the placed board
(`gen/pin_swap.py`), put both arm amplifiers' resistors at their pins, and worked out the constellation
from first principles (`sim/constellations.py`, PLAN.md §18: for two bits, a weak pilot at 45° with the
four corners, decided by one window comparator each).  Response 14 then made rev A the test bed for that
study: a seventh sheet of window comparators (I and Q, each side on its own 16-bit threshold, each with a
scope tap and a hysteresis option), a trim on the fast Q arm, a longer loop hold, and a trigger path that
skips the FPGA.  Response 15 labelled every connector by rows (one relation per row, checked on the
written board by `tools/label_check.py`) and found why the router kept failing (875 mm of top-layer ground
track a helper had laid before the router ran; PLAN.md §16).  It then wrote the experiment gateware for both
hosts (`gateware/README.md`: one core, the PYNQ-Z2 at 800 Ms/s over AXI-Lite, the Icepi Zero at 200 Ms/s over a
UART, a Python driver tested against the RTL), and writing it found that the transmitter ran whenever no
gateware drove it: header pin 24 is now TX_EN, active high, through an inverter with a 1 k pull-down
([`REVA_CHANGES.md`](REVA_CHANGES.md)).  The 2x20 socket is soldered at home, which makes JLCPCB's order
one-sided.  Four LLM reviewers went over build 17 (`design_review_*/`); build 18 fixes what they found
([`DESIGN_REVIEW_RESPONSE.md`](DESIGN_REVIEW_RESPONSE.md)), the worst of it the LO pairs, which were
crossed and are now straight and equal.  Prompts 26-29 added the interference survey
(`survey()`, from the window comparators' statistics), the system analysis around the radio
([`docs/SYSTEM.md`](docs/SYSTEM.md)), sheet 6's interference detectors (an AD8310 log amp on the fast Q
arm and its peak hold, +5V_RF and the board's temperature, read by a second ADS1115 at 0x49), and 6.8 nH
ESD / DC shunts at the three antenna jacks; rev A covers 4.9-5.9 GHz (the LNA's band; the balun reaches 5.95).  Prompt 30
put every value in one place (`sim/budget.py`, `gen/parts.py`, `gen/pins.py`), the driver's constants in a
generated module, and a check of every number these documents quote against the build.  Prompt 31 (2026-10-14, a fresh instance's overall look with three independent reviews, `design_review_Claude_Prompt31/`) found
and fixed two faults that would have killed the receiver (both ADC input filters drawn capacitor-first, 100 nF on the fast
arms' outputs; no DC blocks between the balun and the ADL5380's RF inputs), the SMA launches' inner-layer rings, and four
errors in the budget (own-transmitter rejection 21 dB not 31, FDD needs 52 dB of isolation; the ADL5380's 5.8 GHz IP1dB;
the static phase error 9.1° not 4.6°; WiFi captures sign(I) x Q) — REVA_CHANGES.md rows 30-36.  **The board
routes completely: DRC 0, and the release in `mfg/release/` passes every gate (2026-10-14).**  Left for the order day: the CPL rotations,
read off JLCPCB's preview.  Prompt 31 (2026-10-14) took the consignment out of the order: the balun is the TDK HHM1907B1 from
JLCPCB's shelf (the ADL5380 sheet's Johanson 5400 has none there), and the two ADI chips come from JLCPCB's shelf with a
Digi-Key fallback that the release applies only if the shelf is short on the day (`mfg/release/CONSIGNMENT.md`).  Nothing ordered.

* [`PLAN.md`](PLAN.md): the idea, the numbers, the antenna question, the parts with the reasons and
  the rejected alternatives, the header pin map, power, the board, bring-up, what could go wrong.
* [`BRINGUP.md`](BRINGUP.md): what to have on the bench, and the six stages from first power to a
  link between two hills, each with its pass condition and the risk it retires.
* [`CLAUDE_CODE_CHAT.md`](CLAUDE_CODE_CHAT.md): every prompt and response, with the decisions as
  they were made.
* [`DESIGN_REVIEW_RESPONSE.md`](DESIGN_REVIEW_RESPONSE.md): the four reviews of build 17, every finding
  fixed, documented or answered, and how useful each reviewer was.
* [`docs/TRAJECTORIES.md`](docs/TRAJECTORIES.md): from the idle to each QPSK corner at the receiver, in
  time and on the I/Q plane, with the comparators, the slow path and the noise (`sim/trajectories.py`).
* [`docs/HOSTS.md`](docs/HOSTS.md): what the Icepi Zero, a SYZYGY port (Brain-1) or an ECP5 on the board
  would change, in nanoseconds and in chips (`sim/hosts.py`).
* `sim/constellations.py`: idle plus N messages decided by comparators: false events by Rice's
  formula, the bits' time into the arm's rise, a search for the best layout (PLAN.md §18).
* `sim/budget.py`: every number the plan quotes, computed from the datasheets and asserted;
  `sim/rf_lines.py`: the 50 Ω line geometry on JLCPCB's 4-layer stack.
* `gen/`: the generator. `pins.py` (the header, one source of truth), `parts.py` (every part, LCSC
  code, consignment source), `symbols.py` and `footprints.py` (what KiCad's libraries lack),
  `sch_rx.py` / `sch_tx.py` / `sch_pwr.py` / `sch_ant.py` / `sch_slow.py` / `sch_win.py` (the six sheets),
  `schematic.py` (the root), `levels.py` (what is on every wire, from the budget); `placement.py`
  (the floorplan by hand, every passive by rule, the plan drawn to look at), `board.py` (the board,
  inside KiCad's Python, checking pcbnew's pads against the plan before any copper), `routes.py`
  (the RF lines and via fences by plan, the supply pours, the router's orders), `silk.py`.
* `hardware/`: the KiCad 10 project the generator writes; `hardware/checks/` holds the netlist and
  the ERC report for a reviewer without KiCad. Every signal wire (or pair) carries a **blue box**
  with its frequency, level, bandwidth and DC offset, the strings of `gen/levels.py` computed from
  the budget, so the sheets and the diagrams quote one set of numbers.
* `gateware/`: the experiment gateware (Response 15; `gateware/README.md`): one Verilog-2005 core with the
  transmitter's modes, the receiver's event decoder for every scheme of PLAN.md §18 (confirm or veto,
  latencies to the sample, a confusion matrix, a latency histogram, a BER check), the T/R sequencer, a
  counting gate for the thresholds and offsets, and a block-RAM logic analyser; the PYNQ-Z2's overlay from
  Vivado 2024.1 (`pynq/build.tcl`, timing met) and the Icepi Zero's bitstream (`make pnr-icepi`, 100 MHz);
  the Python driver `driver/costaslink.py`; `make lint sim sim-engines sim-axil sim-driver`.
* `docs/images/`: the schematic as PDF and PNG; `block_system`, `block_rx`, `block_tx`,
  `block_loop`, `block_modulations` (.svg to zoom, .png to glance): the annotated block diagrams,
  every arrow with its level, frequency, bandwidth and DC offset and a thumbnail of the signal,
  made by `docs/blockdiagram.py` from the budget.
* `sim/link_rates.py`: range against error rate for every scheme and amplifier tier (PLAN.md §13).
* `tools/`: KiCad from `kienv.py`; JLCPCB's parts API (`jlc_api.py`, cached with timestamps);
  the schematic writer (`kisch.py`); the checks (`sch_check.py`; `net_check.py`: power nets,
  one-pin nets, the signal paths walked, and every footprint pad carrying a net); `pcb_check.py`
  (KiCad's DRC with schematic parity); `label_check.py` (every connector's name printed, its own, and
  one relation to its connector across each row: Response 15); `render_pcb.py`; `sch_where.py` says
  what is drawn near a point.
* `mfg/cost_estimate.py`: what "5 PCBs, 2 assembled" costs at JLCPCB, Digi-Key and elsewhere, from
  JLCPCB's live prices and the calibrated fees (`build/COST_ESTIMATE.md`); `mfg/make_release.py`:
  the upload folder `mfg/release/` (gerbers, BOM, the two CPLs, `PLACEMENT_CHECKS.txt`,
  `FOOTPRINT_CHECK.txt`, `CONSIGNMENT.md` (what is consigned, if anything, and what the fallback costs), `ORDER_SETTINGS.md` in the
  order form's own order with every non-default value marked, `COST_ESTIMATE.md`), behind the gates
  of `CLAUDE_PCB.md` section 10: every code's JLCPCB description checked against the parts table,
  stock, the land patterns fitted, DRC clean, the CPL simulated, relative paths only.

Build everything with `python3 build.py` (KiCad 10 found by `tools/kienv.py`). Every value the
arithmetic chooses is written once, in `sim/budget.py`; the schematic, the board, the driver's
`gateware/board_constants.py`, every study the plan quotes and the block diagrams are remade from it, and
the last step, `tools/doc_check.py`, checks the numbers the hand-written documents quote against what the
build computed (CLAUDE_PCB.md section 2). The release and the cost ask JLCPCB over the network and run
by hand after it: `python3 mfg/make_release.py --refresh`, then `python3 mfg/cost_estimate.py`. The
rules the board is held to are the repository's `CLAUDE_PCB.md`.

Regulatory: a bare-chip radio with a custom antenna is uncertified; FCC §15.23 lets a hobbyist
build up to five for personal use, and the 5.725-5.875 GHz ISM band allows up to +30 dBm with
6 dBi antennas under §15.247. This board transmits about +10 dBm.
