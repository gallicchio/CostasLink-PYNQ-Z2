"""Copper on the board, inside KiCad's Python: fixed copper (zones, tracks
and vias given as coordinates), ground fan-out vias, and the grid router for
everything else.  Called by gen/board.py through gen/routes.py.

Every pad, track, via and zone is an *item*: its cells on the routing grid
and the obstacle it stamps for other nets.  A net is complete when its items
form one group, where items join if they share a cell on a common layer, and
every via or through-hole pad of GND joins the others through In1, the
unbroken ground plane; a via of a supply net inside its In2 pour joins the pour.
Routing a net joins its groups one at a time, the smallest first, with A* from
that group to all the others; a piece that cannot be joined is set aside and the
rest go on.  What the router laid can be taken back out (rip-up: rip(), restore())
and the nets that walled a search in can be named (walls()), for gen/routes.repair().

Board millimetres throughout (board.P / board.B convert).  The routing grid's
layers: 0 = F.Cu, 1 = In2.Cu, 2 = B.Cu; In1.Cu is the ground plane.
(GPiBridge's routing.py, with OWLternating Current's rip-up and widening.)
"""
import math
from array import array
import pcbnew
import router as R

LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
LIDX = {pcbnew.F_Cu: 0, pcbnew.In2_Cu: 1, pcbnew.B_Cu: 2}
VIA = (0.45, 0.25)                 # pad, drill: JLCPCB's standard 4-layer via
TAB_MIN = 0.75                     # a chip's ground pad this wide or more is a paddle or tab (vias inside it)
# Planes: a via or through-hole pad of the net, inside the polygon (board
# mm; None = everywhere), is joined through that plane.  GND is In1.Cu, solid;
# routes.py adds the In2 supply pours (their real outlines, inset by a margin).
PLANES = {"GND": None}
PLANE_MARGIN = 0.6                 # a via this far inside a pour's outline is on it


class Item:
    """cells: {layer: grid cells its copper covers}, for joining items;
    inner: where a routed track may end on it (a pad's cells far enough
    inside that a track ending there crosses the pad's edge at full width;
    any cell of a track, via or zone); obj, seg: a track's or via's pcbnew
    object and (layer, start, end, width) / ("via", x, y, drill)."""
    __slots__ = ("net", "cells", "stamp", "plane", "what", "inner", "obj", "seg", "routed")

    def __init__(self, net, cells, stamp, plane, what, inner=None):
        self.net, self.cells, self.stamp, self.plane, self.what = net, cells, stamp, plane, what
        self.inner = inner if inner is not None else cells
        self.obj = self.seg = None
        self.routed = False                       # laid by the router (rip-up may take it back)


