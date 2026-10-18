#!/usr/bin/env python3
"""Where every part goes: millimetres from the board's top-left corner, x right, y down,
rotation in degrees counter-clockwise (KiCad's), side F or B.

    python3 gen/placement.py          plan the placement from the netlist and the footprints:
                                      build/placement.json (what gen/board.py places) and
                                      build/view/placement.png (to look at)

The floorplan (CLAUDE_PCB.md section 5: connectors and blocks first, each signal path through
its chips in the schematic's order, then each chip's passives hung off its pins):

  * 120 x 100 mm, four layers (120 x 90 until Response 9).  The PYNQ-Z2 lies under the bottom-left of the board: our left
    edge at the PYNQ's x = 72 (clear of its HDMI jack, as the GPSDO board), our bottom edge
    11 mm above its top edge, so its Raspberry Pi header comes up through the 2x20 socket on
    our underside along the bottom edge (pin 1 at the right-hand end, odd row outer) and the
    only part of the PYNQ under us is that 11 mm strip.  Three M3 standoffs to the desk in the
    corners that are not over the PYNQ, and a slot onto the PYNQ's own top-right mounting hole.
    The Icepi Zero plugs up into the same socket from below.
  * The five SMAs stand along the top edge, barrels out: RX ANT, TX ANT, then the switch
    block's SW TX, ANT, SW RX (SW TX next to TX ANT: the jumper lead is short).
  * The receive chain runs straight down from RX ANT at x = 24: LNA, step attenuator, two gain
    blocks, the coupler (RX MON to its right), the balun, the ADL5380 with its RF pins facing up.
    Its I pair leaves to the left into the I arm, its Q pair to the right into the Q arm, its LO
    comes up from the RX synthesizer below it; the VCXO sits under the synthesizer, the slow I
    stage and the slow comparators at the bottom-left over header pins 33/37/40, the fast
    comparators at the bottom-middle over header pins 8/10/18.
  * The transmit chain runs straight up to TX ANT at x = 56: the TX synthesizer (its TCXO and
    REF IN to its right), the ADL5375 with RFOUT facing up and the two ladders either side, the
    gain block, the pi pad, the coupler (TX MON to its left), the SMA.
  * The Costas loop (mux, sign jumpers, HOLD, PI filter, SEL) sits under the TX synthesizer,
    with the DAC and the ADC to its right; VC runs left to the VCXO.
  * The switch block is the top-right corner; the five regulators form a column on the right
    under it; the USB-C is on the right edge with the input fuse, FET, TVS and bulk beside it;
    the header's 5 V path (fuse, FET, jumper) sits by the socket's right end.  Test pads, J303
    and the trigger jacks line the bottom-right strip, which is off the PYNQ.
  * The latency triggers (two buffers, three SMAs off the left edge) take the left margin above the I arm.

Everything not listed in ANCHORS is placed by rules from the netlist (plan(): a shunt stands
perpendicular at the pin it serves, outside the chip's courtyard; a series part lies on the
line between the two pads it joins; the rest sit beside the chip they belong to), then pushed
apart until no courtyards overlap.  The report says what could not be placed cleanly.
"""
import collections, glob, json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
from sexp import parse, kids, kid, val, head
import board_info as BI

BOARD = dict(w=120.0, h=100.0, r=2.0)     # 100 tall since Response 9 (Jason: "make the board bigger if that would help"): 10 mm more between the arms and the socket
EDGE_KEEP = 1.0                      # no courtyard closer to the edge than this (SMA barrels excepted)
GAP = 0.5                            # between courtyards (0.25 until Response 9: a 0.15 mm track needs 0.47 between two pads)
FAN_BAND = 1.8                       # kept clear round a fine-pitch chip for its fan-out vias (gen/routes.fan)

# ---- the PYNQ-Z2 under the board (GPSDO-PYNQ-Z2/pcb/geom.py, measured) ---------------------
PZ_W, PZ_H = 137.0, 87.0
PZ_LEFT, PZ_BOTTOM = 72.0, 76.0      # the PYNQ's x under our left edge; its y (up) under our bottom edge
HDR_MID_X, HDR_PITCH, HDR_ODD_DY, HDR_EVEN_DY = 101.65, 2.54, 3.5, 6.04
PZ_HOLE_TR = (133.3, 4.3)            # the PYNQ's top-right mounting hole: from its left edge and its TOP edge


def pz(x, y_up):
    """PYNQ frame (its bottom-left corner, y up) to board millimetres."""
    return (round(x - PZ_LEFT, 3), round(BOARD["h"] - (y_up - PZ_BOTTOM), 3))


def hdr_pin(n):
    """Board (x, y) of Raspberry Pi header pin n (1-40): pin 1 at the right-hand end, odd row outer."""
    col = (n - 1) // 2
    return pz(HDR_MID_X + 19 * HDR_PITCH / 2 - col * HDR_PITCH, PZ_H - (HDR_ODD_DY if n % 2 else HDR_EVEN_DY))


PZ_HOLE = pz(PZ_HOLE_TR[0], PZ_H - PZ_HOLE_TR[1])
PZ_SHADOW = (0.0, BOARD["h"] - (PZ_H - PZ_BOTTOM), pz(PZ_W, 0.0)[0], BOARD["h"])   # over the PYNQ: no desk standoff here
SOCKET_KEEP = (hdr_pin(39)[0] - 2.0, hdr_pin(1)[1] - 1.5, hdr_pin(1)[0] + 2.0, hdr_pin(2)[1] + 1.5)   # the socket's pads, both sides

SMA_Y = 7.0                          # the SMAs' centre pins: the barrel reaches 4.6 mm past the top edge
RX_X, TX_X = 24.0, 56.0              # the receive chain's and the transmit chain's RF line
# the chains' corridors (x0, y0, x1, y1): only a part ON the line (a chip, or a series part placed on it)
# may stand in one; the RF track and its coplanar gap run there (Response 9: a decoupling capacitor was
# pushed onto the TX line, and the LNA's DC block sideways off the RX line)
CORRIDORS = [(RX_X - 0.9, SMA_Y + 3.0, RX_X + 0.9, 56.5), (TX_X - 0.9, SMA_Y + 3.0, TX_X + 0.9, 36.0)]

# The board's own marks (CLAUDE_PCB.md section 5; the design review: there were none): three fiducials,
# netless copper dots in mask openings at three corners on the top (every part JLCPCB places is there),
# and the copper layers' numbers at one spot.  No part, track, via, pour or silkscreen comes near
# either (gen/board.marks draws them; gen/routes.plan_and_route and gen/silk keep clear).
FIDUCIALS = [(11.0, 11.0), (115.5, 15.0), (116.5, 87.5)]
FID_COPPER, FID_MASK, FID_CLEAR = 0.5, 1.0, 1.5      # radii: the copper dot, the mask opening, nothing else
LAYER_MARK = (102.5, 20.5)                           # "1" on F.Cu ... "4" on B.Cu, 1.2 mm high (at (74, 30) until Prompt 35: the rail jacks' row)
LAYER_MARK_BOX = (LAYER_MARK[0] - 1.6, LAYER_MARK[1] - 1.3, LAYER_MARK[0] + 1.6, LAYER_MARK[1] + 1.3)
MARK_KEEP = [(x - FID_CLEAR, y - FID_CLEAR, x + FID_CLEAR, y + FID_CLEAR) for x, y in FIDUCIALS] + [LAYER_MARK_BOX]


def at(x, y, rot=0, side="F"):
    return (float(x), float(y), float(rot), side)


