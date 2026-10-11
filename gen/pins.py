"""The 40-pin Raspberry Pi header, pin by pin, on the two FPGA boards this board plugs onto, and
what this board puts on each pin.

One source of truth: the schematic's header symbol, the silkscreen's pin names, both constraint
files (gateware/pynq_z2.xdc, gateware/icepi_zero.lpf) and the handbook's pinout are generated
from HEADER and ICEPI.

PYNQ-Z2: header pin numbers and Zynq package pins are the GPSDO-PYNQ-Z2 board's measured and
verified table (its gen/design.py and README round 2: TUL's schematic, sheet 4; every signal pin
has its own 200 ohm series resistor on the PYNQ-Z2).  Pin 1 is at the right-hand end of the
PYNQ's header, on the row nearest its top edge; odd pins are the outer row.

Icepi Zero (Lattice ECP5 LFE5U-25F-6BG256C, cheyao/icepi-zero): header pin -> ball from its
gateware/icepi-zero.lpf (the `gpio[BCM]` comments are header pin numbers), ball -> function from
Lattice's FPGA-SC-02033 ECP5U-25 pinout (both in ../ECP5-2ADC-2DAC/reference and /datasheets).
No series resistors: the balls go straight to the header (GPSDO README R15).  All header I/O is
LVCMOS33 on banks 6 and 7 (the chip's left side) except pins 35 and 37 on bank 0 (top).  The
ECP5's generic DDR input (GDDRX2) samples at 655.8 Mb/s in speed grade -6 on the left and right
banks only, so the fast inputs stay off 35 and 37.  Its header is unpopulated as shipped: fit a
male vertical header, pin 1 in the Pi corner, and this board plugs on unchanged (the Icepi then
hangs off the socket; see PLAN.md section 7).  Pins 1/17 are 3.3 V and 2/4 are USB VBUS on both
boards; this board draws 1.3 A, so on the Icepi it takes 5 V from its own USB-C (JP301 open).  The Icepi
has no I2C pull-ups: fit R3xx (4.7 k, DNP) on the power sheet; the PYNQ has 2k2.

Clock-capable pins (an edge can drive a clock net directly, so the FPGA can time-stamp an
asynchronous event without first sampling it):
  PYNQ-Z2 (MRCC/SRCC): 10, 11, 13, 18, 26, 31, 35, 40
  Icepi Zero (PCLK/GR_PCLK): 16, 18, 19, 21, 22, 26, 32
  both: 18 and 26 only -> CMP_I (the data) on 18, TRIG_IN (the detector pulse) on 26.
The other comparator outputs are sampled (IDDR/ISERDES on the Zynq, GDDRX2 on the ECP5), which
is how the data is read on both anyway; a clock-capable pin is a bonus, not a requirement.  The slow
path's three comparators (sheet 6: 5 MHz, 40 x the gain, 36 ns later: they confirm or veto the fast
ones) are on 31, 32 and 40.  Bank 0's two pins carry MUX_RX (a slow input) and TRIG_A (an output).

Signals are provisional until the board is routed: interchangeable pins (all 3.3 V LVCMOS) are
bound last, from the placed board (CLAUDE_PCB.md section 5).  18 and 26 are not interchangeable.
"""

