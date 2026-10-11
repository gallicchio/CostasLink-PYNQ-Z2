"""Helpers every sheet's generator uses (after GPiBridge's gen/schematic.py).

A sheet module calls begin(sch) and then places parts with part()/hpart()/vpart(),
draws wires with W(), and puts notes at nodes with note().  Coordinates are
millimetres, x right, y DOWN, on the 1.27 mm grid.

Reference designators are numbered by board, so the silkscreen says which board a
part belongs to: base 1-99, tree 101-199, perch 201-299, bat 301-399, the owl token
401-499, the cat token 501-599.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import kisch
from parts import PARTS, LIB
kisch.POWER_LIB = LIB

G = 2.54
NOTE = (255, 255, 194)
SIG = (214, 236, 255)          # the signal on a wire: frequency, level, bandwidth, DC (gen/levels.py)
S = None                 # the sheet being drawn
REFS = {}                # ref -> part key, across every sheet (one panel, one netlist)
_flags = None


_n = {}
_base = 0
ROLES = {}               # role -> ref: what each part is for, for the placement (gen/placement.py)
_tag = None


def tag(name):
    """Name the role of the next part placed (part(), down(), up(), series()...)."""
    global _tag
    assert name not in ROLES, "role %s used twice" % name
    _tag = name


def begin(sch, ref_base=0):
    """Start drawing `sch`; its automatically numbered references (R, C, D, TP) start
    after ref_base (0 for the base board, 100 for the tree, 200 for the perch...)."""
    global S, _flags, _base
    S = sch
    _flags = iter("#FLG_%s%02d" % (sch.filename.split(".")[0], i) for i in range(1, 99))
    _base = ref_base
    _n.clear()


def part(key, ref, x, y, rot=0, unit=1, value=None, mirror=None, text="auto", fsize=1.27, sym=None, **kw):
    """Place PARTS[key] as `ref`.  text: "auto" (reference above, value below), "right"
    (both to the right of a vertical part), "left", or "hide"."""
    assert ref not in REFS or REFS[ref] == key, "reference %s used twice" % ref
    p = dict(PARTS[key])
    if sym:
        p["sym"] = LIB + ":" + sym
    fields = {"MPN": p["mpn"]} if p.get("mpn") else {}
    value = p["value"] if value is None else value
    if text == "right":
        dx = 2.8 if p["sym"].endswith(":C") or p["sym"].endswith(":C_Polarized") else (3.4 if p["sym"].endswith(":LED") or p["sym"].endswith(":D_TVS") else 1.9)
        kw.setdefault("ref_at", (x + dx, y - 0.3))
        kw.setdefault("val_at", (x + dx, y + 0.3))
    elif text == "left":
        dx = 2.8 if p["sym"].endswith(":C") or p["sym"].endswith(":C_Polarized") else 1.9
        kw.setdefault("ref_at", (x - dx, y - 0.3))
        kw.setdefault("val_at", (x - dx, y + 0.3))
        kw.setdefault("justify", "right")
    elif text == "hide":
        kw["hide_ref"] = kw["hide_value"] = True
    if p["fp"].split(":")[-1].startswith("Coil_"):
        kw.setdefault("in_bom", False)       # copper, not a part: as its footprint says
    pl = S.sym(p["sym"], x, y, rot=rot, ref=ref, value=value, footprint=p["fp"], unit=unit, mirror=mirror,
               lcsc=p["lcsc"], fields=fields, fsize=fsize, **kw)
    REFS[ref] = key
    global _tag
    if _tag:
        ROLES[_tag] = ref
        _tag = None
    return pl


def part_at_pin(key, ref, pin, x, y, rot=0, **kw):
    """Place PARTS[key] so that its `pin` lands exactly at (x, y) (a chip whose RF pin must sit
    on a line that other parts share)."""
    lib_id = PARTS[key]["sym"] if not kw.get("sym") else LIB + ":" + kw["sym"]
    node, pins = kisch.SYMS.get(lib_id)
    unit = kw.get("unit", 1)
    for p in pins:
        if p["num"] == str(pin) and p["unit"] in (0, unit):
            dx, dy = kisch._xform(p["x"], p["y"], rot, kw.get("mirror"))
            return part(key, ref, x - dx, y - dy, rot=rot, **kw)
    raise KeyError("pin %s not on %s" % (pin, lib_id))


def _pins(pl):
    _, pins = kisch.SYMS.get(pl.lib_id)
    seen, out = set(), []
    for p in pins:
        if p["unit"] in (0, pl.unit):
            xy = pl.pin(p["num"])
            if xy not in seen:
                seen.add(xy)
                out.append(xy)
    return out


def hpart(key, ref, xc, y, **kw):
    """A two-pin part lying on a horizontal line; returns (left, right)."""
    pl = part(key, ref, xc, y, rot=90, **kw)
    a, b = sorted(_pins(pl), key=lambda q: q[0])
    return a, b


def vpart(key, ref, x, yc, **kw):
    """A two-pin part standing on a vertical line; returns (top, bottom)."""
    kw.setdefault("text", "right")
    if PARTS[key]["sym"].endswith(":D_TVS"):
        kw.setdefault("rot", 270)                    # KiCad draws diodes lying down; 270 stands it up with the cathode (pin 1) on top
    pl = part(key, ref, x, yc, **kw)
    a, b = sorted(_pins(pl), key=lambda q: q[1])
    return a, b


def gnd(x, y, net="GND"):
    return S.power(net, x, y)


def flag(net, x, y, **kw):
    return S.power(net, x, y, **kw)


WIRE_ORIGIN = {}         # (x0, y0, x1, y1) -> "file:line" of the call that drew it (for the checker)


def W(*pts):
    import inspect
    fr = inspect.stack()[1]
    where = "%s:%d" % (os.path.basename(fr.filename), fr.lineno)
    for a, b in zip(pts, pts[1:]):
        key = tuple(round(v, 2) for v in (a[0], a[1], b[0], b[1]))
        WIRE_ORIGIN[key] = where
        WIRE_ORIGIN[(key[2], key[3], key[0], key[1])] = where
    S.wires(*pts)


def J(x, y):
    S.junction(x, y)


def pwr_flag(x, y, rot=0):
    return S.sym(PARTS["PWR_FLAG"]["sym"], x, y, rot=rot, ref=next(_flags), value="PWR_FLAG", footprint="",
                 in_bom=False, on_board=False, hide_ref=True, hide_value=True)


def label(x, y, name, size=1.0, justify="left bottom"):
    """A net name on a wire (the wire carries on: nothing disappears)."""
    S.label(x, y, name, size=size, justify=justify)


PENDING = []             # notes wait until the sheet is drawn, then flush_notes() places them clear of everything


def note(x, y, text, cols=44, size=1.0):
    PENDING.append(("note", x, y, text, cols, size, NOTE))


def sig(x, y, text, cols=24, size=1.0):
    """A blue box stating what is on the wire beside it: frequency, level, bandwidth, DC offset
    (the strings come from gen/levels.py, i.e. from sim/budget.py)."""
    PENDING.append(("sig", x, y, text, cols, size, SIG))


def _note_box(x, y, text, cols, size):
    import math
    s = kisch.wrap(text, cols)
    ww = kisch.text_w(s, size) * 1.15 + 2.5
    h = kisch.text_h(s, size) * 1.05 + 2.4
    ww, h = math.ceil(ww / kisch.GRID) * kisch.GRID, math.ceil(h / kisch.GRID) * kisch.GRID
    return (x, y, x + ww, y + h)


def _area(a, b, pad=0.0):
    w = min(a[2], b[2]) - max(a[0], b[0]) - pad
    h = min(a[3], b[3]) - max(a[1], b[1]) - pad
    return w * h if (w > 0 and h > 0) else 0.0


def _cost(box, texts, items, segs, W, H):
    c = 0.0
    for t in texts:
        c += _area(box, t)
    for it in items:
        c += _area(box, it)
    x0, y0, x1, y1 = box[0] - 0.5, box[1] - 0.5, box[2] + 0.5, box[3] + 0.5
    for (a, b, cc, d) in segs:
        if (min(a, cc) < x1 and x0 < max(a, cc) and min(b, d) < y1 and y0 < max(b, d)):
            c += 30.0
    if x0 < 8 or y0 < 8 or x1 > W - 8 or y1 > H - 25:
        c += 1000.0
    return c


def flush_notes(S, radius_x=50.0, radius_y=30.0):
    """Place every pending note at the nearest clear spot (texts, symbol bodies, wires, the page)
    within radius of where it was asked for, nearest first; returns the report lines."""
    report = []
    W, H = S.W, S.H
    steps_x = [0.0] + [s * d for s in (2.54, 5.08, 7.62, 10.16, 12.7, 15.24, 17.78, 20.32, 25.4, 30.48, 35.56, 40.64, 45.72, 50.8) if s <= radius_x for d in (1, -1)]
    steps_y = [0.0] + [s * d for s in (2.54, 5.08, 7.62, 10.16, 12.7, 15.24, 17.78, 20.32, 22.86, 25.4, 27.94, 30.48) if s <= radius_y for d in (1, -1)]
    cands = sorted(((dx, dy) for dx in steps_x for dy in steps_y), key=lambda d: (abs(d[0]) + abs(d[1]), abs(d[1]), abs(d[0])))
    for kind, x, y, text, cols, size, color in list(PENDING):
        box0 = _note_box(x, y, text, cols, size)
        win = (box0[0] - radius_x - 5, box0[1] - radius_y - 5, box0[2] + radius_x + 5, box0[3] + radius_y + 5)
        near = lambda b: b[0] < win[2] and b[2] > win[0] and b[1] < win[3] and b[3] > win[1]
        texts = [t for t in S.texts if near(t)]
        items = [it for it in S.items if not it[4].startswith("sheet:") and near(it)]
        segs = [sg for sg in S._segs if near((min(sg[0], sg[2]), min(sg[1], sg[3]), max(sg[0], sg[2]), max(sg[1], sg[3])))]
        best = None
        for dx, dy in cands:
            box = (box0[0] + dx, box0[1] + dy, box0[2] + dx, box0[3] + dy)
            c = _cost(box, texts, items, segs, W, H)
            if best is None or c < best[0]:
                best = (c, dx, dy)
            if c == 0:
                break
        c, dx, dy = best
        S.note(x + dx, y + dy, text, size=size, cols=cols, color=color)
        if c > 0:
            report.append("  note not clear (cost %.0f): %r at (%.0f,%.0f)" % (c, text[:40], x + dx, y + dy))
        elif abs(dx) + abs(dy) > 15:
            report.append("  note moved %.0f,%.0f: %r" % (dx, dy, text[:40]))
    PENDING.clear()
    return report


def title(x, y, text, size=2.0):
    return S.text(x, y, text, size=size, bold=True)


def box(x, y, w, h):
    """A dashed box round a block."""
    S.rect(x, y, w, h, style="dash", width=0.2)


def decouple(xpin, ypin, caps, refs, rail, gnd_net="GND", side=+1, dy=7.62):
    """Decoupling at a supply pin that points UP: a short riser to a junction, the rail's
    flag above, and each capacitor hanging to one side of the riser to its own ground.
    caps: part keys, nearest first; refs: their references; side: +1 right, -1 left."""
    yj = ypin - dy
    W((xpin, ypin), (xpin, yj))
    flag(rail, xpin, yj - 2.54)
    W((xpin, yj), (xpin, yj - 2.54))
    x = xpin
    for k, (key, ref) in enumerate(zip(caps, refs)):
        x2 = xpin + side * (k + 1) * 5.08
        W((x, yj), (x2, yj))
        x = x2
        t, b = vpart(key, ref, x2, yj + 3.81, fsize=1.0, text="right" if side > 0 else "left")
        gnd(*b, net=gnd_net)
    J(xpin, yj)
    return yj


# ---- drawing helpers every sheet uses ----------------------------------------------
def nref(prefix):
    """The next free reference of a kind (R, C, D, TP), in the order the sheet is drawn,
    after this board's base (begin())."""
    _n[prefix] = _n.get(prefix, _base) + 1
    while "%s%d" % (prefix, _n[prefix]) in REFS:
        _n[prefix] += 1
    return "%s%d" % (prefix, _n[prefix])


