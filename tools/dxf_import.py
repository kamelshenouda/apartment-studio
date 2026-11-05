#!/usr/bin/env python3
"""Read an apartment's as-built plan from an AutoCAD drawing (DWG or DXF) and write a draft apartment.json, with a
check page.

A DWG is converted with LibreDWG's dwg2dxf (install_libredwg.sh builds it once); AutoCAD is not needed. A DXF saved
from AutoCAD works as it is. The drawing should hold the plan in model space; when it holds the plan more than
once, the copy with the room names is read. Doors and windows drawn as blocks named "...Door..." or "...Window..."
(Revit's opening families, for one) are read from the block's outline, with their tags (D01, W03) when nearby. Layers are recognised by name (case does not matter; --layers overrides):

  walls      WALL, A-WALL, MUR ...          closed polylines or hatches (single lines cannot be read as walls)
  columns    COL, COLS, COLUMN, S-COLS ...  closed polylines or hatches
  doors      DOOR, A-DOOR ...               a swing arc, ideally with its leaf line from the hinge
  glazing    GLAZ, WIN, WINDOW, A-GLAZ ...  each window or glazed door as a closed frame (panes inside are counted)
  rooms      AREA-IDEN, ROOM, NAME ...      the room names as text, placed inside each room
  dims       DIM, A-ANNO-DIMS ...           linear dimensions
  site       SITE, GARDEN, L-SITE ...       a closed outline of the garden or plot (optional)

Everything else (furniture, titles, hatching patterns, stray lines) is left out and listed in the report.

What the drawing cannot say, the draft assumes and says so: the units if the file does not state them, window sills
and heights (100 and 120 cm), door heads (230 cm), the ceiling (280 cm), and the site's position and orientation
(--lat --lon --facing). The owner checks the draft on check.html before it becomes the apartment and is locked.

  python3 tools/dxf_import.py plan.dxf OUTDIR [--units mm|cm|m|in] [--lat .. --lon .. --facing ..]
"""
import argparse, json, math, os, re, string, sys
import numpy as np
from scipy import ndimage
from PIL import Image, ImageDraw
import ezdxf

HERE = os.path.dirname(os.path.abspath(__file__))
LAYERS = {
    'walls': r'(^|[-_ ])(wall+s?|mur|murs)($|[-_ ])|a-wall',              # 'walll' too: a typo in a real drawing
    'columns': r'(^|[-_ ])(col|cols|column|columns|pillar|struct)($|[-_ ])',
    'doors': r'(^|[-_ ])(door|doors|porte)($|[-_ ])',
    'glazing': r'(^|[-_ ])(glaz|glazing|win|window|windows|fenetre)($|[-_ ])',
    'rooms': r'area-iden|(^|[-_ ])(room|rooms|name|names|space)($|[-_ ])',
    'dims': r'(^|[-_ ])(dim|dims|dimension|dimensions)($|[-_ ])',
    'site': r'(^|[-_ ])(site|garden|plot|boundary)($|[-_ ])',
}
UNITS = {1: ('in', 2.54), 2: ('ft', 30.48), 4: ('mm', 0.1), 5: ('cm', 1.0), 6: ('m', 100.0)}
USE = [(r'bed|master|kid|nanny|maid|dressing|office|study', 'pri'), (r'bath|wc|toilet|shower|powder', 'wetz'),
       (r'kitchen|laundry|utility|store|pantry|service', 'ser'), (r'corridor|hall|lobby|foyer|entr|passage', 'cir'),
       (r'living|reception|dining|family|salon|majlis|lounge', 'pub')]


def dwg_to_dxf(path, workdir):
    """A DWG converted to DXF with LibreDWG's dwg2dxf (see install_libredwg.sh); AutoCAD is not needed."""
    import shutil, subprocess
    exe = os.environ.get('DWG2DXF') or shutil.which('dwg2dxf') or os.path.expanduser('~/.local/libredwg/bin/dwg2dxf')
    if not os.path.exists(exe):
        raise SystemExit('Reading a DWG needs LibreDWG: run tools/install_libredwg.sh once (it builds dwg2dxf '
                         'into ~/.local/libredwg), or save the drawing as DXF from AutoCAD.')
    os.makedirs(workdir, exist_ok=True)
    out = os.path.join(workdir, os.path.splitext(os.path.basename(path))[0] + '.dxf')
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(os.path.dirname(os.path.dirname(exe)), 'lib') + ':' + os.environ.get('LD_LIBRARY_PATH', ''))
    r = subprocess.run([exe, '-y', '-o', out, path], capture_output=True, text=True, env=env)
    if not os.path.exists(out):
        raise SystemExit('dwg2dxf could not convert the drawing:\n' + r.stderr[-1500:])
    return out


OPENING_BLOCK = r'door|window|opening|porte|fenetre'
TAG = r'^[DW]-?\d{1,3}[A-Z]?$'


def layer_name(layer):
    """A layer's own name: a referenced drawing bound into this one prefixes its layers ('XREF-WIN-04$0$A-GLAZ',
    nested 'A$0$B$0$A-GLAZ'), and an attached one 'XREF|A-GLAZ'."""
    return re.split(r'\$\d+\$|\|', layer)[-1]


def classify(layer, mapping):
    layer = layer_name(layer)
    labels = re.search(r'iden|tag|anno|note|text|ttlb', layer, re.I)    # tags, notes and titles on a door layer are not doors
    grid = re.search(r'grid|axis|axes', layer, re.I)                     # setting-out grid lines are not columns
    for cat, pat in mapping.items():
        if labels and cat not in ('rooms', 'dims'):
            continue
        if grid and cat == 'columns':
            continue
        if re.search(pat, layer, re.I):
            return cat
    return None


def entities(msp):
    """Model-space entities with block references opened up; each keeps its own layer, or the block's when on 0.
    Door and window blocks are read separately (import_dxf)."""
    for e in msp:
        if e.dxftype() == 'INSERT' and re.search(OPENING_BLOCK, e.dxf.name, re.I) and not re.search(r'tag|iden', e.dxf.name, re.I):
            continue
        if e.dxftype() == 'INSERT':
            try:
                for v in e.virtual_entities():
                    if v.dxf.layer == '0':
                        v.dxf.layer = e.dxf.layer
                    yield v
            except Exception:
                continue
        else:
            yield e