# Hand-placed parts.  The chips' rotations are chosen so that the RF pins lie on the chain
# lines (asserted in check()).  KiCad turns counter-clockwise: at rot 90 a pad at local
# (x, y) lands at (y, -x).
ANCHORS = {
    # mounting
    "H301": at(5.0, 5.0), "H302": at(115.0, 5.0), "H303": at(115.0, 94.0), "H304": at(PZ_HOLE[0], PZ_HOLE[1]),
    # the socket, under the board, pin 1 at the right-hand end
    "J302": at(hdr_pin(1)[0], hdr_pin(1)[1], 0, "B"),
    # SMAs along the top edge, barrels out
    "J101": at(RX_X, SMA_Y, 90), "J202": at(TX_X, SMA_Y, 90),
    "J402": at(76.0, SMA_Y, 90), "J401": at(92.0, SMA_Y, 90), "J403": at(108.0, SMA_Y, 90),
    # ---- receive chain, straight down x = RX_X ----
    "U101": at(RX_X + 0.5, 15.0, 180),       # LNA: RF_IN (pin 3) up, RF_OUT (4) down, both 0.5 left of centre at 180
    "L102": at(RX_X + 3.1, 16.3, 180),      # the LNA's VCC choke beside its VCC pin (6, right of the line), under R101: rule-placed on the LEFT, its
                                             # 0.2 mm track went up and round the SMA's pin inside the legs to cross the line (Prompt 33)
    "U102": at(RX_X + 0.75, 23.0, 270),      # DSA: RF1 (5) up, RF2 (14) down
    "R102": at(RX_X + 4.35, 21.0, 90),       # the DSA's P/S pull-up beside its pin (3, right of the line): rule-placed on the LEFT, its track
                                             # crossed the line round J101's pin inside the SMA's legs, then walled the LNA's VCC pin in (Prompt 34)
    "U103": at(RX_X + 1.95, 32.0, 0),        # gain block 1: pins 1/3 on its left face, in above, out below
    "U117": at(RX_X + 1.95, 40.0, 0),        # gain block 2
    "CP101": at(RX_X, 49.6, 270),            # coupler: IN (1) up, OUT (2) down, coupled port to the right
    "J102": at(31.5, 47.5, 0),               # RX MON
    "T101": at(RX_X + 0.275, 55.0, 270),     # balun (TDK 0402, four pads): at 270 pin 1 (unbalanced) is top left on the line, GND top right, the pair 2/3 below
    "C159": at(RX_X - 0.2, 57.2, 270),       # the pair's DC blocks (Prompt 31): pin 1 (the balun's side) up; 1.5 mm apart (their courtyards and the gap), each leg jogs to its ADL5380 pin
    "C160": at(RX_X + 1.3, 57.2, 270),
    "U104": at(RX_X + 0.85, 61.3, 0),        # ADL5380: RF up (21/22), I left (3/4), Q right (15/16), LO below (9/10); 61 since the pair's DC blocks (Prompt 31)
    "U105": at(12.5, 60.0, 180),             # I arm FDA: inputs face the demodulator
    "U106": at(37.0, 60.0, 0),               # Q arm FDA
    # The arm amplifiers' resistors at their pins (Response 10: the rules had put U105's 4.02 k feedback
    # resistors 10 and 13 mm away, a long summing node on an 850 MHz-GBW amplifier, and U106's input
    # lines crossing beside the chip).  Each feedback resistor stands vertical against its FB / IN pin
    # pair; the shunt to ground stands on the input's line; the gain resistor lies on it towards the
    # demodulator.  The two arms mirror each other about x 24.75 (the demodulator's centre line),
    # each courtyard 0.5 mm clear of its amplifier's.
    "R110": at(15.7, 59.0, 90), "R109": at(15.7, 61.5, 90),     # U105 Rf: I_SUM/FB+ above, FB-/IN+ below
    "R108": at(17.2, 59.0, 90), "R106": at(17.2, 61.5, 270),    # shunts: I_SUM, IN+ to ground
    "R107": at(19.2, 59.51, 180), "R105": at(19.2, 60.99, 180), # Rg from IHI (to I_SUM) and ILO (to IN+)
    "R522": at(19.2, 57.9, 180),                                 # I_OFF_F's 100 k into I_SUM, beside R107
    "R117": at(33.8, 59.0, 270), "R118": at(33.8, 61.5, 270),   # U106 Rf: FB-/IN+ above, IN-/FB+ below (R116 is the trim since Response 14)
    "R116": at(30.3, 63.0, 270),                                 # Q_OFF_F's 100 k into the IN- node, under the gain resistor
    "R113": at(32.3, 59.0, 90), "R115": at(32.3, 61.5, 270),    # shunts
    "R112": at(30.3, 59.51, 0), "R114": at(30.3, 60.99, 0),     # Rg from QHI and QLO
    "J104": at(5.0, 62.5, 0),                # I MON
    "J105": at(44.0, 53.0, 0),               # Q MON
    "U115": at(RX_X + 0.85, 77.3, 180),
    "R228": at(62.5, 55.0, 90),
    # The two ADCs' RC input filters (Prompt 31: the capacitors moved to the ADC pins' nets, and the shunt-at-pin
    # rule then walled the resistors' far pads and the slow ADC's SCL pin; the 160 Hz filter does not care where
    # its parts sit).  U114 (85, 81): the I_P / Q_P pair to its left, VC / ERR above its right; the I2C pins'
    # side (right, upper) kept clear.  U510 (35, 19.5): V5_MON / TEMP below its right, clear of SCL/SDA.
    "C154": at(80.0, 78.8, 0), "C155": at(80.0, 84.5, 0),      # (0.7 lower walled R141's I_P pin in: builds 40b-d) "R141": at(77.0, 80.3, 0), "R142": at(77.0, 82.7, 0),
    "C156": at(90.0, 77.8, 0), "C157": at(92.5, 77.8, 0), "R143": at(95.0, 77.8, 0), "R144": at(97.5, 77.8, 0),
    "C526": at(40.5, 21.5, 0), "C527": at(40.5, 23.5, 0), "R532": at(43.5, 23.5, 0), "R533": at(46.0, 23.5, 0),              # the TCXO's DNP pad-1 pull-up (Prompt 31), beside Y201, not where the rules dropped it (28, 97)      # RX synthesizer: RFOUTA (12/13) on its top face, up into the LO pins
    "J109": at(18.5, 66.0, 90),              # LO RX MON
    "Y101": at(RX_X + 0.85, 86.0, 0),        # VCXO under the synthesizer (REF_IN is on the synthesizer's bottom face)
    "U116": at(32.0, 86.0, 0),               # REF OUT buffer
    "J108": at(36.5, 86.5, 0),               # REF OUT (MMCX: the edge near the VCXO is the slow I stage's and the socket's)
    "U501": at(11.0, 70.0, 270),             # slow I stage: inputs up (from the I arm), outputs down
    "U502": at(38.0, 67.0, 270),             # slow Q stage
    "J501": at(5.0, 73.0, 0),                # I SLOW MON (MMCX)
    "J502": at(43.58, 67.0, 90),              # Q SLOW MON: centre pad down, towards its 1 k (walled in facing the stage);
                                              # 0.4 right and 0.5 up (Response 15): its name's column between it and U502,
                                              # JP102's Q+ clear below it
    "R519": at(44.65, 71.66, 0),              # its 1 k, where the rules had it, under its name's column (Response 15)
    "U504": at(36.0, 78.0, 0),               # CMP_QP_S: under the slow Q stage (its 1k series parts then sit
    "U505": at(41.0, 78.0, 0),               # CMP_QN_S:  between the two, not stranded under the RX synthesizer)
    "U503": at(16.0, 86.0, 0),               # CMP_I_S   (their header pins: gen/pin_swap.py, from the placement)
    "U107": at(43.0, 85.0, 0),               # CMP_I    -> pin 18 (x 33.5)
    "U601": at(48.0, 85.0, 0),               # CMP_QP   -> pin 10 (x 43.6)  (sheet 7 since Response 14)
    "U602": at(53.0, 85.0, 0),               # CMP_QN   -> pin 8  (x 46.2)
    "U603": at(58.0, 85.0, 0),               # CMP_IP   (the I window, Response 14; its pin from gen/pin_swap.py)
    "U604": at(63.0, 85.0, 0),               # CMP_IN
    # the window comparators' scope taps (U.FL), in the clear ground left of the ADC
    # one row, centre pads down towards the comparators, in their order (QP, QN, IP, IN) so no tap line crosses
    # a millimetre up from 74.6 (Response 15): the row's names go under it, clear of JP301
    "J603": at(69.9, 73.6, 90), "J604": at(75.4, 73.6, 90), "J601": at(80.9, 73.6, 90), "J602": at(86.4, 73.6, 90),
    "U605": at(95.5, 70.0, 0),               # the window thresholds' DAC (AD5696R, 0x0C), where DAC 2 stood
    # the interference detectors (Prompt 28), in the free field above the Q arm, between the RX chain
    # (x 24) and the TX modulator (x 50): the log amp nearest the fast Q arm with both inputs (pins 1, 8)
    # facing it, the peak hold above it, the ADC above them (the I2C bus comes to it), the NTC beside the
    # arm amplifiers
    "U507": at(32.0, 39.0, 270),             # AD8310: west of the column where J105's and J204's labels stand
    "U508": at(40.0, 30.0, 0),               # OPA2388: the peak hold
    "U510": at(35.0, 19.5, 0),               # ADS1115 0x49
    "TH501": at(33.8, 52.4, 0),              # NTC
    "R523": at(35.6, 50.35, 0),              # the log amp's 1 k inputs, west of the column where J105's labels stand
    "R524": at(35.6, 48.8, 0),
    # the antenna jacks' ESD / DC shunts (Prompt 28, fitted since 29), ON their lines: the rules had stood them 4 mm off,
    # a stub that would detune 5.8 GHz when fitted.  Each as near its line as the placer's rules allow (0.5 mm
    # between courtyards, 0.2 mm round the SMA's legs): a 1-1.6 mm stub, 0.05 of a wavelength.  RX and ANT:
    # upright beside the DC block, off its jack-side pad; TX: lying beside the line under the jack's leg
    "L101": at(25.53, 11.9, 270),
    "R101": at(27.0, 14.3, 270),             # the LNA's enable pull-up, out of L101's spot beside the DC block
    "L202": at(57.79, 11.4, 0),
    "L401": at(93.51, 11.86, 270),
    "J103": at(47.0, 78.6, 0),               # CMP I MON (under the SIGN jumper, right of the slow Q comparators)
    "R121": at(37.7, 82.5, 0),               # its 1 k, between U107 and REF OUT: in build 18's reshuffle the rules put it
                                             # under REF OUT's name, and J108's limit had nowhere to go
    "R120": at(40.12, 82.85, 180),           # and the two beside it where the rules had them (the four variants of
    "R612": at(42.92, 87.1, 180),            # build 18: this one routes completely)
    # ---- transmit chain, straight up x = TX_X ----
    "U203": at(TX_X, 55.0, 180),             # TX synthesizer: RFOUTA on its top face, up into the modulator's LO
    "Y201": at(66.0, 55.0, 0),               # TCXO
    "JP201": at(71.0, 49.0, 90),             # REF: TCXO / REF IN, pins along x
    "J203": at(113.0, 49.0, 0),              # REF IN: an SMA off the right edge, level with JP201 (its line crosses the power column)
    "J204": at(46.5, 45.5, 180),             # LO TX MON: left of the synthesizer, level with its RFOUTB pins' run
    "C232": at(51.25, 48.66, 90),            # RFOUTB_N's 1.5 pF block where the rules put it (a series part follows its load, so both are anchored)
    "R220": at(53.15, 48.18, 0),             # and its 49.9 ohm load level with the block's top pad: it was walled in 3 mm away
                                             # (both 0.5 mm left since the LO pair's N leg moved out to x 55.4: the design review)
    "U201": at(TX_X, 38.0, 90),              # ADL5375: RFOUT (16) up, LO (3/4) below, I pins (21/22) left, Q (9/10) right
    "R315": at(13.14, 89.0, 0),              # LE_PLL_RX's pull-down above header pin 33: by rule it hung 12 mm off U115's
                                             # crowded LE side and walled the net in (Response 15)
    "U202": at(TX_X - 1.95, 29.0, 180),      # gain block: RFIN (1) below, RFOUT (3) above, on its right face
    "CP201": at(TX_X, 15.5, 90),             # coupler: IN below, OUT up, coupled port to the left
    "J201": at(49.5, 19.0, 180),             # TX MON
    # ---- the Costas loop and the monitors ----
    "JP101": at(44.0, 59.5, 90),             # SIGN (pins along x)
    "U110": at(51.0, 63.0, 0),               # the mux
    "JP102": at(48.5, 70.5, 90),             # SIGN B2 (0.5 mm right of 48 in Response 15: J502 beside it)
    "JP103": at(60.0, 70.5, 90),             # SEL
    "U111": at(60.0, 63.0, 0),               # HOLD
    "R125": at(30.9, 89.0, 0),               # LOOP_HOLD's 100 k pull-down above its header pin (19), like R315: beside U111 its ground pad sat on a fill island with no room for a via (Prompt 32)
    "J106": at(58.0, 79.0, 0),               # ERR MON (MMCX)
    "U112": at(73.0, 65.0, 0),               # OPA2388
    "J107": at(80.0, 57.5, 0),               # VC MON (MMCX)
    "U113": at(85.0, 69.0, 0),               # DAC 1
    "U114": at(85.0, 81.0, 0),               # ADC
    "U506": at(9.0, 83.0, 90),               # DAC 2 (0x61): all four outputs serve the left half (V_T2, I_OFF, Q_OFF, I_OFF_F);
                                             # it sat by DAC 1 until Response 10 and its lines crossed the board.  I2C pins down.
                                             # 1 mm lower since build 18: I SLOW MON's planned line (the tap now ahead of
                                             # the pole) runs above its I_OFF / Q_OFF pins and had walled them in
    # ---- triggers, left margin ----
    # TRIG A, TRIG B, TRIG IN: SMAs off the left edge (rot 180: the barrel points -x), 11.5 mm apart for the nuts and fingers
    # TRIG A and B a millimetre up from 25 and 36.5 (Response 15): room under TRIG B's name for J208 and its own name
    "J205": at(7.0, 24.0, 180), "J206": at(7.0, 35.5, 180), "J207": at(7.0, 48.0, 180),
    "U204": at(15.0, 30.5, 180), "JP202": at(12.5, 54.0, 270), # U204 turned: its outputs face the jacks
    # U205 and its 1k above TRIG IN's pin, under its own MMCX and that one's name, so TRIG IN's name and limit sit
    # level with the pin like TRIG A's and TRIG B's (Response 15: one relation for the column; at y 48 the 1k sat
    # where the name goes)
    "U205": at(15.0, 45.7, 0), "R223": at(21.5, 49.0, 90),    # the 453 ohm between the buffer and J208 (right of TRIG IN's label strip)
    "U206": at(61.5, 45.5, 0),               # TX_EN's inverter, left of the rail monitors' name columns (at (66.5, 42) until Prompt 35)

    "C602": at(65.86, 83.35, 0), "R605": at(68.38, 85.0, 0),
    "R510": at(47.81, 62.85, 0),             # the slow Q stage's input resistor just under JP101's SIGN B1 (Response 15;
                                             # by rule it went 8 mm off, into the TX synthesizer's routing)
    "R141": at(80.44, 81.25, 0), "R142": at(78.24, 82.7, 0),   # the ADC's input resistors at its pins, where the rules had them   # U604's decoupling and LE/HYS where the rules had them before Response 15
    "J208": at(19.0, 53.3, 0),               # TRIG IN MON (MMCX, Response 14): under TRIG IN's label since Prompt 35 (TRIG B's two-line limit took its
                                             # old place above U205), between JP202 and the RX corridor, its name under it
                                             # between TRIG B's name and its own (Response 15), left of L103
    # ---- the antenna switch, top right ----
    "U401": at(92.0, 18.0, 270),             # RFC (3) up to ANT; RF1 (5) down-left to SW TX, RF2 (8) down-right to SW RX
    "U402": at(100.0, 11.0, 0),              # TR_B = not TR_A (Response 14): above the SW RX line, between the SMAs
    "C401": at(92.0, 11.75, 270),            # the ANT line's DC block, between the SMA's legs and the chip (pin 1, the jack's side, up)
    "C402": at(76.0, 12.5, 90),              # SW TX's block, straight under its jack (the line to RF1 is a diagonal from here)
    "C403": at(108.0, 12.5, 90),             # SW RX's block
    "R401": at(96.5, 15.6, 0), "R403": at(96.5, 13.4, 0),     # the 100 ohm on A and B, right of the chip's control pins (not on the RF1 line)
    "R402": at(100.5, 15.6, 0), "R404": at(100.5, 13.4, 0),   # A's pull-up, B's pull-down
    "J490": at(108.0, 25.0),                 # TR A, an MMCX (Prompt 35: it was a test pad at (104, 22)); below the RF2 line (y ~15 here), right of U301
    "JP302": at(113.5, 27.0, 0), "JP303": at(113.5, 34.5, 0),   # the I2C pull-up jumpers (Prompt 35), in the free strip under the switch block (pin 1 at the anchor, 6.2 mm of courtyard)
    "R312": at(109.5, 30.5, 90), "R313": at(109.5, 37.5, 90),    # their 4.7 k beside them (by rule they went to the ADC's SDA pin, into the window monitors' limit strip)
    "R215": at(61.5, 57.0, 0),               # U203's CE pull-up, straight out of its pin 4 (by rule it stood under Y201 and did not route: build 40a)
    "R211": at(58.5, 19.15, 0),              # the pi pad's DNP shunts stand beside the line, not on it
    "R210": at(58.5, 24.5, 0),
    "R213": at(53.5, 13.0, 0),               # the TX coupler's isolated-port load, clear of the SMA's leg
    "R103": at(27.54, 55.18, 270),           # the RX coupler's isolated-port load, below-right of its ISO pad where build 39's rules had it (Prompt 35's
                                             # neighbours sent it up-left, and the line then ran along the coupled line: the tidy trimmed it, one unconnected)
    # ---- power, right side ----
    "U301": at(98.0, 28.0, 0), "U302": at(98.0, 36.0, 0), "U303": at(98.0, 44.0, 0), "U304": at(98.0, 52.0, 0), "U305": at(98.0, 60.0, 0),
    "J301": at(117.55, 70.0, 90),            # USB-C, its face 1.2 mm past the right edge (rot 90: the pad row toward -x)
    "Q301": at(106.0, 78.0, 0), "D303": at(106.0, 86.0, 0), "FB301": at(93.5, 50.0, 0),    # the bead 5 mm right since Prompt 35 (J396's name column)
    "C320": at(94.8, 86.0, 0),               # +5V_IN's 100 uF polymer (the hot-plug damper), left of the 22 uF pair: the rules found no room
    "D301": at(112.0, 62.0, 0), "D302": at(112.0, 57.0, 0),
    "Q302": at(72.0, 86.0, 0), "JP301": at(66.0, 79.5, 90),     # JP301 moved up in Response 14: the comparator row took its place
    "J303": at(103.2, 96.0, 90),             # right of the test pads (Response 15: they moved 4.6 mm right); pins run +x
    # test pads along the bottom-right, one per rail and a ground
    # the rails' pads, 4 mm apart, each named above itself in one column (Response 15: 5 mm right of F302)
    "TP301": at(71.6, 97.0), "TP302": at(75.6, 97.0), "TP303": at(79.6, 97.0), "TP304": at(83.6, 97.0),
    "TP305": at(87.6, 97.0), "TP306": at(91.6, 97.0), "TP307": at(95.6, 97.0), "TP308": at(99.6, 97.0),
    "F302": at(68.3, 91.43, 270),            # the header's 2 A PTC, 0.8 mm left of where the rules had put it: clear of TP301's name
    # LD TX and LD RX (Prompt 35): U.FL right of the rail row, their names above.  LD RX's pad spot by U115 has no
    # room for a jack (build 40a: it sat in the I_P corridor and the net broke), LD TX by U203 walled the CE pull-up in
    "J290": at(87.0, 45.5), "J190": at(92.5, 45.5),
    "J590": at(38.5, 37.0),                             # LOG Q: U.FL below the peak hold (its pad's spot under U510 has no room for a jack)
    # the seven rail monitors (Prompt 35): a row of U.FL through 1 k in the free field between the TX chain and the
    # regulators, each resistor under its jack; the names a column above each (LABEL_ROWS)
    # two rows (a U.FL needs 5.5 mm of pitch): four with their names in columns above, three with theirs below;
    # each 1 k between the rows under or over its jack
    # the four main rails in a row (a U.FL's courtyard is 4.35 x 5.0 mm: 5.5 mm pitch, no second row fits under their
    # name columns), names below (a column above read as the SMAs' above it: label_rows.owner_ok), each 1 k over its jack;
    # the PLL and OSC rails on a jack each beside their regulators in the north-east strip, names below
    **{"J39%d" % i: at(65.0 + 5.5 * i, 29.0, 0) for i in range(4)},
    **{"R39%d" % i: at(65.0 + 5.5 * i, 25.0, 90) for i in range(4)},
    # x 103.3: 0.7 off the regulators' courtyards (SOT-23-5: +-2.05), their name columns clear of REF IN's limit strip (x >= 105.3)
    "J394": at(103.3, 33.0), "R394": at(103.3, 29.0, 0),
    "J395": at(103.3, 49.5), "R395": at(103.3, 45.5, 0),      # each 1 k over its jack, as in the row
    "J396": at(103.3, 66.0), "R396": at(103.3, 62.0, 0),
}

