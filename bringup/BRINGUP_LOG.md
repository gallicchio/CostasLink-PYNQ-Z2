# Rev A bring-up log

The as-built rev A, measured against [`../BRINGUP.md`](../BRINGUP.md)'s pass conditions.  Every number here is a reading
in `data/board_<X>/<date>.jsonl` (the time, the instrument and its settings are there); this page is the summary, written
as the stages go.  What a rev B should change is in [`REVB.md`](REVB.md).

**The boards.**  JLCPCB order 13544840A_Y21, delivered 2026-10-28: five boards, two assembled on the top.  The assembled
two are **A** and **B** (marked on the back silk by hand, beside J302); the three bare ones C-E.

| board | J302 soldered | shunts | stage reached | notes |
|---|---|---|---|---|
| A | | | 0 | |
| B | | | 0 | |

**The software on the bench (2026-10-29).**
- **The PYNQ.** The stock `pynq_z2_v3.0.1.img` (PynqLinux 3.0 "Belfast", kernel `5.15.19-xilinx-v2022.1`, pynq 3.0.1,
  Python 3.10.4). On the lab LAN at 192.168.8.142 by DHCP, and at its static 192.168.2.99. The bench PC's key is
  installed for `xilinx`.
- **The overlay**, `build/pynq/overlay_2022.1/` (from 12:20): Vivado 2022.1, the release PYNQ 3.0 is built on, from the
  working tree at `9561e5d` plus the day's gateware fix (below).
  - Bit sha256 `a416f915...`, `.hwh` `fa0175a7...`.  Timing: WNS +1.298 ns, WHS +0.030 ns.  5023 LUTs, 5511 flip-flops,
    9 BRAM tiles; the core at 0x43C00000 (4 KB).  I2C SCL / SDA each an IBUF + OBUFT, TX_Q1 an OBUFT (build.tcl checks).
  - Deployed to `~/costaslink/` on the PYNQ, where the driver runs under its Python 3.10.
  - Before it, kept for the record and not to be used: `overlay_2022.1_r0` (`b6a5a083...`, the committed gateware)
    and `_r1` (`812aba1f...`, plus the I2C timeout).  Both, like the 2024.1 overlay of 2026-10-11 in
    `build/pynq/overlay/` (`8532eddf...`), drive the I2C lines instead of releasing them.
- **The gateware fix (2026-10-29).**  Vivado synthesized the block design's module reference out of context and
  "Converted tricell instance to logic" (Synth 8-5799, a critical warning in every build so far) on i2c_scl, i2c_sda
  and tx_q1: no I2C transaction could ever have worked on the PYNQ.  `build.tcl` now synthesizes the block design
  globally and refuses a bitstream whose three tristate pins do not end in a tristate buffer.  And the I2C master
  gives a stuck bus up after 10 ms (it waited for SCL forever), with I2C_CTRL [19] timeout, [20] SCL, [21] SDA:
  `tb_costaslink.v` holds SCL low and checks both, `make sim-driver` 27 tests pass.
- **Why these overlays fit the board.** The header's pin map (`gen/pins.py`, the XDC's one source) is unchanged since
  Prompt 17; the RTL's other changes since 2026-10-11 are two renames.
- **The driver:** the repository at `70f9e05` plus the bring-up's changes below.

