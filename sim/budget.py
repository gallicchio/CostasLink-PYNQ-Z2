#!/usr/bin/env python3
"""The design arithmetic of CostasLink-PYNQ-Z2, asserted (CLAUDE_PCB.md section 4, "Values").

Everything the plan and the schematic notes quote as a number is computed here from the
datasheet figures in PARTS below, so that a changed part changes every number at once.

    python3 sim/budget.py            prints the tables; exits non-zero if an assertion fails
    python3 sim/budget.py --json F   also writes the results for the generator's notes

Sections: link budget, receiver chain levels, single-antenna isolation, latency, the TX
resistor DAC, the Costas loop, the FDA level shift, the MAX2871 loop filter, power and
regulator dissipation.  Sources are cited beside each figure (datasheet text in
build/txt/, made by the build from datasheets/).
"""
import json, math, sys

c0 = 299792458.0
kT_dBm_Hz = -174.0                       # kT at 290 K per Hz

# ---------------------------------------------------------------------------
# Datasheet figures used below (build/txt/<part>.txt unless noted)
PARTS = dict(
    # ADL5375-05 at LO = 5800 MHz (ADL5375 Rev. D, specification table, "LO = 5800 MHz")
    mod_pout_fullscale_dBm=-1.36,      # POUT with 1 V p-p differential baseband
    mod_op1db_dBm=4.9,
    mod_carrier_feedthrough_dBm=-19.5,
    mod_bb_bias_V=0.5,                 # ADL5375-05 baseband bias level
    mod_bb_abs_V=(0.0, 1.0),           # absolute voltage allowed on each baseband pin
    mod_bb_Rin_k=60.0,                 # differential input resistance, kOhm (min)
    mod_bb_Ibias_uA=41.0,              # bias current sourced from each baseband input
    mod_I_mA=203.0,
    # ADL5611 at 5800 MHz (ADL5611 Rev. B, "FREQUENCY = 5800 MHz")
    gb_gain_dB=14.3,
    gb_p1db_dBm=12.8,                  # the 5800 MHz row (Grok4.7 / KimiK3 review: 16.0 was the 6 GHz band's figure)
    gb_nf_dB=6.0,                      # the 5800 MHz row (was 3.5, the 3.5 GHz figure)
    gb_I_mA=124.0,                     # max
    # SKY65404-31 (201512O, Table 4, 4.9-5.9 GHz)
    lna_gain_dB=13.0,
    lna_nf_dB=1.0,
    lna_p1db_out_dBm=9.0,
    lna_abs_max_in_dBm=1.0,            # Table 2: absolute maximum RF input, LNA enabled
    lna_I_mA=15.0,
    # PE43711 (Table 3): insertion loss up to 6 GHz, 7 bits of 0.25 dB
    dsa_il_dB=2.4,
    dsa_max_dB=31.75,
    dsa_switch_ns=275.0,
    # ADL5380 at 5800 MHz, ADJ open (ADL5380 Rev. B, "DYNAMIC PERFORMANCE at RF = 5800 MHz")
    dem_gain_dB=5.8,                   # voltage conversion gain into 450 ohm differential
    dem_ip1db_dBm=11.6,                # input 1 dB compression (5.8 GHz column)
    dem_nf_dB=15.0,                    # noise figure at 5.8 GHz (figure 7 region; conservative)
    dem_bw_MHz=390.0,
    dem_out_cm_V=3.8,                  # Table 1: VS - 1.2 V with ADJ open (Table 4 says 3.2; the review took the worse, Response 9)
    dem_Rout_ohm=25.0,                 # per pin, in series
    dem_I_mA=245.0,                    # worst (ADJ = 1.5 k); ADJ open is less
    # THS4541 (datasheet): 850 MHz GBW, input common-mode range to Vs+ - 1.2 V
    fda_gbw_MHz=850.0,
    fda_vos_mV=0.5,                    # input offset, typical (the datasheet: +-0.4 mV typ, 1.5 max)
    fda_cm_headroom_V=1.3,             # input common-mode high, GUARANTEED minimum (Vs+) - 1.3 V over -40..125 C (1.2 is typical)
    fda_I_mA=10.1,
    # TLV3601 (datasheet 6.5): propagation 2.5 ns typ, 3.5 ns max at 50 mV overdrive; hysteresis 1.5-5 mV
    cmp_tpd_ns=2.5,
    cmp_hyst_mV=5.0,
    cmp_offset_mV=5.0,
    cmp_I_mA=4.9,
    # MAX2871 (datasheet): total 165 mA typ / 200 mA max both outputs at max power; REF_IN 10-210 MHz
    pll_I_mA=200.0,
    pll_icp_mA=2.56,                   # ICP = 1.63/RSET x (1+CP) : RSET 5.1k, CP = 7
    pll_pfd_MHz=25.0,
    pll_fout_MHz=5800.0,
    pll_kvco_MHz_V=60.0,               # MAX2871 VCO gain, typical 40-80 MHz/V across the band (datasheet)
    # SX3V25.000 VCXO (LCSC C5179998 datasheet): pull +-100 ppm min over 0.3-3.0 V (Vc 1.65 V centre)
    vcxo_MHz=25.0,
    vcxo_pull_ppm=100.0,
    vcxo_vc_V=(0.3, 3.0),
    vcxo_I_mA=10.0,
    # TC32H4 TCXO +-2.5 ppm over temperature, +-2 ppm initial (C5119013 datasheet)
    tcxo_ppm=2.5,
    # TPS7A2033: SOT-23-5, R_thJA about 187 C/W (as the ECP5 board found for this package)
    ldo_rth_C_W=187.0,
    hdr_R_ohm=200.0,                   # PYNQ-Z2 RPi header series resistor on every signal (TUL schematic sheet 4)
    cmp_series_ohm=33.0,               # the board's own series resistor on every comparator output (sheets 3, 6, 7)
    # the 5 V input path's MAXIMUM resistances (CLAUDE_PCB.md section 15: the worst case, not the typical)
    ptc_R1max_ohm=0.070,               # Bourns MF-MSMF200: R1max (the PTC after a trip and an hour)
    fet_rds_max_ohm=0.060,             # AO3401A: RDS(on) max at VGS = -4.5 V, 25 C
    bead_dcr_max_ohm=0.045,            # Murata BLM21PG221SN1: DC resistance max (on +5V_RF only)
    supply_min_V=5.10,                 # BRINGUP.md: the bench supply at the plug, a short lead (USB-C's vSafe5V minimum is 4.75)
    hdr_C_pF=10.0,                     # header + trace + Zynq input, about
)
P = PARTS
R = {}                                 # results


