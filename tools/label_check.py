#!/usr/bin/env python3
"""Check the connectors' labels on the written board (Response 15), independently of the code that
placed them: KiCad's own text boxes, read off hardware/CostasLink-PYNQ-Z2.kicad_pcb.

    python3 tools/label_check.py

Jason: "There should be a big-font silk screen right next to the connector, so it's obvious what it's
for ... If there are SMAs in a row, their labels should all be in the same relative orientation ...
This consistency requirement needs to be enforced."  For every SMA, U.FL, MMCX and test pad on top:
  * its name is printed (the value; a test pad's rail without the "+"), at least 1.0 mm tall for an SMA,
    0.9 mm for a tap or a pad, and within 3 mm of its body;
  * the name is unmistakably its own (gen/label_rows.owner_ok: from the name's near end no other
    connector, header or LED body nearly as near, and none of their boxes within 0.5 mm of as near);
  * in a row (gen/label_rows.rows: one footprint, lined up), every name stands in the same relation to
    its own connector (side, gap, offset along the side), at the same angle and height;
  * its limit (gen/levels.LIMITS) is printed, and in a row every limit sits the same way from its name
    (or, the members all sharing one limit, once for the row);
and every header's pin labels (gen/placement.HEADER_LABELS) are printed within 3 mm of it and are its own.
Writes hardware/checks/labels.json; exit status 1 on any violation.  gen/board.py's silk stage runs it,
and mfg/make_release.py refuses a board that fails it.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))

if "--inside" not in sys.argv:
    import subprocess, kienv
    r = subprocess.run(kienv.python() + [os.path.abspath(__file__), "--inside"] + sys.argv[1:], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write("".join(l + "\n" for l in r.stdout.splitlines() if "Font '" not in l))
    sys.exit(r.returncode)

import pcbnew
import board_info as BI
import label_rows as LR
import levels as LV
import placement as PL

NEAR = 3.0
MIN_H = {"SMA": 1.0, "tap": 0.9, "TP": 0.9}
OUT = os.path.join(BI.CHECKS, "labels.json")


def main():
    board = pcbnew.LoadBoard(BI.PCB)
    ox, oy = BI.ORIGIN
    W, H = PL.BOARD["w"], PL.BOARD["h"]

    def Bv(v):
        return (pcbnew.ToMM(v.x) - ox, pcbnew.ToMM(v.y) - oy)

    def box(t):
        bb = t.GetEffectiveTextShape().BBox()
        a, b = Bv(pcbnew.VECTOR2I(bb.GetX(), bb.GetY())), Bv(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
        return (a[0], a[1], b[0], b[1])

    texts = []
    for d in board.GetDrawings():
        if d.GetClass() == "PCB_TEXT" and d.GetLayer() == pcbnew.F_SilkS:
            texts.append(dict(text=d.GetText(), box=box(d), angle=round(d.GetTextAngleDegrees()) % 180,
                              h=round(pcbnew.ToMM(d.GetTextHeight()), 3)))
    items, bodies = [], {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if fp.GetLayer() == pcbnew.B_Cu:
            continue
        name = str(fp.GetFPID().GetLibItemName())
        fam = LR.family(ref, name)
        if fam or ref.startswith(("JP", "J30", "D30")):
            bodies[ref] = LR.body_of(fp, Bv, W, H)
        if fam:
            items.append(dict(ref=ref, family=fam, fp=name, rot=fp.GetOrientationDegrees(), anchor=LR.anchor_of(fp, fam, Bv),
                              name=LR.name_of(ref, fp.GetValue()),
                              limit="" if fam == "TP" else LV.LIMITS.get(fp.GetValue(), ("", ""))[0]))
    by = {it["ref"]: it for it in items}
    bad, found, notes = [], {}, []

    def nearest(text, body):
        cands = [t for t in texts if t["text"] == text]
        cands.sort(key=lambda t: LR.box_dist(t["box"], body))
        return cands[0] if cands and LR.box_dist(cands[0]["box"], body) <= NEAR else None

    for it in items:
        r = it["ref"]
        t = nearest(it["name"], bodies[r])
        if t is None:
            bad.append("%s: its name %r is not printed within %g mm of it" % (r, it["name"], NEAR))
            continue
        found[r] = t
        if t["h"] < MIN_H[it["family"]] - 1e-6:
            bad.append("%s: %r is %.2f mm tall, under the %.1f mm a %s's name needs" % (r, it["name"], t["h"], MIN_H[it["family"]], it["family"]))
        o = LR.owner_ok(t["box"], bodies[r], [(k, b) for k, b in bodies.items() if k != r])
        if o:
            bad.append("%s: %r could be read as %s's" % (r, it["name"], o))
    rows = LR.rows(items)
    report = []
    for axis, refs in rows:
        rel = {}
        for r in refs:
            if r in found:
                rel[r] = LR.relation(bodies[r], by[r]["anchor"], found[r]["box"]) + (found[r]["angle"], found[r]["h"])
        line = dict(row=refs, axis=axis, relations={r: [v[0], v[1] if not isinstance(v[1], tuple) else list(v[1]), round(v[2], 3), v[3], v[4]]
                                                     for r, v in rel.items()})
        report.append(line)
        if any(v[0] == "over" for v in rel.values()):
            bad.append("%s: a name over its own connector" % " ".join(refs))
        first = refs[0]
        for r in refs[1:]:
            if first in rel and r in rel:
                a, b = rel[first], rel[r]
                if not LR.same(a[:3], b[:3]) or a[3] != b[3] or abs(a[4] - b[4]) > 1e-3:
                    bad.append("row %s: %s's name is %s %s from it (angle %d, %.2f mm), %s's %s %s (angle %d, %.2f mm)"
                               % (" ".join(refs), first, a[0], a[1:3], a[3], a[4], r, b[0], b[1:3], b[3], b[4]))
        # the limits
        lims = [by[r]["limit"] for r in refs]
        if not any(lims):
            continue
        if len(refs) > 1 and len(set(lims)) == 1:
            if all(r in LR.LIMIT_EXEMPT for r in refs):
                notes.append("row %s: its limit left off: %s" % (" ".join(refs), LR.LIMIT_EXEMPT[refs[0]]))
                continue
            # the shared limit stands beyond the NAMES (a column row's names hang 10 mm from the bodies): search round both
            boxes = [bodies[r] for r in refs] + [found[r]["box"] for r in refs if r in found]
            row_box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
            if nearest(lims[0], row_box) is None:
                bad.append("row %s: the shared limit %r is not printed by the row" % (" ".join(refs), lims[0]))
            continue
        offs = {}
        for r in refs:
            if not by[r]["limit"] or r not in found:
                continue
            if r in LR.LIMIT_EXEMPT and nearest(by[r]["limit"], bodies[r]) is None:
                notes.append("%s: its limit left off: %s" % (r, LR.LIMIT_EXEMPT[r]))
                continue
            lt = nearest(by[r]["limit"], found[r]["box"]) or nearest(by[r]["limit"], bodies[r])
            if lt is None:
                bad.append("%s: its limit %r is not printed beside its name or its connector" % (r, by[r]["limit"]))
                continue
            o = LR.owner_ok(lt["box"], bodies[r], [(k, b) for k, b in bodies.items() if k != r], box_add=False)
            if o and LR.box_dist(lt["box"], found[r]["box"]) > 0.6:
                bad.append("%s: its limit %r could be read as %s's" % (r, by[r]["limit"], o))
            nb, lb = found[r]["box"], lt["box"]
            offs[r] = (round(lb[0] - nb[0], 2), round(lb[1] - nb[1], 2), round(lb[2] - nb[2], 2), round(lb[3] - nb[3], 2))
        vals = list(offs.items())
        for r, v in vals[1:]:
            r0, v0 = vals[0]
            # the same side of the name and the same edge in line (left edges, right edges or centres)
            extra = 1.2 * abs(by[r]["limit"].count("\n") - by[r0]["limit"].count("\n"))   # a two-line limit beside one-line ones (TRIG A / B)
            same_side = abs(v[1] - v0[1]) <= LR.TOL and abs(v[3] - v0[3]) <= 0.6 + extra
            in_line = min(abs(v[0] - v0[0]), abs(v[2] - v0[2]), abs((v[0] + v[2]) - (v0[0] + v0[2])) / 2) <= LR.TOL
            if not (same_side and in_line):
                bad.append("row %s: %s's limit sits %s from its name, %s's %s" % (" ".join(refs), r0, v0, r, v))
    # the headers
    for ref, labels, mid in PL.HEADER_LABELS:
        if ref not in bodies:
            continue
        for t in labels:
            if not t:
                continue
            x = nearest(t, bodies[ref])
            if x is None:
                bad.append("%s: its label %r is not printed within %g mm of it" % (ref, t, NEAR))
                continue
            o = LR.owner_ok(x["box"], bodies[ref], [(k, b) for k, b in bodies.items() if k != ref])
            if o:
                bad.append("%s: its label %r could be read as %s's" % (ref, t, o))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(dict(connectors=len(items), rows=report, violations=bad, exempt=notes), open(OUT, "w"), indent=1)
    nrow = sum(1 for a, r in rows if len(r) > 1)
    print("label_check: %d connectors in %d rows (%d of them more than one), %d header(s); %d violation(s) -> %s"
          % (len(items), len(rows), nrow, len(PL.HEADER_LABELS), len(bad), os.path.relpath(OUT, ROOT)))
    for n in notes:
        print("   note: " + n)
    for b in bad:
        print("   LABEL: " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
