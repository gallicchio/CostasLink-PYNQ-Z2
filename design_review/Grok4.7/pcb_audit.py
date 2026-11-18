#!/usr/bin/env python3
"""Read-only copper audit of the shared board. Writes nothing but stdout."""
import os, sys, math
os.environ.setdefault("KICAD_RUN_FROM_BUILD_DIR", "1")
import pcbnew

PCB = "hardware/CostasLink-PYNQ-Z2.kicad_pcb"
board = pcbnew.LoadBoard(PCB)
MM = pcbnew.ToMM

def xy(p):
    return (MM(p.x), MM(p.y))

print("board", board.GetFileName())
print("footprints", len(list(board.GetFootprints())))
print("tracks", len(list(board.GetTracks())))
print("zones", board.GetAreaCount())

# layer names
for i in range(board.GetCopperLayerCount()):
    print(" layer", i, board.GetLayerName(i))

# --- RF trace widths ---
rf_nets = []
for t in board.GetTracks():
    if not isinstance(t, pcbnew.PCB_TRACK) or isinstance(t, pcbnew.PCB_VIA):
        continue
    name = t.GetNetname()
    if name and ("RF" in name or "LO" in name or "ANT" in name or name.startswith("Net-")):
        pass

# collect unique net names that look like RF by walking SMA / coupler / balun pads
want_refs = {"J101", "J202", "J401", "J402", "J403", "T101", "CP101", "CP201",
             "U101", "U102", "U103", "U104", "U115", "U117", "U201", "U202", "U203", "U401"}
nets = {}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    if ref not in want_refs:
        continue
    for p in fp.Pads():
        nets.setdefault(p.GetNetname(), []).append((ref, p.GetNumber(), xy(p.GetPosition())))

print("\n== nets on RF parts ==")
for n, pins in sorted(nets.items(), key=lambda kv: -len(kv[1])):
    if n in ("GND", "+5V_RF", "+3V3_PLL_RX", "+3V3_PLL_TX", "+3V3_ANA", "+3V3_DIG", ""):
        continue
    print(f"  {n}: {pins[:8]}")

# track width histogram per net of interest
interest = [n for n in nets if n not in ("GND", "+5V_RF", "+3V3_PLL_RX", "+3V3_PLL_TX", "+3V3_ANA", "+3V3_DIG", "")]
print("\n== track widths on those nets ==")
for n in interest:
    widths = {}
    layers = {}
    length = 0.0
    for t in board.GetTracks():
        if t.GetNetname() != n:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            layers["via"] = layers.get("via", 0) + 1
            continue
        w = round(MM(t.GetWidth()), 3)
        widths[w] = widths.get(w, 0) + 1
        length += MM(t.GetLength())
        layers[board.GetLayerName(t.GetLayer())] = layers.get(board.GetLayerName(t.GetLayer()), 0) + 1
    if widths or layers.get("via"):
        print(f"  {n}: widths {widths} layers {layers} len {length:.1f} mm")

# --- coupler footprints: pads, graphic copper, nearby zone ---
print("\n== coupler footprints ==")
for fp in board.GetFootprints():
    if fp.GetReference() not in ("CP101", "CP201"):
        continue
    print(fp.GetReference(), "at", xy(fp.GetPosition()), "rot", fp.GetOrientation().AsDegrees(),
          "fp", fp.GetFPID().GetLibItemName())
    for p in fp.Pads():
        print("  pad", p.GetNumber(), "net", p.GetNetname(), "at", xy(p.GetPosition()),
              "size", (MM(p.GetSize().x), MM(p.GetSize().y)))
    for d in fp.GraphicalItems():
        if d.GetLayer() == pcbnew.F_Cu or "Cu" in board.GetLayerName(d.GetLayer()):
            print("  graphic", d.GetClass(), "layer", board.GetLayerName(d.GetLayer()),
                  "width", MM(d.GetWidth()) if hasattr(d, "GetWidth") else "?")
            if hasattr(d, "GetStart") and hasattr(d, "GetEnd"):
                print("    ", xy(d.GetStart()), "->", xy(d.GetEnd()))

# --- L2 zone coverage: sample a grid, count holes ---
print("\n== zone names ==")
for i in range(board.GetAreaCount()):
    z = board.GetArea(i)
    print(f"  {i}: layer {board.GetLayerName(z.GetLayer())} net {z.GetNetname()} "
          f"filled {z.IsFilled()} priority {z.GetAssignedPriority()} "
          f"clearance {MM(z.GetLocalClearance()) if hasattr(z,'GetLocalClearance') else '?'}")

# sample whether a point is inside any filled zone on a layer
def in_zone(layer, x_mm, y_mm):
    pt = pcbnew.VECTOR2I(pcbnew.FromMM(x_mm), pcbnew.FromMM(y_mm))
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetLayer() != layer or not z.IsFilled():
            continue
        if z.HitTestFilledArea(pt):
            return z.GetNetname()
    return None

