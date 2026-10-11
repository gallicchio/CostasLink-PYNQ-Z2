"""The silkscreen: what the board says about itself.  Called by gen/board.py.

Top side, for a person holding the board with the lid off:
  * what each connector is and which pin is which (SWD, UART, the plug's
    contact numbers), the LEDs' meanings, BOOT, and every test point's rail;
  * the chips by part number and job;
  * the designators of the chips, transistors, crystal and inductor, beside
    their parts; the passives' designators are on the fab layer only, which
    the assembly drawing prints (beside a 0402 a designator is as likely to be
    read as its neighbour's: the Raspberry Pi Pico prints none);
  * the board's name.
Bottom side, in the strip the plug's flange leaves uncovered: the identity
(name, what it is, authors, revision and date, licences).

JLCPCB prints nothing finer than 0.15 mm lines and nothing legible under
0.8 mm text, so every line and stroke here is at least 0.15 mm and every
text at least 0.8 mm high.  KiCad's stock footprints draw their silkscreen at
0.12 mm: it is widened.  The passives' own marks (two dashes beside an 0402)
are dropped: they say nothing and crowd the labels.

Placement is checked in code as it is made: no text over a pad, a via, a
hole, another text or a part's body, and nothing within 0.25 mm of the edge.
A label that cannot be placed is reported, never forced.
"""
import math
import pcbnew
import board_info as BI
import placement as PL

STROKE = 0.15            # JLCPCB's minimum line width
TEXT_H = 0.8             # JLCPCB's minimum legible text height
REF_W = 0.7              # designators a little narrow, to fit beside 0402s
EDGE = 0.2               # silkscreen to board edge
PAD_GAP = 0.15           # silkscreen to exposed copper
GAP = 0.12               # between two silkscreen items

PASSIVE_FOOTPRINTS = ("R_0402", "C_0402", "R_0603", "C_0603")

# The designators printed, and where, in order of preference: U(p), D(own),
# L(eft), R(ight) of the part.  Everything else goes to the fab layer: the
# connectors, LEDs, test points and button carry functional labels instead,
# and U2 and U3 are named with their part numbers above them.
REF_SIDES = {r: "UDLR" for r in ("U101", "U102", "U103", "U117", "U104", "U105", "U106", "U107", "U108", "U109", "U110", "U111",
                                   "U112", "U113", "U114", "U115", "U116", "U201", "U202", "U203", "U204", "U205", "U301", "U302", "U303",
                                   "U304", "U305", "U401", "U501", "U502", "U503", "U504", "U505", "U506", "Y101", "Y201", "T101", "Q301", "Q302")}


def mm(v):
    return pcbnew.FromMM(float(v))


