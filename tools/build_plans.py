"""The plan page: the apartment drawn from apartment.json, with the pieces placed in the 3D (furnish.json) and the
sun's path over the site. The drawing helpers also record plain geometry (REC) that build_3d.py turns into the 3D.

All geometry is in centimetres, x to the right of the sheet, y down the sheet (the plan's top edge faces
site.facing in apartment.json).
  python3 tools/build_plans.py            -> site/plan.html
"""
import html as htmlmod, json, math, os, re
import sunpath
import openings
import apartment

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = apartment.ROOT
OUT = os.path.join(ROOT, 'site', 'plan.html')

# ---------------------------------------------------------------- 3D recorder
# When REC is a list, the drawing helpers also append plain geometry records that build_3d.py turns into the 3D
# model. CTX holds the active variant classes.
REC = None
CTX = []
REC_RECT = {'wall', 'wall neww', 'col', 'island', 'table', 'tv', 'track'}
FURN = [0]


def rec(kind, **kw):
    if REC is not None:
        REC.append(dict(kind=kind, ctx=list(CTX), furn=FURN[0] > 0, **kw))


# ---------------------------------------------------------------- primitives
def f(v):
    return ('%.1f' % v).rstrip('0').rstrip('.')

def rect(x0, y0, x1, y1, cls='', rx=0, extra=''):
    if cls in REC_RECT or cls.startswith('gpanel') or cls.startswith('z '):
        rec('rect', box=(x0, y0, x1, y1), cls=cls)
    r = f' rx="{f(rx)}"' if rx else ''
    if cls.split(' ')[0] == 'table':
        cls += ' loose'                       # a loose table (the plan's Built-in only view hides it)
    return f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(x1-x0)}" height="{f(y1-y0)}"{r} class="{cls}"{extra}/>'

def text(x, y, s, cls='', extra=''):
    return f'<text x="{f(x)}" y="{f(y)}" class="{cls}"{extra}>{s}</text>'

def line(x0, y0, x1, y1, cls=''):
    return f'<line x1="{f(x0)}" y1="{f(y0)}" x2="{f(x1)}" y2="{f(y1)}" class="{cls}"/>'

def circle(cx, cy, r, cls=''):
    if cls in ('table', 'rug'):
        cls += ' loose'
    return f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}" class="{cls}"/>'

def wall(x0, y0, x1, y1, openings=(), cls='wall'):
    """Solid wall rectangle split around openings [(a, b), ...] along its long axis."""
    horiz = (x1 - x0) >= (y1 - y0)
    lo, hi = (x0, x1) if horiz else (y0, y1)
    cuts = sorted(openings)
    segs, cur = [], lo
    for a, b in cuts:
        if a > cur:
            segs.append((cur, a))
        cur = max(cur, b)
    if cur < hi:
        segs.append((cur, hi))
    for a, b in cuts:
        rec('opening', box=(a, y0, b, y1) if horiz else (x0, a, x1, b), cls=cls)
    out = []
    for a, b in segs:
        out.append(rect(a, y0, b, y1, cls) if horiz else rect(x0, a, x1, b, cls))
    return ''.join(out)

def window(x0, y0, x1, y1):
    rec('window', box=(x0, y0, x1, y1))
    horiz = (x1 - x0) >= (y1 - y0)
    s = rect(x0, y0, x1, y1, 'win')
    if horiz:
        m = (y0 + y1) / 2
        s += line(x0, m, x1, m, 'winl')
    else:
        m = (x0 + x1) / 2
        s += line(m, y0, m, y1, 'winl')
    return s

def door(hx, hy, lx, ly, ex, ey, cls='door'):
    """Swing door: hinge H, leaf end L (door open 90deg), closed position E."""
    rec('door', hinge=(hx, hy), leaf=(lx, ly), shut=(ex, ey), cls=cls)
    r = math.hypot(lx - hx, ly - hy)
    a1 = math.atan2(ly - hy, lx - hx); a2 = math.atan2(ey - hy, ex - hx)
    d = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    sweep = 1 if d > 0 else 0
    return (f'<path d="M{f(hx)} {f(hy)} L{f(lx)} {f(ly)}" class="{cls}"/>'
            f'<path d="M{f(lx)} {f(ly)} A{f(r)} {f(r)} 0 0 {sweep} {f(ex)} {f(ey)}" class="swing"/>')

