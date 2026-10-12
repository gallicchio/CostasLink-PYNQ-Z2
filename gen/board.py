#!/usr/bin/env python3
"""Make hardware/CostasLink-PYNQ-Z2.kicad_pcb from the netlist, the placement plan
(build/placement.json, made by gen/placement.py), the planned copper (gen/routes.py) and the
silkscreen (gen/silk.py).

    python3 gen/board.py              place, lay the RF lines, route, pour, silk, save
    python3 gen/board.py --place      placement only (no copper): for looking at the floorplan
    python3 gen/board.py --place --with-silk   and the silkscreen on it (no vias yet): do the labels fit?
    python3 gen/board.py --planned    the planned copper and the pours, no router
    python3 gen/board.py --silk       the silkscreen again on the last build's copper (build/pre_silk.kicad_pcb,
                                      saved by every full build just before its silk stage): for iterating labels

Runs inside KiCad's own Python (it relaunches itself there through tools/kienv.py), so pcbnew
does every rotation, flip and pad transform, and the placement plan's own model of them is
checked against pcbnew's result (the socket's pins against the PYNQ-Z2's header, the RF pads
against their lines) before any copper is laid.

Board coordinates are millimetres from the board's top-left corner, x right, y down;
board_info.ORIGIN puts that corner on KiCad's page (tools/pcb_check.py subtracts it again).
After GPiBridge's gen/board.py.
"""
import json, math, os, sys, time, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

if "--inside" not in sys.argv:
    import subprocess, kienv
    # streamed, not captured: a routing run takes long and its progress is worth watching
    p = subprocess.Popen(kienv.python() + [os.path.abspath(__file__), "--inside"] + sys.argv[1:],
                         cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1,
                         env=dict(os.environ, PYTHONHASHSEED="0", PYTHONUNBUFFERED="1"))
    for line in p.stdout:
        if "Font '" not in line:
            sys.stdout.write(line); sys.stdout.flush()
    sys.exit(p.wait())

import pcbnew
from sexp import parse, kids, kid, val
import board_info as BI
import placement as PL

HW = BI.HW
PCB = BI.PCB
NETLIST = BI.NETLIST
LIBDIR = os.path.join(HW, "lib", BI.LIB + ".pretty")
ORIGIN = BI.ORIGIN
PLAN = os.path.join(ROOT, "build", "placement.json")
PRE_SILK = os.path.join(ROOT, "build", "pre_silk.kicad_pcb")


def mm(v):
    return pcbnew.FromMM(float(v))


def P(x, y):
    """Board coordinates (mm from the top-left corner) to KiCad's."""
    return pcbnew.VECTOR2I(mm(ORIGIN[0] + x), mm(ORIGIN[1] + y))


def B(v):
    """KiCad's coordinates back to board millimetres."""
    return (pcbnew.ToMM(v.x) - ORIGIN[0], pcbnew.ToMM(v.y) - ORIGIN[1])