class Silk:
    def __init__(self, board, P, B):
        self.board, self.P, self.B = board, P, B
        self.W, self.H = PL.BOARD["w"], PL.BOARD["h"]
        self.blocked = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}    # (x0, y0, x1, y1, what)
        self.placed = {pcbnew.F_SilkS: [], pcbnew.B_SilkS: []}
        self.problems = []

    # ---- geometry --------------------------------------------------------------
    def box(self, bb, grow=0.0):
        x0, y0 = self.B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
        x1, y1 = self.B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
        return (x0 - grow, y0 - grow, x1 + grow, y1 + grow)

    @staticmethod
    def hit(a, b):
        return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

    def free(self, layer, r, vias=True):
        """Why the rectangle r cannot take silkscreen on `layer`, or None.  vias=False lets a
        connector's name cross a via: the board's vias are tented both sides (gen/board.py's
        setup), so the ink lands on solder mask, and KiCad's DRC agrees; never a pad or a hole."""
        if r[0] < EDGE or r[1] < EDGE or r[2] > self.W - EDGE or r[3] > self.H - EDGE:
            return "the board edge"
        for b in self.blocked[layer] + self.placed[layer]:
            if not vias and b[4] == "via":
                continue
            if self.hit(r, b):
                return b[4]
        return None

    def blockers(self, layer, r):
        """every obstacle the rectangle r is over (vias excepted), for a build log's diagnosis"""
        out = []
        if r[0] < EDGE or r[1] < EDGE or r[2] > self.W - EDGE or r[3] > self.H - EDGE:
            out.append("the board edge")
        for b in self.blocked[layer] + self.placed[layer]:
            if b[4] != "via" and self.hit(r, b) and b[4] not in out:
                out.append(b[4])
        return out

    def obstacles(self, fps):
        """Pads, vias, holes and part bodies, on the side each is seen from."""
        top, bot = pcbnew.F_SilkS, pcbnew.B_SilkS
        for fp in fps.values():
            ref = fp.GetReference()
            back = fp.GetLayer() == pcbnew.B_Cu
            for pad in fp.Pads():
                r = self.box(pad.GetBoundingBox(), PAD_GAP)
                tht = pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
                if tht or not back:
                    self.blocked[top].append(r + ("%s pad %s" % (ref, pad.GetNumber()),))
                if tht or back:
                    self.blocked[bot].append(r + ("%s pad %s" % (ref, pad.GetNumber()),))
            # the body: its fab outline (what sits on the board), else the courtyard
            fab = [it for it in fp.GraphicalItems() if it.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab)
                   and it.GetClass() == "PCB_SHAPE"]
            if not fab:                                    # a test point: its pad and ring
                fab = [it for it in fp.GraphicalItems() if it.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS)]
                fab += list(fp.Pads())
            if not fab:
                continue
            bb = fab[0].GetBoundingBox()
            for it in fab[1:]:
                bb.Merge(it.GetBoundingBox())
            body = self.box(bb)
            if ref.startswith("H"):
                continue                                   # its hole is a pad above
            if ref == "J302":
                continue                                   # the socket is on the back; its pins are pads above
            self.blocked[bot if back else top].append(body + ("%s body" % ref,))
        for t in self.board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T:
                r = self.box(t.GetBoundingBox(), 0.05)
                self.blocked[top].append(r + ("via",))
                self.blocked[bot].append(r + ("via",))

    def keep_graphics(self, fps):
        """Footprints' own silkscreen: passives' dashes dropped, the rest
        widened to 0.15 mm and counted as placed."""
        for fp in fps.values():
            name = fp.GetFPIDAsString().split(":")[-1]
            for it in list(fp.GraphicalItems()):
                if it.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                    continue
                if it.GetClass() == "PCB_TEXT":
                    t = it
                    t.SetTextThickness(mm(STROKE))
                    self.placed[it.GetLayer()].append(self.box(t.GetBoundingBox(), GAP) + ("%s text" % fp.GetReference(),))
                    continue
                if name.startswith(PASSIVE_FOOTPRINTS):
                    fp.Remove(it)
                    continue
                bx = self.box(it.GetBoundingBox())
                if bx[0] < EDGE or bx[1] < EDGE or bx[2] > self.W - EDGE or bx[3] > self.H - EDGE:
                    fp.Remove(it)                              # past the edge: the SMA barrels' outlines
                    continue
                if not it.IsSolidFill() and pcbnew.ToMM(it.GetWidth()) < STROKE:
                    it.SetWidth(mm(STROKE))
                self.placed[it.GetLayer()].append(self.box(it.GetBoundingBox(), GAP) + ("%s outline" % fp.GetReference(),))

    # ---- texts -------------------------------------------------------------------
    def _style(self, t, h, w=None, stroke=STROKE, bottom=False, angle=0):
        t.SetBold(False)                 # first: un-bolding resets the stroke to size/8
        t.SetItalic(False)
        t.SetTextSize(pcbnew.VECTOR2I(mm(w or h), mm(h)))
        t.SetTextThickness(mm(stroke))
        t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
        t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        t.SetMirrored(bottom)
        t.SetTextAngleDegrees(angle)

    def _extent(self, t):
        return self.box(t.GetEffectiveTextShape().BBox())

    def label(self, text, x, y, h=TEXT_H, w=None, stroke=STROKE, bottom=False, angle=0, justify="center",
              what=None, vias=True):
        """A board text centred (or left/right justified) at (x, y); placed
        only where it is free."""
        layer = pcbnew.B_SilkS if bottom else pcbnew.F_SilkS
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(text)
        t.SetLayer(layer)
        self._style(t, h, w, stroke, bottom, angle)
        if justify != "center":
            t.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT, "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[justify])
        t.SetPosition(self.P(x, y))
        r = self._extent(t)
        why = self.free(layer, r, vias)
        if why:
            self.problems.append("label %r at (%.2f, %.2f), extent (%.2f, %.2f)-(%.2f, %.2f): over %s"
                                 % ((text, x, y) + tuple(r) + (why,)))
            return None
        self.board.Add(t)
        self.placed[layer].append((r[0] - GAP, r[1] - GAP, r[2] + GAP, r[3] + GAP, "label %r" % text))
        return r

    def probe(self, text, x, y, h=TEXT_H, w=None, stroke=STROKE, bottom=False, angle=0, justify="center"):
        """Would this label fit?  Its extent if so, else None: nothing is added to the board."""
        layer = pcbnew.B_SilkS if bottom else pcbnew.F_SilkS
        t = pcbnew.PCB_TEXT(self.board)
        t.SetText(text)
        t.SetLayer(layer)
        self._style(t, h, w, stroke, bottom, angle)
        if justify != "center":
            t.SetHorizJustify({"left": pcbnew.GR_TEXT_H_ALIGN_LEFT, "right": pcbnew.GR_TEXT_H_ALIGN_RIGHT}[justify])
        t.SetPosition(self.P(x, y))
        r = self._extent(t)
        return None if self.free(layer, r) else r

    def line(self, pts, bottom=False, width=STROKE):
        layer = pcbnew.B_SilkS if bottom else pcbnew.F_SilkS
        for a, b in zip(pts, pts[1:]):
            s = pcbnew.PCB_SHAPE(self.board)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart(self.P(*a)); s.SetEnd(self.P(*b))
            s.SetLayer(layer); s.SetWidth(mm(width))
            r = self.box(s.GetBoundingBox())
            why = self.free(layer, r)
            if why:
                self.problems.append("line (%.2f, %.2f)-(%.2f, %.2f): over %s" % (a[0], a[1], b[0], b[1], why))
                continue
            self.board.Add(s)
            self.placed[layer].append((r[0] - GAP, r[1] - GAP, r[2] + GAP, r[3] + GAP, "line"))

    # ---- designators ---------------------------------------------------------------
    def references(self, fps):
        top = pcbnew.F_SilkS
        bodies = {}
        for ref, fp in fps.items():
            if fp.GetLayer() == pcbnew.B_Cu:
                continue
            bb = None
            for pad in fp.Pads():
                pb = pad.GetBoundingBox()
                if bb is None:
                    bb = pb
                else:
                    bb.Merge(pb)
            for it in fp.GraphicalItems():
                if it.GetLayer() == pcbnew.F_Fab and it.GetClass() == "PCB_SHAPE":
                    bb.Merge(it.GetBoundingBox()) if bb is not None else None
            bodies[ref] = self.box(bb) if bb is not None else None
        for ref in sorted(fps, key=_refkey):
            fp = fps[ref]
            t = fp.Reference()
            sides = REF_SIDES.get(ref, "fab")
            if fp.GetLayer() == pcbnew.B_Cu or sides == "fab" or bodies.get(ref) is None:
                self._to_fab(fp)
                continue
            self._style(t, TEXT_H, REF_W)
            x0, y0, x1, y1 = bodies[ref]
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            done = False
            for gap in (0.2, 0.45):
                for side in sides:
                    for angle in ((0,) if side in "UD" else (0, 90)):
                        t.SetTextAngleDegrees(angle)
                        t.SetPosition(self.P(cx, cy))
                        ex = self._extent(t)
                        hw, hh = (ex[2] - ex[0]) / 2, (ex[3] - ex[1]) / 2
                        x, y = {"U": (cx, y0 - gap - hh), "D": (cx, y1 + gap + hh),
                                "L": (x0 - gap - hw, cy), "R": (x1 + gap + hw, cy)}[side]
                        t.SetPosition(self.P(x, y))
                        r = self._extent(t)
                        if self.free(top, r) or not self._nearest_is(ref, r, bodies):
                            continue
                        self.placed[top].append((r[0] - GAP, r[1] - GAP, r[2] + GAP, r[3] + GAP, "%s ref" % ref))
                        t.SetLayer(top)
                        t.SetVisible(True)
                        done = True
                        break
                    if done:
                        break
                if done:
                    break
            if not done:
                self._to_fab(fp)

    @staticmethod
    def _nearest_is(ref, r, bodies):
        """The label's nearest part body is its own: never ambiguous."""
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2

        def dist(b):
            dx = max(b[0] - cx, 0, cx - b[2])
            dy = max(b[1] - cy, 0, cy - b[3])
            return math.hypot(dx, dy)
        mine = dist(bodies[ref])
        return all(dist(b) > mine + 0.05 for k, b in bodies.items() if k != ref and b is not None)

    def _to_fab(self, fp):
        """The designator on the fab layer only, for the assembly drawing.  Most
        footprints already draw it there (a ${REFERENCE} text sized to the
        part); then the field itself is hidden, or the drawing shows it twice."""
        t = fp.Reference()
        back = fp.GetLayer() == pcbnew.B_Cu
        t.SetLayer(pcbnew.B_Fab if back else pcbnew.F_Fab)
        own = any(it.GetClass() == "PCB_TEXT" and "${REFERENCE}" in it.GetText()
                  and it.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab) for it in fp.GraphicalItems())
        if own:
            t.SetVisible(False)
            self._fab_text(fp)
            return
        self._style(t, 0.5, 0.5, 0.08, bottom=back)
        t.SetPosition(fp.GetPosition())
        t.SetVisible(True)


    def _fab_text(self, fp):
        """The footprint's own fab designator, legible in the assembly drawing
        and inside the part: Raspberry Pi's are drawn with a 0.01 mm hairline,
        and the test points' and the button's sit outside them, on top of the
        silkscreen labels."""
        body = None
        for it in list(fp.GraphicalItems()) + list(fp.Pads()):
            if it.GetClass() == "PCB_TEXT" or (it.GetClass() == "PCB_SHAPE" and it.GetLayer() not in (pcbnew.F_Fab, pcbnew.B_Fab)):
                continue
            bb = it.GetBoundingBox()
            if body is None:
                body = bb
            else:
                body.Merge(bb)
        x0, y0, x1, y1 = self.box(body)
        side = min(x1 - x0, y1 - y0)
        for it in fp.GraphicalItems():
            if it.GetClass() == "PCB_TEXT" and "${REFERENCE}" in it.GetText() and it.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
                h = max(0.25, min(1.0, 0.45 * side))
                it.SetTextSize(pcbnew.VECTOR2I(mm(h), mm(h)))
                it.SetTextThickness(mm(max(0.04, 0.15 * h)))
                it.SetPosition(fp.GetPosition())
                if fp.GetReference() in FAB_OFFSET:
                    dx, dy = FAB_OFFSET[fp.GetReference()]
                    it.SetPosition(fp.GetPosition() + pcbnew.VECTOR2I(mm(dx), mm(dy)))
                it.SetKeepUpright(True)          # Raspberry Pi's parts are turned 180 with U1


