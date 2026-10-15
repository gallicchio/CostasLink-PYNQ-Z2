"""Footprints drawn for CostasLink (the rest are KiCad's; the SMA is the ECP5 board's vendored copy).

SKY65404-31_QFN-6_1.5x1.5mm
    JLCPCB's own land pattern for C210262 (EasyEDA "DFN-6_L1.5-W1.5-P0.50-BL-EP1.2", read through
    mfg/footprint_check.land_pattern on 2026-10-09): six 0.28 x 0.30 pads at x = -0.5, 0, +0.5 on
    rows y = +-0.704 (pins 1-3 along y = +0.704 left to right, 4-6 along y = -0.704 right to left,
    EasyEDA's numbering), and a 1.3 x 0.8 exposed pad (pin 7).  Using JLCPCB's drawing means the
    part fits by construction and the CPL rotation prediction is exact.  Skyworks' Figure 11
    agrees within 0.05 mm (0.25 x 0.55 pads at 0.50 pitch, rows 1.20 apart outer edge).

Balun_Johanson_5400BL15B050
    From the Johanson drawing (datasheet page 1, "Mounting Considerations", read 2026-10-09):
    body 2.00 x 1.25 mm; six terminals, three per long side at 0.65 mm pitch; land pads 0.35 wide
    and 0.80 long, their outer edges 1.0 mm from the centre line (so centred at y = +-0.60).
    Terminal figure (brown mark up): 3, 2, 1 along the top row left to right, 4, 5, 6 along the
    bottom row left to right.  So pin 1 (unbalanced) is top right, 6 (NC) bottom right, and the
    balanced pair 3/4 leaves the LEFT end on both rows; 2 and 5 (GND) are the middle pads.  The
    brown mark's corner is drawn on the silkscreen at pad 1.  No JLCPCB drawing exists for this
    part (consigned), so the CPL rotation must be read in the preview.

Balun_TDK_HHM1907B1
    The balun fitted since Prompt 31 (the Johanson above is kept for the record).  From TDK's drawing
    (rf_balun_hhm1907b1_en, "Recommended land pattern", read 2026-10-14): body 1.0 x 0.5 mm; four
    terminals, two per end; land pads 0.30 wide and 0.35 long, outer edges 0.80 apart in x and 0.90 in y
    (so centred at x = +-0.25, y = +-0.275).  Terminal figure (top view, marking up): 4 and 3 along the
    top row left to right, 1 and 2 along the bottom row left to right.  So 1 (unbalanced) is bottom left,
    4 (GND) above it, and the balanced pair 2 (bottom) / 3 (top) is the RIGHT end.  Half-turn symmetric
    pads, so a silkscreen dot marks pad 1.  JLCPCB stocks it (C531388), so mfg/footprint_check.py compares
    these pads with their drawing and the CPL rotation is predicted from it.

RPi_Socket_2x20_P2.54mm_Underside
    The 2x20 socket (C2977589, 8.5 mm insulator), the GPSDO-PYNQ-Z2 board's drawing: pin 1 at the
    origin, odd pins along -x from it, the even row at +2.54 in y, 1.0 mm holes in 1.7 mm pads,
    pad 1 square.  Drawn as a front-side footprint and placed on the BACK by gen/board.py (KiCad's
    flip mirrors y), which is what puts the PYNQ's pin 1 under our pin 1.  JLCPCB's drawing of
    C2977589 (HDR-TH_40P-P2.54-V-F-R2-C20-S2.54) has the same 1.0 mm holes on the same grid.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
VENDORED = os.path.join(HERE, "vendored")

HEAD = '''(footprint "%(name)s"
	(version 20240108)
	(generator "costaslink")
	(generator_version "10.0")
	(layer "F.Cu")
	(descr "%(descr)s")
	(tags "%(tags)s")
	(attr %(attr)s)
	(property "Reference" "REF**" (at 0 %(refy)g 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))
	(property "Value" "%(name)s" (at 0 %(valy)g 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))
'''


def _rect(x0, y0, x1, y1, layer, w):
    return ('\t(fp_rect (start %g %g) (end %g %g) (stroke (width %g) (type solid)) (fill no) (layer "%s"))'
            % (x0, y0, x1, y1, w, layer))


def _line(x0, y0, x1, y1, layer, w):
    return ('\t(fp_line (start %g %g) (end %g %g) (stroke (width %g) (type solid)) (layer "%s"))'
            % (x0, y0, x1, y1, w, layer))


def _smd(num, x, y, w, h, shape="roundrect"):
    rr = ' (roundrect_rratio 0.25)' if shape == "roundrect" else ''
    return ('\t(pad "%s" smd %s (at %g %g) (size %g %g) (layers "F.Cu" "F.Paste" "F.Mask")%s)'
            % (num, shape, x, y, w, h, rr))


def _tht(num, x, y, d, drill, shape="circle"):
    return ('\t(pad "%s" thru_hole %s (at %g %g) (size %g %g) (drill %g) (layers "*.Cu" "*.Mask") (remove_unused_layers no))'
            % (num, shape, x, y, d, d, drill))


def sky65404():
    L = [HEAD % dict(name="SKY65404-31_QFN-6_1.5x1.5mm", descr="Skyworks SKY65404-31, QFN-6 1.5x1.5 mm; JLCPCB's land pattern for C210262",
                     tags="LNA QFN", attr="smd", refy=-1.8, valy=1.8)]
    L.append(_rect(-0.75, -0.75, 0.75, 0.75, "F.Fab", 0.1))
    L.append(_rect(-1.1, -1.1, 1.1, 1.1, "F.CrtYd", 0.05))
    # silkscreen: two short lines clear of the pads, and a pin-1 dot beside pad 1 (x -0.5, y +0.704)
    L.append(_line(-0.95, -0.2, -0.95, 0.2, "F.SilkS", 0.15))
    L.append(_line(0.95, -0.2, 0.95, 0.2, "F.SilkS", 0.15))
    L.append('\t(fp_circle (center -1.0 1.0) (end -0.9 1.0) (stroke (width 0.15) (type solid)) (fill yes) (layer "F.SilkS"))')
    for n, (x, y) in enumerate(((-0.5, 0.704), (0.0, 0.704), (0.5, 0.704), (0.5, -0.704), (0.0, -0.704), (-0.5, -0.704)), 1):
        L.append(_smd(str(n), x, y, 0.28, 0.30))
    L.append('\t(pad "7" smd rect (at 0 0) (size 1.3 0.8) (layers "F.Cu" "F.Mask"))')
    # paste on the exposed pad: a 1.0 x 0.6 window (about 60 %)
    L.append('\t(pad "7" smd rect (at 0 0) (size 1.0 0.6) (layers "F.Paste"))')
    L.append(")\n")
    return "\n".join(L)


def balun():
    L = [HEAD % dict(name="Balun_Johanson_5400BL15B050", descr="Johanson 5400BL15B050 1:1 balun, 2.0x1.25 mm, 6 terminals at 0.65 mm pitch (datasheet drawing)",
                     tags="balun 0805", attr="smd", refy=-2.0, valy=2.0)]
    L.append(_rect(-1.0, -0.625, 1.0, 0.625, "F.Fab", 0.1))
    L.append(_rect(-1.3, -1.25, 1.3, 1.25, "F.CrtYd", 0.05))
    L.append(_line(-1.15, -0.3, -1.15, 0.3, "F.SilkS", 0.15))
    L.append(_line(1.15, -0.3, 1.15, 0.3, "F.SilkS", 0.15))
    # the brown mark is at pin 1: top right (y up on the datasheet = -y here)
    L.append('\t(fp_circle (center 1.35 -0.95) (end 1.45 -0.95) (stroke (width 0.15) (type solid)) (fill yes) (layer "F.SilkS"))')
    top = {"3": -0.65, "2": 0.0, "1": 0.65}         # y = -0.60 (top row in the datasheet's figure)
    bot = {"4": -0.65, "5": 0.0, "6": 0.65}         # y = +0.60
    for n, x in top.items():
        L.append(_smd(n, x, -0.60, 0.35, 0.80))
    for n, x in bot.items():
        L.append(_smd(n, x, 0.60, 0.35, 0.80))
    L.append(")\n")
    return "\n".join(L)


def balun_tdk():
    L = [HEAD % dict(name="Balun_TDK_HHM1907B1", descr="TDK HHM1907B1 1:1 balun 4.9-5.95 GHz, 1.0x0.5 mm, 4 terminals (datasheet land pattern)",
                     tags="balun 0402", attr="smd", refy=-1.3, valy=1.3)]
    L.append(_rect(-0.5, -0.25, 0.5, 0.25, "F.Fab", 0.1))
    L.append(_rect(-0.75, -0.55, 0.75, 0.55, "F.CrtYd", 0.05))
    # the marking is at pad 1's end: bottom left (y up on the datasheet = -y here)
    L.append('\t(fp_circle (center -0.75 0.6) (end -0.67 0.6) (stroke (width 0.15) (type solid)) (fill yes) (layer "F.SilkS"))')
    for n, (x, y) in {"1": (-0.25, 0.275), "2": (0.25, 0.275), "3": (0.25, -0.275), "4": (-0.25, -0.275)}.items():
        L.append(_smd(n, x, y, 0.30, 0.35))
    L.append(")\n")
    return "\n".join(L)


def rpi_socket():
    # Drawn as the MIRROR image of the socket seen from above: the odd row along -x and the even row
    # 2.54 ABOVE it (-y).  gen/board.py puts it on the back with pcbnew's Flip(), which (measured in
    # its check, 2026-10-09) mirrors y and leaves x, so on the board pin 3 lands 2.54 left of pin 1 and
    # the even row 2.54 toward the bottom edge: the PYNQ-Z2's header, pin for pin (gen/placement.py
    # hdr_pin, checked there and again in gen/board.py).
    L = [HEAD % dict(name="RPi_Socket_2x20_P2.54mm_Underside", descr="2x20 2.54 mm socket (C2977589), pin 1 at the origin, drawn mirrored (even row at -y) for the back side",
                     tags="raspberry pi header socket", attr="through_hole", refy=-4.5, valy=4.5)]
    x0, x1 = -19 * 2.54 - 1.4, 1.4
    y0, y1 = -2.54 - 1.4, 1.4
    for layer, w in (("F.SilkS", 0.15), ("F.CrtYd", 0.05), ("F.Fab", 0.1)):
        L.append(_rect(x0, y0, x1, y1, layer, w))
    for n in range(1, 41):
        col = (n - 1) // 2
        L.append(_tht(str(n), -col * 2.54, 0.0 if n % 2 else -2.54, 1.7, 1.0, "rect" if n == 1 else "circle"))
    L.append(")\n")
    return "\n".join(L)


def sma():
    """The ECP5 board's SMA footprint (JLCPCB's drawing of C496551, through easyeda2kicad), with
    its 3D model pointed at our library."""
    import re
    text = open(os.path.join(VENDORED, "SMA-TH_BWSMA-KWE-Z001.kicad_mod"), encoding="utf-8").read()
    text = text.replace('(footprint "SMA-TH_BWSMA-KWE-Z001"', '(footprint "SMA_BWSMA-KWE-Z001"', 1)
    # JLCPCB's drawing numbers the four legs 1-4 and the centre 5; the Conn_Coaxial symbol has pin 1 =
    # the centre conductor and pin 2 = the shield (Response 8: the netlist had the RF on a leg and the
    # centre pad with no net; tools/net_check.py now fails on any pad without a net)
    n = [0]
    def renum(m):
        n[0] += 1
        return '(pad "%s"' % ("1" if m.group(1) == "5" else "2")
    text = re.sub(r'\(pad "([1-5])"', renum, text)
    assert n[0] == 5, n
    # The centre pin's 2.0 mm ring on In1, In2 and B.Cu, where nothing connects to it, was 0.41 pF of excess
    # capacitance against the planes' 2.5 mm antipads: 66 ohm shunt at 5.8 GHz, 9 dB return loss, 0.6 dB a launch
    # (review B, Prompt 31).  No copper there but the plated hole, and gen/project.py's "SMA launch antipad" rule
    # keeps the planes 1.35 mm from the hole (a 4 mm antipad): about 12 % reflection instead of 35 %.
    i = text.index('(pad "1" thru_hole circle')
    j = text.index('(remove_unused_layers no)', i)            # the vendored pad's own line (a second one would be dropped)
    text = text[:j] + '(remove_unused_layers yes)\n\t\t(keep_end_layers yes)' + text[j + len('(remove_unused_layers no)'):]
    return text


def mmcx():
    """BWMMCX-KE (LCSC C5137198, datasheets/BWMMCX-KE_C5137198.pdf): a vertical through-hole MMCX
    jack, 3.6 mm square, 500 matings.  The land pattern is JLCPCB's (its EasyEDA footprint through
    easyeda2kicad, Response 10, checked against the datasheet's drawing): four 1.6 mm legs on 1.1 mm
    drills at (+-1.25, +-1.25), the centre pin 1.52 mm on a 0.92 mm drill at the origin.  Pin 1 =
    the centre, 2 = the legs (the Conn_Coaxial symbol), as the SMA.  A trace leaves the centre
    along either axis, between two legs (0.9 mm between their pads)."""
    L = [HEAD % dict(name="MMCX_BWMMCX-KE_Vertical", descr="MMCX jack, vertical, through-hole: Bat Wireless BWMMCX-KE (LCSC C5137198), 0-6 GHz, 500 cycles",
                     tags="MMCX coaxial vertical", attr="through_hole", refy=-3.2, valy=3.2)]
    L.append('\t(pad "1" thru_hole circle (at 0 0) (size 1.52 1.52) (drill 0.92) (layers "*.Cu" "*.Mask"))')
    for x, y in ((-1.25, -1.25), (-1.25, 1.25), (1.25, 1.25), (1.25, -1.25)):
        L.append('\t(pad "2" thru_hole circle (at %g %g) (size 1.6 1.6) (drill 1.1) (layers "*.Cu" "*.Mask"))' % (x, y))
    # the legs' pads reach 2.05 from the centre: the silk square clears them, the courtyard holds both
    L.append(_rect(-2.45, -2.45, 2.45, 2.45, "F.CrtYd", 0.05))
    L.append(_rect(-1.8, -1.8, 1.8, 1.8, "F.Fab", 0.1))
    L.append(_rect(-2.25, -2.25, 2.25, 2.25, "F.SilkS", 0.12))
    L.append(")\n")
    return "\n".join(L)


def coupler():
    """Two parallel quarter-wave CPWG lines (sim/rf_lines.py), the main line between pads 1 and 2,
    the coupled line between 3 (coupled port, at the input end) and 4 (isolated port); each pair
    is a net tie through the footprint's own copper.  The coupling of an edge-coupled pair at
    this gap is about -20 dB; it is a monitor port, so +-5 dB does not matter."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "sim"))
    import rf_lines
    w, gap, L_ = rf_lines.RF_W, rf_lines.RF_GAP, round(rf_lines.QUARTER_WAVE, 2)
    yc = -(w + gap)
    lines = [HEAD % dict(name="Coupler_20dB_5.8GHz_CPWG", descr="-20 dB coupled-line coupler, two %.2f mm lines %.2f mm wide, %.2f mm apart; a net tie" % (L_, w, gap),
                         tags="coupler net tie", attr="smd exclude_from_pos_files exclude_from_bom", refy=-4.0, valy=3.0)]
    lines.append('\t(net_tie_pad_groups "1,2" "3,4")')
    lines.append(_rect(-L_ / 2 - 0.5, yc - w, L_ / 2 + 0.5, w, "F.CrtYd", 0.05))
    lines.append(_rect(-L_ / 2, yc - w / 2, L_ / 2, w / 2, "F.Fab", 0.1))
    for num, x, y in (("1", -L_ / 2, 0.0), ("2", L_ / 2, 0.0), ("3", -L_ / 2, yc), ("4", L_ / 2, yc)):
        lines.append('\t(pad "%s" smd rect (at %g %g) (size %g %g) (layers "F.Cu"))' % (num, x, y, w, w))
    for y in (0.0, yc):
        lines.append('\t(fp_line (start %g %g) (end %g %g) (stroke (width %g) (type solid)) (layer "F.Cu"))' % (-L_ / 2, y, L_ / 2, y, w))
    lines.append(")\n")
    return "\n".join(lines)


