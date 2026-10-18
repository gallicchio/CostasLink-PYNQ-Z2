"""Connector labels by rows (Response 15), the rules both sides use: gen/silk_jacks.py places the
labels by them and tools/label_check.py checks the finished board by them.

Labelled: every SMA, every U.FL and MMCX tap and every test pad on the top, by its value (a test
pad's rail without the "+").  A row: connectors of one footprint (an SMA, a U.FL, an MMCX, a test pad),
the SMAs also of one rotation, whose anchors line up within ALIGN along x or y and follow each
other at most GAP_MAX apart (a connector alone is a row of one).  Every label of a row stands in
the same relation to its own connector: the same side (N, S, E, W or a corner), the same gap from
the connector's body, the same offset along it (centred on the anchor's axis), the same angle and
the same height.  And every label is unmistakably its own connector's: no other connector, jumper
or header body is nearly as near its near end (owner_ok; CLAUDE_PCB.md sections 4 and 6).
"""
import math

ALIGN = 0.6                                   # mm: anchors this close in x (or y) line up
GAP_MAX = {"SMA": 200.0, "tap": 10.0, "TP": 6.0}   # the SMAs along one edge are one row, however far apart
EXCLUDE = ("J301", "J302", "J303")            # the USB-C, the socket, the T/R header (pin labels)
OWNER_ADD, OWNER_MUL = 1.0, 1.5               # from the label's near end, another body >= own + 1 mm and >= 1.5 x own
BOX_ADD = 0.5                                 # and the label's box >= 0.5 mm farther from any other body than from its own
TOL = 0.06                                    # mm: "the same" gap and offset
# a limit left off, and why (printed by every check, so it is a decision on record, not an accident)
LIMIT_EXEMPT = {
    "J208": "TRIG IN MON sits between TRIG B's and TRIG IN's names with room for its own name only; its level is "
            "every /10 tap's, 0-0.3 V/50R, printed under the window monitors and CMP I MON",
    "J502": "Q SLOW MON sits between U502 and JP102 with room for its name's column only; its level is I SLOW MON's, "
            "0-3.3 V through 1k, printed beside J501",
    "J290": "LD TX sits between the lower rail row's name columns with room for its name only; its level is every /10 tap's, "
            "0-0.3 V/50R, printed under the window monitors",
    "J190": "LD RX likewise",
    "J394": "3V3_PLL_TX (U.FL) stands alone beside its regulator with room for its name's column only; its level, DC through 1k, "
            "is printed under the rail row (J390-J393)",
    "J395": "3V3_PLL_RX likewise",
    "J396": "3V3_OSC likewise",
    "J109": "LO RX MON sits inside the RX synthesizer's loop filter with room for its name only (Prompt 35: the LD RX jack took "
            "the last of it); its level is LO TX MON's, 0 dBm, 50R, printed beside J204",
}


def family(ref, fpname):
    if ref in EXCLUDE:
        return None
    if ref.startswith("TP"):
        return "TP"
    if ref.startswith("J") and not ref.startswith("JP"):
        if "SMA" in fpname:
            return "SMA"
        if "U.FL" in fpname or "MMCX" in fpname:
            return "tap"
    return None


def name_of(ref, value):
    return value.replace("+", "") if ref.startswith("TP") else value


def rows(items):
    """items: dicts with ref, family, fp (the footprint's name), anchor (x, y), rot.  Returns [(axis, [refs])]: axis 'x' for a
    row along x, 'y' for a column, None for a connector alone; members ordered along the axis."""
    by = {it["ref"]: it for it in items}
    refs = sorted(by)

    def groups(axis):
        parent = {r: r for r in refs}

        def find(r):
            while parent[r] != r:
                parent[r] = parent[parent[r]]
                r = parent[r]
            return r
        for i, a in enumerate(refs):
            for b in refs[i + 1:]:
                A, Bb = by[a], by[b]
                if A["family"] != Bb["family"] or A.get("fp") != Bb.get("fp"):
                    continue                          # one kind of connector: a U.FL and an MMCX are not a row
                if A["family"] == "SMA" and round(A["rot"]) % 360 != round(Bb["rot"]) % 360:
                    continue
                dx, dy = abs(A["anchor"][0] - Bb["anchor"][0]), abs(A["anchor"][1] - Bb["anchor"][1])
                if axis == "x" and dy <= ALIGN and dx <= GAP_MAX[A["family"]]:
                    parent[find(a)] = find(b)
                if axis == "y" and dx <= ALIGN and dy <= GAP_MAX[A["family"]]:
                    parent[find(a)] = find(b)
        out = {}
        for r in refs:
            out.setdefault(find(r), []).append(r)
        return [g for g in out.values() if len(g) > 1]
    hx, vy = groups("x"), groups("y")
    taken = {}
    for axis, gs in (("x", hx), ("y", vy)):
        for g in gs:
            for r in g:
                if r not in taken or len(taken[r][1]) < len(g):
                    taken[r] = (axis, g)
    result, seen = [], set()
    for r in refs:
        if r in seen:
            continue
        if r in taken:
            axis, g = taken[r]
            members = [m for m in g if taken.get(m, (None, None))[1] is g]
            k = 0 if axis == "x" else 1
            members.sort(key=lambda m: by[m]["anchor"][k])
            result.append((axis, members))
            seen.update(members)
        else:
            result.append((None, [r]))
            seen.add(r)
    return result