class Router:
    def __init__(self, board, P, B, w, h):
        self.board, self.P, self.B = board, P, B
        self.g = R.Grid(w, h)
        self.items = []
        self.by_net = {}
        self.nets = {}
        for name, ni in board.GetNetsByName().items():
            if str(name):
                self.nets[str(name)] = ni
        self.failed = []
        self.region = {}                          # net -> (class, cells) of a walled-in search
        self.n_tracks = self.n_vias = 0

    # ---- items ----------------------------------------------------------------
    def _item(self, net, shape, layers, plane=False, clear=R.CLEAR, what="", inner=None):
        c0 = self.g.shape_cells(shape, 0.0)
        cells = {L: set(c0) for L in layers}
        stamp = self.g.obstacle(shape, layers, clear)
        self.g.add(stamp)
        it = Item(net, cells, stamp, plane, what, {L: set(inner) for L in layers} if inner is not None else None)
        self.items.append(it)
        self.by_net.setdefault(net, []).append(len(self.items) - 1)
        return it

    def lift(self, net):
        for i in self.by_net.get(net, []):
            self.g.sub(self.items[i].stamp)

    def drop(self, net):
        for i in self.by_net.get(net, []):
            self.g.add(self.items[i].stamp)

    @staticmethod
    def pad_shape(pad, B):
        """("disc", x, y, r), ("seg", x0, y0, x1, y1, r) for an oval (the
        segment between its end circles' centres), or ("rect", x, y, hw, hh,
        angle) for the rest (a rounded rectangle's corners count as square)."""
        x, y = B(pad.GetPosition())
        sz = pad.GetSize(pcbnew.F_Cu)
        w, h = pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)
        kind = pad.GetShape(pcbnew.F_Cu)
        ang = -pad.GetOrientationDegrees()
        if kind == pcbnew.PAD_SHAPE_CIRCLE or (kind == pcbnew.PAD_SHAPE_OVAL and abs(w - h) < 1e-6):
            return ("disc", x, y, w / 2)
        if kind == pcbnew.PAD_SHAPE_CUSTOM:        # the SOT-89's tab: its anchor is not its outline
            bb = pad.GetBoundingBox()
            x0, y0 = B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
            x1, y1 = B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
            return ("rect", (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0.0)
        if kind == pcbnew.PAD_SHAPE_OVAL:
            # the long axis in the pad's frame, turned onto the board (the
            # inverse of the turn shape_cells applies to a rect)
            ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
            if h > w:
                L = (h - w) / 2
                dx, dy = -L * sa, L * ca
            else:
                L = (w - h) / 2
                dx, dy = L * ca, L * sa
            return ("seg", x - dx, y - dy, x + dx, y + dy, min(w, h) / 2)
        return ("rect", x, y, w / 2, h / 2, ang)

    @staticmethod
    def pad_layers(pad):
        if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            return [0, 1, 2]
        return [LIDX[l] for l in LAYERS if pad.IsOnLayer(l)]

    def load_pads(self):
        """Every pad becomes an item; drills (plated or not) forbid vias nearby; a footprint's
        rule areas (the U.FL's "no tracks under me") are keep-outs; its own copper graphics (the
        coupler's lines) are obstacles; an exposed pad (1.5 mm or more) is remembered for ep_vias()."""
        self.eps = []
        self.ep_refs = set()
        self.ep_shape = {}
        self.tabs = []                                 # a chip's smaller ground paddle or tab: vias inside it (tab_vias)
        n_rules = 0
        for fp in self.board.GetFootprints():
            for it in fp.GraphicalItems():
                if it.GetClass() == "PCB_SHAPE" and it.GetLayer() in LIDX and it.GetShape() == pcbnew.SHAPE_T_SEGMENT:
                    a, b = self.B(it.GetStart()), self.B(it.GetEnd())
                    w = pcbnew.ToMM(it.GetWidth())
                    shape = ("seg", a[0], a[1], b[0], b[1], w / 2)
                    # a coupler's line is the net of the pad it ends in (a foreign name walled the
                    # coupled and isolated ports in: Response 9)
                    for net, p0, p1 in copper_split(fp, a, b, self.B):
                        self._item(net, ("seg", p0[0], p0[1], p1[0], p1[1], w / 2), [LIDX[it.GetLayer()]], what="copper")
                    self._novia_shape(shape, VIA[0] / 2 + R.CLEAR)
            for z in fp.Zones():
                n_rules += 1
                if not z.GetIsRuleArea():
                    continue
                bb = z.GetBoundingBox()
                x0, y0 = self.B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
                x1, y1 = self.B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
                layers = [LIDX[l] for l in LAYERS if z.IsOnLayer(l)]
                m = VIA[0] / 2 + 0.2                   # a via centred just outside the area still overlaps it
                # tracks: the area as drawn (grown, a U.FL's area covered its own centre pad and
                # walled it in); vias: grown by their radius
                if z.GetDoNotAllowTracks() and layers:
                    self.keepout(x0 - 0.15, y0 - 0.15, x1 + 0.15, y1 + 0.15, layers, via=False)   # a track's half width and a little
                if z.GetDoNotAllowVias():
                    self.keepout(x0 - m, y0 - m, x1 + m, y1 + m, [], via=True)
            for pad in fp.Pads():
                shape = self.pad_shape(pad, self.B)
                x, y = shape[1], shape[2]
                att = pad.GetAttribute()
                if att in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                    d = pcbnew.ToMM(pad.GetDrillSize().x)
                    # no via drill within 0.25 mm of this drill (hole to hole), any net
                    self._novia(x, y, d / 2 + VIA[1] / 2 + 0.25)
                if att == pcbnew.PAD_ATTRIB_NPTH:
                    bb = pad.GetBoundingBox()
                    x0, y0 = self.B(pcbnew.VECTOR2I(bb.GetX(), bb.GetY()))
                    x1, y1 = self.B(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
                    self._item("<npth>", ("rect", (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0.0), [0, 1, 2], clear=0.3, what="npth")
                    self._novia_shape(("rect", (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2, 0.0), 0.5)
                    continue
                layers = self.pad_layers(pad)
                if not layers:
                    continue
                net = pad.GetNetname() or "<nc:%s.%s>" % (fp.GetReference(), pad.GetNumber())
                self._item(net, shape, layers, plane=(att == pcbnew.PAD_ATTRIB_PTH),
                           what="%s.%s" % (fp.GetReference(), pad.GetNumber()), inner=self._inner_cells(shape))
                sz = pad.GetSize(pcbnew.F_Cu)
                if att == pcbnew.PAD_ATTRIB_SMD and shape[0] == "rect" and min(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) >= 1.5 and net == "GND":
                    self.eps.append((net, shape, fp.GetReference()))       # an exposed pad: vias go INSIDE it
                    self.ep_refs.add(fp.GetReference())
                    self.ep_shape[fp.GetReference()] = shape
                    continue
                # a chip's ground paddle or tab under 1.5 mm (the SKY65404's 1.3 x 0.8, the SOT-89's tab:
                # a custom pad, judged by its outline): vias inside it too, where they fit (the design
                # review: the LNA's paddle had none and the gain blocks' tabs none)
                if (att == pcbnew.PAD_ATTRIB_SMD and net == "GND" and fp.GetReference().startswith("U") and shape[0] == "rect"
                        and min(shape[3], shape[4]) * 2 >= TAB_MIN):
                    self.tabs.append((pad, shape, fp.GetReference()))
                    continue
                # no vias inside any other pad (SMD or through hole), nor touching it
                self._novia_shape(shape, VIA[0] / 2 + R.CLEAR)
        self.n_tab_vias = self.tab_vias()          # first, before any fence or fan-out via can stand in a tab
        print("copper: %d footprint rule areas, %d exposed pads, %d vias in %d smaller paddles and tabs"
              % (n_rules, len(self.eps), self.n_tab_vias, len(self.tabs)), flush=True)

    def ep_vias(self, pitch=0.8, inset=0.45):
        """A grid of ground vias inside every exposed pad (CLAUDE_PCB.md section 5: many vias in an
        RF chip's paddle; they also join the paddle to the plane, so the chip's ground pins can be
        tied to it with short tracks instead of a via in front of each, which walled its
        neighbours in).  At 0.8 mm a 2.6 mm paddle takes 3 x 3, the ADL5380's and ADL5375's
        datasheet pattern (1.0 mm gave 2 x 2: the design review); then the smaller paddles and
        tabs (tab_vias, made with the pads).  Returns the number made."""
        n = 0
        for net, shape, ref in self.eps:
            _, cx, cy, hw, hh, ang = shape
            nx = max(1, int((2 * hw - 2 * inset) / pitch) + 1)
            ny = max(1, int((2 * hh - 2 * inset) / pitch) + 1)
            for i in range(nx):
                for j in range(ny):
                    x = cx - (nx - 1) * pitch / 2 + i * pitch
                    y = cy - (ny - 1) * pitch / 2 + j * pitch
                    k = self.g.k(x, y)
                    if self.g.novia[k]:
                        continue
                    self.via(net, x, y)
                    n += 1
        return n

    def tab_vias(self, spacing=0.75, margin=0.05):
        """Vias inside each smaller ground paddle or tab: as many along each axis as fit `spacing`
        apart (0.5 mm of drill to drill at the least), each wholly inside the pad's copper (its
        outline tested, so the SOT-89's tab takes them and its narrow lead does not)."""
        n = 0
        r = VIA[0] / 2 + margin
        for pad, shape, ref in self.tabs:
            _, cx, cy, hw, hh, ang = shape
            pos = []
            for half in (hw, hh):
                span = max(0.0, 2 * (half - r))
                k = 1 + int(span / spacing + 1e-9)
                pos.append([0.0] if k == 1 else [-span / 2 + i * span / (k - 1) for i in range(k)])
            for dx in pos[0]:
                for dy in pos[1]:
                    x, y = cx + dx, cy + dy
                    ring = [(x, y)] + [(x + r * math.cos(a), y + r * math.sin(a)) for a in [i * math.pi / 4 for i in range(8)]]
                    if not all(pad.HitTest(self.P(px, py)) for px, py in ring):
                        continue
                    if self.g.novia[self.g.k(x, y)]:
                        continue
                    self.via("GND", x, y)
                    n += 1
            self._novia_shape(shape, VIA[0] / 2 + R.CLEAR)     # then no other via in it, nor touching it
        return n

    def _inner_cells(self, shape, m=0.075):
        """A pad's cells at least m inside its edge (half a 0.15 mm track), so
        a track ending there never meets the pad at a corner only (KiCad's
        connection-width check); a pad too small for that offers its centre."""
        if shape[0] == "disc":
            _, x, y, rad = shape
            cells = self.g._disc(x, y, rad - m) if rad > m else []
            cx, cy = x, y
        elif shape[0] == "seg":
            _, x0, y0, x1, y1, hw = shape
            cells = self.g.shape_cells(("seg", x0, y0, x1, y1, max(hw - m, 0.0)), 1e-4)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        else:
            _, cx, cy, hw, hh, ang = shape
            cells = self.g.shape_cells(("rect", cx, cy, max(hw - m, 0.0), max(hh - m, 0.0), ang), 1e-4)
        return set(cells) or {self.g.k(cx, cy)}

    def _novia(self, x, y, r):
        for k in self.g._disc(x, y, r):
            self.g.novia[k] = 1

    def _novia_shape(self, shape, r):
        for k in self.g.shape_cells(shape, r):
            self.g.novia[k] = 1

    def keepout(self, x0, y0, x1, y1, layers, via=True):
        self.g.keepout(x0, y0, x1, y1, layers, via)

    # ---- adding copper ----------------------------------------------------------
    def track(self, net, L, a, b, width, stamp=True):
        t = pcbnew.PCB_TRACK(self.board)
        t.SetStart(self.P(*a)); t.SetEnd(self.P(*b))
        t.SetWidth(pcbnew.FromMM(width)); t.SetLayer(LAYERS[L])
        t.SetNet(self.nets[net])
        self.board.Add(t)
        self.n_tracks += 1
        if stamp:
            it = self._item(net, ("seg", a[0], a[1], b[0], b[1], width / 2), [L], what="track")
            it.obj, it.seg = t, (L, a, b, width)
        return t

    def polyline(self, net, L, pts, width):
        for a, b in zip(pts, pts[1:]):
            if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
                self.track(net, L, a, b, width)

    def via(self, net, x, y, size=VIA):
        v = pcbnew.PCB_VIA(self.board)
        v.SetPosition(self.P(x, y))
        v.SetWidth(pcbnew.FromMM(size[0])); v.SetDrill(pcbnew.FromMM(size[1]))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        # no pad on an inner layer the via does not connect on: the ground plane
        # then comes 0.2 mm from the drill instead of from a pad, and two vias
        # that touch on a layer they do not use make no narrow copper there
        v.Padstack().SetUnconnectedLayerMode(pcbnew.UNCONNECTED_LAYER_MODE_REMOVE_EXCEPT_START_AND_END)
        v.SetNet(self.nets[net])
        self.board.Add(v)
        self.n_vias += 1
        it = self._item(net, ("disc", x, y, size[0] / 2), [0, 1, 2], plane=True, what="via")
        it.obj, it.seg = v, ("via", x, y, size[1])
        self._novia(x, y, size[1] / 2 + VIA[1] / 2 + 0.25)
        if getattr(self, "_vcount", None) is not None:
            for k in self.g._disc(x, y, size[1] / 2 + VIA[1] / 2 + 0.25):
                self._vcount[k] += 1
        return v

    def void(self, layer, pts, name=None):
        """A rule area on `layer` where no copper fill is laid (tracks, vias and pads stay allowed): the RF
        launches' antipads and the ground relief under RF pads (gen/routes.rf_voids)."""
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer)
        z.SetIsRuleArea(True)
        for setter, val in (("SetDoNotAllowZoneFills", True), ("SetDoNotAllowCopperPour", True)):
            if hasattr(z, setter):
                getattr(z, setter)(val)
                break
        for setter in ("SetDoNotAllowVias", "SetDoNotAllowTracks", "SetDoNotAllowPads", "SetDoNotAllowFootprints"):
            if hasattr(z, setter):
                getattr(z, setter)(False)
        if name:
            z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(self.P(x, y))
        self.board.Add(z)
        return z

    def zone(self, net, layer, pts, priority=0, clearance=0.15, min_width=0.15, connect="thermal",
             name=None, item=True, spoke=0.25, gap=0.2, block_vias=True):
        """A copper pour.  With item=True its outline's inside is also a
        routing item: other nets keep clear of it on its layer, its own net may
        join it.  block_vias=False lets other nets' vias pass through it (the
        fill backs off round them), which a supply pour on an inner layer must
        allow or nothing can change layer under it."""
        z = pcbnew.ZONE(self.board)
        z.SetLayer(layer)
        z.SetNet(self.nets[net])
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(pcbnew.FromMM(clearance))
        z.SetMinThickness(pcbnew.FromMM(min_width))
        z.SetPadConnection({"thermal": pcbnew.ZONE_CONNECTION_THERMAL,
                            "solid": pcbnew.ZONE_CONNECTION_FULL}[connect])
        z.SetThermalReliefGap(pcbnew.FromMM(gap))
        z.SetThermalReliefSpokeWidth(pcbnew.FromMM(spoke))
        if name:
            z.SetZoneName(name)
        ol = z.Outline()
        ol.NewOutline()
        for x, y in pts:
            ol.Append(self.P(x, y))
        self.board.Add(z)
        if item and layer in LIDX:
            self._poly_item(net, LIDX[layer], pts, block_vias)
        return z

    def _poly_item(self, net, L, pts, block_vias=True):
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        i0, j0 = self.g.cell(min(xs), min(ys))
        i1, j1 = self.g.cell(max(xs), max(ys))
        inside = []
        for j in range(max(0, j0), min(self.g.ny - 1, j1) + 1):
            for i in range(max(0, i0), min(self.g.nx - 1, i1) + 1):
                if point_in_poly(i * R.PITCH, j * R.PITCH, pts):
                    inside.append(j * self.g.nx + i)
        stamp = {}
        inset = set(inside)
        for c in R.CLS:
            if c == "via" and not block_vias:
                continue
            r = R.CLEAR + R.CLASSES[c]
            n = int(math.ceil(r / R.PITCH))
            grown = set()
            # only the border cells need growing
            for k in inside:
                i, j = k % self.g.nx, k // self.g.nx
                if all(((j + dj) * self.g.nx + i + di) in inset for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                    grown.add(k)
                    continue
                for di in range(-n, n + 1):
                    for dj in range(-n, n + 1):
                        if (di * di + dj * dj) * R.PITCH * R.PITCH <= r * r:
                            ii, jj = i + di, j + dj
                            if 0 <= ii < self.g.nx and 0 <= jj < self.g.ny:
                                grown.add(jj * self.g.nx + ii)
            stamp[(L, c)] = list(grown)
        self.g.add(stamp)
        # a track joining the pour ends at least 0.3 mm inside its outline (one that ended on the
        # edge met fill that had backed off from a neighbour and stayed unconnected)
        nx = self.g.nx
        deep = {k for k in inset if all(k + d in inset for d in (3, -3, 3 * nx, -3 * nx))}
        it = Item(net, {L: inset}, stamp, False, "zone", inner={L: deep or inset})
        self.items.append(it)
        self.by_net.setdefault(net, []).append(len(self.items) - 1)

    # ---- connectivity ---------------------------------------------------------
    def on_plane(self, net, it):
        """Is this via or through-hole pad on the net's plane (GND: everywhere; a supply:
        at least PLANE_MARGIN inside its pour's outline)?"""
        poly = PLANES.get(net, False)
        if poly is False or not it.plane:
            return False
        if poly is None:
            return True
        cells = next(iter(it.cells.values()), None)
        if not cells:
            return False
        x, y = self.g.pos(next(iter(cells)))
        return inside_margin(x, y, poly, PLANE_MARGIN)

    def groups(self, net):
        ids = [i for i in self.by_net.get(net, []) if self.items[i].what != "dead"]
        parent = {i: i for i in ids}

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        owner = {}
        first_plane = None
        for i in ids:
            it = self.items[i]
            if self.on_plane(net, it):
                if first_plane is None:
                    first_plane = i
                else:
                    union(i, first_plane)
            for L, cells in it.cells.items():
                for k in cells:
                    o = owner.get((L, k))
                    if o is None:
                        owner[(L, k)] = i
                    else:
                        union(i, o)
        out = {}
        for i in ids:
            out.setdefault(find(i), []).append(i)
        return list(out.values())

    def cells_of(self, ids, layers=None, inner=False):
        s = set()
        for i in ids:
            for L, cells in (self.items[i].inner if inner else self.items[i].cells).items():
                if layers is None or L in layers:
                    for k in cells:
                        s.add((L, k))
        return s

    def unrouted(self, net):
        return len(self.groups(net)) - 1

    # ---- routing --------------------------------------------------------------
    def route_net(self, net, width, layers=(0, 1, 2), layer_cost=None, via_cost=R.VIA_COST,
                  max_pop=1500000, allow_via=True, bbox_margin=None):
        """Join the net's pieces, the smallest to the rest each time.  A piece that cannot
        be joined is set aside (the others may still reach it) and the rest go on: one
        blocked pad does not leave the whole net unrouted.  True if it ends in one piece."""
        cls = R.width_class(width)
        tries = 0
        stuck = set()                                 # items of pieces that failed as a start
        ok = True
        while True:
            groups = self.groups(net)
            if len(groups) < 2:
                return ok
            groups.sort(key=lambda g: len(self.cells_of(g)))
            free = [g for g in groups if not stuck.intersection(g)]
            if not free:
                return False
            src = free[0]
            others = [i for g in groups if g is not src for i in g]
            starts = self.cells_of(src, layers, inner=True)
            goals = self.cells_of(others, layers, inner=True)
            if not starts or not goals:
                self.failed.append((net, "no cells on the allowed layers"))
                return False
            bbox = None
            if bbox_margin is not None:
                pts = [self.g.pos(k) for _, k in list(starts) + list(goals)]
                m = bbox_margin
                bbox = (max(0, int((min(p[0] for p in pts) - m) / R.PITCH)),
                        max(0, int((min(p[1] for p in pts) - m) / R.PITCH)),
                        min(self.g.nx - 1, int((max(p[0] for p in pts) + m) / R.PITCH)),
                        min(self.g.ny - 1, int((max(p[1] for p in pts) + m) / R.PITCH)))
            self.lift(net)
            try:
                path = self.g.route(starts, goals, cls, layers=layers, allow_via=allow_via, max_pop=max_pop,
                                    bbox=bbox, via_cost=via_cost, layer_cost=layer_cost)
            finally:
                self.drop(net)
            if path is None:
                if self.g.last_region:
                    self.region[net] = (cls, self.g.last_region)
                what = ",".join(sorted(self.items[i].what for i in src if self.items[i].what not in ("track", "via")))
                self.failed.append((net, "from %s: %s" % (what or "a track", getattr(self.g, "last_why", "?"))))
                stuck.update(src)
                ok = False
                continue
            self.lay(net, path, width)
            tries += 1
            if tries > 200:
                self.failed.append((net, "too many pieces"))
                return False

    def pad_points(self, group):
        """{(ref, pad): (x, y)} for the pads among a piece's items (a piece of only tracks has none)"""
        out = {}
        for i in group:
            w = self.items[i].what
            if "." in w and w not in ("track", "via"):
                ref, num = w.rsplit(".", 1)
                xy = self.pads.xy.get((ref, num)) if getattr(self, "pads", None) else None
                if xy is not None:
                    out[(ref, num)] = xy
        return out

    def route_between(self, net, ga, gb, width, layers=(0, 1, 2), layer_cost=None, allow_via=True,
                      max_pop=100000, margin=2.0):
        """Join two given pieces of a net, searching only round them (margin mm): one short
        connection, without the rest of the net's pull.  True if laid; a failure is not recorded."""
        cls = R.width_class(width)
        starts = self.cells_of(ga, layers, inner=True)
        goals = self.cells_of(gb, layers, inner=True)
        if not starts or not goals:
            return False
        pts = [self.g.pos(k) for _, k in list(starts) + list(goals)]
        bbox = (max(0, int((min(p[0] for p in pts) - margin) / R.PITCH)),
                max(0, int((min(p[1] for p in pts) - margin) / R.PITCH)),
                min(self.g.nx - 1, int((max(p[0] for p in pts) + margin) / R.PITCH)),
                min(self.g.ny - 1, int((max(p[1] for p in pts) + margin) / R.PITCH)))
        self.lift(net)
        try:
            path = self.g.route(starts, goals, cls, layers=layers, allow_via=allow_via, max_pop=max_pop,
                                bbox=bbox, via_cost=R.VIA_COST, layer_cost=layer_cost)
        finally:
            self.drop(net)
        if path is None:
            return False
        self.lay(net, path, width)
        return True

    def lay(self, net, path, width):
        segs, vias = R.simplify(path, self.g.nx)
        n0 = len(self.items)
        for (L, x0, y0, x1, y1) in segs:
            self.track(net, L, (x0, y0), (x1, y1), width)
        for (x, y) in vias:
            self.via(net, x, y)
        for it in self.items[n0:]:
            it.routed = True

    # ---- rip-up -------------------------------------------------------------------
    def freeze_vias(self):
        """From here on a via the router lays can be taken back out: remember where vias
        may not go before it (the planned copper), and count the router's own."""
        self._nbase = bytes(self.g.novia)
        self._vcount = array("H", bytes(2 * len(self.g.novia)))

    def routed_copper(self, net):
        """The router's tracks and vias of `net`, to put back exactly (restore())."""
        return [it.seg for i in self.by_net.get(net, []) for it in [self.items[i]] if it.routed and it.seg]

    def rip(self, net):
        """Take every track and via the router laid for `net` back out."""
        for i in self.by_net.get(net, []):
            it = self.items[i]
            if not it.routed or it.what == "dead":
                continue
            self._kill(i)

    def restore(self, net, copper):
        for seg in copper:
            if seg[0] == "via":
                self.via(net, seg[1], seg[2])
            else:
                L, a, b, w = seg
                self.track(net, L, a, b, w)
            self.items[-1].routed = True

    def _kill(self, i):
        """Take a track or via out of the board and of the router (its item stays, empty)."""
        it = self.items[i]
        if it.what == "via" and it.seg and getattr(self, "_vcount", None) is not None:
            _, x, y, d = it.seg
            for k in self.g._disc(x, y, d / 2 + VIA[1] / 2 + 0.25):
                if self._vcount[k]:               # (a via from before freeze_vias() stays marked)
                    self._vcount[k] -= 1
                    if not self._vcount[k]:
                        self.g.novia[k] = self._nbase[k]
        self.g.sub(it.stamp)
        it.stamp = {}
        it.cells = {}
        it.inner = {}
        if it.obj is not None:
            self.board.Remove(it.obj)
            if it.what == "via":
                self.n_vias -= 1
            else:
                self.n_tracks -= 1
        it.what = "dead"
        it.obj = None
        it.seg = None

    def walls(self, net, cls, region, planned=False):
        """The nets whose router-laid copper bounds `region` (a walled-in search's cells,
        router.last_region): the ones to rip up so `net` can get out."""
        n = self.g.nx * self.g.ny
        nx = self.g.nx
        edge = {}
        for st in region:
            L, k = divmod(st, n)
            g, kl = self.g.g[(L, cls)], self.g.keep[L]
            for dk in (1, -1, nx, -nx, nx + 1, nx - 1, -nx + 1, -nx - 1):
                kk = k + dk
                if 0 <= kk < n and (g[kk] or kl[kk]):
                    edge.setdefault(L, set()).add(kk)
        out = []
        for other, ids in self.by_net.items():
            if other == net:
                continue
            for i in ids:
                it = self.items[i]
                if (it.routed or planned) and it.what != "dead" and any(
                        edge.get(L) and not edge[L].isdisjoint(ks)
                        for (L, c), ks in it.stamp.items() if c == cls):
                    out.append(other if not planned else "%s:%s%s" % (other, it.what, "" if it.routed else "(planned)"))
                    if not planned:
                        break
        if planned:
            kept = sum(1 for L, ks in edge.items() for k in ks if self.g.keep[L][k])
            out.append("keep:%d cells; layers %s" % (kept, sorted(edge)))
        return out

    # ---- after routing --------------------------------------------------------------
    def prune(self, net):
        """Take out the net's vias that change no layer (a fan-out via the router never used:
        KiCad reports it dangling) and every track with a loose end, each removal verified: the
        net must have no more pieces afterwards than before, or the item goes straight back.
        Ground is left alone (its fence and paddle vias carry no track by design).  Returns
        (vias, tracks) removed."""
        if net == "GND":
            return 0, 0
        base = self.unrouted(net)
        nv = nt = 0
        keep = set()                                      # segs that proved necessary
        while True:
            ids = [i for i in self.by_net.get(net, []) if self.items[i].what != "dead"]
            owner = {}
            for i in ids:
                for L, cells in self.items[i].cells.items():
                    for k in cells:
                        owner.setdefault((L, k), set()).add(i)
            killed = False
            for i in ids:
                it = self.items[i]
                if it.what == "dead" or not it.seg or it.seg in keep:
                    continue
                if it.what == "via":
                    used = {L for L in it.cells if any(j != i for k in it.cells[L] for j in owner.get((L, k), ()))}
                    if self.on_plane(net, it):
                        if used:
                            continue
                    elif len(used) >= 2:
                        continue
                elif it.what == "track":
                    L, a, b, w = it.seg
                    loose = False
                    for p in (a, b):
                        near = self.g._disc(p[0], p[1], max(w / 2, 0.1))
                        if not any(j != i for kk in near for j in owner.get((L, kk), ())):
                            loose = True
                    if not loose:
                        continue
                else:
                    continue
                seg, routed = it.seg, it.routed
                self._kill(i)
                if self.unrouted(net) > base:              # it was carrying the net after all
                    if seg[0] == "via" and len(used) == 1:
                        # a junction only: the tracks that met at the via, joined by a short track
                        # on that layer instead (KiCad calls a via used on one layer dangling)
                        L = next(iter(used))
                        x, y = seg[1], seg[2]
                        ends = []
                        for j in self.by_net.get(net, []):
                            jt = self.items[j]
                            if jt.what == "track" and jt.seg and jt.seg[0] == L:
                                for p in (jt.seg[1], jt.seg[2]):
                                    if math.hypot(p[0] - x, p[1] - y) <= VIA[0] / 2 + 0.01:
                                        ends.append((p, jt.seg[3], jt.routed))
                        for p, w, r in ends:
                            if math.hypot(p[0] - x, p[1] - y) > 1e-6:
                                self.track(net, L, (x, y), p, w)
                                self.items[-1].routed = r
                        if self.unrouted(net) <= base:
                            nv += 1
                            killed = True
                            break
                        for p, w, r in ends:
                            if math.hypot(p[0] - x, p[1] - y) > 1e-6:
                                self._kill(len(self.items) - 1)
                    if seg[0] == "via":
                        self.via(net, seg[1], seg[2])
                    else:
                        self.track(net, seg[0], seg[1], seg[2], seg[3])
                    self.items[-1].routed = routed
                    keep.add(seg)
                    continue
                if seg[0] == "via":
                    nv += 1
                else:
                    nt += 1
                killed = True
                break                                     # the owner map is stale: rebuild it
            if not killed:
                return nv, nt

    def sweep(self, net, reach=0.25):
        """The last word on loose ends: a track with an end that touches nothing of its net within
        `reach` carries nothing (KiCad reports it dangling); taken out, and again until none is
        left.  Returns how many."""
        n = 0
        keep = set()
        while True:
            ids = [i for i in self.by_net.get(net, []) if self.items[i].what != "dead"]
            owner = {}
            for i in ids:
                for L, cells in self.items[i].cells.items():
                    for k in cells:
                        owner.setdefault((L, k), set()).add(i)
            hit = None
            for i in ids:
                it = self.items[i]
                if it.what != "track" or not it.seg or it.seg in keep:
                    continue
                L, a, b, w = it.seg
                for p in (a, b):
                    near = self.g._disc(p[0], p[1], max(w / 2, reach))
                    if not any(j != i for kk in near for j in owner.get((L, kk), ())):
                        hit = i
                        break
                if hit is not None:
                    break
            if hit is None:
                return n
            it = self.items[hit]
            seg, routed, base = it.seg, it.routed, self.unrouted(net)
            L, a, b, w = seg
            # which end is loose
            loose_end = None
            for p in (a, b):
                near = self.g._disc(p[0], p[1], max(w / 2, reach))
                if not any(j != hit for kk in near for j in owner.get((L, kk), ())):
                    loose_end = p
            self._kill(hit)
            if self.unrouted(net) > base:
                # it carries the net through copper it crosses on the way (a pad of its own net under
                # it) and runs on past: trim it back to the last point that touches something
                far, nearp = (a, b) if loose_end == a else (b, a)
                Ln = math.hypot(far[0] - nearp[0], far[1] - nearp[1])
                cut = None
                steps = max(1, int(Ln / 0.05))
                for k in range(steps, -1, -1):
                    t = k / float(steps)
                    q = (nearp[0] + (far[0] - nearp[0]) * t, nearp[1] + (far[1] - nearp[1]) * t)
                    cells = self.g._disc(q[0], q[1], w / 2 + 0.01)
                    if any(j != hit for kk in cells for j in owner.get((L, kk), ())):
                        cut = q
                        break
                if cut is not None and math.hypot(cut[0] - nearp[0], cut[1] - nearp[1]) > 0.05:
                    self.track(net, L, nearp, cut, w)
                    self.items[-1].routed = routed
                    if self.unrouted(net) <= base:
                        n += 1
                        continue
                    self._kill(len(self.items) - 1)
                self.track(net, L, a, b, w)
                self.items[-1].routed = routed
                keep.add(seg)
                continue
            n += 1

    def fatten(self, net, widths, split=1.5, keep_narrow=()):
        """Widen the net's tracks toward `widths` (the widest first) wherever the copper
        round them leaves room: the router laid them at a width every pin they reach can
        take, and a power line is wide only where it can be.  Long tracks are first cut
        `split` from each end, so the part beside a fine pin stays narrow and the rest
        widens.  Returns (tracks widened, tracks in all)."""
        ids = [i for i in self.by_net.get(net, []) if self.items[i].what == "track" and self.items[i].seg]
        for i in ids:
            L, a, b, w = self.items[i].seg
            routed = self.items[i].routed
            n = math.hypot(b[0] - a[0], b[1] - a[1])
            if n <= 2 * split + 0.5:
                continue
            ux, uy = (b[0] - a[0]) / n, (b[1] - a[1]) / n
            p1 = (a[0] + ux * split, a[1] + uy * split)
            p2 = (b[0] - ux * split, b[1] - uy * split)
            self._kill(i)
            for q0, q1 in ((a, p1), (p1, p2), (p2, b)):
                self.track(net, L, q0, q1, w)
                self.items[-1].routed = routed
        self.lift(net)
        done = total = 0
        try:
            for i in list(self.by_net.get(net, [])):
                it = self.items[i]
                if it.what != "track" or not it.seg or not it.routed:
                    continue                      # a planned line (a fan-out stub at a pin) stays as drawn
                total += 1
                L, a, b, w = it.seg
                if any(math.hypot(a[0] - x, a[1] - y) < 1.0 or math.hypot(b[0] - x, b[1] - y) < 1.0 for x, y in keep_narrow):
                    continue                      # at a fine-pitch pin: the pad's width is the rule
                for wn in widths:
                    if wn <= w + 1e-6:
                        break
                    cls = R.width_class(wn)
                    # the centre line's cells: sampled with half a pitch of reach, since a line laid at
                    # pad coordinates lies between grid nodes and a radius-0 query found no cell at all
                    # (Response 9: fan-out stubs at QFN pins widened to 0.8 mm and shorted their neighbours)
                    cells = self.g.shape_cells(("seg", a[0], a[1], b[0], b[1], 0.0), R.PITCH * 1.01)
                    g, kl = self.g.g[(L, cls)], self.g.keep[L]
                    if any(g[k] or kl[k] for k in cells):
                        continue
                    it.obj.SetWidth(pcbnew.FromMM(wn))
                    it.seg = (L, a, b, wn)
                    it.stamp = self.g.obstacle(("seg", a[0], a[1], b[0], b[1], wn / 2), [L], R.CLEAR)
                    done += 1
                    break
        finally:
            self.drop(net)
        return done, total

    # ---- fan-out vias ----------------------------------------------------------------
    def fanout(self, net, pad_items=None, reach=1.6, width=0.25, skip=(), skip_refs=()):
        """A via beside every SMD pad of `net` that does not already reach
        it through copper: a short track from the pad to the nearest spot where
        a via fits.  For GND every via joins In1.  Pads of the parts in skip_refs
        (chips with an exposed pad) are left to the router, which ties them to
        the paddle."""
        made = 0
        for i in list(self.by_net.get(net, [])):
            it = self.items[i]
            if it.plane or it.what in ("track", "via", "zone", "copper", "dead") or not it.what:
                continue
            if pad_items is not None and it.what not in pad_items:
                continue
            if any(it.what.startswith(p) for p in skip):
                continue
            if it.what.split(".")[0] in skip_refs:
                continue
            if self._reaches_plane(net, i):
                continue
            spot = self._via_spot(net, it, reach, width)
            if spot is None and PLANES.get(net):
                spot = self._via_spot(net, it, reach, width, anywhere=True)   # off its pour: the router joins it on In2
            if spot is None:
                continue                          # the router joins it to the net later
            path, (x, y) = spot
            if len(path) > 1:
                self.lay(net, path, width)
            self.via(net, x, y)
            made += 1
        return made

    def _reaches_plane(self, net, i):
        if PLANES.get(net, False) is False:
            return False
        for g in self.groups(net):
            if i in g:
                return any(self.on_plane(net, self.items[j]) for j in g)
        return False

    def _via_spot(self, net, it, reach, width, anywhere=False):
        """Breadth-first from the pad's cells on its layer to the nearest cell
        where a via of `net` fits (on the net's plane, if it has one, unless `anywhere`);
        returns (path, (x, y))."""
        cls = R.width_class(width)
        L = min(it.cells)
        self.lift(net)
        try:
            gl = self.g.g[(L, cls)]
            vg = [self.g.g[(LL, "via")] for LL in range(R.NL)]
            start = [k for k in it.cells[L] if not self.g.keep[L][k]]     # never from inside a rule area
            if not start:                          # a pad off the grid (past the edge): nothing to fan out
                return None
            sx = sum(self.g.pos(k)[0] for k in start) / len(start)
            sy = sum(self.g.pos(k)[1] for k in start) / len(start)
            par = {k: None for k in start}
            frontier = list(start)
            nx = self.g.nx
            maxd = reach / R.PITCH
            poly = None if anywhere else PLANES.get(net)
            while frontier:
                nxt = []
                # nearest-first inside a ring: sort by distance from the pad centre
                frontier.sort(key=lambda k: (self.g.pos(k)[0] - sx) ** 2 + (self.g.pos(k)[1] - sy) ** 2)
                for k in frontier:
                    if k not in it.cells[L] and not self.g.novia[k] and all(not v[k] for v in vg) \
                            and not any(self.g.keep[LL][k] for LL in range(R.NL)) \
                            and (not poly or inside_margin(*self.g.pos(k), poly, PLANE_MARGIN)):
                        path = []
                        c = k
                        while c is not None:
                            path.append((L, c))
                            c = par[c]
                        path.reverse()
                        # start the track at the pad's centre cell (unless that lies in a rule area)
                        ck = self.g.k(sx, sy)
                        if ck in it.cells[L] and path[0][1] != ck and not self.g.keep[L][ck]:
                            path.insert(0, (L, ck))
                        return path, self.g.pos(k)
                for k in frontier:
                    i, j = k % nx, k // nx
                    for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                        ii, jj = i + di, j + dj
                        if not (0 <= ii < nx and 0 <= jj < self.g.ny):
                            continue
                        kk = jj * nx + ii
                        if kk in par or gl[kk] or self.g.keep[L][kk]:
                            continue
                        if di and dj and (self.g.keep[L][j * nx + ii] or self.g.keep[L][jj * nx + i]):
                            continue                      # a diagonal step clips the corner cell (a rule area)
                        if (ii - sx / R.PITCH) ** 2 + (jj - sy / R.PITCH) ** 2 > maxd * maxd:
                            continue
                        par[kk] = k
                        nxt.append(kk)
                frontier = nxt
        finally:
            self.drop(net)
        return None


def copper_split(fp, a, b, B):
    """A footprint's copper segment as (net, start, end) pieces: a line that joins two pads of
    different nets (a coupler's coupled line, a net tie) is half each, so neither end's pad is
    walled in by its own line under the other net's name."""
    na = _pad_net_at(fp, a, B)
    nb = _pad_net_at(fp, b, B)
    if na and nb and na != nb:
        m = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        return [(na, a, m), (nb, m, b)]
    return [(na or nb or "<cu:%s>" % fp.GetReference(), a, b)]


def _pad_net_at(fp, p, B):
    for pad in fp.Pads():
        x, y = B(pad.GetPosition())
        sz = pad.GetSize(pcbnew.F_Cu)
        r = max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) / 2 + 0.05
        if math.hypot(p[0] - x, p[1] - y) <= r and pad.GetNetname():
            return pad.GetNetname()
    return None


def copper_net(fp, a, b, B):
    """The net of the pad of `fp` that either end of the segment a-b lies in, or None."""
    for pad in fp.Pads():
        x, y = B(pad.GetPosition())
        sz = pad.GetSize(pcbnew.F_Cu)
        r = max(pcbnew.ToMM(sz.x), pcbnew.ToMM(sz.y)) / 2 + 0.05
        for p in (a, b):
            if math.hypot(p[0] - x, p[1] - y) <= r and pad.GetNetname():
                return pad.GetNetname()
    return None


def stamp(R, net, width, x0, y0, x1, y1):
    """The router's view of a window, for looking at why a net failed: per
    layer, 0 free, 1 blocked for this net's track width, 2 the net's own
    copper; and where a via would fit."""
    import router as RR
    cls = RR.width_class(width)
    i0, j0 = R.g.cell(x0, y0)
    i1, j1 = R.g.cell(x1, y1)
    own = R.cells_of(R.by_net.get(net, []))
    R.lift(net)
    try:
        layers = []
        for L in range(RR.NL):
            g = R.g.g[(L, cls)]
            rows = []
            for j in range(j0, j1 + 1):
                row = []
                for i in range(i0, i1 + 1):
                    k = j * R.g.nx + i
                    row.append(2 if (L, k) in own else (1 if (g[k] or R.g.keep[L][k]) else 0))
                rows.append(row)
            layers.append(rows)
        via = []
        vg = [R.g.g[(L, "via")] for L in range(RR.NL)]
        for j in range(j0, j1 + 1):
            via.append([0 if (not R.g.novia[j * R.g.nx + i] and all(not v[j * R.g.nx + i] for v in vg)) else 1
                        for i in range(i0, i1 + 1)])
    finally:
        R.drop(net)
    return dict(net=net, width=width, x0=i0 * RR.PITCH, y0=j0 * RR.PITCH, pitch=RR.PITCH, layers=layers, via=via)


def point_in_poly(x, y, pts):
    inside = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xc = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xc:
                inside = not inside
    return inside


def pt_seg(p, a, b):
    ax, ay = b[0] - a[0], b[1] - a[1]
    n = ax * ax + ay * ay
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * ax + (p[1] - a[1]) * ay) / n))
    return math.hypot(p[0] - a[0] - t * ax, p[1] - a[1] - t * ay)


def inside_margin(x, y, pts, m):
    """Inside the polygon and at least m from every edge (an L-shaped pour's bounding box
    says nothing: Response 8's two dangling vias sat in the notch of the +3V3_ANA pour)."""
    if not point_in_poly(x, y, pts):
        return False
    n = len(pts)
    return all(pt_seg((x, y), pts[i], pts[(i + 1) % n]) >= m for i in range(n))
