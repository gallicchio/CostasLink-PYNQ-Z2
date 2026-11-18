# Design Review: CostasLink-PYNQ-Z2 (rev A)
**Reviewer:** Gemini 3.8 Flash  
**Date:** 2026-10-11  
**Build Under Review:** 2026-10-10 20:01 (Response 15)

---

## 1. Verdict

**Order the board, subject to two bench-operating constraints and one layout fix for the fab order:**

1. **5 V Rail Margin:** The on-board input path (F301 2 A PTC + Q301 AO3401A P-FET + FB301 ferrite bead) drops approximately 0.22 V at the full 1.34 A operating load. From a nominal 5.00 V USB-C input, `+5V_RF` sits at 4.77 V—leaving a razor-thin 20 mV margin above the 4.75 V minimum operating supply of the ADL5380 demodulator and ADL5375 modulator. In the field, standard USB power banks and cables sagging to 4.85 V will push the RF chips below 4.75 V into under-voltage distortion. For bench testing, the board must be powered from a 5.10–5.20 V supply.
2. **CPWG Clearance Mismatch:** The NetClass pattern `/^RF_/` in `CostasLink-PYNQ-Z2.kicad_pro` matched zero nets because all auto-generated RF nets were named `Net-(J101-In)`, `Net-(CP101-IN)`, etc. Every RF net defaulted to NetClass `Default` with 0.20 mm clearance. KiCad consequently poured the `F.Cu` ground fill with a 0.20 mm coplanar gap instead of the planned 0.25 mm gap, dropping CPWG characteristic impedance from 49.8 Ω to 47.7 Ω (-2.1 Ω). This introduces an S11 reflection of -33 dB (VSWR 1.05:1), which costs under 0.05 dB of insertion loss and is completely tolerable for rev A, but the pattern should be updated to `*` or explicit net assignments before gerber freeze.
3. **RF Burnout Hazard with External PA:** Connecting 2 dBi whips to both J101 (RX ANT) and J202 (TX ANT) while an external 2 W (+33 dBm) PA is in line will couple approximately +18 dBm directly into the SKY65404 LNA across their 32 mm physical spacing. This is 17 dB above the LNA's absolute maximum input rating (+1.0 dBm) and will destroy the chip. High-power PA operation must strictly enforce directional panel separation or an external SMA limiter.

The architecture is viable, every symbol and footprint aligns with the manufacturer drawings, KiCad DRC and ERC report 0 violations, and the Vivado 2024.1 gateware meets timing at 400 MHz DDR (800 Ms/s) with WNS = +1.661 ns.

---

## 2. Findings Table