# Fab designators that cannot sit at their part's centre (board mm from it):
# J2's centre, between the plug's rows, carries "the plug goes on this side"
# on the back, so its designator moves to the D's left end, past contact 12.
FAB_OFFSET = {}


def _refkey(ref):
    """Big parts first (they have the fewest places), then by letter and number."""
    order = {"U": 0, "Q": 1, "Y": 2, "L": 3, "J": 4, "D": 5, "R": 6, "C": 7}
    letters = "".join(c for c in ref if c.isalpha())
    num = int("".join(c for c in ref if c.isdigit()) or 0)
    return (order.get(letters, 9), letters, num)


# ---------------------------------------------------------------------------
def apply(board, fps, P, B):
    S = Silk(board, P, B)
    S.obstacles(fps)
    S.keep_graphics(fps)
    xy = {}
    for ref, fp in fps.items():
        for pad in fp.Pads():
            xy.setdefault((ref, pad.GetNumber()), B(pad.GetPosition()))
    p = lambda ref, num: xy[(ref, num)]
    labels(S, p)
    S.references(fps)
    import silk_blocks
    probs, rect = silk_blocks.boxes(S, fps)
    S.problems += probs
    for msg in S.problems:
        print("   SILK: " + msg)
    n_top = sum(1 for fp in fps.values() if fp.Reference().GetLayer() == pcbnew.F_SilkS)
    print("silk: %d labels, %d of %d designators on the silkscreen (the rest on the fab layer), %d problems"
          % (len(S.placed[pcbnew.F_SilkS]) + len(S.placed[pcbnew.B_SilkS]), n_top, len(fps), len(S.problems)))
    return S


