"""Build the 3D page (site/3d.html) from apartment.json.

The plan page's drawing helpers record plain geometry while they draw (build_plans.REC); every record becomes simple
solids in centimetres: walls to the ceiling, lintels over doors, sills and glass in the windows, door leaves open and
shut (the viewer's Doors switch picks), sliding glass doors, frames and roller shutters on every exterior opening,
floors and ceilings per room, skirting, light fittings, and any furniture, joinery and garden the plan draws. The
scene is inlined into tools/viewer.html, which draws it with three.js. The viewer marks the places a project may word
or set up differently as <@name>default</@name> (see viewer_html).

A project with its own design layouts runs this file inside its own build_3d.py and replaces the hooks below
(before, column_top, tv_wall, pendant_style, details, grounds, art, labels_for, lighting, garden, site_rect, finish).

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
GLAZED_DOORS = []              # boxes of glazed doors the plan draws as plain openings
TALL = ('Wardrobe', 'Pantry', 'Cleaning', 'Iron', 'Larder', 'Toys', 'Coats')

items = []
DOORN = [0]        # numbers the doors and sliding leaves, so each can be opened or shut on its own ('d-open.N')
FURN = [None]      # 'loose' or 'built' while building furniture records (the viewer's Furniture switch)
LOOSE = {'chair', 'sofa', 'bed', 'roundtable', 'stool', 'rug', 'nightstand', 'bench', 'piano', 'pouf', 'playhouse', 'plant', 'dtable'}

def furn_class(r):
    if not r.get('furn'):
        return None
    if r['kind'] in LOOSE or (r['kind'] == 'rect' and r.get('cls') == 'table'):
        return 'loose'
    return 'built'

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

def cyl(cx, cy, r, z0, z1, mat, ctx=None):
    d = {'t': 'c', 'c': [round(cx, 1), round(cy, 1)], 'r': r, 'z': [z0, z1], 'm': mat}
    if ctx:
        d['v'] = ctx
    if FURN[0]:
        d['f'] = FURN[0]
    items.append(d)

def rounded_rect(x0, y0, x1, y1, r, n=10):
    """Outline of a rectangle with round corners, anticlockwise, for extruded table tops."""
    import math
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts

def poly(pts, z0, z1, mat, ctx=None):
    d = {'t': 'p', 'p': [[round(x, 1), round(y, 1)] for x, y in pts], 'z': [z0, z1], 'm': mat}
    if ctx:
        d['v'] = ctx
    if FURN[0]:
        d['f'] = FURN[0]
    items.append(d)

def sphere(cx, cy, z, r, mat, sy=1.0):
    d = {'t': 's', 'c': [round(cx, 1), round(cy, 1)], 'z': z, 'r': r, 'sy': sy, 'm': mat}
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
    """A window's sill and glass height, from the openings schedule (100 and 120 cm if it is not there)."""
    o = opening_of(b)
    return (o[3], o[4]) if o and o[3] > 0 else (100, 120)

ART = []           # framed art: (image, axis, wall face, side, from, to, bottom, top) in plan cm; images in ASSETS
ASSETS = os.path.join(HERE, 'assets')

def webp_uri(im, quality=80):
    """A picture as a WebP data URI: about a third the size of the same picture as JPEG, at the same look."""
    import io
    buf = io.BytesIO(); im.convert('RGB').save(buf, 'WEBP', quality=quality, method=6)
    return 'data:image/webp;base64,' + base64.b64encode(buf.getvalue()).decode()


def art_uris():
    """Small data URIs of the artworks for the web viewer."""
    from PIL import Image
    out = {}
    for name in sorted({a[0] for a in ART}):
        im = Image.open(os.path.join(ASSETS, f'art_{name}.jpg')).convert('RGB')
        im.thumbnail((384, 384))
        out[name] = webp_uri(im, 80)
    return out

LAYOUTS = {'existing': ('as_built', 'As built')}   # key: (plan function in build_plans, label shown in the viewer)

def windows_and_shutters():
    """Aluminium frames on the windows and sliders, and an exterior roller shutter on every opening:
    guide rails always, the curtain half down ('sh-half') or fully down ('sh-closed')."""
    for o in op.OPENINGS:
        code, _, (x0, y0, x1, y1), sill, hgt, (nx, ny) = o
        door = code.startswith('D')
        z0, top = (0, HEAD) if door else (sill, sill + hgt)
        along_x = bool(ny)
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2

        def fr(a0, a1, b0, b1, c0, c1, mat='frame', ctx=None):
            # a runs along the opening, b across the wall, c is height
            if along_x:
                box(a0, b0, a1, b1, c0, c1, mat, ctx)
            else:
                box(b0, a0, b1, a1, c0, c1, mat, ctx)
        a0, a1 = (x0, x1) if along_x else (y0, y1)
        c = cy if along_x else cx
        # frame: jambs at both ends; windows also get a head, a sill rail and a mullion (two casement sashes)
        fr(a0, a0 + 5, c - 3, c + 3, z0, top); fr(a1 - 5, a1, c - 3, c + 3, z0, top)
        if not door:
            fr(a0, a1, c - 3, c + 3, top - 5, top); fr(a0, a1, c - 3, c + 3, z0, z0 + 5)
            fr((a0 + a1) / 2 - 2.5, (a0 + a1) / 2 + 2.5, c - 3, c + 3, z0, top)
        # shutter on the outside face
        f = (y0 if ny < 0 else y1) if along_x else (x0 if nx < 0 else x1)
        sg = ny if along_x else nx
        b_out = sorted((f, f + sg * 7))
        fr(a0, a0 + 4, b_out[0], b_out[1], z0, top, 'frame'); fr(a1 - 4, a1, b_out[0], b_out[1], z0, top, 'frame')
        cur = sorted((f + sg * 3, f + sg * 5))
        fr(a0 + 2, a1 - 2, cur[0], cur[1], top - (top - z0) / 2, top, 'shutter', 'sh-half')
        fr(a0 + 2, a1 - 2, cur[0], cur[1], z0, top, 'shutter', 'sh-closed')


MATNAME = {'oak': 'oak', 'oakdark': 'dark oak', 'white': 'white lacquer', 'quartz': 'grey stone', 'travertine': 'travertine',
           'black': 'black', 'fabric': 'oatmeal fabric', 'linen': 'cream upholstery', 'ceramic': 'white ceramic',
           'steel': 'stainless steel', 'stone': 'stone', 'wallpaint': 'painted to match the wall', 'bronze': 'dark bronze',
           'satin': 'frameless satin-etched glass, oak top rail', 'fluted': 'fluted glass in an oak frame', 'slats': 'oak slats',
           'cstone': 'cream stone', 'flute': 'fluted oak', 'cane': 'cane'}
APPNAME = {'Fridge': 'Fridge', 'Oven·MW': 'Oven and microwave', 'DW': 'Dishwasher', 'W+D': 'Washer-dryer', 'Washer': 'Washing machine'}

