"""Drawing helpers shared by the three sheets (on top of gen/sch_util.py): a chip's supply bar
with one capacitor per pin, its ground pins to ground, pull-ups on pins that point up, DC blocks
on RF lines, a monitor tap (U.FL, MMCX or SMA by its name) through its series resistor, a comparator, a bias tee, a coupler's
monitor jack, and the MAX2871 synthesizer block, which the RX and TX sheets draw identically
(CLAUDE_PCB.md section 4: repeated blocks are identical tiles).

Geometry rules these keep: every wire is horizontal or vertical and ends on a pin or a junction;
no pin lands inside another wire; parts hanging off a line sit 7.62 mm apart so their texts do
not touch (alternating sides where they must be closer).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import sch_util as U
from sch_util import G, part, hpart, vpart, gnd, flag, W, J, label, note, nref, down, up, series, tp


def stub(pl, pin, dx=0.0, dy=0.0):
    """A wire from a pin out by (dx, dy); returns the end."""
    x, y = pl.pin(pin)
    e = (x + dx, y + dy)
    W((x, y), e)
    return e


def L(a, b, first="h"):
    """An L-shaped wire from a to b, horizontal first (or vertical first)."""
    if abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6:
        W(a, b)
        return
    c = (b[0], a[1]) if first == "h" else (a[0], b[1])
    W(a, c, b)


def cap_down(key, x, y, text="right", net="GND"):
    """A capacitor hanging from the node (x, y) to ground; returns its reference."""
    r, b = down(key, x, y, net=net, text=text)
    return r


def supply_bar(pl, pins, rail, cap="C 100nF", dy=12.7, bulk=None, side_caps=0, caps_side="right", cap_offset=0.0):
    """A bar above a chip's supply pins (which point up), one riser per pin, one rail flag at the
    bar's far end, and one capacitor per pin hanging from the bar midway between the pins (when
    the pins are 5.08 or more apart) or, when they are closer, `side_caps` capacitors beside the
    group at 7.62 mm (on `caps_side`).  `bulk` = a key for one more, at the capacitors' end."""
    pts = [pl.pin(n) for n in pins]
    y = pts[0][1]
    yb = y - dy
    xs = sorted(p[0] for p in pts)
    x0, x1 = xs[0], xs[-1]
    for x, _ in pts:
        W((x, y), (x, yb))
    pitch = min((b - a) for a, b in zip(xs, xs[1:])) if len(xs) > 1 else 99.0
    sgn = 1 if caps_side == "right" else -1
    if caps_side == "both":                                 # half the capacitors each side, the flag at the right end
        n = side_caps or len(pins)
        nl = n // 2
        caps_x = [x0 - 10.16 * (k + 1) for k in range(nl)] + [x1 + 10.16 * (k + 1) for k in range(n - nl)]
        xend = min(caps_x)
        xflag = max(caps_x) + (10.16 if bulk else 0.0)
        if bulk:
            caps_x.append(xflag)
            bulk = None
        W((xend, yb), (xflag + 5.08, yb))
        xflag += 5.08
        flag(rail, xflag, yb)
        for cx in caps_x:
            J(cx, yb); down(cap, cx, yb, text="right")
        for x, _ in pts:
            J(x, yb)
        return yb
    if side_caps or pitch < 10.16:                          # a capacitor's text needs 10.16 to the next one
        n = side_caps or len(pins)
        base = (x1 if sgn > 0 else x0) + sgn * cap_offset
        caps_x = [base + sgn * 10.16 * (k + 1) for k in range(n)]
    elif sgn < 0 and len(xs) == 1:
        caps_x = [x0 - 10.16]
    else:
        caps_x = [(a + b) / 2.0 for a, b in zip(xs, xs[1:])] + [x1 + 5.08]
    xend = (max(caps_x) if sgn > 0 else min(caps_x)) + sgn * (10.16 if bulk else 0.0)
    xflag = (x0 - 5.08) if sgn > 0 else (xend - 5.08)
    W((min(xflag, xend, x0), yb), (max(xflag, xend, x1), yb))
    flag(rail, xflag, yb)
    for k, cx in enumerate(caps_x):
        J(cx, yb)
        down(cap, cx, yb, text="right")
    if bulk:
        J(xend, yb)
        down(bulk, xend, yb, text="right" if sgn > 0 else "left")
    for x, _ in pts:
        if min(xflag, xend) < x < max(xflag, xend):
            J(x, yb)
    return yb


