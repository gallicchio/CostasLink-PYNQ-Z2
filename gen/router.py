"""A grid router with A* per connection, for a four-layer board whose In1 is
an unbroken ground plane: tracks go on F.Cu, In2.Cu and B.Cu.

Adapted from the ECP5-2ADC-2DAC project's pcb/router.py.  Obstacles live in
reference-counted cell grids, one per (layer, width class): an obstacle of
radius R blocks every cell closer than R + clearance + half the track width,
so a track of that class is legal wherever its cells are free.  A net's own
pads and tracks are lifted out of the grids while it is routed, which lets a
track start inside its pad and join its own net anywhere.  Vias are through
vias and need a free cell on every routing layer in the via's class.

Grid pitch 0.1 mm, so the RP2354A's 0.4 mm pins sit on it.
"""
import heapq, math
from array import array

PITCH = 0.1
LAYERS = ["F.Cu", "In2.Cu", "B.Cu"]          # In1.Cu is the ground plane
NL = len(LAYERS)
CLEAR = 0.16                                   # rules ask 0.15; the grid rounds
# half widths: fine 0.127 mm, thin 0.15, mid 0.2, wide 0.4, via 0.45 mm pad
# half widths: fine 0.127 mm, thin 0.15, mid 0.2, mid2 0.3, wide 0.4, fat 0.8 (a track wider than its
# class's half width overlaps its neighbours: Response 8's first board routed 0.8 mm rails as "wide")
CLASSES = {"fine": 0.0635, "thin": 0.075, "mid": 0.1, "mid2": 0.15, "wide": 0.2, "fat": 0.4, "via": 0.225}
CLS = ["fine", "thin", "mid", "mid2", "wide", "fat", "via"]
REGION = 40000                                 # a walled-in search smaller than this keeps its cells (rip-up)
VIA_COST = 40.0                                # about 4 mm of track
TURN_COST = 2.0
# per layer, the cost multiplier of (horizontal, vertical) steps: F.Cu free,
# In2 and B.Cu nudged toward one direction each so they cross cleanly
DIR_PENALTY = {0: (1.0, 1.0), 1: (1.0, 1.3), 2: (1.3, 1.0)}


def width_class(w):
    hw = w / 2.0
    for c in ("fine", "thin", "mid", "mid2", "wide", "fat"):
        if hw <= CLASSES[c] + 1e-6:
            return c
    raise ValueError("no width class for a %.2f mm track" % w)


