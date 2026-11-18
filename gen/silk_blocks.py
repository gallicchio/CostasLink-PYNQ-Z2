"""The silkscreen's section boxes: one box per functional block (gen/placement.BLOCKS), its name
inside under the top edge, and the check CLAUDE_PCB.md section 5 asks for: every part of the block
inside its box, nothing of another block inside it, no two boxes overlapping, no box line over a
pad, a part or a label.  Called by gen/silk.py; the boxes are computed from the placed courtyards,
so they follow the placement.
"""
import json, os
import pcbnew
import placement as PL

MARGIN = 0.7            # from the outermost courtyard to the box line
LABEL_H = 1.0
PLAN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "placement.json")


def courtyard(S, fp):
    """The part's courtyard box in board mm (its pads' box if the footprint draws none)."""
    layer = pcbnew.B_CrtYd if fp.GetLayer() == pcbnew.B_Cu else pcbnew.F_CrtYd
    # (BOX2I.Merge returns a non-owning proxy of the box; keeping THAT and dropping the owner freed
    # the box under it: KiCad aborted with "malloc(): unaligned tcache chunk".  Merge in place.)
    bb = None
    for it in fp.GraphicalItems():
        if it.GetLayer() == layer and it.GetClass() == "PCB_SHAPE":
            if bb is None:
                bb = it.GetBoundingBox()
            else:
                bb.Merge(it.GetBoundingBox())
    if bb is None:
        for pad in fp.Pads():
            if bb is None:
                bb = pad.GetBoundingBox()
            else:
                bb.Merge(pad.GetBoundingBox())
    return S.box(bb)


def boxes(S, fps):
    """Draw the boxes and their names; returns the list of problems found."""
    plan = json.load(open(PLAN))
    group = plan.get("group", {})
    names = plan.get("blocks", [])
    probs = []
    court = {ref: courtyard(S, fp) for ref, fp in fps.items() if fp.GetLayer() != pcbnew.B_Cu}
    rect = {}
    for name in names:
        refs = [r for r, g in group.items() if g == name and r in court]
        if not refs:
            probs.append("box %r has no parts on the top side" % name)
            continue
        x0 = min(court[r][0] for r in refs) - MARGIN
        y0 = min(court[r][1] for r in refs) - MARGIN
        x1 = max(court[r][2] for r in refs) + MARGIN
        y1 = max(court[r][3] for r in refs) + MARGIN
        # an SMA's barrel hangs past the edge: the box stops inside the board
        W, H = PL.BOARD["w"], PL.BOARD["h"]
        x0, y0, x1, y1 = max(x0, 0.8), max(y0, 0.8), min(x1, W - 0.8), min(y1, H - 0.8)
        rect[name] = (x0, y0, x1, y1)
    # strangers inside a box, and boxes that overlap
    for name, (x0, y0, x1, y1) in rect.items():
        inside = [r for r, c in court.items() if group.get(r) not in (name, None) and not r.startswith("H")
                  and c[0] >= x0 and c[2] <= x1 and c[1] >= y0 and c[3] <= y1]
        if inside:
            probs.append("box %r holds %d part(s) of other blocks: %s" % (name.split(":")[0], len(inside), " ".join(sorted(inside)[:12])))
    done = list(rect.items())
    for i, (na, a) in enumerate(done):
        for nb, b in done[i + 1:]:
            if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                probs.append("boxes %r and %r overlap" % (na.split(":")[0], nb.split(":")[0]))
    # draw: the name first (so the lines keep off it); the four sides only when every one of them
    # is clear (a box line through a part is worse than no box; the name alone still says what
    # the region is)
    drawn = 0
    for name, (x0, y0, x1, y1) in rect.items():
        short = name.split(":")[0]
        S.label(short, x0 + 0.6, y0 + 0.5 + LABEL_H / 2, h=LABEL_H, justify="left", what="box name")
        sides = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
        clear = all(S.free(pcbnew.F_SilkS, (min(a[0], b[0]) - 0.1, min(a[1], b[1]) - 0.1, max(a[0], b[0]) + 0.1, max(a[1], b[1]) + 0.1)) is None
                    for a, b in sides)
        if clear:
            S.line([(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)])
            drawn += 1
        else:
            probs.append("box %r drawn as its name only: a side would cross a part" % short)
    return probs, rect