def bottom_gnd(pl, pins, drop=G):
    for n in pins:
        x, y = pl.pin(n)
        W((x, y), (x, y + drop))
        gnd(x, y + drop)


def side_gnd(pl, pins, dx=2.54):
    """Pins on a chip's right side, all ground: a bar beside the chip joins them, one ground below."""
    pts = [pl.pin(n) for n in pins]
    xb = pts[0][0] + dx
    ys = sorted(p[1] for p in pts)
    for x, y in pts:
        W((x, y), (xb, y))
        if y != ys[0]:
            J(xb, y)
    W((xb, ys[0]), (xb, ys[-1]))
    W((xb, ys[-1]), (xb, ys[-1] + G))
    gnd(xb, ys[-1] + G)


def pullup_top(pl, pin, key, rail, text="right"):
    """A pin pointing up tied to `rail` through a resistor (CE, enables, P/S)."""
    x, y = pl.pin(pin)
    up(key, x, y, rail, text=text, rise=G)


def adc_inputs(adc, lines, rkey="R 10k", ckey="C 100nF"):
    """An ADS1115's four RC input filters on its 2.54-pitch pins, the resistor between the source and the
    capacitor and the capacitor at the PIN: the resistor isolates the source from the 100 nF.  Review A of
    Prompt 31 found both ADCs drawn the other way round, the capacitor hanging from the source's end of the
    line, which put 100 nF straight on the fast arms' outputs (I_P, Q_P), on the VCXO's control line and on
    the loop error, and 100 nF on the log amp's and the peak hold's outputs: the fast arms shorted above a
    few kHz.  Each line now comes up from below on its own vertical, the bottom pin's nearest the chip, so no
    capacitor crosses another line: pin <- horizontal with the capacitor hanging from it <- vertical with the
    resistor standing in it <- the net label at its foot.  `lines` is ((pin, name), ...) top to bottom."""
    n = len(lines)
    y_r = adc.pin(lines[-1][0])[1] + 19.05                # the resistors in a row under the capacitors' ground flags
    for k, (pin, name) in enumerate(lines):
        px, py = adc.pin(pin)
        xk = px - 12.7 - 10.16 * (n - 1 - k)
        W((px, py), (xk, py))
        r = nref("R")                                     # the resistor's reference before the capacitor's: the
        J(xk + 2.54, py); down(ckey, xk + 2.54, py, text="right")   # same order as before, so no reference moves
        t, b = vpart(rkey, r, xk, y_r, text="right")
        W((xk, py), t)
        W(b, (xk, b[1] + 2.54))
        label(xk, b[1] + 2.54, name, size=1.0)


def dcblock(x0, y, x1, key="C 1.5pF", above=True):
    """A DC-blocking capacitor on a horizontal RF line from x0 to x1; returns (x1, y)."""
    xc = (x0 + x1) / 2.0
    a, b = series(key, xc, y, above=above)
    if abs(a[0] - x0) > 1e-6:
        W((x0, y), a)
    if abs(b[0] - x1) > 1e-6:
        W(b, (x1, y))
    return (x1, y)


def esd_shunt(x, y):
    """Prompt 28: an antenna jack's ESD and DC path: a 6.8 nH wirewound (LQW15AN6N8, self-resonant at 6.0 GHz
    or above) from the line to ground, on the jack's side of its DC block.  Across 4.9-6 GHz it is 400 ohm to
    1.5 k (about 0.05 dB); it carries static off a cable or an antenna that is not DC-grounded, and below
    ~1 GHz, where most of a touch's ESD energy is, it is a few ohms to ground.  Fitted since Prompt 29."""
    from sch_util import nref
    ref = nref("L")
    J(x, y)
    t, b = vpart("L6N8", ref, x, y + G + 3.81, value="6.8nH", text="left", fsize=1.0)
    W((x, y), t)
    gnd(*b)
    return ref