# ---------------------------------------------------------------------------
def read_netlist(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    comps = {}
    for c in kids(kid(doc, "components"), "comp"):
        ref = val(kid(c, "ref"))
        fields = {}
        fl = kid(c, "fields")
        for f in kids(fl, "field") if fl else []:
            if len(f) > 2:
                fields[val(kid(f, "name"))] = val(f, 2)
        props = {}
        for p in kids(c, "property"):
            nm = kid(p, "name")
            if nm:
                props[val(nm)] = val(kid(p, "value")) if kid(p, "value") else ""
        comps[ref] = dict(value=val(kid(c, "value")), footprint=val(kid(c, "footprint")), fields=fields, dnp="dnp" in props)
    nets = {}
    for n in kids(kid(doc, "nets"), "net"):
        nets[val(kid(n, "name"))] = [(val(kid(x, "ref")), val(kid(x, "pin"))) for x in kids(n, "node")]
    return comps, nets


# ---------------------------------------------------------------------------
# JLCPCB's JLC04161H-7628, 1.6 mm: F.Cu RF and signals, In1 a solid ground, In2 the supply pours
# and leftover routing, B.Cu signals under a ground fill (CLAUDE_PCB.md section 5; the socket on the back).
STACKUP = [("F.Cu", "copper", 0.035), ("dielectric 1", "prepreg", 0.2104),
           ("In1.Cu", "copper", 0.0152), ("dielectric 2", "core", 1.065),
           ("In2.Cu", "copper", 0.0152), ("dielectric 3", "prepreg", 0.2104),
           ("B.Cu", "copper", 0.035)]


def setup(board):
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(mm(1.6))
    ds.m_MinClearance = mm(0.15)
    ds.m_HoleClearance = mm(0.2)
    ds.m_HoleToHoleMin = mm(0.25)
    ds.m_CopperEdgeClearance = mm(0.3)
    ds.m_TrackMinWidth = mm(0.127)
    ds.m_ViasMinSize = mm(0.45)
    ds.m_MinThroughDrill = mm(0.25)
    ds.m_SolderMaskMinWidth = mm(0.0)
    ds.m_SolderMaskExpansion = mm(0.0)
    for name in ("In1.Cu", "In2.Cu"):
        board.SetLayerType(board.GetLayerID(name), pcbnew.LT_SIGNAL)
    # the drill/place origin at the board's bottom-left corner: gerbers, drill and placement files
    # all measure from it, x right and y up
    ds.SetAuxOrigin(P(0, PL.BOARD["h"]))
    ds.SetGridOrigin(P(0, PL.BOARD["h"]))


def outline(board):
    w, h, r = PL.BOARD["w"], PL.BOARD["h"], PL.BOARD["r"]
    segs = [((r, 0), (w - r, 0)), ((w, r), (w, h - r)), ((w - r, h), (r, h)), ((0, h - r), (0, r))]
    for a, b in segs:
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(P(*a)); s.SetEnd(P(*b))
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1))
        board.Add(s)
    for cx, cy, a0 in ((r, r, 180), (w - r, r, 270), (w - r, h - r, 0), (r, h - r, 90)):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_ARC)
        s.SetCenter(P(cx, cy))
        s.SetStart(P(cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))))
        s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T), True)
        s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1))
        board.Add(s)


def marks(board):
    """The board's own marks (gen/placement.FIDUCIALS, LAYER_MARK; CLAUDE_PCB.md section 5): each
    fiducial a filled copper disc in a larger mask opening, with a rule area round it that keeps the
    ground pour off; each copper layer's number in copper at one spot.  Netless graphics, not
    footprints: no symbol, no parity warning, no BOM or CPL row."""
    def disc(layer, x, y, r):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_CIRCLE)
        s.SetCenter(P(x, y)); s.SetEnd(P(x + r, y))
        s.SetFilled(True); s.SetWidth(0)
        s.SetLayer(layer)
        board.Add(s)
    for x, y in PL.FIDUCIALS:
        disc(pcbnew.F_Cu, x, y, PL.FID_COPPER)
        disc(pcbnew.F_Mask, x, y, PL.FID_MASK)
        z = pcbnew.ZONE(board)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowZoneFills(True); z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False); z.SetDoNotAllowFootprints(False)
        z.SetLayer(pcbnew.F_Cu)
        z.SetZoneName("fiducial")
        ol = z.Outline()
        ol.NewOutline()
        r = PL.FID_CLEAR
        for k in range(16):
            a = 2 * math.pi * k / 16
            v = P(x + r * math.cos(a), y + r * math.sin(a))
            ol.Append(v.x, v.y)
        board.Add(z)
    x, y = PL.LAYER_MARK
    for n, layer in enumerate((pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu), 1):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(str(n))
        t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(mm(1.2), mm(1.2))); t.SetTextThickness(mm(0.2))
        t.SetPosition(P(x, y))
        t.SetMirrored(layer == pcbnew.B_Cu)        # read from the back
        board.Add(t)


def load_fp(fpid):
    lib, name = fpid.split(":", 1)
    fp = pcbnew.FootprintLoad(LIBDIR, name)
    if fp is None:
        raise SystemExit("footprint %s not found in %s" % (fpid, LIBDIR))
    return fp


SEEDS = set()


def seed(what):
    """Restart KiCad's UUID generator from a seed named for what comes next, so each part's UUIDs
    depend on that part alone and a rebuild of an unchanged board writes the same file."""
    n = zlib.crc32(("costaslink:" + what).encode()) or 1
    assert n not in SEEDS, "two seeds collide: %s" % what
    SEEDS.add(n)
    pcbnew.KIID.SeedGenerator(n)