def piece_name(r):
    """What the viewer calls a recorded piece, and what it is made of (None: not a piece)."""
    k, t = r['kind'], (r.get('label') or '')
    jm, jt = r.get('m') or 'oak', r.get('top') or 'travertine'
    if k == 'join':
        x0, y0, x1, y1 = r['box']; h = r.get('h') or 90; z0 = r.get('z0') or 0
        thin = min(x1 - x0, y1 - y0)
        if not t:
            if z0 >= 140:
                t = 'Hook rail' if h - z0 <= 6 and thin <= 8 else 'Wall cupboards' if h - z0 > 20 else 'Shelf'
            elif z0 >= 60:
                t = 'Breakfast bar' if jm == 'oak' and 75 <= z0 <= 85 else 'Hook rail' if h - z0 <= 6 and thin <= 8 else 'Worktop'
            elif h <= 95:
                t = 'Island' if thin >= 90 else 'Kitchen run' if r.get('top') else 'Counter'
            else:
                t = 'Oak wall panel' if thin <= 15 else 'Tall joinery'
        mt = MATNAME.get(jm, jm) + (', ' + MATNAME.get(jt, jt) + ' top' if (h or 90) <= 95 and z0 < 60 and t not in ('Breakfast bar', 'Desk') else '')
        t = {'Changing': 'Changing table', 'DB · keys': 'Fuse board and keys cupboard', 'Basket': 'Laundry basket pull-out',
             'Cleaning': 'Cleaning cupboard', 'Iron': 'Ironing board cabinet', 'Broom · vacuum': 'Broom and vacuum cupboard',
             'Bench · shoes': 'Shoe bench', 'Coats · DB · keys': 'Coats, fuse board and keys', 'BBQ · sink · prep': 'Outdoor kitchen',
             'Toys · guest wardrobe': 'Toys and guest wardrobe', 'Media · drawers': 'Media unit with drawers', 'W+D': 'Washer-dryer'}.get(t, t)
        return {'Sink': 'Sink run', 'TV': 'TV unit', 'Counter': 'Counter'}.get(t, t), mt
    if k == 'app':
        return APPNAME.get(t, t), {'Fridge': 'black, in oak joinery', 'Oven·MW': 'black, in oak joinery'}.get(t, 'appliance')
    if k == 'bed':
        x0, y0, x1, y1 = r['box']; w = min(x1 - x0, y1 - y0)
        return ('Double bed' if w >= 140 else 'Single bed'), 'oak frame, linen'
    if k == 'dtable':
        return 'Dining table', 'solid oak, two routed grooves'
    if k == 'stoneisland':
        return 'Island (trial)', 'cream stone, stone end; fluted oak base with an LED strip; black sink, dishwasher'
    if k == 'stonetable':
        return 'Dining table for 8 (trial)', 'cream stone, 8 cm edge, on the island\'s line, stone pedestal'
    if k == 'chair':
        if r.get('m') == 'cream':
            return 'Dining chair', 'cream upholstery, oak frame'
        if r.get('m') == 'cane':
            return 'Dining chair', 'oak frame, cane back, cream seat'
        return ('Armchair', 'oatmeal fabric') if r['s'] >= 60 else ('Chair', 'oak')
    if k == 'stool':
        return ('Counter stool', 'black leather, black frame') if r.get('m') == 'black' else ('Stool', 'oak')
    simple = {'sofa': ('Sofa', 'oatmeal fabric'), 'wc': ('WC', 'white ceramic'), 'basin': ('Basin and vanity', 'oak, white ceramic'),
              'shower': ('Shower', 'stone tray'), 'tub': ('Bath', 'white ceramic'), 'hob': ('Hob', 'black glass'), 'sink': ('Sink', 'black'),
              'rug': ('Rug', 'wool'), 'pouf': ('Pouf', 'fabric'), 'nightstand': ('Bedside table', 'oak'), 'cot': ('Cot', 'oak, linen'),
              'piano': ('Digital piano', 'white'), 'bench': ('Bench', 'white'), 'plant': ('Plant', 'stoneware pot'), 'tree': ('Tree', ''),
              'playhouse': ('Playhouse', 'white, oak roof'), 'pergola': ('Pergola', 'dark bronze aluminium'),
              'screen': ('Garden screen', 'oak slats'), 'roundtable': ('Round table', 'oak')}
    if k in simple:
        return simple[k]
    if k == 'rect':
        c = r.get('cls') or ''
        return {'wall': ('Wall', ''), 'wall neww': ('New wall', ''), 'col': ('Column', ''), 'island': ('Island', 'oak, travertine top'),
                'table': ('Table', 'oak'), 'tv': ('TV on the slatted oak wall', 'oak slats on felt'),
                'gpanel fluted': ('Fluted-glass screen', 'fluted glass in an oak frame'),
                'gpanel satin': ('Etched-glass sliding door', 'frameless satin-etched glass, oak top rail'),
                'gpanel opanel': ('Oak sliding panel', 'oak slats')}.get(c, (None, None))
    return None, None


SKIRT_H, SKIRT_T = 8, 1.2     # painted skirting, 8 cm high and 12 mm proud of the wall

def skirting(R):
    """White skirting along every stretch of wall that bounds a dry room's floor (not across doorways or open sides,
    not in the tiled bathrooms). Walls are found as wall boxes standing on the floor within 3 cm of the floor's edge."""
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
        for a, b in runs(x0, x1, [(w[0], w[3]) for w in walls if abs(w[4] - y0) <= 3]):   # wall beyond the top edge
            box(a, y0, b, y0 + SKIRT_T, 0, SKIRT_H, 'white')
        for a, b in runs(x0, x1, [(w[0], w[3]) for w in walls if abs(w[1] - y1) <= 3]):   # bottom edge
            box(a, y1 - SKIRT_T, b, y1, 0, SKIRT_H, 'white')
        for a, b in runs(y0, y1, [(w[1], w[4]) for w in walls if abs(w[3] - x0) <= 3]):   # left edge
            box(x0, a, x0 + SKIRT_T, b, 0, SKIRT_H, 'white')
        for a, b in runs(y0, y1, [(w[1], w[4]) for w in walls if abs(w[0] - x1) <= 3]):   # right edge
            box(x1 - SKIRT_T, a, x1, b, 0, SKIRT_H, 'white')

def lighting(layout, rooms=()):
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