# where a hand-placed part's own passives should look for room, when the rules' first choice
# is taken: (ref, (dx, dy)) nudges applied after the rules
NUDGE = {}

# The functional blocks, for the silkscreen's boxes (gen/silk_blocks.py; CLAUDE_PCB.md section 5:
# everything that belongs to a block lies inside its box, nothing else does).  A rule-placed part
# belongs to the block of the part it was hung off.
BLOCKS = {
    "RX CHAIN 5.8 GHz: LNA, DSA, 2x gain, coupler, balun, demodulator, I/Q arms":
        ["J101", "U101", "U102", "U103", "U117", "CP101", "J102", "T101", "U104", "U105", "U106", "J104", "J105"],
    "RX LO: MAX2871 on the 25 MHz VCXO (the loop's VCO)": ["U115", "J109", "Y101", "U116", "J108", "J190"],
    "SLOW PATH: x20, 4.8 MHz, confirm or veto": ["U501", "U502", "J501", "J502", "U503", "U504", "U505", "U506"],
    "INTERFERENCE: log, peak, 5V, temp (0x49)": ["U507", "U508", "U510", "J590"],
    "FAST COMPARATORS: CMP_I and the I and Q windows": ["U107", "U601", "U602", "U603", "U604", "J103"],
    "WINDOW MONITORS": ["J601", "J602", "J603", "J604"],
    "TX CHAIN 5.8 GHz: ADL5375, gain block, pad, coupler": ["U201", "U202", "CP201", "J201", "R211", "R210", "R213", "U206"],
    "TX LO: MAX2871 on the TCXO or REF IN": ["U203", "Y201", "JP201", "J203", "J204", "J290"],
    "COSTAS LOOP: sign(I) x Q, HOLD, PI filter; DACs, ADC":
        ["JP101", "U110", "JP102", "JP103", "U111", "J106", "U112", "J107", "U113", "U114", "U605"],
    "LATENCY TRIGGERS": ["J205", "J206", "J207", "U204", "U205", "JP202", "J208"],
    "ANTENNA SWITCH HMC536 (fit for one antenna)": ["J402", "J401", "J403", "U401", "C401", "C402", "C403", "R401", "R402", "R403", "R404", "J490", "U402"],
    "RAIL MONITORS: U.FL through 1k": ["J39%d" % i for i in range(7)] + ["R39%d" % i for i in range(7)],
    "POWER: 5 V in, five 3.3 V rails": ["U301", "U302", "U303", "U304", "U305", "J301", "Q301", "D303", "FB301", "D301", "D302",
                                          "Q302", "JP301", "J303", "TP301", "TP302", "TP303", "TP304", "TP305", "TP306", "TP307", "TP308"],
}
GROUP_OF = {ref: name for name, refs in BLOCKS.items() for ref in refs}

