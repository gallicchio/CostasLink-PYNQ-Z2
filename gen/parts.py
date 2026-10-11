"""Every part on the board, in one place.

The schematic takes symbols, footprints, values and LCSC codes from here; the library
(gen/library.py) is built from the symbols and footprints named here; the BOM, the CPL and the
checks read it.  A part's LCSC code must name exactly the part described: the release compares
each code's JLCPCB description with `match` (every word must appear) before it writes anything
(CLAUDE_PCB.md section 3).

Fields:
  sym      symbol in the project library (CostasLink:...)
  fp       footprint in the project library
  fp_src   where gen/library.py gets the footprint: "stock:<KiCad lib>", "lcsc:<code>"
           (JLCPCB's own land pattern, via easyeda2kicad), "gen" (gen/footprints.py)
  lcsc     LCSC/JLCPCB code; None for a CONSIGNED part (see CONSIGN) or a part JLCPCB does not place
  mpn      manufacturer part number
  value    what the schematic and silkscreen print
  match    words JLCPCB's description of `lcsc` must contain
  note     why this part (shown in the BOM); the rejected alternatives are in PLAN.md section 4

Stock and prices were queried 2026-10-09 00:36-01:11 PDT (tools/jlc_cache.json keeps each answer
with its time; build/stock_probe*.txt are the printouts).  PLAN.md section 4 has the table.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board_info import LIB

STOCK = "stock:"


def P(sym, fp, fp_src, lcsc, mpn, value, match, note="", consign=None):
    d = dict(sym=LIB + ":" + sym, fp=LIB + ":" + fp, fp_src=fp_src, lcsc=lcsc, mpn=mpn,
             value=value, match=match, note=note)
    if consign:
        d["consign"] = consign
    return d


# Consigned parts: not placed from JLCPCB's stock but bought at a distributor and shipped to
# JLCPCB (Jason, Prompt 1).  `consign` names the distributor part numbers; stock seen 2026-10-09.
CONSIGN_NOTE = "CONSIGNED: bought at Digi-Key/Mouser, shipped to JLCPCB (PLAN.md section 4)"

PARTS = {
    # --- the RF chips ------------------------------------------------------------------
    "ADL5380": P("ADL5380", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", STOCK + "Package_DFN_QFN", None,
                 "ADL5380ACPZ-R7", "ADL5380",
                 ["ADL5380"], "IQ demodulator 0.4-6 GHz, 390 MHz baseband, DC-coupled outputs: the Costas loop's phase detector. " + CONSIGN_NOTE,
                 consign=dict(digikey="ADL5380ACPZ-R7CT-ND", mouser="584-ADL5380ACPZ-R7", lcsc="C579152",
                              seen="Digi-Key 4,527 in stock at $17.96 (1-9), Jason 2026-10-09")),
    "ADL5375": P("ADL5375", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", STOCK + "Package_DFN_QFN", None,
                 "ADL5375-05ACPZ-R7", "ADL5375-05",
                 ["ADL5375-05"], "IQ modulator 0.4-6 GHz, 0.5 V baseband bias: the transmitter. " + CONSIGN_NOTE,
                 consign=dict(digikey="ADL5375-05ACPZ-R7CT-ND", mouser="584-ADL5375-05ACPZR7", lcsc="C579150")),
    "BALUN": P("Balun_5400", "Balun_Johanson_5400BL15B050", "gen", None, "5400BL15B0050001E", "5400BL15B050",
               ["5400BL15B050"], "1:1 balun 4.9-5.9 GHz at the ADL5380's RF input (the datasheet's 5.8 GHz circuit). " + CONSIGN_NOTE,
               consign=dict(digikey="712-1363-1-ND", mouser="609-5400BL15B0050001E", lcsc="C2837312", legacy="5400BL15B050E")),
    "MAX2871": P("MAX2871", "QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm", STOCK + "Package_DFN_QFN", "C7458627",
                 "MAX2871ETJ+T", "MAX2871", ["MAX2871ETJ+T"],
                 "23.5 MHz-6 GHz fractional-N synthesizer with VCO, 3.3 V, SPI (ADF4351 register map); one for the TX LO, one for the RX LO"),
    "SKY65404": P("SKY65404-31", "SKY65404-31_QFN-6_1.5x1.5mm", "gen", "C210262", "SKY65404-31", "SKY65404-31",
                  ["SKY65404-31"], "5 GHz LNA: 1.0 dB NF, 13 dB, 10 mA; absolute maximum input +1 dBm"),
    "PE43711": P("PE43711", "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm", STOCK + "Package_DFN_QFN", "C470929", "PE43711B-Z", "PE43711",
                 ["PE43711B-Z"], "9 kHz-6 GHz digital step attenuator, 0-31.75 dB in 0.25 dB steps, serial mode on the shared SPI"),
    "ADL5611": P("ADL5611", "SOT-89-3", STOCK + "Package_TO_SOT_SMD", "C208262", "ADL5611ARKZ-R7", "ADL5611",
                 ["ADL5611ARKZ-R7"], "gain block, 14.3 dB at 5.8 GHz (22 dB at 1 GHz), 5 V through a 43 nH choke; one in the RX, one in the TX"),
    # --- baseband and the loop -----------------------------------------------------------
    "THS4541": P("THS4541", "VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm", STOCK + "Package_DFN_QFN", "C2058382", "THS4541IRGTT", "THS4541",
                 ["THS4541IRGTT"], "850 MHz fully differential amplifier on 3.3 V: the I and Q fast arms at gain 4, the slow stages at gain 20"),
    "TLV3601": P("TLV3601", "SOT-353_SC-70-5", STOCK + "Package_TO_SOT_SMD", "C2974371", "TLV3601DCKR", "TLV3601",
                 ["TLV3601DCKR"], "2.5 ns comparator, rail-to-rail inputs, push-pull 3.3 V output straight to the FPGA"),
    "LVC1G3157": P("SN74LVC1G3157", "SOT-363_SC-70-6", STOCK + "Package_TO_SOT_SMD", "C38663", "SN74LVC1G3157DCKR", "74LVC1G3157",
                   ["SN74LVC1G3157DCKR"], "300 MHz analog SPDT: sign(I) selects +Q or -Q = the Costas multiplier"),
    "TS5A3159": P("TS5A3159DCK", "SOT-363_SC-70-6", STOCK + "Package_TO_SOT_SMD", "C46388", "TS5A3159DCKR", "TS5A3159",
                  ["TS5A3159DCKR"], "1 ohm analog switch: LOOP_HOLD opens the integrator's input"),
    "OPA2388": P("OPA2388", "VSSOP-8_3x3mm_P0.65mm", STOCK + "Package_SO", "C2059281", "OPA2388IDGKR", "OPA2388",
                 ["OPA2388IDGKR"], "zero-drift dual op amp, rail-to-rail in and out on 2.5-5.5 V: the PI loop filter and the VC summing stage "
                 "(the OPA2187 first chosen wants 4.5 V and its inputs stop 2 V below the rail: Response 9's review)"),
    "2N7002": P("2N7002", "SOT-23", STOCK + "Package_TO_SOT_SMD", "C8545", "2N7002", "2N7002",
                ["2N7002", "N-Channel"], "N-MOSFET: VBUS pulls the USB ideal diode's gate down, so USB wins over the header (Basic)"),
    "MCP4728": P("MCP4728", "MSOP-10_3x3mm_P0.5mm", STOCK + "Package_SO", "C478093", "MCP4728T-E/UN", "MCP4728",
                 ["MCP4728T-E/UN"], "4-channel 12-bit I2C DAC: TX ladder references Vr_I and Vr_Q, the fast Q arm's offset trim, the VC offset"),
    # Response 14 (the measurement package, Jason: "If it would unlock interesting tests, I don't mind a
    # few 2-10% price increases"): the four window comparators get their own 16-bit thresholds and an
    # adjustable hysteresis; TR_B is made on the board so its header pin can carry a comparator.
    "TLV3603": P("TLV3603", "SOT-363_SC-70-6", STOCK + "Package_TO_SOT_SMD", "C5213955", "TLV3603DCKR", "TLV3603",
                 ["TLV3603DCKR"], "the window comparators: the TLV3601 with LE/HYS (high 0 mV, floating 3 mV, 150k to VEE 30 mV, "
                 "56k 60 mV, low latches); JLCPCB had 16 on 2026-10-10: consign from Digi-Key if short"),
    "AD5696R": P("AD5696R", "TSSOP-16_4.4x5mm_P0.65mm", STOCK + "Package_SO", "C650158", "AD5696RARUZ", "AD5696R",
                 ["AD5696RARUZ"], "16-bit quad I2C DAC, internal 2.5 V reference, address 0x0C: the window thresholds "
                 "(0.038 mV steps against 2.9 mV of noise in the lab); A grade: the threshold servo absorbs INL and drift"),
    "LVC1G04": P("74LVC1G04", "SOT-353_SC-70-5", STOCK + "Package_TO_SOT_SMD", "C8207", "SN74LVC1G04DCKR", "74LVC1G04",
                 ["SN74LVC1G04DCKR"], "TR_B made from TR_A on the board (frees header pin 28)"),
    "ADS1115": P("ADS1115IDGS", "TSSOP-10_3x3mm_P0.5mm", STOCK + "Package_SO", "C37593", "ADS1115IDGSR", "ADS1115",
                 ["ADS1115IDGSR"], "4-channel 16-bit I2C ADC: I and Q averages, VC, the loop error (lock detection in software)"),
    # --- oscillators -----------------------------------------------------------------------
    "VCXO": P("VCXO_3225", "Crystal_SMD_3225-4Pin_3.2x2.5mm", STOCK + "Crystal", "C5179998", "SX3V25.000B20100F30TNN", "VCXO 25MHz",
              ["SX3V25.000B20100F30TNN"], "25 MHz VCXO, pull +-100 ppm over 0.3-3.0 V, 15 kHz modulation bandwidth: the Costas loop's VCO (RX reference)"),
    "TCXO": P("TCXO_3225", "Crystal_SMD_3225-4Pin_3.2x2.5mm", STOCK + "Crystal", "C5119013", "TC32H4-25.000-33GNDTNL", "TCXO 25MHz",
              ["TC32H4-25.000-33GNDTNL"], "25 MHz TCXO +-2.5 ppm, LVCMOS out: the TX reference (same footprint as the VCXO)"),
    # --- logic and glue ---------------------------------------------------------------------
    "LVC2G34": P("74LVC2G34", "SOT-363_SC-70-6", STOCK + "Package_TO_SOT_SMD", "C14461", "SN74LVC2G34DCKR", "74LVC2G34",
                 ["SN74LVC2G34DCKR"], "dual buffer: TRIG A and TRIG B to their SMAs"),
    "LVC1G17": P("74LVC1G17", "SOT-353_SC-70-5", STOCK + "Package_TO_SOT_SMD", "C10425", "SN74LVC1G17DCKR", "74LVC1G17",
                 ["SN74LVC1G17DCKR"], "Schmitt buffer on TRIG IN; the REF OUT buffer on the VCXO"),
    "MCP4728A1": P("MCP4728", "MSOP-10_3x3mm_P0.5mm", STOCK + "Package_SO", "C627342", "MCP4728A1T-E/UN", "MCP4728A1 0x61",
                   ["MCP4728A1T-E/UN"], "the slow path's DAC at the preset address 0x61: V_T2 (its Q window), I_OFF and Q_OFF (offset trims)"),
    # --- the antenna switch (its own block with three SMAs; PLAN.md section 4) ----------------
    "HMC536": P("HMC536MS8G", "MSOP-8-1EP_3x3mm_P0.65mm_EP1.73x1.85mm", STOCK + "Package_SO", "C17271830", "HMC536MS8G", "HMC536",
                ["HMC536MS8G"], "DC-6 GHz GaAs T/R switch: 15 ns rise, 30 ns on/off, 27 dB isolation, +29 dBm, 0/3.3 V control "
                "straight from the FPGA; MSOP-8, hand-solderable.  JLCPCB had 5 on 2026-10-09; Digi-Key none until 2027-01 "
                "(1127-1051-1-ND).  The 10 ns HMC427A costs $62-75 and needs 5 V complementary logic (PLAN.md section 4)"),
    # --- power --------------------------------------------------------------------------------
    "TPS7A2033": P("TPS7A20xxxDBV", "SOT-23-5", STOCK + "Package_TO_SOT_SMD", "C2862740", "TPS7A2033PDBVR", "TPS7A2033",
                   ["TPS7A2033PDBVR"], "3.3 V 300 mA LDO, 10 uVrms: one each for PLL TX, PLL RX, analog and digital"),
    "LP5907": P("LP5907MFX-3.3", "SOT-23-5", STOCK + "Package_TO_SOT_SMD", "C23380874", "LP5907MFX-3.3", "LP5907 3.3V",
                ["LP5907MFX-3.3"], "3.3 V 250 mA LDO, 6.5 uVrms: the oscillators' rail"),
    "AO3401A": P("AO3401A", "SOT-23", STOCK + "Package_TO_SOT_SMD", "C15127", "AO3401A", "AO3401A",
                 ["AO3401A", "P-Channel"], "P-MOSFET ideal diode on each 5 V input (Basic)"),
    "PTC2A": P("Polyfuse", "Fuse_1812_4532Metric", STOCK + "Fuse", "C210837", "MF-MSMF200-2", "2A PTC",
               ["MF-MSMF200-2"], "resettable fuse, holds 2 A, trips at 4 A, on each 5 V input"),
    "TVS5V": P("D_TVS", "D_SMA", STOCK + "Diode_SMD", "C113952", "SMAJ5.0A", "SMAJ5.0A",
               ["SMAJ5.0A"], "5 V TVS on the input rail"),
    "FB_2A": P("Ferrite_Bead", "L_0805_2012Metric", STOCK + "Inductor_SMD", "C85840", "BLM21PG221SN1D", "220R@100MHz 2A",
               ["BLM21PG221SN1D"], "ferrite bead feeding +5V_RF"),
    "LED_G": P("LED", "LED_0603_1608Metric", STOCK + "LED_SMD", "C2286", "KT-0603R", "LED",
               ["KT-0603R"], "rail LED (Basic)"),
    # --- connectors --------------------------------------------------------------------------
    "USBC": P("USB_C_Receptacle_USB2.0_16P", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", STOCK + "Connector_USB", "C165948",
              "TYPE-C-31-M-12", "USB-C 5V", ["TYPE-C-31-M-12"], "5 V in; built on three boards, CPL datum known"),
    "SMA": P("Conn_Coaxial", "SMA_BWSMA-KWE-Z001", "gen", "C496551", "BWSMA-KWE-Z001", "SMA",
             ["BWSMA-KWE-Z001"], "right-angle through-hole SMA (the ECP5 board's part; +90 CPL correction known)"),
    "UFL": P("Conn_Coaxial", "U.FL_Hirose_U.FL-R-SMT-1_Vertical", STOCK + "Connector_Coaxial", "C88374", "U.FL-R-SMT-1(80)", "U.FL",
             ["U.FL-R-SMT-1(80)"], "monitor tap (the 5.8 GHz couplers' and the tight ones; 30 matings)"),
    "MMCX": P("Conn_Coaxial", "MMCX_BWMMCX-KE_Vertical", "gen", "C5137198", "BWMMCX-KE", "MMCX",
              ["BWMMCX-KE"], "vertical through-hole MMCX, 500 matings: the baseband monitors with room round them (Response 10)"),
    "RPI_SOCKET": P("RPi_Header_40", "RPi_Socket_2x20_P2.54mm_Underside", "gen", "C2977589", "2.54-2*20", "PYNQ-Z2 RPi header",
                    ["2x20P", "2.54mm"], "2x20 socket, 8.5 mm, on the underside (the GPSDO board's part), fitted by JLCPCB"),
    "HDR1x2": P("Conn_01x02", "PinHeader_1x02_P2.54mm_Vertical", STOCK + "Connector_PinHeader_2.54mm", "C492401", "PZ254V-11-02P", "JP",
                ["PZ254V-11-02P"], "2-pin jumper, exact length"),
    "HDR1x3": P("Conn_01x03", "PinHeader_1x03_P2.54mm_Vertical", STOCK + "Connector_PinHeader_2.54mm", "C2937625", "PZ254V-11-03P", "JP",
                ["PZ254V-11-03P"], "3-pin selector, exact length"),
    "HDR1x6": P("Conn_01x06", "PinHeader_1x06_P2.54mm_Vertical", STOCK + "Connector_PinHeader_2.54mm", "C492405", "PZ254V-11-06P", "SPARE",
                ["PZ254V-11-06P"], "(unused since the slow path took the spares; J303 is 1x3)"),
    "TP": P("TestPoint", "TestPoint_Pad_D1.5mm", STOCK + "TestPoint", None, "", "TP", [], "a test pad: not a part"),
    "HOLE": P("MountingHole", "MountingHole_3.2mm_M3_DIN965", STOCK + "MountingHole", None, "", "M3", [], "mounting hole: not a part"),
    "HOLE_SLOT": P("MountingHole", "MountingHole_Slot_3.2x5.2mm_M3", "gen", None, "", "M3 slot", [], "the slot onto the PYNQ-Z2's own standoff: not a part"),
    "COUPLER": P("Coupler_20dB", "Coupler_20dB_5.8GHz_CPWG", "gen", None, "", "-20 dB", [],
                 "coupled-line coupler drawn in copper (sim/rf_lines.py: a quarter wave at 5.8 GHz); a net tie, not a part"),
    "PWR_FLAG": dict(sym=LIB + ":PWR_FLAG", fp="", fp_src=None, lcsc=None, mpn="", value="PWR_FLAG", match=[], note=""),
    # --- RF inductors ---------------------------------------------------------------------------
    "L27N": P("L", "L_0402_1005Metric", STOCK + "Inductor_SMD", "C882469", "LQW15AN27NG80D", "27nH",
              ["LQW15AN27NG80D"], "MAX2871 output pull-ups (the datasheet's value)"),
    "L43N": P("L", "L_0603_1608Metric", STOCK + "Inductor_SMD", "C113126", "LQW18AN43NG00D", "43nH",
              ["LQW18AN43NG00D"], "ADL5611 bias choke (datasheet Table 6, 500 MHz-6 GHz)"),
    "L0N6": P("L", "L_0402_1005Metric", STOCK + "Inductor_SMD", "C95042", "MLG1005S0N6CT000", "0.6nH",
              ["MLG1005S0N6CT000"], "SKY65404 supply inductor (Skyworks' circuit)"),
}

# Passives: value -> (LCSC code, MPN, package, match words).  0402 unless the value says otherwise.
# C0G where the value sets a frequency or sits in the RF path (CLAUDE_PCB.md section 12).
CAPS = {
    "0.5pF": ("C285052", "0402CG0R5B500NT", "C_0402_1005Metric", ["0.5pF", "0402", "C0G"], "SKY65404 input match"),
    "1.5pF": ("C1552", "0402CG1R5C500NT", "C_0402_1005Metric", ["1.5pF", "0402", "C0G"], "5.8 GHz DC block: series-resonant at 6.1 GHz with its 0.45 nH"),
    "10pF": ("C32949", "CL05C100JB5NNNC", "C_0402_1005Metric", ["10pF", "0402", "C0G"], ""),
    "33pF": ("C1562", "0402CG330J500NT", "C_0402_1005Metric", ["33pF", "0402", "C0G"], ""),
    "68pF": ("C14441", "CL05C680JB5NNNC", "C_0402_1005Metric", ["68pF", "0402", "C0G"], "ADL5611 bypass"),
    "100pF": ("C1546", "0402CG101J500NT", "C_0402_1005Metric", ["100pF", "0402", "C0G"], ""),
    "160pF": ("C2188753", "GCM1555C1H161JA16D", "C_0402_1005Metric", ["160pF", "0402"], "PLL loop filter C3 (C0G)"),
    "390pF": ("C282239", "CC0402JRNPO9BN391", "C_0402_1005Metric", ["390pF", "0402", "NP0"], "PLL loop filter C1"),
    "1nF": ("C1523", "0402B102K500NT", "C_0402_1005Metric", ["1nF", "0402"], ""),
    "6.8nF C0G": ("C162241", "GRM1885C1H682JA01D", "C_0603_1608Metric", ["6.8nF", "0603", "C0G"], "PLL loop filter C2"),
    "10nF": ("C15195", "CL05B103KB5NNNC", "C_0402_1005Metric", ["10nF", "0402"], ""),
    "100nF": ("C1525", "CL05B104KO5NNNC", "C_0402_1005Metric", ["100nF", "0402"], "decoupling (Basic)"),
    "100nF C0G": ("C170182", "1206N104J500CT", "C_1206_3216Metric", ["100nF", "1206", "NP0"], "Costas integrator"),
    "1uF": ("C52923", "CL05A105KA5NQNC", "C_0402_1005Metric", ["1uF", "0402"], "decoupling (Basic)"),
    "2.2uF": ("C23630", "CL10A225KO8NNNC", "C_0603_1608Metric", ["2.2uF", "0603"], "LDO in/out (Basic)"),
    "4.7uF": ("C19666", "CL10A475KO8NNNC", "C_0603_1608Metric", ["4.7uF", "0603"], "(Basic)"),
    "10uF": ("C15850", "CL21A106KAYNNNE", "C_0805_2012Metric", ["10uF", "0805"], "bulk (Basic)"),
    "22uF": ("C45783", "CL21A226MAQNNNE", "C_0805_2012Metric", ["22uF", "0805"], "input bulk (Basic)"),
}
RES = {
    "0R": ("C17168", "0402WGF0000TCE", ["0Ω", "0402"]),
    "2.2R 1206": ("C144499", "AC1206FR-072R2L", ["2.2Ω", "1206"]),
    "33R": ("C25105", "0402WGF330JTCE", ["33Ω", "0402"]),
    "49.9R": ("C25120", "0402WGF499JTCE", ["49.9Ω", "0402"]),
    "100R": ("C25076", "0402WGF1000TCE", ["100Ω", "0402"]),
    "300R": ("C25102", "0402WGF3000TCE", ["300Ω", "0402"]),
    "453R": ("C5126227", "FRC0402F4530TS", ["453Ω", "0402"]),
    "750R": ("C25132", "0402WGF7500TCE", ["750Ω", "0402"]),
    "820R": ("C25135", "0402WGF8200TCE", ["820Ω", "0402"]),
    "1k": ("C11702", "0402WGF1001TCE", ["1kΩ", "0402"]),
    "1.2k": ("C25862", "0402WGF1201TCE", ["1.2kΩ", "0402"]),
    "1.5k": ("C25867", "0402WGF1501TCE", ["1.5kΩ", "0402"]),
    "2k": ("C4109", "0402WGF2001TCE", ["2kΩ", "0402"]),
    "2.2k": ("C25879", "0402WGF2201TCE", ["2.2kΩ", "0402"]),
    "4.02k": ("C137968", "RC0402FR-074K02L", ["4.02kΩ", "0402"]),
    "4.7k": ("C25900", "0402WGF4701TCE", ["4.7kΩ", "0402"]),
    "5.1k": ("C25905", "0402WGF5101TCE", ["5.1kΩ", "0402"]),
    "10k": ("C25744", "0402WGF1002TCE", ["10kΩ", "0402"]),
    "20k": ("C25765", "0402WGF2002TCE", ["20kΩ", "0402"]),
    "100k": ("C25741", "0402WGF1003TCE", ["100kΩ", "0402"]),
    "150k": ("C25755", "0402WGF1503TCE", ["150kΩ", "0402"]),     # TLV3603 LE/HYS to VEE: 30 mV of hysteresis (DNP)
}

for _v, (_code, _mpn, _fp, _match, _note) in CAPS.items():
    PARTS["C " + _v] = P("C", _fp, STOCK + "Capacitor_SMD", _code, _mpn, _v.replace(" C0G", ""), _match, _note)
for _v, (_code, _mpn, _match) in RES.items():
    _fp = "R_1206_3216Metric" if "1206" in _v else "R_0402_1005Metric"
    PARTS["R " + _v] = P("R", _fp, STOCK + "Resistor_SMD", _code, _mpn, _v.replace(" 1206", ""), _match, "")


def consigned():
    return {k: p for k, p in PARTS.items() if p.get("consign")}


if __name__ == "__main__":
    n = sum(1 for p in PARTS.values() if p.get("lcsc"))
    print("%d part kinds, %d with LCSC codes, %d consigned, %d not parts"
          % (len(PARTS), n, len(consigned()), sum(1 for p in PARTS.values() if not p.get("lcsc") and not p.get("consign"))))