# Which jack each named port gets (Response 10, Jason: the five field ports to MMCX "or even SMA if
# there is room", the others to MMCX where there is room, the tight ones as they were).  The field
# ports are SMAs on the board's edges (REF OUT an MMCX: the edge near the VCXO is taken); three baseband monitors with room round them are vertical
# MMCX (500 matings); the 5.8 GHz couplers' taps stay U.FL (a through-hole centre pin is a stub at
# 5.8 GHz) and so do the taps boxed in by their stages.  The symbol (Conn_Coaxial) is the same for all.
JACK = {"TRIG A": "SMA", "TRIG B": "SMA", "TRIG IN": "SMA", "REF IN": "SMA", "REF OUT": "MMCX",
        "VC MON": "MMCX", "ERR MON": "MMCX", "I SLOW MON": "MMCX", "TRIG IN MON": "MMCX"}


def jack_of(name):
    return JACK.get(name, "UFL")


def tap(x, y, name, rkey="R 1k", dx=12.7, text=None, note_dx=8.0):
    """A monitor tap from node (x, y): series resistor to the right, the jack (jack_of(name)),
    shield to ground; the name stands beside the jack (its designator is not printed on the board)."""
    a, b = series(rkey, x + dx / 2.0, y)
    W((x, y), a)
    j = part(jack_of(name), nref("J"), x + dx + 5.08, y, rot=0, value=name, text="hide")
    W(b, j.pin("1"))
    p2 = j.pin("2")
    W(p2, (p2[0], p2[1] + G))
    gnd(p2[0], p2[1] + G)
    if text is not False:
        import levels as LV
        note(x + dx + note_dx, y - 1.5, text or LV.LIMITS.get(name, (None, name))[1], cols=24)
    return j


def ufl(x, y, name, rot=0):
    """A jack (jack_of(name)) whose centre pin is at (x, y) (rot 0: the jack to the right), shield grounded."""
    j = part(jack_of(name), nref("J"), x + 5.08, y, rot=rot, value=name, text="hide")
    p2 = j.pin("2")
    W(p2, (p2[0], p2[1] + G))
    gnd(p2[0], p2[1] + G)
    return j


def comparator(ref, x, y, rail="+3V3_DIG", kind="TLV3601"):
    """A TLV3601 (or TLV3603) at (x, y) with its supply capacitor to the right of the VCC pin.  A
    TLV3603's LE/HYS pin gets two DNP footprints: 0 ohm to the rail (no hysteresis) and 150 k to
    ground (30 mV); with both empty the pin floats: 3 mV, the TLV3601's (its datasheet's table)."""
    pl = part(kind, ref, x, y)
    vx, vy = pl.pin("6" if kind == "TLV3603" else "5")
    W((vx, vy), (vx, vy - 7.62))
    flag(rail, vx, vy - 7.62)
    W((vx, vy - 2.54), (vx + 7.62, vy - 2.54))
    J(vx, vy - 2.54)
    down("C 100nF", vx + 7.62, vy - 2.54, text="right")
    ex, ey = pl.pin("2")
    W((ex, ey), (ex, ey + G))
    gnd(ex, ey + G)
    if kind == "TLV3603":
        hx, hy = pl.pin("5")
        yj = hy + 2 * G
        W((hx, hy), (hx, yj))
        J(hx, yj)
        t, b = vpart("R 150k", nref("R"), hx, yj + G + 3.81, dnp=True, value="DNP 150k", text="right", fsize=1.0)
        W((hx, yj), t)
        gnd(*b)
        xr = hx + 12.7
        a2, b2 = hpart("R 0R", nref("R"), hx + 6.35, yj, dnp=True, value="DNP 0R", ref_at=(hx + 6.35, yj - 3.8),
                       val_at=(hx + 6.35, yj - 2.6), fsize=1.0, justify="center")
        W((hx, yj), a2)
        W(b2, (xr, yj))
        flag(rail, xr, yj)
    return pl