# board outline bbox from Edge.Cuts
xs, ys = [], []
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts and hasattr(d, "GetStart"):
        xs += [MM(d.GetStart().x), MM(d.GetEnd().x)]
        ys += [MM(d.GetStart().y), MM(d.GetEnd().y)]
print("edge sample", min(xs) if xs else None, max(xs) if xs else None, min(ys) if ys else None, max(ys) if ys else None)

# RF path point samples: coupler pad positions already printed; also sample along a few tracks
print("\n== L2 / L1 coverage samples along RF tracks (every 2 mm) ==")
L2 = pcbnew.In1_Cu if hasattr(pcbnew, "In1_Cu") else None
# find inner layers
print("In1", pcbnew.In1_Cu, "In2", pcbnew.In2_Cu, "F", pcbnew.F_Cu, "B", pcbnew.B_Cu)

holes = []
for n in interest:
    segs = []
    for t in board.GetTracks():
        if t.GetNetname() != n or isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetLayer() != pcbnew.F_Cu:
            continue
        a, b = xy(t.GetStart()), xy(t.GetEnd())
        segs.append((a, b, MM(t.GetWidth())))
    if not segs:
        continue
    # sample
    miss = 0
    tot = 0
    narrow = []
    for a, b, w in segs:
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        steps = max(1, int(L / 1.0))
        for k in range(steps + 1):
            x = a[0] + (b[0]-a[0]) * k / steps
            y = a[1] + (b[1]-a[1]) * k / steps
            tot += 1
            g = in_zone(pcbnew.In1_Cu, x, y)
            if g != "GND":
                miss += 1
                if len(holes) < 12:
                    holes.append((n, round(x,2), round(y,2), g))
            if w < 0.25:
                narrow.append((round(w,3), round(x,2), round(y,2)))
    print(f"  {n}: {tot} samples, L2 not GND at {miss}; narrow segs {len([s for s in segs if s[2]<0.25])}")

print("L2 holes (first):", holes)

# --- 5V path: track widths and zone area ---
print("\n== +5V_IN / +5V_RF copper ==")
for netname in ("+5V_IN", "+5V_RF", "+5V_HDR"):
    tw = {}
    length = 0.0
    vias = 0
    for t in board.GetTracks():
        if t.GetNetname() != netname:
            continue
        if isinstance(t, pcbnew.PCB_VIA):
            vias += 1
            continue
        w = round(MM(t.GetWidth()), 3)
        tw[w] = tw.get(w, 0) + MM(t.GetLength())
        length += MM(t.GetLength())
    print(f"  {netname}: track length {length:.0f} mm by width { {k: round(v,1) for k,v in tw.items()} } vias {vias}")

# zone area estimate by sampling a 1 mm grid over the board
if xs and ys:
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    print(f"outline {x0:.1f},{y0:.1f} to {x1:.1f},{y1:.1f}")
    for layer, lname in ((pcbnew.In1_Cu, "L2"), (pcbnew.In2_Cu, "L3"), (pcbnew.B_Cu, "L4"), (pcbnew.F_Cu, "L1")):
        counts = {}
        n = 0
        step = 2.0
        yy = y0 + 1
        while yy < y1:
            xx = x0 + 1
            while xx < x1:
                n += 1
                g = in_zone(layer, xx, yy)
                counts[g] = counts.get(g, 0) + 1
                xx += step
            yy += step
        print(f"  {lname} 2mm grid n={n}: " + ", ".join(f"{k}:{v}" for k,v in sorted(counts.items(), key=lambda kv: -kv[1])[:8]))

# --- exposed pads via counts ---
print("\n== exposed-pad via counts (pads named 0 / 7 / EP / 17) ==")
for fp in board.GetFootprints():
    ref = fp.GetReference()
    for p in fp.Pads():
        num = p.GetNumber()
        if num in ("0", "7", "17", "33", "EP") or (p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and MM(p.GetSize().x) > 1.2 and MM(p.GetSize().y) > 1.2 and p.GetNetname()=="GND"):
            # count vias within the pad
            c = xy(p.GetPosition())
            sx, sy = MM(p.GetSize().x)/2, MM(p.GetSize().y)/2
            nv = 0
            for t in board.GetTracks():
                if not isinstance(t, pcbnew.PCB_VIA):
                    continue
                vx, vy = xy(t.GetPosition())
                if abs(vx-c[0]) <= sx+0.1 and abs(vy-c[1]) <= sy+0.1 and t.GetNetname()=="GND":
                    nv += 1
            if nv or num in ("0", "17", "33"):
                print(f"  {ref} pad {num} size {MM(p.GetSize().x):.2f}x{MM(p.GetSize().y):.2f} net {p.GetNetname()} vias {nv}")

print("\nDONE")