def slider(x0, y0, x1, y1, n=2):
    """Garden sliding door drawn as n overlapping panels inside the opening."""
    rec('slider', box=(x0, y0, x1, y1))
    horiz = (x1 - x0) >= (y1 - y0)
    out = [rect(x0, y0, x1, y1, 'sillg')]
    L = (x1 - x0) if horiz else (y1 - y0)
    p = L / n + 6
    for i in range(n):
        o = i * (L - p) / (n - 1) if n > 1 else 0
        off = -2 if i % 2 else 2
        if horiz:
            m = (y0 + y1) / 2 + off
            out.append(rect(x0 + o, m - 1.6, x0 + o + p, m + 1.6, 'pane'))
        else:
            m = (x0 + x1) / 2 + off
            out.append(rect(m - 1.6, y0 + o, m + 1.6, y0 + o + p, 'pane'))
    return ''.join(out)

def label(x, y, name, area=None, cls='rl'):
    s = text(x, y, name, cls)
    if area:
        s += text(x, y + 26, area, 'ra')
    return s

def room(x, y, name, rect=None, dims=None, note=None):
    """Room label: name, then width x length in metres; area on a third line, hidden unless 'Areas' is on."""
    s = text(x, y, name, 'rl')
    if rect:
        x0, y0, x1, y1 = rect
        dims = dims or f'{(x1 - x0) / 100:.2f} × {(y1 - y0) / 100:.2f}'
    rec('room', name=name, at=(x, y), rect=rect, dims=dims)
    if rect:
        s += text(x, y + 26, dims, 'rdim')
        s += text(x, y + 50, f'{(x1 - x0) * (y1 - y0) / 1e4:.1f} m²', 'ra')
    elif dims:
        s += text(x, y + 26, dims, 'rdim')
    if note:
        s += text(x, y + (50 if rect or dims else 26), note, 'gh')
    return s

def m2(*rects):
    a = sum((x1 - x0) * (y1 - y0) for x0, y0, x1, y1 in rects) / 1e4
    return f'{a:.1f} m²'

def dim(x0, y0, x1, y1, t, off=0):
    """Dimension line with ticks; text centred."""
    horiz = abs(y1 - y0) < abs(x1 - x0)
    s = line(x0, y0, x1, y1, 'dl')
    if horiz:
        s += line(x0 - 6, y0 + 6, x0 + 6, y0 - 6, 'dt') + line(x1 - 6, y1 + 6, x1 + 6, y1 - 6, 'dt')
        s += text((x0 + x1) / 2, y0 - 7 + off, t, 'dimt')
    else:
        s += line(x0 - 6, y0 + 6, x0 + 6, y0 - 6, 'dt') + line(x1 - 6, y1 + 6, x1 + 6, y1 - 6, 'dt')
        cx, cy = x0 - 8 + off, (y0 + y1) / 2
        s += f'<text x="{f(cx)}" y="{f(cy)}" class="dimt" transform="rotate(-90 {f(cx)} {f(cy)})">{t}</text>'
    return s


# ---------------------------------------------------------------- the survey sheet's own dimensions (optional)
SURVEY_PDF = apartment.SURVEY['pdf']
_SURVEY = None

