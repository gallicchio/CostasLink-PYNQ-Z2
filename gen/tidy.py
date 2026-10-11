"""The last copper pass (Response 14): KiCad's own connectivity, not the router's grid, decides what
touches.  Every track end KiCad calls dangling is either a near miss (copper of the same net within
REACH on the same layer: joined by a short segment to it) or a dead stub (removed when short); a via
KiCad calls dangling is removed.  Builds 9-14 left five to seven of these: the router's cells said
two pieces met where their copper stopped 0.05-0.2 mm apart, or a stub ended just outside a pad's
corner.  Run it after the zones are filled (a stub that ends in a pour is not dangling) and fill
them again after it.
"""
import math
import pcbnew

REACH = 0.45        # mm: how far a dangling end may be joined
STUB = 3.0          # mm: a dangling track shorter than this with nothing in reach is removed


def _id(item):
    # KiCad's own identity: GetTracks() hands back fresh Python wrappers each time, so `is` never matches
    return item.m_Uuid.AsString()


def _mm(p):
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def _seg_near(p, a, b):
    """distance from p to segment ab and the nearest point on it (mm)"""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    q = (ax + t * dx, ay + t * dy)
    return math.hypot(p[0] - q[0], p[1] - q[1]), q


def _touches(board, item, p, layer, net, pads, zones):
    """does same-net copper other than `item` touch the point p (mm) on `layer`?"""
    vp = pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1]))
    for pad in pads.get(net, []):
        if pad.IsOnLayer(layer) and pad.HitTest(vp, pcbnew.FromMM(0.001)):
            return True
    for t in board.GetTracks():
        if t.GetNetCode() != net or _id(t) == _id(item):
            continue
        if t.GetClass() == "PCB_VIA":
            if t.IsOnLayer(layer) and math.hypot(*(a - b for a, b in zip(_mm(t.GetPosition()), p))) <= pcbnew.ToMM(t.GetWidth(layer)) / 2.0 + 0.001:
                return True
        elif t.GetLayer() == layer:
            d, _ = _seg_near(p, _mm(t.GetStart()), _mm(t.GetEnd()))
            if d <= pcbnew.ToMM(t.GetWidth()) / 2.0 + 0.001:
                return True
    for z in zones.get(net, []):
        if z.IsOnLayer(layer) and z.HitTestFilledArea(layer, vp):
            return True
    return False


def _nearest(board, item, p, layer, net, pads):
    """the nearest same-net copper point within REACH on `layer` (mm), or None"""
    best = None
    vp = pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1]))
    for pad in pads.get(net, []):
        if not pad.IsOnLayer(layer):
            continue
        c = _mm(pad.GetPosition())
        d = math.hypot(p[0] - c[0], p[1] - c[1])
        bb = pad.GetBoundingBox()
        half = max(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2.0
        if d - half <= REACH and (best is None or d - half < best[0]):
            best = (d - half, c)                               # join to the pad's centre
    for t in board.GetTracks():
        if t.GetNetCode() != net or _id(t) == _id(item):
            continue
        if t.GetClass() == "PCB_VIA":
            if t.IsOnLayer(layer):
                c = _mm(t.GetPosition())
                d = math.hypot(p[0] - c[0], p[1] - c[1])
                if d <= REACH and (best is None or d < best[0]):
                    best = (d, c)
        elif t.GetLayer() == layer:
            d, q = _seg_near(p, _mm(t.GetStart()), _mm(t.GetEnd()))
            if d <= REACH and (best is None or d < best[0]):
                best = (d, q)
    return None if best is None else best[1]


def snap_to_vias(board, log=print):
    """Join every track end that lies inside a via of its own net, but off its centre, to the centre by
    a short segment.  The planned fan-out vias stand at exact, off-grid places and the router ends its
    tracks on the 0.1 mm grid inside them, up to 0.2 mm off; KiCad does not count such an end on an
    inner layer as joined, so the track and the via were each "dangling", and the pass below removed
    a via that carried ERR (Response 15).  The segment lies inside the via's own pad, so it cannot
    come near anything; moving the track's end instead dragged it at an angle into its neighbours
    (18 clearance errors) and collapsed short tracks to nothing.  Returns how many it added."""
    vias = {}
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            vias.setdefault(t.GetNetCode(), []).append((_mm(t.GetPosition()), pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2.0))
    added = 0
    for t in list(board.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            continue
        for p in (_mm(t.GetStart()), _mm(t.GetEnd())):
            for c, r in vias.get(t.GetNetCode(), []):
                d = math.hypot(p[0] - c[0], p[1] - c[1])
                if 0.005 < d <= r + 0.001:
                    s_ = pcbnew.PCB_TRACK(board)
                    s_.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
                    s_.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c[0]), pcbnew.FromMM(c[1])))
                    # no wider than 0.15 mm: a rail's 0.5 mm segment stood out of the via's 0.45 mm pad
                    s_.SetWidth(min(t.GetWidth(), pcbnew.FromMM(0.15)))
                    s_.SetLayer(t.GetLayer())
                    s_.SetNetCode(t.GetNetCode())
                    board.Add(s_)
                    added += 1
                    break
    if added:
        log("   tidy: %d track ends joined to their vias' centres" % added)
    return added