def db(x):
    return 10.0 * math.log10(x)


def friis_loss_dB(d_m, f_Hz):
    return 20.0 * math.log10(4.0 * math.pi * d_m * f_Hz / c0)


def dBm_to_Vrms(p_dBm, R_ohm=50.0):
    return math.sqrt(10 ** (p_dBm / 10.0) * 1e-3 * R_ohm)


def e24(x):
    """Nearest E24 value."""
    import bisect
    ser = [1.0, 1.1, 1.2, 1.3, 1.5, 1.6, 1.8, 2.0, 2.2, 2.4, 2.7, 3.0, 3.3, 3.6, 3.9, 4.3, 4.7, 5.1, 5.6, 6.2, 6.8, 7.5, 8.2, 9.1]
    e = math.floor(math.log10(x))
    m = x / 10 ** e
    best = min(ser + [10.0], key=lambda s: abs(math.log(s / m)))
    return best * 10 ** e


def e96(x):
    e = math.floor(math.log10(x))
    m = x / 10 ** e
    i = round(96 * math.log10(m))
    return round(10 ** (i / 96.0), 2) * 10 ** e


def section(t):
    print("\n== " + t)


# ---------------------------------------------------------------------------
section("1. Transmitter")
# The TX resistor DAC drives IBBP single-ended against IBBN held at the 0.5 V bias:
# levels 0.5 - a, 0.5, 0.5 + a.  The differential swing is a (not 2a), so the output
# is 20 log10(2a / 1.0 V p-p... ) below the 1 V p-p differential full-scale figure.
a_V = 0.35                                 # single-ended step: IBBP from 0.15 V to 0.85 V
assert P["mod_bb_abs_V"][0] <= 0.5 - a_V and 0.5 + a_V <= P["mod_bb_abs_V"][1], "baseband pins outside 0-1 V"
vdiff_pp = 2 * a_V                          # +a to -a is the full differential swing (BPSK)
tx_backoff_dB = 20 * math.log10(vdiff_pp / 1.0)
mod_out_dBm = P["mod_pout_fullscale_dBm"] + tx_backoff_dB
tx_out_dBm = mod_out_dBm + P["gb_gain_dB"]
R["tx_mod_out_dBm"] = mod_out_dBm
R["tx_out_dBm"] = tx_out_dBm
print("baseband step a = %.2f V (IBBP %.2f / 0.50 / %.2f V); BPSK swing %.2f V p-p diff = %.1f dB from full scale"
      % (a_V, 0.5 - a_V, 0.5 + a_V, vdiff_pp, tx_backoff_dB))
print("ADL5375 out %.1f dBm (carrier feedthrough %.1f dBm = %.0f dBc), ADL5611 +%.1f dB -> TX SMA %.1f dBm"
      % (mod_out_dBm, P["mod_carrier_feedthrough_dBm"], P["mod_carrier_feedthrough_dBm"] - mod_out_dBm,
         P["gb_gain_dB"], tx_out_dBm))
assert mod_out_dBm < P["mod_op1db_dBm"] - 3, "modulator driven into compression"
assert tx_out_dBm < P["gb_p1db_dBm"] - 1, "TX gain block in compression"
# the QPSK corners are +3 dB on the axis point: they land on the gain block's 5.8 GHz P1dB (PLAN.md section 18
# prices that as 1 dB on a corner); assert they are not past it
print("QPSK corners %.1f dBm against the ADL5611's 5.8 GHz P1dB %.1f dBm" % (tx_out_dBm + 3.0, P["gb_p1db_dBm"]))
assert tx_out_dBm + 3.0 <= P["gb_p1db_dBm"] + 0.1, "the corners are past the gain block's P1dB"

# The 2-bit resistor DAC: two equal resistors Rb from the FPGA pins (0 / 3.3 V, through the
# PYNQ's 200 ohm) and Rr from the Vr reference.  Node X = (3.3 (b0+b1)/Rb + Vr/Rr) / (2/Rb + 1/Rr).
VIO = 3.3
Rb = 2200.0
Rr = 300.0
Rb_eff = Rb + P["hdr_R_ohm"]
def dac_node(nhigh, Rb_, Vr):
    return (VIO * nhigh / Rb_ + Vr / Rr) / (2.0 / Rb_ + 1.0 / Rr)
# choose Vr so that X(1) = 0.5 V with the header resistor in place
Vr = (0.5 * (2.0 / Rb_eff + 1.0 / Rr) - VIO / Rb_eff) * Rr
levels = [dac_node(n, Rb_eff, Vr) for n in (0, 1, 2)]
levels_icepi = [dac_node(n, Rb, Vr) for n in (0, 1, 2)]
step = levels[2] - levels[1]
Znode = 1.0 / (2.0 / Rb_eff + 1.0 / Rr)
R.update(dac_Rb=Rb, dac_Rr=Rr, dac_Vr=Vr, dac_levels=levels, dac_step=step, dac_Znode=Znode)
print("TX DAC: Rb %.0f (+%.0f header) x2, Rr %.0f to Vr = %.3f V (DAC channel): levels %s V, step %.3f V, node %.0f ohm, "
      "tau into 3 pF %.2f ns" % (Rb, P["hdr_R_ohm"], Rr, Vr, ["%.3f" % v for v in levels], step, Znode, Znode * 3e-12 * 1e9))