def survey_dims():
    """Every dimension on the survey sheet (survey.pdf in apartment.json, if given), converted to plan cm, using the
    sheet's scale, origin and crop. Thin strokes (0.28 pt) are dimension lines, 0.71 pt strokes the ticks."""
    global _SURVEY
    if _SURVEY is not None:
        return _SURVEY
    if not SURVEY_PDF:                               # an imported apartment: its dimensions are 'dim' elements instead
        _SURVEY = ''
        return _SURVEY
    import re
    try:
        import pymupdf
    except ImportError:
        _SURVEY = ''
        return _SURVEY
    k = apartment.SURVEY['scale']
    ox, oy = apartment.SURVEY['origin']
    X = lambda x: (x - ox) * k
    Y = lambda y: (y - oy) * k
    X0, Y0, X1, Y1 = apartment.SURVEY['crop']
    page = pymupdf.open(SURVEY_PDF)[0]
    lines, ticks, texts = [], [], []
    # room tags (plain integers) and door/window tags (D01, W02...) with their boxes and leaders are not dimensions
    tagboxes = []
    for blk in page.get_text('dict')['blocks']:
        for ln in blk.get('lines', []):
            for sp in ln['spans']:
                t = sp['text'].strip(); bb = sp['bbox']
                if re.fullmatch(r'\d{1,2}|[DW]\d\d', t):
                    cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
                    tagboxes.append((cx - 26, cy - 10, cx + 26, cy + 10))
    in_tag = lambda x, y: any(t0 <= x <= t2 and t1 <= y <= t3 for t0, t1, t2, t3 in tagboxes)
    for g in page.get_drawings():
        if g['type'] != 's':
            continue
        r = g['rect']
        if r.x0 < X0 or r.x1 > X1 or r.y0 < Y0 or r.y1 > Y1:
            continue
        w = round(g.get('width') or 0, 2)
        items = [it for it in g['items'] if it[0] == 'l']
        if w == 0.28:
            if len(g['items']) >= 4 and r.width < 60 and r.height < 25:
                continue                                      # room / door tags
            for _, a, b in items:
                if in_tag(a.x, a.y) or in_tag(b.x, b.y):
                    continue
                if abs(a.x - b.x) < 0.05 or abs(a.y - b.y) < 0.05:
                    if max(abs(a.x - b.x), abs(a.y - b.y)) > 1.2:
                        lines.append((X(a.x), Y(a.y), X(b.x), Y(b.y)))
        elif w == 0.71:
            for _, a, b in items:
                ticks.append((X(a.x), Y(a.y), X(b.x), Y(b.y)))
    for blk in page.get_text('dict')['blocks']:
        for ln in blk.get('lines', []):
            for sp in ln['spans']:
                t = sp['text'].strip(); bb = sp['bbox']
                if re.fullmatch(r'\d+\.\d+', t) and X0 < bb[0] < X1 and Y0 < bb[1] < Y1:
                    cx, cy = X((bb[0] + bb[2]) / 2), Y((bb[1] + bb[3]) / 2)
                    vertical = abs(ln['dir'][1]) > 0.5
                    texts.append((cx, cy, t[:-2] if t.endswith('.0') else t, vertical))
    out = ['<g class="survey">']
    out += [f'<line x1="{f(a)}" y1="{f(b)}" x2="{f(c)}" y2="{f(d)}" class="sdl"/>' for a, b, c, d in lines]
    out += [f'<line x1="{f(a)}" y1="{f(b)}" x2="{f(c)}" y2="{f(d)}" class="sdt"/>' for a, b, c, d in ticks]
    for cx, cy, t, v in texts:
        tr = f' transform="rotate(-90 {f(cx)} {f(cy)})"' if v else ''
        out.append(f'<text x="{f(cx)}" y="{f(cy + 4)}" class="sdtext"{tr}>{t}</text>')
    out.append('</g>')
    _SURVEY = ''.join(out)
    return _SURVEY


# ---------------------------------------------------------------- the plan
GARDEN = apartment.GARDEN
COLUMNS = apartment.COLUMNS


def garden_layer():
    if not GARDEN:
        return ''
    pts = apartment.garden_points()
    area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2e4
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    return (f'<path d="{GARDEN}" class="garden"/>'
            f'<g class="glabels">{text(cx, cy, "GARDEN", "gl")}{text(cx, cy + 32, f"{area:.0f} m²", "ga")}</g>')


def draw(e):
    """One element of the surveyed plan (apartment.json), drawn with the same helpers the design layouts use."""
    k = e['k']
    if k == 'group':
        return f'<g class="{e["cls"]}">'
    if k == 'end':
        return '</g>'
    if k == 'zone':
        return rect(*e['box'], 'z ' + e['use'])
    if k == 'wall':
        return wall(*e['box'], e.get('openings', ()), e.get('cls', 'wall'))
    if k == 'column':
        return rect(*e['box'], 'col')
    if k == 'window':
        return window(*e['box'])
    if k == 'slider':
        return slider(*e['box'], e.get('panels', 2))
    if k == 'sill':
        return rect(*e['box'], 'sillg' if e.get('glazed') else 'sill')
    if k == 'shutters':                              # exterior roller shutters: a dashed line just outside each opening
        s = ''
        for o in openings.OPENINGS:
            fx0, fy0, fx1, fy1 = openings.exterior_face(o)
            nx, ny = o[5]
            s += line(fx0 + nx * 8, fy0 + ny * 8, fx1 + nx * 8, fy1 + ny * 8, 'shut')
        return s
    if k == 'door':
        return door(*e['hinge'], *e['leaf'], *e['end'], e.get('cls', 'door'))
    if k == 'room':
        return room(*e['label'], e['name'], e.get('rect'))
    if k == 'text':
        return text(*e['at'], e['text'], e.get('cls', ''))
    if k == 'line':
        return line(*e['from'], *e['to'], e.get('cls', ''))
    if k == 'survey_dims':
        return survey_dims()
    if k == 'dim':                                   # a dimension read from the drawing (dxf_import.py)
        return dim(*e['from'], *e['to'], e['text'], e.get('off', 0))
    raise ValueError('unknown plan element: ' + k)