def bias_tee(x, y, rail="+5V_RF"):
    """The ADL5611's output bias: 43 nH up from the RF node (x, y) to the rail with 68 pF, 1 nF
    and 1 uF beside it.  The RF line continues to the right of x."""
    lt, lb = vpart("L43N", nref("L"), x, y - 3.81 - G, fsize=1.0)
    W((x, y), lb)
    yj = lt[1] - G
    W(lt, (x, yj))
    W((x, yj), (x, yj - G))
    flag(rail, x, yj - G)
    xx = x
    for k, key in enumerate(("C 68pF", "C 1nF", "C 1uF")):
        x2 = xx + 10.16
        W((xx, yj), (x2, yj))
        xx = x2
        down(key, x2, yj, text="right")
        J(x2, yj) if k < 2 else None
    J(x, yj)
    J(x, y)
    return xx


def coupler_mon(x, y, name, ref, level=None):
    """A -20 dB coupled-line coupler in the RF line at x (its IN pin): the monitor jack on the
    coupled port, 49.9 ohm on the isolated port; returns the OUT pin's point."""
    cp = U.part_at_pin("COUPLER", ref, "1", x, y, in_bom=False)
    cpl, iso, out = cp.pin("3"), cp.pin("4"), cp.pin("2")
    # the coupled port goes up and left to the jack; the isolated port up and right to its load
    W(cpl, (cpl[0] - 5.08, cpl[1]), (cpl[0] - 5.08, cpl[1] - 17.78))
    jm = part("UFL", nref("J"), cpl[0] - 5.08 - 5.08, cpl[1] - 17.78 - 5.08, rot=270, value=name, text="hide")
    W((cpl[0] - 5.08, cpl[1] - 17.78), jm.pin("1"))
    s2 = jm.pin("2")
    W(s2, (s2[0] - G, s2[1]))
    gnd(s2[0] - G, s2[1])
    W(iso, (iso[0] + 5.08, iso[1]))
    down("R 49.9R", iso[0] + 5.08, iso[1], text="right")
    note(x - 4, y + 10, "-20 dB coupled-line coupler, copper on the board (7.3 mm beside the line): " + name + " on the coupled end"
         + (" (%s)" % level if level else "") + ", 49.9 ohm on the isolated end", cols=30)
    return out