def place_parts(board, comps, nets, plan):
    netinfo = {}
    for name in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni
    pin_net = {}
    for name, nodes in nets.items():
        for ref, pin in nodes:
            pin_net[(ref, pin)] = name
    fps = {}
    missing = []
    for ref, c in sorted(comps.items()):
        if not c["footprint"] or c["footprint"].endswith(":"):
            continue                         # PWR_FLAGs
        seed(ref)
        fp = load_fp(c["footprint"])
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        for k, v in c["fields"].items():
            if k in ("LCSC", "MPN"):
                fp.SetField(k, v)
                f = fp.GetField(k) if hasattr(fp, "GetField") else fp.GetFieldByName(k)
                f.SetVisible(False)
                f.SetLayer(pcbnew.F_Fab)
        if c["dnp"]:
            fp.SetDNP(True)
            fp.SetExcludedFromPosFiles(True)
            fp.SetExcludedFromBOM(True)
        board.Add(fp)
        if ref not in plan:
            missing.append(ref)
            x, y, rot, side = 100.0 + 3 * (len(missing) % 6), 3.0 * (len(missing) // 6) + 20, 0, "F"
        else:
            x, y, rot, side = plan[ref]
        fp.SetPosition(P(x, y))
        if side == "B":
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        fp.SetOrientationDegrees(rot)
        for pad in fp.Pads():
            n = pin_net.get((ref, pad.GetNumber()))
            if n:
                pad.SetNet(netinfo[n])
        fps[ref] = fp
    return fps, netinfo, missing


def verify(fps):
    """pcbnew's pads where the plan says: the socket on the PYNQ's header, the RF pads on the
    chain lines.  A disagreement here means the plan's model of a rotation or flip is wrong."""
    probs = []

    def pad(ref, num):
        for p in fps[ref].Pads():
            if p.GetNumber() == num:
                return B(p.GetPosition())
        raise KeyError((ref, num))
    for n in (1, 2, 3, 39, 40):
        x, y = pad("J302", str(n))
        wx, wy = PL.hdr_pin(n)
        if abs(x - wx) > 0.05 or abs(y - wy) > 0.05:
            probs.append("socket pin %d at (%.2f, %.2f), the PYNQ-Z2's header pin is at (%.2f, %.2f)" % (n, x, y, wx, wy))
    for ref, num, xw in (("U101", "3", PL.RX_X), ("U102", "14", PL.RX_X), ("U103", "3", PL.RX_X), ("CP101", "1", PL.RX_X),
                         ("T101", "1", PL.RX_X), ("U202", "3", PL.TX_X), ("CP201", "2", PL.TX_X), ("J202", "1", PL.TX_X)):
        x, y = pad(ref, num)
        if abs(x - xw) > 0.05:
            probs.append("%s.%s at x %.2f, its line is at %.2f" % (ref, num, x, xw))
    return probs


def copper(board, args):
    """The planned copper (RF lines, pairs, paddles, fan-outs), the pours, then the router
    (gen/routes.py); returns the Router."""
    import routing as RT
    import routes as RS
    R = RT.Router(board, P, B, PL.BOARD["w"], PL.BOARD["h"])
    R.load_pads()
    pads = RS.Pads(board, B)
    R.pads = pads
    RS.plan_and_route(R, pads, planned_only="--planned" in args)
    return R


def pours(board, R):
    import routes as RS
    RS.ground_fills(R)
    board.BuildConnectivity()
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    n = sum(1 for z in board.Zones() if z.HasFilledPolysForLayer(z.GetFirstLayer()) and
            z.GetFilledPolysList(z.GetFirstLayer()).OutlineCount())
    print("pours: %d zones, %d filled" % (len(list(board.Zones())), n))


def report(R, path):
    left = {}
    for n in R.by_net:
        if n.startswith("<"):
            continue
        k = R.unrouted(n)
        if k:
            left[n] = k
    out = dict(tracks=R.n_tracks, vias=R.n_vias, unrouted=left, failed=[list(f) for f in R.failed])
    json.dump(out, open(path, "w"), indent=1)
    return left


def label_check():
    """tools/label_check.py on the board just written: the connectors' labels, by rows (Response 15)"""
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "label_check.py")], cwd=ROOT, text=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    sys.stdout.write(r.stdout)