class Grid:
    def __init__(self, w, h, edge_clear=0.3):
        self.w, self.h = w, h
        self.nx, self.ny = int(round(w / PITCH)) + 1, int(round(h / PITCH)) + 1
        self.n = self.nx * self.ny
        self.g = {(L, c): array("H", bytes(2 * self.n)) for L in range(NL) for c in CLS}
        self.keep = {L: bytearray(self.n) for L in range(NL)}    # 1 = no track of any net
        self.novia = bytearray(self.n)
        # the board edge: copper keeps edge_clear from it
        for c in CLS:
            m = int(math.ceil((edge_clear + CLASSES[c]) / PITCH))
            for L in range(NL):
                a = self.g[(L, c)]
                for j in range(self.ny):
                    for i in range(self.nx):
                        if i < m or j < m or i >= self.nx - m or j >= self.ny - m:
                            a[j * self.nx + i] += 1

    def cell(self, x, y):
        return (int(round(x / PITCH)), int(round(y / PITCH)))

    def k(self, x, y):
        i, j = self.cell(x, y)
        return j * self.nx + i

    def pos(self, k):
        return ((k % self.nx) * PITCH, (k // self.nx) * PITCH)

    # ---- obstacles --------------------------------------------------------
    def shape_cells(self, shape, r):
        """Cells within r of a shape: ("disc", x, y, rad) | ("rect", x, y, hw,
        hh, ang) | ("seg", x0, y0, x1, y1, hw)."""
        kind = shape[0]
        if kind == "disc":
            _, x, y, rad = shape
            return self._disc(x, y, rad + r)
        if kind == "seg":
            _, x0, y0, x1, y1, hw = shape
            L = math.hypot(x1 - x0, y1 - y0)
            n = max(1, int(L / (PITCH * 0.5)))
            out = set()
            for s in range(n + 1):
                t = s / float(n)
                out.update(self._disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, hw + r))
            return out
        _, x, y, hw, hh, ang = shape
        ca, sa = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        rr = math.hypot(hw, hh) + r
        ci, cj = self.cell(x, y)
        n = int(math.ceil(rr / PITCH)) + 1
        out = []
        for di in range(-n, n + 1):
            i = ci + di
            if not (0 <= i < self.nx):
                continue
            for dj in range(-n, n + 1):
                j = cj + dj
                if not (0 <= j < self.ny):
                    continue
                dx, dy = i * PITCH - x, j * PITCH - y
                ux, uy = dx * ca + dy * sa, -dx * sa + dy * ca
                gx, gy = max(0.0, abs(ux) - hw), max(0.0, abs(uy) - hh)
                if gx * gx + gy * gy <= r * r + 1e-9:
                    out.append(j * self.nx + i)
        return out

    def _disc(self, x, y, r):
        ci, cj = self.cell(x, y)
        n = int(math.ceil(r / PITCH)) + 1
        out = []
        r2 = r * r + 1e-9
        for di in range(-n, n + 1):
            i = ci + di
            if not (0 <= i < self.nx):
                continue
            dx2 = (i * PITCH - x) ** 2
            for dj in range(-n, n + 1):
                j = cj + dj
                if 0 <= j < self.ny and dx2 + (j * PITCH - y) ** 2 <= r2:
                    out.append(j * self.nx + i)
        return out

    def obstacle(self, shape, layers, clear=CLEAR):
        """{(L, cls): cells} that `shape` on `layers` blocks for each class."""
        out = {}
        for c in CLS:
            cells = self.shape_cells(shape, clear + CLASSES[c])
            for L in layers:
                out[(L, c)] = cells
        return out

    def add(self, cells):
        for key, ks in cells.items():
            a = self.g[key]
            for k in ks:
                a[k] += 1

    def sub(self, cells):
        for key, ks in cells.items():
            a = self.g[key]
            for k in ks:
                if a[k] > 0:
                    a[k] -= 1

    def keepout(self, x0, y0, x1, y1, layers, via=True):
        i0, j0 = self.cell(min(x0, x1), min(y0, y1))
        i1, j1 = self.cell(max(x0, x1), max(y0, y1))
        for j in range(max(0, j0), min(self.ny - 1, j1) + 1):
            for i in range(max(0, i0), min(self.nx - 1, i1) + 1):
                k = j * self.nx + i
                for L in layers:
                    self.keep[L][k] = 1
                if via:
                    self.novia[k] = 1

    # ---- the search -------------------------------------------------------
    def route(self, starts, goals, cls, layers=None, allow_via=True, max_pop=600000, bbox=None,
              via_cost=VIA_COST, layer_cost=None):
        """starts, goals: sets of (L, k).  Returns [(L, k), ...] or None.
        layer_cost: {L: multiplier} on a layer's step costs (default 1).  A search that
        fails leaves the cells it explored in last_region (for the rip-up) and why in
        last_why."""
        nx, n = self.nx, self.n
        if bbox is None:
            i0, j0, i1, j1 = 0, 0, nx - 1, self.ny - 1
        else:
            i0, j0, i1, j1 = bbox
        grid = [self.g[(L, cls)] for L in range(NL)]
        vg = [self.g[(L, "via")] for L in range(NL)]
        keep = self.keep
        novia = self.novia
        use = list(layers) if layers is not None else list(range(NL))
        # a search's states are L * n + k in flat arrays kept between searches: a state's
        # cost is valid only where its stamp is this search's number, so nothing is cleared
        if getattr(self, "_best", None) is None:
            self._best = array("d", bytes(8 * NL * n))
            self._stamp = array("i", bytes(4 * NL * n))
            self._par = array("i", bytes(4 * NL * n))
            self._gen = 0
        self._gen += 1
        gen, best, stamp, par = self._gen, self._best, self._stamp, self._par
        goal = {L * n + k for (L, k) in goals}
        # the heuristic: the octile distance to the nearest of at most 24 representatives
        # of the goal (one a millimetre square), less what a representative may lie beyond
        # the goal's nearest cell, so it never overestimates by much
        reps = {}
        for (_, k) in goals:
            i, j = k % nx, k // nx
            reps.setdefault((i // 10, j // 10), (i, j))
        gpts = list(reps.values())
        if len(gpts) > 24:
            gpts = gpts[::max(1, len(gpts) // 24)]
        slack = 14 if len(reps) > 1 or len(goals) > 1 else 0

        def h(i, j):
            m = 1e18
            for gi, gj in gpts:
                a, b = abs(gi - i), abs(gj - j)
                v = (a + 0.414 * b) if a > b else (b + 0.414 * a)
                if v < m:
                    m = v
            m -= slack
            return m * 0.98 if m > 0 else 0.0

        pq = []
        push, pop = heapq.heappush, heapq.heappop
        for (L, k) in starts:
            st = L * n + k
            if st in goal:
                return [(L, k)]
            if L not in use:
                continue
            best[st], stamp[st], par[st] = 0.0, gen, -1
            push(pq, (h(k % nx, k // nx), 0.0, st, -1))
        NB = [(1, 0, 1.0, 0), (-1, 0, 1.0, 0), (0, 1, 1.0, 1), (0, -1, 1.0, 1),
              (1, 1, 1.414, 2), (1, -1, 1.414, 3), (-1, 1, 1.414, 3), (-1, -1, 1.414, 2)]
        NB = [(di, dj, c, nd, dj * nx + di) for di, dj, c, nd in NB]
        cost = {}
        for L in range(NL):
            ph, pv = DIR_PENALTY[L]
            lc = layer_cost.get(L, 1.0) if layer_cost else 1.0
            cost[L] = (ph * lc, pv * lc, (ph + pv) * lc / 2.0)
        pops, found = 0, -1
        seen = self.last_region = []          # where a search that walls in went (rip-up)
        self.last_why = "?"
        while pq:
            f, gc, st, d = pop(pq)
            if best[st] < gc - 1e-9:
                continue
            pops += 1
            if pops < REGION:
                seen.append(st)
            if pops > max_pop:
                self.last_why = "search budget (%d steps)" % max_pop
                break
            if st in goal:
                found = st
                break
            L = st // n
            k = st - L * n
            i, j = k % nx, k // nx
            ph, pv, pd = cost[L]
            gl, kl = grid[L], keep[L]
            base = L * n
            for di, dj, c, nd, dk in NB:
                ii, jj = i + di, j + dj
                if ii < i0 or jj < j0 or ii > i1 or jj > j1:
                    continue
                kk = k + dk
                s2 = base + kk
                if kl[kk] or (gl[kk] and s2 not in goal):
                    continue                          # a keep-out never serves, not even as the goal's own cell
                if di and dj:
                    if gl[k + di] or gl[k + dj * nx] or kl[k + di] or kl[k + dj * nx]:
                        continue                      # a diagonal clips both corner cells (a rule area too)
                    cc = c * pd
                else:
                    cc = ph if di else pv
                if d >= 0 and d != nd:
                    cc += TURN_COST
                ng = gc + cc
                if stamp[s2] != gen or ng < best[s2]:
                    best[s2], stamp[s2], par[s2] = ng, gen, st
                    push(pq, (ng + h(ii, jj), ng, s2, nd))
            if allow_via and not novia[k] and not vg[0][k] and not vg[1][k] and not vg[2][k]:
                hv = None
                for LL in use:
                    if LL == L:
                        continue
                    s2 = LL * n + k
                    ng = gc + via_cost
                    if stamp[s2] != gen or ng < best[s2]:
                        best[s2], stamp[s2], par[s2] = ng, gen, st
                        if hv is None:
                            hv = h(i, j)
                        push(pq, (ng + hv, ng, s2, -1))
        if found < 0:
            if pops <= max_pop:
                self.last_why = "walled in (%d steps)" % pops
            if pops >= REGION:
                self.last_region = []
            return None
        path, cur = [], found
        while cur >= 0:
            path.append((cur // n, cur % n))
            cur = par[cur]
        path.reverse()
        return path


def simplify(path, nx):
    """Runs of one direction on one layer become segments; a change of layer
    is a via.  Returns (segments [(L, x0, y0, x1, y1)], vias [(x, y)])."""
    segs, vias = [], []
    if not path:
        return segs, vias
    pts = [(L, (k % nx) * PITCH, (k // nx) * PITCH) for L, k in path]
    i = 0
    while i < len(pts) - 1:
        L, x, y = pts[i]
        if pts[i + 1][0] != L:
            vias.append((x, y))
            i += 1
            continue
        dx, dy = round((pts[i + 1][1] - x) / PITCH), round((pts[i + 1][2] - y) / PITCH)
        j = i + 1
        while j + 1 < len(pts) and pts[j + 1][0] == L and \
                (round((pts[j + 1][1] - pts[j][1]) / PITCH), round((pts[j + 1][2] - pts[j][2]) / PITCH)) == (dx, dy):
            j += 1
        segs.append((L, x, y, pts[j][1], pts[j][2]))
        i = j
    return segs, vias
