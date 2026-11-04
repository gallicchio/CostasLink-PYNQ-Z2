# Hand-off: board A on 2026-11-03, for whoever sits down next (a laptop in the lab, a fresh agent)

Written 2026-11-02 20:59 PST by the session that ran the bring-up from the bench PC since 2026-10-28.  Nothing said in
that chat survives; this file and the ones it points to are the whole context.  Read in this order:

1. this file (where things are, the rules, the day's plan, what is running);
2. [`FINDINGS.md`](FINDINGS.md): what the bring-up found, as results (the digest of `BRINGUP_LOG.md`'s 4.0-4.33);
3. [`MONDAY.md`](MONDAY.md): the day's six steps, written for 2026-11-02 and not done that day (Jason could not come
   in); they are the plan for 2026-11-03 unchanged.  Steps 2-3 (the VNA, lifting C102) and 5 (two boards) are the ones
   Jason wants walked through;
4. [`README.md`](README.md) (how the bench talks to the board), [`BRINGUP_LOG.md`](BRINGUP_LOG.md) (every measurement;
   the firmware and server version tables at its top), [`REVB.md`](REVB.md), [`IMPROVEMENTS.md`](IMPROVEMENTS.md),
   [`TODO.md`](TODO.md); the gateware in [`../gateware/README.md`](../gateware/README.md); the system in
   [`../docs/SYSTEM.md`](../docs/SYSTEM.md).

Jason's words for this hand-off (2026-11-02): "I want to be ready tomorrow to sit down and tell you to walk me through
that VNA list and setting up a second board, almost certainly with a new instance on a laptop in the lab.  All context
should be communicated to that agent through .md files in the repo."

## 1. The rules (Jason's, in force; a new agent has not heard them)

* **No `sudo` on the PC or the laptop.**  Only Jason runs root commands there: put each one in the chat as a copy-paste
  block and wait.  `sudo` on the PYNQ is fine (user `xilinx`, password `xilinx`).  Do not install SSH keys on the PYNQ
  (Jason's call); do not work around a permission denial.
* **Commit code and docs; never push.**  Bench data stays on the PC (`bringup/data/` is gitignored); a few example
  pieces of data may go in.  Nothing copyrighted into the repo (datasheets stay out; their text extracts are fine).
  Do not commit `OpticsPCBs/CLAUDE_PCB.md` (Jason's working copy is modified) and do not `git stash`.
* **Instruments:** no `*RST` on the Siglents (scope, generator); outputs off when done; ask what is cabled before any
  signal test; the spectrum analyzer is left sweeping continuously at full span when handed back; a low level or a spur
  is investigated across the hardware's whole frequency range, not only 5-6 GHz.
* **The board:** never VR_I / VR_Q above 0.6 V; never a bare TX ANT to RX ANT cable (pads: RX ANT's absolute maximum is
  +1 dBm); do not overdrive the SMA outputs; do not change the PYNQ's network settings or the board's calibration
  unless asked (avahi on the PYNQ needs Jason's OK).  Power order: the PYNQ, then the overlay loaded (the server
  answering with an accepted ID), then the board (`bench.py --board A psu up` does it in order).
* **The PYNQ:** PYNQ 3.0.1, every overlay from Vivado 2022.1, builds run `nice`d (the PC is shared).  If the PYNQ has to
  be rebooted more than a few times for no known reason, keep things powered off (Jason, 2026-11-01).
* Everything measured is logged: `BRINGUP_LOG.md` (a row per result, with the file names), `REVB.md` (what rev B
  should change, with the evidence), `IMPROVEMENTS.md` (gateware and software, done and next), `TODO.md`.

## 2. The state at hand-off (2026-11-02 20:59 PST)

**Board A** is on the office bench, over the air at 5200 MHz (its own TX the carrier, FPV antennas 30-40 cm apart,
the B210 beside them), locked since 03:24 this morning, the self-test running its rounds (plan 'cycle'), the page at
http://192.168.8.142:8080/ .  Firmware **ID 0x434C000D** (ID 13) from `~/costaslink_id13/` on the PYNQ through the
symlink `~/costaslink_current`, started at boot by `costaslink-netbus` (after the image's `bootpy.service`).  The server
files beside it that hold learned state: `link.json` (the link at 5200 MHz with the carrier null), `selftest.json`
(on, plan, calibrate, window_bias 0.6), `learned.json` (the learning step's profile for both lock points),
`windows.json` (each lock point's calibrated windows, put back at setup), `levels.json` (each point's last sweep,
for the page's panel).  The board's clock is UTC; the PC is PST.

**Power (the E3646A, USB serial):** output 1 the board at 5.30 V, 1.5 A limit (the board draws about 0.9 A); output 2
the PYNQ at 12.0 V, 1.5 A limit, OVP 13.5 V.  One switch serves both outputs; the board is switched by its output's
voltage (0 V or 5.3 V).  `python3 bringup/bench.py --board A psu up | cycle | pynq-off`; the watchdog's pause is
`python3 bringup/bench.py pause --minutes 10` (a top-level command, not under `psu`).

**Running on the bench PC** (started from the chat; they survive it as background shells until the PC is restarted or
they time out; stop them with `pkill -f <name>` before the board is moved):
* `bringup/bench.py --board A --stage watch run watch --hours 64 --pynq-misses 6 --amps-hi 1.5 --pynq-cycles 3`: the
  watchdog (since 2026-11-01 11:02): logs the current, power-cycles a silent PYNQ at most 3 times, else switches both
  outputs off.  **Pause it (`bench.py pause --minutes 10`) before any deliberate server restart or move.**
* `bringup/scopewatch.py --hours 60`: the bench scope photographed during each self-test step, posted to the page.
* `scratchpad/photo.sh` (a 10-minute photograph of the page into `bringup/data/board_A/soak/review_HHMMPST.png`): not
  needed any more; harmless.
* No soak is running (soak15 ended 08:13; its log `bringup/data/board_A/soak/soak15_world.log`).

**The bench network** (`bringup/bench_config.json`): the PYNQ 192.168.8.142 (DHCP on eth0; **also always
192.168.2.99/24 on eth0:1**, static), the DSA875 analyzer 192.168.8.114, the SDS2104X Plus scope 192.168.8.203, the
SDG1032X generator 192.168.8.246; the E3646A and the Fluke 45 on USB-serial (FTDI, `/dev/serial/by-id/...`); the
B210 on USB 3.  The PC is `bell`, 192.168.8.207.

**Git:** branch `master`, the latest commits of 2026-11-02 (`a70998b` BRINGUP_LOG 4.33 and the night's fixes);
`origin` is `git@github.com:QuantumQuasars/OpticsPCBs.git`; **nothing has been pushed since the bring-up began**
(some 280 commits ahead: Jason pushes).

## 3. Working from a laptop in the lab

What the laptop needs that the bench PC has:
* **The repo** (`git clone git@github.com:QuantumQuasars/OpticsPCBs.git`, or a copy of the PC's working tree: the PC's
  tree has the unpushed commits, so clone from the PC or push first).  The bench data (`bringup/data/`) is not in git;
  copy `bringup/data/board_A/` if the day's analysis wants the history.
* **`~/lab-instrument-control`** (QuantumQuasars/lab-instrument-control: the instrument drivers `bench.py` imports:
  `agilent_E36xxA`, `fluke_45`, `rigol_DSA875`, `siglent_SDS2104X`, `siglent_SDG1032X`; its `99-bench-instruments.rules`
  for USB access, and the user in `dialout`).  Set `LAB_INSTRUMENT_CONTROL` if it lives elsewhere.
* Python 3 with `numpy`, `pyserial`; `PIL` and `chromium-browser` only for the page photographs; UHD's Python
  (`python3-uhd`) only for the B210.
* **Reaching the PYNQ** away from the bench network: a direct Ethernet cable from the laptop (set to 192.168.2.10/24)
  reaches the PYNQ at **192.168.2.99** whatever DHCP does; put that address in `bench_config.json` (`pynq_host`) and in
  the page's URL (http://192.168.2.99:8080/).  The PYNQ's own DHCP address on another network is unknown until it joins
  it (its serial console, 115200 on the micro-USB, says; or `arp -a` after a ping sweep).
* **The VNA (8720ES, the RACON room):** its driver is in `~/lab-instrument-control/hp/` (GPIB through a Prologix
  GPIB-USB adapter, `gpib/gpib.md`; calibration and Touchstone output, run on the 8720ES on 2026-10-20/21), so the
  laptop has it with that clone.  The earlier measurements and their log (the calibration CAL1020B with isolation, the
  fixture, what to trust) are `~/DroneSDR/vna/vna_measurements/README.md` and its `.s2p` files on the bench PC, with
  `plot_vna.py` beside them: not in this repo; copy that folder if the day's plots should sit beside the old ones.
* The bench's `bench_config.json` names USB serial ports by their FTDI IDs; on the laptop they are the same strings
  (the adapters carry them), and the LAN addresses change with the lab's network.

### 3a. The lab laptop as found (`zmash`, 2026-11-03, BRINGUP_LOG 4.35)

* **Config:** `COSTAS_BENCH_CONFIG=bringup/bench_config_laptop.json` in front of every `bench.py` command (the PC's
  `bench_config.json` is left alone).  `bench.py check` answers for both supplies and the board.
* **Power: two E3632As, not the E3646A.**  The "top" one (FTDI `FTER3DQU`, `CAL:COUNt?` +29) is the board's, 5.30 V,
  1.5 A; the "bottom" one (`FTEP2CPY`, +20, FACTORY CAL 2014) the PYNQ's, 12 V, OVP 13.5.  `psu.pynq_serial` in the
  config makes `psu up | cycle | pynq-on | pynq-off` drive the PYNQ's own supply in the same order as the E3646A's
  output 2 (the board off first; on only with the server answering our ID).  `psu up --volts 5.3 --amps 1.5` brought
  board A up at 5.295 V, 0.891 A, CV (16:33 PST).
* **The PYNQ** on a direct cable: the laptop's `enp0s31f6` is 192.168.2.119/24 (DHCP from a router at 192.168.2.1);
  the PYNQ answers at its static 192.168.2.99 and takes 192.168.2.142 by DHCP there.  Its micro-USB console is
  `/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0` (115200; the FT2232 appears 0.6 s after the 12 V does: it is
  powered by the PYNQ, not by the USB); the console is logged in as `xilinx` at boot.  No SSH key on it (Jason's rule):
  files go over the console, or the PYNQ fetches them (`wget` from a `python3 -m http.server` bound to 192.168.2.119);
  `sudo -S` on the PYNQ with its password.  From power to the shell 34-41 s, to the server answering about 90 s.
* **The instruments here:** the 8720ES at GPIB 16 through the Prologix `PXAESUX9` (MY41003347, firmware 7.72: the same
  analyzer as October's campaign; found uncorrected at +5 dBm, 50 MHz-20.05 GHz, 201 points); an SDS1104X-E on USB
  (`/dev/usbtmc0`, 100 MHz: not the bench's SDS2104X, so `bench.py`'s scope commands do not apply; its driver now opens
  on USB alone, lab-instrument-control); no Fluke, DSA875, SDG or B210.  The udev rule is installed.
* **What is not on this laptop:** the October VNA files (`~/DroneSDR/vna/vna_measurements/` holds only the 2025
  filter sweeps here), the vendors' manuals (`~/lab-instrument-control/manuals_untracked/`), and `bringup/data/`.
  The 8720ES goes to -40 dBm without pads (`vna.power(-40)` read back, no error; 2026-11-03, BRINGUP_LOG 4.36).
* **The 8720ES's calibration here: register 29** (`RECAREG29;`): full 2-port, 85052D (3.5mmD), 3-6.5 GHz, 1601
  points, 1 kHz IF bandwidth (4.2 s a sweep), -40 dBm, isolation omitted, at the ends of the two test cables.  Park it
  in `HOLD;` between measurements: with the 2-port correction on, every sweep throws option 085's mechanical transfer
  switch (an audible click every 4-8 s; `hp.md`).
* **Vivado:** 2021.2, 2022.1, 2022.2, 2023.1 and 2024.1 under `~/Downloads/Xilinx/Vivado/`.  PYNQ 3.0.1's overlays are
  2022.1's (section 1): `source ~/Downloads/Xilinx/Vivado/2022.1/settings64.sh`, then from `gateware/`
  `nice vivado -mode batch -source pynq/build.tcl -tclargs -strategy Performance_NetDelay_high -out <name>`.  This
  rebuilt ID 13 from `0618a0b` in about 7 minutes with its logged timing (WNS +0.138, WHS +0.052, 13.015 ns) and a
  configuration stream identical to the deployed `~/costaslink_id13/costaslink_top.bit` (`build/pynq/overlay_2022.1_id13_laptop/`).
* **Never load an overlay by hand while `costaslink-netbus` runs.**  On 2026-11-03 an overlay built from the pushed
  (pre-bring-up) tree was loaded over ID 13 under the running server: the PYNQ froze (no ping, no console) within
  minutes and needed its 12 V cycled; the service brought ID 13 back at the next boot (4.35).

## 4. The day: what Jason wants walked through

**Step 1 (if the students come): the demonstration**, MONDAY.md section 1: the page with `?controls=1&view=demo`, the
self-test's plans ('a3delay', 'settle', back to 'cycle'), the B210's interference one at a time (`b210demo.py`), the
physical path.  Everything it needs is on and running.  Run the learning step (`{"plan": "learn"}`, 11 minutes quiet)
before any physics-style run: the profile in use is from 2026-11-01 15:58.

**Step 2: the VNA (MONDAY.md section 2, TODO rows 6-7).**  Board A, its E3646A and the PYNQ move to the RACON room
(or a lab supply at 5.3 V, 1.2 A limit, and the PYNQ on its own 12 V).  Before the move: `bench.py pause --minutes 30`
(the watchdog would otherwise count the PYNQ's silence), then the outputs off.  The 8720ES full 2-port calibration
3-6.5 GHz, source -30 dBm or less into the board (RX ANT's maximum +1 dBm):
* **Test A: RX ANT's S11**, powered and unpowered.  Expected (`sim/aslaid/REPORT.md`, `layout/lna_input_model.py`):
  about -0.8 dB at 5.8 GHz, above -2 dB over 5.5-6.1 GHz, a sharp feature near 5.9 GHz: C102's branch (0.5 pF at the
  LNA's input, series-resonant with its 1.8 mm trace) shorts the input there.
* **Test F: S21 RX ANT to RX MON** at DSA 0 and 31.75 dB (`bench.py --board A board call dsa 0` / `31.75`, or `vna_tests.py measure NAME --dsa 0`, which holds it; the DSA is
  software), -40 dBm in: the chain's gain without the TX leak.  The bench's map (BRINGUP_LOG 3.3, REVB 8) read 37-44 dB
  at 3.0-4.4 GHz, 30 at 5.0, about 7 at 5.7-5.8.  **TX ANT to TX MON** too (REVB 4, 6: the TX makes +3.8 dBm at 5.8 GHz
  against +9.8 planned, and LO TX MON reads 25.7 dB low).
* Save every trace as Touchstone into `bringup/data/board_A/vna/` (not committed); the plots and the numbers go into a
  BRINGUP_LOG row.  `bringup/vna_tests.py` does it (2026-11-03: rows 4.36-4.37): the calibration's checks, the DSA or the
  TX's carrier null held through the sweeps, the spot numbers and the plot.

**Step 3: lift C102 (MONDAY.md section 3, TODO row 9).**  The 0.5 pF shunt from the LNA's input (U101 RF_IN) to ground:
lift it, or only its ground end, and leave the pads empty.  Prediction: **+24-25 dB of receive gain at 5.8 GHz**, S11
from -0.8 to about -7 dB.  Repeat tests A and F at once (the calibration stands).  If it misbehaves, a 0.5 pF goes back.

**Step 4: the link again, one board (MONDAY.md section 4).**  Back in the office: the map over 3-6 GHz
(`overnight.py map`), `campaign.py cal` for the carrier null and the arms' offsets at 5.8 GHz, a `link.json` for 5.8
GHz if the antennas favour it, then `soak.py run` overnight at both carriers.

**Step 5: two boards (MONDAY.md section 5).**  Needs:
* **Board B brought up** (never powered): BRINGUP.md stages 1-3 as board A took them on 10-28/10-29: first power with
  the current limit, the rails, the synthesizers, the TX, the receive chain.  `python3 bringup/stages.py` lists the
  procedures; `bench.py --board B --stage <name> run <name>` runs each with its verdict and logs to
  `bringup/data/board_B/`.  Board A's numbers to compare against are BRINGUP_LOG's stage 1-3 rows.
* **A second PYNQ-Z2**: the PYNQ 3.0.1 image on its card (README.md 'Setting up'), the ID 13 overlay deployed
  (`OVERLAY=build/pynq/overlay_2022.1_id13 bringup/deploy_pynq.sh xilinx@<its address>`, then `install_service.sh` on
  it as root, then the driver files `gateware/driver/{linkd,selftest,dashboard}.py`, `dashboard.html` and a `link.json`
  beside the server: `deploy_pynq.sh` copies the core driver only; copy the rest by `scp` as the version table in
  BRINGUP_LOG shows).  Its own IP; a second `bench_config.json` (or `--board B` with its own `pynq_host`).
* **The frequency plan:** one one-way link each way, apart in frequency (A to B at 5.2 GHz, B to A at 5.8 GHz): the
  5.8 GHz receive needs C102 lifted on both boards.  Until then one direction (A to B at 5.2 GHz, B's TX muted).
* **The software that exists for two boards, untested across two:** `link.json` takes separate `tx_mhz` and `rx_mhz`
  (linkd tunes each synthesizer; VR belongs to `tx_mhz`); the self-test's plans 'send' (BPSK data out continuously) and
  'check' (the other's data checked, its timing recovered by `ber_cdr.v`); single symbols across boards count decisions
  but not right/wrong (no sender's sequence), so latency across boards is the turnaround's (B answers on the fast path,
  A times the round trip, BRINGUP_LOG 3.4g-h).  Two pages, one per PYNQ.

**Step 6: across the long lab (MONDAY.md section 6):** the two VV 24 dBi grids on their 10 m cables (the VNA's link
between them was -48.2 dB, RX ANT about -39 dBm), the lock, the schemes, the turnaround (135.6 ns of flight to
subtract), the latency line from three distances.

## 5. What is open (in one place)

* **A stronger carrier makes QPSK decide wrong** (526 in 7.5 M at -4 dB, 4 489 at -5, 20 390 at -5.75): the windows
  follow a weaker carrier down but never up, and the learned profile applies within 15 % of its level.  Proposed: an AGC
  on the DSA holding the I leg at the calibrated level (IMPROVEMENTS 19); Jason's call, since it changes how linkd
  drives the attenuator.
* **QPSK's latency tail on lock point -** (2-3e-7 of decisions 80-214 ns, right but late; none on +; every table
  alike): IMPROVEMENTS 18, plan 'qpsktail' reproduces it in 10 minutes.
* **The holdover** (carrier gaps up to ~100 s ridden through, half of them a half-cycle slip): off; on is Jason's call.
* **The B210's self-loop at 5240 / 5400 MHz** disturbed the board's own data once (soak15 notes, not re-checked).
* The 8720ES tests, C102, 5.8 GHz, board B, two boards, the long lab: this file's section 4.
* Rev B: [`REVB.md`](REVB.md) (what rev A teaches, 47 rows), [`../docs/REVB_DESIGN_SPACE.md`](../docs/REVB_DESIGN_SPACE.md)
  (the platforms and the QPV deployment, written the night of 2026-11-02).

## 6. The file map

| where | what |
|---|---|
| `gateware/` | the Verilog (`tx_engine.v`, `rx_engine.v`, `ber_cdr.v`, `ihold.v`, `lockmon.v`, ...), `regmap.py`, the testbenches, `README.md` |
| `gateware/driver/` | `costaslink.py` (the driver), `netbus.py` (the server, port 5800), `linkd.py` (the recovery and setup), `selftest.py` (the rounds, the calibration, the learning step), `dashboard.py` + `dashboard.html` (the page, port 8080), `test_sim.py` (30 tests against the RTL simulation: `make sim-driver`) |
| `build/pynq/overlay_2022.1_id13/` | the bitstream and hwh deployed now (`costaslink_top.bit`, `.hwh`); `build_id13.log` |
| `bringup/` | this folder: `bench.py`, `stages.py`, `soak.py` (random disturbances, audited), `scopewatch.py`, `b210link.py` (the B210 as the other end), `b210demo.py`, `abtest.py`, `campaign.py`, `overnight.py`, `locklab.py`, `weekend.py` |
| `bringup/data/board_A/` | the raw logs (JSON lines by day), `soak/` (the soak logs and the page photographs), `ab/`, `b210link/`, `vna/` (to make) |
| `docs/` | `SYSTEM.md` (the QPV chain, the verifiers' sync, platforms), `HOSTS.md` (latency by host), `LOCK.md`, `PATHS.md`, `LAUNCH.md`, `REVB_DESIGN_SPACE.md` |
| `../SyzygyRadioDrivers/` | a colleague's SYZYGY OOK board (the field I/O rev B copies: 4 BME outputs, 4 detector inputs) |