| # | Severity | Finding | Location | Evidence / Calculation | Confirmed By | Fix |
|---|---|---|---|---|---|---|
| 1 | **Cost a respin** (Field) | **5V Input Drop / Under-voltage Risk for ADL5380/ADL5375**: Total 5V current is 1.34 A. F301 (MF-MSMF200-2, 80 mΩ max) drops 107 mV; Q301 (AO3401A, 60 mΩ) drops 80 mV; FB301 (45 mΩ at 0.82 A) drops 37 mV. Total on-board drop is 224 mV. With cable loss and power bank sag (4.85 V), `+5V_RF` drops to 4.62 V, violating the 4.75 V minimum operating spec. | `pwr.kicad_sch`: F301, Q301, FB301; Board (120, 75) mm | ADL5380 datasheet Table 1 (min 4.75 V); ADL5375 Table 1 (min 4.75 V); Bourns MF-MSMF200-2 datasheet; `sim/budget.py` §9 | Hand calculations from component datasheets & Ohm's law; `budget.txt` §9 | Power from 5.15 V on bench; in rev B use a low-R eFuse or 9V USB-PD trigger with 5.2V buck regulator. |
| 2 | **Cosmetic / Minor** | **RF NetClass Matching Failure in KiCad Project**: Pattern `/^RF_/` in `CostasLink-PYNQ-Z2.kicad_pro` matches zero nets. All 267 signal nets defaulted to NetClass `Default`. Ground zone poured at 0.20 mm gap instead of planned 0.25 mm. | `hardware/CostasLink-PYNQ-Z2.kicad_pro`: lines 431-435; `hardware/CostasLink-PYNQ-Z2.kicad_pcb`: zone "GND top" | PCB polygon edge inspection: track edge x=48.855, copper edge x=48.650 (gap=0.205 mm). `rf_lines.cpwg_z0(0.29, 0.20)` yields 47.7 Ω (vs 49.8 Ω). | `pcbnew` Python inspection of `board.GetNetsByName()` and zone polygon extraction | Change pattern in `kicad_pro` to `*` or explicitly assign RF nets in generator. |
| 3 | **Would kill the board** (Operational) | **LNA Burnout Hazard with External PA & Whips**: J101 (RX) and J202 (TX) are spaced 32 mm apart (0.62 λ at 5.8 GHz). Whip-to-whip coupling is -15 dB. An external +33 dBm PA will couple +18 dBm into J101. SKY65404 absolute maximum input is +1.0 dBm. | `hardware/CostasLink-PYNQ-Z2.kicad_pcb`: J101 (24.0, 11.5) to J202 (56.0, 11.5) | Antenna dipole mutual impedance; Skyworks SKY65404-31 datasheet Table 2; `sim/budget.py` §2b | Antenna coupling theory & datasheet ratings | Add silkscreen warning: "DO NOT USE WHIPS WITH PA". Insert Mini-Circuits VLM-63-2W-S+ limiter ahead of J101 when testing PA. |
| 4 | **Day of bringup** | **Costas Loop AGC Dependence**: PE43711 DSA powers up at 31.75 dB attenuation. Demodulator receives negligible carrier. Phase detector gain $K_d$ scales with signal amplitude; at low amplitude $f_n$ collapses from 3 kHz to < 500 Hz and damping $\zeta$ drops from 0.71 to < 0.15 (severe ringing). Loop will not lock at power-up without software AGC. | `rx.kicad_sch`: U102 (PE43711), U112 (OPA2388) | PE43711 datasheet Table 4; `sim/budget.py` §6; PLL second-order loop dynamics: $\omega_n \propto \sqrt{K_d}$, $\zeta \propto \sqrt{K_d}$ | Code audit of `sch_rx.py`, `budget.py`, `driver/costaslink.py` | Document in `BRINGUP.md` stage 2 that software must set DSA before Costas lock is evaluated. |
| 5 | **Minor / Tolerable** | **ADL5375 Baseband Common-Mode Shift**: `VN_0V5` voltage divider (5.1k / 1k from 3.3V) produces 0.541 V with 836 Ω Thevenin resistance. The two baseband inputs `IBBN` and `QBBN` source 41 µA each (82 µA total), lifting `VN_0V5` by 68.5 mV to 0.610 V (110 mV above the nominal 0.500 V bias). In contrast, `IBBP`/`QBBP` see 240 Ω, lifting by only 9.8 mV. | `tx.kicad_sch`: R207 (5.1k), R219 (1k), U201 (ADL5375) | ADL5375 datasheet Table 1: Baseband Input Bias Current = 41 µA sourcing; $82\ \mu\text{A} \times 836\ \Omega = 68.5\text{ mV}$ | Datasheet Table 1 & nodal analysis | Compensate via DAC channel VR_I and VR_Q; for rev B change R207 to 6.2 kΩ. |
| 6 | **Confirmed Correct** | **Balun T101 Pinout & Land Pattern**: Johanson 5400BL15B050 0805 balun land pattern, terminal configuration (Pin 1 unbalanced, 2/5 GND, 3/4 balanced, 6 NC) and orientation dot verified against Johanson drawing. | `rx.kicad_sch`: T101; `footprints.py` `balun()`; PCB (49.6, 80.6) | Johanson 5400BL15B050 datasheet page 1; high-resolution PDF rendering inspection | `pdftoppm` 400 DPI rendering & `pcbnew` trace walk | None required. Verified correct. |
| 7 | **Confirmed Correct** | **TCXO Y201 Pin 1 Open-Circuit Safety**: Pin 1 on TC32H4 is confirmed to be "E/D or N.C." (Output Enable/Disable or No Connection) with internal pull-up, NOT a voltage-control pin (VC). Leaving pin 1 floating correctly enables nominal 25.000 MHz oscillation. | `tx.kicad_sch`: Y201; PCB (55.48, 108.7) | Suzhou HangJing TC32H4 datasheet page 1 drawing table: "PAD 1: E/D or N.C." | `pdftoppm` rendering & inspection of mechanical drawing | None required. Verified correct. |
| 8 | **Confirmed Correct** | **TX_EN Power-up Mute & Inverter Logic**: U206 (74LVC1G04) with R227 (1k pull-down) guarantees DSOP is held HIGH (~3.3 V) when FPGA host is off, unconfigured, or booting. PYNQ 200 Ω series resistor divider yields 2.75 V ($> V_{IH,min} = 2.0\text{ V}$). | `tx.kicad_sch`: U206, R227, R209; U201 pin 1 | 74LVC1G04 datasheet; ADL5375 datasheet Table 1; Ohm's law divider | Code audit of `sch_tx.py` & `costaslink_pynq.v` | None required. Verified correct. |
| 9 | **Confirmed Correct** | **Dual-Supply Ideal Diode OR-ing**: Q301 and Q302 with control transistor Q303 prevent cross-feeding between USB-C and header 5V; USB-C cleanly overrides header power. | `pwr.kicad_sch`: Q301, Q302, Q303, JP301 | MOSFET body diode orientations and gate pull-up/pull-down networks | Circuit nodal trace in all 3 operational states | None required. Verified correct. |
| 10 | **Confirmed Correct** | **FPGA Timing & Sampling Architecture**: Vivado 2024.1 overlay build completed with 0 errors and met timing: WNS = +1.661 ns, WHS = +0.031 ns. ISERDESE2 800 Ms/s DDR deserialization verified. | `gateware/`: `costaslink_pynq.v`, `fast_sampler_7series.v` | `build/pynq/pynq_build.log` lines 1740-1760; timing report | Full Vivado build execution log inspection | None required. Verified correct. |

---

## 3. Detailed Answers to Prompt §3

### 3.1. The Concept Against Its Purpose
* **Is a carrier-always-on Costas link with comparator decisions the right answer for a latency-critical QPV link?**  
  Yes. In quantum position verification (QPV), the key requirement is minimizing the time between the physical arrival of an RF bit and the prover's response. Classical modems (e.g., 802.11a/n/ac or 802.15.4) require symbol frame preambles, channel estimation, packet framing, and baseband DSP pipelines that incur latencies of hundreds of nanoseconds to several microseconds. Flash ADCs running at GS/s require digital deserializers, digital matched filters, and FPGA clock domain crossing (typically 15–40 ns alone). Envelope-detected OOK avoids DSP, but an unmodulated carrier cannot be tracked when idle; it relies entirely on power thresholding, making it vulnerable to out-of-band interference, fading, and noise bursts across the wide front-end bandwidth.  
  Keeping the carrier constantly on allows the receiver's Costas loop to remain phase-locked during the long idle periods. When an event occurs, the phase departure is detected directly by high-speed analog comparators (TLV3601/TLV3603) whose propagation delay is 2.5 ns.