# ---- the Styling switch: props drawn from the furniture the plan already has ('st-on', off by default)
def styling(R):
    """Cushions on sofas, a vase and a bowl on dining tables, books on coffee tables and desks, a throw and cushions
    on beds. Only furniture outside any trial or variant gets them, so nothing floats when a switch changes."""
    FURN[0] = 'loose'
    V = 'st-on'
    for r in R:
        if r['ctx'] or not r.get('furn'):
            continue
        k = r['kind']
        if k == 'sofa':
            for i, (x0, y0, x1, y1) in enumerate(r.get('back', [])):
                along_x = (x1 - x0) >= (y1 - y0)
                L = (x1 - x0) if along_x else (y1 - y0)
                n = max(1, min(3, int(L // 70)))
                for j in range(n):
                    c = (x0 if along_x else y0) + L * (j + .5) / n
                    mat = 'linen' if (i + j) % 2 else 'fabric'
                    if along_x:
                        cy = (y0 + y1) / 2; sg = 1 if cy < sum(q[1] for q in r['pts']) / len(r['pts']) else -1
                        box(c - 22, y1 if sg > 0 else y0 - 14, c + 22, (y1 + 14) if sg > 0 else y0, 42, 84, mat, V)
                    else:
                        cx = (x0 + x1) / 2; sg = 1 if cx < sum(q[0] for q in r['pts']) / len(r['pts']) else -1
                        box(x1 if sg > 0 else x0 - 14, c - 22, (x1 + 14) if sg > 0 else x0, c + 22, 42, 84, mat, V)
        elif k == 'dtable':
            x0, y0, x1, y1 = r['box']; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            cyl(cx, cy, 6, 75, 101, 'ceramic', V); cyl(cx + (25 if x1 - x0 > y1 - y0 else 0), cy + (0 if x1 - x0 > y1 - y0 else 25), 15, 75, 81, 'oakdark', V)
        elif k == 'rect' and r.get('cls') == 'table':
            x0, y0, x1, y1 = r['box']; cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            h = 75 if (x1 - x0) * (y1 - y0) > 12000 else 40
            for i, mat in enumerate(('linen', 'black', 'fabric')):
                box(cx - 13 + i, cy - 9, cx + 11 + i, cy + 8, h + i * 3, h + i * 3 + 3, mat, V)
        elif k == 'join' and 'Desk' in (r.get('label') or ''):
            x0, y0, x1, y1 = r['box']; h = r.get('h') or 75
            box(x0 + 8, y0 + 6, x0 + 30, y0 + 22, h, h + 9, 'linen', V)
            cyl(x1 - 15, (y0 + y1) / 2, 7, h, h + 2, 'black', V); cyl(x1 - 15, (y0 + y1) / 2, 1, h + 2, h + 38, 'black', V)
            cyl(x1 - 15, (y0 + y1) / 2, 10, h + 30, h + 44, 'linen', V)
        elif k == 'bed':
            x0, y0, x1, y1 = r['box']; head = r['head']
            if head in 'we':
                fx = x1 - 45 if head == 'w' else x0 + 5
                box(fx, y0 + 2, fx + 40, y1 - 2, 52, 56, 'fabric', V)
                hx = x0 + 58 if head == 'w' else x1 - 70
                for yy in ((y0 + y1) / 2 - 30, (y0 + y1) / 2 + 2):
                    box(hx, yy, hx + 12, yy + 28, 56, 86, 'linen', V)
            else:
                fy = y1 - 45 if head == 'n' else y0 + 5
                box(x0 + 2, fy, x1 - 2, fy + 40, 52, 56, 'fabric', V)
                hy = y0 + 58 if head == 'n' else y1 - 70
                for xx in ((x0 + x1) / 2 - 30, (x0 + x1) / 2 + 2):
                    box(xx, hy, xx + 28, hy + 12, 56, 86, 'linen', V)
    FURN[0] = None


# ---- the power plan: sockets, switches and data points on the nearest wall face ('pw', off by default)
POWER_Z = {'socket': 30, 'data': 30, 'switch': 105, 'keypad': 105}


def power(layout):
    """[{k: socket|switch|keypad|data, p: (x, y), t: label, z: cm}] for this layout (none by default)."""
    return []


def power_plan(layout, pieces):
    walls = [it['b'] for it in items if it['t'] == 'b' and it.get('g') == 'wall' and it['b'][2] == 0 and it['b'][5] >= 200]
    names = {'socket': 'Socket', 'switch': 'Light switch', 'keypad': 'Lighting keypad', 'data': 'Data point'}
    for q in power(layout):
        x, y = q['p']; z = q.get('z', POWER_Z.get(q['k'], 30)); best = None
        for b in walls:                                   # the nearest face of a wall, and the side the point is on
            cx, cy = min(max(x, b[0]), b[3]), min(max(y, b[1]), b[4]); d = math.hypot(x - cx, y - cy)
            if best is None or d < best[0]:
                best = (d, b)
        if not best or best[0] > 80:
            continue
        b = best[1]; w = 15 if q['k'] == 'keypad' else 8.5
        side = 'x0' if x < b[0] else 'x1' if x > b[3] else 'y0' if y < b[1] else 'y1' if y > b[4] else \
            min((x - b[0], 'x0'), (b[3] - x, 'x1'), (y - b[1], 'y0'), (b[4] - y, 'y1'))[1]   # drawn inside the wall: its nearer face
        y = min(max(y, b[1] + w / 2), b[4] - w / 2) if side[0] == 'x' and b[4] - b[1] >= w else y   # kept on the wall's length
        x = min(max(x, b[0] + w / 2), b[3] - w / 2) if side[0] == 'y' and b[3] - b[0] >= w else x
        bx = {'x0': (b[0] - 1.2, y - w / 2, b[0], y + w / 2), 'x1': (b[3], y - w / 2, b[3] + 1.2, y + w / 2),
              'y0': (x - w / 2, b[1] - 1.2, x + w / 2, b[1]), 'y1': (x - w / 2, b[4], x + w / 2, b[4] + 1.2)}[side]
        box(bx[0], bx[1], bx[2], bx[3], z - 4.25, z + 4.25, 'white', 'pw')
        pieces.append({'n': names.get(q['k'], 'Socket') + (' · ' + q['t'] if q.get('t') and q['k'] in ('socket', 'data') else ''),
                       'b': [round(v, 1) for v in (bx[0], bx[1], z - 4.25, bx[2], bx[3], z + 4.25)],
                       'mt': 'white, %d cm from the floor' % round(z), 'v': 'pw'})


# ---- hooks: what a project adds to the 3D of its own layouts (this engine's defaults do nothing special)
def before(layout):
    """Called after the layout is drawn and before its records are read: a project can draw 3D-only extras."""


def column_top(b):
    """How high a column stands (cm)."""
    return CEIL


def tv_wall(b, ctx):
    """A 'tv' rect: a screen on the wall."""
    x0, y0, x1, y1 = b
    box(x0, y0, x1, y1, 100, 180, 'black', ctx)


def pendant_style(it, layout):
    """A pendant light's style ('st') and height ('z'), by layout."""


def details(layout):
    """Built-in details of a layout that the plan does not draw (called with the furniture switch on 'built')."""


def grounds(layout):
    """The site around the apartment: boundary walls, fences."""


def art(layout):
    """Framed art (ART) hung in this layout."""
    for img, axis, face, sgn, a, b, z0, z1 in ART:
        items.append({'t': 'a', 'img': img, 'w': [axis, face, sgn], 'a': a, 'b': b, 'z': [z0, z1], 'f': 'loose'})


def labels_for(layout, rooms):
    """The names written over the model from above: the rooms, and the garden."""
    labels = [(r['n'], r['at'][0], r['at'][1]) for r in rooms]
    gp = apartment.garden_points()
    if gp:
        labels.append(('Garden', round(sum(q[0] for q in gp) / len(gp)), round(sum(q[1] for q in gp) / len(gp))))
    return labels


def garden():
    return [list(q) for q in apartment.garden_points()]


def site_rect():
    x0, y0, x1, y1 = apartment.extent(0)
    return [x0 - 300, y0 - 300, x1 + 300, y1 + 300]


def finish(out, layout):
    """The layout's scene, last chance to change it."""
    return out


def build(skip=(), doors_shut=False, layout='existing'):
    """skip: record kinds left out (a renderer that models those itself); 'rect:table' skips tables.
    layout: which plan to build (a key of LAYOUTS)."""
    bp.REC = []
    items.clear()                      # one shared list; each layout starts empty
    DOORN[0] = 0
    getattr(bp, LAYOUTS[layout][0])()
    before(layout)
    R = bp.REC
    windows = [r['box'] for r in R if r['kind'] == 'window']
    sliders = [r['box'] for r in R if r['kind'] == 'slider']
    labels = []

    def glazed_door(b, ctx=None):
        """Lintel, sill and head tracks and two sliding leaves: the outer one fixed, the inner one sliding over it.
        The Doors switch shows the inner leaf closed ('d-closed') or slid open ('d-open'), leaving half the width to
        walk through; with no doors it is gone."""
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
        fr(a0, a1, c - 3.5, c + 3.5, 0, 3, 'frame'); fr(a0, a1, c - 3.5, c + 3.5, HEAD - 5, HEAD, 'frame')   # tracks

        def leaf(l0, l1, cc, v):
            fr(l0 + 4, l1 - 4, cc - .8, cc + .8, 6, HEAD - 9, 'glass', v, 'glass')
            fr(l0, l0 + 4, cc - 1.6, cc + 1.6, 3, HEAD - 5, 'frame', v); fr(l1 - 4, l1, cc - 1.6, cc + 1.6, 3, HEAD - 5, 'frame', v)
            fr(l0, l1, cc - 1.6, cc + 1.6, 3, 7, 'frame', v); fr(l0, l1, cc - 1.6, cc + 1.6, HEAD - 9, HEAD - 5, 'frame', v)
        leaf(a0, mid + 2, c - 1.8, None)                      # fixed outer leaf
        DOORN[0] += 1; n = DOORN[0]
        leaf(mid - 2, a1, c + 1.8, 'd-closed.%d' % n)         # inner leaf, closed
        leaf(a0 + 6, mid + 8, c + 1.8, 'd-open.%d' % n)       # inner leaf, slid over the fixed one

    # a sliding door the plan draws straight into a wall gap, with no opening record, still needs its glass and lintel
    openings_ = [r['box'] for r in R if r['kind'] == 'opening']
    for b in sliders:
        if not any(overlaps(b, o) for o in openings_):
            glazed_door(b)

    pieces = []
    doors = [r for r in R if r['kind'] == 'door' and 'garden-door' not in r['cls']]

    def add_piece(r, n0):
        """One clickable piece per record: its name, material, true outer size and the switch group it shows with."""
        new = items[n0:]
        if not new:
            return
        name, mt = piece_name(r)
        if r['kind'] == 'opening':
            name, mt = ('Window', 'aluminium, dark bronze') if any(it['m'] == 'glass' and it['b'][2] > 50 for it in new if it['t'] == 'b') else \
                       ('Garden doors', 'sliding, aluminium, dark bronze') if any(it['m'] == 'glass' for it in new) else (None, None)
        elif r['kind'] == 'door':
            name, mt = {'door entry': ('Front door', 'dark oak'), 'door hidden': ('Hidden door', 'flush, painted to match the wall')}.get(r['cls'], ('Door', 'oak'))
        if not name:
            return
        byv = {}
        if r['kind'] == 'opening':                    # a window or garden door: one piece, sized by its glass when closed
            byv[None] = [it for it in new if it['m'] in ('glass', 'frame') and (it.get('v') in (None, 'w-closed') or str(it.get('v')).startswith('d-closed'))] or new
        else:
            for it in new:
                byv.setdefault(it.get('v'), []).append(it)
        for v, its in byv.items():

            bx = []
            for it in its:
                if it['t'] == 'b':
                    bx.append(it['b'])
                elif it['t'] == 'c':
                    (cx, cy), rr = it['c'], it['r']; bx.append([cx - rr, cy - rr, it['z'][0], cx + rr, cy + rr, it['z'][1]])
                elif it['t'] == 'p':
                    xs = [q[0] for q in it['p']]; ys = [q[1] for q in it['p']]; bx.append([min(xs), min(ys), it['z'][0], max(xs), max(ys), it['z'][1]])
                elif it['t'] == 's':
                    (cx, cy), rr = it['c'], it['r']; sy = it.get('sy', 1); bx.append([cx - rr, cy - rr, it['z'] - rr * sy, cx + rr, cy + rr, it['z'] + rr * sy])
            if not bx:
                continue
            b = [min(q[0] for q in bx), min(q[1] for q in bx), max(0, min(q[2] for q in bx)), max(q[3] for q in bx), max(q[4] for q in bx), max(q[5] for q in bx)]
            pc = {'n': name, 'b': [round(x, 1) for x in b]}
            if mt:
                pc['mt'] = mt
            if v:
                pc['v'] = v
            if its[0].get('f'):
                pc['f'] = its[0]['f']
            if pc.get('f') == 'loose' and v != 'st-on' and r['kind'] != 'opening':   # loose furniture can be moved in the viewer, as a trial
                for it in its:
                    it['pc'] = len(pieces)
            dn = [str(it.get('v'))[9:] for it in new if str(it.get('v')).startswith('d-closed.')]
            if r['kind'] == 'opening' and dn:              # a garden door: its sliding leaf can be opened on its own
                pc['dn'] = int(dn[0])
            pieces.append(pc)

    for r in R:
        k, ctx = r['kind'], (r['ctx'][-1] if r['ctx'] else None)
        FURN[0] = furn_class(r)
        n0 = len(items)
        if k in skip or (k == 'rect' and r.get('cls') == 'table' and 'rect:table' in skip):
            continue
        if k == 'rect':
            x0, y0, x1, y1 = r['box']; c = r['cls']
            if c in ('wall', 'wall neww'):
                box(x0, y0, x1, y1, 0, CEIL, 'wall', ctx, 'wall')
            elif c == 'col':
                box(x0, y0, x1, y1, 0, column_top(r['box']), 'wall', ctx, 'wall')
            elif c.startswith('z '):
                zone = c[2:]
                mat = {'pri': 'oakfloor', 'wetz': 'stone'}.get(zone, 'porcelain')
                box(x0, y0, x1, y1, 0, 1, mat, ctx, 'floor')
                items[-1]['zn'] = zone          # the viewer's Floors switch turns the dry zones to wood
                box(x0, y0, x1, y1, CEIL - 1, CEIL, 'ceiling', ctx, 'ceiling')
            elif c == 'island':
                box(x0 + 4, y0 + 4, x1 - 4, y1 - 4, 0, 86, 'oak', ctx)
                box(x0, y0, x1, y1, 86, 90, 'travertine', ctx)
            elif c == 'table':
                area = (x1 - x0) * (y1 - y0)
                h = 75 if area > 12000 else 40
                box(x0, y0, x1, y1, h - 4, h, 'oak', ctx)
                for lx, ly in ((x0 + 6, y0 + 6), (x1 - 12, y0 + 6), (x0 + 6, y1 - 12), (x1 - 12, y1 - 12)):
                    box(lx, ly, lx + 6, ly + 6, 0, h - 4, 'oakdark', ctx)
            elif c == 'tv':
                tv_wall(r['box'], ctx)
            elif c == 'gpanel satin':
                # Proposal 1 foyer: frameless satin-etched glass with polished edges, no oak stiles (1 Oct: the client
                # didn't want a wooden rod at its edge); a slim oak top rail carries it on the ceiling-fixed track
                box(x0, y0, x1, y1, 1, 240, 'satin', ctx, 'glass')
                box(x0, y0 - 1, x1, y1 + 1, 240, 244, 'oak', ctx)
            elif c == 'gpanel fluted':
                box(x0, y0, x1, y1, 1, 238, 'fluted', ctx, 'glass')
                # oak frame: top and bottom rails, stiles at the ends
                box(x0, y0, x1, y1, 0, 6, 'oak', ctx); box(x0, y0, x1, y1, 234, 240, 'oak', ctx)
                if (x1 - x0) > (y1 - y0):
                    box(x0, y0, x0 + 5, y1, 0, 240, 'oak', ctx); box(x1 - 5, y0, x1, y1, 0, 240, 'oak', ctx)
                else:
                    box(x0, y0, x1, y0 + 5, 0, 240, 'oak', ctx); box(x0, y1 - 5, x1, y1, 0, 240, 'oak', ctx)
                box(min(x0, x1) - 2, min(y0, y1) - 2, max(x0, x1) + 2, max(y0, y1) + 2, 240, 244, 'oakdark', ctx)
            elif c == 'gpanel opanel':
                box(x0, y0, x1, y1, 0, 270, 'slats', ctx, 'panel')
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
                # open: two casement sashes swung in square to the wall at the jambs ('w-open', with the Doors switch)
                o = next((o for o in op.OPENINGS if overlaps(o[2], r['box'])), None)
                if o:
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
            elif any(overlaps(r['box'], s) for s in sliders) or any(overlaps(r['box'], g) for g in GLAZED_DOORS):
                glazed_door(r['box'], ctx)
            else:
                box(x0, y0, x1, y1, HEAD, CEIL, 'wall', ctx, 'wall')
                # a door's frame: an oak lining in the reveal, 2 cm each side and over the head, 1 cm proud of both wall faces
                dr = next((d for d in doors if x0 - 3 <= d['hinge'][0] <= x1 + 3 and y0 - 3 <= d['hinge'][1] <= y1 + 3), None)
                if dr and dr['cls'] != 'door hidden':
                    fm = 'oakdark' if dr['cls'] == 'door entry' else 'oak'
                    if (x1 - x0) > (y1 - y0):
                        box(x0, y0 - 1, x0 + 2, y1 + 1, 0, HEAD, fm, ctx); box(x1 - 2, y0 - 1, x1, y1 + 1, 0, HEAD, fm, ctx)
                        box(x0, y0 - 1, x1, y1 + 1, HEAD - 2, HEAD, fm, ctx)
                    else:
                        box(x0 - 1, y0, x1 + 1, y0 + 2, 0, HEAD, fm, ctx); box(x0 - 1, y1 - 2, x1 + 1, y1, 0, HEAD, fm, ctx)
                        box(x0 - 1, y0, x1 + 1, y1, HEAD - 2, HEAD, fm, ctx)
        elif k == 'door':
            if 'garden-door' in r['cls']:
                continue
            (hx, hy), (lx, ly) = r['hinge'], r['leaf']
            mat = {'door entry': 'oakdark', 'door hidden': 'wallpaint'}.get(r['cls'], 'oak')

            def leaf(ex, ey, variant):
                handle = r['cls'] != 'door hidden'                    # the hidden door opens with a push latch
                if abs(ex - hx) > abs(ey - hy):
                    box(hx, hy - 2, ex, hy + 2, 0, HEAD - 2, mat, variant)
                    if handle:                                         # black lever both sides, 6 cm in from the free edge, at 1.05 m
                        sg = 1 if ex > hx else -1
                        box(ex - sg * 20, hy - 7, ex - sg * 6, hy + 7, 103.5, 106, 'black', variant)
                        box(ex - sg * 8, hy - 4, ex - sg * 4, hy + 4, 98, 111, 'black', variant)
                else:
                    box(hx - 2, hy, hx + 2, ey, 0, HEAD - 2, mat, variant)
                    if handle:
                        sg = 1 if ey > hy else -1
                        box(hx - 7, ey - sg * 20, hx + 7, ey - sg * 6, 103.5, 106, 'black', variant)
                        box(hx - 4, ey - sg * 8, hx + 4, ey - sg * 4, 98, 111, 'black', variant)
            if doors_shut:
                leaf(*r['shut'], ctx)
            elif r['cls'] == 'door hidden':                  # the flush hidden door always shows shut, in the wall plane
                leaf(*r['shut'], ctx or 'd-hidden')
            else:                                            # both states; the viewer's Doors switch picks one
                DOORN[0] += 1
                leaf(lx, ly, 'd-open.%d' % DOORN[0]); leaf(*r['shut'], 'd-closed.%d' % DOORN[0])
        elif k == 'join' and r.get('z0'):                  # wall-hung: cabinets, shelves, the ceiling airer
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, r['z0'], r['h'], r.get('m') or 'oak', ctx)
        elif k == 'join':
            x0, y0, x1, y1 = r['box']; t = r['label']; h = r.get('h')
            jm, jt = r.get('m') or 'oak', r.get('top') or 'travertine'
            if h is None:
                if any(w in t for w in TALL):
                    h = 240
                elif 'Desk' in t:
                    h = 75
                elif 'Bench' in t:
                    h = 45
                elif 'Changing' in t:
                    h = 90
                else:
                    h = 90
            if h <= 95 and 'Desk' not in t and 'Media' not in t:
                box(x0, y0, x1, y1, 0, h - 3, jm, ctx)
                box(x0, y0, x1, y1, h - 3, h, jt, ctx)
                if t == 'TV':                               # a 65" screen on the wall behind the low unit
                    if (y1 - y0) > (x1 - x0):
                        cy = (y0 + y1) / 2; box(x0 + 0.5, cy - 72, x0 + 4.5, cy + 72, h + 40, h + 122, 'black', ctx)
                    else:
                        cx = (x0 + x1) / 2; box(cx - 72, y0 + 0.5, cx + 72, y0 + 4.5, h + 40, h + 122, 'black', ctx)
            elif 'Desk' in t:
                box(x0, y0, x1, y1, h - 4, h, 'oak', ctx)
                box(x0, y0, x0 + 4, y1, 0, h - 4, 'oak', ctx) if (y1 - y0) > (x1 - x0) else box(x0, y0, x1, y0 + 4, 0, h - 4, 'oak', ctx)
                box(x1 - 4, y0, x1, y1, 0, h - 4, 'oak', ctx) if (y1 - y0) > (x1 - x0) else box(x0, y1 - 4, x1, y1, 0, h - 4, 'oak', ctx)
            else:
                box(x0, y0, x1, y1, 0, h, jm, ctx)
        elif k == 'app' and r.get('face') == 'e':         # in a tall oak bank to the ceiling, doors towards larger x
            x0, y0, x1, y1 = r['box']; t = r['label']
            box(x0, y0, x1, y1, 0, CEIL, 'oak', ctx)
            if t == 'Fridge':                               # black fridge doors, an oak cupboard above
                box(x1 - 0.5, y0 + 4, x1 + 1.5, y1 - 4, 2, 186, 'black', ctx)
                box(x1 - 0.5, (y0 + y1) / 2 - 0.3, x1 + 1.7, (y0 + y1) / 2 + 0.3, 2, 186, 'oakdark', ctx)
            else:                                           # oven at waist height, the microwave above it
                box(x1 - 0.5, y0 + 4, x1 + 1.5, y1 - 4, 85, 145, 'black', ctx)
                box(x1 - 0.5, y0 + 4, x1 + 1.5, y1 - 4, 150, 188, 'black', ctx)
        elif k == 'app':
            x0, y0, x1, y1 = r['box']; t = r['label']
            if t == 'Fridge':
                box(x0, y0, x1, y1, 0, 240, 'oak', ctx)
            elif t.startswith('Oven'):
                box(x0, y0, x1, y1, 0, 240, 'oak', ctx)
                box(x0 + 4, y0 - 1, x1 - 4, y0 + 2, 85, 145, 'black', ctx)
                box(x0 + 4, y0 - 1, x1 - 4, y0 + 2, 150, 188, 'black', ctx)
            elif t == 'W+D':
                box(x0, y0, x1, y1, 0, 180, 'ceramic', ctx)
            else:
                box(x0, y0, x1, y1, 0, 87, 'ceramic', ctx)
        elif k == 'bed':
            x0, y0, x1, y1 = r['box']; head = r['head']
            box(x0, y0, x1, y1, 0, 32, 'oak', ctx)
            box(x0 + 2, y0 + 2, x1 - 2, y1 - 2, 32, 52, 'linen', ctx)
            hb = {'w': (x0, y0, x0 + 8, y1), 'e': (x1 - 8, y0, x1, y1),
                  'n': (x0, y0, x1, y0 + 8), 's': (x0, y1 - 8, x1, y1)}[head]
            box(*hb, 0, 105, 'oak', ctx)
            # pillows against the headboard: two on a double, one on a single
            w = (y1 - y0) if head in 'we' else (x1 - x0)
            n = 2 if w >= 140 else 1
            pw = min(70, (w - 12) / n - 4)
            for i in range(n):
                a0 = (y0 if head in 'we' else x0) + (w - n * pw - (n - 1) * 6) / 2 + i * (pw + 6)
                if head == 'w':
                    box(x0 + 10, a0, x0 + 55, a0 + pw, 52, 66, 'linen', ctx)
                elif head == 'e':
                    box(x1 - 55, a0, x1 - 10, a0 + pw, 52, 66, 'linen', ctx)
                elif head == 'n':
                    box(a0, y0 + 10, a0 + pw, y0 + 55, 52, 66, 'linen', ctx)
                else:
                    box(a0, y1 - 55, a0 + pw, y1 - 10, 52, 66, 'linen', ctx)
            # duvet fold
            if head in 'ns':
                fy = y0 + (y1 - y0) * (0.55 if head == 'n' else 0.45)
                box(x0 + 2, fy - 12, x1 - 2, fy + 12, 52, 56, 'fabric', ctx)
            else:
                fx = x0 + (x1 - x0) * (0.55 if head == 'w' else 0.45)
                box(fx - 12, y0 + 2, fx + 12, y1 - 2, 52, 56, 'fabric', ctx)
        elif k == 'dtable':                                 # oak dining table: rounded ends, two grooves, legs set in
            x0, y0, x1, y1 = r['box']; rr = r['r']; long_y = (y1 - y0) > (x1 - x0)
            poly(rounded_rect(x0, y0, x1, y1, rr), 71, 75, 'oak', ctx)
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            for d in (-10, 10):
                if long_y:
                    box(mx + d - 0.4, y0 + 26, mx + d + 0.4, y1 - 26, 74.6, 75.2, 'oakdark', ctx)
                else:
                    box(x0 + 26, my + d - 0.4, x1 - 26, my + d + 0.4, 74.6, 75.2, 'oakdark', ctx)
            ix, iy = (8, 24) if long_y else (24, 8)
            for lx, ly in ((x0 + ix, y0 + iy), (x1 - ix - 8, y0 + iy), (x0 + ix, y1 - iy - 8), (x1 - ix - 8, y1 - iy - 8)):
                box(lx, ly, lx + 8, ly + 8, 0, 71, 'oak', ctx)
            box(x0 + ix + 2, y0 + iy + 2, x1 - ix - 2, y1 - iy - 2, 63, 71, 'oak', ctx)      # apron
        elif k == 'stoneisland':                            # island trial: a square cream-stone island; the table carries on from its stone end
            x0, y0, x1, y1 = r['box']; tz = r['top']
            box(x0, y0, x1, y1, tz - 10, tz, 'cstone', ctx)                          # 10 cm slab
            box(x1 - 10, y0, x1, y1, 0, tz - 10, 'cstone', ctx)                      # stone end down to the floor, where the table meets it
            box(x0 + 4, y0 + 4, x1 - 10, y1 - 4, 0, tz - 10, 'flute', ctx)           # square fluted oak base, set in under the slab
            box(x0 + 4, y0 + 2.8, x1 - 10, y0 + 3.8, tz - 11.5, tz - 10.5, 'led', ctx)   # LED strip under the slab: living side
            box(x0 + 2.8, y0 + 4, x0 + 3.8, y1 - 4, tz - 11.5, tz - 10.5, 'led', ctx)    # and the free end
            sx0, sy0, sx1, sy1 = r['sink']; mx = (sx0 + sx1) / 2                     # black double sink, the tap behind it (as in the design)
            box(sx0, sy0, sx1, sy1, tz, tz + 0.6, 'black', ctx); box(mx - 0.6, sy0, mx + 0.6, sy1, tz + 0.2, tz + 0.8, 'cstone', ctx)
            cyl(mx, sy0 - 7, 1.4, tz, tz + 34, 'black', ctx); box(mx - 1.2, sy0 - 7, mx + 1.2, sy0 + 16, tz + 31, tz + 34, 'black', ctx)
        elif k == 'stonetable':                             # island trial: stone table, square where it runs into the island, round at the free end
            import math
            x0, y0, x1, y1 = r['box']; h = r['h']; rr = r['r']; cy = (y0 + y1) / 2
            pts = [(x0, y1), (x0, y0)] + [(x1 - rr + rr * math.cos(math.radians(a)), cy + rr * math.sin(math.radians(a))) for a in range(-90, 91, 10)]
            poly(pts, h - 8, h, 'cstone', ctx)
            box(*r['ped'], 0, h - 8, 'cstone', ctx)
        elif k == 'chair' and r.get('m') == 'cane':       # oak frame, a woven cane back between two posts, a cream seat pad
            cx, cy = r['c']; s = r['s'] / 2; back = r['back']
            for lx, ly in ((cx - s + 3, cy - s + 3), (cx + s - 7, cy - s + 3), (cx - s + 3, cy + s - 7), (cx + s - 7, cy + s - 7)):
                box(lx, ly, lx + 4, ly + 4, 0, 42, 'oak', ctx)
            box(cx - s + 2, cy - s + 2, cx + s - 2, cy + s - 2, 40, 43, 'oak', ctx)                  # seat frame
            box(cx - s + 4, cy - s + 4, cx + s - 4, cy + s - 4, 43, 49, 'linen', ctx)                # seat pad
            if back in 'ns':
                yb = cy - s + 3 if back == 'n' else cy + s - 7
                box(cx - s + 3, yb, cx - s + 7, yb + 4, 42, 86, 'oak', ctx); box(cx + s - 7, yb, cx + s - 3, yb + 4, 42, 86, 'oak', ctx)
                box(cx - s + 7, yb + 1.5, cx + s - 7, yb + 2.5, 56, 82, 'cane', ctx); box(cx - s + 3, yb, cx + s - 3, yb + 4, 82, 88, 'oak', ctx)
            else:
                xb = cx - s + 3 if back == 'w' else cx + s - 7
                box(xb, cy - s + 3, xb + 4, cy - s + 7, 42, 86, 'oak', ctx); box(xb, cy + s - 7, xb + 4, cy + s - 3, 42, 86, 'oak', ctx)
                box(xb + 1.5, cy - s + 7, xb + 2.5, cy + s - 7, 56, 82, 'cane', ctx); box(xb, cy - s + 3, xb + 4, cy + s - 3, 82, 88, 'oak', ctx)
        elif k == 'chair' and r.get('m') == 'cream':      # upholstered dining chair on an oak frame
            cx, cy = r['c']; s = r['s'] / 2; back = r['back']
            for lx, ly in ((cx - s + 3, cy - s + 3), (cx + s - 7, cy - s + 3), (cx - s + 3, cy + s - 7), (cx + s - 7, cy + s - 7)):
                box(lx, ly, lx + 4, ly + 4, 0, 42, 'oak', ctx)
            box(cx - s + 2, cy - s + 2, cx + s - 2, cy + s - 2, 42, 49, 'linen', ctx)
            bb = {'n': (cx - s + 3, cy - s + 1, cx + s - 3, cy - s + 8), 's': (cx - s + 3, cy + s - 8, cx + s - 3, cy + s - 1),
                  'w': (cx - s + 1, cy - s + 3, cx - s + 8, cy + s - 3), 'e': (cx + s - 8, cy - s + 3, cx + s - 1, cy + s - 3)}[back]
            box(*bb, 49, 88, 'linen', ctx)
        elif k == 'chair':
            cx, cy = r['c']; s = r['s'] / 2; back = r['back']
            lounge = r['s'] >= 60
            seat = 40 if lounge else 45
            mat = 'fabric' if lounge else 'oak'
            box(cx - s, cy - s, cx + s, cy + s, 0 if lounge else seat - 5, seat, mat, ctx)
            bb = {'n': (cx - s, cy - s, cx + s, cy - s + 7), 's': (cx - s, cy + s - 7, cx + s, cy + s),
                  'w': (cx - s, cy - s, cx - s + 7, cy + s), 'e': (cx + s - 7, cy - s, cx + s, cy + s)}[back]
            box(*bb, seat, 78 if lounge else 85, mat, ctx)
            if not lounge:
                for lx, ly in ((cx - s + 3, cy - s + 3), (cx + s - 6, cy - s + 3), (cx - s + 3, cy + s - 6), (cx + s - 6, cy + s - 6)):
                    box(lx, ly, lx + 3, ly + 3, 0, seat - 5, 'oakdark', ctx)
        elif k == 'stool':
            cx, cy = r['c']
            if r.get('m') == 'black':                      # counter stool: black leather bucket seat with a low back, black sled frame
                cyl(cx, cy, 20, 60, 66, 'black', ctx)
                for dx, dy in ((-15, -15), (15, -15), (-15, 15), (15, 15)):
                    box(cx + dx - 1, cy + dy - 1, cx + dx + 1, cy + dy + 1, 0, 60, 'black', ctx)
                box(cx - 16, cy - 16, cx + 16, cy + 16, 22, 23.5, 'black', ctx)      # footrest frame
                f = r.get('face')
                if f:
                    bx = {'s': (cx - 17, cy - 21, cx + 17, cy - 18), 'n': (cx - 17, cy + 18, cx + 17, cy + 21),
                          'w': (cx + 18, cy - 17, cx + 21, cy + 17), 'e': (cx - 21, cy - 17, cx - 18, cy + 17)}[f]
                    box(*bx, 66, 88, 'black', ctx)
            else:
                cyl(cx, cy, 19, 60, 65, 'oak', ctx); cyl(cx, cy, 3, 0, 60, 'oakdark', ctx)
        elif k == 'sofa':
            poly(r['pts'], 0, 42, 'fabric', ctx)
            for b in r.get('back', []):
                box(*b, 42, 80, 'fabric', ctx)
        elif k == 'wc':
            cx, cy = r['c']
            box(cx - 18, cy - 26, cx + 18, cy + 26, 0, 40, 'ceramic', ctx)
        elif k == 'basin':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 30, 82, 'oak', ctx); box(x0, y0, x1, y1, 82, 88, 'ceramic', ctx)
        elif k == 'shower':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 0, 4, 'stone', ctx)
        elif k == 'tub':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 0, 55, 'ceramic', ctx)
        elif k == 'hob':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 90, 91, 'black', ctx)
        elif k == 'sink':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 89, 90.6, 'steel', ctx)
        elif k == 'pendant':
            cx, cy = r['c']
            it = {'t': 'l', 'c': [cx, cy], 'z': 182}
            if ctx:
                it['v'] = ctx
            if r.get('st') == 'dome':
                it['st'] = 'dome'                           # woven rattan dome, its rim 77 cm over the table (island trial)
                it['z'] = 152
            else:
                pendant_style(it, layout)
            items.append(it)
        elif k == 'rug':
            cx, cy = r['c']
            cyl(cx, cy, r['r'], 1, 2, 'rug', ctx)
        elif k == 'roundtable':
            cx, cy = r['c']
            cyl(cx, cy, r['r'], r['h'] - 4, r['h'], 'oak', ctx); cyl(cx, cy, 8, 0, r['h'] - 4, 'oakdark', ctx)
        elif k == 'pouf':
            cx, cy = r['c']
            cyl(cx, cy, r['r'], 0, 42, 'fabric', ctx)
        elif k == 'nightstand':
            box(*r['box'], 0, 55, 'oak', ctx)
        elif k == 'cot':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 25, 40, 'linen', ctx)
            for bb in ((x0, y0, x1, y0 + 4), (x0, y1 - 4, x1, y1), (x0, y0, x0 + 4, y1), (x1 - 4, y0, x1, y1)):
                box(*bb, 0, 90, 'oak', ctx)
        elif k == 'piano':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 0, 78, 'white', ctx)
            box(x0 - 2, y0 + 5, x0 + 14, y1 - 5, 74, 80, 'keys', ctx)
        elif k == 'bench':
            box(*r['box'], 0, 48, 'white', ctx)
        elif k == 'lawn':
            poly(r['pts'], -12, -10, 'grass')
        elif k == 'paving':
            mat = {'terrace': 'porcelain', 'deck': 'oakfloor', 'gravel': 'gravel'}[r['surf']]
            poly(r['pts'], -12, 0 if r['surf'] != 'gravel' else -9, mat)
        elif k == 'plantbed':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, -12, 25, 'soil')
            if r['hedge']:
                box(x0 + 10, y0 + 10, x1 - 10, y1 - 10, 25, r['hedge'], 'leaf')
        elif k == 'plant':                                  # indoor plant: stoneware pot and a leafy head
            cx, cy = r['c']; rr = r['r']; h = r['h']
            cyl(cx, cy, rr, 0, 48, 'ceramic', ctx)
            sphere(cx, cy, h * 0.62, rr * 1.35, 'leaf', 1.3)
            sphere(cx + rr * 0.4, cy - rr * 0.3, h * 0.82, rr * 1.0, 'leaf', 1.2)
            sphere(cx - rr * 0.35, cy + rr * 0.25, h * 0.45, rr * 0.9, 'leaf', 1.1)
        elif k == 'tree':
            cx, cy = r['c']; rr = r['r']; h = r['h']
            cyl(cx, cy, 9, 0, h * 0.55, 'trunk')
            sphere(cx, cy, h * 0.72, rr * 0.9, 'leaf', 0.8)
            sphere(cx + rr * 0.35, cy - rr * 0.2, h * 0.62, rr * 0.6, 'leaf', 0.8)
            sphere(cx - rr * 0.3, cy + rr * 0.3, h * 0.66, rr * 0.65, 'leaf', 0.8)
        elif k == 'screen':
            x0, y0, x1, y1 = r['box']
            for sx in range(int(x0), int(x1), 12):
                box(sx, y0, sx + 7, y1, 0, r['h'], 'oak')
        elif k == 'pergola':
            for x0, y0, x1, y1 in r['roof']:
                box(x0, y0, x1, y0 + 12, 262, 280, 'bronze', ctx); box(x0, y1 - 12, x1, y1, 262, 280, 'bronze', ctx)
                for sx in range(int(x0) + 20, int(x1) - 10, 30):
                    box(sx, y0, sx + 6, y1, 266, 280, 'bronze', ctx)
            for px, py in r['posts']:
                box(px - 6, py - 6, px + 6, py + 6, 0, 280, 'bronze', ctx)
        elif k == 'awning':
            # A: retractable fabric roof on a slim bronze frame; B: cassette awnings on the bedroom façade.
            # 'aw-frame' shows whenever the shades are chosen, 'aw-out' only while the fabric is out.
            roof = r['name'] == 'A'
            z = 262 if roof else 246
            for (x0, y0, x1, y1), fy in zip(r['rects'], r['facade']):
                box(x0, fy - 22, x1, fy, 262, 280, 'bronze', 'aw-frame')                  # cassette on the wall
                box(x0 + 2, y0, x1 - 2, fy - 22, z, z + 2, 'canvas', 'aw-out')           # the fabric
                box(x0, y0, x1, y0 + 8, z - 10, z + 2, 'bronze', 'aw-out')               # front bar
                if roof:
                    box(x0, y0, x0 + 8, fy - 22, z - 6, z, 'bronze', 'aw-frame')        # guide rails
                    box(x1 - 8, y0, x1, fy - 22, z - 6, z, 'bronze', 'aw-frame')
            for px, py in r['posts']:
                box(px - 5, py - 5, px + 5, py + 5, 0, z, 'bronze', 'aw-frame')
        elif k == 'playhouse':
            x0, y0, x1, y1 = r['box']
            box(x0, y0, x1, y1, 0, 110, 'white')
            box(x0 - 8, y0 - 8, x1 + 8, y1 + 8, 110, 125, 'oak')
        add_piece(r, n0)

    FURN[0] = None
    skirting(R)
    FURN[0] = 'built'
    details(layout)
    FURN[0] = None
    grounds(layout)

    windows_and_shutters()
    styling(R)
    power_plan(layout, pieces)

    art(layout)

    rooms = [{'n': r['name'], 'at': list(r['at']), 'r': list(r['rect']) if r['rect'] else None, 'd': r['dims']}
             for r in R if r['kind'] == 'room' and r.get('dims')]
    x0, y0, x1, y1 = apartment.extent(0)
    out = {'items': list(items), 'labels': labels_for(layout, rooms), 'rooms': rooms, 'pieces': pieces,
           'lights': lighting(layout, rooms), 'garden': garden(), 'site': site_rect(), 'bounds': [x0, y0, x1, y1]}
    return finish(out, layout)

_ENGINE = os.path.dirname(os.path.abspath(sys._getframe().f_code.co_filename))


def viewer_html(overrides=None):
    """The viewer page (tools/viewer.html). Places a project may word or set up differently are marked in it as
    <@name>default</@name>; overrides maps a name to the project's own text, and every other mark keeps its default."""
    import re
    src = open(os.path.join(_ENGINE, 'viewer.html'), encoding='utf-8').read()
    ov = overrides or {}
    return re.sub(r'<@(v\d+)>(.*?)</@\1>', lambda m: ov.get(m.group(1), m.group(2)), src, flags=re.S)


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
    tpl = viewer_html()
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