def join_isolated_pads(board, log=print):
    """Join every SMD pad that no copper of its net reaches (no track end, via or filled zone inside it) to
    the nearest same-net track on its layer, when one passes within REACH of the pad's edge, by a segment
    from the pad's centre (KiCad's connectivity says which pads are isolated).  The router's cells can count a track that runs past a pad as joined to it while
    KiCad, which wants a track's end inside the pad, does not: TX_EN's line passed R227's pad 1 0.05 mm
    clear of it and the DRC said "unconnected" (Response 15).  The dangling-end pass below never sees this:
    the track's own ends are anchored elsewhere.  Returns how many it joined."""
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    tracks_by_net = {}
    for t in board.GetTracks():
        tracks_by_net.setdefault(t.GetNetCode(), []).append(t)
    members = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            members[pad.GetNetCode()] = members.get(pad.GetNetCode(), 0) + 1
    joined = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            net = pad.GetNetCode()
            if net <= 0 or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or members.get(net, 0) < 2:
                continue
            # KiCad's own connectivity decides (a track over a pad counts; the pad's exact shape decides near a
            # corner): isolated means nothing but pads joined to it
            if any(i.GetClass() != "PAD" for i in conn.GetConnectedItems(pad)):
                continue
            layer = pcbnew.F_Cu if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
            c = _mm(pad.GetPosition())
            bb = pad.GetBoundingBox()
            half = min(pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())) / 2.0
            best = None
            for t in tracks_by_net.get(net, []):
                if t.GetClass() == "PCB_VIA" or t.GetLayer() != layer:
                    continue
                d, q = _seg_near(c, _mm(t.GetStart()), _mm(t.GetEnd()))
                if d - half <= REACH and (best is None or d < best[0]):
                    best = (d, q, t)
            if best is None:
                continue
            d, q, t = best
            seg = pcbnew.PCB_TRACK(board)
            seg.SetStart(pad.GetPosition())
            seg.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1])))
            seg.SetWidth(t.GetWidth())
            seg.SetLayer(layer)
            seg.SetNetCode(net)
            board.Add(seg)
            tracks_by_net[net].append(seg)
            joined += 1
            log("   tidy: joined %s pad %s (%s) to its line %.2f mm away" % (fp.GetReference(), pad.GetNumber(), pad.GetNetname(), d))
    return joined


