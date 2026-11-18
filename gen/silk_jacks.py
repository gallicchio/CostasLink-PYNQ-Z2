"""The connectors' labels, by rows (Response 15; the rules are gen/label_rows.py's, and
tools/label_check.py checks the board by them).  Jason: "There should be a big-font silk screen
right next to the connector, so it's obvious what it's for ... If there are SMAs in a row, their
labels should all be in the same relative orientation."

Each row gets one placement for all its members: a side (the SMAs inward first, the taps below
first, the test pads above first), a gap from the body, an angle and a size, the first in that
order where every member's label is free, is nearer its own connector than any other by a clear
margin (label_rows.owner_ok) and keeps SEP from every other connector's label.  The limit (what
the jack takes or gives, gen/levels.LIMITS) goes beyond its name in the same relation for every
member; a row whose members share one limit prints it once.  A row that finds no common place
for its names is a problem the build reports and tools/label_check.py fails: move the parts in
the way (gen/placement.py), never a label on its own.

The headers: a three-pin header's end choices beyond its end pins, level with them, and its
function (or its middle pin) beside the middle pin; a two-pin jumper named beside it.
"""
import math
import pcbnew
import label_rows as LR

SIZES = {"SMA": ((1.5, 1.35, 0.25), (1.3, 1.17, 0.22)),
         "tap": ((1.2, 1.05, 0.2), (1.0, 0.9, 0.18), (1.0, 0.8, 0.18)),
         "TP": ((1.0, 0.9, 0.18), (0.85, 0.78, 0.15))}
LIMIT = (0.8, 0.72, 0.15)
HEADER = ((0.9, 0.8, 0.15), (0.8, 0.7, 0.15))
TIERS = ((0.25, 0.45), (0.7, 1.0), (1.4, 1.9))
SEP = 0.8                 # mm from one connector's label to another's
LIM_GAP = 0.2             # mm between a name and its limit
import placement as PL
HEADERS = PL.HEADER_LABELS                     # (ref, texts in pin order, where the middle or the name goes)


def _inward(rot):
    """the side of an edge SMA that faces into the board (its barrel points the other way)"""
    return {90: "S", 180: "E", 0: "W", 270: "N"}[int(round(rot)) % 360]


def _prefs(fam, rot):
    if fam == "SMA":
        i = _inward(rot)
        if i in "NS":
            return (i, "E", "W", i + "E", i + "W")
        return (i, "S", "N", "S" + i, "N" + i)
    if fam == "tap":
        return ("S", "N", "E", "W", "SE", "SW", "NE", "NW")
    return ("N", "S", "E", "W", "NE", "NW", "SE", "SW")