print("  same board on a host without series resistors (Icepi): levels %s V" % ["%.3f" % v for v in levels_icepi])
assert abs(levels[1] - 0.5) < 1e-6
assert 0.25 < step < 0.40, step
i_dac_mA = (0.5 - Vr) / Rr * 1e3
print("  Vr DAC channel sources %.2f mA at the centre level (MCP4728 output buffer: fine)" % i_dac_mA)
ib_offset_mV = P["mod_bb_Ibias_uA"] * 1e-6 * Znode * 1e3
print("  ADL5375's %.0f uA input bias current lifts the node %.1f mV: trimmed by Vr" % (P["mod_bb_Ibias_uA"], ib_offset_mV))
# The N inputs (IBBN, QBBN) share one divider from +3V3_ANA, and both pins source their 41 uA into it: the
# build-17 5.1k / 1k (836 ohm) sat at 0.61 V, 0.1 V over the ladders (Gemini3.8Flash, Grok4.7, KimiK3).  Choose
# the divider so that, loaded by 82 uA, it lands on the ladders' centre level with their own lift.
bias_Rt, bias_Rb = 4700.0, 750.0
bias_Rth = bias_Rt * bias_Rb / (bias_Rt + bias_Rb)
bias_VN = 3.3 * bias_Rb / (bias_Rt + bias_Rb) + 2 * P["mod_bb_Ibias_uA"] * 1e-6 * bias_Rth
vp_centre = 0.5 + ib_offset_mV * 1e-3
R.update(bias_Rt=bias_Rt, bias_Rb=bias_Rb, bias_VN=bias_VN)
print("  N-side bias: %.1fk / %.0f from 3.3 V (%.0f ohm) loaded by 2 x %.0f uA: %.3f V against the ladders' %.3f V (%+.1f mV)"
      % (bias_Rt / 1e3, bias_Rb, bias_Rth, P["mod_bb_Ibias_uA"], bias_VN, vp_centre, (bias_VN - vp_centre) * 1e3))
assert abs(bias_VN - vp_centre) < 0.010, bias_VN

# ---------------------------------------------------------------------------
section("2. Link budget")
f = 5.8e9
B_MHz = 100.0                              # the fast arm's bandwidth (THS4541 at gain 4, section 7): noise, latency AND selectivity (section 4)
def friis(stages):
    """Cascade noise figure (dB) of [(gain_dB, nf_dB), ...]."""
    F, G = 1.0, 1.0
    for g_dB, nf_dB in stages:
        F += (10 ** (nf_dB / 10.0) - 1) / G
        G *= 10 ** (g_dB / 10.0)
    return 10 * math.log10(F)
# the receive chain by Friis, the DSA at 0 dB (its insertion loss is its noise figure), the 5.8 GHz rows of
# each datasheet (the old note said "LNA + 0.5 dB" with the ADL5611 at 3.5 dB; at 5.8 GHz it is 6.0)
nf_chain_dB = friis([(P["lna_gain_dB"], P["lna_nf_dB"]), (-P["dsa_il_dB"], P["dsa_il_dB"]), (P["gb_gain_dB"], P["gb_nf_dB"]),
                     (P["gb_gain_dB"], P["gb_nf_dB"]), (P["dem_gain_dB"], P["dem_nf_dB"])])
noise_dBm = kT_dBm_Hz + db(B_MHz * 1e6) + nf_chain_dB
R["noise_floor_dBm"] = noise_dBm
# The antennas (Prompt 2): four 24 dBi 40 x 30 cm flat panels with 10 m cables (N at the panel, SMA at
# the board or the amplifier); a pair of 30 dBi 60 cm dual-polarised dishes as the bigger option; a
# 2 dBi whip (a quarter-wave stick on the SMA) for the bench.  A 10 m cable at 5.8 GHz is 5 dB of LMR-200 (0.5 dB/m), 12 dB of RG-58:
# the amplifier belongs at the panel, with the cable on its low-loss side.
ANTENNAS = {"whip": 2.0, "panel": 24.0, "dish": 30.0}   # whip: a quarter-wave stick screwed on the SMA
CABLE_dB_per_m = 0.5
R.update(antennas=ANTENNAS, cable_dB_per_m=CABLE_dB_per_m, B_MHz=B_MHz, nf_chain_dB=nf_chain_dB, f_Hz=f)
print("TX %.1f dBm; noise floor in %.0f MHz with NF %.1f dB: %.1f dBm; antennas %s dBi; cable %.1f dB/m (10 m = %.0f dB)"
      % (tx_out_dBm, B_MHz, nf_chain_dB, noise_dBm, ANTENNAS, CABLE_dB_per_m, 10 * CABLE_dB_per_m))
rows = []
for d, ant, cable_m, pa in ((3.0, "whip", 0.0, 0.0), (10.0, "whip", 0.0, 0.0), (30.0, "whip", 0.0, 0.0),
                            (300.0, "panel", 10.0, 0.0), (3000.0, "panel", 10.0, 0.0), (3000.0, "panel", 0.0, 0.0),
                            (20000.0, "panel", 0.0, 0.0), (20000.0, "dish", 0.0, 0.0)):
    gant = ANTENNAS[ant]
    lc = 2 * cable_m * CABLE_dB_per_m                      # a cable at each end, amplifiers at the board
    pr = tx_out_dBm + pa + 2 * gant - lc - friis_loss_dB(d, f)
    snr = pr - noise_dBm
    rows.append((d, gant, friis_loss_dB(d, f), pr, snr))
    print("  d = %6.0f m, %-5s %2.0f dBi, %2.0f m cables: path loss %.1f dB, RX %.1f dBm, SNR %.1f dB%s"
          % (d, ant, gant, cable_m, friis_loss_dB(d, f), pr, snr, "" if snr > 10 else "  <-- below the 10 dB a clean idle carrier wants"))
R["link_rows"] = rows
assert rows[1][4] > 30, "the lab link (10 m, whips) has 30 dB to spare"
assert rows[6][4] > 10, "20 km with the panels and no amplifier still clears 10 dB (sim/link_rates.py has the error rates)"