# header pin: (net on this board, Zynq pin, Zynq site, what it does)
HEADER = {
    1: ("3V3_HOST", "", "3V3", "not used: the board makes its own 3.3 V"),
    2: ("+5V_HDR", "", "5V", "5 V from the FPGA board (jumper; the PYNQ on its barrel supply; not from the Icepi)"),
    3: ("I2C_SDA", "W18", "IO_L22P_T3_34", "I2C to the DAC and ADC; 2k2 pull-up on the PYNQ"),
    4: ("+5V_HDR", "", "5V", "5 V from the FPGA board"),
    5: ("I2C_SCL", "W19", "IO_L22N_T3_34", "I2C clock; 2k2 pull-up on the PYNQ"),
    6: ("GND", "", "GND", ""),
    7: ("TX_I1", "Y18", "IO_L17P_T2_34", "TX I ladder, bit 1"),
    8: ("CMP_QN", "V6", "IO_L22P_T3_13", "comparator: Q < -Vth"),
    9: ("GND", "", "GND", ""),
    10: ("CMP_QP", "Y6", "IO_L13N_T2_MRCC_13", "comparator: Q > +Vth (MRCC N of the pair with pin 18)"),
    11: ("TX_I0", "U7", "IO_L11P_T1_SRCC_13", "TX I ladder, bit 0"),
    12: ("LOOP_SEL", "C20", "IO_L1P_T0_AD0P_35", "the Costas switch's select when JP1 is set to FPGA"),
    13: ("TX_Q1", "V7", "IO_L11N_T1_SRCC_13", "TX Q ladder, bit 1 (rpio_27: absent from the stock XDC)"),
    14: ("GND", "", "GND", ""),
    15: ("TX_Q0", "U8", "IO_L17N_T2_13", "TX Q ladder, bit 0"),
    16: ("CMP_IN", "W6", "IO_L22N_T3_13", "I window, - side: I_N above V_TIN (fast; the PYNQ's 2k2 pull-up here is a harmless load)"),
    17: ("3V3_HOST", "", "3V3", "not used"),
    18: ("CMP_I", "Y7", "IO_L13P_T2_MRCC_13", "comparator: sign(I) = the data (clock-capable on both boards)"),
    19: ("LOOP_HOLD", "V8", "IO_L15P_T2_DQS_13", "high opens the Costas integrator's input (VC frozen)"),
    20: ("GND", "", "GND", ""),
    21: ("LE_PLL_TX", "V10", "IO_L21N_T3_DQS_13", "MAX2871 (TX) latch enable"),
    22: ("CMP_IP", "F20", "IO_L15N_T2_DQS_AD12N_35", "I window, + side: I_P above V_TIP (fast; sheet 7, Response 14)"),
    23: ("MUX_TX", "W10", "IO_L16P_T2_13", "MAX2871 (TX) MUX: lock detect or register readback"),
    24: ("TX_EN", "F19", "IO_L15P_T2_DQS_AD12P_35", "TX enable, high = transmit: U206 inverts it onto the ADL5375's DSOP; 1 k to ground here, so a host that is off, unconfigured or not driving it leaves the modulator off"),
    25: ("GND", "", "GND", ""),
    26: ("TRIG_IN", "U19", "IO_L12N_T1_MRCC_34", "external trigger (a detector pulse) through the Schmitt buffer (clock-capable on both)"),
    27: ("TR_A", "Y16", "IO_L7P_T1_34", "antenna switch control A; B = not A is made on the board (also on J303; 2k2 pull-up on the PYNQ)"),
    28: ("CMP_QN_S", "Y17", "IO_L7N_T1_34", "slow path: Q < -Vth2"),
    29: ("SPI_SDATA", "Y19", "IO_L17N_T2_34", "SPI data to the MAX2871s and the PE43711"),
    30: ("GND", "", "GND", ""),
    31: ("SPI_SCLK", "U18", "IO_L12P_T1_MRCC_34", "SPI clock: both MAX2871s and the PE43711"),
    32: ("CMP_QP_S", "B20", "IO_L1N_T0_AD0N_35", "slow path: Q > +Vth2"),
    33: ("LE_PLL_RX", "W8", "IO_L15N_T2_DQS_13", "MAX2871 (RX) latch enable"),
    34: ("GND", "", "GND", ""),
    35: ("MUX_RX", "Y8", "IO_L14N_T2_SRCC_13", "MAX2871 (RX) MUX (Icepi bank 0: no GDDRX2)"),
    36: ("LE_DSA", "B19", "IO_L2P_T0_AD8P_35", "PE43711 latch enable"),
    37: ("TRIG_A", "W9", "IO_L16N_T2_13", "trigger out A (buffered to its SMA) (Icepi bank 0: no GDDRX2)"),
    38: ("TRIG_B", "A20", "IO_L2N_T0_AD8N_35", "trigger out B (buffered to its SMA)"),
    39: ("GND", "", "GND", ""),
    40: ("CMP_I_S", "Y9", "IO_L14P_T2_SRCC_13", "slow path: sign(I) through the 5 MHz stage (confirms or vetoes CMP_I)"),
}