def as_built():
    """The apartment, drawn straight from apartment.json."""
    return ''.join(draw(e) for e in apartment.PLAN)


# ---------------------------------------------------------------- pieces placed in the 3D (furnish.json)
# the furniture catalogue: the project's own (tools/catalogue.json) if it has one, else the engine's
_ENGINE = os.path.dirname(os.path.abspath(__import__('sys')._getframe().f_code.co_filename))
_CAT = next(p for p in (os.path.join(HERE, 'catalogue.json'), os.path.join(_ENGINE, 'catalogue.json')) if os.path.exists(p))
CATALOGUE = {p['t']: p for g in json.load(open(_CAT)) for p in g['pieces']}


def placed_symbol(t, w, d, c=None):
    """One catalogue piece centred on (0, 0), its back towards -y: the same symbol the viewer's 2D plan draws (fSym)."""
    c = c or CATALOGUE.get(t) or {}
    m, y, h = c.get('m', 'box'), c.get('y', 0), c.get('h', 0)
    hw, hd, hi = w / 2, d / 2, c.get('y', 0) >= 90
    o = []
    cls = {'pf': 'fur', 'pfl': 'furl', 'pfd': 'furd', 'pfs': 'pil', 'pfr': 'rug'}
    def k(c_):
        if c_ == 'pfh':
            return 'class="furl" style="stroke-dasharray:6 4"'
        if c_ == 'pfg':
            return 'class="furl" style="fill:#5E7F4A33;stroke:#5E7F4A"'
        return f'class="{cls[c_]}"'
    def R(x0, y0, x1, y1, c_, rx=0):
        o.append(f'<rect x="{f(x0)}" y="{f(y0)}" width="{f(x1-x0)}" height="{f(y1-y0)}"' + (f' rx="{f(rx)}"' if rx else '') + f' {k(c_)}/>')
    def C(x, y_, r, c_):
        o.append(f'<circle cx="{f(x)}" cy="{f(y_)}" r="{f(r)}" {k(c_)}/>')
    def E(x, y_, rx, ry, c_):
        o.append(f'<ellipse cx="{f(x)}" cy="{f(y_)}" rx="{f(rx)}" ry="{f(ry)}" {k(c_)}/>')
    def Ln(x1, y1, x2, y2, c_='pfl'):
        o.append(f'<line x1="{f(x1)}" y1="{f(y1)}" x2="{f(x2)}" y2="{f(y2)}" {k(c_)}/>')
    def X():
        Ln(-hw, -hd, hw, hd); Ln(-hw, hd, hw, -hd)
    B = 'pfh' if hi else 'pf'
    if m == 'sofa':
        o.append(f'<rect x="{f(-hw)}" y="{f(-hd)}" width="{f(w)}" height="{f(d)}" rx="4" class="sofa"/>')
        R(-hw, -hd, hw, -hd + 18, 'pfl', 3); R(-hw, -hd + 18, -hw + 16, hd, 'pfl', 3); R(hw - 16, -hd + 18, hw, hd, 'pfl', 3)
    elif m == 'corner':
        o.append(f'<path d="M{f(-hw)} {f(-hd)} H{f(hw)} V{f(-hd + 95)} H{f(-hw + 95)} V{f(hd)} H{f(-hw)} Z" class="sofa"/>')
        R(-hw, -hd, hw, -hd + 18, 'pfl', 3); R(-hw, -hd + 18, -hw + 18, hd, 'pfl', 3)
    elif m in ('pouf', 'lounger'):
        R(-hw, -hd, hw, hd, B, min(8, hw / 3))
        if m == 'lounger':
            Ln(-hw + 55, -hd, -hw + 55, hd)
    elif m in ('low', 'screen'):
        R(-hw, -hd, hw, hd, B, 1.5)
        if m == 'low':
            Ln(-hw, -hd + 4, hw, -hd + 4)
    elif m in ('tall', 'wallc'):
        R(-hw, -hd, hw, hd, B, 1); Ln(-hw + 3, 0, hw - 3, 0, 'pfh' if hi else 'pfl')
        if m == 'tall' and d >= 50:
            hx = -hw + 12
            while hx < hw - 6:
                Ln(hx - 3, -6, hx + 3, 6); hx += 14
    elif m == 'open':
        R(-hw, -hd, hw, hd, B, 1); Ln(-hw, -hd + 2, hw, -hd + 2)
        n = max(1, round(w / 90))
        for u in range(1, n):
            Ln(-hw + u * w / n, -hd, -hw + u * w / n, hd)
    elif m in ('table', 'island'):
        R(-hw, -hd, hw, hd, B, 3)
        if m == 'island':
            Ln(-hw, hd - 25, hw, hd - 25, 'pfh')
    elif m == 'deskL':
        o.append(f'<path d="M{f(-hw)} {f(-hd)} H{f(hw)} V{f(-hd + 70)} H{f(-hw + 70)} V{f(hd)} H{f(-hw)} Z" class="fur"/>')
    elif m in ('tableR', 'stool'):
        E(0, 0, hw, hd, B)
    elif m == 'chair':
        R(-hw, -hd, hw, hd, B, 6); R(-hw, -hd, hw, -hd + 7, 'pfd', 2)
    elif m in ('bed', 'bunk'):
        nb = 2 if w >= 150 else 1
        pw = (w - 30) / 2 if nb == 2 else w - 30
        R(-hw, -hd, hw, hd, B, 4); R(-hw, -hd, hw, -hd + 8, 'pfd')
        for i in range(nb):
            cx = ((1 if i else -1) * (pw / 2 + 5)) if nb == 2 else 0
            R(cx - pw / 2, -hd + 16, cx + pw / 2, -hd + 56, 'pfs', 4)
        Ln(-hw, -hd + d * .45, hw, -hd + d * .45)
        if m == 'bunk':
            Ln(hw - 6, hd - 50, hw - 6, hd - 10, 'pfd')
    elif m == 'cot':
        R(-hw, -hd, hw, hd, B, 4); R(-hw + 6, -hd + 6, hw - 6, hd - 6, 'pfl', 3)
    elif m == 'rug':
        R(-hw, -hd, hw, hd, 'pfr', 4)
    elif m == 'rugR':
        E(0, 0, hw, hd, 'pfr')
    elif m in ('flamp', 'coat'):
        C(0, 0, hw * .5 + 4, 'pf'); C(0, 0, 3, 'pfd')
    elif m == 'pendant':
        C(0, 0, hw, 'pfh'); Ln(-hw * .6, 0, hw * .6, 0, 'pfh'); Ln(0, -hw * .6, 0, hw * .6, 'pfh')
    elif m == 'fan':
        C(0, 0, hw, 'pfh'); C(0, 0, 9, 'pfh')
        for fb in range(3):
            a = fb * 2.094
            Ln(math.cos(a) * 10, math.sin(a) * 10, math.cos(a) * (hw - 3), math.sin(a) * (hw - 3), 'pfh')
    elif m == 'tent':
        R(-hw, -hd, hw, hd, B); X()
    elif m in ('mirror', 'art', 'rail', 'ac'):
        R(-hw, -hd, hw, hd, B, hd if t.endswith('R') else 0)
    elif m in ('base', 'drawers'):
        R(-hw, -hd, hw, hd, B); Ln(-hw, hd - 3, hw, hd - 3)
    elif m == 'sink':
        R(-hw, -hd, hw, hd, B)
        nbw = 2 if w >= 100 else 1
        bw = (w - 22) / 2 if nbw == 2 else min(w - 20, 60)
        for bi in range(nbw):
            bx = ((1 if bi else -1) * (bw / 2 + 3)) if nbw == 2 else 0
            R(bx - bw / 2, -hd + 12, bx + bw / 2, hd - 6, 'pfs', 5); C(bx, 4, 2.5, 'pfl')
    elif m == 'hob':
        R(-hw, -hd, hw, hd, B)
        nr = 5 if w >= 90 else 4
        for hr in range(nr):
            if nr == 5 and hr == 4:
                C(0, 2, 10, 'pfl')
                continue
            C((1 if hr % 2 else -1) * (w / 4.6), (-1 if hr < 2 else 1) * 11 + 2, 7, 'pfl')
    elif m in ('dw', 'fridge', 'ovens', 'hood', 'bbq'):
        R(-hw, -hd, hw, hd, 'pfh' if m == 'hood' else B); X()
    elif m in ('washer', 'acout'):
        R(-hw, -hd, hw, hd, B, 2); C(0, 0 if m == 'acout' else 3, min(hw, hd) * .62, 'pfl')
    elif m == 'wc':
        wl = h <= 45
        if not wl:
            R(-hw, -hd, hw, -hd + 18, B, 2)
        else:
            R(-hw * .8, -hd, hw * .8, -hd + 6, B, 1)
        by = -hd + 6 if wl else -hd + 18
        E(0, (by + hd) / 2, hw - (0 if wl else 3), (hd - by) / 2, 'pf'); E(0, (by + hd) / 2 + 3, hw - 9, (hd - by) / 2 - 8, 'pfs')
    elif m == 'bidet':
        E(0, 0, hw, hd, 'pf'); E(0, 2, hw - 8, hd - 9, 'pfs')
    elif m in ('vanity', 'basin'):
        R(-hw, -hd, hw, hd, B, 2)
        nt = 2 if w >= 110 else 1
        for vi in range(nt):
            vx = ((1 if vi else -1) * w / 4) if nt == 2 else 0
            E(vx, 3, min(22, w / nt / 2 - 6), hd - 9, 'pfs')
    elif m == 'shower':
        R(-hw, -hd, hw, hd, B); X(); C(0, 0, 4, 'pfl')
    elif m == 'bath':
        R(-hw, -hd, hw, hd, B, 6); R(-hw + 7, -hd + 7, hw - 7, hd - 7, 'pfs', min(18, hd - 7)); C(-hw + 16, 0, 2.5, 'pfl')
    elif m == 'heater':
        C(0, 0, hw, B)
    elif m == 'rack':
        R(-hw, -hd, hw, hd, B)
        rz = -hd + 8
        while rz < hd:
            Ln(-hw, rz, hw, rz); rz += 8
    elif m == 'parasol':
        C(0, 0, hw, 'pfh')
        for pa in range(4):
            a = pa * math.pi / 4
            Ln(-math.cos(a) * hw, -math.sin(a) * hw, math.cos(a) * hw, math.sin(a) * hw, 'pfh')
        R(-22, -22, 22, 22, 'pf')
    elif m == 'planter':
        R(-hw, -hd, hw, hd, B, 2)
        pi = -hw + hd
        while pi < hw:
            C(pi, 0, hd * .7, 'pfg'); pi += d
    elif m in ('plant', 'tree'):
        C(0, 0, hw, 'pfg'); C(0, 0, hw * .5, 'pf')
        for lk in range(8):
            la = lk * math.pi / 4
            Ln(math.cos(la) * hw * .5, math.sin(la) * hw * .5, math.cos(la) * hw * .95, math.sin(la) * hw * .95)
    else:
        R(-hw, -hd, hw, hd, B, 2)
    return ''.join(o)