# ---------------------------------------------------------------------------
section("2b. One antenna by time division: the HMC536 switch (build/txt/HMC536.txt)")
# the 5.0-6.0 GHz rows, GUARANTEED (minimum) values: isolation 27 dB (typ 32), P0.1dB 27 dBm at 3 V control (typ 29)
SW = dict(t_rise_ns=15.0, t_on_ns=30.0, iso_dB=27.0, il_dB=0.7, p01dB_dBm=27.0)
# SW TX's limit: what leaks to SW RX must stay 3 dB under the LNA's +1 dBm absolute maximum (no limiter), and
# the switch must stay linear (the silkscreen printed +29, its typical P0.1dB: the design review)
SW["tx_max_dBm"] = min(SW["p01dB_dBm"], P["lna_abs_max_in_dBm"] + SW["iso_dB"] - 3.0)
R["switch"] = SW
flight_ns_per_m = 1e9 / c0
for d in (10.0, 100.0, 300.0):
    rt = 2 * d * flight_ns_per_m
    print("  %4.0f m: round trip %.0f ns; the verifier's switch (%.0f ns) is back in RX in time %s; the prover's switch adds a fixed %.0f ns"
          % (d, rt, SW["t_on_ns"], "yes" if SW["t_on_ns"] < rt else "NO", SW["t_on_ns"]))
leak = tx_out_dBm - SW["iso_dB"]
print("  own TX leaks %.1f - %.0f = %.1f dBm into the RX jack while transmitting (LNA abs max %.0f dBm): fine bare, "
      "but a PA at +27 dBm leaks 0 dBm, so a PA with the switch wants a limiter ahead of the LNA" % (tx_out_dBm, SW["iso_dB"], leak, P["lna_abs_max_in_dBm"]))
assert leak < P["lna_abs_max_in_dBm"] - 10
print("  SW TX limit without a limiter: %+.0f dBm (leaks %+.0f dBm to SW RX against the LNA's %+.0f dBm; the switch's P0.1dB %+.0f dBm min)"
      % (SW["tx_max_dBm"], SW["tx_max_dBm"] - SW["iso_dB"], P["lna_abs_max_in_dBm"], SW["p01dB_dBm"]))
for name, t in (("SKY13453 (SOI, integrated driver)", 1000.0), ("HMC8038 / HMC849A", 150.0), ("HMC536 (chosen)", SW["t_on_ns"]), ("HMC427A ($62-75, 5 V logic)", 10.0)):
    print("  %-36s %6.0f ns = the round trip of %.0f m: usable beyond that, and adds that much to the prover's answer" % (name, t, t / flight_ns_per_m / 2))

# ---------------------------------------------------------------------------
section("2c. The USB-C amplifier modules Jason has (datasheets/AliExpress*.pdf, Prompt 8)")
# The PA: "SBB5089+SE5004-5.8G-2W", 5-6 GHz, 40 dB, P1dB +33 dBm at 5.5 GHz, 2 A from 5 V (type-C),
# 45 x 30 x 14 mm CNC shell, $21.49 + $7.54 shipping (AliExpress page, HESUI store).  Run it 3 dB below
# P1dB: a (nearly) constant-envelope PSK carrier tolerates compression, but the ladder's 3 dB envelope
# step between idle and a QPSK point and the flip through zero are cleaner linear.
PA_MOD = dict(name="SBB5089+SE5004 5.8 GHz 2 W module", gain_dB=40.0, p1db_dBm=33.0, band_GHz=(5.0, 6.0), I_A=2.0,
              price_usd=29.03, run_dBm=30.0)
PA_MOD["in_dBm"] = PA_MOD["run_dBm"] - PA_MOD["gain_dB"]
PA_MOD["pad_dB"] = round((tx_out_dBm - PA_MOD["in_dBm"]) / 10.0) * 10.0       # an SMA attenuator in the lead, a stock value
PA_MOD["out_dBm"] = tx_out_dBm - PA_MOD["pad_dB"] + PA_MOD["gain_dB"]
PA_MOD["heat_W"] = 5.0 * PA_MOD["I_A"] - 10 ** (PA_MOD["run_dBm"] / 10.0) * 1e-3
R["pa_module"] = PA_MOD
print("PA module: %s, %.0f dB, P1dB +%.0f dBm, %.0f A at 5 V.  To run it at +%.0f dBm it wants %.0f dBm in: the board's +%.1f dBm through a "
      "%.0f dB SMA attenuator gives +%.1f dBm out.  Without the pad the module is driven %.0f dB into compression.  Heat: about %.0f W in a "
      "45 x 30 x 14 mm shell: a heatsink or a fan, and a 5 V / 3 A source (a USB-C PD bank in the field)."
      % (PA_MOD["name"], PA_MOD["gain_dB"], PA_MOD["p1db_dBm"], PA_MOD["I_A"], PA_MOD["run_dBm"], PA_MOD["in_dBm"], tx_out_dBm,
         PA_MOD["pad_dB"], PA_MOD["out_dBm"], tx_out_dBm + PA_MOD["gain_dB"] - PA_MOD["p1db_dBm"], PA_MOD["heat_W"]))
assert PA_MOD["out_dBm"] <= PA_MOD["p1db_dBm"] - 2.5
# The LNA: "Active SAW Filter & LNA module", 5.8 GHz version, type-C 5 V.  The page's table stops at
# 2.4 GHz (17 dB, NF 1.6 dB); the 5.8 GHz unit has NO published gain, noise figure or passband.  Assumed
# until measured (BRINGUP.md stage 1): 15 dB, NF 2 dB, passband 5725-5875 MHz (the FPV band; "SAW" at
# 5.8 GHz is a ceramic or LC filter), and at least 30 dB of rejection 600 MHz away.  It sits at the panel's
# N connector so the 10 m cable's 5 dB comes after it; the DSA absorbs its gain.
LNA_MOD = dict(name="SAW filter + LNA module, 5.8 GHz version", gain_dB=15.0, nf_dB=2.0, passband_MHz=(5725, 5875), reject_600MHz_dB=30.0,
               price_usd=13.06, assumed=True)
R["lna_module"] = LNA_MOD
nf_with = LNA_MOD["nf_dB"] + 10 * math.log10(1 + (10 ** (nf_chain_dB / 10.0) - 1) / 10 ** ((LNA_MOD["gain_dB"] - 10 * CABLE_dB_per_m) / 10.0))
print("LNA module (assumed numbers): %.0f dB, NF %.1f dB ahead of a 10 m cable (%.0f dB) and this board (NF %.1f): system NF %.1f dB; "
      "the DSA takes the %.0f dB of extra gain.  Its filter is the receiver's only selectivity before the demodulator: with the own "
      "transmitter 600 MHz away it adds the %.0f dB (assumed) that section 4 asks of the antennas."
      % (LNA_MOD["gain_dB"], LNA_MOD["nf_dB"], 10 * CABLE_dB_per_m, nf_chain_dB, nf_with, LNA_MOD["gain_dB"], LNA_MOD["reject_600MHz_dB"]))