class Labeller:
    def __init__(self, S):
        import levels as LV
        self.S, self.LV = S, LV
        self.cache = {}
        self.boxes = []                       # (ref, box): every connector label placed so far
        self.items, self.bodies = [], {}
        S.label_failures = []
        for fp in S.board.GetFootprints():
            ref = fp.GetReference()
            if fp.GetLayer() == pcbnew.B_Cu:
                continue
            fam = LR.family(ref, str(fp.GetFPID().GetLibItemName()))
            if fam or ref.startswith(("JP", "J30", "D30")):
                self.bodies[ref] = LR.body_of(fp, S.B, S.W, S.H)
            if fam:
                name = LR.name_of(ref, fp.GetValue())
                self.items.append(dict(ref=ref, family=fam, name=name, rot=fp.GetOrientationDegrees(), fp=str(fp.GetFPID().GetLibItemName()),
                                       anchor=LR.anchor_of(fp, fam, S.B),
                                       limit=LV.LIMITS.get(fp.GetValue(), ("", ""))[0] if fam != "TP" else ""))
        self.by = {it["ref"]: it for it in self.items}
        # the placement plan's word on each row's side, and the strips it kept clear (gen/placement.py LABEL_ROWS)
        self.planned = {}
        for row in PL.LABEL_ROWS:
            for r in row[0]:
                self.planned[r] = (row[1], row[2])
        import json, os
        plan = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "placement.json")))
        self.strips = [(o, tuple(r)) for o, r in plan.get("strips", [])]

    # ---- geometry ---------------------------------------------------------------------------
    def measure(self, text, size, angle):
        key = (text, size, angle)
        if key not in self.cache:
            S = self.S
            t = pcbnew.PCB_TEXT(S.board)
            t.SetText(text)
            t.SetLayer(pcbnew.F_SilkS)
            S._style(t, size[0], size[1], size[2], False, angle)
            t.SetPosition(S.P(50.0, 50.0))
            r = S._extent(t)
            self.cache[key] = (r[0] - 50.0, r[1] - 50.0, r[2] - 50.0, r[3] - 50.0)
        return self.cache[key]

    @staticmethod
    def at_side(body, anchor, side, gap, ext):
        w, h = ext[2] - ext[0], ext[3] - ext[1]
        x0, y0, x1, y1 = body
        ax, ay = anchor
        if side == "N":
            cx, cy = ax, y0 - gap - h / 2
        elif side == "S":
            cx, cy = ax, y1 + gap + h / 2
        elif side == "E":
            cx, cy = x1 + gap + w / 2, ay
        elif side == "W":
            cx, cy = x0 - gap - w / 2, ay
        else:
            cx = x1 + gap + w / 2 if "E" in side else x0 - gap - w / 2
            cy = y0 - gap - h / 2 if "N" in side else y1 + gap + h / 2
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    @staticmethod
    def beyond(name, side, angle, ext):
        """the limit's box beyond its name, away from the connector, in the row's one relation"""
        w, h = ext[2] - ext[0], ext[3] - ext[1]
        if angle == 0:
            if side in ("N", "S"):
                cx = (name[0] + name[2]) / 2
                cy = name[1] - LIM_GAP - h / 2 if side == "N" else name[3] + LIM_GAP + h / 2
            else:
                cx = name[0] + w / 2 if "E" in side else name[2] - w / 2
                cy = name[1] - LIM_GAP - h / 2 if side.startswith("N") else name[3] + LIM_GAP + h / 2
        else:
            cx = name[0] - LIM_GAP - w / 2 if side.endswith("W") else name[2] + LIM_GAP + w / 2
            if side.startswith("N"):
                cy = name[3] - h / 2
            elif side.startswith("S"):
                cy = name[1] + h / 2
            else:
                cy = (name[1] + name[3]) / 2
        return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)

    def others(self, ref):
        return [(r, b) for r, b in self.bodies.items() if r != ref]

    def fits(self, cands, owners=True, why=False, row=()):
        """every box free, none on another, names unmistakably their own, SEP from other connectors' labels
        (why=True: every reason it fails, for the build log)"""
        S = self.S
        whys = []
        for i, (text, box, kind, ref, size, angle) in enumerate(cands):
            w = S.blockers(pcbnew.F_SilkS, box) if why else S.free(pcbnew.F_SilkS, box, vias=False)
            if w:
                if not why:
                    return False
                whys.append("%r over %s" % (text, ", ".join(w)))
            for t2, b2, k2, r2, s2, a2 in cands[:i]:
                g = LR.box_dist(box, b2)
                if g < 0.15 or (r2 != ref and kind != "shared" and k2 != "shared" and g < SEP):
                    if not why:
                        return False
                    whys.append("%r too near %r" % (text, t2))
            if owners and kind == "name":
                o = LR.owner_ok(box, self.bodies[ref], self.others(ref))
                if o is not None:
                    if not why:
                        return False
                    whys.append("%r as near %s" % (text, o))
            for r2, b2 in self.boxes:
                if r2 != ref and LR.box_dist(box, b2) < SEP:
                    if not why:
                        return False
                    whys.append("%r too near %s's label" % (text, r2))
            for o, st in self.strips:                  # another connector's or header's place, kept for it
                if o != ref and o not in row and S.hit(box, st):
                    if not why:
                        return False
                    whys.append("%r in %s's strip" % (text, o))
        return "; ".join(whys) if why else True

    def commit(self, cands):
        S = self.S
        for text, box, kind, ref, size, angle in cands:
            ext = self.measure(text, size, angle)
            x = (box[0] + box[2]) / 2 - (ext[0] + ext[2]) / 2
            y = (box[1] + box[3]) / 2 - (ext[1] + ext[3]) / 2
            r = S.label(text, x, y, h=size[0], w=size[1], stroke=size[2], angle=angle, vias=False)
            if r is None:
                S.label_failures.append("%s: %r would not go where it was probed" % (ref, text))
            else:
                self.boxes.append((ref, r))

    # ---- a row --------------------------------------------------------------------------------
    def candidates(self, axis, refs, side, gap, size, angle, limits):
        its = [self.by[r] for r in refs]
        out = []
        for it in its:
            ext = self.measure(it["name"], size, angle)
            out.append((it["name"], self.at_side(self.bodies[it["ref"]], it["anchor"], side, gap, ext), "name", it["ref"], size, angle))
        if not limits:
            return out
        lims = [it["limit"] for it in its]
        if not any(lims):
            return out
        if axis == "x" and len(its) > 1 and len(set(lims)) == 1:
            # one shared limit, centred on the row, beyond the names (or below everything for E/W labels)
            ext = self.measure(lims[0], LIMIT, 0)
            w, h = ext[2] - ext[0], ext[3] - ext[1]
            cx = sum(it["anchor"][0] for it in its) / len(its)
            boxes = [c[1] for c in out] + [self.bodies[r] for r in refs]
            if side.startswith("N"):
                cy = min(b[1] for b in boxes) - LIM_GAP - h / 2
            else:
                cy = max(b[3] for b in boxes) + LIM_GAP + h / 2
            out.append((lims[0], (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2), "shared", refs[0], LIMIT, 0))
            return out
        for (text, box, kind, ref, s, a), it in zip(list(out), its):
            if it["limit"]:
                ext = self.measure(it["limit"], LIMIT, angle)
                out.append((it["limit"], self.beyond(box, side, angle, ext), "limit", ref, LIMIT, angle))
        return out

    def row(self, axis, refs):
        fam = self.by[refs[0]]["family"]
        prefs = _prefs(fam, self.by[refs[0]]["rot"])
        angles = (0, 90)
        if refs[0] in self.planned:                    # the side the placement kept clear, first
            side, ang = self.planned[refs[0]]
            prefs = (side,) + tuple(p for p in prefs if p != side)
            angles = (ang,) + tuple(a for a in angles if a != ang)
        import os
        if os.environ.get("LABEL_DEBUG") in refs:          # why the planned side fails, size by size
            for size in SIZES[fam]:
                for gap in TIERS[0] + TIERS[1]:
                    for lim in (False, True):
                        print("   LABEL_DEBUG %s %s %d %.2f %s%s: %s" % (refs[0], prefs[0], angles[0], gap, size, " +limits" if lim else "",
                              self.fits(self.candidates(axis, refs, prefs[0], gap, size, angles[0], lim), why=True, row=refs)))
        names_only = None
        # the side the placement planned and kept clear wins over a bigger font elsewhere: another side
        # takes room the plan gave to someone else (J502's name above it took JP101's, Response 15)
        order = []
        if refs[0] in self.planned:
            order += [(size, angles[0], (gap,), prefs[0]) for size in SIZES[fam] for tier in TIERS for gap in tier]
        order += [(size, angle, tier, side) for size in SIZES[fam] for angle in angles for tier in TIERS for side in prefs]
        for size, angle, tier, side in order:
            for gap in tier:
                c = self.candidates(axis, refs, side, gap, size, angle, False)
                if not self.fits(c, row=refs):
                    continue
                full = self.candidates(axis, refs, side, gap, size, angle, True)
                if len(full) == len(c) or self.fits(full, row=refs):
                    self.commit(full)
                    return
                if names_only is None:
                    names_only = (c, side, angle)
        if names_only is not None:
            c, side, angle = names_only
            self.commit(c)
            self.loose_limits(refs, side, angle)
            return
        size = SIZES[fam][-1]
        whys = ["%s %d %.2f: %s" % (side, a, gap, self.fits(self.candidates(axis, refs, side, gap, size, a, False), why=True, row=refs))
                for a in (0, 90) for side in prefs[:4] for gap in (0.25,)]
        self.S.label_failures.append("%s (%s): no common place for the names of %s\n        %s" % (
            "row along " + axis if axis else "alone", self.by[refs[0]]["family"], " ".join(refs), "\n        ".join(whys)))

    def loose_limits(self, refs, side, angle):
        """the names are uniform; a limit that cannot follow the row's relation goes where it fits nearest its
        connector: beyond its name first, then any side of the connector, unmistakably that connector's"""
        S = self.S
        for r in refs:
            it = self.by[r]
            if not it["limit"] or r in LR.LIMIT_EXEMPT:
                continue
            name = [b for rr, b in self.boxes if rr == r][-1]
            body = self.bodies[r]
            ext = self.measure(it["limit"], LIMIT, 0)
            w, h = ext[2] - ext[0], ext[3] - ext[1]
            spots = []
            for g in (0.2, 0.4, 0.7):                  # beyond the name, then beside it
                spots += [((name[0] + name[2]) / 2, name[3] + g + h / 2), ((name[0] + name[2]) / 2, name[1] - g - h / 2),
                          (name[0] + w / 2, name[3] + g + h / 2), (name[2] - w / 2, name[3] + g + h / 2),
                          (name[0] + w / 2, name[1] - g - h / 2), (name[2] - w / 2, name[1] - g - h / 2)]
            for g in (0.25, 0.5, 0.9, 1.4):            # then round the connector itself: centred, or flush with
                for sd in ("S", "N", "E", "W", "SE", "SW", "NE", "NW"):   # one of its edges
                    bx = self.at_side(body, it["anchor"], sd, g, ext)
                    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
                    spots.append((cx, cy))
                    if sd in ("S", "N"):
                        spots += [(body[0] + w / 2, cy), (body[2] - w / 2, cy)]
                    elif sd in ("E", "W"):
                        spots += [(cx, body[1] + h / 2), (cx, body[3] - h / 2)]
            # then turned, a column beside the connector (a turned name leaves no room across it: J502)
            ev = self.measure(it["limit"], LIMIT, 90)
            wv, hv = ev[2] - ev[0], ev[3] - ev[1]
            vspots = []
            for g in (0.25, 0.5, 0.9):
                for sd in ("E", "W"):
                    bx = self.at_side(body, it["anchor"], sd, g, ev)
                    cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
                    vspots += [(cx, cy), (cx, body[1] + hv / 2), (cx, body[3] - hv / 2)]
            done = False
            for (cx, cy), ang, ww, hh in [(p_, 0, w, h) for p_ in spots] + [(p_, 90, wv, hv) for p_ in vspots]:
                bx = (cx - ww / 2, cy - hh / 2, cx + ww / 2, cy + hh / 2)
                cand = [(it["limit"], bx, "limit", r, LIMIT, ang)]
                if self.fits(cand, row=refs) and LR.owner_ok(bx, body, self.others(r), box_add=False) is None:
                    self.commit(cand)
                    done = True
                    break
            if not done:
                S.label_failures.append("%s: no place for its limit %r" % (r, it["limit"]))
                import os
                if os.environ.get("LABEL_DEBUG") == r:
                    for cx, cy in vspots:
                        bx = (cx - wv / 2, cy - hv / 2, cx + wv / 2, cy + hv / 2)
                        print("   LABEL_DEBUG limit turned at (%.2f, %.2f): %s; owner %s" % (cx, cy, self.fits(
                            [(it["limit"], bx, "limit", r, LIMIT, 90)], why=True, row=refs),
                            LR.owner_ok(bx, body, self.others(r), box_add=False)))

    # ---- the headers ----------------------------------------------------------------------------
    def header(self, ref, texts, mid="N"):
        S = self.S
        fp = S.board.FindFootprintByReference(ref)
        if fp is None:
            return
        pads = {p.GetNumber(): S.B(p.GetPosition()) for p in fp.Pads()}
        body = self.bodies[ref]
        p1, pn = pads["1"], pads[str(len(pads))]
        horiz = abs(pn[0] - p1[0]) >= abs(pn[1] - p1[1])
        if len(texts) == 1:
            prefs = ("N", "S", "E", "W") if horiz else ("E", "W", "N", "S")
            prefs = (mid,) + tuple(p for p in prefs if p != mid)
        for size in HEADER:
            for tier in TIERS:
                for gap in tier:
                    if len(texts) == 1:
                        options = [[(texts[0], s, ((body[0] + body[2]) / 2, (body[1] + body[3]) / 2), 0)] for s in prefs]
                    else:
                        if horiz:
                            e1, e3 = ("W", "E") if p1[0] < pn[0] else ("E", "W")
                            mids = ("N", "S")
                        else:
                            e1, e3 = ("N", "S") if p1[1] < pn[1] else ("S", "N")
                            mids = ("W", "E")
                        if mid in mids:
                            mids = (mid,) + tuple(m for m in mids if m != mid)
                        ends = [[(texts[0], e1, p1, 0), (texts[1], m, pads["2"], 0), (texts[2], e3, pn, 0)] for m in mids]
                        # or every pin labelled beside itself, all on one side, the text turned along the pins
                        sides = ("N", "S") if horiz else ("W", "E")
                        pins = [[(t, sd, pads[str(k + 1)], 90 if horiz else 0) for k, t in enumerate(texts)] for sd in sides]
                        options = pins + ends if mid == "pins" else ends + pins
                    for opt in options:
                        cands = []
                        for item in opt:
                            text, side, anc = item[:3]
                            ang = item[3] if len(item) > 3 else 0
                            if not text:
                                continue
                            ext = self.measure(text, size, ang)
                            cands.append((text, self.at_side(body, anc, side, gap, ext), "pin", ref, size, ang))
                        if self.fits(cands, owners=False) and all(
                                LR.owner_ok(c[1], body, self.others(ref)) is None for c in cands):
                            self.commit(cands)
                            return
        whys = []
        for opt in options:
            cands = [(it[0], self.at_side(body, it[2], it[1], 0.25, self.measure(it[0], HEADER[-1], it[3])), "pin", ref, HEADER[-1], it[3])
                     for it in opt if it[0]]
            whys.append(" ".join(c[0] + ":" + it[1] for c, it in zip(cands, opt)) + " -> " + str(
                self.fits(cands, owners=False, why=True) or [LR.owner_ok(c[1], body, self.others(ref)) for c in cands]))
        S.label_failures.append("%s: no place for its labels %s\n        %s" % (ref, " / ".join(t for t in texts if t), "\n        ".join(whys)))

    # ---- all of them ------------------------------------------------------------------------------
    def run(self):
        groups = LR.rows(self.items)
        rank = {"SMA": 0, "tap": 1, "TP": 3}
        groups.sort(key=lambda g: (rank[self.by[g[1][0]]["family"]], -len(g[1]), g[1][0]))
        done_headers = False
        for axis, refs in groups:
            if not done_headers and rank[self.by[refs[0]]["family"]] >= 3:
                for ref, texts, mid in HEADERS:
                    self.header(ref, texts, mid)
                done_headers = True
            self.row(axis, refs)
        if not done_headers:
            for ref, texts, mid in HEADERS:
                self.header(ref, texts, mid)
        return groups


def place(S):
    L = Labeller(S)
    groups = L.run()
    for msg in S.label_failures:
        S.problems.append("LABEL " + msg)
    # what is placed after (the chips' names, the designators, the block titles) keeps SEP from a connector's
    # labels: Y101's "VCXO" beside REF OUT read as one name, "VCXO REF OUT" (Response 15)
    # along a name's own line the gap must be wider still: 0.8 mm still read as one phrase
    k, kx = SEP - 0.12, 2.0
    for ref, b in L.boxes:
        S.placed[pcbnew.F_SilkS].append((b[0] - k, b[1] - k, b[2] + k, b[3] + k, "beside %s's label" % ref))
        S.placed[pcbnew.F_SilkS].append((b[0] - kx, b[1] + 0.1, b[2] + kx, b[3] - 0.1, "in line with %s's label" % ref))
    return L, groups