# ----------------------------------------------------------------------------------------------
# geometry
# ----------------------------------------------------------------------------------------------
# ---- where the connectors' names go (Response 15) ---------------------------------------------
# Jason: "If there are SMAs in a row, their labels should all be in the same relative orientation".
# Each row's side is decided here and its strips are kept clear of the parts placed by rule (a part
# placed by hand in one is reported); gen/silk_jacks.py tries this side first and
# tools/label_check.py checks what was printed (CLAUDE_PCB.md sections 4 and 6).
LABEL_ROWS = (
    (("J101", "J202", "J402", "J401", "J403"), "W", 0),     # the top edge: each name left of its SMA, level with its pin
    (("J205", "J206", "J207"), "E", 0),                     # the left edge: inward, level with each pin
    (("J203",), "S", 0),                                    # REF IN, alone on the right edge: under it (inward, its limit is long)
    (("J603", "J604", "J601", "J602"), "S", 0),             # the window monitors: under each, the shared limit under them
    (("TP301", "TP302", "TP303", "TP304", "TP305", "TP306", "TP307", "TP308"), "N", 90),   # a column above each pad
    (("J390", "J391", "J392", "J393"), "S", 90),            # the rail monitors (Prompt 35): a column below each jack
    (("J394",), "S", 90), (("J395",), "S", 90), (("J396",), "S", 90),
    (("J290", "J190"), "N", 90),                            # the lock detects: columns above (their limits exempt)
    (("J208",), "S", 0, "name"),                            # TRIG IN MON: under it, above U205 (its limit where it fits)
    (("J502",), "W", 90, "name"),                           # Q SLOW MON: a column left of it, between it and U502
    (("J105",), "W", 90),                                   # Q MON: a column left of it (Prompt 28: the detectors had taken the space)
)
# The headers' pin labels (gen/silk_jacks.py): a selector's two choices beyond its outer pins, level with them, and
# what it does at its middle pin on `mid`'s side; "pins" puts every pin's name above itself, turned along the pins;
# a two-pin jumper's name on `mid`'s side.  Pin order: the netlist's (JP101 and JP102: pin 1 is Q_P, pin 3 Q_N;
# until Response 15 the board said Q- at pin 1).
HEADER_LABELS = (
    ("JP101", ("Q+", "SIGN B1", "Q-"), "S"),     # U110's B1 input: Q+ or Q- (the other jumper the other way); under it: C215 above
    ("JP102", ("Q+", "SIGN B2", "Q-"), "S"),     # U110's B2 input, the same layout as JP101's
    ("JP103", ("CMP", "SEL", "FPGA"), "pins"),   # each above its pin: JP102's Q- sits 3 mm left of it
    ("JP201", ("TCXO", "REF", "REF IN"), "N"),
    ("J303", ("TR A", "TR B", "GND"), "pins"),
    ("JP202", ("50R",), "S"),
    ("JP302", ("SDA PU",), "N"), ("JP303", ("SCL PU",), "S"),       # the I2C pull-ups: fitted for the Icepi Zero, open for the PYNQ-Z2
    ("JP301", ("HDR 5V",), "S"),
)
HEADER_SIZE = (0.8, 0.7)                 # the smaller of gen/silk_jacks.HEADER: what must fit
LABEL_SIZE = {"SMA": (1.5, 1.35), "tap": (1.0, 0.8), "TP": (1.0, 0.9)}     # (height, width) of the names reserved for
LIMIT_SIZE = (0.8, 0.72)
CHAR = 0.92                          # a character's advance, of its width (KiCad's stroke font, measured)


def pad_wh(P, ref, num):
    """a pad's width and height on the board: turned with its part (a quarter turn swaps them)"""
    w, h = P.fp(ref)["pads"][num][2:]
    return (h, w) if int(round(P.pos[ref][2])) % 180 == 90 else (w, h)


def label_strips(P):
    """(owner, rectangle) for every name (and limit) of LABEL_ROWS, from the connectors' pads"""
    import levels as LV
    out = []
    for row in LABEL_ROWS:
        refs, side, angle = row[:3]
        names_only = "name" in row[3:]
        lim_side = [f.split()[1] for f in row[3:] if f.startswith("limit ")]     # a limit on its own side, turned
        refs = [r for r in refs if r in P.pos]
        if not refs:
            continue
        lims = [LV.LIMITS.get(P.comps[r]["value"], ("", ""))[0] if not (r.startswith("TP") or names_only) else "" for r in refs]
        shared = len(refs) > 1 and len(set(lims)) == 1 and lims[0] and side in "NS"
        blocks = []
        for r, lim in zip(refs, lims):
            fam = "TP" if r.startswith("TP") else ("SMA" if "SMA" in P.comps[r]["fp"] else "tap")
            h, w = LABEL_SIZE[fam]
            name = P.comps[r]["value"].replace("+", "") if fam == "TP" else P.comps[r]["value"]
            L, T = CHAR * w * len(name) + 0.3, h + 0.3
            if angle == 90:
                L, T = h + 0.2, L + 0.9                # a column: KiCad's text runs past the estimate along its length (builds 40a-c)
            pts = [(P.pad_xy(r, n), pad_wh(P, r, n)) for n in P.fp(r)["pads"]]
            x0 = min(q[0] - d[0] / 2 for q, d in pts) - 0.1
            x1 = max(q[0] + d[0] / 2 for q, d in pts) + 0.1
            y0 = min(q[1] - d[1] / 2 for q, d in pts) - 0.1
            y1 = max(q[1] + d[1] / 2 for q, d in pts) + 0.1
            if not r.startswith("TP"):                 # the body the silk sees (a U.FL's fab square is wider than its pads):
                c = P.bbox(r)                          # the courtyard less half a millimetre, within the board
                x0, y0 = min(x0, max(c[0] + 0.5, 0.0)), min(y0, max(c[1] + 0.5, 0.0))
                x1, y1 = max(x1, min(c[2] - 0.5, BOARD["w"])), max(y1, min(c[3] - 0.5, BOARD["h"]))
            ax, ay = P.pad_xy(r, "1") if fam in ("SMA", "TP") else P.pos[r][:2]
            g = 0.1
            if side == "N":
                rect = (ax - L / 2, y0 - g - T, ax + L / 2, y0 - g)
            elif side == "S":
                rect = (ax - L / 2, y1 + g, ax + L / 2, y1 + g + T)
            elif side == "E":
                rect = (x1 + g, ay - T / 2, x1 + g + L, ay + T / 2)
            else:
                rect = (x0 - g - L, ay - T / 2, x0 - g, ay + T / 2)
            if lim and not shared and angle == 0:
                lines = lim.split("\n")                 # a two-line limit (TRIG A's "OUT" over its level): the longest line wide, both tall
                ll, lt = CHAR * LIMIT_SIZE[1] * max(len(l) for l in lines) + 0.3, (LIMIT_SIZE[0] + 0.3) * len(lines)
                if side in "EW":
                    lx0 = rect[0] if side == "E" else rect[2] - ll
                    rect = (min(rect[0], lx0), rect[1], max(rect[2], lx0 + ll), rect[3] + lt)
                elif side == "S":
                    rect = (min(rect[0], ax - ll / 2), rect[1], max(rect[2], ax + ll / 2), rect[3] + lt)
                else:
                    rect = (min(rect[0], ax - ll / 2), rect[1] - lt, max(rect[2], ax + ll / 2), rect[3])
            out.append((r, rect))
            blocks.append(rect)
            if lim_side:
                lim = LV.LIMITS.get(P.comps[r]["value"], ("", ""))[0]
                ll, lt = LIMIT_SIZE[0] + 0.3, CHAR * LIMIT_SIZE[1] * len(lim) + 0.3       # a column
                out.append((r, (x1 + g, ay - lt / 2, x1 + g + ll, ay + lt / 2) if lim_side[0] == "E"
                            else (x0 - g - ll, ay - lt / 2, x0 - g, ay + lt / 2)))
        if shared:
            ll, lt = CHAR * LIMIT_SIZE[1] * len(lims[0]) + 0.3, LIMIT_SIZE[0] + 0.3
            cx = sum(P.pos[r][0] for r in refs) / len(refs)
            y = max(b[3] for b in blocks) if side == "S" else min(b[1] for b in blocks) - lt
            out.append((refs[0], (cx - ll / 2, y, cx + ll / 2, y + lt)))
    h, w = HEADER_SIZE
    for ref, texts, mid in HEADER_LABELS:
        if ref not in P.pos:
            continue
        pins = [P.pad_xy(ref, str(k + 1)) for k in range(len(texts))]
        pads = [(P.pad_xy(ref, n), pad_wh(P, ref, n)) for n in P.fp(ref)["pads"]]
        # the pads and the outline round them (KiCad's headers: 0.48 mm past the pads, and its line)
        x0 = min(q[0] - d[0] / 2 for q, d in pads) - 0.6
        x1 = max(q[0] + d[0] / 2 for q, d in pads) + 0.6
        y0 = min(q[1] - d[1] / 2 for q, d in pads) - 0.6
        y1 = max(q[1] + d[1] / 2 for q, d in pads) + 0.6
        L = lambda t: CHAR * w * len(t) + 0.3
        T = h + 0.35
        x0, y0, x1, y1 = x0 - 0.25, y0 - 0.25, x1 + 0.25, y1 + 0.25      # the silk's gap from the outline
        if len(texts) == 1:
            cx = (x0 + x1) / 2
            r = (cx - L(texts[0]) / 2, y1, cx + L(texts[0]) / 2, y1 + T) if mid == "S" else (cx - L(texts[0]) / 2, y0 - T, cx + L(texts[0]) / 2, y0)
            out.append((ref, r))
        elif mid == "pins":
            for (px, py), t in zip(pins, texts):
                out.append((ref, (px - T / 2, y0 - L(t), px + T / 2, y0)))
        else:
            (ax, ay), (bx, by), (cx, cy) = pins
            lo, hi = ((ax, texts[0]), (cx, texts[2])) if ax < cx else ((cx, texts[2]), (ax, texts[0]))
            out.append((ref, (x0 - L(lo[1]), ay - T / 2, x0, ay + T / 2)))
            out.append((ref, (x1, ay - T / 2, x1 + L(hi[1]), ay + T / 2)))
            r = (bx - L(texts[1]) / 2, y0 - T, bx + L(texts[1]) / 2, y0) if mid == "N" else (bx - L(texts[1]) / 2, y1, bx + L(texts[1]) / 2, y1 + T)
            out.append((ref, r))
    return out


