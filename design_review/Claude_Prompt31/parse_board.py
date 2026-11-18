#!/usr/bin/env python3 -I
"""Parse the committed board (an s-expression) into plain Python and pickle it.  Board frame: x = X - 25,
y = 125 - Y (the aux origin is the board's bottom-left corner, y up), the frame of PLACEMENT_CHECKS and the gerbers."""
import sys, math, pickle, os

HERE = os.path.dirname(os.path.abspath(__file__))
OX, OY = 25.0, 125.0


def parse(text):
    i, n = 0, len(text)
    stack = [[]]
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == '(':
            stack.append([]); i += 1
        elif c == ')':
            node = stack.pop(); stack[-1].append(node); i += 1
        elif c == '"':
            j = i + 1; s = []
            while text[j] != '"':
                if text[j] == '\\':
                    j += 1
                s.append(text[j]); j += 1
            stack[-1].append(''.join(s)); i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()':
                j += 1
            tok = text[i:j]
            try:
                v = float(tok) if ('.' in tok or 'e' in tok) else int(tok)
            except ValueError:
                v = tok
            stack[-1].append(v); i = j
    return stack[0][0]


def kids(node, key):
    return [k for k in node[1:] if isinstance(k, list) and k and k[0] == key]


def kid(node, key, default=None):
    k = kids(node, key)
    return k[0] if k else default


def netname(nets, nk):
    v = nk[1]
    return v if isinstance(v, str) else nets.get(v)


def bf(x, y):
    """page -> board frame"""
    return (round(x - OX, 4), round(OY - y, 4))


def rot(x, y, a):
    r = math.radians(a)
    return (x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r))