def try_label(S, text, spots, **kw):
    """The first of `spots` (x, y) where the label fits; None if none does (reported once)."""
    n0 = len(S.problems)
    for x, y in spots:
        r = S.label(text, x, y, **kw)
        if r is not None:
            del S.problems[n0:]
            return r
    del S.problems[n0 + 1:]
    return None


def ring(cx, cy, r0=3.0, r1=9.0, step=0.6):
    """Spots on rings round (cx, cy), nearest first."""
    out = []
    r = r0
    while r <= r1:
        n = max(8, int(2 * math.pi * r / 1.2))
        for k in range(n):
            a = 2 * math.pi * k / n
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        r += step
    return out


def labels(S, p):
    """The functional labels, laid out from the parts' positions: every jack named beside it with
    what it takes or gives (gen/levels.LIMITS), every test pad with its rail, every jumper with its
    choices (all three by rows, gen/silk_jacks.py), the chips by part number, the board's identity
    on the back."""
    W, H = PL.BOARD["w"], PL.BOARD["h"]
    # the connectors, the test pads and the headers: by rows, one relation per row (gen/silk_jacks.py)
    import silk_jacks
    silk_jacks.place(S)
    # the LEDs
    for ref, name in (("D301", "5V"), ("D302", "3V3")):
        x, y = p(ref, "1")
        try_label(S, name, [(x - 2.2, y), (x + 2.2, y), (x, y - 1.6), (x, y + 1.6)], h=0.8)
    # the chips, by part number, near each (on the ring round it where there is room)
    for ref, name in (("U104", "ADL5380 demod"), ("U201", "ADL5375 mod"), ("U115", "MAX2871 RX LO"), ("U203", "MAX2871 TX LO"),
                      ("U102", "PE43711 DSA"), ("U101", "SKY65404 LNA"), ("U401", "HMC536 T/R"), ("U103", "ADL5611"), ("U117", "ADL5611"),
                      ("U202", "ADL5611"), ("U105", "THS4541 I x4"), ("U106", "THS4541 Q x4"), ("U501", "THS4541 I x20"), ("U502", "THS4541 Q x20"),
                      ("U112", "OPA2388 PI"), ("U110", "sign(I) x Q"), ("U111", "HOLD"), ("U113", "DAC 0x60"), ("U506", "DAC 0x61"), ("U114", "ADC 0x48"),
                      ("Y101", "VCXO"), ("Y201", "TCXO")):
        fp = S.board.FindFootprintByReference(ref)
        if fp is None:
            continue
        cx, cy = S.B(fp.GetPosition())
        try_label(S, name, [(cx, cy - 4.2), (cx, cy + 4.2), (cx - 7.5, cy), (cx + 7.5, cy)] + ring(cx, cy, 3.6, 9.0), h=0.8)
    # the name, top edge between the SMAs
    try_label(S, BI.TITLE, [(40.0, 3.0), (38.0, 3.0), (40.0, 2.6)], h=1.4, stroke=0.2)
    # under the title, clear of TX ANT's name left of its jack (Response 15)
    try_label(S, "rev %s  %s" % (BI.REV, BI.DATE), [(40.0, 5.2), (37.0, 5.2), (35.5, 5.2), (34.0, 5.4)], h=0.8)
    try_label(S, "USB-C 5 V 1.5 A", [(112.0, 78.0), (112.0, 84.0), (110.5, 78.0), (109.0, 86.5)], h=0.9, angle=90)
    bottom(S, p)