def placed_furniture(layout):
    fj = os.path.join(ROOT, 'furnish.json')
    pieces = (json.load(open(fj)).get(layout) or {}).get('pieces', []) if os.path.exists(fj) else []
    s = ''
    for p in pieces:
        c = CATALOGUE.get(p.get('t'))
        if not c:
            continue
        w, d = p.get('w') or c['w'], p.get('d') or c['d']
        s += (f'<g class="loose placed" transform="translate({f(p["x"])} {f(p["y"])}) rotate({f(p.get("r", 0))})">'
              f'<title>{c["name"]} · {f(w)} × {f(d)} cm</title>{placed_symbol(p["t"], w, d)}</g>')
    return f'<g class="furn">{s}</g>' if s else ''

def with_placed(body, layout):
    """The placed pieces go under the room names, so the names stay readable."""
    pf = placed_furniture(layout)
    i = body.find('<g class="labels">')
    return body[:i] + pf + body[i:] if i >= 0 else body + pf


def svg(body):
    x0, y0, x1, y1 = apartment.extent(90)
    W, H = x1 - x0, y1 - y0 + 140
    a = math.radians(180 - sunpath.FACING)
    nx, ny = x1 - 70, y1 + 50
    return (f'<svg class="plan" viewBox="{f(x0)} {f(y0)} {f(W)} {f(H)}" role="img" aria-label="Floor plan of {htmlmod.escape(apartment.NAME)}" '
            f'xmlns="http://www.w3.org/2000/svg">{garden_layer()}{body}'
            f'<g class="north" transform="translate({f(nx)} {f(ny)})"><circle r="34" class="nc"/>'
            f'<path d="M0 30 L-13 -8 L0 0 L13 -8 Z" class="na" transform="rotate({180 - sunpath.FACING})"/>'
            f'<text x="{-50 * math.sin(a):.0f}" y="{50 * math.cos(a) + 8:.0f}" class="nt">N</text></g>'
            f'<g class="scale" transform="translate({f(x0 + 40)} {f(y1 + 60)})">'
            f'<rect width="100" height="10" class="sb1"/><rect x="100" width="100" height="10" class="sb2"/>'
            f'<rect x="200" width="300" height="10" class="sb1"/>'
            f'<text x="0" y="-8" class="st">0</text><text x="100" y="-8" class="st">1</text>'
            f'<text x="200" y="-8" class="st">2</text><text x="500" y="-8" class="st">5 m</text></g>'
            f'</svg>')