RESCUED = os.path.join(ROOT, "build", "ground_rescue.done")      # refill_by_project's passes: the rescue's is done


def refill_by_project():
    """Refill the pours with the project's rules loaded: the board is built on an empty board that
    has none, so the RF and LO lines' CPWG gap (gen/project.py's zone-clearance rule on their net
    classes) holds only in a fill made after the project file names their nets.  In a process of
    its own: in this one KiCad keeps the empty board's default project in memory, fills by it, and
    saves it over the project file (build 18's first try: Default clearance 0.2, no net classes).
    Returns the board as saved."""
    import subprocess, kienv
    import project
    if os.path.exists(RESCUED):
        os.remove(RESCUED)
    for _ in range(6):
        r = subprocess.run(kienv.python() + [os.path.abspath(__file__), "--inside", "--refill"], cwd=ROOT)
        if r.returncode != 3:
            break
    if os.path.exists(RESCUED):
        os.remove(RESCUED)
    if r.returncode:
        raise SystemExit("board: the refill failed")
    project.write(HW)                         # whatever KiCad wrote over it
    return pcbnew.LoadBoard(PCB)


def refill_only():
    board = pcbnew.LoadBoard(PCB)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    import tidy                              # a stub that ended in the first fill can dangle in this one
    j, r = tidy.tidy(board)
    if j or r:
        print("refill: tidy joined %d, removed %d; filled again" % (j, r))
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(PCB)
    if not os.path.exists(RESCUED):          # the first pass: a ground pad the fill left on an island gets a via
        open(RESCUED, "w").close()           # of its own; the dangling check follows in a fresh process (one
        if ground_rescue(board):             # connectivity pass a process: KiCad's SWIG loses types on a second)
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
            board.Save(PCB)
        return 3
    n = drop_dangling_by_drc(board)          # then whatever KiCad's own DRC still calls dangling: one pass a
    if n:                                    # process (KiCad's SWIG loses the connectivity's type on a second)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        board.Save(PCB)
        return 3                             # look again, in a fresh process
    print("refill: the pours filled by %s's rules" % os.path.basename(BI.NAME + ".kicad_pro"))
    return 0