def box_dist(a, b):
    """the gap between two rectangles (0 if they touch or overlap)"""
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def point_dist(p, b):
    return math.hypot(max(b[0] - p[0], 0.0, p[0] - b[2]), max(b[1] - p[1], 0.0, p[1] - b[3]))


def owner_ok(box, own, others, box_add=True):
    """None if the label is unmistakably its own body's, else the body that competes.  A reader ties
    a label to what is at its near end: from the label's point nearest its own body's centre, every
    other body at least OWNER_ADD farther and OWNER_MUL times as far; and no other body's box within
    BOX_ADD of being as near as its own (box_add=False for a limit: it is read with its name)"""
    ox, oy = (own[0] + own[2]) / 2.0, (own[1] + own[3]) / 2.0
    p = (min(max(ox, box[0]), box[2]), min(max(oy, box[1]), box[3]))
    d, dbox = point_dist(p, own), box_dist(box, own)
    for ref, b in others:
        e = point_dist(p, b)
        if e < d + OWNER_ADD or e < OWNER_MUL * d or (box_add and box_dist(box, b) < dbox + BOX_ADD):
            return ref
    return None


def relation(body, anchor, box, eps=0.02):
    """(side, gap, along): which side of the body the label is on, how far from the body, and its
    centre's offset along that side from the anchor (a corner: both gaps, offset 0)"""
    v = "N" if box[3] <= body[1] + eps else ("S" if box[1] >= body[3] - eps else "")
    h = "W" if box[2] <= body[0] + eps else ("E" if box[0] >= body[2] - eps else "")
    side = v + h
    cx, cy = (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0
    if side == "N":
        return side, body[1] - box[3], cx - anchor[0]
    if side == "S":
        return side, box[1] - body[3], cx - anchor[0]
    if side == "E":
        return side, box[0] - body[2], cy - anchor[1]
    if side == "W":
        return side, body[0] - box[2], cy - anchor[1]
    if side:
        gx = box[0] - body[2] if "E" in side else body[0] - box[2]
        gy = body[1] - box[3] if "N" in side else box[1] - body[3]
        return side, (round(gx, 3), round(gy, 3)), 0.0
    return "over", 0.0, 0.0


def same(a, b):
    """two relations the same, within TOL"""
    if a[0] != b[0]:
        return False
    ga, gb = a[1], b[1]
    if isinstance(ga, tuple):
        if any(abs(x - y) > TOL for x, y in zip(ga, gb)):
            return False
    elif abs(ga - gb) > TOL:
        return False
    return abs(a[2] - b[2]) <= TOL


def body_of(fp, B, W, H):
    """a footprint's body on the board, mm: its pads, its fab outline and its own silkscreen outline
    (a test pad's ring, a header's pin-1 corner), clipped to the board (an edge SMA's barrel is off it)"""
    import pcbnew
    bb = None
    for it in list(fp.Pads()) + [g for g in fp.GraphicalItems() if g.GetClass() == "PCB_SHAPE" and g.GetLayer() in
                                 (pcbnew.F_Fab, pcbnew.B_Fab, pcbnew.F_SilkS, pcbnew.B_SilkS)]:
        b = it.GetBoundingBox()
        if bb is None:
            bb = b
        else:
            bb.Merge(b)
    x0, y0 = B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
    x1, y1 = B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
    return (max(x0, 0.0), max(y0, 0.0), min(x1, W), min(y1, H))


def anchor_of(fp, fam, B):
    """where a connector's label is centred along its side: an SMA's centre pin, a tap's centre, a pad"""
    if fam in ("SMA", "TP"):
        for pad in fp.Pads():
            if pad.GetNumber() == "1":
                return B(pad.GetPosition())
    return B(fp.GetPosition())