def synthesizer(ref, x, y, rail, le_name, mux_name, lo_name, mon_name, ref_src, bar_dy=12.7):
    """One MAX2871 with its loop filter (sim/budget.py section 8), supply bar, output chokes and
    DC blocks.  RFOUTA leaves to the right as the LO pair (P raised 12.7 above N), RFOUTB goes
    to a monitor U.FL and a 50 ohm load.  `ref_src` is the point the reference arrives from.
    Returns (placed, dict(lo_p=(x, y), lo_n=(x, y)) at the right ends of the DC blocks)."""
    pl = part("MAX2871", ref, x, y)
    yb = supply_bar(pl, ["6", "10", "28", "32", "17", "16"], rail, dy=bar_dy, bulk="C 10uF", side_caps=6, caps_side="left", cap_offset=10.16)
    bottom_gnd(pl, ["8", "9", "27", "31", "21", "18", "11", "33"])
    # pull-ups on the top: CE and RFOUT_EN high (software holds the part); each a resistor up to the bar
    x1s = max(pl.pin(n)[0] for n in ("6", "10", "28", "32", "17", "16"))
    for n, side in (("4", "left"), ("26", "right")):
        xp, yp = pl.pin(n)
        W((xp, yp), (xp, yp - 1.27))
        rt, rb_ = vpart("R 10k", nref("R"), xp, yp - 1.27 - 3.81, fsize=1.0, text=side)
        if abs(rt[1] - yb) > 0.01:
            W(rt, (xp, yb))
        if xp > x1s:                                         # RFOUT_EN is past the bar's end: continue the bar to it
            W((x1s, yb), (xp, yb))
        else:
            J(xp, yb)
    # reference in through 100 nF
    rx, ry = pl.pin("29")
    a, b = series("C 100nF", rx - 7.62, ry)
    W(b, (rx, ry))
    L(ref_src, a, first="v")
    # SPI and control
    for n, name in (("1", "SPI_SCLK"), ("2", "SPI_SDATA"), ("3", le_name)):
        e = stub(pl, n, dx=-10.16)
        U.S.hlabel(e[0], e[1], name, shape="input", rot=180)
    e = stub(pl, "30", dx=-10.16)
    U.S.hlabel(e[0], e[1], mux_name, shape="output", rot=180)
    e = stub(pl, "25", dx=-5.08)
    tp(e[0], e[1], "LD " + ref)
    U.S.nc(*pl.pin("5"))
    # loop filter: CP_OUT -> C1 || (R2 + C2) -> R3 -> TUNE with C3 (all C0G), the values sim/budget.py section 8 chose
    import levels as LV
    V = LV.VAL
    cx, cy = pl.pin("7")
    tx_, ty = pl.pin("20")
    xf = cx - 10.16
    W((cx, cy), (xf, cy))
    down(V["pll_C1"], xf, cy, text="left")
    J(xf, cy)
    xr2 = xf - 10.16
    W((xf, cy), (xr2, cy))
    r2, b2 = down(V["pll_R2"], xr2, cy, net=None, text="left")
    W(b2, (b2[0], b2[1] + G))
    down(V["pll_C2"], b2[0], b2[1] + G, text="left", drop=0)
    J(xr2, cy)
    xr3 = xr2 - 10.16
    W((xr2, cy), (xr3, cy))
    rr = part(V["pll_R3"], nref("R"), xr3, (cy + ty) / 2.0, rot=0, text="left", fsize=1.0)
    ra, rb = sorted((rr.pin("1"), rr.pin("2")), key=lambda p: p[1])
    W((xr3, cy), ra)
    W(rb, (xr3, ty))
    W((xr3, ty), (tx_, ty))
    xc3 = xr3 - 10.16
    W((xr3, ty), (xc3, ty))
    down(V["pll_C3"], xc3, ty, text="left")
    J(xr3, ty)
    note(xc3 - 10, ty + 20, "Loop filter: %.0f kHz, 50 deg, Icp %.2f mA (RSET %s, CP = %d), Kvco %.0f MHz/V, N = %.0f (sim/budget.py section 8).  C0G."
         % (LV.B["pll_fc"] / 1e3, LV.P["pll_icp_mA"], V["pll_Rset"][2:], LV.P["pll_cp_code"], LV.P["pll_kvco_MHz_V"], LV.P["pll_fout_MHz"] / LV.P["pll_pfd_MHz"]), cols=30)
    # RSET
    e = stub(pl, "22", dx=-5.08)
    down(V["pll_Rset"], e[0], e[1], text="left")
    # the three filter pins on the right (2.54 apart): 1 uF each, hung below the chip from
    # three columns, the top pin's the farthest out so that no line crosses another
    ybot = pl.pin("33")[1] + 10.16
    for k, n in enumerate(("19", "23", "24")):
        e = stub(pl, n, dx=25.4 - 10.16 * k)
        W(e, (e[0], ybot))
        down("C 1uF", e[0], ybot, text="right", drop=0)
    # RF outputs: open collectors, 27 nH to the rail, 1.5 pF blocks; the symbol spaces the four
    # pins 15.24 apart so that each line's choke stands up to its flag without touching the next
    out = {}
    for n, key in (("12", "lo_p"), ("13", "lo_n"), ("14", "mon_p"), ("15", "mon_n")):
        px, py = pl.pin(n)
        yl = py
        xl = px + 10.16
        W((px, py), (xl, yl))
        up("L27N", xl, yl, rail, text="right")
        J(xl, yl)
        xe = xl + 17.78
        end = dcblock(xl, yl, xe)
        out[key] = end
    # RFOUTB P to the monitor jack, N into 50 ohm
    mpx, mpy = out["mon_p"]
    jm = part("UFL", nref("J"), mpx + 5.08, mpy, value=mon_name, text="hide")
    W((mpx, mpy), jm.pin("1"))
    s2 = jm.pin("2")
    W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    note(mpx - 10, mpy + 9, mon_name + ": the synthesizer's second output; enable it in software to look at the LO (-4 to +5 dBm).", cols=26)
    mnx, mny = out["mon_n"]
    W((mnx, mny), (mnx + 2.54, mny))
    down("R 49.9R", mnx + 2.54, mny, text="right")
    return pl, out


