"""Build the 3D page (site/3d.html) from apartment.json.

The plan page's drawing helpers record plain geometry while they draw the apartment (build_plans.REC); every record
becomes simple solids in centimetres: walls to the ceiling, lintels over doors, sills and glass in the windows, door
leaves open and shut (the viewer's Doors switch picks), sliding glass doors, frames and roller shutters on every
exterior opening, floors and ceilings per room, skirting, and a light fitting in every room. The scene is inlined into
tools/viewer.html, which draws it with three.js.

  python3 tools/build_3d.py            -> site/3d.html
"""
import base64, json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apartment  # noqa: E402
import build_plans as bp  # noqa: E402
import openings as op  # noqa: E402
import sunpath  # noqa: E402

ROOT = apartment.ROOT
CEIL = apartment.CEIL          # slab soffit
HEAD = apartment.HEAD          # door and sliding-door head

items = []
FURN = [None]


def box(x0, y0, x1, y1, z0, z1, mat, ctx=None, tag=None):
    x0, x1 = sorted((x0, x1)); y0, y1 = sorted((y0, y1))
    if x1 - x0 < 0.5 or y1 - y0 < 0.5 or z1 - z0 < 0.5:
        return
    d = {'t': 'b', 'b': [round(v, 1) for v in (x0, y0, z0, x1, y1, z1)], 'm': mat}
    if ctx:
        d['v'] = ctx
    if tag:
        d['g'] = tag
    if FURN[0]:
        d['f'] = FURN[0]
    items.append(d)


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def centre(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def opening_of(b):
    """The exterior opening (apartment.json openings) at this box, if any."""
    return next((o for o in op.OPENINGS if overlaps(o[2], b)), None)


def window_spec(b):
    o = opening_of(b)
    return (o[3], o[4]) if o and o[3] > 0 else (100, 120)


def windows_and_shutters():
    """Aluminium frames on the windows and sliders, and an exterior roller shutter on every opening:
    guide rails always, the curtain half down ('sh-half') or fully down ('sh-closed')."""
    for o in op.OPENINGS:
        code, _, (x0, y0, x1, y1), sill, hgt, (nx, ny) = o
        door = sill <= 0
        z0, top = (0, HEAD) if door else (sill, sill + hgt)
        along_x = bool(ny)
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2

        def fr(a0, a1, b0, b1, c0, c1, mat='frame', ctx=None):
            if along_x:
                box(a0, b0, a1, b1, c0, c1, mat, ctx)
            else:
                box(b0, a0, b1, a1, c0, c1, mat, ctx)
        a0, a1 = (x0, x1) if along_x else (y0, y1)
        c = cy if along_x else cx
        fr(a0, a0 + 5, c - 3, c + 3, z0, top); fr(a1 - 5, a1, c - 3, c + 3, z0, top)
        if not door:
            fr(a0, a1, c - 3, c + 3, top - 5, top); fr(a0, a1, c - 3, c + 3, z0, z0 + 5)
            fr((a0 + a1) / 2 - 2.5, (a0 + a1) / 2 + 2.5, c - 3, c + 3, z0, top)
        f = (y0 if ny < 0 else y1) if along_x else (x0 if nx < 0 else x1)
        sg = ny if along_x else nx
        b_out = sorted((f, f + sg * 7))
        fr(a0, a0 + 4, b_out[0], b_out[1], z0, top, 'frame'); fr(a1 - 4, a1, b_out[0], b_out[1], z0, top, 'frame')
        cur = sorted((f + sg * 3, f + sg * 5))
        fr(a0 + 2, a1 - 2, cur[0], cur[1], top - (top - z0) / 2, top, 'shutter', 'sh-half')
        fr(a0 + 2, a1 - 2, cur[0], cur[1], z0, top, 'shutter', 'sh-closed')


SKIRT_H, SKIRT_T = 8, 1.2


def skirting(R):
    """Painted skirting along every stretch of wall that bounds a dry room's floor (not across doorways, not in the
    bathrooms)."""
    walls = [it['b'] for it in items if it['t'] == 'b' and it.get('g') == 'wall' and it['b'][2] == 0]

    def runs(lo, hi, spans):
        spans = sorted((max(lo, a), min(hi, b)) for a, b in spans if b > lo and a < hi)
        out = []
        for a, b in spans:
            if out and a <= out[-1][1] + 0.5:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return [(a, b) for a, b in out if b - a >= 4]
    for r in R:
        if r['kind'] != 'rect' or not r['cls'].startswith('z ') or r['cls'] == 'z wetz':
            continue
        x0, y0, x1, y1 = r['box']
        for a, b in runs(x0, x1, [(w[0], w[3]) for w in walls if abs(w[4] - y0) <= 3]):
            box(a, y0, b, y0 + SKIRT_T, 0, SKIRT_H, 'white')
        for a, b in runs(x0, x1, [(w[0], w[3]) for w in walls if abs(w[1] - y1) <= 3]):
            box(a, y1 - SKIRT_T, b, y1, 0, SKIRT_H, 'white')
        for a, b in runs(y0, y1, [(w[1], w[4]) for w in walls if abs(w[3] - x0) <= 3]):
            box(x0, a, x0 + SKIRT_T, b, 0, SKIRT_H, 'white')
        for a, b in runs(y0, y1, [(w[1], w[4]) for w in walls if abs(w[0] - x1) <= 3]):
            box(x1 - SKIRT_T, a, x1, b, 0, SKIRT_H, 'white')


def lighting(rooms):
    """A light plan any apartment can start from: a ceiling light in each small room, downlights about 1.5 m apart in
    the larger ones, and a wall light outside every glazed door to the garden."""
    out = []
    for r in rooms:
        if not r['r']:
            continue
        x0, y0, x1, y1 = r['r']
        w, d = x1 - x0, y1 - y0
        if w * d < 12e4 or min(w, d) < 200:
            out.append({'k': 'ceil', 'p': [round((x0 + x1) / 2), round((y0 + y1) / 2)]})
            continue
        nx, ny = max(2, round(w / 150)), max(2, round(d / 150))
        for i in range(nx):
            for j in range(ny):
                out.append({'k': 'down', 'p': [round(x0 + w * (i + .5) / nx), round(y0 + d * (j + .5) / ny)]})
    for o in op.OPENINGS:
        if o[3] <= 0:
            fx0, fy0, fx1, fy1 = op.exterior_face(o)
            nx, ny = o[5]
            out.append({'k': 'ext', 'p': [round((fx0 + fx1) / 2 + nx * 12), round((fy0 + fy1) / 2 + ny * 12)]})
    return out


def piece_name(r):
    k = r['kind']
    if k == 'rect':
        return {'wall': ('Wall', ''), 'wall neww': ('New wall', ''), 'col': ('Column', '')}.get(r.get('cls') or '', (None, None))
    return None, None


def build(doors_shut=False):
    bp.REC = []
    items.clear()
    bp.as_built()
    R = bp.REC
    windows = [r['box'] for r in R if r['kind'] == 'window']
    sliders = [r['box'] for r in R if r['kind'] == 'slider']

    def glazed_door(b, ctx=None):
        """Lintel, tracks and two sliding leaves: the outer one fixed, the inner one shown closed ('d-closed') or
        slid open over it ('d-open')."""
        x0, y0, x1, y1 = b
        box(x0, y0, x1, y1, HEAD, CEIL, 'wall', ctx, 'wall')
        cx0, cy0 = centre(b)
        along_x = (x1 - x0) > (y1 - y0)
        a0, a1 = (x0, x1) if along_x else (y0, y1)
        c = cy0 if along_x else cx0
        mid = (a0 + a1) / 2

        def fr(p0, p1, q0, q1, z0, z1, mat, v=None, tag=None):
            if along_x:
                box(p0, q0, p1, q1, z0, z1, mat, v or ctx, tag)
            else:
                box(q0, p0, q1, p1, z0, z1, mat, v or ctx, tag)
        fr(a0, a1, c - 3.5, c + 3.5, 0, 3, 'frame'); fr(a0, a1, c - 3.5, c + 3.5, HEAD - 5, HEAD, 'frame')

        def leaf(l0, l1, cc, v):
            fr(l0 + 4, l1 - 4, cc - .8, cc + .8, 6, HEAD - 9, 'glass', v, 'glass')
            fr(l0, l0 + 4, cc - 1.6, cc + 1.6, 3, HEAD - 5, 'frame', v); fr(l1 - 4, l1, cc - 1.6, cc + 1.6, 3, HEAD - 5, 'frame', v)
            fr(l0, l1, cc - 1.6, cc + 1.6, 3, 7, 'frame', v); fr(l0, l1, cc - 1.6, cc + 1.6, HEAD - 9, HEAD - 5, 'frame', v)
        leaf(a0, mid + 2, c - 1.8, None)
        leaf(mid - 2, a1, c + 1.8, 'd-closed')
        leaf(a0 + 6, mid + 8, c + 1.8, 'd-open')

    openings_ = [r['box'] for r in R if r['kind'] == 'opening']
    for b in sliders:
        if not any(overlaps(b, o) for o in openings_):
            glazed_door(b)

    pieces = []
    doors = [r for r in R if r['kind'] == 'door']

    def add_piece(r, n0):
        new = items[n0:]
        if not new:
            return
        name, mt = piece_name(r)
        if r['kind'] == 'opening':
            name, mt = ('Window', 'aluminium') if any(it['m'] == 'glass' and it['b'][2] > 50 for it in new if it['t'] == 'b') else \
                       ('Garden doors', 'sliding, aluminium') if any(it['m'] == 'glass' for it in new) else (None, None)
        elif r['kind'] == 'door':
            name, mt = {'door entry': ('Front door', 'dark oak')}.get(r['cls'], ('Door', 'oak'))
        if not name:
            return
        byv = {}
        if r['kind'] == 'opening':
            byv[None] = [it for it in new if it['m'] in ('glass', 'frame') and it.get('v') in (None, 'w-closed', 'd-closed')] or new
        else:
            for it in new:
                byv.setdefault(it.get('v'), []).append(it)
        for v, its in byv.items():
            bx = [it['b'] for it in its if it['t'] == 'b']
            if not bx:
                continue
            b = [min(q[0] for q in bx), min(q[1] for q in bx), max(0, min(q[2] for q in bx)), max(q[3] for q in bx), max(q[4] for q in bx), max(q[5] for q in bx)]
            pc = {'n': name, 'b': [round(x, 1) for x in b]}
            if mt:
                pc['mt'] = mt
            if v:
                pc['v'] = v
            pieces.append(pc)

    for r in R:
        k, ctx = r['kind'], (r['ctx'][-1] if r['ctx'] else None)
        n0 = len(items)
        if k == 'rect':
            x0, y0, x1, y1 = r['box']; c = r['cls']
            if c in ('wall', 'wall neww'):
                box(x0, y0, x1, y1, 0, CEIL, 'wall', ctx, 'wall')
            elif c == 'col':
                box(x0, y0, x1, y1, 0, CEIL, 'wall', ctx, 'wall')
            elif c.startswith('z '):
                zone = c[2:]
                mat = {'pri': 'oakfloor', 'wetz': 'stone'}.get(zone, 'porcelain')
                box(x0, y0, x1, y1, 0, 1, mat, ctx, 'floor')
                items[-1]['zn'] = zone
                box(x0, y0, x1, y1, CEIL - 1, CEIL, 'ceiling', ctx, 'ceiling')
        elif k == 'opening':
            x0, y0, x1, y1 = r['box']
            if any(overlaps(r['box'], w) for w in windows):
                sill, hgt = window_spec(r['box'])
                box(x0, y0, x1, y1, 0, sill, 'wall', ctx, 'wall')
                box(x0, y0, x1, y1, sill + hgt, CEIL, 'wall', ctx, 'wall')
                cx0, cy0 = centre(r['box'])
                along_x = (x1 - x0) > (y1 - y0)
                if along_x:
                    box(x0, cy0 - 1, x1, cy0 + 1, sill, sill + hgt, 'glass', 'w-closed', 'glass')
                else:
                    box(cx0 - 1, y0, cx0 + 1, y1, sill, sill + hgt, 'glass', 'w-closed', 'glass')
                o = opening_of(r['box'])
                if o:                                     # open: two casement sashes swung in square to the wall
                    nx, ny = o[5]
                    a0, a1 = (x0, x1) if along_x else (y0, y1)
                    half = (a1 - a0) / 2 - 5
                    face = (y0 if ny > 0 else y1) if along_x else (x0 if nx > 0 else x1)
                    inn = -ny if along_x else -nx
                    f0, f1 = sorted((face, face + inn * half))
                    for j in (a0 + 5, a1 - 8):
                        if along_x:
                            box(j, f0, j + 3, f1, sill + 4, sill + hgt - 4, 'glass', 'w-open', 'glass')
                            box(j, f0, j + 3, f1, sill, sill + 4, 'frame', 'w-open'); box(j, f0, j + 3, f1, sill + hgt - 4, sill + hgt, 'frame', 'w-open')
                        else:
                            box(f0, j, f1, j + 3, sill + 4, sill + hgt - 4, 'glass', 'w-open', 'glass')
                            box(f0, j, f1, j + 3, sill, sill + 4, 'frame', 'w-open'); box(f0, j, f1, j + 3, sill + hgt - 4, sill + hgt, 'frame', 'w-open')
            elif any(overlaps(r['box'], s) for s in sliders):
                glazed_door(r['box'], ctx)
            else:
                box(x0, y0, x1, y1, HEAD, CEIL, 'wall', ctx, 'wall')
                dr = next((d for d in doors if x0 - 3 <= d['hinge'][0] <= x1 + 3 and y0 - 3 <= d['hinge'][1] <= y1 + 3), None)
                if dr:                                    # an oak lining in the reveal, 1 cm proud of both faces
                    fm = 'oakdark' if dr['cls'] == 'door entry' else 'oak'
                    if (x1 - x0) > (y1 - y0):
                        box(x0, y0 - 1, x0 + 2, y1 + 1, 0, HEAD, fm, ctx); box(x1 - 2, y0 - 1, x1, y1 + 1, 0, HEAD, fm, ctx)
                        box(x0, y0 - 1, x1, y1 + 1, HEAD - 2, HEAD, fm, ctx)
                    else:
                        box(x0 - 1, y0, x1 + 1, y0 + 2, 0, HEAD, fm, ctx); box(x0 - 1, y1 - 2, x1 + 1, y1, 0, HEAD, fm, ctx)
                        box(x0 - 1, y0, x1 + 1, y1, HEAD - 2, HEAD, fm, ctx)
        elif k == 'door':
            (hx, hy), (lx, ly) = r['hinge'], r['leaf']
            mat = 'oakdark' if r['cls'] == 'door entry' else 'oak'

            def leaf(ex, ey, variant):                    # the leaf, with a black lever both sides at 1.05 m
                if abs(ex - hx) > abs(ey - hy):
                    box(hx, hy - 2, ex, hy + 2, 0, HEAD - 2, mat, variant)
                    sg = 1 if ex > hx else -1
                    box(ex - sg * 20, hy - 7, ex - sg * 6, hy + 7, 103.5, 106, 'black', variant)
                    box(ex - sg * 8, hy - 4, ex - sg * 4, hy + 4, 98, 111, 'black', variant)
                else:
                    box(hx - 2, hy, hx + 2, ey, 0, HEAD - 2, mat, variant)
                    sg = 1 if ey > hy else -1
                    box(hx - 7, ey - sg * 20, hx + 7, ey - sg * 6, 103.5, 106, 'black', variant)
                    box(hx - 4, ey - sg * 8, hx + 4, ey - sg * 4, 98, 111, 'black', variant)
            if doors_shut:
                leaf(*r['shut'], ctx)
            else:
                leaf(lx, ly, 'd-open'); leaf(*r['shut'], 'd-closed')
        add_piece(r, n0)

    FURN[0] = None
    skirting(R)
    windows_and_shutters()
    rooms = [{'n': r['name'], 'at': list(r['at']), 'r': list(r['rect']) if r['rect'] else None, 'd': r['dims']}
             for r in R if r['kind'] == 'room']
    labels = [(r['n'], r['at'][0], r['at'][1]) for r in rooms]
    gp = apartment.garden_points()
    if gp:
        labels.append(('Garden', round(sum(q[0] for q in gp) / len(gp)), round(sum(q[1] for q in gp) / len(gp))))
    x0, y0, x1, y1 = apartment.extent(0)
    return {'items': list(items), 'labels': labels, 'rooms': [r for r in rooms if r['d']], 'pieces': pieces,
            'lights': lighting(rooms), 'garden': [list(q) for q in gp], 'site': [x0 - 300, y0 - 300, x1 + 300, y1 + 300],
            'bounds': [x0, y0, x1, y1]}


def entry():
    """Where the viewer opens: just inside the front door, looking into the apartment (or the middle of the
    biggest room if no door is marked as the entry)."""
    for e in apartment.PLAN:
        if e['k'] == 'door' and 'entry' in e.get('cls', ''):
            (hx, hy), (lx, ly), (ex, ey) = e['hinge'], e['leaf'], e['end']
            mx, my = (hx + ex) / 2, (hy + ey) / 2
            dx, dy = lx - hx, ly - hy
            L = math.hypot(dx, dy) or 1
            inx, iny = (0, dy / L) if abs(ex - hx) >= abs(ey - hy) else (dx / L, 0)
            return {'pos': [round(mx + inx * 70), round(my + iny * 70)], 'look': [round(mx + inx * 600), round(my + iny * 600)]}
    rooms = [e for e in apartment.PLAN if e['k'] == 'room' and e.get('rect')]
    if rooms:
        r = max(rooms, key=lambda e: (e['rect'][2] - e['rect'][0]) * (e['rect'][3] - e['rect'][1]))['rect']
        return {'pos': [r[0] + 60, r[1] + 60], 'look': [r[2], r[3]]}
    return {'pos': [0, 0], 'look': [100, 100]}


def blueprint_svg():
    """The walls as thin outlines, drawn while the 3D loads."""
    keep, bp.REC = bp.REC, []
    try:
        bp.as_built()
        recs = bp.REC
    finally:
        bp.REC = keep
    walls = [tuple(r['box']) for r in recs if r['kind'] == 'rect' and r.get('cls', '').split(' ')[0] in ('wall', 'col')]
    rs = ''.join('<rect x="%g" y="%g" width="%g" height="%g" style="--i:%d"/>' % (x0, y0, x1 - x0, y1 - y0, i % 24)
                 for i, (x0, y0, x1, y1) in enumerate(sorted(walls, key=lambda r: (r[1], r[0]))))
    x0, y0, x1, y1 = apartment.extent(40)
    return ('<svg class="bprint" id="bprint" viewBox="%g %g %g %g" aria-hidden="true"><path class="bgarden" d="%s"/>'
            '<g data-l="existing" class="on">%s</g></svg>' % (x0, y0, x1 - x0, y1 - y0, bp.GARDEN, rs))


def scene():
    sc = {'layouts': {'existing': dict(build(), name=apartment.NAME)}, 'default': 'existing', 'name': apartment.NAME}
    sc['changes'] = []
    sc['ba'] = {'keep': [], 'gone': [], 'new': []}
    sc['scenes'] = []
    sc['preview'] = False
    sc['fcat'] = json.load(open(os.path.join(HERE, 'catalogue.json')))
    fj = os.path.join(ROOT, 'furnish.json')
    sc['furnish'] = {k: [dict({'id': 'p%d' % i}, **q) for i, q in enumerate(v['pieces'])]       # the viewer tracks each piece by id
                     for k, v in (json.load(open(fj)) if os.path.exists(fj) else {}).items()}
    sc['context'] = [{'name': n, 'p': [list(q) for q in poly], 'z': [lo, hi]} for n, poly, lo, hi in sunpath.CONTEXT]
    sc['entry'] = entry()
    sc['tz'] = {k: tz for k, _, _, tz, _ in sunpath.DAYS}
    sc['site'] = {'lat': apartment.LAT, 'lon': apartment.LON, 'facing': apartment.FACING}
    return sc


if __name__ == '__main__':
    import plan_lock
    plan_lock.guard()        # the plan's measurements must match plan-lock.json, or nothing is built
    sc = scene()
    tpl = open(os.path.join(HERE, 'viewer.html')).read()
    html = tpl.replace('/*SCENE*/null', json.dumps(sc, separators=(',', ':')))
    html = html.replace('<!--BLUEPRINT-->', blueprint_svg(), 1)
    html = html.replace('{{NAME}}', apartment.NAME.replace('<', '&lt;'))
    out = os.path.join(ROOT, 'site', '3d.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    # three.js and three-mesh-bvh (MIT) are served from the site itself (tools/vendor -> site/lib), so no CDN is needed
    import re, shutil
    CDN = 'https://cdn.jsdelivr.net/npm/'
    for url in set(re.findall(re.escape(CDN) + r'[^"\']+', html)):
        local = os.path.join(HERE, 'vendor', url[len(CDN):])
        if not url.endswith('/') and not os.path.exists(local):
            sys.exit(f'{url} is not in tools/vendor')
    html = html.replace(CDN, './lib/').replace(' crossorigin>', '>')
    shutil.copytree(os.path.join(HERE, 'vendor'), os.path.join(ROOT, 'site', 'lib'), dirs_exist_ok=True)
    open(out, 'w').write(html)
    print('wrote', os.path.relpath(out, ROOT), len(html), 'bytes,', len(sc['layouts']['existing']['items']), 'items')