def rooms_table():
    rows = []
    for e in apartment.PLAN:
        if e['k'] == 'room' and e.get('rect'):
            x0, y0, x1, y1 = e['rect']
            rows.append(f'<tr><td>{htmlmod.escape(e["name"])}</td><td>{(x1 - x0) / 100:.2f} × {(y1 - y0) / 100:.2f} m</td>'
                        f'<td>{(x1 - x0) * (y1 - y0) / 1e4:.1f} m²</td></tr>')
    return ''.join(rows)


def openings_table():
    hours = openings.sun_hours()
    rows = []
    for o in openings.OPENINGS:
        h = hours[o[0]]
        b = o[2]
        w = max(b[2] - b[0], b[3] - b[1])
        rows.append(f'<tr><td>{o[0]}</td><td>{htmlmod.escape(o[1] or "")}</td><td>{w / 100:.2f} m</td>'
                    f'<td>{openings.facing(o[5])}° {sunpath.compass(openings.facing(o[5]))}</td>'
                    + ''.join(f'<td>{h[k][0]:.1f} h</td>' for k in ('jun', 'mar', 'dec')) + '</tr>')
    return ''.join(rows)


def page():
    tpl = open(os.path.join(HERE, 'plan_template.html')).read()
    sf = sunpath.facts()
    area = sum((e['rect'][2] - e['rect'][0]) * (e['rect'][3] - e['rect'][1]) for e in apartment.PLAN
               if e['k'] == 'room' and e.get('rect')) / 1e4
    html = (tpl.replace('{{NAME}}', htmlmod.escape(apartment.NAME))
               .replace('{{PLAN}}', svg(with_placed(as_built(), 'existing')))
               .replace('{{ROOMS}}', rooms_table())
               .replace('{{OPENINGS}}', openings_table())
               .replace('{{AREA}}', f'{area:.0f}')
               .replace('{{FACING}}', f'{round(sunpath.FACING)}° {sunpath.compass(sunpath.FACING)}')
               .replace('{{SUNPATH}}', sunpath.svg()))
    html = re.sub(r'\{\{SUN\.(\w+)\.(\w+)\}\}', lambda m: str(sf[m.group(1)][m.group(2)]), html)
    return html


if __name__ == '__main__':
    import plan_lock
    plan_lock.guard()        # the plan's measurements must match plan-lock.json, or nothing is built
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    h = page()
    open(OUT, 'w').write(h)
    print('wrote', os.path.relpath(OUT, ROOT), len(h))
