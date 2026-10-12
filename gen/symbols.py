"""The symbols drawn for CostasLink (the rest are KiCad's, vendored by gen/library.py).

Each is drawn the way the schematic flows: signal inputs on the left, outputs on the right,
supplies on top, grounds below.  Pin numbers come from the datasheets' pin figures and tables,
cited per symbol (build/txt/<part>.txt is the datasheet's text), and tools/check_pins.py reads
them back against those tables.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import kisch
from kisch import _hdr, _pin, _rect, _poly

G = 2.54
B, I, O, PI, PO, PA, NC = "bidirectional", "input", "output", "power_in", "power_out", "passive", "no_connect"


def _close(out):
    out += ['(embedded_fonts no)', ')']
    return "\n".join(out)


def box_symbol(name, ref, left, right, top, bottom, w, keywords="", value=None,
               top_pitch=G, top_x=None, extra=(), bottom_x=None, bottom_pitch=None):
    """A rectangle `w` wide.  left/right: lists of (number, name, type) or None for a gap, top to
    bottom.  top/bottom: (number, name, type) left to right, at `top_pitch` (or at explicit x
    positions `top_x` / `bottom_x`).  Pins are 5.08 long on a 2.54 grid."""
    rows = max(len(left), len(right))
    hh = rows * G / 2.0 + G / 2.0
    hw = w / 2.0
    out = _hdr(name, ref, value or name, hh + 3.81, keywords=keywords)
    out.append('(symbol "%s_0_1"' % name)
    out.append(_rect(-hw, hh, hw, -hh))
    out.extend(extra)
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    y0 = hh - G
    for i, p in enumerate(left):
        if p:
            out.append(_pin(p[0], p[1], -hw - 5.08, y0 - i * G, 0, 5.08, p[2]))
    for i, p in enumerate(right):
        if p:
            out.append(_pin(p[0], p[1], hw + 5.08, y0 - i * G, 180, 5.08, p[2]))
    def grid(v):
        return round(round(v / 1.27) * 1.27, 2)        # KiCad connects only on the 1.27 mm grid
    xs = top_x or [grid(-(len(top) - 1) * top_pitch / 2.0 + i * top_pitch) for i in range(len(top))]
    for x, p in zip(xs, top):
        out.append(_pin(p[0], p[1], x, hh + 5.08, 270, 5.08, p[2]))
    bp = bottom_pitch or 2 * G
    bx = bottom_x or [grid(-(len(bottom) - 1) * bp / 2.0 + i * bp) for i in range(len(bottom))]
    for x, p in zip(bx, bottom):
        out.append(_pin(p[0], p[1], x, -hh - 5.08, 90, 5.08, p[2]))
    out.append(')')
    return _close(out), dict(hw=hw, hh=hh, top_x=xs)


# ---------------------------------------------------------------------------------------
# MAX2871 (datasheet "Pin Description", TQFN-32 5x5; build/txt/MAX2871.txt lines 790-861).
# Reference and SPI on the left, RF outputs on the right, supplies on top, grounds below,
# the loop-filter pins (CP_OUT, TUNE) at the bottom left so the filter hangs under the chip.
def max2871():
    left = [("29", "REF_IN", I), None, None, ("1", "CLK", I), ("2", "DATA", I), ("3", "LE", I), None,
            ("30", "MUX", B), ("25", "LD", O), None, None, None, None, None, None, None,
            ("7", "CP_OUT", O), ("5", "SW", PA), None, ("20", "TUNE", I), None, ("22", "RSET", PA), None, None]
    # the four RF outputs 15.24 apart: each line carries a choke standing up to the rail
    right = [None, ("12", "RFOUTA_P", O), None, None, None, None, None, ("13", "RFOUTA_N", O), None, None, None, None, None,
             ("14", "RFOUTB_P", O), None, None, None, None, None, ("15", "RFOUTB_N", O), None,
             ("19", "NOISE_FILT", PA), ("23", "BIAS_FILT", PA), ("24", "REG", PA)]
    top = [("4", "CE", I), ("6", "VCC_CP", PI), ("10", "VCC_PLL", PI), ("28", "VCC_DIG", PI), ("32", "VCC_SD", PI),
           ("17", "VCC_VCO", PI), ("16", "VCC_RF", PI), ("26", "RFOUT_EN", I)]
    bottom = [("8", "GND_CP", PI), ("9", "GND_PLL", PI), ("27", "GND_DIG", PI), ("31", "GND_SD", PI),
              ("21", "GND_TUNE", PI), ("18", "GND_VCO", PI), ("11", "GND_RF", PI), ("33", "EP", PI)]
    return box_symbol("MAX2871", "U", left, right, top, bottom, 40.64,
                      keywords="Maxim/ADI MAX2871 23.5 MHz to 6 GHz fractional/integer-N synthesizer with VCO, TQFN-32",
                      top_pitch=5.08, bottom_pitch=3.81)


# ADL5380 (datasheet Table 2 "Pin Function Descriptions", LFCSP-24 4x4; build/txt/ADL5380.txt
# lines 300-330).  RF in on the left, LO below it, I/Q baseband out on the right.
def adl5380():
    left = [("22", "RFIP", I), ("21", "RFIN", I), None, None, ("9", "LOIP", I), ("10", "LOIN", I), None, None,
            ("19", "ADJ", PA), None, ("12", "NC", NC)]
    right = [("3", "IHI", O), ("4", "ILO", O), None, None, None, None, ("16", "QHI", O), ("15", "QLO", O), None, None, None]
    top = [("6", "VCC1", PI), ("13", "VCC2", PI), ("24", "VCC3", PI)]
    bottom = [("7", "ENBL", I), ("1", "GND1", PI), ("2", "GND2", PI), ("5", "GND3", PI), ("8", "GND4", PI), ("11", "GND", PI),
              ("14", "GND", PI), ("17", "GND", PI), ("18", "GND", PI), ("20", "GND", PI), ("23", "GND", PI), ("25", "EP", PI)]
    return box_symbol("ADL5380", "U", left, right, top, bottom, 30.48,
                      keywords="ADI ADL5380 400 MHz to 6 GHz quadrature demodulator, LFCSP-24",
                      top_pitch=7.62, bottom_pitch=2.54)


# ADL5375 (datasheet Table 3, LFCSP-24 4x4; build/txt/ADL5375.txt lines 380-402).
# Baseband in on the left, LO below it, RF out on the right.
def adl5375():
    left = [("21", "IBBP", I), ("22", "IBBN", I), None, None, None, ("10", "QBBP", I), ("9", "QBBN", I), None, None, None,
            ("3", "LOIP", I), ("4", "LOIN", I), None, None, ("1", "DSOP", I)]
    right = [None, None, None, None, None, None, ("16", "RFOUT", O), None, None, None, None, None, None, None, None]
    top = [("18", "VPS1", PI), ("24", "VPS2", PI)]
    bottom = [("2", "COMM", PI), ("5", "COMM", PI), ("8", "COMM", PI), ("11", "COMM", PI), ("12", "COMM", PI),
              ("14", "COMM", PI), ("17", "COMM", PI), ("19", "COMM", PI), ("20", "COMM", PI), ("23", "COMM", PI),
              ("25", "EP", PI)]
    extra_nc = []
    sym, geo = box_symbol("ADL5375", "U", left, right, top, bottom, 25.4,
                          keywords="ADI ADL5375-05 400 MHz to 6 GHz quadrature modulator, 0.5 V baseband bias, LFCSP-24",
                          top_pitch=7.62, bottom_pitch=2.54)
    # the four NC pins (6, 7, 13, 15) hang off the right side so they can be marked no-connect
    sym = sym.replace('(symbol "ADL5375_1_1"',
                      '(symbol "ADL5375_1_1"\n' + "\n".join(
                          _pin(n, "NC", geo["hw"] + 5.08, geo["hh"] - G * (k + 10), 180, 5.08, NC)
                          for k, n in enumerate(("6", "7", "13", "15"))))
    return sym, geo


# PE43711 (datasheet Table 9 and Figure 35, QFN-24 4x4; build/txt/PE43711.txt lines 1585-1660).
# RF1 (input) left, RF2 (output) right; the serial interface below the RF input; the parallel
# control pins (grounded in serial mode) at the bottom.
def pe43711():
    left = [("5", "RF1", PA), None, None, ("17", "CLK", I), ("18", "SI", I), ("16", "LE", I), None, None, None, None, None, None]
    # Table 9 of the datasheet: pins 4, 6-13 and 15 are all GND (the pin audit of Response 8 found 6-13 and 15
    # missing): the nine extra ones go down the right side, where sch_rx joins them on one bar
    right = [("14", "RF2", PA), None, None, ("6", "GND", PI), ("7", "GND", PI), ("8", "GND", PI), ("9", "GND", PI), ("10", "GND", PI),
             ("11", "GND", PI), ("12", "GND", PI), ("13", "GND", PI), ("15", "GND", PI)]
    top = [("2", "VDD", PI), ("3", "P/S", I)]
    bottom = [("1", "D0", I), ("24", "D1", I), ("23", "D2", I), ("22", "D3", I), ("21", "D4", I), ("20", "D5", I),
              ("19", "D6", I), ("4", "GND", PI), ("25", "EP", PI)]
    return box_symbol("PE43711", "U", left, right, top, bottom, 22.86,
                      keywords="pSemi PE43711 9 kHz to 6 GHz 7-bit digital step attenuator, QFN-24",
                      bottom_pitch=2.54, top_pitch=10.16)


# ADL5611 (SOT-89-3): 1 RFIN, 2 GND (and the exposed tab), 3 RFOUT = supply (Table 5).
def adl5611():
    return box_symbol("ADL5611", "U", [("1", "RFIN", I)], [("3", "RFOUT", O)], [], [("2", "GND", PI)], 12.7,
                      keywords="ADI ADL5611 30 MHz to 6 GHz gain block, 14.3 dB at 5.8 GHz, SOT-89; RFOUT carries the 5 V bias")


# SKY65404-31 (Table 1, QFN-6 1.5x1.5): 1 V_ENABLE, 2 GND, 3 RF_IN, 4 RF_OUT, 5 GND, 6 VCC; 7 = paddle.
def sky65404():
    return box_symbol("SKY65404-31", "U", [("3", "RF_IN", I), None], [("4", "RF_OUT", O), None],
                      [("6", "VCC", PI), ("1", "V_ENABLE", I)], [("2", "GND", PI), ("5", "GND", PI), ("7", "EP", PI)], 17.78,
                      keywords="Skyworks SKY65404-31 4.9-5.9 GHz LNA, 1 dB NF, 13 dB, QFN-6 1.5x1.5 mm", bottom_pitch=2.54, top_pitch=7.62)


# THS4541 (Table 5-1, VQFN-16 RGT): FB- 1, IN+ 2, IN- 3, FB+ 4, Vs+ 5-8, Vocm 9, OUT+ 10, OUT- 11,
# PD 12, Vs- 13-16, 17 = the pad (isolated; to ground).  Drawn as a triangle-less box: the
# feedback pins beside their inputs so the gain network draws naturally.
def ths4541():
    # FB- (1) sits beside IN+ (2) and FB+ (4) beside IN- (3) on the package, so each feedback
    # resistor stands between two neighbouring rows, 7.62 apart
    left = [("1", "FB-", PA), None, None, ("2", "IN+", I), None, None, ("3", "IN-", I), None, None, ("4", "FB+", PA), None, ("9", "Vocm", I)]
    right = [None, None, ("10", "OUT+", O), None, None, None, None, ("11", "OUT-", O), None, None, None, None]
    top = [("5", "Vs+", PI), ("6", "Vs+", PI), ("7", "Vs+", PI), ("8", "Vs+", PI), ("12", "PD", I)]
    bottom = [("13", "Vs-", PI), ("14", "Vs-", PI), ("15", "Vs-", PI), ("16", "Vs-", PI), ("17", "EP", PI)]
    return box_symbol("THS4541", "U", left, right, top, bottom, 22.86,
                      keywords="TI THS4541 850 MHz fully differential amplifier, VQFN-16", bottom_pitch=2.54,
                      top_x=[-2.54, 0.0, 2.54, 5.08, 12.7])


# TLV3601 (Table 5-1, SC-70-5 DCK): 1 OUT, 2 VEE, 3 IN+, 4 IN-, 5 VCC.  Drawn as a comparator triangle.
def tlv3601():
    name = "TLV3601"
    out = _hdr(name, "U", name, 7.62, keywords="TI TLV3601 2.5 ns comparator, push-pull output, SC-70-5")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_poly([(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)], fill="background"))
    out.append(_poly([(-3.8, 2.54 - 0.6), (-3.8, 2.54 + 0.6)], width=0.2))      # + at IN+
    out.append(_poly([(-4.4, 2.54), (-3.2, 2.54)], width=0.2))
    out.append(_poly([(-4.4, -2.54), (-3.2, -2.54)], width=0.2))               # - at IN-
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("3", "IN+", -8.89, 2.54, 0, 3.81, I))
    out.append(_pin("4", "IN-", -8.89, -2.54, 0, 3.81, I))
    out.append(_pin("1", "OUT", 8.89, 0, 180, 3.81, O))
    out.append(_pin("5", "VCC", 0, 6.35, 270, 3.81, PI))
    out.append(_pin("2", "VEE", 0, -6.35, 90, 3.81, PI))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=5.08)


# TLV3603 (Table 5-1, SC-70-6 DCK): 1 OUT, 2 VEE, 3 IN+, 4 IN-, 5 LE/HYS, 6 VCC.  The TLV3601 with a
# latch / hysteresis pin (high 0 mV, floating 3 mV, a resistor to VEE 30-60 mV, low latches).
def tlv3603():
    name = "TLV3603"
    out = _hdr(name, "U", name, 7.62, keywords="TI TLV3603 2.5 ns comparator, push-pull output, adjustable hysteresis and latch, SC-70-6")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_poly([(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)], fill="background"))
    out.append(_poly([(-3.8, 2.54 - 0.6), (-3.8, 2.54 + 0.6)], width=0.2))
    out.append(_poly([(-4.4, 2.54), (-3.2, 2.54)], width=0.2))
    out.append(_poly([(-4.4, -2.54), (-3.2, -2.54)], width=0.2))
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("3", "IN+", -8.89, 2.54, 0, 3.81, I))
    out.append(_pin("4", "IN-", -8.89, -2.54, 0, 3.81, I))
    out.append(_pin("1", "OUT", 8.89, 0, 180, 3.81, O))
    out.append(_pin("6", "VCC", 0, 6.35, 270, 3.81, PI))
    out.append(_pin("2", "VEE", 0, -6.35, 90, 3.81, PI))
    out.append(_pin("5", "LE/HYS", 2.54, -6.35, 90, 3.81, I))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=5.08)


# AD5696R (TSSOP-16, Figure 4 and the pin table, docs/datasheets/txt/ad5696r_5695r_5694r.txt): 1 VREF,
# 2 VOUTB, 3 VOUTA, 4 GND, 5 VDD, 6 VOUTC, 7 VOUTD, 8 SDA, 9 LDAC, 10 GAIN, 11 VLOGIC, 12 A0, 13 SCL,
# 14 A1, 15 RESET, 16 RSTSEL.  I2C address 0 0 0 1 1 A1 A0.
def ad5696r():
    # drawn for this board's straps: every pin tied high on top, every pin tied low underneath
    left = [("8", "SDA", B), ("13", "SCL", I)]
    right = [("3", "VOUTA", O), ("2", "VOUTB", O), ("6", "VOUTC", O), ("7", "VOUTD", O), None, ("1", "VREF", PO)]
    top = [("5", "VDD", PI), ("11", "VLOGIC", PI), ("15", "~{RESET}", I), ("16", "RSTSEL", I)]
    bottom = [("4", "GND", PI), ("9", "~{LDAC}", I), ("10", "GAIN", I), ("12", "A0", I), ("14", "A1", I)]
    return box_symbol("AD5696R", "U", left, right, top, bottom, 17.78, bottom_pitch=2.54,
                      keywords="ADI AD5696R 16-bit quad voltage-output DAC, I2C, 2.5 V internal reference, TSSOP-16")


# SN74LVC1G3157 (Table 4-1, SC-70-6 DCK): 1 B2, 2 GND, 3 B1, 4 A, 5 VCC, 6 S.  S high: A = B1.
def lvc1g3157():
    name = "SN74LVC1G3157"
    out = _hdr(name, "U", "74LVC1G3157", 7.62, keywords="TI SN74LVC1G3157 SPDT analog switch, 300 MHz; S low connects A to B1, S high to B2")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_rect(-5.08, 5.08, 5.08, -5.08))
    out.append(_poly([(-2.0, 2.54), (2.0, 0.6)], width=0.25))                   # the blade
    out.append(_poly([(-2.3, 2.54), (-1.7, 2.54)], width=0.3))
    out.append(_poly([(-2.3, -2.54), (-1.7, -2.54)], width=0.3))
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("3", "B1", -8.89, 2.54, 0, 3.81, PA))
    out.append(_pin("1", "B2", -8.89, -2.54, 0, 3.81, PA))
    out.append(_pin("4", "A", 8.89, 0, 180, 3.81, PA))
    out.append(_pin("6", "S", 0, -8.89, 90, 3.81, I))
    out.append(_pin("5", "VCC", -2.54, 8.89, 270, 3.81, PI))
    out.append(_pin("2", "GND", 2.54, -8.89, 90, 3.81, PI))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=5.08)


# TS5A3159 (datasheet pin table, SC-70-6 DCK): 1 NO, 2 GND, 3 NC, 4 COM, 5 V+, 6 IN.  IN high: COM-NO.
def ts5a3159():
    name = "TS5A3159DCK"
    out = _hdr(name, "U", "TS5A3159", 7.62, keywords="TI TS5A3159 1 ohm SPDT analog switch; IN high connects COM to NO")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_rect(-5.08, 5.08, 5.08, -5.08))
    out.append(_poly([(-2.0, 2.54), (2.0, 0.6)], width=0.25))
    out.append(_poly([(-2.3, 2.54), (-1.7, 2.54)], width=0.3))
    out.append(_poly([(-2.3, -2.54), (-1.7, -2.54)], width=0.3))
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("1", "NO", -8.89, 2.54, 0, 3.81, PA))
    out.append(_pin("3", "NC", -8.89, -2.54, 0, 3.81, PA))
    out.append(_pin("4", "COM", 8.89, 0, 180, 3.81, PA))
    out.append(_pin("6", "IN", 0, -8.89, 90, 3.81, I))
    out.append(_pin("5", "V+", -2.54, 8.89, 270, 3.81, PI))
    out.append(_pin("2", "GND", 2.54, -8.89, 90, 3.81, PI))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=5.08)


# HMC536MS8G (datasheet functional diagram, page 1): 1 A, 2 B, 3 RFC, 4 N/C, 5 RF1, 6 GND, 7 GND, 8 RF2.
# A low / B high: RFC-RF1; A high / B low: RFC-RF2.  RFC (the antenna) on the left, RF1/RF2 right.
def hmc536():
    return box_symbol("HMC536MS8G", "U", [("3", "RFC", PA)], [("5", "RF1", PA), None, ("8", "RF2", PA)],
                      [("4", "NC", NC)], [("1", "A", I), ("2", "B", I), ("6", "GND", PI), ("7", "GND", PI), ("9", "EP", PI)], 25.4,
                      keywords="ADI HMC536MS8G DC-6 GHz GaAs SPDT T/R switch, positive control, 30 ns",
                      bottom_pitch=5.08)


# A 4-pin 3225 oscillator (SX3V VCXO: 1 VC, 2 GND, 3 OUT, 4 VDD, its datasheet's pin figure;
# the TC32H4 TCXO has the same pads and 1 = control/NC).  Control in on the left, out right.
def osc_3225(name, keywords, pin1):
    return box_symbol(name, "Y", [("1", pin1, I)], [("3", "OUT", O)], [("4", "VDD", PI)], [("2", "GND", PI)], 12.7,
                      keywords=keywords)


def vcxo():
    return osc_3225("VCXO_3225", "25 MHz VCXO, 3225, +-100 ppm pull over 0.3-3.0 V on VC", "VC")


def tcxo():
    return osc_3225("TCXO_3225", "25 MHz TCXO +-2.5 ppm, 3225, LVCMOS output; pin 1 is the control / no-connect pin", "VC/NC")


# Johanson 5400BL15B050 balun (datasheet "Terminal Configuration"): 1 unbalanced, 2 GND,
# 3 balanced, 4 balanced, 5 GND, 6 NC.
def balun_5400():
    name = "Balun_5400"
    out = _hdr(name, "T", "5400BL15B050", 7.62, keywords="Johanson 5400BL15B050 1:1 balun 4.9-5.9 GHz, 0805")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_rect(-5.08, 5.08, 5.08, -5.08))
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("1", "UNBAL", -8.89, 0, 0, 3.81, PA))
    out.append(_pin("3", "BAL+", 8.89, 2.54, 180, 3.81, PA))
    out.append(_pin("4", "BAL-", 8.89, -2.54, 180, 3.81, PA))
    out.append(_pin("2", "GND", -2.54, -8.89, 90, 3.81, PA))
    out.append(_pin("5", "GND", 2.54, -8.89, 90, 3.81, PA))
    out.append(_pin("6", "NC", 0, 8.89, 270, 3.81, NC))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=5.08)


# The PYNQ-Z2's Raspberry Pi header as this board sees it (gen/pins.py): the 28 FPGA signals on the
# sides, odd pins left and even pins right in pin order, the 5 V pins on top (and the two 3.3 V
# pins, unused), the eight grounds underneath.  Pin numbers are the header's.
def rpi_header():
    import pins as PINS
    left, right = [], []
    for n in range(1, 41):
        net, zynq, site, what = PINS.HEADER[n]
        if not zynq:
            continue
        row = (str(n), "%d %s" % (n, net), B)
        (left if n % 2 else right).append(row)
    rows = max(len(left), len(right))
    left += [None] * (rows - len(left)); right += [None] * (rows - len(right))
    top = [("2", "2 +5V", PI), ("4", "4 +5V", PI), ("1", "1 3V3", NC), ("17", "17 3V3", NC)]
    bottom = [(str(n), "%d GND" % n, PI) for n in (6, 9, 14, 20, 25, 30, 34, 39)]
    return box_symbol("RPi_Header_40", "J", left, right, top, bottom, 35.56,
                      keywords="the PYNQ-Z2's 40-pin Raspberry Pi header, 2x20 socket on the underside; pin numbers are the header's",
                      top_pitch=7.62, bottom_pitch=3.81)


# A -20 dB coupled-line coupler: copper on the board (gen/footprints.py), a net tie between
# pins 1-2 (the line) and 3-4 (the coupled line); drawn as two parallel lines.
def coupler():
    name = "Coupler_20dB"
    out = _hdr(name, "CP", "-20 dB", 7.62, keywords="coupled-line directional coupler, two quarter-wave lines on the board; a net tie, not a part")
    out.append('(symbol "%s_0_1"' % name)
    out.append(_poly([(-5.08, -2.54), (5.08, -2.54)], width=0.5))
    out.append(_poly([(-5.08, 2.54), (5.08, 2.54)], width=0.5))
    out.append(_poly([(-3.0, 0.3), (3.0, 0.3)], width=0.15))
    out.append(')')
    out.append('(symbol "%s_1_1"' % name)
    out.append(_pin("1", "IN", -8.89, -2.54, 0, 3.81, PA))
    out.append(_pin("2", "OUT", 8.89, -2.54, 180, 3.81, PA))
    out.append(_pin("3", "CPL", -8.89, 2.54, 0, 3.81, PA))
    out.append(_pin("4", "ISO", 8.89, 2.54, 180, 3.81, PA))
    out.append(')')
    return _close(out), dict(hw=5.08, hh=2.54)


CUSTOM = {"MAX2871": max2871, "Coupler_20dB": coupler, "ADL5380": adl5380, "ADL5375": adl5375, "PE43711": pe43711, "ADL5611": adl5611,
          "SKY65404-31": sky65404, "THS4541": ths4541, "TLV3601": tlv3601, "TLV3603": tlv3603, "AD5696R": ad5696r, "SN74LVC1G3157": lvc1g3157,
          "TS5A3159DCK": ts5a3159, "VCXO_3225": vcxo, "TCXO_3225": tcxo, "Balun_5400": balun_5400, "HMC536MS8G": hmc536,
          "RPi_Header_40": rpi_header}

# KiCad's own symbols, by our name (gen/library.py vendors them, flattened)
STOCK = {
    "R": "Device:R", "C": "Device:C", "C_Polarized": "Device:C_Polarized", "L": "Device:L", "LED": "Device:LED", "D_TVS": "Device:D_TVS",
    "Polyfuse": "Device:Polyfuse", "Ferrite_Bead": "Device:FerriteBead",
    "USB_C_Receptacle_USB2.0_16P": "Connector:USB_C_Receptacle_USB2.0_16P",
    "Conn_Coaxial": "Connector:Conn_Coaxial", "Conn_02x20_Odd_Even": "Connector_Generic:Conn_02x20_Odd_Even",
    "Conn_01x02": "Connector_Generic:Conn_01x02", "Conn_01x03": "Connector_Generic:Conn_01x03",
    "Conn_01x06": "Connector_Generic:Conn_01x06",
    "TestPoint": "Connector:TestPoint", "MountingHole": "Mechanical:MountingHole", "PWR_FLAG": "power:PWR_FLAG",
    "AO3401A": "Transistor_FET:AO3401A", "TPS7A20xxxDBV": "Regulator_Linear:TPS7A20xxxDBV",
    "LP5907MFX-3.3": "Regulator_Linear:LP5907MFX-3.3", "OPA2388": "Amplifier_Operational:OPA2189xDGK", "2N7002": "Transistor_FET:2N7002",
    "MCP4728": "Analog_DAC:MCP4728", "ADS1115IDGS": "Analog_ADC:ADS1115IDGS",
    "74LVC2G34": "74xGxx:74LVC2G34", "74LVC1G17": "74xGxx:74LVC1G17", "74LVC1G04": "74xGxx:74LVC1G04",
}

# every power net, and whether its flag is drawn as a ground (bar below the node)
RAILS = {"+5V_IN": False, "+5V_RF": False, "+5V_HDR": False, "VBUS": False,
         "+3V3_PLL_TX": False, "+3V3_PLL_RX": False, "+3V3_ANA": False, "+3V3_DIG": False, "+3V3_OSC": False,
         "GND": True}

if __name__ == "__main__":
    for n, fn in CUSTOM.items():
        text, geo = fn()
        print(n, len(text.splitlines()), "lines")