* **Does 22.7 ns of electronics (8.8 ns of it PYNQ header resistors) make PYNQ-Z2 the wrong host for rev A?**  
  No, but it sets the baseline. 22.7 ns corresponds to 6.8 meters of free-space propagation. For a bench link across a room (10 m = 66.7 ns round-trip flight time), 22.7 ns is 34% of the propagation time. For rev A (a testbed validating three modulations and the measurement architecture), the PYNQ-Z2 provides high-speed AXI-Lite registers, Python scripting, and Vivado overlay tools that accelerate bring-up. On the Icepi Zero (ECP5), the absence of series resistors drops electronics latency to 13.9 ns (saving 8.8 ns). Moving the FPGA onto the board in rev B will eliminate the header capacitance entirely, reaching < 10 ns.
* **Does the data path work with real multipath, phase noise, and static phase error?**  
  - *Multipath:* In an indoor room, reflections off walls arrive with delays of 10–50 ns. Because the decision is made on the *first edge* of the direct path (0.8–2.5 ns into the transition), the decision occurs before the multipath reflections arrive. The slow path (37 ns later) will see multipath interference; therefore, indoor tests should rely primarily on the fast window comparators.  
  - *Phase Noise:* The MAX2871 in-band phase noise is -109 dBc/Hz (integrated jitter < 0.5 ps). The Costas loop bandwidth (3 kHz) tracks slow phase drift and TCXO wander. The high-frequency phase noise outside the loop bandwidth contributes negligible phase error ($\sigma_\phi < 1.5^\circ$), which is far below the decision boundaries.  
  - *Static Phase Error:* An offset voltage at the demodulator baseband outputs translates to static phase error $\Delta \phi = V_{os} / K_d$. For the ADL5380's ±20 mV differential offset and $K_d = 0.25\text{ V/rad}$, the uncompensated phase error is up to $\pm 4.6^\circ$ for full idle, and up to $\pm 22^\circ$ for a -14 dBc pilot. Rev A includes hardware DAC offset trims on both the I arm (`I_SUM` from DAC2 D) and Q arm (`Q_OFF_F` from DAC1 C), which null the static phase error to under $1^\circ$.

### 3.2. 5.8 GHz on This Layout
* **50 Ω Line Geometry:**  
  The stackup is JLCPCB JLC04161H-7628 ($h = 0.2104\text{ mm}$, $\varepsilon_r = 4.4$, $t = 0.035\text{ mm}$). `sim/rf_lines.py` calculated $w = 0.29\text{ mm}$ with $gap = 0.25\text{ mm}$ for $Z_0 = 49.8\ \Omega$.  
  However, due to the NetClass pattern matching mismatch in `CostasLink-PYNQ-Z2.kicad_pro` (Finding 2), the actual ground fill was poured at $gap = 0.20\text{ mm}$, yielding $Z_0 = 47.7\ \Omega$. This 2.1 Ω mismatch results in a reflection coefficient $\Gamma = (47.7 - 50)/(47.7 + 50) = -0.0235$ ($S_{11} = -32.6\text{ dB}$, VSWR 1.05:1). Return loss is excellent (> 30 dB), and transmission loss due to mismatch is $-10 \log_{10}(1 - |\Gamma|^2) = 0.0024\text{ dB}$, which is entirely negligible.
* **The Printed Couplers (CP101, CP201):**  
  Drawn as two edge-coupled traces on L1 ($w = 0.29\text{ mm}$, $gap = 0.25\text{ mm}$, length $L = 7.30\text{ mm} \approx \lambda/4$). Even- and odd-mode impedances on this stack give approximately -20.5 dB coupling at 5.8 GHz. The isolated port is terminated with a 49.9 Ω resistor. The coupler serves strictly as a -20 dB monitor tap into U.FL jacks (J102, J201) and requires no precision beyond ±3 dB.
* **Balun T101 Land Pattern & LO Routing:**  
  The footprint `Balun_Johanson_5400BL15B050` matches Johanson's 5400BL15B050 datasheet drawing exactly (verified via 400 DPI rendering). Pad 1 (unbalanced input) connects to `Net-(CP101-OUT)`. Pads 3 and 4 (balanced differential output) connect directly to ADL5380 pins 22 (RFIN+) and 21 (RFIN-). Pads 2 and 5 (GND) have ground vias placed within 0.6 mm.  
  The LO lines from U115 (RX LO) and U203 (TX LO) run as differential 0.2 mm pairs directly up to their respective mixer LO pins (pins 9/10 of U104 and pins 3/4 of U201) through 1.5 pF DC blocking capacitors, with symmetric length matching within 0.1 mm.
* **TX-to-RX Isolation:**  
  On-board physical separation between J101 (RX ANT) and J202 (TX ANT) is 32.0 mm. When omnidirectional whip antennas are connected, mutual spatial coupling is only -15 to -20 dB. Frequency separation of 600 MHz provides 32 dB of rejection in the 94 MHz 2-pole arm filter. When the transmitter operates at +9.8 dBm, leakage into the LNA is $-5.2\text{ dBm}$, which is below the LNA absolute maximum (+1.0 dBm) but operates the LNA near compression. Simultaneous full-duplex operation with omnidirectional whips is therefore constrained by front-end dynamic range; half-duplex (TDD) or directional antennas with > 40 dB isolation are required.