def ground_rescue(board, island=60, reach=3.0, clear=0.2):
    """A ground pad on an island of the top pour (Prompt 28: adding the detectors moved the router's
    power tracks beside U305, R125 and C317, and their pads' pour lost every via): a via of its own beside
    it, joined by a short top track, where the via and the track keep `clear` from every other net's
    copper.  An island is a pad joined to fewer than `island` items (the board's ground is ~1700).
    Returns the number of vias added."""
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    gnd = board.GetNetcodeFromNetname("GND")
    ref_via = next((t for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetCode() == gnd), None)
    if ref_via is None:
        return 0
    vw, vd = ref_via.GetWidth(pcbnew.F_Cu), ref_via.GetDrillValue()
    tw = pcbnew.FromMM(0.25)
    cl = pcbnew.FromMM(clear)
    copper_layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
    others = []                                # (layer, shape) of every other net's pad, track and via
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != gnd:
                for L in copper_layers:
                    if p.IsOnLayer(L):
                        others.append((L, p.GetEffectiveShape(L)))
    for t in board.GetTracks():
        if t.GetNetCode() == gnd:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            for L in copper_layers:
                others.append((L, t.GetEffectiveShape(L)))
        else:
            others.append((t.GetLayer(), t.GetEffectiveShape(t.GetLayer())))
    edge = board.GetBoardEdgesBoundingBox()
    added = 0
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetCode() != gnd or not p.IsOnLayer(pcbnew.F_Cu) or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if len(conn.GetConnectedItems(p)) >= island:
                continue
            c = p.GetPosition()
            done = False
            for r in [0.8 + 0.15 * k for k in range(int((reach - 0.8) / 0.15) + 1)]:
                for a in range(0, 360, 15):
                    v = pcbnew.VECTOR2I(c.x + pcbnew.FromMM(r * math.cos(math.radians(a))), c.y + pcbnew.FromMM(r * math.sin(math.radians(a))))
                    if not edge.Contains(v) or min(v.x - edge.GetX(), edge.GetRight() - v.x, v.y - edge.GetY(), edge.GetBottom() - v.y) < pcbnew.FromMM(1.0):
                        continue
                    via = pcbnew.SHAPE_CIRCLE(v, vw // 2)
                    seg = pcbnew.SHAPE_SEGMENT(c, v, tw)
                    if any(sh.Collide(via, cl) for L, sh in others):
                        continue
                    if any(L == pcbnew.F_Cu and sh.Collide(seg, cl) for L, sh in others):
                        continue
                    nv = pcbnew.PCB_VIA(board)
                    nv.SetPosition(v); nv.SetWidth(vw); nv.SetDrill(vd); nv.SetNetCode(gnd)
                    nv.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    board.Add(nv)
                    nt = pcbnew.PCB_TRACK(board)
                    nt.SetStart(c); nt.SetEnd(v); nt.SetWidth(tw); nt.SetLayer(pcbnew.F_Cu); nt.SetNetCode(gnd)
                    board.Add(nt)
                    print("refill: ground rescue: a via for %s.%s at %.1f mm (%.2f, %.2f)"
                          % (fp.GetReference(), p.GetNumber(), r, pcbnew.ToMM(v.x) - BI.ORIGIN[0], pcbnew.ToMM(v.y) - BI.ORIGIN[1]))
                    added += 1
                    done = True
                    break
                if done:
                    break
            if not done:
                print("refill: ground rescue: no room for a via beside %s.%s" % (fp.GetReference(), p.GetNumber()))
    return added


def drop_dangling_by_drc(board):
    """A track KiCad's DRC calls dangling that the connectivity does not (build 18: a fan-out stub
    whose via did not fit ended on the middle of the router's own track of the net, which joins it
    for the connectivity and not for the DRC): ask kicad-cli, and remove each such track whose
    removal leaves the board's unconnected count where it was.  Returns the number removed."""
    import subprocess, tempfile, kienv
    out = os.path.join(tempfile.mkdtemp(prefix="costaslink_drc_"), "drc.json")
    subprocess.run(kienv.cli() + ["pcb", "drc", "--format", "json", "--severity-all", "--units", "mm", "-o", out, PCB],
                   capture_output=True, text=True)
    if not os.path.exists(out):
        return 0
    dang = [v for v in json.load(open(out)).get("violations", []) if v.get("type") == "track_dangling"]
    board.BuildConnectivity()
    before = board.GetConnectivity().GetUnconnectedCount(False)
    removed = 0
    for v in dang:
        for it in v["items"]:
            x, y = it["pos"]["x"], it["pos"]["y"]
            for t in list(board.GetTracks()):
                if t.Type() != pcbnew.PCB_TRACE_T:
                    continue
                ends = [(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)) for p in (t.GetStart(), t.GetEnd())]
                if not any(abs(ex - x) < 0.005 and abs(ey - y) < 0.005 for ex, ey in ends) or \
                        t.GetNetname() not in it["description"] or pcbnew.ToMM(t.GetLength()) > 3.0:
                    continue
                length, net = pcbnew.ToMM(t.GetLength()), t.GetNetname()
                spare = t.Duplicate()            # a removed item is never put back itself (KiCad freed one twice)
                board.Remove(t)
                board.BuildConnectivity()
                if board.GetConnectivity().GetUnconnectedCount(False) > before:
                    board.Add(spare)             # it was the only way: keep it
                    board.BuildConnectivity()
                    continue
                print("refill: removed a %.2f mm %s track the DRC called dangling at (%.2f, %.2f)"
                      % (length, net, x - BI.ORIGIN[0], y - BI.ORIGIN[1]))
                removed += 1
                break
    return removed


LO_SKEW_MAX = 0.5                      # mm between the legs of an LO pair (CLAUDE_PCB.md section 5)