**On the PYNQ (2026-10-29 11:43):** the board powered with the PYNQ up (its base overlay loaded, the header undriven),
then the overlay loaded by starting `pynq_serve.sh` by hand (sudo, nohup; not yet the boot service).  The supply at
5.30 V from 11:47 (+5V_RF 4.976 V by the board's own V5_MON at 0.93 A).  `stages.watch` guards it while unattended:
off on a current outside 0.6-1.2 A, a trip, +5V_RF outside 4.75-5.30 V, the NTC over 85 C, or the PYNQ silent.  At
12:16:24 it switched the board off by mistake: the server's restart for the new overlay broke its connection, it did
not reconnect and counted the PYNQ silent (fixed: it reconnects once before counting a miss).  The board was off 90 s,
mid stage 1.5 (the EEPROM writes were simply redone), and the PYNQ drove its pins meanwhile.

**The instruments on the bench (2026-10-29)**, all answering through `bench.py check`:

| instrument | type | link | which one |
|---|---|---|---|
| Agilent E3646A | power supply (2 outputs; output 1 to the board) | RS-232, FTDI `A9PUYBUD` | the second unit: `CAL:COUNt?` +61, factory cal 29 Sep 2007, both outputs work (the first unit, +21, has a dead output 1: lab-instrument-control `hp/hp.md`) |
| Fluke 45 | multimeter | RS-232, FTDI `A95AME9U` | serial 9166018 |
| Rigol DSA875 | spectrum analyzer (9 kHz-7.5 GHz) | LAN 192.168.8.114 (raw socket 5555) and USB | DSA8E163700011 |
| Siglent SDS2104X Plus | oscilloscope | LAN 192.168.8.203 and USB | SDS2PDDX6R0722, firmware 5.0.1.3.9R12 |
| Siglent SDG1032X | function generator | LAN 192.168.8.246 and USB | SDG1XCAC3R0195, firmware 1.01.01.30R1B2 |
| Ettus USRP B210 | SDR (50 MHz-6 GHz, 2 TX, 2 RX) | USB 3 | serial 310BR0607, rev 4, firmware 8.0, FPGA 16.0 (UHD 4.9) |
| PYNQ-Z2 | the host | LAN 192.168.8.142; JTAG and console on USB (`usb-Xilinx_TUL_1234-tul-if01`: the console) | |

The scope, the generator and the analyser are used over the LAN for now. Their USB links need lab-instrument-control's
udev rule (`99-bench-instruments.rules`), which the reinstalled PC does not have yet.

## Before power (2026-10-28)

Read before any board was powered; both are driver fixes, made and tested in the RTL simulation:

1. **Stage 0.4 / 1.5's "every DAC channel to mid-scale" would have put the modulator's baseband pins at their absolute
   maximum.**  The MCP4728s leave the factory with 0 V on every channel (its Table 4-2).  `bringup_stage1(eeprom=True)`
   wrote 1.65 V to all eight, VR_I and VR_Q included, as power-up defaults.  With the reference at 1.65 V through R203's
   300 ohm, the I ladder's 11 point (the gateware's idle, TX_IDLE = 0x7) sits at (2 x 3.3 / 2.2 k + 1.65 / 300) / (2 / 2.2 k
   + 1 / 300) = 2.0 V on IBBP, and the Q ladder (348 ohm) with TRIG IN high at 2.2 V on QBBP: the ADL5375's absolute maximum
   is 0 to 2 V on those pins (its Table 2), the operating range 0-1 V.  And the driver's DAC shadows started at mid-scale,
   so any later single-channel write (`dac(DAC1, VC_OFF=...)`, stage 2.2's VCXO sweep) would have written the same 1.65 V
   to both references.  Now: `DAC_DEFAULT_V` (VR_I 0.2125 V, VR_Q 0.2456 V, the rest 1.65 V) is the shadows' start, the
   runtime write and the EEPROM default; `dac()` and `dac_eeprom()` refuse a reference over 0.6 V (`VR_MAX_V`, 1.18 / 1.47 V
   at the pins at worst).  BRINGUP.md stage 0.4's sentence wants the same correction.
2. **The LO MON jacks are dark after `pll_init()`.**  J109 LO RX MON (and J204 LO TX MON) take RFOUTB, and the power-up
   words (`max2871_words.vh`) leave RFB_EN at 0.  `lo_mon(which, on)` resends the six words with it set; `pll_tune` keeps
   the setting.  Stage 2.2 calls it.
3. Stage 1.5 now also writes the four window thresholds above the idle (V_MID + 0.1 V: the AD5696R starts at 1.25 V, under
   the arms, which holds its comparators high), and reads the detectors (V5_MON, TEMP) for the pass condition.

## What to gather, and which instrument does what

Have, on this bench or in the lab, and to bring to this PC:

| for | thing | stages |
|---|---|---|
| the boards | the 2x20 sockets J302 (C2977589) x 2 and the 2.54 mm shunts (C5305) x 14 + spares; a loupe or the USB microscope; `mfg/release/CostasLink-PYNQ-Z2_assembly_top.pdf` and `PLACEMENT_CHECKS.txt` printed; flush cutters (the five 5.8 GHz SMAs' centre pins to within 0.3 mm of the solder) | 1.0 |
| the PYNQ | the PYNQ-Z2 and its 12 V supply (the board does not take the PYNQ's 5 V: JP301 open); a micro-USB cable (its serial console); an Ethernet cable; a microSD card of 16 GB or more and a USB card reader (this PC shows no reader); the shared standoff | 1.5 on |
| the 5 V | the **E3646A**'s output 1 (on the bench: the 0-8 V 3 A range, OVP crowbar, no OCP, one output switch for both outputs, so `bench.py` holds output 2 at 0 V and 20 mA), or an E3632A (0-15 V 7 A, OVP, OCP); either with a USB-RS-232 adapter and a null-modem cable that carries DTR and DSR (`hp/hp.md`); a **USB-A socket breakout to banana or screw terminals** and a **short, heavy USB-A-to-C lead** (under 30 cm: the PTC, FET and bead already take 0.21 V); banana leads | 1 on |
| the rails | the **Fluke 45** with its adapter and a null modem (3-wire is enough), and fine-tipped leads or micro-grabbers for TP301-TP308 | 1.2 |
| 5.8 GHz | the **Rigol DSA875** (9 kHz-7.5 GHz, on the LAN since its USB hub failed) and an **N(m)-to-SMA(f) adapter** for its input; **U.FL-to-SMA pigtails x 6+** (twelve monitors are U.FL, 30 matings each: leave leads on the ones used most); SMA m-m leads 3 x 150 mm and 2 x 1 m; **SMA 50 ohm loads x 3** (TX ANT and RX ANT while they are not cabled); the two Nooelec pad kits (two 20 dB = 39.7 dB for stage 3's loopback; never less than 20 dB between TX ANT and RX ANT) | 2 on |
| baseband | the **SDS2104X Plus** (4 channels; it is 100 MHz unless upgraded: the edges of stage 3.4 want more), **MMCX-to-SMA leads x 6** (REF OUT J108, ERR J106, VC J107, TRIG IN MON J208, I SLOW MON J501, TR A J490), SMA(f)-to-BNC(m) adapters x 4 and BNC leads, two x10 probes (TR A on 1 M; the summing nodes) | 2.2, 3 |
| a reference | the **SDG1032X** (25 MHz, 1 V p-p open circuit into REF IN J203, which is high impedance: R214 is DNP), a BNC-to-SMA lead | 2.4 |
| heat | the IR camera or thermometer | 1.4 |

Worth borrowing now for stages 3-4 (each needs a driver here; I can write it from the manual):

| thing | where | what it gives |
|---|---|---|
| **Agilent 54855A** Infiniium (6 GHz, 20 GS/s, 50 ohm inputs; LAN as SICL / VXI-11) | (named in chat) | stage 3.4 and 4.2's latencies on real edges: TRIG OUT A against CMP I MON, the 15 ns + the cable, where the 100 MHz SDS sees 3.5 ns rise times.  Manual here; the driver needs scpi_link's VXI-11 device name made settable first |
| **HP 5370B** time-interval counter (20 ps single shot, GPIB through the Prologix) | stock room | the same latencies as statistics over 10^4 events.  No manual here yet |
| **Agilent E4438C** ESG (to 6 GHz with option 506: read its label) or the **HP 8665B** (100 kHz-6 GHz, no manual here) | RF lab | a known carrier at RX ANT: the receive chain's gain at RX MON (stage 3.1) independent of the board's own transmitter, `received_dBm()`'s calibration (4.0, 4.5), the fast and slow paths' floors.  Until one comes, the **B210** on the bench gives a 5.8 GHz carrier of uncertain level: set it against the DSA875 through the same leads and pads, then into RX ANT |
| **8720ES** VNA, at -30 dBm or less into the board | RACON room | S21 RX ANT -> RX MON with the board powered: the chain's gain across 4.9-6 GHz and the DSA's 0.25 dB steps; S11 of the five 5.8 GHz SMAs (the launches' field solve against the board); the HMC536's loss and isolation in both states |
| **FieldFox N9918B** (26.5 GHz) | RF lab | the second harmonic at 11.6 GHz at TX MON (stage 5's item, before the PA) |

## Stage 1.0: out of the bag

Board A: the top scanned at 600 dpi and photographed (`data/board_A/photos/`), each check against the assembly drawing and
the maker's marking convention (the notes in `data/board_A/2026-10-29.jsonl`), and by Jason with the loupe.  Directions:
the five 5.8 GHz SMAs to the north, as the assembly drawing is drawn.

| check | A | B |
|---|---|---|
| (a) the nine SMAs' barrels off the edges (five up, three left, J203 right) | pass (scan) | |
| (b) D303 cathode bar (SMAJ5.0A), C320 stripe (100 uF polymer), D301 / D302 (LEDs), D501 (peak detector) | C320 pass (the can's minus stripe opposite the silk +); D303, D501 pass (bands at the west end, loupe); LEDs: lit at 1.2 | |
| (c) pin 1 by the dot: U104 ADL5380, U201 ADL5375, U102 PE43711, U115 / U203 MAX2871, U101 LNA, the four THS4541, U401 HMC536; T101's marked end at the top beside the dot (microscope) | pass: U104, U201, U102, U115, U203, U106, U502 (phone close-ups), U501, U401, U105, U101 (loupe); T101: a stripe on its marked end (north end to confirm) | |
| (d) the three ADL5611s' wide tab toward the RF output; the U.FLs' signal pad on the track side | pass: U103, U117, U202; all 22 U.FLs | |
| J302 on the back, pin 1 at the right-hand end of the bottom edge, square | | |
| shunts: JP101 Q-, JP102 Q+, JP103 CMP, JP201 TCXO, JP203 fitted; JP202, JP301, JP302, JP303 open | | |
| the five 5.8 GHz SMAs' centre pins clipped to 0.3 mm | | |
| every placed part there, the DNPs bare (scan: bare gold at each footprint) | pass: 339 small parts fitted, the 13 DNP resistors bare | |
| markings | MAX2871 `2871E TJ541 +BEAP` (genuine format: LCSC's photo of C7458627), ADL5380 `#2421`, ADL5375-05 `#2509`, PE43711 `2605 FL1751`, THS4541 `TI 26I CJ67` | |

## Stage 1: first power, no RF

| step | expected | A | B |
|---|---|---|---|
| 1.1 smoke, 0.10 A limit | into the limit at a volt or two | pass: 1.87 V in the 0.10 A limit; 2.38 V at 0.25 A, 2.95 V at 0.50 A, 4.61 V at 0.80 A (all CC), CV from 1.10 A (`stage1.ramp`) | |
| 1.2 +5V_IN (TP301) | within 0.15 V of the supply | **4.862 V at 5.147 V, 0.871 A: 0.285 V below** (the path below); 4.958 V at 5.247 V | |
| +5V_RF (TP302) | >= 4.85 V | **4.823 V at 5.147 V (low)**; pass, 4.918 V, with the supply at 5.25 V | |
| +3V3_PLL_TX (TP303), +3V3_PLL_RX (TP304) | 3.30 +- 0.05 | pass: 3.283, 3.268 V | |
| +3V3_ANA (TP305), +3V3_DIG (TP306), +3V3_OSC (TP307) | 3.30 +- 0.05 | pass: 3.285, 3.269, 3.299 V | |
| LEDs D301, D302 | lit | pass | |
| 1.3 current, synthesizers unprogrammed | 0.89-1.29 A (+- 10 %) | pass: 0.865 A at 5.148 V, 0.871 A after 20 min, 0.885 A at 5.247 V (the MAX2871s draw almost nothing unprogrammed) | |
| 1.4 heat at 10 min: ADL5380, ADL5375, 3 x ADL5611, 2 x MAX2871 | 50-70 C, nothing over 85 C | 65 C at most, a blob around U104 (the IR camera cannot resolve parts); the board's TEMP sensor once on the PYNQ | |
| 1.5 I2C | 0x0C 0x48 0x49 0x60 0x61 | pass with the fixed overlay (12:16): the five.  First **stalled, a gateware bug**: the first transaction (0x48) never ended.  The I2C timeout added on the day (I2C_CTRL [21:19]) then showed SCL and SDA both 0 with the master idle, and the build logs had the cause: Vivado synthesized the block design's module reference out of context and "Converted tricell instance to logic" (Synth 8-5799, critical) on i2c_scl, i2c_sda and tx_q1, so the FPGA drove the I2C lines instead of releasing them; the Oct 11 2024.1 build has the same three warnings.  Fixed in build.tcl (global synthesis; a bitstream without IOBUFs on the three is refused) | |
| ADC: I, Q / VC / ERR | near V_MID / 1.65 V / - | pass (fixed overlay, 12:18): I 1.651, Q 1.625, VC 1.708, ERR 1.625 V; the scan finds the five, the DAC EEPROM defaults written to both MCP4728s | |
| detectors: V5_MON, TEMP | +5V_RF / 2; room | +5V_RF 4.976 V (the path's estimate 4.949 V); TEMP 48.3 C at 12:18, 56.7 C at 12:21 (TH501 is 12.6 mm from U104; the procedure's 15-45 C assumed a cold board) | |

**The 5 V path (board A, 0.871 A, the Fluke against J303's GND pin; `data/board_A/2026-10-29.jsonl`).**  Node voltages:
supply out1 - -0.071, + 5.077, F301 VBUS pad 4.990, F301 Q301 pad 4.941, TP301 4.862, TP302 4.823 V.

| section | drop | resistance |
|---|---|---|
| return: board GND to the supply's - (USB-C, cable, breakout, lead) | 71 mV | 82 mohm |
| supply + to VBUS at F301 (lead, breakout, cable, USB-C) | 87 mV | 100 mohm |
| F301, the 2 A PTC | 49 mV | 56 mohm |
| Q301 (AO3401A) and the +5V_IN copper to TP301, 40 mm away | 79 mV | 91 mohm |
| FB301 (220R, 2 A, 0805) and the vias, +5V_IN to +5V_RF | 39 mV | 44 mohm |

The board's part, 192 mohm, is 0.26 V at stage 2's 1.37 A against the 0.21 V budgeted; with this bench lead (181 mohm)
+5V_RF would sit at 4.74 V at 1.37 A even with 5.25 V at the supply.  For stage 2: a shorter, heavier USB lead, or the
supply at about 5.36 V (VBUS at the plug then 5.11 V).  REVB.md row 2.

## Stage 2: the synthesizers and the transmitter

| step | expected | A | B |
|---|---|---|---|
| 2.1 PLL_INIT, lock detect TX / RX | done, 1 / 1 | pass: done, 1 / 1 at 5.800 GHz.  The readback proven: each MUX pin forced low (0), high (1), three-state (1: pulled up, which is why both read 1 before PLL_INIT); asked for 7.0 GHz (N = 280) each reads 0, back at 5.8 GHz 1 | |
| current with both synthesizers running | toward 1.37 A with the TX on | 0.934 A, TX off (5.297 V): each MAX2871 97 mA (its SHDN bit: 0.934 -> 0.836 A); the rest of the board 0.74 A against the 0.89 A budgeted, so about 1.0 A with the TX on | |
| lock over the VCOs' range | every 25 MHz, 3000-6000 MHz | pass: TX 121/121, RX 121/121 locked (150 ms after each retune) | |
| lock time after a 25 MHz retune | | 59-63 ms (TX at 5800 MHz: 1 ms): VAS_TEMP = 1, which the datasheet puts at about 100 ms instead of 10/fBS = 200 us.  Fine for the link; the WiFi survey's hops want VAS_TEMP = 0 | |
| VC_OFF -> VC (loop held), RX lock | | VC = 3.347 - 0.993 VC_OFF (an inverting sum), linear 0.3-3.0 V; RX locked throughout (VC 0.37-3.05 V) | |
| offset trims -> the ADC's I, Q | PATHS.md: I_OFF_F +-66 mV differential | I_OFF_F -0.020 V/V on I, Q_OFF_F -0.020 V/V on Q and ERR (one side of each arm: as designed); I_OFF, Q_OFF, V_T2 act on the slow arms only | |
| the receive chain alive (no carrier, RX ANT open) | | LOG_Q 1.295 V at DSA 31.75 dB, 1.303 / 1.318 / 1.355 / 1.471 V at 24 / 16 / 8 / 0 dB: the floor rises with the gain, the front end's own noise at low attenuation | |
| 2.2 LO TX MON (J204): frequency, level, 25 MHz spurs | 5.800 GHz, -1 dBm +- 3, <= -60 dBc | **fail on level**: 5 799 994 333 Hz (-0.98 ppm against the DSA875's own timebase), locked, spurs at -25 / +25 / +50 MHz <= -66 dBc (the floor at 10 dB attenuation), but **-29.7 dBm**, -26.5 dBm after Jason reseated the U.FL (13:38): 25 dB low.  RFOUTB off: -36.7 dBm, so RFOUTB switches but by only 7 dB.  The line is the TX synthesizer's (it stays when the RX one moves to 5825 MHz).  Pigtail U.FL -> SMA -> N, analyser on USB.  **Why: the tap's track.**  Net-(J204-In), C231 to J204, 12.3 mm apart, is routed 115.6 mm round the board (`tools/detour_check.py`; RX's tap is 9.5 mm).  Swept with RFOUTB on (`sweep` entry, 13:43): -3.4 / -2.8 dBm at 3.0 / 3.5 GHz, -13.7 at 4.0, -16.7 at 5.0, -21.0 at 5.7, -26.7 at 5.8, -25.4 at 6.0, rippled: a long lossy mismatched line, not a dead output.  The monitor's frequency and spurs stand; its level is +25.7 dB at 5.8 GHz.  REVB row 4 | |
| LO RX MON (J109) | the same | **fail on level**: 5 799 894 000 Hz (-18.3 ppm on the analyser's timebase: the VCXO at VC 1.65 V), locked, spurs <= -77 dBc, **-8.7 dBm**, 7.7 dB low.  Its tap is 9.5 mm but through 2 vias.  Swept (14:03, `sweep` entry): -18 to -23 dBm at 3.0-3.4 GHz, -0.6 to -3.6 at 3.8-4.2, -7 to -10 at 4.6-6.0; not J204's shape (-3 dBm at 3.0-3.5 GHz, falling to -26.7 at 5.8) through the same pigtail.  Neither LO MON net is in the RF/LO net classes: RFOUTB's legs are the Default 0.15 mm with 2-4 vias each, the pull-ups at the ends of 2.5-16.8 mm branches (RFOUTA's, in the LO class: 1.0 mm).  A simple line model gives swings of this size but not their frequencies; the VNA on the unpowered jacks would settle it.  REVB row 4 | |
| the loop integrator, held | holds | **walks to a rail**: between 12:19 (VC = 3.347 - 0.993 VC_OFF: U112A at about 1.6 V) and 13:36, U112A reached its 3.28 V rail (VC = 3 V_MID - U112A - VC_OFF read 0.007-0.033 V for every VC_OFF >= 1.65): 0.36 mV/s or more, 36 pA or more into C130.  As PATHS.md says, a hold is for milliseconds.  `run loop_center` brings it back (ERR biased +19 / -25 mV with I_OFF_F, the hold opened by the sequencer for a counted time): 1.652 V in 3 steps.  The two rates (21.4 V/s up for +19 mV, 8.4 V/s down for -25 mV) imply RC about 1.5 ms (10 k x 100 nF = 1.0) and an integrator reference 13 mV under the ADC's 1.65 V: check at stage 3 | |
| isolation, RX LO into LO TX MON | | the RX LO at -65.4 dBm at J204 against the TX LO's -29.2 (RX 700 kHz away); below -93 dBm when the RX one is 25 MHz away | |
| VCXO pull (VC_OFF 0.3-3.0 V, loop held) | >= +-500 kHz; 430 kHz/V | pass (`run stage2.vcxo_ref`: REF OUT's frequency on the scope, edge times fitted over 100 us, 1 Hz repeatability): VC 0.29-2.97 V gives -115.8 to +94.6 ppm, the RX LO -672 to +549 kHz; 78.8 ppm/V = 457 kHz/V at 5.8 GHz; at VC 1.65 V, -13.8 ppm (board warm, NTC 58 C).  The RX LO's own leak onto LO TX MON (-65 dBm, at 5.8 GHz - 700 kHz before the integrator was centred: VC near 0 V) put the VCXO at the same offset on the analyser's timebase within 1 ppm | |
| REF OUT (J108) | 25 MHz, ~1.7 V p-p into 50 ohm | pass: 1.63 V p-p into the scope's 50 ohm (source 51 ohm: R 33 + the LVC1G17's own), edges 2.35 ns, duty 50.0 %; into 1 Mohm through the lead 3.40 V p-p, 4.2 ns edges (`data/board_A/ref_out_*.png`) | |
| 2.3 TX MON (J201), (1, 0) | -10 dBm +- 3 (+9.8 dBm at TX ANT) | **fail: -17.2 dBm**, 7 dB low (TX ANT into a 50 ohm termination; 14:39, and 14:42 after the null).  Either the chain gives about +3 dBm at TX ANT instead of +9.8, or the copper coupler couples about 26 dB instead of 20: TX ANT straight into the analyser tells which.  Supply 1.014 A with the TX on (0.948 off: the ADL5375 and the third ADL5611's share, 66 mA), +5V_RF 4.938 V (pass, >= 4.75) | |
| the four axis points | within 1 dB | pass after the null: -16.90 / -16.99 / -17.16 / -17.17 dBm (0.27 dB); before it 1.5 dB, the carrier's leak adding along Q | |
| (0, 0) before / after the null; VR_I, VR_Q at the null | 15-20 dB down / deeper; within a few mV of 0.2125 / 0.2456 V | 17.2 dB down before (pass); after `run stage2.null` (42 steps) -72.7 dBm, 55.3 dB under (1, 0), 53.5 dB in the repeat.  **At VR_I 0.2365, VR_Q 0.2986 V: +24 / +53 mV from the printed values** (fail on 'within a few mV': the ADL5375's own offsets, about 19 / 40 mV at IBBP / QBBP through the ladders' weights).  Kept as board A's calibration (`data/board_A/cal.json`); the DACs hold them until the next write, the EEPROM still the printed ones | |
| TX_DIS | mutes | pass: -62.0 dBm, 45 dB under (1, 0); 9 dB above the trimmed (0, 0): what leaks with the modulator disabled | |
| TX ANT (J202) straight into the analyser (10 cm RG-316, 0.5 dB allowed), (1, 0) | +9.8 dBm +- 3 | **fail: +3.8 dBm** at 5.8 GHz (`run stage2.tx_ant`, 15:07): the chain, not the coupler, which couples **20.95 dB** (TX MON -17.2 against TX ANT +3.8).  Axis flat (+3.8 to +4.1), (0, 0) -48.9 dBm, TX_DIS -39.6 dBm; 1.016 A, +5V_RF 4.936 V | |
| the TX output over 3-6 GHz, (1, 0) | | +15.2 dBm at 3.0-3.25 GHz, +13.0 at 4.0, +10.3 at 5.0, +9.1 at 5.5, +5.0 at 5.75, +3.8 at 5.8, +4.0 at 6.0 (`run stage2.tx_spurs`, 15:13): an 11 dB tilt; 5.8 GHz is on its slope.  The ADL5611 (14.3 dB at 5.8 GHz) then has about -10.5 dBm from the ADL5375 against the -4.5 planned: the modulator's output at 5.8 GHz, its LO drive (RFOUTA -1 dBm a side) or the ladder's swing, to find | |
| **+-25 MHz sidebands on the TX output** | <= -60 dBc (the reference's spurs) | **-36 / -39 dBc** at TX ANT, the lower stronger; none on LO TX MON (<= -66 dBc).  `run stage2.tx_spurs` (15:13): the same **absolute** level (-32 / -35 dBm) at (1, 0), (-1, 0), (0, 1) and at the nulled (0, 0), where the carrier is -50 dBm: added on the baseband, not riding on the carrier; gone with TX_DIS (-72 / -74); unchanged with the TX PFD at 5 MHz (no +-5 MHz spurs): not the synthesizer's reference spurs; +-75 MHz at -35 / -40 dBm and +-50 MHz at the floor: odd harmonics, a 25 MHz square wave; about -37 dBc from 3 to 6 GHz.  Not the VCXO (VC moved 0.1-1.1 V, the offset did not follow, 15:11).  Interleaved carrier / sideband readings (15:15): the offset is carrier / 232, the TCXO, within 0.45 +- 1 ppm.  So a few mV of the TCXO's 25 MHz reach IBBP / QBBP (TX_I / TX_Q: 2.2 k || 2.2 k || 300 ohm, about 245 ohm at 25 MHz, no capacitor at the pin; 0.04 pF from a 3.3 V edge is enough).  The reference's B.Cu run from JP201 to C222 passes 0.14 mm (plan) from TX_Q0 and 0.30 from TX_I1 on F.Cu.  Next: stage 2.4 at 25.002 MHz from the generator tells the TCXO's own copper from the REF_IN path | |
| 2.4 REF IN, 25 MHz 1 V p-p, JP201 to REF IN | the TX synthesizer locks | **pass**: locked from the SDG1032X at 24.990, 25.000, 25.002 and 25.010 MHz, 1 V p-p open-circuit (`run stage2.ref_in_tx`, 15:35; the 10 kHz offsets 15:36), the analyser on TX ANT.  The carrier follows (232 x; -1.15 ppm on the analyser's timebase), broadened by the generator's phase noise x 232 (-3 to -7 dBm in 30 Hz).  **The +-25 MHz sidebands follow the generator, not the TCXO**: 10 kHz off, -45 / -48 dBc at the generator's offset, nothing at the TCXO's (-58 to -65, the skirt): the coupling is in the reference's path to U203 (JP201.2 -> C222 -> REF_IN), 10 dB weaker for the generator's 1 V sine than the TCXO's 3.3 V (REVB row 5).  **And linear in the drive** (15:42, `ref_in_amplitude`): 0.75 / 1.0 / 1.4 / 2.0 / 2.8 V p-p at 25.010 MHz raise both sidebands by +2.3-2.8 / +5.2-5.9 / +8.5-9.1 / +11.5-12.5 dB against 20 log of the ratio's +2.5 / +5.4 / +8.5 / +11.4, and +-3f stays at the floor (-74 to -79 dBc): the trace's voltage coupling, not U203's reference buffer (which would square the sine and hold the level).  The TCXO's -36 / -39 dBc against 2.8 V p-p's -36 / -39: its 3.3 V CMOS fundamental (4.2 V p-p of sine at full swing, 3.4 at the datasheet's 90 %) within 2-3 dB.  JP201 back to TCXO after | |

## Stage 3: loopback (board A, the night of 2026-10-29)

The bench Jason left at 16:50: TX ANT -> 10 cm RG-316 -> two 20 dB pads (40.2 dB with the lead) -> RX ANT; the DSA875 on
RX MON (J102); the scope's ch1 REF OUT, ch2 I MON, ch3 Q MON, ch4 VC MON (1 Mohm; checked 16:12: `cabling_check`,
ch2 is I by I_OFF_F); 50 ohm on TX MON's pigtail; JP201 on TCXO.  `bringup/overnight.py` runs the sections; its files
are in `data/board_A/overnight/`, the plots in `data/board_A/plots/` (`plot_board.py`).  The DSA is never set below
the floor that keeps the ADL5380's input at 0 dBm or less (its maximum +15).

| step | expected | A | B |
|---|---|---|---|
| 3.1 RX MON against the DSA, 5.8 GHz (16:01) | -1 dB per dB; chain 38.9 dB (RX ANT to CP101) | **fail**: RX MON follows only under DSA ~9 dB (-45.8 dBm at 0 dB); above it a -55 dBm floor that does not follow (leakage, entering after the DSA).  The chain at 5.8 GHz: about 10 dB (RX MON + 20 - RX ANT's -36.4), **28-32 dB under plan** (`plots/rx_dsa_5800.png`) | |
| the receive chain over 3-6 GHz (map, every 50 MHz, 16:17-16:30) | flat-ish, the LNA's band 4.9-5.9 GHz | **the gain falls off above 4.5 GHz**: 37-44 dB from 3.0 to 4.4 GHz (the plan's 38.9), 30 dB at 5.0, 20 at 5.35, 7 at 5.7-5.8, -3 at 5.9, 13 at 6.0 (those two are not the chain: the fine map below); RX MON's slope against the DSA near 1 up to 5.2 GHz, 0.45-0.8 at 5.5-5.8, about 0 at 5.9 (`plots/night_rx_chain.png`, `night_iq_heat.png`).  Not a dead or disabled LNA (that would be flat: -15 to -25 dB disabled, Table 4): a roll-off of about 35 dB over 1.3 GHz, right across the band the LNA is matched for.  The demodulator after it is fine (below).  REVB row 8 | |
| the fine map, 5.3-6.0 GHz every 10 MHz (17:32-18:00, `overnight.py mapfine`) | the shape of the dip | **The chain is a roll-off, not a notch.**  The part of RX MON that follows the DSA falls smoothly: chain gain 22.5 dB at 5.3 GHz, 15.5 at 5.5, 6.8 at 5.7, 7.3 at 5.8, about 4 at 5.85.  Above 5.86 GHz neither RX MON nor the demodulator's I/Q follows the DSA at all (5.94 GHz: -48.0 to -47.8 dBm, I 0.113 V p-p, at every setting from 0 to 31.75 dB): a signal at the TX frequency that enters after the DSA and upstream of CP101 (RX MON and I/Q rise together), -51 dBm at RX MON at 5.9 GHz, -46 at 6.0; the same leak sits at -53 dBm at 5.0-5.5 GHz (the DSA's range there is 23 dB) and under -75 at 5.7.  The minimum at 5.88-5.89 GHz (-64.9 dBm at DSA 0) is the chain and the leak cancelling: at DSA 8 it is at 5.85 GHz and 5 dB shallower.  With TX_DIS the level at 5.9-6.0 GHz drops 10-19 dB (to -61..-65 dBm).  REVB row 10 | |
| the layout, read from the board file (19:00, `layout/layout_survey.py`, `layout/draw_region.py`) | 50 ohm CPWG, a fenced ground | **The lines are as designed; the parts on them are not where the reference puts them.**  Every RX line: 0.29 mm (0.25 / 0.20 at necks and branches), the gap to the pour 0.25 mm all along, In1 ground under 100 % (76-88 % only over the SMA's and the ADL5611 pads' designed voids), fence vias 0.6-1.9 per mm.  At the LNA: C102 (0.5 pF) 4.0 mm of track from RF_IN on a 1.8 mm branch; VCC 1.6 mm to L102, C103 2.3 mm beyond; one via in the exposed pad.  At the gain blocks: L103 / L104 to a +5V_RF via 0.8 mm off, no capacitor within 9.8 mm.  The stitching: 43 % of the top pour round the chain more than 2.5 mm from a ground via (max 8.6 mm; 20.7 mm elsewhere on the board).  A model of the input network as laid out (`layout/lna_input_model.py`) gives the LNA stage's roll-off: `plots/rx_lna_stage_model.png`.  REVB rows 8 and 10 | |
| the demodulator's I/Q balance (iq, every 100 MHz, 16:31-16:35) | | Q / I within -0.18 / +0.24 dB from 3 to 6 GHz; quadrature error +3.2 degrees at 3 GHz falling smoothly to -1.6 at 6 GHz, 0 at 5.35 (`plots/night_iq_balance.png`): sine fits to the beat on I MON / Q MON, the DSA set for 0.4 V p-p | |
| 3.3 the loop, 5.0 GHz, DSA 20 dB (16:4x) | locks; Q MON to zero, I MON steady | **locks, 90 degrees round**: released at zero beat it holds VC at 1.861 V while VC_OFF steps -0.05 / -0.10 V (U112A takes each up), I and Q static, but Q at its maximum (+0.13 V) and I at its comparator's threshold: the sign(I) x Q loop's other stable point, its sign inverted.  BRINGUP 3.3's remedy: both sign jumpers (JP101, JP102) to their other positions, by hand.  A false lock 60 kHz off (VC 1.719 V, I and Q at their offsets with the beat averaged away) after a +0.05 V step; lost at DSA 26 dB.  The board's ADC cannot tell lock from beat: the ADS1115 averages a kHz beat to its mean; only the scope can | |
| 3.3b the loop at 5.0 GHz: the inverted Costas lock against a plain PLL on Q made by the I trim (`linktests.py force`, `lockcmp`, 20:00-20:40) | a plain PLL locks cleanly | **The trim cannot make the plain PLL; the inverted lock works at the regulated level.**  An extreme I_OFF_F holds CMP_I only against a weak carrier: 0.3 or 0 V at DSA 31.75 (duty 1.000); at DSA 20 no trim does (duty 0.50-0.66, 5-7 k edges in 10 ms on a 5 kHz beat), and 3.0-3.3 V never does (duty 0.44-0.51: the trim reaches one way only).  Forced high at DSA 31.75 the loop does not lock: the integrator rails, ERR carrying the Q leg's ~25 mV offset against a ~20 mV carrier.  (Forced low, which REVB 9's cause says locks at 0 degrees, the trim cannot reach: JP103 to FPGA and LOOP_SEL are the way.)  The inverted lock: DSA 20 (regulated) locks from 8 of 10 starts (-5 to +40 kHz), DSA 18 4/10, DSA 24 3/10, DSA 28 none; always at VC 1.860 with the idle on +Q or -Q, and it flips between the two under a +-0.02 V VC_OFF step.  Hold-in under 20 kHz (a +0.05 V step unlocks it).  LOOP_HOLD holds (VC follows VC_OFF exactly) | |
| 3.4-3.5 the schemes through the loop, 5.0 GHz, DSA 20 (`linktests.py schemes`, 20:50-21:15) | every scheme decoded; latency 23.5 ns of electronics plus the decoder | **The board's (I, Q) is the TX point mirrored (I to -I) and turned +-90 degrees**: A3r's confusion matrix is diagonal only with the mirror (4000 of 4000 against 0), Response 10's inverted I arm (REVB 9).  With the decisions on the four windows (sign(I) chatters at this lock), from the TX event (the ladder pins' register) to the decision, 20 000 events each: the BPSK flip (A1q, on QP / QN) 20 000 decided, none false or missed, 67.5-73.8 ns (mean 70.9); OOK 20 000, 72.5-77.5 (74.0); the Q step (A2r) 19 990, 66.2-158.8 (72.1); **the plan's QPSK corners (A3r, two bits, four non-idle states) 19 300 decided, every one right** (one corner sat near its Q threshold: 4322 of 5000), 67.5-128.8 ns (71.0).  First-edge decisions: A2r 19 999 (72.1 ns); A3r 938, by design (a corner's first window is shared by two messages).  At DSA 18 and 22: 1-3 % false or missed and a tail to 1 us.  Not possible at this lock: A1 and the PRBS BER (both read sign(I)), and B1 / B2 / A4 (the pilot is 14 dB under the idle, where the loop does not lock).  The held-loop BER read random (0.13-0.17 at 1-100 Mbaud: the held integrator walks the phase a radian in ~50 ms).  FSK (TX_MODE 4, the axis points in turn at 1-12.5 MHz): the windows fire in rotation order, one sense cleanly at 2.5 and 12.5 MHz (QP, IN, QN, IP), the other mixed; the sense wants a decoder of its own.  `plots/link_constellations_5000.png`, `plots/link_latency_5000.png` | |
| 3.3c the loop at 5.15 and 5.2 GHz (`lockcmp`, 20:14-20:31), inside the lab grids' 5.15-5.85 GHz | | **More robust than at 5.0 GHz.**  5.2 GHz, the regulated DSA 10: locks from 5 of 8 starts (-5, -2, +5, +10, +20 kHz; the +2 kHz starts read 'false' only because the held beat was too slow to measure), at DSA 8-14 the same, at 6 one; 5.15 GHz the same at DSA 10.5-16.5.  `plots/link_lock_map.png` | |
| 3.4b the schemes at 5.2 GHz, DSA 10 (`schemes`, 20:20-20:33) | | A1q 20 000 of 20 000, 68.8-73.8 ns (70.5); OOK 20 000, 71.2-78.8 (73.0); A2r 20 000, 67.5-87.5 (71.5); A3r 18 393, all right (one corner 3394 of 5000), 67.5-88.8 (70.5); none false or missed.  DSA 12: 1-2 % missed.  DSA 8: no lock in the run (the lock map's edge).  `plots/link_constellations_5200.png`, `plots/link_latency_5200.png` | |
| 3.4c A3r with the fast I arm nulled (`tune_a3`, 20:38-20:41) | | **The plan's two-bit scheme decoded completely.**  I_OFF_F to CMP_I's 50 % with no carrier (2.97 V at 5.0 GHz, 2.75 V at 5.2: REVB 15) puts the lock exactly on +-Q (dI 0.000 against -0.026).  Windows at 0.35 a, the decision 16 samples (2 clocks) after the first window: **20 000 of 20 000 right, none false or missed, 66.2-75.0 ns (mean 70.0) at 5.0 GHz, 66.2-76.2 (69.6) at 5.2**; at 0.45 a the same; at 0.55 a 98.8-99.6 %.  Each 8 samples more of decision delay costs 10 ns and buys nothing at 0.35-0.45 a.  `plots/link_a3r_tuning.png` | |
| 3.4d the pilot schemes B1, B2, A4 (`pilot`, 20:41-20:45) | | The pilot from VR_I / VR_Q (+0.097 / +0.051 V for 0.2 a; +0.141 / +0.105 V for 0.3 a), the loop locked on it with the DSA lowered by its level (5.0 GHz, DSA 6-8).  Every decision right, but **every message with +1 on the pilot's axis partly undecided**: B1 12 840 / 13 408 of 20 000, B2 17 058 / 13 872, A4 19 913 / 13 708 (rho 0.2 / 0.3; the -1 messages all decided), 64-74 ns.  Raising the references to make the pilot pushes the +a ladder points into the modulator's headroom (REVB 1, 15).  At 5.2 GHz the pilot lock failed (B1 1.6 M false events; B2, A4 no lock) | |
| 3.4e LO drive, TX (`linktests.py lodrive`, test D of `sim/aslaid/REPORT.md`, 20:47-20:50) | the TX level follows the TX synthesizer's RFOUTA power | **Flat: the ADL5375's LO port is saturated from -4 dBm a side.**  APWR -4 / -1 / +2 / +5 dBm, the (1, 0) carrier at RX MON through the loopback (DSA fixed, the RX synthesizer parked 200 MHz below): 5.0 GHz -28.5 dBm at every setting (within 0.05 dB), 5.2 GHz -30.3 / -30.4, 5.8 GHz -55.4 / -55.0 / -54.4 / -53.8 (+1.6 dB, part of it the rising LO feedthrough adding to a weak carrier).  The +-25 MHz sidebands do not move (-65 / -67 dBm at 5.0 GHz: not the LO).  What rises with APWR is leakage: the nulled carrier at 5.8 GHz -70.1 to -62.0 dBm, the TX_DIS level -69.8 to -62.2.  The writes land (`apwr_check`, 20:51): the board's current 0.9301 / 0.9364 / 0.9448 / 0.9572 A at -4 / -1 / +2 / +5 dBm, the same for either synthesizer (27 mA over the range), and the TX LO's own leak at RX MON 5.5 dB up.  The TX's 6 dB shortfall (REVB 6) is not its LO drive | |
| 3.4f LO drive, RX (`lodrive`, test E, 20:50-20:51) | the I/Q beat follows the RX synthesizer's RFOUTA power | **Flat: the ADL5380's LO port is saturated too.**  The loop held, VC 0.08 V under the lock (a 34-39 kHz beat), sine fits on I MON / Q MON: 5.0 GHz I 0.1616-0.1621 V, 5.2 GHz 0.1519-0.1524 V, 5.8 GHz 0.0481-0.0483 V across APWR -4 to +5 dBm (under 0.05 dB), Q the same.  The as-laid model's -2.4 dBm at the ADL5380's LO pins (finding 6) costs nothing; APWR -4 saves 6 mA a synthesizer and some leakage for 0 dB here (`plots/link_lo_drive.png`; `link/lodrive_20261029_205057.json`, `apwr_check_20261029_205143.json`) | |
| 3.4g the reply overlay deployed (21:48-21:51) | ID version 3, the turnaround paths | `bringup/deploy_pynq.sh` with OVERLAY pointed at the gateware agent's 2024.1 build of master a173ec9 (bit `2e4eda7d...`, hwh `031d6acf...`; WNS +0.073 ns, WHS +0.031; the I2C pins IBUF + OBUFT), the driver from master; a PC copy in `build/pynq/overlay_2024.1_turnaround/`.  The 2022.1 overlay and driver it replaced are kept on the PYNQ in `~/costaslink_backup_20261029_2150_pdt/` (`a416f915...` / `fa0175a7...`).  The server restarted by hand (sudo nohup `pynq_serve.sh`, PYNQ 3.0.1 loads the 2024.1 hwh): ID 0x434C0003, BUILD 0x00647108 (100 MHz, 8 samples a clock, fast path, TX read-back); all five I2C parts answer, the DACs read back, both ADS1115s read, both PLLs lock (STATUS 0x3), 0.949 A | |
| 3.4h the turnaround in single-board loopback (`linktests.py turn`, 5.0 GHz DSA 20 at 21:54-21:58, 5.2 GHz DSA 10 at 22:00; `scope_turn` 22:01) | PLAN.md section 19: fast path ~26-33 ns RX ANT to TX ANT, synchronous reply ~52-68 | **Fast path 23-25 ns, synchronous reply 52-60 ns.**  The board's TX event is the stimulus; the counter (turnaround.v) times the window comparators' arrival of the stimulus's echo to the answer's: RX ANT to TX ANT plus about 1 ns of lead and pads.  A2r (1 bit) is clean (5000 of 5000 each, 0 missed): fast path 21.25 / 23.4-23.7 / 26.25 ns (min / mean / max); the synchronous reply 52.5-53.75 / 60.0-60.3 / 63.75 ns at a 4-sample settled decision, 57.5 / 61.8 / 68.75 at 8, 67.5 / 71.9 / 78.75 at 16 (each 8 samples of decision delay is 10 ns), and 47.5 / 51.9 / 58.75 ns with a first-edge decision (5.2 GHz).  The ring (the fast path with a permutation of the states, no fixed point) gives the precise figure: A3r's four states in Gray order 23.54 ns a hop over 502 hops (5.0 GHz) and 24.30 over 822 (5.2); the flip-and-null pair A1q2 24.04-25.35 over 787-830.  The captures (1.25 ns, the ladder pads read back) split it: the FPGA pad to pad 5.0-6.25 ns on the fast path (Vivado: 2.7-13.1), 31.25 ns on the synchronous first-edge reply and 40-42.5 at a 4-sample delay; the analog loop (ladder pads to the comparators, through the modulator, the lead, 40 dB and the receive chain) 16.25-21.25 ns.  Caveats (gateware/README.md): the TX events are on the clock grid, so the synchronous reply is seen at one phase of its 10 ns spread; the one-shot figures are quantised to 1.25 ns; A3r's and A1q2's counter statistics carry outliers (10-11 ns and ~200 ns: stray window edges), so their figures are the captures' and the rings'.  CMP_I is left out of every count (mask 0x1E): at the inverted lock it sits on its threshold and chatters, and the first pass (`turn_5000_20261029_215447.json`) counted its edges as arrivals.  The scope (`link/scope_turn_5200_20261029_220145.png`): I MON rises with the stimulus and turns about 50 ns later with the answer.  Rings of A2r stall (its hop passes through the idle's vector).  `plots/link_turnaround.png` | |