def slot():
    """An M3 slot, 3.2 x 5.2 mm along x, for the standoff that screws into the PYNQ-Z2's own
    mounting hole: the two boards register through the 2x20 header, so the hole must give."""
    L = [HEAD % dict(name="MountingHole_Slot_3.2x5.2mm_M3", descr="M3 slot 3.2 x 5.2 mm, no copper; the standoff shared with the host board",
                     tags="mounting slot", attr="exclude_from_pos_files exclude_from_bom", refy=-4.0, valy=4.0)]
    L.append('\t(pad "" np_thru_hole oval (at 0 0) (size 5.2 3.2) (drill oval 5.2 3.2) (layers "*.Cu" "*.Mask"))')
    L.append('\t(fp_circle (center 0 0) (end 3.25 0) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))')
    L.append('\t(fp_circle (center 0 0) (end 3.25 0) (stroke (width 0.05) (type solid)) (fill no) (layer "B.CrtYd"))')
    L.append(")\n")
    return "\n".join(L)


def generated():
    return {"SKY65404-31_QFN-6_1.5x1.5mm": sky65404(), "Balun_Johanson_5400BL15B050": balun(), "Balun_TDK_HHM1907B1": balun_tdk(), "MountingHole_Slot_3.2x5.2mm_M3": slot(),
            "RPi_Socket_2x20_P2.54mm_Underside": rpi_socket(), "SMA_BWSMA-KWE-Z001": sma(), "MMCX_BWMMCX-KE_Vertical": mmcx(),
            "Coupler_20dB_5.8GHz_CPWG": coupler()}


# 3D models for these: (file in gen/vendored or KiCad's set, library or None for vendored)
MODELS = {"SMA_BWSMA-KWE-Z001": ("SMA-TH_5P-L14.5-W6.0-H9.6_BWSMA-KWE-Z001.wrl", None),
          "MMCX_BWMMCX-KE_Vertical": ("MMCX-TH_BWMMCX-KE.wrl", None),
          "RPi_Socket_2x20_P2.54mm_Underside": ("PinSocket_2x20_P2.54mm_Vertical.wrl", "Connector_PinSocket_2.54mm"),
          "SKY65404-31_QFN-6_1.5x1.5mm": (None, None), "MountingHole_Slot_3.2x5.2mm_M3": (None, None),
          "Balun_Johanson_5400BL15B050": ("C_0805_2012Metric.wrl", "Capacitor_SMD"),
          "Balun_TDK_HHM1907B1": ("C_0402_1005Metric.wrl", "Capacitor_SMD")}

if __name__ == "__main__":
    for k, v in generated().items():
        print(k, len(v.splitlines()), "lines")