assert nf_with < 3.0

# ---------------------------------------------------------------------------
section("3. Receiver chain levels (10 m, DSA chosen so the demodulator sees about -20 dBm)")
pr10 = rows[1][3]
R["rx_rows"] = {"%.0f m %.0f dBi" % (d, g): pr for d, g, _, pr, _ in rows}
N_GB = 2                                   # two ADL5611 gain blocks after the DSA (Response 6: the comparator floor)
def chain(pin_dBm, dsa_dB):
    lna_out = pin_dBm + P["lna_gain_dB"]
    dsa_out = lna_out - P["dsa_il_dB"] - dsa_dB
    gb_out = dsa_out + N_GB * P["gb_gain_dB"]
    return lna_out, dsa_out, gb_out
G_rf_dB = P["lna_gain_dB"] - P["dsa_il_dB"] + N_GB * P["gb_gain_dB"]
target_dem_in = -20.0
dsa_set = max(0.0, min(P["dsa_max_dB"], round((pr10 + G_rf_dB - target_dem_in) * 4) / 4.0))
lna_out, dsa_out, dem_in = chain(pr10, dsa_set)
R.update(rx_in_dBm=pr10, lna_out_dBm=lna_out, dsa_out_dBm=dsa_out, gb1_out_dBm=dsa_out + P["gb_gain_dB"], N_GB=N_GB, G_rf_dB=G_rf_dB)
vin_rms = dBm_to_Vrms(dem_in)
vbb_diff_rms = vin_rms * 10 ** (P["dem_gain_dB"] / 20.0)
G_fda = 4.0                                # the fast arms: gain 4 = 100 MHz; gain 2 would be 180 MHz and 1.7 ns sooner, but 20 dB less
                                           # rejection of the own transmitter 600 MHz away (section 4), so no (Response 7)
vcmp_rms = vbb_diff_rms * G_fda
R.update(dsa_set_dB=dsa_set, dem_in_dBm=dem_in, vbb_diff_rms=vbb_diff_rms, G_fda=G_fda, vcmp_rms=vcmp_rms)
print("RX %.1f dBm -> LNA %.1f -> DSA (%.2f dB set) %.1f -> 2 x ADL5611 %.1f dBm at the demodulator (IP1dB %.1f)"
      % (pr10, lna_out, dsa_set, dsa_out, dem_in, P["dem_ip1db_dBm"]))
print("demod: %.1f mV rms in, x%.2f (%.1f dB) -> %.1f mV rms differential baseband; FDA x%.0f -> %.0f mV rms (+-%.0f mV peak) at the comparators"
      % (vin_rms * 1e3, 10 ** (P["dem_gain_dB"] / 20.0), P["dem_gain_dB"], vbb_diff_rms * 1e3, G_fda, vcmp_rms * 1e3, vcmp_rms * 1e3 * 1.414))
assert P["lna_abs_max_in_dBm"] > pr10 + 10, "LNA abs max too close"
# The comparator floor: a TLV3601 needs about 2 x (offset + hysteresis) = 20 mV peak to decide at all.
# With the DSA at 0 dB that sets the weakest signal each path can read; the noise sets the other
# limit (quiet = 11.4 dB SNR for BPSK, sim/link_rates.py; 8.4 dB before Response 10 corrected its
# sideband factor).  A path is balanced when the two agree.
vmin_cmp = 2 * (P["cmp_offset_mV"] + P["cmp_hyst_mV"]) * 1e-3
def floor_dBm(G_bb):
    """antenna level at which the comparator behind baseband gain G_bb sees vmin_cmp peak (DSA at 0)"""
    vrms_dem = vmin_cmp / 1.414 / G_bb / 10 ** (P["dem_gain_dB"] / 20.0)
    return 10 * math.log10(vrms_dem ** 2 / 50.0 / 1e-3) - G_rf_dB
G_slow = 20.0                              # the slow stage's gain, after the fast arm (section 7b)
floor_fast = floor_dBm(G_fda)
floor_slow = floor_dBm(G_fda * G_slow)
B_slow_MHz = 7.5                           # the slow path's noise bandwidth (section 7b)
noise_slow = kT_dBm_Hz + db(B_slow_MHz * 1e6) + nf_chain_dB
R.update(sensitivity_dBm=floor_fast, floor_fast_dBm=floor_fast, floor_slow_dBm=floor_slow, G_slow=G_slow,
         B_slow_MHz=B_slow_MHz, noise_floor_slow_dBm=noise_slow, cmp_floor_mV=vmin_cmp * 1e3)
print("comparator floor (%.0f mV peak, DSA at 0): fast path %.1f dBm at the antenna (noise quiet %.1f dBm in %.0f MHz), "
      "slow path %.1f dBm (noise quiet %.1f dBm in %.1f MHz)"
      % (vmin_cmp * 1e3, floor_fast, noise_dBm + 11.4, B_MHz, floor_slow, noise_slow + 11.4, B_slow_MHz))
assert floor_slow < noise_slow + 11.4, "the slow path must be noise-limited, not comparator-limited"
assert floor_fast < noise_dBm + 11.4 + 8, "the fast path should be within 8 dB of noise-limited"

# ---------------------------------------------------------------------------
section("4. One antenna?  TX-to-RX isolation needed for frequency-division duplex")
# The leakage lands on the demodulator at the offset df and is only filtered AFTER the
# demodulator.  It must stay (a) below the demodulator's IP1dB - 10 dB and (b) below the
# wanted signal minus 10 dB after the arm filter's rejection at df.
def lp_reject_dB(df_MHz, poles=2, fc_MHz=B_MHz):
    return 10 * poles * math.log10(1 + (df_MHz / fc_MHz) ** 2)
