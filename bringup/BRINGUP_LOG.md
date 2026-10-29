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
| LO RX MON (J109) | the same | | |
| the loop integrator, held | holds | **walks to a rail**: between 12:19 (VC = 3.347 - 0.993 VC_OFF: U112A at about 1.6 V) and 13:36, U112A reached its 3.28 V rail (VC = 3 V_MID - U112A - VC_OFF read 0.007-0.033 V for every VC_OFF >= 1.65): 0.36 mV/s or more, 36 pA or more into C130.  As PATHS.md says, a hold is for milliseconds.  `run loop_center` brings it back (ERR biased +19 / -25 mV with I_OFF_F, the hold opened by the sequencer for a counted time): 1.652 V in 3 steps.  The two rates (21.4 V/s up for +19 mV, 8.4 V/s down for -25 mV) imply RC about 1.5 ms (10 k x 100 nF = 1.0) and an integrator reference 13 mV under the ADC's 1.65 V: check at stage 3 | |
| isolation, RX LO into LO TX MON | | the RX LO at -65.4 dBm at J204 against the TX LO's -29.2 (RX 700 kHz away); below -93 dBm when the RX one is 25 MHz away | |
| VCXO pull (VC_OFF 0.3-3.0 V, loop held) | >= +-500 kHz; 430 kHz/V | pass (`run stage2.vcxo_ref`: REF OUT's frequency on the scope, edge times fitted over 100 us, 1 Hz repeatability): VC 0.29-2.97 V gives -115.8 to +94.6 ppm, the RX LO -672 to +549 kHz; 78.8 ppm/V = 457 kHz/V at 5.8 GHz; at VC 1.65 V, -13.8 ppm (board warm, NTC 58 C).  The RX LO's own leak onto LO TX MON (-65 dBm, at 5.8 GHz - 700 kHz before the integrator was centred: VC near 0 V) put the VCXO at the same offset on the analyser's timebase within 1 ppm | |
| REF OUT (J108) | 25 MHz, ~1.7 V p-p into 50 ohm | pass: 1.63 V p-p into the scope's 50 ohm (source 51 ohm: R 33 + the LVC1G17's own), edges 2.35 ns, duty 50.0 %; into 1 Mohm through the lead 3.40 V p-p, 4.2 ns edges (`data/board_A/ref_out_*.png`) | |
| 2.3 TX MON (J201), (1, 0) | -10 dBm +- 3 (+9.8 dBm at TX ANT) | | |
| the four axis points | within 1 dB | | |
| (0, 0) before / after the null; VR_I, VR_Q at the null | 15-20 dB down / deeper; within a few mV of 0.2125 / 0.2456 V | | |
| TX_DIS | mutes | | |
| 2.4 REF IN, 25 MHz 1 V p-p, JP201 to REF IN | the TX synthesizer locks | | |