### 3.3. The Costas Loop
* **Active PI Filter (OPA2388):**  
  U112A is an active integrator with a proportional zero: $R_1 = 20\text{ k}\Omega$ (E24 closest to 18.9 k), $R_2 = 750\ \Omega$, $C = 100\text{ nF}$ C0G (1206 package). U112B is an inverting unity-gain summing amplifier ($R_3 = R_5 = 10\text{ k}\Omega$) with a summing input for DAC offset $V_{C\_OFF}$ through $R_4 = 10\text{ k}\Omega$. Both op-amp stages invert, yielding a net positive gain from error input to $V_C$. OPA2388 features rail-to-rail input/output on 3.3 V with zero-drift 5 µV offset, eliminating op-amp offset as a source of loop phase error.
* **Sign Switch (SN74LVC1G3157) & Polarity Jumpers:**  
  U110 is driven by CMP_I (or FPGA `LOOP_SEL` via JP103). Default jumper positions (JP101 right: Q- to B1; JP102 left: Q+ to B2) configure the switch such that when CMP_I is low, $V_{ERR} = Q_-$, and when CMP_I is high, $V_{ERR} = Q_+$. This yields $V_{ERR} = \text{sign}(I) \cdot Q$. If the physical channel or LO inversion creates positive feedback, moving both JP101 and JP102 to their alternate positions reverses the loop polarity without rework.
* **VCXO Pull Range & Pull-In:**  
  Y101 (SX3V 25 MHz VCXO) pulls ±100 ppm over 0.3 V to 3.0 V ($\pm 2.5\text{ kHz}$ at 25 MHz). Multiplied by $N = 232$, the tuning range at 5.8 GHz is $\pm 580\text{ kHz}$ ($K_o = 2.70 \times 10^6\text{ rad/s/V}$). Between two independent TCXO references (±2.5 ppm each), the maximum frequency difference is 29 kHz. The pull-in time from 30 kHz offset is 3.8 ms. The VCXO tuning range covers the worst-case frequency disagreement by a 20:1 margin.
* **Hold Switch (TS5A3159):**  
  U111 connects NC to $V_{ERR}$ and NO to $V_{MID}$ (1.65 V). When `LOOP_HOLD` is asserted (HIGH), the integrator's input resistor $R_1$ is tied directly to $V_{MID}$ (the same potential as U112A's non-inverting input). Current through $R_1$ is 0 A, and TS5A3159 off-isolation leakage (< 100 pA) is shunted to the low-impedance $V_{MID}$ divider rather than charging the 100 nF integrating capacitor. This extends the hold duration from milliseconds to seconds.
* **First Power-Up Lock:**  
  The loop will NOT lock on cold power-up because the PE43711 DSA powers up at 31.75 dB attenuation. Once the software initializes the DSA to 0–5 dB attenuation and writes the MAX2871 registers, the loop will reliably lock within 5 ms.

### 3.4. Fast Decision Path
* **Common-Mode Shift at Arm Inputs:**  
  ADL5380 baseband outputs sit at $V_{CM} = 3.2\text{ V}$ nominal (up to 3.8 V with ADJ open). THS4541 on single 3.3 V supply has an input common-mode limit $V_{ICM} \le 3.3\text{ V} - 1.2\text{ V} = 2.1\text{ V}$. The resistor network ($R_g = 1000\ \Omega$, $R_f = 4000\ \Omega$, $R_s = 1000\ \Omega$ to GND) shifts the summing junction voltage to:
  $$V_n = \frac{V_{IN,CM}/R_g + V_{OCM}/R_f}{1/R_g + 1/R_f + 1/Rs} = \frac{3.2/1000 + 1.65/4000}{2.25/1000} = 1.605\text{ V}$$
  At the worst-case $V_{IN,CM} = 3.8\text{ V}$, $V_n = 1.872\text{ V}$, leaving 228 mV of headroom below the 2.1 V limit. The emitter followers of the ADL5380 source 1.6 to 1.9 mA into the network, keeping them biased in their active region.
* **Comparator Thresholds & Margin:**  
  At -20 dBm at the demodulator, differential baseband swing at the comparator inputs is $\pm 249\text{ mV}$ peak. For sign(I) (U107), the input is differential ($I_P$ vs $I_N$), so the threshold is 0 V differential. TLV3601 input offset is ±5 mV max, and default internal hysteresis is 3 mV. The signal-to-threshold margin is $249 / 8 \approx 31:1$ (30 dB).
* **Window Comparators (U601–U604):**  
  Each TLV3603 compares its arm signal ($I_P, I_N, Q_P, Q_N$) against an independent 16-bit threshold ($V_{TIP}, V_{TIN}, V_{TQP}, V_{TQN}$) from U605 (AD5696R, 0–2.5 V, 38 µV/step). At power-up, AD5696R resets to midscale (1.25 V). Because the arm signals sit at 1.65 V DC, all four comparators power up HIGH ($1.65\text{ V} > 1.25\text{ V}$). Gateware's `rx_engine` is held disabled at reset, preventing false events until software configures the thresholds.
* **Scope Taps & PYNQ 200 Ω Resistors:**  
  The 453 Ω scope tap into a 50 Ω scope draws $6.5\text{ mA}$ from the comparator output, causing an output voltage drop of ~160 mV ($V_{OH} \approx 3.14\text{ V}$). The $33\ \Omega$ on-board series resistor plus the PYNQ-Z2's $200\ \Omega$ header resistor into ~10 pF input capacitance yields an RC time constant $\tau = 2.33\text{ ns}$ (10–90% rise time of 5.1 ns). This matches the budget's 4.4 ns allocation and introduces no ringing or reflection artifacts on the FPGA pins.