def turn(x, y, rot):
    """A footprint-local point turned by KiCad's rotation (counter-clockwise on the screen)."""
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    return (x * c + y * s, -x * s + y * c)


def place_pt(local, pos):
    x, y, rot, side = pos
    lx, ly = local
    if side == "B":
        ly = -ly                                   # pcbnew's Flip() mirrors y (measured in gen/board.py's check)
    tx, ty = turn(lx, ly, rot)
    return (x + tx, y + ty)


def bbox_of(court, pos):
    x0, y0, x1, y1 = court
    pts = [place_pt(p, pos) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def hit(a, b, gap=0.0):
    return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap


# ----------------------------------------------------------------------------------------------
# inputs: footprints and the netlist
# ----------------------------------------------------------------------------------------------
def load_footprints():
    """name -> dict(pads={num: (x, y, w, h)}, court=(x0, y0, x1, y1), tht=bool)."""
    out = {}
    pretty = os.path.join(BI.HW, "lib", BI.LIB + ".pretty")
    for f in sorted(glob.glob(os.path.join(pretty, "*.kicad_mod"))):
        node = parse(open(f, encoding="utf-8").read())[0]
        name = os.path.basename(f)[:-10]
        pads, tht = {}, False
        for p in kids(node, "pad"):
            num, kind = val(p), val(p, 2)
            a = kid(p, "at")
            sz = kid(p, "size")
            if kind == "thru_hole":
                tht = True
            lay = kid(p, "layers")
            if kind == "np_thru_hole" or not lay:
                continue
            layers = [val(lay, i) for i in range(1, len(lay))]
            if not any(l in ("F.Cu", "*.Cu") for l in layers):
                continue                           # paste-only windows
            if num not in pads:
                pads[num] = (float(val(a)), float(val(a, 2)), float(val(sz)), float(val(sz, 2)))
        xs, ys = [], []
        for it in node:
            if isinstance(it, list) and head(it) in ("fp_line", "fp_rect", "fp_circle", "fp_poly", "fp_arc"):
                lay = kid(it, "layer")
                if lay and val(lay) in ("F.CrtYd", "B.CrtYd"):
                    if head(it) == "fp_circle":
                        c, e = kid(it, "center"), kid(it, "end")
                        r = math.hypot(float(val(e)) - float(val(c)), float(val(e, 2)) - float(val(c, 2)))
                        xs += [float(val(c)) - r, float(val(c)) + r]; ys += [float(val(c, 2)) - r, float(val(c, 2)) + r]
                        continue
                    for k in ("start", "end"):
                        q = kid(it, k)
                        if q:
                            xs.append(float(val(q))); ys.append(float(val(q, 2)))
                    pts = kid(it, "pts")
                    if pts:
                        for xy in kids(pts, "xy"):
                            xs.append(float(val(xy))); ys.append(float(val(xy, 2)))
        if xs:
            court = (min(xs), min(ys), max(xs), max(ys))
        else:                                      # a test point: its pad
            x, y, w, h = next(iter(pads.values()))
            court = (x - w / 2, y - h / 2, x + w / 2, y + h / 2)
        out[name] = dict(pads=pads, court=court, tht=tht)
    return out


def load_netlist():
    doc = parse(open(BI.NETLIST, encoding="utf-8").read())[0]
    comps = {}
    for c in kids(kid(doc, "components"), "comp"):
        ref = val(kid(c, "ref"))
        fp = val(kid(c, "footprint"))
        if not fp or fp.endswith(":"):
            continue                               # PWR_FLAGs
        props = {}
        for p in kids(c, "property"):
            nm, vl = kid(p, "name"), kid(p, "value")
            props[val(nm) if nm else "?"] = val(vl) if vl else ""
        comps[ref] = dict(value=val(kid(c, "value")), fp=fp.split(":")[-1], dnp="dnp" in props)
    nets = {}
    for n in kids(kid(doc, "nets"), "net"):
        nets[val(kid(n, "name"))] = [(val(kid(x, "ref")), val(kid(x, "pin"))) for x in kids(n, "node")]
    return comps, nets


def load_sch_positions():
    """ref -> (sheet file, x, y): where the schematic drew each symbol.  A capacitor between a rail
    and ground belongs to the chip it was drawn beside (gen/sch_blocks.supply_bar draws one per pin)."""
    out = {}
    for f in sorted(glob.glob(os.path.join(BI.HW, "*.kicad_sch"))):
        doc = parse(open(f, encoding="utf-8").read())[0]
        for s in kids(doc, "symbol"):
            a = kid(s, "at")
            ref = None
            for p in kids(s, "property"):
                if val(p) == "Reference":
                    ref = val(p, 2)
            if ref and a and not ref.startswith("#") and ref not in out:
                out[ref] = (os.path.basename(f), float(val(a)), float(val(a, 2)))
    return out


def is_rail(net):
    return net == "GND" or net.startswith("+") or net.endswith("VBUS")


def refkey(ref):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


# ----------------------------------------------------------------------------------------------
# the plan
# ----------------------------------------------------------------------------------------------
class Plan:
    def __init__(self):
        self.fps = load_footprints()
        self.comps, self.nets = load_netlist()
        self.pos = {}                              # ref -> (x, y, rot, side)
        self.want = {}                             # ref -> (nx, ny): the direction to push it if it collides
        self.pin_net = {}
        for net, nodes in self.nets.items():
            for ref, pin in nodes:
                self.pin_net[(ref, pin)] = net
        self.report = []
        self.sch = load_sch_positions()
        self.group = {}                            # ref -> the silkscreen block it belongs to
        self.on_line = set()                       # series parts on an RF chain line: they move along it only
        for ref, p in ANCHORS.items():
            if ref in self.comps:
                self.pos[ref] = p
                if ref in GROUP_OF:
                    self.group[ref] = GROUP_OF[ref]
            else:
                self.report.append("anchor %s is not in the netlist" % ref)
        self.strips = label_strips(self)           # the connectors' names, kept clear (Response 15)

    # ---- geometry of a placed part -------------------------------------------------------
    def fp(self, ref):
        return self.fps[self.comps[ref]["fp"]]

    def pad_xy(self, ref, num):
        x, y, w, h = self.fp(ref)["pads"][num]
        return place_pt((x, y), self.pos[ref])

    def centre(self, ref):
        return self.pos[ref][:2]

    def bbox(self, ref, pos=None):
        return bbox_of(self.fp(ref)["court"], pos or self.pos[ref])

    def side_normal(self, ref, num):
        """The outward direction from the chip's centre through the pad, snapped to an axis
        (a 2-terminal part: along its own axis, away from the other pad)."""
        px, py = self.pad_xy(ref, num)
        pads = self.fp(ref)["pads"]
        if len(pads) == 2:
            other = next(n for n in pads if n != num)
            ox, oy = self.pad_xy(ref, other)
            dx, dy = px - ox, py - oy
        else:
            cx, cy = self.centre(ref)
            dx, dy = px - cx, py - cy
        if abs(dx) >= abs(dy):
            return (1.0 if dx >= 0 else -1.0, 0.0)
        return (0.0, 1.0 if dy >= 0 else -1.0)

    # ---- the LO pairs' blocks -----------------------------------------------------------------
    # each synthesizer's RFOUTA pair and the mixer pins it faces: (synthesizer, P, N, mixer, P's pin, N's pin).
    # P goes to LOIN and N to LOIP (sheets 1 and 2): the pins then face each other, and the pair runs
    # straight (P to LOIP crossed it, and one leg went 40 mm round: the design review)
    LO_LINKS = [("U115", "12", "13", "U104", "10", "9"), ("U203", "12", "13", "U201", "4", "3")]
    LO_PITCH = 1.2                       # the legs' centres where the DC blocks stand side by side (0.58 mm between their pads)
    LO_RUN = 1.4                         # straight out of each 0.5 mm pitch pin first (gen/routes.PIN_RUN)
    LO_CHOKE_GAP = 0.35                  # between a block's pad and its choke's (the choke's stub: a pad and this)
    LO_CORRIDOR = 1.05                   # half the pair's corridor: a leg's line edge (0.745) and room for its gap

    def lo_blocks(self):
        """The LO pairs, mirror images of each other leg for leg (CLAUDE_PCB.md section 5: a
        differential pair is two equal lines): out of each pin straight for LO_RUN, a jog out to
        LO_PITCH, the two DC blocks of each leg side by side (the mixer's near the mixer, the
        synthesizer's near the synthesizer), and each RFOUTA pull-up choke beside its leg's
        synthesizer-side block, outboard, its rail end away from the line.  Every one is pinned:
        nothing pushes one leg's part and not the other's."""
        self.lo_parts = set()
        self.lo_corridors = []
        for syn, sp, sn, mix, mp, mn in self.LO_LINKS:
            if syn not in self.pos or mix not in self.pos:
                continue
            xs_p, ys = self.pad_xy(syn, sp)
            xs_n, _ = self.pad_xy(syn, sn)
            xm_p, ym = self.pad_xy(mix, mp)
            xm_n, _ = self.pad_xy(mix, mn)
            assert abs(xm_p - xs_p) < 0.01 and abs(xm_n - xs_n) < 0.01, \
                "%s/%s: the LO pins do not face each other (%.2f/%.2f against %.2f/%.2f)" % (syn, mix, xs_p, xs_n, xm_p, xm_n)
            u = 1.0 if ys > ym else -1.0                     # along the pair, mixer to synthesizer
            half = lambda ref, pin: max(self.fp(ref)["pads"][pin][2:]) / 2
            tip_m = ym + u * half(mix, mp)                   # the pins' outer ends
            tip_s = ys - u * half(syn, sp)
            xc = (xs_p + xs_n) / 2
            jog = self.LO_PITCH / 2 - abs(xs_p - xs_n) / 2
            cap_half = max(abs(v[0]) + v[2] / 2 for v in self.fp(self._lo_part(syn, sp, "C"))["pads"].values())
            y_mcap = tip_m + u * (self.LO_RUN + jog + 0.1 + cap_half)
            y_scap = tip_s - u * (self.LO_RUN + jog + 0.1 + cap_half)
            # the pair's corridor, pin row to pin row: no other part's courtyard within LO_CORRIDOR of the
            # pair's centre line (R209 stood 0.1 mm from the N leg's line: build 18's first placement)
            self.lo_corridors.append((xc - self.LO_CORRIDOR, min(tip_m, tip_s), xc + self.LO_CORRIDOR, max(tip_m, tip_s)))
            for pin_s, pin_m, xs in ((sp, mp, xs_p), (sn, mn, xs_n)):
                side = 1.0 if xs > xc else -1.0
                x = xc + side * self.LO_PITCH / 2
                snet, mnet = self.pin_net[(syn, pin_s)], self.pin_net[(mix, pin_m)]
                scap, mcap = self._lo_part(syn, pin_s, "C"), self._lo_part(mix, pin_m, "C")
                self._pin_two(scap, (x, y_scap), snet, (0.0, u))           # its synthesizer-side pad toward the synthesizer
                self._pin_two(mcap, (x, y_mcap), mnet, (0.0, -u))          # its mixer-side pad toward the mixer
                choke = self._lo_part(syn, pin_s, "L")
                if choke:
                    cpads = self.fp(choke)["pads"]
                    c_half = max(abs(v[0]) for v in cpads.values())
                    c_padw = max(v[2] for v in cpads.values()) / 2
                    sx, sy = self.pad_xy(scap, next(n for n in self.fp(scap)["pads"] if self.pin_net.get((scap, n)) == snet))
                    reach = 0.31 + self.LO_CHOKE_GAP + c_padw + c_half       # the block pad's half width (0.62 / 2), the gap, the choke pad, its centre
                    self._pin_two(choke, (x + side * reach, sy), snet, (-side, 0.0))   # its line pad inward
                self.lo_parts.update(p for p in (scap, mcap, choke) if p)

    def _lo_part(self, chip, pin, kind):
        """The one two-terminal part of `kind` ("C", "L") on the net at chip.pin (None if none)."""
        net = self.pin_net.get((chip, pin))
        found = [r for r, p in self.nets.get(net, []) if r != chip and r[0] == kind and len(self.fp(r)["pads"]) == 2]
        assert len(found) <= 1, (chip, pin, kind, found)
        return found[0] if found else None

    def _pin_two(self, ref, xy, net, toward):
        """Pin a two-terminal part at xy, turned so its pad on `net` points along `toward`."""
        pads = self.fp(ref)["pads"]
        sig = next(n for n in pads if self.pin_net.get((ref, n)) == net)
        for rot in (0, 90, 180, 270):
            px, py = place_pt(pads[sig][:2], at(xy[0], xy[1], rot))
            if (px - xy[0]) * toward[0] + (py - xy[1]) * toward[1] > 0.1:
                break
        self.pos[ref] = at(xy[0], xy[1], rot)
        self.want[ref] = toward
        self.on_line.add(ref)
        self.group[ref] = self.group.get(self._lo_owner(ref))

    def _lo_owner(self, ref):
        for syn, sp, sn, mix, mp, mn in self.LO_LINKS:
            for chip, pin in ((syn, sp), (syn, sn), (mix, mp), (mix, mn)):
                if ref in [r for r, p in self.nets.get(self.pin_net.get((chip, pin)), [])]:
                    return chip
        return None

    # ---- the rules ------------------------------------------------------------------------
    def anchors_on(self, net, exclude):
        """Placed pads on `net` (ref, pin, x, y), chips first."""
        out = []
        for ref, pin in self.nets.get(net, []):
            if ref == exclude or ref not in self.pos:
                continue
            x, y = self.pad_xy(ref, pin)
            out.append((ref, pin, x, y))
        def prio(t):
            ref = t[0]
            if ref[0] in "UQYTD":
                return 0
            if ref.startswith(("JP", "J3")):
                return 2
            if ref[0] == "J":
                return 3
            return 1
        out.sort(key=lambda t: (prio(t), t[0]))
        return out

    def place_two_terminal(self, ref):
        pads = self.fp(ref)["pads"]
        nums = sorted(pads, key=lambda n: (len(n), n))
        n1, n2 = nums[0], nums[1]
        net1, net2 = self.pin_net.get((ref, n1)), self.pin_net.get((ref, n2))
        a1 = self.anchors_on(net1, ref) if net1 and not is_rail(net1) else []
        a2 = self.anchors_on(net2, ref) if net2 and not is_rail(net2) else []
        half = abs(pads[n2][0] - pads[n1][0]) / 2 or abs(pads[n2][1] - pads[n1][1]) / 2
        court = self.fp(ref)["court"]
        clen = (court[2] - court[0]) / 2
        # a shunt: one end on a signal pad, the other on a rail or ground
        if (a1 and not a2 and (net2 is None or is_rail(net2))) or (a2 and not a1 and (net1 is None or is_rail(net1))):
            sig_pin, anchors = (n1, a1) if a1 else (n2, a2)
            aref, apin, ax, ay = anchors[0]
            nx, ny = self.side_normal(aref, apin)
            abox = self.bbox(aref)
            gap = GAP + self.escape(aref)
            # stand it outside the anchor's courtyard, the signal pad nearest the chip
            if nx:
                edge = abox[2] if nx > 0 else abox[0]
                cx = edge + nx * (gap + clen)
                cy = ay
                rot = 0 if (nx > 0) == (pads[sig_pin][0] < pads[n2 if sig_pin == n1 else n1][0]) else 180
            else:
                edge = abox[3] if ny > 0 else abox[1]
                cy = edge + ny * (gap + clen)
                cx = ax
                # at rot 90 local +x lands at -y (up), so pad 1 (local -x) lands BELOW: a part below the
                # chip (ny > 0) whose signal pad is pad 1 wants rot 270 (Response 9: every shunt above or
                # below a chip had its signal pad on the far side until this was turned round)
                rot = 270 if (ny > 0) == (pads[sig_pin][0] < pads[n2 if sig_pin == n1 else n1][0]) else 90
            self.pos[ref] = at(cx, cy, rot)
            self.want[ref] = (nx, ny)
            self.group[ref] = self.group.get(aref)
            return True
        # a series part: between the nearest pair of anchors
        if a1 and a2:
            best = min(((math.hypot(p[2] - q[2], p[3] - q[3]), p, q) for p in a1 for q in a2), key=lambda t: t[0])
            _, p, q = best
            mx, my = (p[2] + q[2]) / 2, (p[3] + q[3]) / 2
            dx, dy = q[2] - p[2], q[3] - p[3]
            L = math.hypot(dx, dy) or 1.0
            # two chip pins that are not in line (the LO pair's blocks between two QFNs, the I/Q
            # series resistors): the part stands straight out of the finer chip's pin, so the planned
            # line leaves the pad along its axis and the bend comes after the part, not in front of
            # the pins beside it (Response 9)
            big = [t for t in (p, q) if t[0][0] in "UT" and len(self.fp(t[0])["pads"]) >= 5]
            # the line from the chip pin to the far end: is it along the pin's own axis?
            def along(t):
                nx, ny = self.side_normal(t[0], t[1])
                o = q if t is p else p
                ox, oy = o[2] - t[2], o[3] - t[3]
                Lo = math.hypot(ox, oy) or 1.0
                return (ox * nx + oy * ny) / Lo > 0.87            # within 30 degrees
            if big and (p[0] == q[0] or not all(along(t) for t in big)):
                if p[0] == q[0]:
                    # both ends on one chip (a loop filter's R3 from CP_OUT to TUNE): off the pin whose
                    # net has the fewer members, never across the chip
                    host = p if len(self.nets[net1]) <= len(self.nets[net2]) else q
                else:
                    host = max(big, key=lambda t: len(self.fp(t[0])["pads"]))
                near = n1 if host is p else n2
                self.place_shunt(ref, near, host[0], host[1])
                self.group[ref] = self.group.get(host[0])
                self.stagger(ref, host[0], host[1])
                return True
            if abs(dx) >= abs(dy):
                rot = 0 if (dx > 0) == (pads[n1][0] < pads[n2][0]) else 180
            else:
                rot = 270 if (dy > 0) == (pads[n1][0] < pads[n2][0]) else 90
            # pushed ALONG its line when it collides (sideways would bend the RF chains: Response 8)
            self.want[ref] = (dx / L, dy / L) if math.hypot(p[2] - mx, p[3] - my) < 4.0 else (-dx / L, -dy / L)
            self.pos[ref] = at(mx, my, rot)
            if any(abs(p[2] - cx) < 0.4 and abs(q[2] - cx) < 0.4 for cx in (RX_X, TX_X)):
                self.on_line.add(ref)
            self.group[ref] = self.group.get(p[0]) or self.group.get(q[0])
            return True
        # one end known, the other end's net has nothing placed yet: hang it off the known pad
        # along the chip's side, its free end outward (the next part of the chain follows it)
        if a1 or a2:
            known_pin, anchors = (n1, a1) if a1 else (n2, a2)
            aref, apin, ax, ay = anchors[0]
            nx, ny = self.side_normal(aref, apin)
            abox = self.bbox(aref)
            gap = GAP + self.escape(aref)
            if nx:
                cx = (abox[2] if nx > 0 else abox[0]) + nx * (gap + clen)
                cy = ay
                rot = 0 if (nx > 0) == (pads[known_pin][0] < pads[n2 if known_pin == n1 else n1][0]) else 180
            else:
                cy = (abox[3] if ny > 0 else abox[1]) + ny * (gap + clen)
                cx = ax
                rot = 270 if (ny > 0) == (pads[known_pin][0] < pads[n2 if known_pin == n1 else n1][0]) else 90
            self.pos[ref] = at(cx, cy, rot)
            self.want[ref] = (nx, ny)
            self.group[ref] = self.group.get(aref)
            return True
        return False

    def place_other(self, ref):
        """Anything else: beside the placed part it shares most nets with."""
        count = collections.Counter()
        for num in self.fp(ref)["pads"]:
            net = self.pin_net.get((ref, num))
            if not net or is_rail(net):
                continue
            for oref, _ in self.nets[net]:
                if oref != ref and oref in self.pos:
                    count[oref] += 1
        if not count:
            return False
        host = count.most_common(1)[0][0]
        hb = self.bbox(host)
        court = self.fp(ref)["court"]
        self.pos[ref] = at(hb[2] + GAP + (court[2] - court[0]) / 2, (hb[1] + hb[3]) / 2, 0)
        self.want[ref] = (1.0, 0.0)
        self.group[ref] = self.group.get(host)
        return True

    def rail_caps(self):
        """Parts between two rails (a decoupling capacitor, a bulk capacitor): at the rail pad of the
        chip the schematic drew them beside, one per pad in the schematic's left-to-right order."""
        groups = collections.defaultdict(list)
        for ref in sorted(self.comps, key=refkey):
            if ref in self.pos:
                continue
            pads = self.fp(ref)["pads"]
            if len(pads) != 2:
                continue
            nums = sorted(pads, key=lambda n: (len(n), n))
            nets = [self.pin_net.get((ref, n)) for n in nums]
            if not all(nets) or not all(is_rail(n) for n in nets):
                continue
            rail = next((n for n in nets if n != "GND"), None)
            if rail is None or ref not in self.sch:
                continue
            sheet, sx, sy = self.sch[ref]
            best = None
            for oref, opin in self.nets[rail]:
                if oref == ref or oref not in self.pos or len(self.fp(oref)["pads"]) <= 2 or oref not in self.sch:
                    continue
                osheet, ox, oy = self.sch[oref]
                if osheet != sheet:
                    continue
                d = math.hypot(ox - sx, oy - sy)
                if best is None or d < best[0]:
                    best = (d, oref)
            if best is None:                       # no chip on this sheet: the nearest hand-placed part on the rail
                for oref, opin in self.nets[rail]:
                    if oref == ref or oref not in ANCHORS or oref not in self.sch:
                        continue
                    osheet, ox, oy = self.sch[oref]
                    d = math.hypot(ox - sx, oy - sy) + (0.0 if osheet == sheet else 1000.0)
                    if best is None or d < best[0]:
                        best = (d, oref)
            if best is None:
                continue
            groups[(best[1], rail)].append((sx, ref, nums, nets))
        for (owner, rail), caps in groups.items():
            pads = sorted([(self.pad_xy(owner, n)[0], n) for n in self.fp(owner)["pads"] if self.pin_net.get((owner, n)) == rail])
            caps.sort()
            for k, (sx, ref, nums, nets) in enumerate(caps):
                px, pnum = pads[k % len(pads)]
                sig_pin = nums[0] if nets[0] == rail else nums[1]
                self.place_shunt(ref, sig_pin, owner, pnum)

    def place_shunt(self, ref, sig_pin, aref, apin):
        pads = self.fp(ref)["pads"]
        nums = sorted(pads, key=lambda n: (len(n), n))
        other = nums[1] if sig_pin == nums[0] else nums[0]
        court = self.fp(ref)["court"]
        clen = (court[2] - court[0]) / 2
        ax, ay = self.pad_xy(aref, apin)
        nx, ny = self.side_normal(aref, apin)
        abox = self.bbox(aref)
        gap = GAP + self.escape(aref)
        if nx:
            cx = (abox[2] if nx > 0 else abox[0]) + nx * (gap + clen)
            cy = ay
            rot = 0 if (nx > 0) == (pads[sig_pin][0] < pads[other][0]) else 180
        else:
            cy = (abox[3] if ny > 0 else abox[1]) + ny * (gap + clen)
            cx = ax
            rot = 270 if (ny > 0) == (pads[sig_pin][0] < pads[other][0]) else 90
        self.pos[ref] = at(cx, cy, rot)
        self.want[ref] = (nx, ny)
        self.group[ref] = self.group.get(aref)

    def stagger(self, ref, chip, pin):
        """A second series part straight out of the pin beside one that has one already (the I and Q
        pairs' resistors, the LO blocks): 2.2 mm further out and 0.7 mm to the side, away from the
        first, so neither line runs through the other's part (Response 9)."""
        used = self.__dict__.setdefault("pin_series", {})
        px, py = self.pad_xy(chip, pin)
        nx, ny = self.side_normal(chip, pin)
        for (c, q), (qx, qy, qref) in list(used.items()):
            if c != chip or math.hypot(qx - px, qy - py) > 0.6:
                continue
            L = math.hypot(px - qx, py - qy) or 1.0
            ux, uy = (px - qx) / L, (py - qy) / L                  # along the row, away from the first pin
            x, y, rot, side = self.pos[ref]
            self.pos[ref] = at(x + nx * 2.2 + ux * 0.7, y + ny * 2.2 + uy * 0.7, rot, side)
            break
        used[(chip, pin)] = (px, py, ref)

    def escape(self, ref):
        """Room left between a fine-pitch chip's courtyard and the parts at its pins, so a 0.15 mm
        track can leave the pin beside a part (CLAUDE_PCB.md section 5: a capacitor straight in
        front of a signal pin blocks it and both neighbours)."""
        return FAN_BAND if len(self.fp(ref)["pads"]) >= 16 else 0.0

    def bands(self):
        """The fan-out band round every fine-pitch chip (courtyard grown by FAN_BAND): no part
        may stand in it (gen/routes.fan puts the pins' vias there; a capacitor straight in front
        of a signal pin blocks it and both neighbours)."""
        if not hasattr(self, "_bands"):
            self._bands = []
            for ref in self.pos:
                if ref in ANCHORS and len(self.fp(ref)["pads"]) >= 16 and ref[0] == "U":
                    x0, y0, x1, y1 = self.bbox(ref)
                    self._bands.append((ref, (x0 - FAN_BAND, y0 - FAN_BAND, x1 + FAN_BAND, y1 + FAN_BAND)))
        return self._bands

    def auto(self):
        self.lo_blocks()
        self.rail_caps()
        todo = [r for r in sorted(self.comps, key=refkey) if r not in self.pos]
        for _ in range(8):
            left = []
            for ref in todo:
                pads = self.fp(ref)["pads"]
                ok = self.place_two_terminal(ref) if len(pads) == 2 else self.place_other(ref)
                if not ok:
                    left.append(ref)
            if not left or len(left) == len(todo):
                todo = left
                break
            todo = left
        for ref in todo:                           # nowhere to hang it: park it, and say so
            self.report.append("%s (%s) has no placed neighbour: parked" % (ref, self.comps[ref]["value"]))
            self.pos[ref] = at(100.0 + 3.0 * (len(self.report) % 5), 82.0, 0)
            self.want[ref] = (0.0, 1.0)

    # ---- pushing apart ---------------------------------------------------------------------
    def fixed(self, ref):
        return ref in ANCHORS or ref in getattr(self, "lo_parts", ())

    def blocked(self, ref, pos):
        """Why a part at `pos` cannot be there: another courtyard, the edge, the socket's pads."""
        b = bbox_of(self.fp(ref)["court"], pos)
        side = pos[3]
        W, H = BOARD["w"], BOARD["h"]
        if not ("SMA" in self.comps[ref]["fp"] or "USB" in self.comps[ref]["fp"]):
            if b[0] < EDGE_KEEP or b[1] < EDGE_KEEP or b[2] > W - EDGE_KEEP or b[3] > H - EDGE_KEEP:
                return "edge"
        if side == "F" and hit(b, SOCKET_KEEP, 0.0) and ref != "J302":
            return "socket"
        for kb in MARK_KEEP:
            if hit(b, kb, 0.0):
                return "a fiducial or the layer marks"
        if side == "F" and ref not in ANCHORS:
            for owner, strip in self.strips:
                if owner != ref and hit(b, strip, 0.0):
                    return owner + " label"
        if side == "F" and ref not in ANCHORS and ref not in self.on_line:
            for cref, band in self.bands():
                if hit(b, band, 0.0):
                    return cref + " fan band"
            if True:
                for c in CORRIDORS:
                    if hit(b, c, 0.0):
                        return "RF corridor"
                for c in getattr(self, "lo_corridors", ()):
                    if hit(b, c, 0.0) and ref not in self.lo_parts:
                        return "LO corridor"
        for oref, opos in self.pos.items():
            if oref == ref:
                continue
            if opos[3] != side and not (self.fp(oref)["tht"] or self.fp(ref)["tht"]):
                continue
            lo = getattr(self, "lo_parts", ())
            if hit(b, self.bbox(oref), 0.0 if (ref in lo and oref in lo) else GAP):
                return oref
            # a vendored courtyard can be smaller than its pads (the SMA's legs): test the pads too
            if self.fp(oref)["tht"]:
                for num, (px, py, w, h) in self.fp(oref)["pads"].items():
                    x, y = place_pt((px, py), opos)
                    r = max(w, h) / 2
                    if hit(b, (x - r, y - r, x + r, y + r), 0.2):
                        return oref + " pad " + num
        return None

    def resolve(self, passes=40):
        movable = [r for r in self.pos if not self.fixed(r)]
        for _ in range(passes):
            moved = 0
            for ref in movable:
                why = self.blocked(ref, self.pos[ref])
                if why is None:
                    continue
                x, y, rot, side = self.pos[ref]
                nx, ny = self.want.get(ref, (0.0, 1.0))
                found = None
                # straight outward first (two parts at adjacent pins then stagger along their axes,
                # which keeps a planned line straight: Response 9), then sideways, then a spiral
                for d in [k * 0.25 for k in range(1, 13)]:
                    if self.blocked(ref, (x + nx * d, y + ny * d, rot, side)) is None:
                        found = (x + nx * d, y + ny * d)
                        break
                    if ref in self.on_line and self.blocked(ref, (x - nx * d, y - ny * d, rot, side)) is None:
                        found = (x - nx * d, y - ny * d)
                        break
                if ref in self.on_line and found is None:
                    continue                       # never sideways off an RF line: reported below
                for d in ([] if found else [k * 0.25 for k in range(1, 40)]):
                    cands = [(x + nx * d, y + ny * d), (x + ny * d, y - nx * d), (x - ny * d, y + nx * d),
                             (x + nx * d + ny * d, y + ny * d - nx * d), (x + nx * d - ny * d, y + ny * d + nx * d)]
                    for cx, cy in cands:
                        if self.blocked(ref, (cx, cy, rot, side)) is None:
                            found = (cx, cy)
                            break
                    if found:
                        break
                if found is None:
                    for d in [k * 0.5 for k in range(1, 30)]:
                        for ang in range(0, 360, 30):
                            cx, cy = x + d * math.cos(math.radians(ang)), y + d * math.sin(math.radians(ang))
                            if self.blocked(ref, (cx, cy, rot, side)) is None:
                                found = (cx, cy)
                                break
                        if found:
                            break
                if found:
                    self.pos[ref] = at(found[0], found[1], rot, side)
                    moved += 1
            if not moved:
                break
        bad = []
        for ref in self.pos:
            why = self.blocked(ref, self.pos[ref])
            if why:
                bad.append((ref, why))
        return bad

    # ---- checks -------------------------------------------------------------------------
    def check(self):
        """The RF chains' pads on their lines; the socket's pins where the PYNQ's are."""
        probs = []
        for ref, num, x_want in (("U101", "3", RX_X), ("U101", "4", RX_X), ("U102", "5", RX_X), ("U102", "14", RX_X),
                                 ("U103", "1", RX_X), ("U103", "3", RX_X), ("U117", "1", RX_X), ("U117", "3", RX_X),
                                 ("CP101", "1", RX_X), ("CP101", "2", RX_X), ("T101", "1", RX_X), ("J101", "1", RX_X),
                                 ("U201", "16", TX_X - 0.25), ("U202", "1", TX_X), ("U202", "3", TX_X),
                                 ("CP201", "1", TX_X), ("CP201", "2", TX_X), ("J202", "1", TX_X)):
            x, y = self.pad_xy(ref, num)
            if abs(x - x_want) > 0.05:
                probs.append("%s.%s at x %.2f, wanted %.2f" % (ref, num, x, x_want))
        for n in (1, 2, 3, 39, 40):
            x, y = self.pad_xy("J302", str(n))
            wx, wy = hdr_pin(n)
            if abs(x - wx) > 0.05 or abs(y - wy) > 0.05:
                probs.append("socket pin %d at (%.2f, %.2f), the PYNQ's is at (%.2f, %.2f)" % (n, x, y, wx, wy))
        for ref in ("H301", "H302", "H303"):
            x, y = self.pos[ref][:2]
            if PZ_SHADOW[0] <= x <= PZ_SHADOW[2] and y >= PZ_SHADOW[1]:
                probs.append("%s is a desk standoff in the PYNQ's shadow" % ref)
        return probs


def plan():
    P = Plan()
    P.auto()
    bad = P.resolve()
    probs = P.check()
    for ref, why in bad:
        P.report.append("%s (%s) still overlaps %s" % (ref, P.comps[ref]["value"], why))
    for ref, pos in P.pos.items():                 # a part placed by hand in a name's strip: move one of them
        if ref in ANCHORS and pos[3] == "F":       # (its pads, what the silkscreen keeps clear of, not its courtyard)
            pads = [(P.pad_xy(ref, n), pad_wh(P, ref, n)) for n in P.fp(ref)["pads"]]
            if not pads:
                continue
            pb = (min(q[0] - d[0] / 2 for q, d in pads) - 0.15, min(q[1] - d[1] / 2 for q, d in pads) - 0.15,
                  max(q[0] + d[0] / 2 for q, d in pads) + 0.15, max(q[1] + d[1] / 2 for q, d in pads) + 0.15)
            for owner, strip in P.strips:          # the strips are estimates (0.92 x width a character): a tenth of a
                                                   # millimetre is theirs; gen/silk_jacks.py and tools/label_check.py judge
                if owner != ref and hit(pb, strip, -0.1) and not hit(P.bbox(owner), P.bbox(ref), 0.0):
                    P.report.append("%s (%s) sits in %s's label strip" % (ref, P.comps[ref]["value"], owner))
    P.report += probs
    return P


def write(P):
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    out = {ref: list(P.pos[ref]) for ref in sorted(P.pos, key=refkey)}
    json.dump(dict(board=BOARD, place=out, report=P.report, pz_hole=PZ_HOLE, socket_keep=SOCKET_KEEP,
                   strips=[[o, [round(v, 3) for v in r]] for o, r in P.strips],
                   group={r: g for r, g in P.group.items() if g}, blocks=list(BLOCKS)),
              open(os.path.join(ROOT, "build", "placement.json"), "w"), indent=1)


def draw(P, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle, Circle
    W, H = BOARD["w"], BOARD["h"]
    fig, ax = plt.subplots(figsize=(W / 8.0, H / 8.0), dpi=200)
    ax.add_patch(Rectangle((0, 0), W, H, fill=False, lw=1.0, color="k"))
    ax.add_patch(Rectangle((PZ_SHADOW[0], PZ_SHADOW[1]), PZ_SHADOW[2] - PZ_SHADOW[0], PZ_SHADOW[3] - PZ_SHADOW[1], color="#dddddd", lw=0))
    ax.add_patch(Rectangle((SOCKET_KEEP[0], SOCKET_KEEP[1]), SOCKET_KEEP[2] - SOCKET_KEEP[0], SOCKET_KEEP[3] - SOCKET_KEEP[1], fill=False, ls=":", lw=0.5, color="k"))
    for ref, pos in P.pos.items():
        b = P.bbox(ref)
        big = len(P.fp(ref)["pads"]) > 2 or ref.startswith(("J", "Y", "TP", "H", "CP"))
        back = pos[3] == "B"
        col = "#c0392b" if ref in ANCHORS else ("#2980b9" if not P.comps[ref]["dnp"] else "#95a5a6")
        ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fill=big, alpha=0.25 if big else 1.0,
                               lw=0.4, ec=col, fc=col, ls="--" if back else "-"))
        for num, (x, y, w, h) in P.fp(ref)["pads"].items():
            px, py = place_pt((x, y), pos)
            ax.add_patch(Circle((px, py), 0.12, color="#555555", lw=0))
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        ax.text(cx, cy, ref if big else ref.replace("C", "C").replace("R", "R"), ha="center", va="center",
                fontsize=3.0 if big else 1.6, color="k")
    ax.set_xlim(-2, W + 2); ax.set_ylim(H + 2, -2); ax.set_aspect("equal"); ax.axis("off")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def main():
    P = plan()
    write(P)
    draw(P, os.path.join(ROOT, "build", "view", "placement.png"))
    n_auto = sum(1 for r in P.pos if r not in ANCHORS)
    print("placement: %d parts, %d by hand, %d by rule; %d problem(s) -> build/placement.json, build/view/placement.png"
          % (len(P.pos), len(P.pos) - n_auto, n_auto, len(P.report)))
    for line in P.report:
        print("   " + line)
    return 1 if P.report else 0


if __name__ == "__main__":
    sys.exit(main())