def polygons(e):
    """Closed outlines of an entity, as lists of (x, y) in drawing units."""
    t = e.dxftype()
    if t == 'LWPOLYLINE' and (e.closed or len(e) > 2 and tuple(e[0][:2]) == tuple(e[-1][:2])):
        return [[(p[0], p[1]) for p in e.get_points('xy')]]
    if t == 'POLYLINE' and e.is_closed:
        return [[(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]]
    if t in ('SOLID', 'TRACE', '3DFACE'):
        pts = [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx3, e.dxf.vtx2] if t != '3DFACE' else [e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx2, e.dxf.vtx3]
        return [[(p.x, p.y) for p in pts]]
    if t == 'HATCH':                                  # one group: its paths combine even-odd (holes stay holes)
        out = []
        for path in e.paths:
            if hasattr(path, 'vertices'):
                out.append([(v[0], v[1]) for v in path.vertices])
            else:
                pts = []
                for edge in path.edges:
                    if hasattr(edge, 'start'):
                        pts.append((edge.start[0], edge.start[1]))
                if len(pts) > 2:
                    out.append(pts)
        return [('xor', out)] if len(out) > 1 else out
    return []


def line_walls(ents, k):
    """Walls drawn as two parallel lines (LINEs, and the segments of open polylines), as many offices and Revit
    exports draw them: each line is paired with its nearest parallel neighbour 4 to 61 cm away and the band between
    them becomes wall, as four-cornered outlines in drawing units. Where one line runs on past the other (a corner, a
    T), the band runs on by the wall's thickness so the corner fills; where both stop (an opening), it stops."""
    segs = []
    for e in ents:
        t = e.dxftype()
        if t == 'LINE':
            segs.append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
        elif t in ('LWPOLYLINE', 'POLYLINE') and not polygons(e):
            pts = [(q[0], q[1]) for q in e.get_points('xy')] if t == 'LWPOLYLINE' else [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            segs += list(zip(pts, pts[1:]))
    lo, hi, tol = 4 / k, 61 / k, math.radians(.6)
    L = []
    for a, b in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        if math.hypot(dx, dy) * k < 8:
            continue
        th = math.atan2(dy, dx) % math.pi
        L.append((th, a, b))
    L.sort()
    def partners(i):
        """Parallel lines 4 to 61 cm from line i and running alongside it: [(|d|, d, from, to)] in i's own frame."""
        th, a, b = L[i]
        ux, uy = math.cos(th), math.sin(th); nx, ny = -uy, ux
        d0 = a[0] * nx + a[1] * ny
        s0, s1 = sorted((a[0] * ux + a[1] * uy, b[0] * ux + b[1] * uy))
        cands = []
        for j, (th2, a2, b2) in enumerate(L):
            if j == i or min(abs(th2 - th), math.pi - abs(th2 - th)) > tol:
                continue
            dd = ((a2[0] + b2[0]) / 2) * nx + ((a2[1] + b2[1]) / 2) * ny - d0
            if not lo <= abs(dd) <= hi:
                continue
            t0, t1 = sorted((a2[0] * ux + a2[1] * uy, b2[0] * ux + b2[1] * uy))
            if min(s1, t1) - max(s0, t0) > lo:
                cands.append((abs(dd), dd, t0, t1, j))
        return cands
    P_ = [partners(i) for i in range(len(L))]
    # a run of evenly spaced parallel lines (stair treads, a hatch, louvres) is not walls: a line with neighbours
    # on both sides is part of a run, and so are the run's two end lines next to it
    run = {i for i, c in enumerate(P_) if any(d > 0 for _, d, *_ in c) and any(d < 0 for _, d, *_ in c)}
    run |= {i for i, c in enumerate(P_) if c and min(c)[4] in run}
    out = []
    for i, (th, a, b) in enumerate(L):
        if i in run:
            continue
        ux, uy = math.cos(th), math.sin(th); nx, ny = -uy, ux
        d0 = a[0] * nx + a[1] * ny
        s0, s1 = sorted((a[0] * ux + a[1] * uy, b[0] * ux + b[1] * uy))
        claimed = {1: [], -1: []}                     # per side: the stretches a nearer partner already pairs
        for ad, dd, t0, t1, j in sorted(P_[i]):
            if j in run:
                continue
            o0, o1 = max(s0, t0), min(s1, t1)
            side = 1 if dd > 0 else -1
            free = [(o0, o1)]
            for c0, c1 in claimed[side]:
                free = [q for f0, f1 in free for q in ((f0, min(f1, c0)), (max(f0, c1), f1)) if q[1] - q[0] > lo]
            for f0, f1 in free:
                e0 = max(min(s0, t0), f0 - ad) if f0 <= o0 + 1e-9 else f0          # run on into a corner
                e1 = min(max(s1, t1), f1 + ad) if f1 >= o1 - 1e-9 else f1
                P = lambda sv, dv: (sv * ux + dv * nx, sv * uy + dv * ny)
                out.append([P(e0, d0), P(e1, d0), P(e1, d0 + dd), P(e0, d0 + dd)])
            claimed[side].append((o0, o1))
    return out


def rects(mask):
    """A filled grid (1 cm cells) as rectangles: runs along x, merged downwards while they match."""
    out, open_ = [], {}
    h = mask.shape[0]
    for y in range(h + 1):
        runs = set()
        if y < h:
            row = np.concatenate(([0], mask[y].astype(np.int8), [0]))
            d = np.flatnonzero(np.diff(row))
            runs = {(int(a), int(b)) for a, b in zip(d[::2], d[1::2])}
        for k in list(open_):
            if k not in runs:
                out.append((k[0], open_.pop(k), k[1], y))
        for k in runs:
            open_.setdefault(k, y)
    return sorted(out, key=lambda r: (r[1], r[0]))


def run_at(mask, x, y, axis, reach=40):
    """The extent of filled cells through (x, y) across a wall: along y when axis is 'x', along x otherwise."""
    H, W = mask.shape
    x, y = int(round(x)), int(round(y))
    if not (0 <= x < W and 0 <= y < H):
        return None
    if axis == 'x':                    # wall runs along x: thickness along y
        col = mask[:, x]
        ys = [yy for yy in range(max(0, y - reach), min(H, y + reach)) if col[yy]]
        if not ys:
            return None
        # the run nearest to y
        best = min(ys, key=lambda yy: abs(yy - y)); a = b = best
        while a - 1 >= 0 and col[a - 1]:
            a -= 1
        while b + 1 < H and col[b + 1]:
            b += 1
        return a, b + 1
    row = mask[y, :]
    xs = [xx for xx in range(max(0, x - reach), min(W, x + reach)) if row[xx]]
    if not xs:
        return None
    best = min(xs, key=lambda xx: abs(xx - x)); a = b = best
    while a - 1 >= 0 and row[a - 1]:
        a -= 1
    while b + 1 < W and row[b + 1]:
        b += 1
    return a, b + 1


def rnd(v):
    """Plan cm, kept to a tenth of a millimetre (no rounding to whole centimetres)."""
    v = round(v, 2)
    return int(v) if v == int(v) else v


def import_dxf(path, units=None, layers=None, site=None, plan=None):
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    mapping = dict(LAYERS, **(layers or {}))
    report = {'source': os.path.basename(path), 'assumed': [], 'warnings': [], 'ignored': {}, 'layers': {}}
    code = doc.header.get('$INSUNITS', 0)
    if units:
        name, k = units, {'mm': .1, 'cm': 1., 'm': 100., 'in': 2.54}[units]
    elif code in UNITS:
        name, k = UNITS[code]
    else:
        name, k = 'mm', .1
        report['assumed'].append('The drawing does not state its units; millimetres assumed (use --units to change).')
    report['units'] = name
    got = {c: [] for c in mapping}
    got['blocks'] = []; got['tags'] = []
    for e in msp:                                     # door and window blocks (Revit and many offices draw them so)
        if e.dxftype() == 'INSERT' and re.search(OPENING_BLOCK, e.dxf.name, re.I) and not re.search(r'tag|iden', e.dxf.name, re.I):
            try:
                v = list(e.virtual_entities())
            except Exception:
                continue
            kind = 'window' if re.search(r'window|fenetre', e.dxf.name, re.I) else 'door'
            got['blocks'].append((kind, e.dxf.name, v))
    for e in msp:                                     # door and window tags: W01, D06 ...
        if e.dxftype() in ('TEXT', 'MTEXT'):
            t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip()
            if re.fullmatch(TAG, t):
                got['tags'].append((t, e.dxf.insert))
    blocknames = {n for _, n, _ in got['blocks']}
    for e in entities(msp):
        if e.dxftype() == 'INSERT':
            continue
        cat = classify(e.dxf.layer, mapping)
        if cat is None:
            report['ignored'][e.dxf.layer] = report['ignored'].get(e.dxf.layer, 0) + 1
            continue
        report['layers'].setdefault(cat, set()).add(e.dxf.layer)
        got[cat].append(e)
    report['layers'] = {c: sorted(v) for c, v in report['layers'].items()}
    if not got['walls']:
        raise SystemExit('No wall layer found. Layers in the drawing: ' + ', '.join(sorted({e.dxf.layer for e in msp})) +
                         '. Name the walls layer WALL or A-WALL, or pass --layers \'{"walls":"<regex>"}\'.')

    # the frame: drawing units -> plan cm, y flipped (CAD y points up, the plan's y runs down the sheet)
    wall_polys = [p for e in got['walls'] for p in polygons(e)]
    # walls drawn as two parallel lines, when that is how the drawing draws them: a wall layer that is almost all open
    # lines (a drawing with hatched or outlined walls keeps those, and its lines are their edges)
    n_open = sum(1 for e in got['walls'] if e.dxftype() == 'LINE' or e.dxftype() in ('LWPOLYLINE', 'POLYLINE') and not polygons(e))
    lw = line_walls(got['walls'], k) if n_open and len(wall_polys) < .05 * n_open else []
    if lw:
        wall_polys += lw
        report['assumed'].append(f'{len(lw)} stretch(es) of wall were read from pairs of parallel lines 4 to 61 cm apart; '
                                 'check them against the red outlines on the plan.')
    col_polys = [p for e in got['columns'] for p in polygons(e)]
    site_polys = [p for e in got['site'] for p in polygons(e)]
    # a drawing may hold the plan more than once (a copy for another sheet): keep the copy with the room names
    pts_of = lambda g: g[1] if isinstance(g, tuple) else [g]
    def box(g):
        q = [x for p in pts_of(g) for x in p]
        return (min(a for a, _ in q), min(b for _, b in q), max(a for a, _ in q), max(b for _, b in q))
    boxes = [box(g) for g in wall_polys]
    groups, M = [], 300 / k                          # pieces within 3 m of each other belong to the same copy
    for b in boxes:
        hit = [g for g in groups if b[0] <= g[2] + M and b[2] >= g[0] - M and b[1] <= g[3] + M and b[3] >= g[1] - M]
        for g in hit:
            groups.remove(g)
            b = (min(b[0], g[0]), min(b[1], g[1]), max(b[2], g[2]), max(b[3], g[3]))
        groups.append(b)
    if len(groups) > 1:
        def names_in(g):
            n = 0
            for e in got['rooms']:
                if e.dxftype() in ('TEXT', 'MTEXT') and g[0] <= e.dxf.insert.x <= g[2] and g[1] <= e.dxf.insert.y <= g[3]:
                    n += 1
            return n
        # each copy's title, if the sheet gives one: the nearest 'Ground floor', 'First floor', 'Roof', 'Elevation'...
        TITLE = r'\b(ground|first|second|third|fourth|fifth|upper|lower|basement|roof|mezzanine|typical|attic)\b|\b(floor|level|plan|elevation|section)\b'
        titles = []
        for e in msp:
            if e.dxftype() in ('TEXT', 'MTEXT'):
                t = (e.plain_text() if e.dxftype() == 'MTEXT' else e.dxf.text).strip()
                if 2 < len(t) < 40 and re.search(TITLE, t, re.I):
                    titles.append((t, e.dxf.insert.x, e.dxf.insert.y))
        def title_of(g):
            m = 800 / k; best = None
            for t, x, y in titles:
                dx = max(g[0] - x, 0, x - g[2]); dy = max(g[1] - y, 0, y - g[3])
                if dx <= m and dy <= m and (best is None or dx + dy < best[0]):
                    best = (dx + dy, t)
            return best and ' '.join(best[1].split())
        named = [(g, title_of(g)) for g in groups]
        plans = [(g, t) for g, t in named if not (t and re.search(r'elevation|section', t, re.I))] or named
        if plan:
            pick = [q for q in plans if q[1] and plan.lower() in q[1].lower()] or \
                   ([plans[int(plan) - 1]] if str(plan).isdigit() and 0 < int(plan) <= len(plans) else [])
            if not pick:
                raise SystemExit(f'No plan called "{plan}" on this drawing. Its plans: ' + ', '.join(t or f'plan {i + 1} (no title)' for i, (_, t) in enumerate(plans)) + '.')
            keep = pick[0][0]
        else:
            keep = max(plans, key=lambda q: (names_in(q[0]), bool(q[1] and re.search(r'ground', q[1], re.I)), (q[0][2] - q[0][0]) * (q[0][3] - q[0][1])))[0]
        report['plans'] = [t or f'plan {i + 1} (no title)' for i, (_, t) in enumerate(plans)]
        report['plan'] = next(t or f'plan {i + 1} (no title)' for i, (g, t) in enumerate(plans) if g == keep)
        inside = lambda b, m=0: b[0] >= keep[0] - m and b[2] <= keep[2] + m and b[1] >= keep[1] - m and b[3] <= keep[3] + m
        wall_polys = [g for g in wall_polys if inside(box(g))]
        col_polys = [g for g in col_polys if inside(box(g), 5 / k)]
        site_polys = [g for g in site_polys if inside(box(g), 3000 / k)]
        def at(p):
            m = 400 / k
            return keep[0] - m <= p[0] <= keep[2] + m and keep[1] - m <= p[1] <= keep[3] + m
        got['rooms'] = [e for e in got['rooms'] if not hasattr(e.dxf, 'insert') or at(e.dxf.insert)]
        got['dims'] = [e for e in got['dims'] if e.dxftype() != 'DIMENSION' or at(e.dxf.defpoint)]
        got['doors'] = [e for e in got['doors'] if e.dxftype() != 'ARC' or at(e.dxf.center)]
        got['glazing'] = [e for e in got['glazing'] if all(at(q) for p in polygons(e) for q in pts_of(p)[0])]
        got['tags'] = [t for t in got['tags'] if at(t[1])]
        def bb(v):
            q = [(x.dxf.start.x, x.dxf.start.y) for x in v if x.dxftype() == 'LINE'] + [(x.dxf.end.x, x.dxf.end.y) for x in v if x.dxftype() == 'LINE']
            return q
        got['blocks'] = [b for b in got['blocks'] if bb(b[2]) and all(at(q) for q in bb(b[2]))]
        if len(plans) > 1 and any(t for _, t in plans):
            report['warnings'].append(f'The drawing holds {len(plans)} plans ({", ".join(report["plans"])}); {report["plan"]} was read. '
                                      'To read another, choose it (studio) or pass --plan with its name.')
        else:
            report['warnings'].append(f'The drawing holds the plan {len(groups)} times; the copy with the room names was read, the other(s) left out.')
    single = sum(1 for e in got['walls'] if e.dxftype() in ('LINE', 'ARC') or e.dxftype() == 'LWPOLYLINE' and not polygons(e))
    if single and not wall_polys:          # open lines that pair with nothing
        report['warnings'].append(f'{single} wall line(s) are open lines, not closed outlines or hatches, and were left out. '
                                  'Close each wall as a polyline or hatch it, then import again.')
    allpts = [q for g in wall_polys + col_polys + site_polys for p in pts_of(g) for q in p]
    if not allpts:
        raise SystemExit('The wall layer has no closed outlines or hatches to read.')
    minx = min(q[0] for q in allpts); maxy = max(q[1] for q in allpts)
    T = lambda x, y: ((x - minx) * k, (maxy - y) * k)
    pl = lambda poly: [T(*q) for q in poly]
    W = int(math.ceil(max(T(*q)[0] for q in allpts))) + 4
    H = int(math.ceil(max(T(*q)[1] for q in allpts))) + 4

    def raster(polys):
        im = Image.new('1', (W, H), 0); d = ImageDraw.Draw(im)
        for p in polys:
            if len(p) > 2:
                d.polygon([(round(x, 2), round(y, 2)) for x, y in pl(p)], fill=1)
        a = np.array(im, dtype=bool)
        # PIL fills the polygon including its far edges; trim the far edge so a 10 cm wall stays 10 cells
        return a

    # walls and columns, read on a 1 cm grid
    def fill(polys):
        m = np.zeros((H, W), bool)
        for g in polys:
            if isinstance(g, tuple):                  # a hatch with holes: its paths combine even-odd
                part = np.zeros((H, W), bool)
                for p in g[1]:
                    part ^= fill([p])
                m |= part
                continue
            p = g
            q = pl(p)
            xs = [a for a, _ in q]; ys = [b for _, b in q]
            orth = all(abs(q[i][0] - q[i - 1][0]) < .05 or abs(q[i][1] - q[i - 1][1]) < .05 for i in range(len(q)))
            if orth:                                  # exact for rectangles and other right-angled outlines
                im = Image.new('1', (W * 2, H * 2), 0)
                ImageDraw.Draw(im).polygon([(x * 2, y * 2) for x, y in q], fill=1)
                a = np.array(im, dtype=bool)[1::2, 1::2]     # sample cell centres
                m |= a
            else:
                fill.skew += 1
                im = Image.new('1', (W, H), 0); ImageDraw.Draw(im).polygon(q, fill=1); m |= np.array(im, dtype=bool)
        return m
    fill.skew = 0
    wmask = fill(wall_polys)
    cmask = fill(col_polys)
    # walls drawn only as lines (many partitions carry no hatch): close the lines into faces and keep the thin ones
    segs = []
    for e in got['walls']:
        t = e.dxftype()
        if t == 'LINE':
            segs.append((T(e.dxf.start.x, e.dxf.start.y), T(e.dxf.end.x, e.dxf.end.y)))
        elif t == 'LWPOLYLINE':
            q = [T(p[0], p[1]) for p in e.get_points('xy')]
            segs += list(zip(q, q[1:]))
    oboxes = []                                       # the door and window blocks close the wall outlines at each opening
    for _, _, v in got['blocks']:
        q = []
        for x in v:
            if x.dxftype() == 'LINE':
                a, b = T(x.dxf.start.x, x.dxf.start.y), T(x.dxf.end.x, x.dxf.end.y); segs.append((a, b)); q += [a, b]
        if q:
            oboxes.append((min(a for a, _ in q), min(b for _, b in q), max(a for a, _ in q), max(b for _, b in q)))
    for e in got['columns']:
        if e.dxftype() == 'LINE':
            segs.append((T(e.dxf.start.x, e.dxf.start.y), T(e.dxf.end.x, e.dxf.end.y)))
    if segs:
        from shapely.geometry import LineString, MultiLineString
        from shapely.ops import polygonize, unary_union
        net = unary_union(MultiLineString([[a, b] for a, b in segs if a != b]))
        faces, added = list(polygonize(net)), 0
        for f in faces:
            r = f.minimum_rotated_rectangle
            xs, ys = r.exterior.coords.xy
            sides = sorted({round(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]), 1) for i in range(4)})
            if f.area < 1 or sides[0] > 45:          # a room, not a wall (walls are 45 cm thick at most)
                continue
            c = f.representative_point()
            if any(b[0] - .5 <= c.x <= b[2] + .5 and b[1] - .5 <= c.y <= b[3] + .5 for b in oboxes):
                continue                              # a door or window opening, not a wall
            q = [(x, y) for x, y in zip(*f.exterior.coords.xy)]
            im = Image.new('1', (W * 2, H * 2), 0)
            ImageDraw.Draw(im).polygon([(x * 2, y * 2) for x, y in q], fill=1)
            a = np.array(im, dtype=bool)[1::2, 1::2] & ~cmask
            if (a & ~wmask).sum() > 0:
                added += 1
            wmask |= a
        if added:
            report['assumed'].append(f'{added} wall piece(s) were drawn only as outline lines and were closed into walls.')
    if fill.skew:
        report['warnings'].append(f'{fill.skew} outline(s) are not at right angles; they are read cell by cell and will show stepped edges.')
    columns = []
    for g in col_polys:
        q = [x for p in pts_of(g) for x in pl(p)]; xs = [a for a, _ in q]; ys = [b for _, b in q]
        columns.append([rnd(min(xs)), rnd(min(ys)), rnd(max(xs)), rnd(max(ys))])
    columns = [list(c) for c in sorted({tuple(c) for c in columns}, key=lambda c: (c[1], c[0]))]

    # glazing: closed frames; frames inside another frame are its panes
    frames = []
    for e in got['glazing']:
        for p in polygons(e):
            q = pl(p); xs = [a for a, _ in q]; ys = [b for _, b in q]
            frames.append((min(xs), min(ys), max(xs), max(ys)))
    frames = sorted(set(frames), key=lambda b: -(b[2] - b[0]) * (b[3] - b[1]))
    glaz = []
    for b in frames:
        host = next((g for g in glaz if b[0] >= g['box'][0] - .5 and b[2] <= g['box'][2] + .5 and b[1] >= g['box'][1] - .5 and b[3] <= g['box'][3] + .5), None)
        if host:
            host['panes'] += 1
        else:
            glaz.append({'box': b, 'panes': 0})
    # door and window blocks: each is the rectangle of its gap in the wall
    tags = [(t, T(p.x, p.y)) for t, p in got['tags']]
    def tag_for(b, letter):
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        c = [(math.hypot(x - cx, y - cy), t) for t, (x, y) in tags if t.upper().startswith(letter)]
        c = [x for x in c if x[0] <= 160]
        return min(c)[1] if c else None
    bdoors = []
    for kind, name, v in got['blocks']:
        q = [T(x.dxf.start.x, x.dxf.start.y) for x in v if x.dxftype() == 'LINE'] + [T(x.dxf.end.x, x.dxf.end.y) for x in v if x.dxftype() == 'LINE']
        if not q:
            continue
        b = (min(a for a, _ in q), min(c for _, c in q), max(a for a, _ in q), max(c for _, c in q))
        if any(abs(b[i] - x['box'][i]) < .5 for x in glaz + bdoors for i in range(4)) and any(
                all(abs(b[i] - x['box'][i]) < .5 for i in range(4)) for x in glaz + bdoors):
            continue                                  # the same opening twice
        if kind == 'window':
            glaz.append({'box': b, 'panes': 0, 'kind': 'window', 'tag': tag_for(b, 'W')})
        else:
            bdoors.append({'box': b, 'tag': tag_for(b, 'D'), 'name': name})
    if got['blocks']:
        report['assumed'].append(f'{len(bdoors)} door(s) and {sum(1 for g in glaz if g.get("kind") == "window")} window(s) were read '
                                 'from their opening blocks, which do not show which way a door swings.')
    if any(e.dxftype() == 'LINE' for e in got['glazing']) and not glaz:
        report['warnings'].append('The glazing layer has only lines; draw each window as a closed frame to be read.')

    # doors: a swing arc, and the leaf line from the hinge if there is one
    lines = [(T(e.dxf.start.x, e.dxf.start.y), T(e.dxf.end.x, e.dxf.end.y)) for e in got['doors'] if e.dxftype() == 'LINE']
    near = lambda a, b, tol=1.0: math.hypot(a[0] - b[0], a[1] - b[1]) <= tol
    doors = []
    for e in got['doors']:
        if e.dxftype() != 'ARC':
            continue
        c = e.dxf.center; r = e.dxf.radius
        h = T(c.x, c.y)
        ends = [T(c.x + r * math.cos(math.radians(a)), c.y + r * math.sin(math.radians(a))) for a in (e.dxf.start_angle, e.dxf.end_angle)]
        open_end = None
        for a, b in lines:
            for p, q in ((a, b), (b, a)):
                if near(p, h) and any(near(q, x) for x in ends):
                    open_end = next(x for x in ends if near(q, x))
        if open_end is None:                          # no leaf line: the closed end is the one meeting a jamb
            def jamb(x):
                dx, dy = x[0] - h[0], x[1] - h[1]; L = math.hypot(dx, dy) or 1
                px, py = int(round(x[0] + dx / L * 3)), int(round(x[1] + dy / L * 3))
                return 0 <= px < W and 0 <= py < H and wmask[py, px]
            open_end = ends[0] if jamb(ends[1]) else ends[1]
            report['assumed'].append(f'A door at ({rnd(h[0])}, {rnd(h[1])}) has no leaf line; its closed side was taken from the wall it meets.')
        shut = ends[1] if open_end is ends[0] else ends[0]
        # the closed end meets the far jamb: move it onto the wall face if the swing falls a little short or long
        dx, dy = shut[0] - h[0], shut[1] - h[1]; L = math.hypot(dx, dy) or 1; ux, uy = dx / L, dy / L
        best = None
        for t in [x / 2 for x in range(-6, 7)]:            # within 3 cm either way, in half-centimetre steps
            px, py = shut[0] + ux * t, shut[1] + uy * t
            cx, cy = int(math.floor(px + ux * .5)), int(math.floor(py + uy * .5))
            bx, by = int(math.floor(px - ux * .5)), int(math.floor(py - uy * .5))
            if 0 <= cx < W and 0 <= cy < H and 0 <= bx < W and 0 <= by < H and (wmask | cmask)[cy, cx] and not (wmask | cmask)[by, bx]:
                if best is None or abs(t) < abs(best):
                    best = t
        if best:
            shut = (shut[0] + ux * best, shut[1] + uy * best)
        doors.append({'hinge': h, 'leaf': open_end, 'end': shut})

    # each door and window leaves a gap in the wall: it becomes a wall with that opening, so the 3D puts a lintel over it
    gaps = []
    for d in doors:
        (hx, hy), (ex, ey) = d['hinge'], d['end']
        if abs(hy - ey) < .5:                        # closes along x: the wall's thickness is along y
            sgn = 1 if ex > hx else -1
            t = run_at(wmask, ex + sgn * 2, hy, 'x') or run_at(wmask, hx - sgn * 2, hy, 'x')
            if t:
                gaps.append({'box': [rnd(min(hx, ex)), rnd(t[0]), rnd(max(hx, ex)), rnd(t[1])], 'openings': [[rnd(min(hx, ex)), rnd(max(hx, ex))]]})
        elif abs(hx - ex) < .5:
            sgn = 1 if ey > hy else -1
            t = run_at(wmask, hx, ey + sgn * 2, 'y') or run_at(wmask, hx, hy - sgn * 2, 'y')
            if t:
                gaps.append({'box': [rnd(t[0]), rnd(min(hy, ey)), rnd(t[1]), rnd(max(hy, ey))], 'openings': [[rnd(min(hy, ey)), rnd(max(hy, ey))]]})
        else:
            report['warnings'].append(f'A door at ({rnd(hx)}, {rnd(hy)}) is not at a right angle to the plan and was drawn without its wall gap.')
    for g in glaz + bdoors:
        x0, y0, x1, y1 = g['box']
        horiz = (x1 - x0) >= (y1 - y0)
        gaps.append({'box': [rnd(x0), rnd(y0), rnd(x1), rnd(y1)], 'openings': [[rnd(x0), rnd(x1)] if horiz else [rnd(y0), rnd(y1)]][0:1]})

    # rooms: each name fills the space around it, up to the walls, columns, doors and windows
    block = wmask | cmask
    for g in gaps:
        x0, y0, x1, y1 = g['box']; block[int(y0):int(math.ceil(y1)), int(x0):int(math.ceil(x1))] = True
    block = ndimage.binary_closing(block, structure=np.ones((3, 3)), iterations=1) | block   # close cracks under 3 cm
    lab, _ = ndimage.label(~block)                     # every enclosed space, numbered
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    rooms = []
    for e in got['rooms']:
        if e.dxftype() not in ('TEXT', 'MTEXT'):
            continue
        if e.dxftype() == 'TEXT':
            name = e.dxf.text; ins = e.dxf.align_point if (e.dxf.halign or e.dxf.valign) else e.dxf.insert
        else:
            name = e.plain_text(); ins = e.dxf.insert
        name = re.sub(r'\s+', ' ', name).strip()
        if not name or re.fullmatch(r'[\d.,\s]+(m2|m²|sqm)?', name, re.I):
            continue
        x, y = T(ins.x, ins.y)
        nice = string.capwords(name) if name.isupper() else name
        rect = None
        xi, yi = int(x), int(y)
        if 0 <= xi < W and 0 <= yi < H and not block[yi, xi]:
            n = lab[yi, xi]
            ys, xs = np.nonzero(lab == n)
            if n not in edge:
                rect = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
            else:
                report['warnings'].append(f'"{nice}" is not closed off by walls, doors or windows; it has no size.')
        rooms.append({'name': nice, 'label': [rnd(x), rnd(y)], 'rect': rect, 'space': int(lab[yi, xi]) if 0 <= xi < W and 0 <= yi < H else 0})
    shared = {}
    for r in rooms:
        if r['rect']:
            shared.setdefault(r['space'], []).append(r['name'])
    for names in shared.values():
        if len(names) > 1:
            report['warnings'].append(' and '.join(names) + ' share one open space (no wall or door between them); '
                                      'each is given the size of the whole space. Say where the line between them is.')

    # exterior openings: the side of each window that the outside reaches
    outside = np.isin(lab, list(edge))               # the spaces the drawing's edge reaches
    out_at = lambda px, py: not (0 <= px < W and 0 <= py < H) or bool(outside[py, px])   # beyond the drawing is outside too

    def side_free(b, sgn):
        """The cell just outside one long face of an opening box."""
        x0, y0, x1, y1 = b; horiz = (x1 - x0) >= (y1 - y0); cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        return (int(cx), int((y1 + 4) if sgn > 0 else (y0 - 5))) if horiz else (int((x1 + 4) if sgn > 0 else (x0 - 5)), int(cy))

    def room_at(p):
        return next((r for r in rooms if r['rect'] and r['rect'][0] <= p[0] < r['rect'][2] and r['rect'][1] <= p[1] < r['rect'][3]), None)

    # block doors: a wide one to the outside is a glazed door; the others swing (the side and hinge are assumed)
    swung = 0
    for d in bdoors:
        x0, y0, x1, y1 = d['box']; horiz = (x1 - x0) >= (y1 - y0); L = (x1 - x0) if horiz else (y1 - y0)
        pa, pb = side_free(d['box'], -1), side_free(d['box'], 1)
        out = [out_at(*p) for p in (pa, pb)]
        if any(out) and L >= 120:
            glaz.append({'box': d['box'], 'panes': 0, 'kind': 'glazed door', 'tag': d['tag']})
            continue
        # swing into the bigger room (into the flat for an outside door), hinged at the lower end
        ra, rb = room_at(pa), room_at(pb)
        area = lambda r: (r['rect'][2] - r['rect'][0]) * (r['rect'][3] - r['rect'][1]) if r else -1
        sgn = -1 if (out[1] or (not out[0] and area(ra) >= area(rb))) else 1
        if horiz:
            yf = y0 if sgn < 0 else y1
            h, e = (x0, yf), (x1, yf); lf = (x0, yf + sgn * L)
        else:
            xf = x0 if sgn < 0 else x1
            h, e = (xf, y0), (xf, y1); lf = (xf + sgn * L, y0)
        doors.append({'hinge': h, 'leaf': lf, 'end': e}); swung += 1
    if swung:
        report['assumed'].append(f'{swung} door swing(s) are assumed: each opens into the bigger room, hinged at its left or top '
                                 'end. Click a door on the check page to turn it or move its hinge.')
    openings, nw, nd = [], 0, 0
    panes_drawn = any(g.get('panes', 0) >= 2 for g in glaz)
    for g in glaz:
        x0, y0, x1, y1 = g['box']; horiz = (x1 - x0) >= (y1 - y0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        sides = [(0, -1), (0, 1)] if horiz else [(-1, 0), (1, 0)]
        normal = None
        for nx, ny in sides:
            px = int(cx + nx * ((x1 - x0) / 2 + 4)); py = int(cy + ny * ((y1 - y0) / 2 + 4))
            if out_at(px, py):
                normal = (nx, ny)
        # a drawing that shows its sliding doors' panes says which frames slide: the frames without panes are windows,
        # however wide; otherwise a frame 1.20 m or longer is taken for a glazed door
        door = g.get('kind') == 'glazed door' or (g.get('kind') != 'window' and (g['panes'] >= 2 if panes_drawn else max(x1 - x0, y1 - y0) >= 120))
        g['slider'] = door
        if normal is None:
            continue
        inside = (int(cx - normal[0] * ((x1 - x0) / 2 + 4)), int(cy - normal[1] * ((y1 - y0) / 2 + 4)))
        host = next((r['name'] for r in rooms if r['rect'] and r['rect'][0] <= inside[0] < r['rect'][2] and r['rect'][1] <= inside[1] < r['rect'][3]), '')
        if door:
            nd += 1; code = g.get('tag') or 'D%02d' % nd; sill, hgt = 0, 230
        else:
            nw += 1; code = g.get('tag') or 'W%02d' % nw; sill, hgt = 100, 120
        openings.append({'code': code, 'room': host, 'box': [rnd(x0), rnd(y0), rnd(x1), rnd(y1)], 'sill': sill, 'height': hgt, 'normal': list(normal), 'assumed': True})
    if openings:
        report['assumed'].append('Window sills and heights (100 and 120 cm) and glazed-door heights (230 cm) are assumed; '
                                 + ('frames with sliding panes drawn are read as glazed doors. ' if panes_drawn else 'frames 1.20 m or longer are read as glazed doors. ')
                                 + 'Correct them on the check page.')

    dims = []
    for e in got['dims']:
        if e.dxftype() != 'DIMENSION':
            continue
        try:
            a, b, base = e.dxf.defpoint2, e.dxf.defpoint3, e.dxf.defpoint
        except Exception:
            continue
        p, q, o = T(a.x, a.y), T(b.x, b.y), T(base.x, base.y)
        if abs(p[1] - q[1]) < abs(p[0] - q[0]):
            fr, to = (min(p[0], q[0]), o[1]), (max(p[0], q[0]), o[1])
        else:
            fr, to = (o[0], min(p[1], q[1])), (o[0], max(p[1], q[1]))
        L = math.hypot(to[0] - fr[0], to[1] - fr[1])
        dims.append({'from': [rnd(fr[0]), rnd(fr[1])], 'to': [rnd(to[0]), rnd(to[1])], 'text': ('%.2f' % (L / 100))})

    garden = ''
    if site_polys:
        q = pl(max(site_polys, key=len))
        garden = 'M' + ' L'.join('%s %s' % (rnd(x), rnd(y)) for x, y in q) + ' Z'

    plan = [{'k': 'group', 'cls': 'zones'}]
    for r in rooms:
        if r['rect']:
            use = next((u for pat, u in USE if re.search(pat, r['name'], re.I)), 'pub')
            plan.append({'k': 'zone', 'use': use, 'box': r['rect']})
    plan += [{'k': 'end'}, {'k': 'group', 'cls': 'struct'}]
    plan += [{'k': 'wall', 'box': [rnd(v) for v in b]} for b in rects(wmask)]
    plan += [dict({'k': 'wall'}, **g) for g in gaps]
    plan += [{'k': 'column', 'box': c} for c in columns]
    for g in glaz:
        b = [rnd(v) for v in g['box']]
        plan.append({'k': 'slider', 'box': b, 'set': 'openings', 'panels': max(2, g['panes'])} if g['slider'] else {'k': 'window', 'box': b, 'set': 'openings'})
    if openings:
        plan.append({'k': 'shutters', 'set': 'openings'})
    def entry(d):
        """A swing door with the outside just beyond its closed line, on the side away from its leaf."""
        (hx, hy), (lx, ly), (ex, ey) = d['hinge'], d['leaf'], d['end']
        mx, my = (hx + ex) / 2, (hy + ey) / 2
        sx, sy = (0, -1 if ly > hy else 1) if abs(ex - hx) >= abs(ey - hy) else (-1 if lx > hx else 1, 0)
        return out_at(int(mx + sx * 25), int(my + sy * 25))
    plan += [dict({'k': 'door', 'hinge': [rnd(v) for v in d['hinge']], 'leaf': [rnd(v) for v in d['leaf']], 'end': [rnd(v) for v in d['end']]},
                  **({'cls': 'door entry'} if entry(d) else {})) for d in doors]
    plan += [{'k': 'end'}, {'k': 'group', 'cls': 'labels'}]
    plan += [dict({'k': 'room', 'name': r['name'], 'label': r['label']}, **({'rect': r['rect']} if r['rect'] else {})) for r in rooms]
    plan += [{'k': 'end'}, {'k': 'group', 'cls': 'dims'}]
    plan += [dict({'k': 'dim'}, **d) for d in dims]
    plan += [{'k': 'end'}]

    lat, lon, facing = (site or {}).get('lat'), (site or {}).get('lon'), (site or {}).get('facing')
    if lat is None or lon is None or facing is None:
        report['assumed'].append('The site is not set: give --lat, --lon and --facing (the compass bearing the plan\'s top '
                                 'edge faces) for the real sun. Until then the sun tools use 30.0, 31.5 and 180.')
    A = {'about': 'Imported from ' + report['source'] + ' by dxf_import.py: a draft to check on check.html before it is locked.',
         'name': os.path.splitext(report['source'])[0],
         'site': {'lat': lat if lat is not None else 30.0, 'lon': lon if lon is not None else 31.5,
                  'facing': facing if facing is not None else 180, 'facing_note': 'compass bearing the plan\'s top edge (-y) faces'},
         'heights': {'ceiling': 280, 'door_head': 230},
         'survey': {'pdf': None, 'note': 'No survey PDF: the dimensions come from the DXF (the "dim" elements).'},
         'garden': garden,
         'openings': openings,
         'plan': plan,
         'import': report}
    report['assumed'].append('Ceiling 2.80 m and door heads 2.30 m are assumed.')
    report['counts'] = {'walls': sum(1 for e in plan if e['k'] == 'wall'), 'columns': len(columns), 'doors': len(doors),
                        'windows': sum(1 for g in glaz if not g['slider']), 'glazed doors': sum(1 for g in glaz if g['slider']),
                        'rooms': len(rooms), 'rooms with a size': sum(1 for r in rooms if r['rect']), 'dimensions': len(dims),
                        'exterior openings': len(openings)}
    return A, (W, H), [(cat, [pl(p) for g in polys for p in pts_of(g)]) for cat, polys in (('walls', wall_polys), ('columns', col_polys))]


def write(A, outdir):
    os.makedirs(outdir, exist_ok=True)
    s = json.dumps(A, indent=1, ensure_ascii=False)
    s = re.sub(r'\[\s*([-\d.,\s]+?)\s*\]', lambda m: '[' + re.sub(r'\s+', '', m.group(1)).replace(',', ', ') + ']', s)
    p = os.path.join(outdir, 'apartment.json')
    open(p, 'w', encoding='utf-8').write(s + '\n')
    return p


CHECK_JS = r"""
(function(){
  var $=function(id){ return document.getElementById(id); };
  var READ=JSON.parse($('draft').textContent), A=JSON.parse(JSON.stringify(READ)), sel=null;
  var host=window.parent!==window?window.parent:window.opener||null, inStudio=!!host;   // the studio around it, or the studio that opened it
  var NS='http://www.w3.org/2000/svg';
  var r1=function(v){ return Math.round(v*100)/100; };              // keeps the drawing's own precision (a tenth of a mm)
  var f=function(v){ return String(+(+v).toFixed(1)); };
  function doorSVG(d){ var hx=d.hinge[0],hy=d.hinge[1],lx=d.leaf[0],ly=d.leaf[1],ex=d.end[0],ey=d.end[1];
    var r=Math.hypot(lx-hx,ly-hy), a1=Math.atan2(ly-hy,lx-hx), a2=Math.atan2(ey-hy,ex-hx);
    var dd=((a2-a1+Math.PI)%(2*Math.PI)+2*Math.PI)%(2*Math.PI)-Math.PI, sw=dd>0?1:0;
    return '<path d="M'+f(hx)+' '+f(hy)+' L'+f(lx)+' '+f(ly)+'" class="'+(d.cls||'door')+'"/>'+
      '<path d="M'+f(lx)+' '+f(ly)+' A'+f(r)+' '+f(r)+' 0 0 '+sw+' '+f(ex)+' '+f(ey)+'" class="swing"/>'; }
  function hit(d){ var xs=[d.hinge[0],d.leaf[0],d.end[0]], ys=[d.hinge[1],d.leaf[1],d.end[1]];
    var x0=Math.min.apply(0,xs)-8, y0=Math.min.apply(0,ys)-8, x1=Math.max.apply(0,xs)+8, y1=Math.max.apply(0,ys)+8;
    return '<rect class="hit" x="'+f(x0)+'" y="'+f(y0)+'" width="'+f(x1-x0)+'" height="'+f(y1-y0)+'"/>'; }
  var G=[].slice.call(document.querySelectorAll('.dd'));
  function same(a,b){ return JSON.stringify([a.hinge,a.leaf,a.end])===JSON.stringify([b.hinge,b.leaf,b.end]); }
  function drawDoors(){ G.forEach(function(g,n){ var i=+g.getAttribute('data-i'), d=A.plan[i];
    g.innerHTML=doorSVG(d)+hit(d); g.classList.toggle('on',sel===g); g.classList.toggle('fixed',!same(d,READ.plan[i])); });
    var m=$('marks'); m.innerHTML='';
    if(sel){ var d=A.plan[+sel.getAttribute('data-i')], t=document.createElementNS(NS,'text');
      t.setAttribute('x',f((d.hinge[0]+d.end[0])/2)); t.setAttribute('y',f((d.hinge[1]+d.end[1])/2-14)); t.setAttribute('class','dn');
      t.textContent=sel.getAttribute('aria-label').replace('Door ',''); m.appendChild(t); } }
  function choose(g){ sel=g; $('doorname').textContent=g?g.getAttribute('aria-label'):'No door chosen';
    [].forEach.call(document.querySelectorAll('#doorbar button'),function(b){ b.disabled=!g; }); drawDoors(); }
  G.forEach(function(g){ g.addEventListener('click',function(){ choose(g); });
    g.addEventListener('keydown',function(e){ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); choose(g); } }); });
  [].forEach.call(document.querySelectorAll('#doorbar button'),function(b){ b.addEventListener('click',function(){
    if(!sel)return; var i=+sel.getAttribute('data-i'), d=A.plan[i], H=d.hinge, L=d.leaf, E=d.end, v=[L[0]-H[0],L[1]-H[1]], act=b.getAttribute('data-act');
    if(act==='side')d.leaf=[r1(H[0]-v[0]),r1(H[1]-v[1])];                         // the leaf on the wall's other side
    else if(act==='hinge'){ d.hinge=E; d.end=H; d.leaf=[r1(E[0]+v[0]),r1(E[1]+v[1])]; }   // the same side, hinged at the far jamb
    else { d.hinge=READ.plan[i].hinge.slice(); d.leaf=READ.plan[i].leaf.slice(); d.end=READ.plan[i].end.slice(); }
    changed(); }); });
  // openings: the long side of the box is its width
  var tb=document.querySelector('#ops tbody');
  (A.openings||[]).forEach(function(o,k){ var w=Math.max(o.box[2]-o.box[0],o.box[3]-o.box[1]), tr=document.createElement('tr');
    tr.innerHTML='<th></th><td></td><td>'+(w/100).toFixed(2)+' m</td><td><input data-k="'+k+'" data-f="sill" inputmode="decimal"></td><td><input data-k="'+k+'" data-f="height" inputmode="decimal"></td>';
    tr.children[0].textContent=o.code; tr.children[1].textContent=o.room||''; tb.appendChild(tr); });
  if(!(A.openings||[]).length){ var tr=document.createElement('tr'); tr.innerHTML='<td colspan="5">No openings to the outside were read.</td>'; tb.appendChild(tr); }
  function fill(){ [].forEach.call(tb.querySelectorAll('input'),function(x){ x.value=A.openings[+x.getAttribute('data-k')][x.getAttribute('data-f')]; x.classList.remove('bad'); });
    $('ceil').value=A.heights.ceiling; $('dhead').value=A.heights.door_head; $('ceil').classList.remove('bad'); $('dhead').classList.remove('bad'); }
  function num(x){ var v=x.value.trim().replace(',','.'), n=Number(v); return v!==''&&isFinite(n)&&n>=0?n:null; }
  [].forEach.call(tb.querySelectorAll('input'),function(x){ x.addEventListener('input',function(){ var n=num(x); x.classList.toggle('bad',n===null);
    if(n===null)return; var k=+x.getAttribute('data-k'), o=A.openings[k], r=READ.openings[k]; o[x.getAttribute('data-f')]=n;
    if('assumed' in r)o.assumed=r.assumed&&o.sill===r.sill&&o.height===r.height;      // a sill or height given is no longer assumed
    changed(); }); });
  [['ceil','ceiling'],['dhead','door_head']].forEach(function(p){ $(p[0]).addEventListener('input',function(){ var n=num(this); this.classList.toggle('bad',n===null||n<150);
    if(n!==null&&n>=150){ A.heights[p[1]]=n; changed(); } }); });
  function notes(){ var out=[], nd=0;
    G.forEach(function(g){ var i=+g.getAttribute('data-i'), d=A.plan[i], o=READ.plan[i]; if(same(d,o))return; nd++;
      var side=(d.leaf[0]-d.hinge[0])*(o.leaf[0]-o.hinge[0])+(d.leaf[1]-d.hinge[1])*(o.leaf[1]-o.hinge[1])<0;
      var moved=d.hinge[0]!==o.hinge[0]||d.hinge[1]!==o.hinge[1];
      out.push(g.getAttribute('aria-label')+': '+[moved?'hinged at the other end':'',side?'swings to the other side':''].filter(Boolean).join(', ')+'.'); });
    (A.openings||[]).forEach(function(o,k){ var r=READ.openings[k]; if(o.sill!==r.sill||o.height!==r.height)out.push(o.code+': sill '+o.sill+' cm, height '+o.height+' cm.'); });
    if(A.heights.ceiling!==READ.heights.ceiling)out.push('Ceiling '+A.heights.ceiling+' cm.');
    if(A.heights.door_head!==READ.heights.door_head)out.push('Door heads '+A.heights.door_head+' cm.');
    return out; }
  function changed(){ var out=notes(); drawDoors(); A['import'].corrected=out;
    var high=(A.openings||[]).filter(function(o){ return o.sill+o.height>A.heights.ceiling; }).map(function(o){ return o.code; });
    $('fixnote').textContent=(out.length?out.length+' correction'+(out.length>1?'s':'')+(inStudio?', used when you build the site.':', kept in the file you save.'):'')+
      (high.length?' Check '+high.join(', ')+': sill and height together are above the ceiling.':'');
    if(inStudio)host.postMessage({checkDraft:A},'*'); }
  function text(){ return JSON.stringify(A,null,1).replace(/\[\s*([-\d.,\s]+?)\s*\]/g,function(m,g){ return '['+g.replace(/\s+/g,'').split(',').join(', ')+']'; })+'\n'; }
  $('save').addEventListener('click',function(){ var u=URL.createObjectURL(new Blob([text()],{type:'application/json'})), a=document.createElement('a');
    a.href=u; a.download='apartment.json'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(function(){ URL.revokeObjectURL(u); },4000);
    $('fixnote').textContent='Saved apartment.json: put it in place of drawings/import/apartment.json, then tell Claude Code the import is right.'; });
  $('reset').addEventListener('click',function(){ A=JSON.parse(JSON.stringify(READ)); fill(); choose(null); changed(); $('fixnote').textContent=inStudio?'Back to what was read.':''; });
  if(inStudio){ $('save').hidden=true; $('cli').hidden=true; }
  fill(); drawDoors();
  if(inStudio){ host.postMessage({checkReady:1},'*'); if(READ['import'].corrected&&READ['import'].corrected.length)changed(); }
})();
"""


def check_page(A, size, src, outdir):
    """check.html: the draft plan drawn with the plan page's own helpers, over the drawing's walls and columns in red,
    with what was assumed and what could not be read. What a drawing cannot say is corrected on the page itself: click a
    door to turn its swing or move its hinge; each opening's sill and height; the ceiling and door heads. Opened on a
    computer, the page saves the corrected apartment.json; inside the studio, it hands the draft to the page around it."""
    sys.path.insert(0, HERE)
    import build_plans as bp
    import openings as op
    keep = op.OPENINGS
    op.OPENINGS = [(o['code'], o['room'], tuple(o['box']), o['sill'], o['height'], tuple(o['normal'])) for o in A['openings']]
    try:
        parts, n = [], 0
        for i, e in enumerate(A['plan']):
            if e['k'] == 'door':
                n += 1
                parts.append(f'<g class="dd" data-i="{i}" tabindex="0" role="button" aria-label="Door {n}">{bp.draw(e)}</g>')
            else:
                parts.append(bp.draw(e))
        body = ''.join(parts)
    finally:
        op.OPENINGS = keep
    W, H = size
    red = ''.join('<polygon points="%s" class="src"/>' % ' '.join('%.1f,%.1f' % q for q in p) for _, ps in src for p in ps)
    garden = '<path d="%s" class="garden"/>' % A['garden'] if A['garden'] else ''
    rep = A['import']
    li = lambda xs: ''.join('<li>%s</li>' % x for x in xs) or '<li>None.</li>'
    counts = ''.join('<tr><th>%s</th><td>%s</td></tr>' % (k, v) for k, v in rep['counts'].items())
    ignored = ', '.join('%s (%d)' % (k, v) for k, v in sorted(rep['ignored'].items())) or 'nothing'
    layers = ', '.join('%s: %s' % (k, ' '.join(v)) for k, v in rep['layers'].items())
    draft = json.dumps(A, ensure_ascii=False).replace('</', '<\\/')        # safe inside a <script>
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Check the import</title><style>
:root{{--bg:#F6F4EF;--ink:#1D2125;--muted:#5d6267;--line:#d9d4ca;--accent:#2E5A74}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181a;--ink:#e8e6e1;--muted:#a3a8ad;--line:#34383c;--accent:#8db6d1}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:20px 16px 40px;display:grid;gap:18px}}
h1{{margin:0;font-size:24px}} h2{{margin:0;font-size:16px}} p{{margin:0;color:var(--muted)}}
.plan{{background:#fff;border:1px solid var(--line);border-radius:8px;padding:8px;overflow:auto}}
svg{{width:100%;height:auto;display:block;min-width:600px}}
.dd{{cursor:pointer;outline:none}} .dd .hit{{fill:transparent;stroke:none}} .dd:hover .door,.dd:focus-visible .door{{stroke:var(--accent)}}
.dd.fixed .door{{stroke:#2f7d4f}} .dd.on .door{{stroke:#c2410c;stroke-width:3}} .dd.on .swing{{stroke:#c2410c}}
.dn{{font:600 15px system-ui,sans-serif;fill:#c2410c;text-anchor:middle;pointer-events:none}}
.fix{{display:grid;gap:12px;border:1px solid var(--line);border-radius:8px;padding:14px 16px}}
.fix .bar{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
button{{font:inherit;font-size:14px;padding:6px 12px;border-radius:6px;border:1px solid var(--ink);background:transparent;color:var(--ink);cursor:pointer}}
button.main{{background:var(--ink);color:var(--bg)}} button:disabled{{opacity:.4;cursor:default}}
.tw{{overflow-x:auto}} #ops{{min-width:480px}} #ops td,#ops th{{padding:4px 12px 4px 0;font-variant-numeric:tabular-nums}}
.fix input{{font:inherit;width:6.5em;padding:4px 6px;border:1px solid var(--line);border-radius:5px;background:var(--bg);color:var(--ink)}}
.fix input.bad{{border-color:#c2410c}} .hts{{display:flex;flex-wrap:wrap;gap:8px 20px}} .hts label{{display:flex;gap:8px;align-items:center}}
#fixnote{{color:var(--ink)}} #fixnote:empty{{display:none}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
table{{border-collapse:collapse}} th{{text-align:left;font-weight:500;color:var(--muted);padding:2px 12px 2px 0}}
ul{{margin:6px 0 0;padding-left:18px}}
.src{{fill:none;stroke:#e0352b;stroke-width:1.2;stroke-dasharray:4 3}}
.garden{{fill:#eef3e8;stroke:#9bb08a;stroke-dasharray:8 6}}
.z{{opacity:.55}}.z.pri{{fill:#e7efe6}}.z.wetz{{fill:#e2ebf3}}.z.ser{{fill:#eceaf3}}.z.cir{{fill:#eeece7}}.z.pub{{fill:#f3ebe0}}
.wall{{fill:#1D2125}}.col{{fill:#5b5249}}.win{{fill:#fff;stroke:#1D2125;stroke-width:1}}.winl{{stroke:#5a8ab0;stroke-width:1.5}}
.sillg{{fill:#fff;stroke:#1D2125;stroke-width:1}}.pane{{fill:#cfe0ee;stroke:#5a8ab0;stroke-width:.8}}
.door{{fill:none;stroke:#1D2125;stroke-width:2}}.swing{{fill:none;stroke:#777;stroke-width:1;stroke-dasharray:5 4}}
.shut{{stroke:#999;stroke-width:1.2;stroke-dasharray:6 4}}
.rl{{font:600 20px system-ui,sans-serif;text-anchor:middle;fill:#1D2125;text-transform:uppercase;letter-spacing:.06em}}
.rdim{{font:16px system-ui,sans-serif;text-anchor:middle;fill:#555}}.ra{{display:none}}
.dl{{stroke:#2E5A74;stroke-width:1.2}}.dt{{stroke:#2E5A74;stroke-width:1.5}}.dimt{{font:15px system-ui,sans-serif;text-anchor:middle;fill:#2E5A74}}
</style></head><body><main>
<h1>Check the import: {rep['source']}</h1>
<p>The plan as read from the drawing, drawn the way the plan page draws it. The red dashed outlines are the drawing's own walls and columns: they should sit exactly on the black. Look at every door, window and room name, and correct below what the drawing could not say.<span id="cli"> Then confirm in Claude Code ("the import is right"), or say what else to correct.</span></p>
<div class="plan"><svg viewBox="-40 -40 {W + 80} {H + 80}" id="plansvg">{garden}{body}{red}<g id="marks"></g></svg></div>
<section class="fix" id="fix"><h2>Correct what the drawing could not say</h2>
<p>A drawing does not say which way a door opens, how high a window sits or how high the ceiling is: what was assumed is below. Click a door on the plan to change it; type a sill or a height. Every change is kept in the draft.</p>
<div class="bar" id="doorbar"><b id="doorname">No door chosen</b><button type="button" data-act="side" disabled>Swing to the other side</button><button type="button" data-act="hinge" disabled>Hinge at the other end</button><button type="button" data-act="back" disabled>As read</button></div>
<div class="tw"><table id="ops"><thead><tr><th>Opening</th><th>Room</th><th>Width</th><th>Sill, cm</th><th>Height, cm</th></tr></thead><tbody></tbody></table></div>
<div class="hts"><label>Ceiling, cm <input id="ceil" inputmode="decimal"></label><label>Door heads, cm <input id="dhead" inputmode="decimal"></label></div>
<p id="fixnote" role="status"></p>
<div class="bar"><button type="button" class="main" id="save">Save the corrected apartment.json</button><button type="button" id="reset">Back to what was read</button></div>
</section>
<div class="grid">
<section><h2>What was read</h2><table>{counts}</table><p>Units: {rep['units']}. Layers: {layers}.</p></section>
<section><h2>Assumed (please confirm)</h2><ul>{li(rep['assumed'])}</ul></section>
<section><h2>Could not be read</h2><ul>{li(rep['warnings'])}</ul><p>Left out: {ignored}.</p></section>
</div></main>
<script type="application/json" id="draft">{draft}</script>
<script>{CHECK_JS}</script></body></html>'''
    p = os.path.join(outdir, 'check.html')
    open(p, 'w', encoding='utf-8').write(html)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('dxf', help='the plan: .dwg (read through LibreDWG) or .dxf'); ap.add_argument('outdir')
    ap.add_argument('--units', choices=['mm', 'cm', 'm', 'in'])
    ap.add_argument('--layers', help='JSON: {"walls": "<regex>", ...} to override layer recognition')
    ap.add_argument('--lat', type=float); ap.add_argument('--lon', type=float); ap.add_argument('--facing', type=float)
    ap.add_argument('--plan', help='which plan, when the drawing holds several: its title (e.g. "First floor") or its number')
    a = ap.parse_args()
    site = {'lat': a.lat, 'lon': a.lon, 'facing': a.facing}
    if a.dxf.lower().endswith('.dwg'):
        a.dxf = dwg_to_dxf(a.dxf, os.path.join(a.outdir, 'converted'))
    A, size, src = import_dxf(a.dxf, a.units, json.loads(a.layers) if a.layers else None, site, a.plan)
    p = write(A, a.outdir)
    c = check_page(A, size, src, a.outdir)
    print('wrote', p, 'and', c)
    print(json.dumps(A['import']['counts']))
    for x in A['import']['assumed']:
        print('assumed:', x)
    for x in A['import']['warnings']:
        print('could not read:', x)


if __name__ == '__main__':
    main()