def lo_skew(board):
    """Each LO leg's copper length, synthesizer to mixer through its two DC blocks (its nets'
    tracks, gen/routes.write_classes), and the gate: the legs of a pair within LO_SKEW_MAX.  KiCad's
    skew rule cannot add a leg's three nets up; build 17's pairs were 10 mm against 44-46 mm and
    nothing failed (the design review).  Returns {leg: mm}."""
    import routes as RS
    legs = json.load(open(RS.CLASSES_JSON))["lo_legs"]
    length = {}
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_TRACE_T:
            length[t.GetNetname()] = length.get(t.GetNetname(), 0.0) + pcbnew.ToMM(t.GetLength())
    out = {leg: round(sum(length.get(n, 0.0) for n in nets), 3) for leg, nets in legs.items()}
    bad = []
    for pair in ("RX LO", "TX LO"):
        p, n = out.get(pair + " +"), out.get(pair + " -")
        print("lo_skew: %s legs %.2f / %.2f mm (%.2f mm apart)" % (pair, p, n, abs(p - n)))
        if abs(p - n) > LO_SKEW_MAX:
            bad.append("%s: %.2f against %.2f mm" % (pair, p, n))
    if bad:
        raise SystemExit("board: LO pair skew over %.1f mm: %s" % (LO_SKEW_MAX, "; ".join(bad)))
    return out


def silk_only(t0):
    """The silk stage alone, on the copper the last full build saved before its silk stage: the same
    seed, so the result is the file a full build would write (the copper is deterministic)."""
    import shutil, silk
    if not os.path.exists(PRE_SILK):
        raise SystemExit("board --silk: no %s; run a full build first" % os.path.relpath(PRE_SILK, ROOT))
    shutil.copy(PRE_SILK, PCB)
    board = pcbnew.LoadBoard(PCB)
    fps = {fp.GetReference(): fp for fp in board.GetFootprints()}
    seed("silk")
    silk.apply(board, fps, P, B)
    board.Save(PCB)
    label_check()
    import project
    project.write(HW)
    lo_skew(refill_by_project())
    print("board --silk: the silkscreen redone on %s -> %s (%.0f s)" % (os.path.relpath(PRE_SILK, ROOT), os.path.relpath(PCB, ROOT),
                                                                    time.time() - t0))
    return 0


def main():
    args = [a for a in sys.argv[1:] if a != "--inside"]
    t0 = time.time()
    if "--silk" in args:
        return silk_only(t0)
    if "--refill" in args:
        return refill_only()
    pcbnew.KIID.SeedGenerator(488)
    comps, nets = read_netlist(NETLIST)
    plan = json.load(open(PLAN))["place"]
    board = pcbnew.CreateEmptyBoard()
    setup(board)
    outline(board)
    marks(board)
    fps, netinfo, missing = place_parts(board, comps, nets, plan)
    probs = verify(fps)
    for p in probs:
        print("   PLACEMENT: " + p)
    if probs:
        raise SystemExit("board: the placement plan and pcbnew disagree; fix gen/placement.py's model")
    left = {}
    if "--place" not in args:
        seed("copper")
        R = copper(board, args)
        seed("pours")
        pours(board, R)
        import tidy                          # KiCad's connectivity decides: near misses joined, dead stubs removed
        # (not on --planned: before the router every fan-out via and stub dangles by design, and tidying
        # them away made the planned copper look empty round the chips, Response 15)
        j, r = tidy.tidy(board) if "--planned" not in args else (0, 0)
        print("tidy: %d near misses joined, %d dead stubs and vias removed" % (j, r))
        if j or r:
            pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        left = report(R, os.path.join(ROOT, "build", "route_report.json"))
        for net, why in R.failed[:40]:
            print("   UNROUTED %s: %s" % (net, why))
        board.Save(PCB)                      # the copper is safe before the silkscreen stage
        board.Save(PRE_SILK)                 # and kept for gen/board.py --silk
        import silk
        seed("silk")
        silk.apply(board, fps, P, B)
        print("copper: %d tracks, %d vias; %d nets with unjoined pieces%s"
              % (R.n_tracks, R.n_vias, len(left), (": " + ", ".join(sorted(left))[:400]) if left else ""))
    elif "--with-silk" in args:
        import silk                          # placement and labels only: a quick look at where labels can go
        seed("silk")
        silk.apply(board, fps, P, B)
    board.Save(PCB)
    if "--place" not in args or "--with-silk" in args:
        label_check()
    import project
    project.write(HW)
    if "--place" not in args:
        lo_skew(refill_by_project())
    print("board: %d footprints placed%s -> %s (%.0f s)" % (len(fps), ("; NOT IN THE PLAN: " + " ".join(missing)) if missing else "",
                                                           os.path.relpath(PCB, ROOT), time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