def main(path, out):
    root = parse(open(path, encoding='utf-8').read())
    nets = {}
    for nd in kids(root, 'net'):
        nets[nd[1]] = nd[2]
    fps = []
    for fp in kids(root, 'footprint'):
        at = kid(fp, 'at')
        fx, fy = at[1], at[2]
        fa = at[3] if len(at) > 3 else 0
        layer = kid(fp, 'layer')[1]
        props = {p[1]: p[2] for p in kids(fp, 'property') if len(p) > 2 and isinstance(p[2], str)}
        ref = props.get('Reference', '?')
        attr = kid(fp, 'attr', [])
        dnp = 'dnp' in attr
        pads = []
        for p in kids(fp, 'pad'):
            pat = kid(p, 'at')
            px, py = pat[1], pat[2]
            pa = pat[3] if len(pat) > 3 else fa
            # pad position in page frame: footprint rotation is counter-clockwise in KiCad's y-down frame
            # pcbnew: footprint at angle a: pad page pos = fp pos + rotate(pad local, -a) in y-down coords
            dx, dy = rot(px, py, -fa)
            X, Y = fx + dx, fy + dy
            size = kid(p, 'size')
            drill = kid(p, 'drill')
            dr = None
            if drill:
                dr = [v for v in drill[1:] if isinstance(v, (int, float))]
            netk = kid(p, 'net')
            layers = kid(p, 'layers', [])[1:]
            # pad angle on the board (page frame, KiCad CCW degrees): the pad's own 'at' angle is absolute
            pads.append(dict(num=str(p[1]), kind=p[2], shape=p[3], xy=bf(X, Y), size=(size[1], size[2]),
                             angle=pa, drill=dr, net=(netname(nets, netk) if netk else None), layers=layers,
                             rr=(kid(p, 'roundrect_rratio') or [None, None])[1]))
        texts = []
        for t in kids(fp, 'property') + kids(fp, 'fp_text'):
            tl = kid(t, 'layer')
            if not tl:
                continue
            hide = kid(t, 'hide')
            if hide and hide[1] == 'yes':
                continue
            tat = kid(t, 'at')
            eff = kid(t, 'effects'); font = kid(eff, 'font') if eff else None
            size = kid(font, 'size') if font else None
            th = kid(font, 'thickness') if font else None
            s = t[2] if t[0] == 'property' else (t[2] if len(t) > 2 else '')
            if t[0] == 'property':
                name = t[1]
            else:
                name = t[1]
            # text position: relative to footprint, rotated by fp angle; angle given absolute in KiCad 8+
            dx, dy = rot(tat[1], tat[2], -fa)
            texts.append(dict(name=name, text=s, layer=tl[1], xy=bf(fx + dx, fy + dy), angle=(tat[3] if len(tat) > 3 else 0),
                              size=(size[1], size[2]) if size else None, thick=th[1] if th else None))
        graphics = []
        for g in [k for k in fp[1:] if isinstance(k, list) and k and k[0] in ('fp_line', 'fp_rect', 'fp_circle', 'fp_poly', 'fp_arc')]:
            gl = kid(g, 'layer')[1]
            st = kid(g, 'stroke'); w = kid(st, 'width')[1] if st else 0
            if g[0] in ('fp_line', 'fp_rect'):
                s, e = kid(g, 'start'), kid(g, 'end')
                dx, dy = rot(s[1], s[2], -fa); ex, ey = rot(e[1], e[2], -fa)
                graphics.append(dict(kind=g[0], layer=gl, a=bf(fx + dx, fy + dy), b=bf(fx + ex, fy + ey), w=w,
                                     fill=(kid(g, 'fill') or [None, 'no'])[1]))
            elif g[0] == 'fp_circle':
                c, e = kid(g, 'center'), kid(g, 'end')
                dx, dy = rot(c[1], c[2], -fa)
                r = math.hypot(e[1] - c[1], e[2] - c[2])
                graphics.append(dict(kind='circle', layer=gl, a=bf(fx + dx, fy + dy), r=r, w=w, fill=(kid(g, 'fill') or [None, 'no'])[1]))
            elif g[0] == 'fp_poly':
                pts = kid(g, 'pts')
                P = []
                for xy in kids(pts, 'xy'):
                    dx, dy = rot(xy[1], xy[2], -fa)
                    P.append(bf(fx + dx, fy + dy))
                graphics.append(dict(kind='poly', layer=gl, pts=P, w=w, fill=(kid(g, 'fill') or [None, 'no'])[1]))
        fps.append(dict(ref=ref, name=fp[1], xy=bf(fx, fy), angle=fa, layer=layer, dnp=dnp, attr=attr[1:], props=props,
                        pads=pads, texts=texts, graphics=graphics))
    segs = []
    for s in kids(root, 'segment'):
        a, b = kid(s, 'start'), kid(s, 'end')
        segs.append(dict(a=bf(a[1], a[2]), b=bf(b[1], b[2]), w=kid(s, 'width')[1], layer=kid(s, 'layer')[1], net=netname(nets, kid(s, 'net'))))
    vias = []
    for v in kids(root, 'via'):
        a = kid(v, 'at')
        lay = kid(v, 'layers')
        vias.append(dict(xy=bf(a[1], a[2]), size=kid(v, 'size')[1], drill=kid(v, 'drill')[1], net=netname(nets, kid(v, 'net')),
                         layers=lay[1:] if lay else None))
    zones = []
    for z in kids(root, 'zone'):
        zn = (kid(z, 'net_name') or kid(z, 'net') or [None, ''])[1]
        if not isinstance(zn, str): zn = nets.get(zn, '')
        lay = kid(z, 'layer') or kid(z, 'layers')
        name = kid(z, 'name', [None, ''])[1]
        outline = []
        for poly in kids(z, 'polygon'):
            outline = [bf(p[1], p[2]) for p in kids(kid(poly, 'pts'), 'xy')]
        filled = []
        for fpoly in kids(z, 'filled_polygon'):
            fl = kid(fpoly, 'layer')[1]
            pts = [bf(p[1], p[2]) for p in kids(kid(fpoly, 'pts'), 'xy')]
            filled.append((fl, pts))
        fill = kid(z, 'fill')
        settings = {}
        if fill:
            for k in fill[1:]:
                if isinstance(k, list):
                    settings[k[0]] = k[1:]
        zones.append(dict(net=zn, layers=lay[1:], name=name, outline=outline, filled=filled, settings=settings,
                          priority=(kid(z, 'priority') or [None, 0])[1], min_thickness=(kid(z, 'min_thickness') or [None, None])[1],
                          clearance=(kid(kid(z, 'connect_pads') or [], 'clearance') or [None, None])[1] if kid(z, 'connect_pads') else None))
    gr = []
    for g in [k for k in root[1:] if isinstance(k, list) and k and k[0] in ('gr_line', 'gr_rect', 'gr_circle', 'gr_poly', 'gr_arc', 'gr_text')]:
        gl = kid(g, 'layer')[1]
        if g[0] == 'gr_text':
            at = kid(g, 'at'); eff = kid(g, 'effects'); font = kid(eff, 'font')
            size = kid(font, 'size'); th = kid(font, 'thickness')
            gr.append(dict(kind='text', layer=gl, text=g[1], xy=bf(at[1], at[2]), angle=(at[3] if len(at) > 3 else 0),
                           size=(size[1], size[2]), thick=th[1] if th else None, just=kid(eff, 'justify')))
        elif g[0] in ('gr_line', 'gr_rect'):
            s, e = kid(g, 'start'), kid(g, 'end')
            st = kid(g, 'stroke'); w = kid(st, 'width')[1] if st else 0
            gr.append(dict(kind=g[0], layer=gl, a=bf(s[1], s[2]), b=bf(e[1], e[2]), w=w))
        elif g[0] == 'gr_circle':
            c, e = kid(g, 'center'), kid(g, 'end')
            st = kid(g, 'stroke'); w = kid(st, 'width')[1] if st else 0
            gr.append(dict(kind='circle', layer=gl, a=bf(c[1], c[2]), r=math.hypot(e[1] - c[1], e[2] - c[2]), w=w))
        elif g[0] == 'gr_poly':
            pts = [bf(p[1], p[2]) for p in kids(kid(g, 'pts'), 'xy')]
            st = kid(g, 'stroke'); w = kid(st, 'width')[1] if st else 0
            gr.append(dict(kind='poly', layer=gl, pts=pts, w=w, fill=(kid(g, 'fill') or [None, 'no'])[1]))
        elif g[0] == 'gr_arc':
            s, m, e = kid(g, 'start'), kid(g, 'mid'), kid(g, 'end')
            st = kid(g, 'stroke'); w = kid(st, 'width')[1] if st else 0
            gr.append(dict(kind='arc', layer=gl, a=bf(s[1], s[2]), m=bf(m[1], m[2]), b=bf(e[1], e[2]), w=w))
    setup = kid(root, 'setup')
    data = dict(nets=nets, fps=fps, segs=segs, vias=vias, zones=zones, gr=gr)
    pickle.dump(data, open(out, 'wb'))
    print("footprints %d, segments %d, vias %d, zones %d, graphics %d, nets %d" % (len(fps), len(segs), len(vias), len(zones), len(gr), len(nets)))
    for z in zones:
        print("zone %-14s %-10s %-16s prio %s minw %s clr %s polys %d settings %s" % (z['net'], z['layers'], z['name'], z['priority'], z['min_thickness'], z['clearance'], len(z['filled']), {k: v for k, v in z['settings'].items() if k in ('island_removal_mode', 'thermal_gap', 'thermal_bridge_width', 'island_area_min')}))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