def kind(key):
    return "C" if key.startswith("C") else "L" if key.startswith("L") else "D" if key.startswith(("TVS", "LED", "D")) else "R"


def down(key, x, y, net="GND", text="right", ref=None, drop=G, fsize=1.0):
    """A two-pin part hanging from the node (x, y): a short drop, the part, then ground
    (or `net`'s flag, or nothing when net is None).  Returns (reference, bottom pin)."""
    ref = ref or nref(kind(key))
    t, b = vpart(key, ref, x, y + drop + 3.81, fsize=fsize, text=text)
    W((x, y), t)
    if net:
        gnd(*b, net=net)
    return ref, b


def up(key, x, y, rail, text="right", ref=None, rise=G, fsize=1.0):
    """A two-pin part standing on the node (x, y), `rail`'s flag on top (a pull-up)."""
    ref = ref or nref(kind(key))
    t, b = vpart(key, ref, x, y - rise - 3.81, fsize=fsize, text=text)
    W(b, (x, y))
    flag(rail, *t)
    return ref, t


def series(key, xc, y, ref=None, above=True, fsize=1.0):
    """A two-pin part lying on a horizontal line, its name and value stacked above it
    (or below); returns (left, right)."""
    ref = ref or nref(kind(key))
    if above:
        return hpart(key, ref, xc, y, ref_at=(xc, y - 4.3), val_at=(xc, y - 3.9), fsize=fsize, justify="center")
    return hpart(key, ref, xc, y, ref_at=(xc, y + 3.9), val_at=(xc, y + 4.3), fsize=fsize, justify="center")


def tp(x, y, value, ref=None, key="TP"):
    """A test pad at (x, y), labelled with what it reads."""
    ref = ref or nref("TP")
    part(key, ref, x, y, value=value, ref_at=(x + 1.5, y - 3.6), val_at=(x + 1.5, y - 1.9), fsize=1.0)
    return ref


def line(y, xs):
    """A horizontal wire through the points xs on row y (pins, taps)."""
    xs = sorted(set(round(x, 3) for x in xs))
    for a, b in zip(xs, xs[1:]):
        W((a, y), (b, y))


def vline(x, ys):
    ys = sorted(set(round(y, 3) for y in ys))
    for a, b in zip(ys, ys[1:]):
        W((x, a), (x, b))


def diode(key, ref, xc, y):
    """A diode lying on a horizontal line, anode on the left; returns (anode, cathode)."""
    d = part(key, ref, xc, y, rot=180, ref_at=(xc, y - 3.0), val_at=(xc, y + 3.3), fsize=1.0)
    return d.pin("2"), d.pin("1")