print("arm filter %.0f MHz, 2 poles; the wanted signal at 10 m is %.1f dBm" % (B_MHz, pr10))
for df in (25.0, 50.0, 100.0, 200.0, 600.0):
    rej = lp_reject_dB(df)
    leak_max_at_rx = min(pr10 - 10 + rej, (P["dem_ip1db_dBm"] - 10) - (P["lna_gain_dB"] - P["dsa_il_dB"] - dsa_set + P["gb_gain_dB"]))
    iso = tx_out_dBm - leak_max_at_rx
    print("  TX/RX %4.0f MHz apart: filter rejects %4.1f dB, leakage at the RX port must be below %.1f dBm => %.0f dB of isolation"
          % (df, rej, leak_max_at_rx, iso))
R["iso_200MHz_dB"] = tx_out_dBm - min(pr10 - 10 + lp_reject_dB(200.0), (P["dem_ip1db_dBm"] - 10) - (P["lna_gain_dB"] - P["dsa_il_dB"] - dsa_set + P["gb_gain_dB"]))
print("  a splitter gives 3 dB, a circulator about 20 dB, two patches side by side 30-40 dB: FDD on one antenna does not work in-band;")
print("  separate TX and RX antennas, or time-division with a switch (the protocol is half duplex anyway).")

# ---------------------------------------------------------------------------
section("5. Latency budget (electronics only; add 3.34 ns per metre of air)")
t_hdr = 2.2 * P["hdr_R_ohm"] * P["hdr_C_pF"] * 1e-12 * 1e9        # 10-90 % rise through the header RC, ns
tx = [("FPGA output buffer", 1.5), ("PYNQ header RC %.0f ohm x %.0f pF (10-90 %%)" % (P["hdr_R_ohm"], P["hdr_C_pF"]), t_hdr),
      ("TX resistor DAC node (%.0f ohm, 3 pF)" % Znode, 2.2 * Znode * 3e-12 * 1e9), ("ADL5375 (750 MHz baseband bandwidth)", 0.5),
      ("ADL5611 + lines + SMA", 0.5)]
t_hdr_rx = 2.2 * (P["hdr_R_ohm"] + P["cmp_series_ohm"]) * P["hdr_C_pF"] * 1e-12 * 1e9   # the comparator's own 33 ohm too (KimiK3)
rx = [("SMA + LNA + DSA + 2 x ADL5611", 1.1), ("ADL5380 (390 MHz)", 1.0), ("THS4541 at gain %.0f, %.0f MHz (10-90 %%)" % (G_fda, B_MHz), 0.35 / B_MHz * 1e3),
      ("fast arm to the 50 % crossing (half the rise, net of the above)", -0.35 / B_MHz * 1e3 * 0.5), ("TLV3601", P["cmp_tpd_ns"]),
      ("33 ohm + PYNQ header RC", t_hdr_rx),
      ("Zynq input buffer + register at 400 MHz (worst 1 clock)", 1.0 + 2.5)]
ttx = sum(t for _, t in tx); trx = sum(t for _, t in rx)
for n, t in tx: print("  TX  %-58s %5.1f ns" % (n, t))
for n, t in rx: print("  RX  %-58s %5.1f ns" % (n, t))
print("  total electronics %.1f ns (TX %.1f + RX %.1f); the OOK board's envelope detector path was budgeted at 10-100 ns" % (ttx + trx, ttx, trx))
R["latency_ns"] = ttx + trx
assert ttx + trx < 25
t_icepi = ttx + trx - t_hdr - t_hdr_rx + 2.2 * P["cmp_series_ohm"] * P["hdr_C_pF"] * 1e-12 * 1e9
R["latency_icepi_ns"] = t_icepi
print("  on the Icepi Zero (no header resistors) the same path is %.1f ns" % t_icepi)
t_slow50 = 0.35 / (B_slow_MHz / 1.57) * 1e3 * 0.5
R["slow_t50_ns"] = t_slow50
R["slow_rise_ns"] = 2 * t_slow50
print("  the slow path's decision comes %.0f ns later (its %.1f MHz pole: %.0f ns rise); the symbol must still be there" % (t_slow50, B_slow_MHz / 1.57, 2 * t_slow50))

# ---------------------------------------------------------------------------
section("6. The Costas loop (the RX synthesizer's VCXO is the loop's VCO)")
N = P["pll_fout_MHz"] / P["vcxo_MHz"]
pull_Hz = P["vcxo_pull_ppm"] * 1e-6 * P["pll_fout_MHz"] * 1e6
Ko = 2 * math.pi * 2 * pull_Hz / (P["vcxo_vc_V"][1] - P["vcxo_vc_V"][0])      # rad/s per V at 5.8 GHz
A_bb = vcmp_rms * 1.414                                                        # the arms' DIFFERENTIAL peak at lock
# U110 passes ONE leg of the Q pair (Q_P or Q_N, each V_MID +- half the differential swing) to the
# integrator, which is referenced to V_MID: the detector sees half of A_bb (GPT-5.6Terra's review; the
# budget had used all of it, and the loop ran at 2.05 kHz, zeta 0.48 with the 20 k it chose)
Kd = A_bb / 2.0
fn_Hz = 3000.0
zeta = 0.707
wn = 2 * math.pi * fn_Hz
tau1 = Kd * Ko / wn ** 2
tau2 = 2 * zeta / wn
C_loop = 100e-9
R1 = tau1 / C_loop
R2 = tau2 / C_loop
R.update(loop_N=N, loop_Ko=Ko, loop_Kd=Kd, loop_R1=R1, loop_R2=R2, loop_C=C_loop)
print("PLL multiplies the %.0f MHz VCXO by N = %.0f; pull +-%.0f ppm = +-%.0f kHz at 5.8 GHz over %.1f V: Ko = %.2e rad/s/V"
      % (P["vcxo_MHz"], N, P["vcxo_pull_ppm"], pull_Hz / 1e3, P["vcxo_vc_V"][1] - P["vcxo_vc_V"][0], Ko))
print("Kd = %.2f V/rad at the DSA's regulated level (-20 dBm at the demodulator, kept from 3 m to about 300 m); for fn = %.0f Hz, zeta = %.2f with C = %.0f nF:"
      % (Kd, fn_Hz, zeta, C_loop * 1e9))
