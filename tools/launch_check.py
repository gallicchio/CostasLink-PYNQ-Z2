#!/usr/bin/env python3
"""The 5.8 GHz launches as the GERBERS have them (Prompt 32: "make sure that all 5-6 GHz connectors have proper
capacitance and inductance in the gerbers").  Reads the plotted copper layers, not the board file, because the
board file's rules and settings are what the plot interprets, and a rule that never matched left build 36's
SMA antipads at 1.8 mm while the design said 4 mm.

    python3 tools/launch_check.py [gerber directory]        default mfg/release/gerbers

For every 5.8 GHz SMA (gen/routes.LAUNCH_SMAS): no pad flash at the centre pin on In1 or In2 (the rings were
removed), and no plane copper within LAUNCH_R - 0.05 mm of the pin centre on In1, In2 and B.Cu.  For every
relieved RF pad (gen/routes.RELIEF_PADS): no In1 copper within half the pad plus VOID_MARGIN - 0.05 of its
centre.  Exit 1 with the list of what fails; writes hardware/checks/launches.json.
"""
import os, re, sys, math, json, glob
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
sys.path.insert(0, HERE)
import board_info as BI
from sexp import parse, kids, kid, val, num


def gerber(path):
    """(flashes [(x, y, aperture)], regions [[(x, y), ...]]) in mm."""
    txt = open(path, encoding="utf-8", errors="replace").read()
    fs = re.search(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", txt)
    sc = 10 ** int(fs.group(2))
    ap = {}
    for m in re.finditer(r"%ADD(\d+)([A-Z]),([\d.X]+)\*%", txt):
        ap[m.group(1)] = (m.group(2), [float(v) for v in m.group(3).split("X")])
    cur, flashes, regions, inreg, poly, x, y = None, [], [], False, [], 0.0, 0.0
    for line in txt.splitlines():
        if line.startswith("D") and line.endswith("*") and line[1:-1].isdigit():
            cur = line[1:-1]
            continue
        if line == "G36*":
            inreg, poly = True, []
            continue
        if line == "G37*":
            inreg = False
            regions.append(poly)
            continue
        m = re.match(r"(?:X(-?\d+))?(?:Y(-?\d+))?D0([123])\*", line)
        if not m:
            continue
        if m.group(1):
            x = int(m.group(1)) / sc
        if m.group(2):
            y = int(m.group(2)) / sc
        if inreg and m.group(3) in "12":
            poly.append((x, y))
        elif m.group(3) == "3":
            flashes.append((x, y, ap.get(cur)))
    return flashes, regions


def inside(px, py, poly):
    ok, n = False, len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < x1 + (py - y1) * (x2 - x1) / (y2 - y1):
            ok = not ok
    return ok


def nearest_copper(px, py, regions, rmax=4.0):
    """The smallest radius from (px, py) at which a sampled circle meets a filled region, or None."""
    polys = [p for p in regions if len(p) > 2]
    r = 0.3
    while r <= rmax:
        for a in range(0, 360, 10):
            qx, qy = px + r * math.cos(math.radians(a)), py + r * math.sin(math.radians(a))
            if any(inside(qx, qy, p) for p in polys):
                return r
        r += 0.05
    return None


def pad_centres(pcb):
    """(ref, pad) -> (x, y, w, h) in the gerber frame (mm from the board's bottom-left corner, y up), from the
    board file's footprints (the page origin BI.ORIGIN, the board BI.BOARD_H high)."""
    out = {}
    doc = parse(open(pcb, encoding="utf-8").read())[0]
    H = float(BI.BOARD_H) if hasattr(BI, "BOARD_H") else 100.0
    for fp in kids(doc, "footprint"):
        ref = next((val(p, 2) for p in kids(fp, "property") if val(p, 1) == "Reference"), None)
        at = kid(fp, "at")
        fx, fy = num(at, 1), num(at, 2)
        rot = num(at, 3) if len(at) > 3 else 0.0
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        for pad in kids(fp, "pad"):
            number = str(val(pad))
            pat = kid(pad, "at")
            dx, dy = num(pat, 1), num(pat, 2)
            sz = kid(pad, "size")
            w, h = num(sz, 1), num(sz, 2)
            # KiCad: y down on the page, a positive angle turns counter-clockwise on the screen
            x = fx + dx * c + dy * s
            y = fy - dx * s + dy * c
            key = (ref, number)
            if key not in out:                     # a connector's several ground pads share a number: keep the first
                out[key] = (x - BI.ORIGIN[0], (BI.ORIGIN[1] + H) - y, w, h)
    return out


def main(argv):
    import rf_launch as RS
    gdir = argv[1] if len(argv) > 1 else os.path.join(ROOT, "mfg", "release", "gerbers")
    files = {os.path.basename(f): f for f in glob.glob(os.path.join(gdir, "*.gbr"))}
    layer = {k: next((v for n, v in files.items() if k in n), None) for k in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu")}
    if not all(layer.values()):
        print("launch_check: missing copper gerbers in %s" % gdir)
        return 2
    parsed = {k: gerber(v) for k, v in layer.items()}
    pads = pad_centres(BI.PCB)
    fails, rows = [], []
    for ref in RS.LAUNCH_SMAS:
        if (ref, "1") not in pads:
            continue
        px, py, w, h = pads[(ref, "1")]
        row = dict(ref=ref, x=round(px, 2), y=round(py, 2))
        for k in ("In1_Cu", "In2_Cu"):
            fl = [f for f in parsed[k][0] if math.hypot(f[0] - px, f[1] - py) < 0.3]
            if fl:
                fails.append("%s centre pin: a pad flash on %s (%s): the ring is back" % (ref, k, fl[0][2]))
        for k in ("In1_Cu", "In2_Cu", "B_Cu"):
            r = nearest_copper(px, py, parsed[k][1])
            row[k] = r
            if r is not None and r < RS.LAUNCH_R - 0.05:
                fails.append("%s centre pin: %s copper %.2f mm from the pin, the launch wants %.2f" % (ref, k, r, RS.LAUNCH_R))
        # the top pour's clearance from the pad (the study's 0.9 mm lever): the pour is a region, the pad a flash
        r = nearest_copper(px, py, parsed["F_Cu"][1], rmax=3.0)
        row["F_Cu"] = r
        want = RS.LAUNCH_PAD_OD / 2 + RS.LAUNCH_CLEAR - 0.1
        if r is not None and r < want:
            fails.append("%s: the top pour %.2f mm from the pin, the pad's clearance wants %.2f" % (ref, r, want))
        rows.append(row)
    for ref, num in RS.RELIEF_PADS:
        if (ref, num) not in pads:
            continue
        px, py, w, h = pads[(ref, num)]
        want = min(w, h) / 2 + RS.VOID_MARGIN - 0.05
        r = nearest_copper(px, py, parsed["In1_Cu"][1], rmax=2.0)
        rows.append(dict(ref="%s.%s" % (ref, num), x=round(px, 2), y=round(py, 2), In1_Cu=r))
        if r is not None and r < want:
            fails.append("%s.%s: In1 copper %.2f mm from the pad's centre, the relief wants %.2f" % (ref, num, r, want))
    # the taper's direction: every line leaves along the footprint's -x (180 deg); with a taper fitted, a line
    # leaving any other way would run off the taper's side
            if not real:
                fails.append("%s: no track leaves its centre pin" % ref)
            for ang, L, w in real:
                if abs(abs(ang) - 180) > 30:
                    fails.append("%s: a %.2f mm track leaves the pin at %.0f deg in the footprint's frame; the taper points along -x (180)" % (ref, L, ang))
    out = os.path.join(BI.CHECKS, "launches.json")
    os.makedirs(BI.CHECKS, exist_ok=True)
    json.dump(dict(gerbers=os.path.relpath(gdir, ROOT), rows=rows, failures=fails), open(out, "w"), indent=1)
    for row in rows:
        print("  %-8s (%6.2f, %6.2f)  %s" % (row["ref"], row["x"], row["y"],
              "  ".join("%s %s" % (k, ("%.2f mm" % v) if v else ">4 mm") for k, v in row.items() if k.endswith("_Cu"))))
    if fails:
        print("launch_check: %d failure(s)" % len(fails))
        for f in fails:
            print("  - " + f)
        return 1
    print("launch_check: %d SMA launches and %d relieved pads as designed -> %s" % (len(RS.LAUNCH_SMAS), len(RS.RELIEF_PADS), os.path.relpath(out, ROOT)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