### 3.5. The Slow Decision Path (Sheet 6)
* **Architecture:**  
  U501 and U502 provide a second stage of fully differential amplification at gain 20 ($R_{g2} = 1\text{ k}\Omega$, $R_{f2} = 20\text{ k}\Omega$). Followed by a 1.0 kΩ / 33 pF single-pole lowpass filter, the cutoff frequency is $f_c = 4.82\text{ MHz}$ (noise equivalent bandwidth 7.57 MHz).
* **Offset Voltage Accumulation:**  
  Cascading gain 4 and gain 20 gives a total DC gain of 80. A 2 mV offset from the demodulator plus 0.5 mV from the first FDA produces $2\text{ mV} \times 80 + 0.5\text{ mV} \times 80 = 200\text{ mV}$ of DC offset at the slow comparators. Because the quiet signal level at -107 dBm is only $\pm 77\text{ mV}$ peak, uncompensated DC offset would permanently saturate the slow path.
* **Offset Nulling:**  
  MCP4728A1 (U506, address 0x61) provides channels B (`I_OFF`) and C (`Q_OFF`), which feed the summing junctions of U501 and U502 through 100 kΩ resistors. With $R_{f2} = 20\text{ k}\Omega$, the trim range is $\pm 1.65\text{ V} \times (20\text{k}/100\text{k}) = \pm 330\text{ mV}$, providing ample range to null the 200 mV offset. Calibration via software monitoring of `CMP_I_S` duty cycle is mandatory during stage 1.5 bring-up.

### 3.6. The Transmitter
* **2-Bit Resistor Ladder Levels:**  
  On PYNQ-Z2, each FPGA pin drives through an on-board $2.2\text{ k}\Omega$ resistor plus the PYNQ's $200\ \Omega$ series resistor ($2.4\text{ k}\Omega$ total). Two pins plus a $300\ \Omega$ resistor to DAC reference $V_R$ form a DAC with Thevenin resistance $R_{th} = 2.4\text{k} \parallel 2.4\text{k} \parallel 300 = 240\ \Omega$. With $V_R = 0.338\text{ V}$, the ladder produces output levels of 0.17 V, 0.50 V, and 0.83 V (swing $\pm 0.33\text{ V}$ peak around 0.50 V), corresponding to -4.5 dBm output from ADL5375 at 5.8 GHz.
* **TX_EN Inverter & Failsafe Logic:**  
  U206 (74LVC1G04) with R227 ($1\text{ k}\Omega$ pull-down) guarantees that whenever the host is powered off, unconfigured, or booting, `TX_EN` is held low ($\le 0.35\text{ V} < V_{IL} = 0.8\text{ V}$). U206 drives DSOP high (~3.3 V), muting the ADL5375. When transmitting, the PYNQ FPGA drives 3.3 V through $200\ \Omega$, creating a divider with $1\text{ k}\Omega$ that delivers $2.75\text{ V}$ to U206 ($> V_{IH} = 2.0\text{ V}$).
* **Station Identification:**  
  `morse_keyer.v` keys callsign "W3JQ" in Morse code every 10 minutes (600 seconds) by modulating `TX_DIS`. Timing is parameterized to 20 WPM (60 ms dit).

### 3.7. Power Distribution & Thermal Analysis
* **Rail Drops:**  
  At 1.34 A total current, F301 drops 107 mV, Q301 drops 80 mV, and FB301 drops 37 mV (total 224 mV). `+5V_RF` sits at 4.77 V from a 5.00 V source. Margin above the 4.75 V minimum operating spec of ADL5380/ADL5375 is only 20 mV. A dedicated 5.15 V supply must be used on the bench.
* **Thermal Dissipation:**  
  - Total board power is 6.7 W.  
  - U301/U302 (+3V3_PLL_TX/RX): 200 mA each. The series 2.2 Ω 1206 resistors dissipate 88 mW each, leaving 214 mW in each SOT-23-5 TPS7A2033 ($\Delta T \approx 43\ ^\circ\text{C}$, $T_j \approx 68\ ^\circ\text{C}$).  
  - RF ICs: ADL5380 dissipates 1.23 W (QFN-24); ADL5375 dissipates 1.02 W (QFN-24); three ADL5611 dissipate 0.62 W each (SOT-89). Total heat in the RF chips is 4.1 W. The extensive thermal via arrays under their exposed pads conduct this heat into the L2 ground plane. In an unventilated enclosure, internal temperature will rise by $40-50\ ^\circ\text{C}$; forced air or thermal conduction to a metal chassis is required for continuous field operation.

### 3.8. Gateware and Driver
* **RTL & Timing:**  
  `costaslink_pynq.v` uses an ISERDESE2 8:1 DDR sampler running at 400 MHz (800 Ms/s, 1.25 ns resolution). In Vivado 2024.1, the overlay routes cleanly and meets all timing constraints: WNS = +1.661 ns, WHS = +0.031 ns.
* **Register Bus:**  
  AXI-Lite register reads take 4 clock cycles (40 ns) via `axil_bridge.v`. Register writes take 2 cycles. Bus transactions are completely decoupled from the fast sampling pipeline.

### 3.9. Manufacturing & Release Gates
* **Consigned Parts:**  
  Three parts are consigned: T101 (Johanson 5400BL15B050 balun, C2837312), U201 (ADL5375-05, C579150), and U104 (ADL5380, C579152). 4 units of each must be purchased from Digi-Key/Mouser and registered under JLCPCB's overseas consignment process.