print("  R1 = %.1f k (E24 %.1f k), R2 = %.0f ohm (E24 %.0f)" % (R1 / 1e3, e24(R1) / 1e3, R2, e24(R2)))
for dfk in (30.0, 300.0):
    dw = 2 * math.pi * dfk * 1e3
    tp = dw ** 2 / (2 * zeta * wn ** 3)
    print("  pull-in from %.0f kHz off: %.1f ms (the FPGA steps the RX PLL when the VCXO cannot reach)" % (dfk, tp * 1e3))
tcxo_off_Hz = 2 * P["tcxo_ppm"] * 1e-6 * P["pll_fout_MHz"] * 1e6
print("  two TCXO-referenced transmitters differ by at most %.0f kHz; the VCXO reaches +-%.0f kHz" % (tcxo_off_Hz / 1e3, pull_Hz / 1e3))
assert pull_Hz > 3 * tcxo_off_Hz
assert fn_Hz * 10 < 80e3, "Costas loop must be well inside the PLL's loop bandwidth"

# ---------------------------------------------------------------------------
section("7. FDA level shift (ADL5380 outputs sit at %.1f V; THS4541 on 3.3 V accepts inputs to %.1f V, guaranteed)" % (P["dem_out_cm_V"], 3.3 - P["fda_cm_headroom_V"]))
Rg, Rf, Rs = 1000.0, 4000.0, 1000.0            # Rg from the demodulator, Rf feedback, Rs from the summing node to ground (1.2 k until the review: 2.02 V at 3.8 V)
Vocm = 1.65
Vn = (P["dem_out_cm_V"] / Rg + Vocm / Rf) / (1 / Rg + 1 / Rf + 1 / Rs)
gain = Rf / Rg
noise_gain = 1 + Rf / (Rg * Rs / (Rg + Rs))
bw = P["fda_gbw_MHz"] / noise_gain
i_pull_mA = (P["dem_out_cm_V"] - Vn) / Rg * 1e3
R.update(fda_Rg=Rg, fda_Rf=Rf, fda_Rs=Rs, fda_Vn=Vn, fda_bw_MHz=bw)
print("Rg %.0f, Rf %.0f, Rs %.0f: summing nodes at %.2f V (limit %.1f), gain %.0f (%.0f dB), noise gain %.1f -> about %.0f MHz, %.2f mA drawn from each demodulator pin"
      % (Rg, Rf, Rs, Vn, 3.3 - P["fda_cm_headroom_V"], gain, 20 * math.log10(gain), noise_gain, bw, i_pull_mA))
# the ADL5380's own tables disagree on its output common mode with ADJ open: Table 4 ~3.2 V, Table 1 VS - 1.2 V
# (3.8 V at 5.0 V).  Check the worse at the highest +5V_RF the input path can deliver (5.25 V at the plug, less the
# drop at the start-up current: 5.15 V) against the THS4541's guaranteed limit (Grok4.7 / KimiK3)
for vcm, why in ((3.2, "Table 4"), (P["dem_out_cm_V"], "Table 1 at 5.0 V"), (5.15 - 1.2, "Table 1 at the highest +5V_RF, 5.15 V")):
    vn = (vcm / Rg + Vocm / Rf) / (1 / Rg + 1 / Rf + 1 / Rs)
    print("  demodulator common mode %.2f V (%s): summing nodes %.3f V, %.0f mV under the guaranteed %.1f V"
          % (vcm, why, vn, (3.3 - P["fda_cm_headroom_V"] - vn) * 1e3, 3.3 - P["fda_cm_headroom_V"]))
    assert vn < 3.3 - P["fda_cm_headroom_V"], (vcm, vn)
assert abs(bw - B_MHz) < 25, (bw, B_MHz)
assert abs(gain - G_fda) < 1e-9

# ---------------------------------------------------------------------------
section("7b. The slow path: a second THS4541 stage at gain %.0f, a 33 pF pole, its own comparators" % G_slow)
Rg2, Rf2 = 1000.0, G_slow * 1000.0
ng2 = 1 + Rf2 / Rg2                            # inputs already at 1.65 V: no shunts
bw2 = P["fda_gbw_MHz"] / ng2
Rrc, Crc = 1000.0, 33e-12
f_rc = 1 / (2 * math.pi * Rrc * Crc) / 1e6
B_slow_noise = f_rc * 1.57                     # one dominant pole's noise bandwidth
vos_out_mV = (P["fda_vos_mV"] * G_fda + P["fda_vos_mV"]) * G_slow
trim_V = 3.3 / 2 * Rf2 / 100e3
R.update(slow_Rg=Rg2, slow_Rf=Rf2, slow_bw_MHz=bw2, slow_Rrc=Rrc, slow_Crc=Crc, slow_fpole_MHz=f_rc, slow_vos_mV=vos_out_mV, slow_trim_V=trim_V)
print("gain %.0f (Rf %.0f k / Rg %.0f k), noise gain %.0f -> %.0f MHz; then %.0f ohm / %.0f pF = %.1f MHz, noise bandwidth %.1f MHz (budgeted %.1f)"
      % (G_slow, Rf2 / 1e3, Rg2 / 1e3, ng2, bw2, Rrc, Crc * 1e12, f_rc, B_slow_noise, B_slow_MHz))
print("offsets: %.1f mV of THS4541 input offset twice, x%.0f = up to %.0f mV at the slow comparators against +-%.0f mV of signal at the quiet threshold: "
      "trimmed by the second DAC through 100 k (+-%.2f V of reach)" % (P["fda_vos_mV"], G_slow, vos_out_mV, 1000 * vmin_cmp * 10 ** ((noise_slow + 8.4 - floor_slow) / 20.0), trim_V))
assert abs(B_slow_noise - B_slow_MHz) < 1.0, B_slow_noise
assert trim_V > vos_out_mV * 1e-3 * 2, "the trim must reach twice the worst offset"

