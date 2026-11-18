#!/usr/bin/env python3
"""Second-pass copper measurements. Read-only."""
import math
import pcbnew

PCB = "hardware/CostasLink-PYNQ-Z2.kicad_pcb"
board = pcbnew.LoadBoard(PCB)
MM = pcbnew.ToMM

def xy(p):
    return (MM(p.x), MM(p.y))

def hit(layer, x, y):
    pt = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
    hits = []
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetLayer() != layer or not z.IsFilled():
            continue
        if z.HitTestFilledArea(layer, pt):
            hits.append(z.GetNetname())
    return hits

# coupler line midpoints and a sweep across the gap
print("== coupler vs F.Cu GND fill ==")
for ref, xmain, xcoup, y0, y1 in (
    ("CP201", 81.0, 80.46, 36.85, 44.15),
    ("CP101", 49.0, 49.54, 70.95, 78.25),
):
    ym = (y0 + y1) / 2
    for name, x in (("main", xmain), ("coup", xcoup), ("gap", (xmain+xcoup)/2),
                    ("outboard_main", xmain + (0.4 if xmain > xcoup else -0.4)),
                    ("outboard_coup", xcoup + (0.4 if xcoup > xmain else -0.4))):
        print(f"  {ref} {name} ({x:.2f},{ym:.2f}) F.Cu {hit(pcbnew.F_Cu, x, ym)} L2 {hit(pcbnew.In1_Cu, x, ym)}")
    # walk from main line centre outward (away from coupler) until GND fill
    direction = 1 if xmain > xcoup else -1
    found = None
    for i in range(0, 80):
        x = xmain + direction * i * 0.01
        h = hit(pcbnew.F_Cu, x, ym)
        if "GND" in h:
            found = i * 0.01
            break
    print(f"  {ref} GND fill starts {found} mm from main-line centre (half-width 0.145, so gap {None if found is None else found-0.145:.3f} mm)")

# measure actual CPWG gap on a long RF track: J202 centre is (81,32); walk a track of Net-(CP201-OUT)
print("\n== measured ground gap on RF nets ==")
rf = []
for t in board.GetTracks():
    if isinstance(t, pcbnew.PCB_VIA):
        continue
    if t.GetLayer() != pcbnew.F_Cu:
        continue
    w = MM(t.GetWidth())
    if abs(w - 0.29) > 0.02:
        continue
    a, b = xy(t.GetStart()), xy(t.GetEnd())
    L = math.hypot(b[0]-a[0], b[1]-a[1])
    if L < 3:
        continue
    rf.append((t.GetNetname(), a, b, w, L))
print(f"  {len(rf)} F.Cu tracks near 0.29 mm and longer than 3 mm")
gaps = []
for name, a, b, w, L in rf:
    # sample midpoint, measure perpendicular distance to GND fill
    mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
    dx, dy = (b[0]-a[0])/L, (b[1]-a[1])/L
    px, py = -dy, dx
    for sign in (1, -1):
        found = None
        for i in range(0, 100):
            x = mx + sign * px * i * 0.01
            y = my + sign * py * i * 0.01
            if "GND" in hit(pcbnew.F_Cu, x, y):
                found = i * 0.01
                break
        gap = None if found is None else found - w/2
        gaps.append((name, round(L,1), round(gap,3) if gap is not None else None, round(mx,1), round(my,1)))
# summarize
from collections import Counter
c = Counter(g[2] for g in gaps)
print("  gap histogram (mm):", dict(sorted((k,v) for k,v in c.items() if k is not None)))
missing = [g for g in gaps if g[2] is None or g[2] > 0.6 or g[2] < 0.1]
print("  odd gaps:", missing[:20], "count", len(missing))

# L2 under those midpoints
print("\n== L2 under RF track midpoints ==")
miss = 0
for name, a, b, w, L in rf:
    mx, my = (a[0]+b[0])/2, (a[1]+b[1])/2
    h = hit(pcbnew.In1_Cu, mx, my)
    if "GND" not in h:
        miss += 1
        print("  NO L2 GND", name, round(mx,2), round(my,2), h)
print("  missing", miss, "of", len(rf))

# 5V pours: sample along a line from USB area. First find Q301, F301, U104
print("\n== power parts ==")
for fp in board.GetFootprints():
    if fp.GetReference() in ("Q301","Q302","F301","F302","FB301","J301","U104","U201","U103","U117","U202","U301","U302","U303","U304","U305"):
        print(f"  {fp.GetReference()} {fp.GetFPID().GetLibItemName()} at {tuple(round(v,2) for v in xy(fp.GetPosition()))} layer {board.GetLayerName(fp.GetLayer())}")

print("\n== +5V zone hit samples ==")
# board is x 25-145, y 25-125. USB-C is on the right edge per the plan.
for fp in board.GetFootprints():
    if fp.GetReference() == "J301":
        jx, jy = xy(fp.GetPosition())
        print("  J301", jx, jy)
        for dx in range(-30, 2, 2):
            x, y = jx + dx, jy
            print(f"    ({x:.0f},{y:.0f}) L3 {hit(pcbnew.In2_Cu, x, y)} L1 {hit(pcbnew.F_Cu, x, y)}")

# netclass clearances
print("\n== netclasses ==")
nc = board.GetNetClasses()
# KiCad 10 API
try:
    for name in nc.GetClassNames():
        c = nc.Find(name) if hasattr(nc, "Find") else None
        print(" ", name, c)
except Exception as e:
    print("  netclass api", type(e), e)
    print("  dir", [m for m in dir(nc) if not m.startswith("_")][:40])

print("DONE")