# header pin: (ECP5 ball, ECP5 pad function, dual function) on the Icepi Zero
ICEPI = {
    3: ("T2", "PL38D", ""), 5: ("R2", "PL38C", ""), 7: ("R1", "PL35B", "VREF1_6"), 8: ("P1", "PL35A", ""),
    10: ("N1", "PL32A", ""), 11: ("R3", "PL41B", ""), 12: ("N4", "PL38A", ""), 13: ("P3", "PL38B", ""),
    15: ("P2", "PL32B", ""), 16: ("M2", "PL26D", "PCLKC6_0"), 18: ("L1", "PL26A", "PCLKT6_1"),
    19: ("L2", "PL26B", "PCLKC6_1"), 21: ("J1", "PL23A", "PCLKT7_1"), 22: ("J2", "PL23B", "PCLKC7_1"),
    23: ("G2", "PL14B", ""), 24: ("H2", "PL20B", ""), 26: ("G1", "PL20A", "GR_PCLK7_1"), 27: ("G3", "PL14C", "VREF1_7"),
    28: ("K3", "PL20D", ""), 29: ("E1", "PL11D", ""), 31: ("F3", "PL5D", ""), 32: ("J3", "PL20C", "GR_PCLK7_0"),
    33: ("E3", "PL5C", ""), 35: ("E4", "PT9A", ""), 36: ("H3", "PL14D", ""), 37: ("D4", "PT9B", ""),
    38: ("F1", "PL14A", ""), 40: ("F2", "PL11C", ""),
}
ICEPI_CLK_BALL = "M1"            # the Icepi's own 50 MHz oscillator (PCLKT6_0)

SIGNALS = {v[0]: k for k, v in HEADER.items() if v[1]}         # net -> header pin, FPGA signals only
POWER = {"GND", "+5V_HDR", "3V3_HOST"}

PYNQ_CLK = {k for k, v in HEADER.items() if "RCC" in v[2]}
ICEPI_CLK = {k for k, v in ICEPI.items() if "PCLK" in v[2]}
BOTH_CLK = PYNQ_CLK & ICEPI_CLK

# what the FPGA drives and what it reads (for the constraints' IOSTANDARD/DRIVE/SLEW and the handbook)
OUTPUTS = {"TX_I1", "TX_I0", "TX_Q1", "TX_Q0", "SPI_SCLK", "SPI_SDATA", "LE_PLL_TX", "LE_PLL_RX", "LE_DSA",
           "LOOP_HOLD", "LOOP_SEL", "TX_EN", "TRIG_A", "TRIG_B", "TR_A"}
INPUTS = {"CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN", "TRIG_IN", "MUX_TX", "MUX_RX", "CMP_I_S", "CMP_QP_S", "CMP_QN_S"}
FAST_INPUTS = {"CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN", "TRIG_IN"}       # sampled at full rate: off the Icepi's bank 0
BIDIR = {"I2C_SDA", "I2C_SCL"}
SPARES = {s for s in SIGNALS if s.startswith("SPARE")}
assert OUTPUTS | INPUTS | BIDIR | SPARES == set(SIGNALS), set(SIGNALS) ^ (OUTPUTS | INPUTS | BIDIR | SPARES)
assert len(SIGNALS) == 28

# the three pins of J303: the switch controls and ground, so an external switch module can be driven
# from there (Response 14: TR_B is made from TR_A on the antenna sheet, so J303 lives there)
J303 = ["TR_A", "TR_B", "GND"]


def check():
    zynq = [v[1] for v in HEADER.values() if v[1]]
    assert len(zynq) == len(set(zynq)) == 28, "28 distinct Zynq pins"
    assert sum(1 for v in HEADER.values() if v[0] == "GND") == 8
    assert set(ICEPI) == {k for k, v in HEADER.items() if v[1]}, "the Icepi table covers the 28 signal pins"
    balls = [v[0] for v in ICEPI.values()]
    assert len(balls) == len(set(balls)) == 28 and ICEPI_CLK_BALL not in balls
    assert BOTH_CLK == {18, 26}, BOTH_CLK
    assert SIGNALS["CMP_I"] == 18 and SIGNALS["TRIG_IN"] == 26
    assert all(SIGNALS[s] not in (35, 37) for s in FAST_INPUTS), "fast inputs off the Icepi's bank 0"
    assert not SPARES, "every header signal pin is used since Response 14"
    return True


if __name__ == "__main__":
    check()
    print("pin  PYNQ-Z2 (Zynq)                 Icepi Zero (ECP5)          net")
    for n in range(1, 41):
        net, zynq, site, what = HEADER[n]
        ic = ICEPI.get(n)
        ics = "%-4s %-6s %-11s" % (ic[0], ic[1], ic[2]) if ic else "%-23s" % site
        print("%2d   %-4s %-25s %s %s%s" % (n, zynq, site, ics, net, "  <- clock on both" if n in BOTH_CLK else ""))
    print("clock-capable: PYNQ", sorted(PYNQ_CLK), "Icepi", sorted(ICEPI_CLK), "both", sorted(BOTH_CLK))