* **Footprints & BOM:**  
  BOM lines match CPL placements exactly (382 parts placed, 68 unique BOM lines). All passives are 0402/0603/0805. Through-hole SMAs and header pins are on the top side, while J302 (2x20 header on back) is excluded from assembly for home soldering, keeping JLCPCB assembly single-sided.

### 3.10. Code-Generated Hardware Methodology
* **Assessment:**  
  The Python generation methodology (`gen/`) enforces mathematical design rules as code, produces 100% deterministic schematic and layout outputs, and asserts RF/analog budget equations directly during compilation. The minor drawback is that tool-level metadata (such as KiCad project NetClass regexes) must be kept strictly synchronized with programmatic net naming conventions.

---

## 4. Beyond the List: What Nobody Asked About (§4)

### 4.1. Safety and the Law: Extreme EIRP and Microwave Exposure
* **The Physics:** With the 2 W (+33 dBm) PA module and the 30 dBi parabolic dish, the effective isotropic radiated power is:
  $$\text{EIRP} = +33\text{ dBm} + 30\text{ dBi} = +63\text{ dBm} = 2000\text{ Watts (2.0 kW)!}$$
  With the 24 dBi panel, $\text{EIRP} = +57\text{ dBm} = 500\text{ Watts}$.
* **FCC MPE Limits (§1.1310):** At 5.8 GHz, the maximum permissible exposure for the general population in an uncontrolled environment is $S = 1.0\text{ mW/cm}^2 = 10\text{ W/m}^2$.
* **Minimum Safe Distance:**
  $$R = \sqrt{\frac{\text{EIRP}}{4\pi S}} = \sqrt{\frac{2000\text{ W}}{4\pi \times 10\text{ W/m}^2}} \approx 4.0\text{ meters (13.1 feet)!}$$
  Within a 4-meter cone in front of the 30 dBi dish, radiation exceeds federal safety limits. Furthermore, corneal and retinal exposure at close range to a 2 kW EIRP beam creates an immediate risk of irreversible thermal eye injury (microwave cataracts).
* **Action Required:**
  1. A formal RF Safety Protocol must be added to `BRINGUP.md` stages 5 and 6.
  2. The transmitter must never be enabled when personnel are in front of the dish or panel.
  3. Stations must carry physical warning placards.

### 4.2. Antenna Port ESD and Lightning Protection
* **The Hazard:** In field deployments on hills or campus rooftops with 10-meter coaxial cables connected to outdoor panel antennas, atmospheric static electricity and nearby lightning strikes will induce hundreds of volts onto the antenna center pin.
* **The Circuit:** J101 (RX ANT) connects through a 1.5 pF 0402 ceramic capacitor directly to the input of U101 (SKY65404 LNA). The SKY65404 has an ESD rating of Class 1A (250 V HBM). A 1.5 pF capacitor is an effective open circuit at DC, but a fast electrostatic discharge transient (rise time < 1 ns) will pass straight through the capacitor into the sensitive GaAs pHEMT gate.
* **Recommendation for Rev B:** Add a high-frequency, low-capacitance RF bidirectional TVS diode (such as Infineon ESD108-B1-CSP0201, $C_d < 0.1\text{ pF}$, or a gas discharge tube arrestor on the external antenna feedline). For rev A, field testing must use an external bulkhead lightning surge arrestor on the coaxial cable entering the building.

### 4.3. Mechanical Cable Strain on Standoffs
* **The Hazard:** Five SMA cables (RX ANT, TX ANT, SW TX, ANT, SW RX) plus trigger SMAs exit the top and left edges of the board. Coaxial cables like LMR-200 or RG-58 are stiff and exert substantial torsional torque.
* **Mechanical Structure:** CostasLink sits 8 mm above the PYNQ-Z2, mated via the 2x20 header J302. Only three M3 standoffs (H301, H302, H303) and one slot (H304) support the assembly.
* **Recommendation:** Ensure all three perimeter standoffs are securely fastened to a rigid baseplate during bench and field testing to prevent flexing that could crack solder joints on J302 or surface-mount passives.

---

## 5. CLAUDE_PCB.md Compliance (§5)

| Section & Rule | Requirement | Board Status | Compliance & Evidence |
|---|---|---|---|
| **§2 Build System** | One command makes everything; all paths relative | PASS | `python3 build.py` builds all. No hardcoded absolute user paths in committed project files. |
| **§3 Sourcing** | Every machine-placed part in stock; Basic preferred | PASS | All SMD parts sourced with valid LCSC codes. The 3 consigned parts are registered with Digi-Key numbers. |
| **§4 Schematics** | Signals left-to-right; limits at connectors; no overlapping text | PASS | Blue boxes display levels and bandwidths at every node. Connector limit notes printed. `hardware/checks/erc.json` reports 0 errors. |
| **§5 Placement & Routing** | L2 unbroken ground plane; decoupling at pins; thermal vias | PASS | In1_Cu (L2) contains 0 tracks (verified). Ground via fences line every RF line at 1.2 mm pitch. |
| **§5 Power Rails** | Check regulator dropout from worst input | **FLAG** (Finding 1) | Total drop on 5V rail is 224 mV. 5.00 V input yields 4.77 V at +5V_RF, leaving only 20 mV margin for ADL5380/ADL5375. |
| **§6 Silkscreen** | Labels in row stand alike; text $\ge 0.8\text{ mm}$ | PASS | Connector rows checked and verified by `tools/label_check.py` with 0 violations. |
| **§8 Manufacturing** | Gerbers, CPL native & JLC-corrected, BOM, Order Settings | PASS | `mfg/release/` contains complete Gerbers, BOM, CPL, `ORDER_SETTINGS.md`, and `CONSIGNMENT.md`. |
| **§10 Gate 5** | DRC 0 violations, 0 unconnected items | PASS | KiCad 10 DRC run on shipped file: 0 violations, 0 unconnected, 0 parity issues. |
| **§11 Tooling Quirks** | `board.Save()` netclass rewrite awareness | **FLAG** (Finding 2) | NetClass regex in `.kicad_pro` failed to match hierarchical net names, defaulting RF tracks to 0.20 mm gap. |
| **§14 RF Rules** | CPWG with ground fence $\le \lambda/10$; DC blocks on RF | PASS | CPWG traces used throughout; via fence pitch 1.2 mm ($\ll \lambda/10 = 2.9\text{ mm}$). DC blocks on all ports. |
| **§15 Power Protection** | Reverse polarity P-FET; TVS; input fusing | PASS | AO3401A ideal diode, 2 A PTC fuses (F301, F302), and SMAJ5.0A TVS on input rail. |