def tidy(board, log=print):
    """Joins first, always: a round that joined anything recomputes KiCad's connectivity before
    removing a thing (a via removed before the tracks that nearly reached it were joined took the
    whole path with it, Response 14's first run).  Then dead stubs, then vias touching nothing."""
    joined = removed = 0
    snap_to_vias(board, log)
    joined += join_isolated_pads(board, log)
    for _ in range(8):
        board.BuildConnectivity()
        conn = board.GetConnectivity()
        pads, zones = {}, {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                pads.setdefault(pad.GetNetCode(), []).append(pad)
        for z in board.Zones():
            zones.setdefault(z.GetNetCode(), []).append(z)
        dangling = [t for t in board.GetTracks() if conn.TestTrackEndpointDangling(t, False)]
        if not dangling:
            break
        tracks = [t for t in dangling if t.GetClass() != "PCB_VIA"]
        vias = [t for t in dangling if t.GetClass() == "PCB_VIA"]
        stubs = []
        joins = 0
        for t in tracks:
            net, layer = t.GetNetCode(), t.GetLayer()
            ends = [_mm(t.GetStart()), _mm(t.GetEnd())]
            free = [e for e in ends if not _touches(board, t, e, layer, net, pads, zones)]
            if not free:
                continue
            w = pcbnew.ToMM(t.GetWidth())
            done = False
            for e in free:
                q = _nearest(board, t, e, layer, net, pads)
                if q is not None and _seg_near(q, ends[0], ends[1])[0] <= w / 2.0 + 0.001:
                    q = None                                   # back along the stub itself: nothing new in reach
                if q is not None and math.hypot(q[0] - e[0], q[1] - e[1]) > 1e-4:
                    s = pcbnew.PCB_TRACK(board)
                    s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(e[0]), pcbnew.FromMM(e[1])))
                    s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q[0]), pcbnew.FromMM(q[1])))
                    s.SetWidth(t.GetWidth())
                    s.SetLayer(layer)
                    s.SetNetCode(net)
                    board.Add(s)
                    joins += 1
                    done = True
                    log("   tidy: joined %s at (%.2f, %.2f) to (%.2f, %.2f)" % (t.GetNetname(), e[0], e[1], q[0], q[1]))
            if not done:
                stubs.append((t, ends, len(free)))
        joined += joins
        if joins:
            continue                                           # recompute before removing anything
        for t, ends, nfree in stubs:
            length = math.hypot(ends[1][0] - ends[0][0], ends[1][1] - ends[0][1])
            if nfree == 1:
                # trim, do not remove: walk in from the free end to the first point where other copper
                # touches the stub (a line may meet it mid-length, Response 14's LOOP_HOLD); remove it
                # only when nothing does short of its anchored end
                net, layer = t.GetNetCode(), t.GetLayer()
                fe = ends[0] if not _touches(board, t, ends[0], layer, net, pads, zones) else ends[1]
                ae = ends[1] if fe is ends[0] else ends[0]
                steps = max(2, int(length / 0.025))
                cut = None
                for k in range(1, steps):
                    f = k / float(steps)
                    pt = (fe[0] + (ae[0] - fe[0]) * f, fe[1] + (ae[1] - fe[1]) * f)
                    if _touches(board, t, pt, layer, net, pads, zones):
                        cut = pt
                        break
                if cut is not None and math.hypot(cut[0] - ae[0], cut[1] - ae[1]) > 0.01:
                    vp = pcbnew.VECTOR2I(pcbnew.FromMM(cut[0]), pcbnew.FromMM(cut[1]))
                    if fe == _mm(t.GetStart()):
                        t.SetStart(vp)
                    else:
                        t.SetEnd(vp)
                    log("   tidy: trimmed a stub of %s back to (%.2f, %.2f)" % (t.GetNetname(), cut[0], cut[1]))
                    removed += 1
                    continue
            if length < STUB or nfree == 2:
                log("   tidy: removed a %.2f mm dead stub of %s" % (length, t.GetNetname()))
                board.Remove(t)
                removed += 1
        if stubs:
            continue                                           # vias only once no stub is left to settle
        for v in vias:
            log("   tidy: removed a dangling via of %s at (%.2f, %.2f)" % ((v.GetNetname(),) + _mm(v.GetPosition())))
            board.Remove(v)
            removed += 1
    return joined, removed