def arm(S, name, ref, hp, lp, yf, xf, rf_key, rg_key="R 1k", rs_key="R 1.2k", shunts=True, hlabels=False, out_rc=None, trim=None, note_text=None,
        node_label=None, out_tap=None):
    """One baseband arm: the pair (hp, lp) through two Rg into a THS4541 at (xf, yf) with the
    feedback resistors `rf_key`; `shunts` adds the 1.2 k level-shift shunts at the summing nodes
    (for the 3.2 V pairs out of the demodulator); `hlabels` also exports the output pair as
    hierarchical labels NAME_P / NAME_N; `out_rc` = (R key, C key) puts a series R and a shunt C on
    each output (the slow path's pole); `trim` = a net name whose voltage reaches the IN- summing
    node through 100 k (an offset trim, drawn here); `node_label` exports the IN- summing node itself as
    a hierarchical label at the left end of its row, for a trim drawn on another sheet; `out_tap`
    names a monitor tap on the + output AHEAD of the RC (CLAUDE_PCB.md section 9: never tap a
    comparator's input behind a series resistor; the design review).  Returns the output pair
    (after the RC when there is one)."""
    fda = part("THS4541", ref, xf, yf)
    fbn, inp, inn, fbp, vocm = fda.pin("1"), fda.pin("2"), fda.pin("3"), fda.pin("4"), fda.pin("9")
    outp, outn = fda.pin("10"), fda.pin("11")
    xr = inp[0] - 7.62                    # the feedback resistors' column
    xg = hp[0] + 15.24                    # Rg, near the source
    xs1, xs2 = xg + 10.16, xr - 10.16     # the two shunts (or the trim)
    hp_below = hp[1] > lp[1]              # the + source drawn under the - one (the I arm since Response 10): texts swap sides
    ra, rb = series(rg_key, xg, hp[1], above=not hp_below)
    W(hp, ra)
    W(rb, (xs1, hp[1]), (xs1, inp[1]), (xr, inp[1]), inp)
    if shunts:
        # the IN+ shunt: anything hanging DOWN from this row would run through the IN- row below it
        # (Response 8's crops showed the IN- line through the resistor's body), so it stands on a loop
        # ABOVE the row: up 5.08, the resistor lying to the right, its ground hanging from the far end
        x_s = xs1 + 2.54
        y_top = inp[1] - 5.08
        J(x_s, inp[1])
        W((x_s, inp[1]), (x_s, y_top))
        ra_s, rb_s = series(rs_key, x_s + 3.81, y_top)
        W(rb_s, (rb_s[0], rb_s[1] + G))
        gnd(rb_s[0], rb_s[1] + G)
    J(xr, inp[1])
    ra2, rb2 = series(rg_key, xg, lp[1], above=hp_below)
    W(lp, ra2)
    xv = xs1 - 5.08
    W(rb2, (xv, lp[1]), (xv, inn[1]), (xs2, inn[1]), (xr, inn[1]), inn)
    if shunts:
        J(xs2, inn[1])
        down(rs_key, xs2, inn[1], text="right")               # the feedback resistors' texts go right too
    if trim and shunts:                                      # the shunt hangs at xs2: the trim hangs a step left of the row's start
        J(xv, inn[1])
        W((xv, inn[1]), (xv - 2.54, inn[1]), (xv - 2.54, inn[1] + 2.54))
        import levels as LV
        r, b = down(LV.VAL["trim_R"], xv - 2.54, inn[1] + 2.54, net=None, text="left")
        W(b, (b[0], b[1] + G))
        label(b[0], b[1] + G, trim, size=1.0, justify="left top")
    elif trim:
        J(xs2, inn[1])
        import levels as LV
        r, b = down(LV.VAL["trim_R"], xs2, inn[1], net=None, text="left")
        W(b, (b[0], b[1] + G))
        label(b[0], b[1] + G, trim, size=1.0, justify="left top")
    if node_label:                                           # the summing node leaves the sheet at the row's left end, a step down
        J(xv, inn[1])
        W((xv, inn[1]), (xv - 2.54, inn[1]), (xv - 2.54, inn[1] + 2.54))
        S.hlabel(xv - 2.54, inn[1] + 2.54, node_label, shape="input", rot=0)       # text to the right: the Rg texts are left and below
    J(xr, inn[1])
    W(fbn, (xr, fbn[1]))
    part(rf_key, nref("R"), xr, (fbn[1] + inp[1]) / 2.0, rot=0, text="right", fsize=1.0)
    W(fbp, (xr, fbp[1]))
    part(rf_key, nref("R"), xr, (inn[1] + fbp[1]) / 2.0, rot=0, text="right", fsize=1.0)
    e = stub(fda, "9", dx=-5.08)
    down("C 100nF", e[0], e[1], text="left")
    yb = supply_bar(fda, ["5", "6", "7", "8"], "+3V3_ANA", dy=10.16, side_caps=2, caps_side="left")
    # PD high: a 10 k from pin 12 up to the supply bar itself (one rail flag, not two side by side)
    x12, y12 = fda.pin("12")
    x1 = max(fda.pin(n)[0] for n in ("5", "6", "7", "8"))
    W((x12, y12), (x12, y12 - 1.27))
    rt, rb_ = vpart("R 10k", nref("R"), x12, y12 - 1.27 - 3.81, fsize=1.0, text="right")
    if x12 > x1:                                             # pin 12 is past the bar's end: continue the bar to it
        W((x1, yb), (x12, yb))
    else:
        J(x12, yb)
    if abs(rt[1] - yb) > 0.01:
        W(rt, (x12, yb))
    bottom_gnd(fda, ["13", "14", "15", "16", "17"])
    if note_text:
        note(xf - 32, yf + 24, note_text, cols=38)
    xo = outp[0] + 7.62
    W(outp, (xo, outp[1])); W(outn, (xo, outn[1]))
    label(outp[0] + 1.27, outp[1], name + "_P", size=1.0)
    label(outn[0] + 1.27, outn[1], name + "_N", size=1.0, justify="left top")
    if hlabels:
        S.hlabel(xo, outp[1], name + "_P", shape="output", rot=0)
        S.hlabel(xo, outn[1], name + "_N", shape="output", rot=0)
    if out_tap:
        J(xo, outp[1])
        W((xo, outp[1]), (xo, outp[1] - 15.24))
        tap(xo, outp[1] - 15.24, out_tap)
    if out_rc:
        rk, ck = out_rc
        # P: series R, node, capacitor to ground.  N jogs down 12.7 first so its capacitor and P's do not meet.
        a, b = series(rk, xo + 7.62, outp[1])
        W((xo, outp[1]), a)
        xn = b[0] + 5.08
        W(b, (xn, outp[1])); J(xn, outp[1]); down(ck, xn, outp[1], text="right")
        yn = outn[1] + 12.7
        W((xo, outn[1]), (xo, yn))
        a2, b2 = series(rk, xo + 7.62, yn, above=False)
        W((xo, yn), a2)
        W(b2, (xn, yn)); J(xn, yn); down(ck, xn, yn, text="right")
        return (xn, outp[1]), (xn, yn)
    return (xo, outp[1]), (xo, outn[1])