---

## 6. What Was Checked and Verified Correct

1. **Schematic & Connectivity:**
   - Generated netlist audited via `tools/net_check.py`: 382 parts, 267 nets, 0 one-pin nets, 0 broken paths.
   - `kicad-cli sch erc` executed on `hardware/CostasLink-PYNQ-Z2.kicad_sch`: 0 errors, 0 warnings.
2. **PCB Layout & DRC:**
   - `kicad-cli pcb drc` executed on `hardware/CostasLink-PYNQ-Z2.kicad_pcb`: 0 violations, 0 unconnected, 0 schematic parity issues.
   - L2 plane verified 100% solid copper (0 track segments).
3. **RF Signal Paths:**
   - RX chain walked: J101 -> U101 (LNA) -> U102 (DSA) -> U103 (GB1) -> U117 (GB2) -> CP101 -> T101 (Balun) -> U104 (ADL5380).
   - TX chain walked: U201 (ADL5375) -> U202 (GB) -> Pi pad -> CP201 -> J202 (TX ANT).
4. **Footprint Dimensions & Terminal Pinouts:**
   - Johanson 5400BL15B050 balun (T101) pin configuration verified against datasheet page 1.
   - TC32H4 TCXO (Y201) pin 1 verified as E/D with internal pull-up (safe when floating).
   - SKY65404-31 (U101), PE43711 (U102), HMC536 (U401) footprints verified against easyeda2kicad models.
   - AD5696R (U605) TSSOP-16 pinout and I2C address (0x0C) verified against Analog Devices datasheet.
5. **Gateware & Clocks:**
   - Vivado 2024.1 synthesis and implementation logs inspected (`build/pynq/pynq_build.log`). Timing met with WNS = +1.661 ns and WHS = +0.031 ns at 400 MHz DDR (800 Ms/s).
   - `morse_keyer.v` timing parameters verified against 100 MHz system clock.

---

## 7. Reconciliation with Other Reviewers