def bottom(S, p):
    """The back: the identity in the strip right of the socket, and the socket's pin numbers."""
    lines = [(BI.TITLE, 1.3, 0.2), ("https://" + BI.URL, 0.8, STROKE), (BI.AUTHORS, 0.8, STROKE),
             ("rev %s  %s   %s" % (BI.REV, BI.DATE, BI.LICENCE), 0.8, STROKE)]
    placed = False
    for x0 in (86.0, 88.0, 80.0, 96.0, 70.0, 60.0):
        for y0 in (57.2, 70.0, 72.0, 74.0, 66.0, 62.0, 58.0, 76.0, 50.0, 40.0, 30.0):
            # probe all four lines first; the block goes in only where every line fits (nothing is
            # ever taken back out of the board: KiCad freed a removed text twice and aborted)
            y, ok = y0, True
            for text, h, st in lines:
                if S.probe(text, x0, y, h=h, stroke=st, bottom=True) is None:
                    ok = False
                    break
                y += 1.6 if h < 1.0 else 2.0
            if ok:
                y = y0
                for text, h, st in lines:
                    S.label(text, x0, y, h=h, stroke=st, bottom=True)
                    y += 1.6 if h < 1.0 else 2.0
                placed = True
                break
        if placed:
            break
    if not placed:
        S.problems.append("the identity block found no clear place on the back")
    yh = PL.hdr_pin(1)[1]
    try_label(S, "PYNQ-Z2 RPi header: pin 1 at this end", [(42.0, yh - 2.9), (42.0, yh - 3.5), (30.0, yh - 2.9), (42.0, yh + 6.1)], bottom=True)
    for n in ("1", "2", "39", "40"):
        x, y = p("J302", n)
        try_label(S, n, [(x + (1.9 if n in ("1", "2") else -1.9), y), (x, y + (1.9 if n in ("2", "40") else -1.9))], h=0.8, bottom=True)