# ---------------------------------------------------------------------------
section("8. MAX2871 loop filter (3rd order passive, Banerjee), both synthesizers")
Kv = P["pll_kvco_MHz_V"] * 1e6 * 2 * math.pi           # rad/s/V
Kphi = P["pll_icp_mA"] * 1e-3 / (2 * math.pi)          # A/rad
Nd = P["pll_fout_MHz"] / P["pll_pfd_MHz"]
fc = 80e3; pm = math.radians(50.0); gamma = 1.0; T31 = 0.3   # loop bandwidth, phase margin, Banerjee's gamma and T3/T1
wc = 2 * math.pi * fc
# Banerjee 2nd-order equations, then T3 as a fraction of T1
T1 = (1.0 / math.cos(pm) - math.tan(pm)) / (wc * (1 + T31))
T3 = T31 * T1
T2 = gamma / (wc ** 2 * (T1 + T3))
A0 = Kphi * Kv / (wc ** 2 * Nd) * math.sqrt((1 + (wc * T2) ** 2) / ((1 + (wc * T1) ** 2) * (1 + (wc * T3) ** 2)))
C1 = A0 * T1 / T2 * (1 + math.sqrt(1 + T2 / T1 * (T2 / A0 * 0 + 1) * 0))  # placeholder, replaced below
# exact 3rd-order solution (Banerjee, "PLL Performance, Simulation and Design", 4th ed., ch. 22)
A2 = A0 * T1 * T3
A1 = A0 * (T1 + T3)
C1 = A2 / T2 ** 2 * (1 + math.sqrt(1 + T2 / A2 * (T2 * A0 - A1)))
C3 = (-T2 ** 2 * C1 ** 2 + T2 * A1 * C1 - A2 * A0) / (T2 ** 2 * C1 - A2)
C2 = A0 - C1 - C3
R2 = T2 / C2
R3 = A2 / (C1 * C3 * T2)
R.update(pll_C1=C1, pll_C2=C2, pll_C3=C3, pll_R2=R2, pll_R3=R3, pll_fc=fc)
print("N = %.0f, Kvco %.0f MHz/V, Icp %.2f mA, loop bandwidth %.0f kHz, phase margin %.0f deg:" % (Nd, P["pll_kvco_MHz_V"], P["pll_icp_mA"], fc / 1e3, math.degrees(pm)))
print("  C1 %.0f pF (E24 %.0f pF), C2 %.1f nF (E24 %.1f nF), R2 %.0f ohm (E24 %.0f), R3 %.0f ohm (E24 %.0f), C3 %.0f pF (E24 %.0f pF)"
      % (C1 * 1e12, e24(C1) * 1e12, C2 * 1e9, e24(C2) * 1e9, R2, e24(R2), R3, e24(R3), C3 * 1e12, e24(C3) * 1e12))
assert C1 > 0 and C2 > 0 and C3 > 0 and R2 > 0 and R3 > 0
assert fc < P["pll_pfd_MHz"] * 1e6 / 10
pn_inband = -230 + 20 * math.log10(Nd) + 10 * math.log10(P["pll_pfd_MHz"] * 1e6)
print("  in-band phase noise floor about %.0f dBc/Hz (normalised -230 dBc/Hz); %.0f kHz loop lets the %.0f Hz Costas loop through untouched" % (pn_inband, fc / 1e3, fn_Hz))

# ---------------------------------------------------------------------------
section("9. Power and regulator dissipation")
I5 = dict(ADL5380=P["dem_I_mA"], ADL5375=P["mod_I_mA"], ADL5611_x3=3 * P["gb_I_mA"])
I33 = dict(PLL_TX=P["pll_I_mA"], PLL_RX=P["pll_I_mA"], OSC=P["vcxo_I_mA"] + 5, DIG=6 * P["cmp_I_mA"] + 10 + 5 + 2, ANA=4 * P["fda_I_mA"] + P["lna_I_mA"] + 5)
tot = sum(I5.values()) + sum(I33.values())
R["I_total_mA"] = tot
R["rails_mA"] = dict(I33, RF=sum(I5.values()))
print("5 V parts: %s mA; 3.3 V rails (each its own LDO): %s mA; total from 5 V %.0f mA (%.1f W)" % (I5, I33, tot, tot * 5e-3))
for rail, i in I33.items():
    rdrop = 2.2 if rail.startswith("PLL") else 0.0
    vin = 5.0 - rdrop * i * 1e-3
    pd = (vin - 3.3) * i * 1e-3
    print("  LDO %-6s %3.0f mA: %s dissipates %.2f W, +%.0f C in SOT-23-5" % (rail, i, "2.2 ohm then " if rdrop else "", pd, pd * P["ldo_rth_C_W"]))
    assert pd * P["ldo_rth_C_W"] < 70, rail
# the input path at its MAXIMUM resistances (the review: the old note used typical drops from a perfect 5.0 V)
i_rf = sum(I5.values()) * 1e-3
vdrop_in = tot * 1e-3 * (P["ptc_R1max_ohm"] + P["fet_rds_max_ohm"]) + i_rf * P["bead_dcr_max_ohm"]
v_rf_min = P["supply_min_V"] - vdrop_in
R.update(vdrop_in_max_V=vdrop_in, v_rf_min_V=v_rf_min)
print("input path at %.2f A, maxima: PTC %.0f mOhm + AO3401A %.0f mOhm, then the bead %.0f mOhm at %.2f A = %.3f V: +5V_RF >= %.2f V from a %.2f V supply "
      "(the ADL53xx and ADL5611 want 4.75 V); from USB-C's 4.75 V minimum it would be %.2f V: USB-C hosts and power banks must hold %.2f V at the plug"
      % (tot * 1e-3, P["ptc_R1max_ohm"] * 1e3, P["fet_rds_max_ohm"] * 1e3, P["bead_dcr_max_ohm"] * 1e3, i_rf, vdrop_in, v_rf_min, P["supply_min_V"],
         4.75 - vdrop_in, 4.75 + vdrop_in + 0.05))
assert v_rf_min > 4.75 + 0.10, v_rf_min

if "--json" in sys.argv:
    R["parts"] = P
    out = sys.argv[sys.argv.index("--json") + 1]
    json.dump(R, open(out, "w"), indent=1, default=str)
    print("\nwrote", out)