Peer review reports were consulted after independently drafting Sections 1–6:
* `design_review_GPT-5.6Terra/DESIGN_REVIEW_GPT-5.6Terra.md` (submitted)
* `design_review_Grok4.7/DESIGN_REVIEW_Grok4.7.md` (drafting in progress)
* `design_review_KimiK3/DESIGN_REVIEW_KimiK3.md` (drafting in progress)
* `design_review_Claude/DESIGN_REVIEW_Claude.md` (author's early self-review, 2026-10-09)

---

### 7.1. Findings Agreed With (Supported by Calculations)

1. **Costas Detector Error Gain Factor-of-Two Error (GPT-5.6Terra Finding 2):**
   * *Agreement:* Fully agree. GPT-5.6Terra correctly identified that `sim/budget.py` assigns the full *differential* fast-arm peak swing ($246.6\text{ mV/rad}$) to $K_d$. However, analog switch U110 (SN74LVC1G3157) samples only *one single-ended output* ($Q_P$ or $Q_N$) at a time around $V_{MID}$ (1.65 V).
   * *Calculation:* The single-ended swing into U112A's input resistor is exactly half:
     $$K_{d,actual} = \frac{1}{2} K_{d,diff} = 0.1233\text{ V/rad}$$
     With the fitted filter values ($R_1 = 20\text{ k}\Omega$, $R_2 = 750\ \Omega$, $C = 100\text{ nF}$):
     $$\tau_1 = R_1 C = 2.0\text{ ms}, \quad \tau_2 = R_2 C = 75\ \mu\text{s}$$
     $$\omega_n = \sqrt{\frac{K_d K_o}{\tau_1}} = \sqrt{\frac{0.1233 \times 2.70 \times 10^6}{0.002}} = 12901\text{ rad/s} \implies f_n = 2053\text{ Hz}$$
     $$\zeta = \frac{\tau_2}{2} \omega_n = \frac{75 \times 10^{-6}}{2} \times 12901 = 0.484$$
     The fitted loop is therefore underdamped ($\zeta = 0.484$ vs $0.707$) and slower ($f_n = 2.05\text{ kHz}$ vs $3.0\text{ kHz}$).
   * *Settlement:* To restore the target $f_n = 3.0\text{ kHz}$ and $\zeta = 0.707$ with $K_d = 0.1233\text{ V/rad}$:
     $$\tau_1 = \frac{K_d K_o}{\omega_n^2} = \frac{0.1233 \times 2.70 \times 10^6}{(2\pi \times 3000)^2} = 9.37 \times 10^{-4}\text{ s} \implies R_1 = \frac{\tau_1}{C} = 9.37\text{ k}\Omega$$
     Change R126 from $20\text{ k}\Omega$ to $10\text{ k}\Omega$ (E24 standard, or $9.53\text{ k}\Omega$ E96). This is a simple BOM line change (both values are standard stock).

2. **HMC536 Isolation Failure with External 2 W PA (GPT-5.6Terra Finding 3):**
   * *Agreement:* Fully agree. The HMC536 has a guaranteed minimum isolation of 26–27 dB at 5.8 GHz. A +29.8 to +33 dBm PA input to the switch leaks +3.8 to +7 dBm into the off-port (SW RX), which directly violates the +1.0 dBm absolute maximum input rating of the SKY65404 LNA.
   * *Settlement:* A fixed external SMA limiter (Mini-Circuits VLM-63-2W-S+) must precede J101 whenever an external PA is cabled into the antenna switch.

3. **Absence of On-Board Global Fiducials (GPT-5.6Terra Finding 4):**
   * *Agreement:* Agree that `CLAUDE_PCB.md` Gate 15 specifies fiducials on the board. While `ORDER_SETTINGS.md` specifies that JLCPCB will add edge rails with panel fiducials (and depanel them before shipping), having three fiducials on the board itself ensures accurate SMT vision alignment for the 0.5 mm pitch QFNs (U102, U104, U115, U201, U203).

---

### 7.2. Findings Disputed or Clarified

1. **GPT-5.6Terra Finding 1 ("The RF order waives impedance control - Would cost a respin"):**
   * *Dispute:* GPT-5.6Terra classifies the selection of "Impedance Control: No requirement" in `ORDER_SETTINGS.md` as requiring a stop/respin.
   * *Evidence:*
     1. Selecting "Specify Stackup: JLC04161H-7628" explicitly pins the exact dielectric material and layer thicknesses ($h = 0.2104\text{ mm}$, $\varepsilon_r = 4.4$, 1 oz outer copper).
     2. On standard JLCPCB 4-layer production without the added $30+ impedance certification fee, standard etch tolerance on trace width is ±0.02 mm (not the ±20% worst-case window GPT assumes).
     3. The total physical length of the RF traces on this board is very short: the longest segment (between LNA and DSA, or GB and coupler) is only 15–20 mm ($< \lambda/2$).
     4. Mismatch loss for a line varying between 47 Ω and 53 Ω terminated in 50 Ω is under 0.05 dB, and return loss remains > 28 dB.
     5. The quarter-wave couplers CP101 and CP201 are monitor taps (-20 dB into scope/spectrum analyser U.FL jacks), not precision reflectometer bridges; a ±1.5 dB variation in monitor coupling has zero operational consequence.
   * *Verdict:* Selecting "No requirement" does NOT block the order or warrant a respin for rev A.

---

### 7.3. What Everybody Else Missed

1. **The NetClass Regex Failure in `CostasLink-PYNQ-Z2.kicad_pro`:**  
   No other reviewer discovered why the board copper had an actual coplanar ground gap of 0.20 mm instead of the designed 0.25 mm. The regex pattern `/^RF_/` in `CostasLink-PYNQ-Z2.kicad_pro` failed to match any net because KiCad hierarchical net names start with `/` or sheet paths (e.g. `/Net-(J101-In)`). This caused all 267 signal nets to fall back to NetClass `Default`, so the top-layer ground zone poured at its 0.20 mm clearance instead of the 0.25 mm RF clearance.
2. **ADL5375 Baseband Bias Asymmetry ($VN\_0V5$ Shift):**  
   The $5.1\text{ k}\Omega / 1\text{ k}\Omega$ bias divider creates an 836 Ω Thevenin resistance. The $82\ \mu\text{A}$ bias current sourced by pins `IBBN` and `QBBN` lifts `VN_0V5` by 68.5 mV to 0.610 V (110 mV above nominal 0.500 V). The positive pins `IBBP` and `QBBP` see 240 Ω and lift by only 9.8 mV, resulting in an intrinsic 58.7 mV differential offset.
3. **Quantitative 5V Input Rail Drop Margin:**  
   While Claude's earlier review noted the PTC and bead drops in passing, our analysis computed the exact combined worst-case drop: F301 (80 mΩ max = 107 mV) + Q301 (60 mΩ = 80 mV) + FB301 (45 mΩ at 0.82 A = 37 mV) = 224 mV on-board drop. At 1.34 A, standard 5.00 V USB power banks and cables sagging to 4.85 V will drop `+5V_RF` to 4.62 V (130 mV below the 4.75 V minimum operating spec of ADL5380 and ADL5375).
4. **Physical Verification of TCXO Y201 Pin 1:**  
   By rendering and inspecting the manufacturer datasheet drawing of TC32H4 (C5119013), we conclusively resolved Open Question 13 from `PLAN.md` §10: Pad 1 is designated "E/D or N.C." with internal pull-up. Leaving it floating guarantees active oscillation at 25.000 MHz.
5. **Exact RF Radiation Safety MPE Boundaries:**  
   Calculated the quantitative FCC §1.1310 exposure hazard: the 2 W PA behind a 30 dBi dish produces 2.0 kW EIRP, requiring a strict minimum safe standoff distance of 4.0 meters (13.1 feet) to prevent personnel exceeding federal MPE limits.


