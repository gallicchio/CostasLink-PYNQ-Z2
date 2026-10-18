"""What is on every wire, as text for the schematic's blue boxes (sch_util.sig) and for the block
diagrams: frequency, level, bandwidth, DC offset.  Everything is read from build/budget.json, which
sim/budget.py writes before the schematic is drawn, so the sheets, the diagrams and the plan quote
one set of numbers.  The bench case is 10 m with 2 dBi whips; where it matters the 300 m panel case
is given too.  VAL maps the budget's resistor and capacitor values to the parts table's keys, so
the sheets draw the values the arithmetic chose.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import parts as PARTS_MOD
B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
P = B["parts"]


def vpp(dbm, R=50.0):
    return 2 * math.sqrt(2) * math.sqrt(10 ** (dbm / 10.0) * 1e-3 * R)


def mv(v):
    return "%.0f mV" % (v * 1e3) if v >= 1e-3 else "%.0f uV" % (v * 1e6)


def lvl(dbm):
    return "%+.1f dBm (%s p-p)" % (dbm, mv(vpp(dbm)))


res_key = PARTS_MOD.nearest_res          # the parts table's key nearest to a sim/budget.py value (budget's "as fitted" too)
cap_key = PARTS_MOD.nearest_cap


VAL = {
    "fda_Rf": res_key(B["fda_Rf"]), "fda_Rg": res_key(B["fda_Rg"]), "fda_Rs": res_key(B["fda_Rs"]),
    "loop_R1": res_key(B["loop_R1"]), "loop_R2": res_key(B["loop_R2"]), "loop_C": cap_key(B["loop_C"], c0g=True),
    "bias_Rt": res_key(B["bias_Rt"]), "bias_Rb": res_key(B["bias_Rb"]),
    "trim_R": res_key(B["trim_R"], tol=1.001),                # the DACs' offset trims into the arms (section 7b)
    "cmp_series": res_key(P["cmp_series_ohm"], tol=1.001),    # every comparator output's source resistor (section 5's latency)
    "slow_Rf": res_key(B["slow_Rf"]), "slow_Rg": res_key(B["slow_Rg"]), "slow_Rrc": res_key(B["slow_Rrc"]),
    "slow_Crc": cap_key(B["slow_Crc"], tol=1.001),
    # the TX ladders (sim/budget.py section 1)
    "dac_Rb": res_key(B["dac_Rb"], tol=1.001), "dac_Rr": res_key(B["dac_Rr"], tol=1.001),
    "dac_RrQ": res_key(B["dac_RrQ"], tol=1.001),               # the Q ladder's reference resistor: its third leg is TRIG IN (Prompt 35)
    # the MAX2871 loop filter (section 8): the nearest stocked values to Banerjee's, and RSET
    "pll_C1": cap_key(B["pll_C1"]), "pll_C2": cap_key(B["pll_C2"], c0g=True), "pll_C3": cap_key(B["pll_C3"]),
    "pll_R2": res_key(B["pll_R2"], tol=1.1), "pll_R3": res_key(B["pll_R3"], tol=1.1), "pll_Rset": res_key(P["pll_rset_ohm"], tol=1.001),
    # the logic monitor taps and the interference detectors (section 8b)
    "tap_R": res_key(B["tap_R"], tol=1.001),
    "det_Rs": res_key(B["det_Rs"], tol=1.001), "det_Cc": cap_key(B["det_Cc"], tol=1.001),
    "det_Coflt": cap_key(B["det_Coflt"], tol=1.001), "det_Cbfin": cap_key(B["det_Cbfin"], tol=1.001),
    "det_Chold": cap_key(B["det_Chold"], tol=1.001), "det_Rbleed": res_key(B["det_Rbleed"], tol=1.001),
    "det_Radc": res_key(B["det_Radc"], tol=1.001), "det_Cadc": cap_key(B["det_Cadc"], tol=1.001),
    "v5_Rt": res_key(B["v5_Rt"], tol=1.001), "v5_Rb": res_key(B["v5_Rb"], tol=1.001), "ntc_Rtop": res_key(B["ntc_Rtop"], tol=1.001),
}

pr10 = B["rx_in_dBm"]
pr300 = B["rx_rows"]["300 m 24 dBi"]
lv = B["dac_levels"]
rails = B["rails_mA"]
RF = "5.8 GHz (%g-%g in spec)" % tuple(P["band_GHz"])
BW_RF = "a CW line; a flip adds +-%.0f MHz skirts" % B["B_MHz"]
sw = B["switch"]
vpk = B["vcmp_rms"] * 1.414                      # the fast arm's peak at the DSA's regulated level
quiet_fast = B["noise_floor_dBm"] + 8.4
quiet_slow = B["noise_floor_slow_dBm"] + 8.4

T = {
    # ---- receiver ---------------------------------------------------------------------------
    "RX_ANT": "%s | %s at 10 m with whips, %s at 300 m with panels | %s | no DC (1.5 pF block) | ABS MAX +1 dBm (the LNA).  With the %s (%.0f dB assumed) ahead, keep ITS input under %+.0f dBm"
              % (RF, lvl(pr10), lvl(pr300), BW_RF, B["lna_module"]["name"], B["lna_module"]["gain_dB"], 1 - B["lna_module"]["gain_dB"]),
    "LNA_OUT": "after the LNA: %s | noise %.1f dBm in %.0f MHz (NF %.1f dB): SNR %.0f dB | DC blocked"
               % (lvl(B["lna_out_dBm"]), B["noise_floor_dBm"], B["B_MHz"], B["nf_chain_dB"], pr10 - B["noise_floor_dBm"]),
    "DSA_OUT": "%s | %s with the DSA at %.2f dB (its range: 0 to %.2f dB; it holds the demodulator at -20 dBm from 3 m to about 300 m) | no DC"
               % (RF, lvl(B["dsa_out_dBm"]), B["dsa_set_dB"], P["dsa_max_dB"]),
    "GB1_OUT": "%s | %s after the first gain block (+%.1f dB) | DC: 5 V bias behind 43 nH, blocked"
               % (RF, lvl(B["gb1_out_dBm"]), P["gb_gain_dB"]),
    "DEM_IN": "%s | %s into the demodulator after the second gain block (IP1dB +%.1f: %.0f dB of headroom) | DC: 5 V bias behind 43 nH, blocked"
              % (RF, lvl(B["dem_in_dBm"]), P["dem_ip1db_dBm"], P["dem_ip1db_dBm"] - B["dem_in_dBm"]),
    "LO_RX": "LO 5.8 GHz = 232 x 25 MHz | 0 dBm differential (%s p-p each side, 27 nH to 3.3 V, 1.5 pF blocks) | moves with VC: +-580 kHz"
             % mv(vpp(0.0) / 2),
    "IQ_DEM": "I and Q, differential pairs | %s rms (%s p-p) at the regulated level | DC-%.0f MHz | common mode %.1f V, 25 ohm per pin | idle: I = +A, Q = 0"
              % (mv(B["vbb_diff_rms"]), mv(B["vbb_diff_rms"] * 2.83), P["dem_bw_MHz"], P["dem_out_cm_V"]),
    "I_ARM": "I_P / I_N, the FAST arm: gain %.0f, %.0f MHz (%.1f ns rise) | +-%s peak at the regulated level | centred 1.65 V | reads down to %.0f dBm at the antenna (the comparator floor; noise-quiet would be %.0f) | the data: sign(I)"
             % (B["G_fda"], B["B_MHz"], 350.0 / B["B_MHz"], mv(vpk), B["floor_fast_dBm"], quiet_fast),
    "Q_ARM": "Q_P / Q_N, the FAST arm: the phase error, 0 at lock, +-%s peak off lock | DC-%.0f MHz | centred 1.65 V | a QPSK symbol puts +-%s on it"
             % (mv(vpk), B["B_MHz"], mv(vpk * 0.707)),
    "CMP_I": "TLV3601 comparator (3 mV hysteresis): CMP_I = sign(I), the BPSK data, the Costas loop's sign, the fast flag: 0 / 3.3 V CMOS, %.1f ns after the input crosses | through 33 ohm (+200 ohm on the PYNQ) | flips with the carrier's 180 deg | %.1f ns jack-to-register on the PYNQ, %.1f on the Icepi | confirmed or vetoed by CMP_I_S %.0f ns later (sheet 6)"
             % (P["cmp_tpd_ns"], B["latency_ns"] - 8.5, B["latency_icepi_ns"] - 4.1, B["slow_t50_ns"]),
    "ERR": "ERR = sign(I) x Q: 0 V (about 1.65 V) at lock, +-%s peak off lock | DC-%.0f MHz before the filter | K_d %.2f V/rad at the regulated level"
           % (mv(vpk), B["B_MHz"], B["loop_Kd"]),
    "VC": "VC: %.1f-%.1f V, 1.65 V = VCXO centre | slow: the %.0f Hz loop | = %.0f kHz/V of LO (x232)"
          % (P["vcxo_vc_V"][0], P["vcxo_vc_V"][1], 3000, B["loop_Ko"] / 2 / math.pi / 1e3),
    "V_MID": "V_MID: 1.65 V DC (10k/10k from 3.3 V, 1 uF): the loop's zero",
    "VC_OFF": "VC_OFF: DC from the DAC, 1.65 V = no offset; +-1 V = -+%.0f kHz of LO (acquisition sweep)" % (B["loop_Ko"] / 2 / math.pi / 1e3),
    "REF_RX": "25 MHz, 3.3 V CMOS square | +-%.0f ppm over %.1f-%.1f V | through 100 nF into REF_IN (0.7 V p-p min)"
              % (P["vcxo_pull_ppm"], P["vcxo_vc_V"][0], P["vcxo_vc_V"][1]),
    "REF_OUT": "REF OUT: 25 MHz, 3.3 V CMOS through 33 ohm | 1.6 V p-p into 50 ohm, 3.3 V open | for the TX sheet's REF IN (transponder)",
    "DAC": "DAC outputs, DC, 0-3.3 V (12 bit, 0.8 mV): VR_I %.2f V, VR_Q %.3f V (the ladders' centres; also the carrier null) | Q_OFF_F (the fast Q arm's offset, +-%.0f mV at its output through %s) | VC_OFF 1.65 V"
           % (B["dac_Vr"], B["dac_VrQ"], B["fast_trim_V"] * 1e3, VAL["trim_R"][2:]),
    "ADC": "ADC inputs: I_P, Q_P, VC, ERR through 10k / 100 nF (160 Hz): averages, 0-3.3 V",
    "RX_MON": "RX MON: %s at 10 m (-20 dB after the gain blocks)" % lvl(B["dem_in_dBm"] - 20),
    # ---- the slow path --------------------------------------------------------------------------
    "I_SLOW": "I_sP / I_sN, the SLOW arm: x%.0f after the fast arm, then %.0f ohm / %.0f pF = %.1f MHz (%.0f ns rise, decides %.0f ns after the fast one) | saturates at +-1.65 V above +-%s at the fast arm: the sign survives | offset up to %.0f mV, trimmed by I_OFF | reads down to %.0f dBm at the antenna (noise-quiet %.0f, floor %.0f)"
              % (B["G_slow"], B["slow_Rrc"], B["slow_Crc"] * 1e12, B["slow_fpole_MHz"], B["slow_rise_ns"], B["slow_t50_ns"], mv(1.65 / B["G_slow"]), B["slow_vos_mV"], quiet_slow, quiet_slow, B["floor_slow_dBm"]),
    "Q_SLOW": "Q_sP / Q_sN, the SLOW arm: x%.0f, %.1f MHz | 0 at lock (plus x%.0f the loop's static error), saturated during a QPSK symbol | window at V_T2 from DAC2 | offset trimmed by Q_OFF"
              % (B["G_slow"], B["slow_fpole_MHz"], B["G_slow"]),
    "CMP_S": "CMP_I_S / CMP_QP_S / CMP_QN_S: 0 / 3.3 V CMOS through 33 ohm | the same decisions %.0f ns after the fast comparators, %.0f dB more sensitive | the gateware confirms or vetoes the fast flag with them"
             % (B["slow_t50_ns"], B["floor_fast_dBm"] - quiet_slow),
    "DAC2": "DAC2 (MCP4728A1, I2C 0x61), DC 0-3.3 V: A = V_T2 (the slow Q window) | B = I_OFF, C = Q_OFF (+-%.2f V at the slow outputs through %s: null the %.0f mV offsets by watching the slow comparators' duty cycle) | D = I_OFF_F (the FAST I arm's offset on sheet 3, +-%.0f mV at its output)"
            % (B["slow_trim_V"], VAL["trim_R"][2:], B["slow_vos_mV"], B["fast_trim_V"] * 1e3),
    # ---- transmitter ------------------------------------------------------------------------
    "TX_BITS": "TX_I1, TX_I0, TX_Q1, TX_Q0: 0 / 3.3 V CMOS, FAST slew, 1.5 ns edge (+4.4 ns through the PYNQ's 200 ohm; none on the Icepi)",
    "TX_NODE": "ladder node: %.2f / %.2f / %.2f V DC for 00 / 01,10 / 11 | %.0f ohm, 3 pF: 1.6 ns | into IBBP (0-1 V allowed)" % (lv[0], lv[1], lv[2], B["dac_Znode"]),
    "TX_BIAS": "IBBN / QBBN: %.3f V DC (%s / %s from 3.3 V, 1 uF; the pins' own 2 x 41 uA included) | the differential drive is then +-%.2f V"
               % (B["bias_VN"], res_key(B["bias_Rt"])[2:], res_key(B["bias_Rb"])[2:], lv[2] - lv[1]),
    "VR": "VR_I %.2f V / VR_Q %.3f V DC from the DAC (0-0.6 V): centres each ladder (Q's reference is %s: its third leg), nulls the carrier" % (B["dac_Vr"], B["dac_VrQ"], VAL["dac_RrQ"][2:]),
    "MOD_OUT": "%s | %s | carrier feedthrough %.1f dBm | no DC (1.5 pF)" % (RF, lvl(B["tx_mod_out_dBm"]), P["mod_carrier_feedthrough_dBm"]),
    "TX_OUT": "%s | %s (P1dB +%.0f) | DC: 5 V bias behind 43 nH, blocked" % (RF, lvl(B["tx_out_dBm"]), P["gb_p1db_dBm"]),
    "TX_ANT": "%s | %s to the antenna, the PA or SW TX | %s | never into RX ANT.  Into the %s (%.0f dB, P1dB +%.0f dBm out) ONLY through a %.0f dB pad: its input must stay under %+.0f dBm"
              % (RF, lvl(B["tx_out_dBm"]), BW_RF, B["pa_module"]["name"], B["pa_module"]["gain_dB"], B["pa_module"]["p1db_dBm"], B["pa_module"]["pad_dB"],
                 B["pa_module"]["p1db_dBm"] - B["pa_module"]["gain_dB"]),
    "TX_MON": "TX MON: %s (-20 dB)" % lvl(B["tx_out_dBm"] - 20),
    "LO_TX": "LO 5.8 GHz = 232 x 25 MHz | 0 dBm differential (27 nH to 3.3 V, 1.5 pF blocks) | +-14.5 kHz from the TCXO's +-%.1f ppm" % P["tcxo_ppm"],
    "REF_TX": "25 MHz +-%.1f ppm, 3.3 V CMOS square | or REF IN / REF OUT by JP201 (10-210 MHz, 0.7 V p-p min)" % P["tcxo_ppm"],
    "TRIG_OUT": "TRIG OUT A / B: 0 / 3.3 V through 33 ohm = about 1.7 V into 50 ohm (the LVC's 32 mA), 2.2 ns | the FPGA marks the symbol sent or decoded",
    "TRIG_IN": "TRIG IN: a 3.3 V logic pulse (1k series; JP202 = 50 ohm; 100k holds it low) | Schmitt-buffered to the FPGA (header 26) AND summed into the Q ladder as a third leg: high = +Q, without the FPGA",
    # ---- switch -------------------------------------------------------------------------------
    "ANT": "%s | out: %+.1f dBm (TX less %.1f dB) | in: whatever arrives, less %.1f dB | ABS MAX +%.0f dBm at the switch (the LNA behind SW RX: +1)"
           % (RF, B["tx_out_dBm"] - sw["il_dB"], sw["il_dB"], sw["il_dB"], sw["p01dB_dBm"]),
    "SW_TX": "SW TX: from TX ANT (%+.1f dBm) or a PA (<= %+.0f dBm without a limiter) | %.0f dB (min) to SW RX: %+.1f dBm leaks into the receiver "
             "while transmitting; a PA over %+.0f dBm wants a limiter ahead of the LNA (+1 dBm abs max)"
             % (B["tx_out_dBm"], sw["tx_max_dBm"], sw["iso_dB"], B["tx_out_dBm"] - sw["iso_dB"], sw["tx_max_dBm"]),
    "SW_RX": "SW RX: to RX ANT or the LNA | the rest state (A high, B low)",
    "TR": "TR_A / TR_B: 0 / 3.3 V from the FPGA | %.0f ns edge-to-RF, %.0f ns rise" % (sw["t_on_ns"], sw["t_rise_ns"]),
    # ---- power -------------------------------------------------------------------------------
    "5V_IN": "5 V in: %.0f mA total (%.1f W); USB-C or the header, each through a 2 A PTC and an ideal diode" % (B["I_total_mA"], B["I_total_mA"] * 5e-3),
    "5V_RF": "+5V_RF: 5 V through the ferrite, %.0f mA (ADL5380 %.0f, ADL5375 %.0f, 3 x ADL5611 %.0f); the PTC, FET and bead drop up to %.0f mV "
             "at their maxima, so %.2f V at the plug leaves %.2f V (the ADL53xx and ADL5611 want 4.75): a bench supply at 5.1-5.25 V, not a weak USB port"
             % (rails["RF"], P["dem_I_mA"], P["mod_I_mA"], 3 * P["gb_I_mA"], B["vdrop_in_max_V"] * 1e3, P["supply_min_V"], B["v_rf_min_V"]),
}
for rail, key in (("PLL_TX", "+3V3_PLL_TX"), ("PLL_RX", "+3V3_PLL_RX"), ("ANA", "+3V3_ANA"), ("DIG", "+3V3_DIG"), ("OSC", "+3V3_OSC")):
    T[key] = "%s: 3.3 V, %.0f mA%s" % (key, rails[rail], "; 2.2 ohm ahead shares the heat" if rail.startswith("PLL") else "")

# What every connector takes or gives, keyed by the connector's value (the name the schematic and the
# silkscreen both print): (the short line printed beside it on the board, the sentence the schematic
# puts beside it).  CLAUDE_PCB.md section 4: limits at every connector; section 6: on the silkscreen.
_pa = B["pa_module"]
TAP_R = VAL["tap_R"][2:].replace("R", " ohm")
TAP_DIV = "/%.0f into 50 ohm (0 / %.2f V)" % ((B["tap_R"] + 50) / 50, B["tap_V50"])
TAP_SHORT = "0-%.1f V/50R" % B["tap_V50"]
LIMITS = {
    "RX ANT": ("in: +1 dBm MAX", "RX ANT, 50 ohm: ABS MAX +1 dBm (the SKY65404's limit).  Expected %s at 10 m with whips, %s at 300 m with panels."
               % (lvl(pr10), lvl(pr300))),
    "TX ANT": ("out: +10 dBm", "TX ANT, 50 ohm: %s out.  The PA module takes at most %+.0f dBm: use the %.0f dB pad.  Never into RX ANT."
               % (lvl(B["tx_out_dBm"]), _pa["p1db_dBm"] - _pa["gain_dB"], _pa["pad_dB"])),
    # the board says "ANT / TX+RX" (Prompt 35; the +27 dBm MAX did not fit between SW TX and ANT: it is SW TX's +25 dBm MAX that binds)
    "ANT": ("TX+RX", "ANT: the one antenna, transmit and receive in turn.  ABS MAX +%.0f dBm through the switch; what comes in reaches SW RX less %.1f dB."
            % (sw["p01dB_dBm"], sw["il_dB"])),
    "SW TX": ("%+.0f dBm MAX" % sw["tx_max_dBm"], "SW TX: from TX ANT (%s) or a PA up to %+.0f dBm: %.0f dB (min) less of it reaches SW RX, "
              "3 dB under the LNA's +1 dBm abs max.  More wants a limiter ahead of the LNA."
              % (lvl(B["tx_out_dBm"]), sw["tx_max_dBm"], sw["iso_dB"])),
    "SW RX": ("to RX ANT", "SW RX: the received signal, to RX ANT (or the LNA module).  Rest state (A high, B low)."),
    "REF IN": ("10-210 MHz, 0.7-3.3 Vpp", "REF IN: 10-210 MHz, 0.7 V p-p min, 3.3 V p-p max (AC-coupled into the MAX2871); fit 49.9 ohm for a 50 ohm source; JP201 to REF IN."),
    "REF OUT": ("25 MHz, 1.6 Vpp/50R", "REF OUT: 25 MHz square, 3.3 V CMOS through 33 ohm: 1.6 V p-p into 50 ohm, 3.3 V open."),
    "RX MON": ("%+.0f dBm, 50R" % (B["dem_in_dBm"] - 20), "RX MON: -20 dB of what enters the demodulator, %s at 10 m; 50 ohm." % lvl(B["dem_in_dBm"] - 20)),
    "TX MON": ("%+.0f dBm, 50R" % (B["tx_out_dBm"] - 20), "TX MON: -20 dB of the transmitter's output: %s; 50 ohm." % lvl(B["tx_out_dBm"] - 20)),
    "LO RX MON": ("0 dBm, 50R", "LO RX MON: the RX synthesizer's second output (RFOUTB), about 0 dBm at 5.8 GHz when enabled in software; 50 ohm."),
    "LO TX MON": ("0 dBm, 50R", "LO TX MON: the TX synthesizer's second output (RFOUTB), about 0 dBm at 5.8 GHz when enabled in software; 50 ohm."),
    "I MON": ("1.65V +-%.0fmV 1k" % (vpk * 1e3), "I MON: the fast I arm's + output through 1k: 1.65 V +-%s peak at the regulated level, %.0f MHz.  A high-impedance probe; a 50 ohm input reads it /21." % (mv(vpk), B["B_MHz"])),
    "Q MON": ("1.65V +-%.0fmV 1k" % (vpk * 1e3), "Q MON: the fast Q arm's + output through 1k: 1.65 V, 0 at lock, +-%s off lock or during a QPSK symbol." % mv(vpk)),
    "I SLOW MON": ("0-3.3 V, 1k", "I SLOW MON: the slow I stage's + output, ahead of its %.1f MHz pole, through 1k: 1.65 V +-1.65 V (x%.0f, saturates), "
                   "the stage's own %.0f MHz.  A 50 ohm scope here does not move the comparator." % (B["slow_fpole_MHz"], B["G_slow"], B["slow_bw_MHz"])),
    "Q SLOW MON": ("0-3.3 V, 1k", "Q SLOW MON: the slow Q stage's + output, ahead of its pole, through 1k: 1.65 V, 0 at lock, saturated during a QPSK symbol."),
    "ERR MON": ("1.65 V +-%.0f mV, 1k" % (vpk * 1e3), "ERR MON: the loop error sign(I) x Q through 1k: 1.65 V at lock, +-%s off lock." % mv(vpk)),
    "VC MON": ("%.1f-%.1f V, 1k" % (P["vcxo_vc_V"][0], P["vcxo_vc_V"][1]), "VC MON: the VCXO's control voltage through 1k: %.1f-%.1f V, 1.65 V at the VCXO's centre." % (P["vcxo_vc_V"][0], P["vcxo_vc_V"][1])),
    "CMP I MON": (TAP_SHORT, "CMP I MON: the fast comparator's output through %s: %s, the data" % (TAP_R, TAP_DIV) + " as it goes to the FPGA."),
    # the board says "TRIG A" with "OUT" on a small line above the level (Prompt 35: "TRIG OUT A" does not fit before the DSA)
    "TRIG A": ("OUT\n3.3 V, 1.7 V/50R", "TRIG A (an output): 0 / 3.3 V through 33 ohm (about 1.7 V into 50 ohm: the LVC's 32 mA), 2.2 ns: the FPGA marks the symbol it sent."),
    "TRIG B": ("OUT\n3.3 V, 1.7 V/50R", "TRIG B (an output): 0 / 3.3 V through 33 ohm (about 1.7 V into 50 ohm: the LVC's 32 mA), 2.2 ns: the FPGA marks the symbol it decoded."),
    # Prompt 35: the test pads an instrument cannot hold a probe on became jacks (the pads for a meter stay on the rails)
    "LD RX": (TAP_SHORT, "LD RX: the RX synthesizer's lock detect (3.3 V CMOS, high = locked) through %s, %s." % (TAP_R, TAP_DIV)),
    "LD TX": (TAP_SHORT, "LD TX: the TX synthesizer's lock detect (3.3 V CMOS, high = locked) through %s, %s." % (TAP_R, TAP_DIV)),
    "TR A": ("3.3 V hi-Z, 35 mV/50R", "TR A: the switch's A control as the FPGA drives it (0 / 3.3 V; high = receive) through 4.7 k: the full swing on a "
             "high-impedance probe, 35 mV into 50 ohm (453 ohm into 50 ohm would pull TR_A, behind the PYNQ's 200 ohm, under the switch's 3 V)."),
    "LOG Q": ("0.4-2.5 V, 1k", "LOG Q: the AD8310's log output (24 mV/dB of the link band on the Q arm, 0.4-2.5 V) through 1k: WiFi's frames on a scope."),
    "TRIG IN": ("in: 5.5 V MAX", "TRIG IN: a 3.3 V logic pulse into a Schmitt buffer through 1k; 5.5 V MAX, never negative; JP202 fitted = 50 ohm termination.  "
                "It also steps the transmitter to +Q by itself (the Q ladder's third leg): a detector can key the link without the FPGA."),
    "IP MON": (TAP_SHORT, "IP MON: the I window's + comparator through %s, %s" % (TAP_R, TAP_DIV) + ": for the scope, beside its line to the FPGA."),
    "IN MON": (TAP_SHORT, "IN MON: the I window's - comparator through %s, %s" % (TAP_R, TAP_DIV) + ": for the scope, beside its line to the FPGA."),
    "QP MON": (TAP_SHORT, "QP MON: the Q window's + comparator through %s, %s" % (TAP_R, TAP_DIV) + ": for the scope, beside its line to the FPGA."),
    "QN MON": (TAP_SHORT, "QN MON: the Q window's - comparator through %s, %s" % (TAP_R, TAP_DIV) + ": for the scope, beside its line to the FPGA."),
    "TRIG IN MON": (TAP_SHORT, "TRIG IN MON: the Schmitt buffer's output through %s, %s" % (TAP_R, TAP_DIV) + ": the trigger edge as the FPGA sees it."),
    "5V_IN": ("DC, 1k", "5V_IN (U.FL): the 5 V input after the fuse and the ideal diode, through 1k: a meter or a logger (a 50 ohm input reads it /21)."),
    "5V_RF": ("DC, 1k", "5V_RF (U.FL): the RF chips' 5 V after the bead, through 1k: 4.75 V minimum under load."),
    "3V3_PLL_TX": ("DC, 1k", "3V3_PLL_TX (U.FL): the TX synthesizer's rail through 1k."),
    "3V3_PLL_RX": ("DC, 1k", "3V3_PLL_RX (U.FL): the RX synthesizer's rail through 1k."),
    "3V3_ANA": ("DC, 1k", "3V3_ANA (U.FL): the arms', the loop's and the LNA's rail through 1k."),
    "3V3_DIG": ("DC, 1k", "3V3_DIG (U.FL): the comparators', switches', DACs' and ADCs' rail through 1k."),
    "3V3_OSC": ("DC, 1k", "3V3_OSC (U.FL): the oscillators' rail through 1k (its noise is FM on both carriers: a spectrum analyser here)."),
    "USB-C 5V": ("5 V, 1.5 A", "USB-C: 5 V only (CC pulled down: any USB-C supply gives 5 V), 1.5 A at most, through a 2 A PTC and an ideal diode."),
    "TR": ("TR A / TR B / GND: 3.3 V logic", "J303: TR_A (from the FPGA, pulled up on the PYNQ) and TR_B (= not TR_A, made on the board), 0 / 3.3 V, and ground: for an external switch module."),
}

LEGEND = ("Blue boxes: what is on the wire beside them (frequency | level | bandwidth | DC), computed by sim/budget.py for the "
          "10 m bench link with 2 dBi whips (the DSA then at %.2f dB, holding the demodulator at -20 dBm); the same numbers as docs/images/block_*.svg." % B["dsa_set_dB"])

FAST_ARM_NOTE = ("THS4541, fully differential amplifier (a differential pair in, a differential pair out about VOCM), one per arm.  The FAST arms: gain %.0f (Rf %s / Rg %s), on 3.3 V.  The %s shunts hold the summing nodes at %.1f V "
                 "(the demodulator's outputs sit at up to %.1f V; the amplifier's inputs may reach 2.0 V).  Noise gain %.1f: %.0f MHz, %.1f ns rise."
                 % (B["G_fda"], VAL["fda_Rf"][2:], VAL["fda_Rg"][2:], VAL["fda_Rs"][2:], B["fda_Vn"], P["dem_out_cm_V"],
                    1 + B["fda_Rf"] / (B["fda_Rg"] * B["fda_Rs"] / (B["fda_Rg"] + B["fda_Rs"])), B["fda_bw_MHz"], 350.0 / B["fda_bw_MHz"]))
SLOW_ARM_NOTE = ("THS4541, fully differential amplifier, the SLOW stage: gain %.0f (Rf %s / Rg %s), inputs already at 1.65 V so no shunts; noise gain %.0f: %.0f MHz, then the "
                 "%s / %s pole at %.1f MHz.  The 100 k from the DAC trims the offset (sim/budget.py 7b)."
                 % (B["G_slow"], VAL["slow_Rf"][2:], VAL["slow_Rg"][2:], 1 + B["slow_Rf"] / B["slow_Rg"], B["slow_bw_MHz"],
                    VAL["slow_Rrc"][2:], VAL["slow_Crc"][2:], B["slow_fpole_MHz"]))


def txt(key):
    return T[key]


if __name__ == "__main__":
    for k, v in VAL.items():
        print("%-9s %s" % (k, v))
    for k, v in T.items():
        print("%-9s %s" % (k, v))
