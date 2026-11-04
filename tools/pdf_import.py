#!/usr/bin/env python3
"""Read an apartment's plan from a PDF drawn by CAD (a vector PDF, not a scan) and write a draft apartment.json with
a check page, through the same importer as DWG and DXF.

A PDF has no layers, so the plan is read from how it is drawn:
  scale        the title block's "1 : 50" (or --scale 1:50), checked against the dimensions' own numbers; a sheet without
               one takes it from the dimensions (in mm, cm or m: whichever gives a usual scale, 1:20 to 1:200)
  walls        solid dark fills (wall hatches), with the pieces of one wall on either side of an opening kept together;
               a small copy of the plan elsewhere on the sheet (a key plan) is left out
  columns      compact solid fills at least 18 cm across both ways, or light fills hatched with slanted lines
  openings     the frame CAD draws for each door and window: a jamb line across the wall at each end and the wall's
               faces drawn between them (dashed for a door, a full line for glass); the tag beside it (W03, D06)
               says window or door. A drawing without frames falls back to gaps between two pieces of one wall
  rooms        the room names written inside the plan; a name written outside it follows its leader line in
  dimensions   numbers on a thin line, measured between the tick marks either side of them

The PDF is rebuilt as a plain DXF (walls, columns, door and window openings as blocks, tags, room names, dimensions)
and read by dxf_import.py, so rooms, door swings, the openings schedule and the check page are the same as for a DWG.
What a PDF cannot say (door swings, sills, heights, the site) is assumed and listed on the check page.

  python3 tools/pdf_import.py plan.pdf OUTDIR [--page 1] [--scale 1:50] [--name ..] [--lat .. --lon .. --facing ..]
"""
import argparse, json, math, os, re, statistics, sys
import numpy as np
import pymupdf
import ezdxf
from ezdxf.enums import TextEntityAlignment

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import dxf_import as dx  # noqa: E402

TAG = re.compile(r'^[DW]-?\d{1,3}[A-Z]?$')
PT_CM = 2.54 / 72                                     # one PDF point on paper, in cm


def lum(c):
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] if c else 1


def paths(g):
    """The closed outlines of a fill, as lists of points (pt)."""
    out, cur = [], []
    for it in g['items']:
        if it[0] == 're':
            r = it[1]; out.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)])
        elif it[0] == 'qu':
            q = it[1]; out.append([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)])
        elif it[0] == 'l':
            a, b = it[1], it[2]
            if not cur:
                cur = [(a.x, a.y)]
            elif math.hypot(cur[-1][0] - a.x, cur[-1][1] - a.y) > .05:
                if len(cur) > 2:
                    out.append(cur)
                cur = [(a.x, a.y)]
            cur.append((b.x, b.y))
        elif it[0] == 'c':
            a, b = it[1], it[-1]
            if not cur:
                cur = [(a.x, a.y)]
            cur.append((b.x, b.y))
    if len(cur) > 2:
        out.append(cur)
    return out


def framed_openings(drawings, P, k, inreg, M):
    """Openings drawn as CAD draws them in plan: a jamb line across the wall at each end (where the wall fill stops)
    and the two wall faces drawn between the jambs, dashed for a door and with a full line for glass.
    Returns [(box in cm, glass)]."""
    H, W = M.shape
    hs, vs = [], []                                   # (fixed coordinate, start, end) in cm
    for g in drawings:
        if g['type'] not in ('s', 'fs'):
            continue
        for it in g['items']:
            if it[0] != 'l':
                continue
            a, b = it[1], it[2]
            if not inreg(a.x, a.y):
                continue
            (x0, y0), (x1, y1) = P(a.x, a.y), P(b.x, b.y)
            if abs(y0 - y1) < .05 and abs(x0 - x1) > .3:
                hs.append(((y0 + y1) / 2, min(x0, x1), max(x0, x1)))
            elif abs(x0 - x1) < .05 and abs(y0 - y1) > .3:
                vs.append(((x0 + x1) / 2, min(y0, y1), max(y0, y1)))

    def wall_at(x, y):
        i, j = int(math.floor(y)), int(math.floor(x))
        return 0 <= i < H and 0 <= j < W and M[i, j]

    def covered(lines, c, a, b):
        """How much of a..b along the line at c is drawn, and whether one stroke draws (nearly) all of it."""
        parts = sorted((max(s, a), min(e, b)) for f, s, e in lines if abs(f - c) < .3 and e > a and s < b)
        tot, end, full = 0, a, False
        for s, e in parts:
            if e - s >= .9 * (b - a):
                full = True
            if e > end:
                tot += e - max(s, end); end = e
        return tot / (b - a), full

    out = []
    for jambs, faces, across in ((vs, hs, True), (hs, vs, False)):
        # jambs across a wall: 5 to 45 cm long, wall on one side and none on the other
        groups = {}
        for c, s, e in jambs:
            if not 5 <= e - s <= 45:
                continue
            m = (s + e) / 2
            side = (lambda d: wall_at(c + d, m)) if across else (lambda d: wall_at(m, c + d))
            if side(-1.5) and not side(1.5):
                groups.setdefault((round(s * 2) / 2, round(e * 2) / 2), []).append((c, 'start'))
            elif side(1.5) and not side(-1.5):
                groups.setdefault((round(s * 2) / 2, round(e * 2) / 2), []).append((c, 'end'))
        for (s, e), js in groups.items():
            js = sorted(set(js))
            for (a, ka), (b, kb) in zip(js, js[1:]):
                if ka != 'start' or kb != 'end' or not 40 <= b - a <= 400:
                    continue
                c1, f1 = covered(faces, s, a, b)
                c2, f2 = covered(faces, e, a, b)
                if c1 < .4 or c2 < .4:
                    continue
                box = (a, s, b, e) if across else (s, a, e, b)
                inner = M[int(math.ceil(box[1])):int(math.floor(box[3])), int(math.ceil(box[0])):int(math.floor(box[2]))]
                if inner.size and inner.mean() > .05:
                    continue
                out.append((box, f1 or f2))
    return out


def read_pdf(path, page=1, scale=None):
    doc = pymupdf.open(path)
    pg = doc[page - 1]
    report = []
    drawings = pg.get_drawings()
    spans, nums = [], []
    for b in pg.get_text('dict')['blocks']:
        for ln in b.get('lines', []):
            text = ' '.join(s['text'].strip() for s in ln['spans'] if s['text'].strip())
            if text:
                x0 = min(s['bbox'][0] for s in ln['spans']); y0 = min(s['bbox'][1] for s in ln['spans'])
                x1 = max(s['bbox'][2] for s in ln['spans']); y1 = max(s['bbox'][3] for s in ln['spans'])
                spans.append({'t': text, 'box': (x0, y0, x1, y1), 'vertical': abs(ln['dir'][1]) > .5})
            for sp in ln['spans']:                    # a chain of dimensions may come as one line of several numbers
                if re.fullmatch(r'\d+(\.\d+)?', sp['text'].strip()):
                    nums.append({'t': sp['text'].strip(), 'box': tuple(sp['bbox']), 'vertical': abs(ln['dir'][1]) > .5})

    # walls: dark solid fills. The plan is where they are; the title block and legends lie outside it.
    fills = [g for g in drawings if g['type'] in ('f', 'fs') and g.get('fill') and lum(g['fill']) < .3]
    if not fills:
        raise SystemExit('No solid dark fills found: this PDF does not show its walls filled (or it is a scan). '
                         'Export the plan from CAD with the walls hatched solid, or use the DWG.')
    # a sheet may also show the plan small (a key plan in the title block) or a black north arrow: group the fills
    # that touch or nearly touch and keep the group that spans the most paper
    boxes = [g['rect'] for g in fills]
    parent = list(range(len(fills)))
    find = lambda i: i if parent[i] == i else find(parent[i])
    near = lambda a, b, d: a.x0 - d <= b.x1 and b.x0 - d <= a.x1 and a.y0 - d <= b.y1 and b.y0 - d <= a.y1
    for i, a in enumerate(boxes):
        for j in range(i):
            b = boxes[j]
            # touching, or two pieces of one wall either side of an opening: the same thickness on the same line,
            # up to 150 pt apart (2.6 m at 1:50)
            inline = near(a, b, 150) and any(abs(a[k] - b[k]) < .5 and abs(a[k + 2] - b[k + 2]) < .5 and a[k + 2] - a[k] < 25
                                             for k in (0, 1))
            if near(a, b, 30) or inline:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(fills)):
        groups.setdefault(find(i), []).append(i)
    span = lambda ix: ((max(boxes[i].x1 for i in ix) - min(boxes[i].x0 for i in ix))
                       * (max(boxes[i].y1 for i in ix) - min(boxes[i].y0 for i in ix)))
    keep = max(groups.values(), key=span)
    if len(groups) > 1:
        report.append(f'{len(fills) - len(keep)} dark fill(s) away from the plan (a key plan, a north arrow) were left out.')
    fills = [fills[i] for i in keep]
    polys = [p for g in fills for p in paths(g)]
    xs = [x for p in polys for x, _ in p]; ys = [y for p in polys for _, y in p]
    region = (min(xs) - 120, min(ys) - 120, max(xs) + 120, max(ys) + 120)
    inreg = lambda x, y: region[0] <= x <= region[2] and region[1] <= y <= region[3]

    # the scale: the title block's 1:N, checked against the dimensions (a number on a line of matching length)
    k_title = None
    for s in spans:
        m = re.search(r'1\s*:\s*(\d{1,4})\b', s['t'])
        if m and not inreg((s['box'][0] + s['box'][2]) / 2, (s['box'][1] + s['box'][3]) / 2):
            k_title = int(m.group(1)) * PT_CM
            report.append(f'Scale 1:{m.group(1)} read from the title block.')
            break
    if scale:
        k_title = int(scale.split(':')[1]) * PT_CM
    widths = sorted({round(g.get('width') or 0, 2) for g in drawings if g['type'] == 's'})
    thin = widths[0] if widths else 0
    segs = []
    for g in drawings:
        if g['type'] != 's' or round(g.get('width') or 0, 2) != thin:
            continue
        for it in g['items']:
            if it[0] == 'l':
                a, b = it[1], it[2]
                if (abs(a.x - b.x) < .05 or abs(a.y - b.y) < .05) and math.hypot(a.x - b.x, a.y - b.y) > 4 and inreg(a.x, a.y):
                    segs.append((a.x, a.y, b.x, b.y))
    # tick marks: the ends of short slanted strokes (or dots) where they sit on a dimension line
    ticks = [q for g in drawings if g['type'] == 's' for it in g['items'] if it[0] == 'l'
             and abs(it[1].x - it[2].x) > .3 and abs(it[1].y - it[2].y) > .3 and math.hypot(it[1].x - it[2].x, it[1].y - it[2].y) < 15
             for q in ((it[1].x, it[1].y), (it[2].x, it[2].y)) if inreg(*q)]
    dims, ratios = [], []
    for s in nums:
        v = float(s['t']); cx, cy = (s['box'][0] + s['box'][2]) / 2, (s['box'][1] + s['box'][3]) / 2
        if not inreg(cx, cy) or v <= 0:
            continue
        best = None
        for x0, y0, x1, y1 in segs:
            horiz = abs(y0 - y1) < .05
            if horiz == s['vertical']:
                continue
            lo, hi = (min(x0, x1), max(x0, x1)) if horiz else (min(y0, y1), max(y0, y1))
            c, t = (y0, cx) if horiz else (x0, cy)
            off = abs((cy if horiz else cx) - c)
            half = (s['box'][3] - s['box'][1] if horiz else s['box'][2] - s['box'][0]) / 2
            if off >= half + 6 or not lo < t < hi:      # the number sits on or just beside its line
                continue
            # a chain of dimensions is one line: the number measures between the ticks either side of it
            on = sorted({round(qx if horiz else qy, 2) for qx, qy in ticks if abs((qy if horiz else qx) - c) < .15 and lo - .1 <= (qx if horiz else qy) <= hi + .1} | {lo, hi})
            a = max((u for u in on if u <= t), default=lo); b = min((u for u in on if u >= t), default=hi)
            seg = (a, c, b, c) if horiz else (c, a, c, b)
            if best is None or off < best[0]:
                best = (off, seg, b - a)
        if best and best[2] > 0:
            ratios.append((v, best[2], best[1]))
    k_dims = statistics.median([v / L for v, L, _ in ratios]) if ratios else None
    unit_cm = 1
    if k_dims and k_title:
        r = k_dims / k_title                          # numbers in cm give 1, in mm 10, in m 0.01
        for u, f in (('cm', 1), ('mm', 10), ('m', .01)):
            if abs(r / f - 1) < .03:
                unit_cm = 1 / f; report.append(f'The dimensions are written in {u} and agree with the scale.'); break
        else:
            report.append(f'The dimensions do not agree with the title block\'s scale (ratio {r:.3f}); the title block was used.')
    if k_dims and not k_title:
        # no scale on the sheet: the dimensions give it, written in mm, cm or m; the one that makes a drawing scale
        # architects use (1:20 to 1:200) is taken
        std = (20, 25, 50, 75, 100, 125, 200)
        f, u = min(((f, u) for f, u in ((1, 'cm'), (.1, 'mm'), (100, 'm'))),
                   key=lambda fu: min(abs(k_dims * fu[0] / PT_CM / n - 1) for n in std))
        n = k_dims * f / PT_CM
        if min(abs(n / m - 1) for m in std) < .03:
            unit_cm = f; k_dims *= f
            report.append(f'No scale on the sheet: the dimensions, written in {u}, give 1:{round(n)}.')
    k = k_title or (k_dims * 1 if k_dims else None)
    if not k:
        raise SystemExit('The scale could not be found: give it with --scale 1:50.')
    across = max(region[2] - region[0], region[3] - region[1]) * k / 100
    if not 2 <= across <= 200:
        raise SystemExit(f'At 1:{round(k / PT_CM)} the plan would be {across:.0f} m across, so the scale is wrong: '
                         'give it with --scale 1:50.')
    for v, L, seg in ratios:
        if abs(v * unit_cm / (L * k) - 1) < .02:
            dims.append((seg, v * unit_cm))

    # the plan's origin: the region's corner, nudged by under a centimetre so that the walls' edges land on whole
    # centimetres as they were drawn (a PDF stores points, so 1:50 gives cm with a fraction of noise)
    def phase(vals):
        a = [2 * math.pi * ((v * k) % 1) for v in vals]
        return math.atan2(sum(map(math.sin, a)), sum(map(math.cos, a))) / (2 * math.pi)
    ox = region[0] + phase([x - region[0] for x in xs]) / k
    oy = region[1] + phase([y - region[1] for y in ys]) / k
    # PDF pt -> plan cm (y already runs down). A PDF keeps a few thousandths of a point of noise from CAD's export,
    # so 613 cm comes back as 612.996: values are kept to the millimetre, which the drawing itself never goes below
    P = lambda x, y: (round((x - ox) * k, 1), round((y - oy) * k, 1))

    # columns: compact fills, at least 18 cm across both ways; the rest are walls
    walls, cols = [], []
    for p in polys:
        q = [P(*a) for a in p]
        w = max(x for x, _ in q) - min(x for x, _ in q); h = max(y for _, y in q) - min(y for _, y in q)
        (cols if min(w, h) >= 18 and max(w, h) / max(min(w, h), 1) < 6 else walls).append(q)
    if cols:
        report.append(f'{len(cols)} fill(s) at least 18 cm across both ways were read as columns.')
    # columns drawn hatched rather than solid: a light fill crossed by at least three parallel slanted strokes
    # that run edge to edge inside it
    slants = [((it[1].x, it[1].y), (it[2].x, it[2].y)) for g in drawings if g['type'] == 's' for it in g['items']
              if it[0] == 'l' and abs(it[1].x - it[2].x) > .3 and abs(it[1].y - it[2].y) > .3 and inreg(it[1].x, it[1].y)]
    hatched = 0
    for g in drawings:
        if g['type'] not in ('f', 'fs') or not g.get('fill') or lum(g['fill']) < .3 or not inreg(g['rect'].x0, g['rect'].y0):
            continue
        r = g['rect']
        if not 5 <= min(r.width, r.height) * k and max(r.width, r.height) * k <= 300:
            continue
        on = lambda q: (r.x0 - .2 <= q[0] <= r.x1 + .2 and r.y0 - .2 <= q[1] <= r.y1 + .2
                        and min(abs(q[0] - r.x0), abs(q[0] - r.x1), abs(q[1] - r.y0), abs(q[1] - r.y1)) < .2)
        dirs = [round(math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi, 1) for a, b in slants if on(a) and on(b)]
        if dirs and max(dirs.count(x) for x in set(dirs)) >= 3:
            for p in paths(g):
                cols.append([P(*a) for a in p]); hatched += 1
    if hatched:
        report.append(f'{hatched} hatched fill(s) were read as columns.')

    # openings: a gap between two pieces of the same wall (same line, same thickness)
    W = int(max(P(region[2], 0)[0], 1)) + 4; H = int(max(P(0, region[3])[1], 1)) + 4
    from PIL import Image, ImageDraw
    im = Image.new('1', (W * 2, H * 2), 0); d = ImageDraw.Draw(im)
    for q in walls + cols:
        d.polygon([(x * 2, y * 2) for x, y in q], fill=1)
    M = np.array(im, dtype=bool)[1::2, 1::2]
    R = dx.rects(M)
    tags = [(s['t'], P((s['box'][0] + s['box'][2]) / 2, (s['box'][1] + s['box'][3]) / 2)) for s in spans if TAG.match(s['t'])]
    gaps = []
    for a in R:
        for b in R:
            if a is b:
                continue
            # along x: b starts after a ends, same band
            ov = min(a[3], b[3]) - max(a[1], b[1]); thick = min(a[3] - a[1], b[3] - b[1])
            if thick <= 45 and ov >= .8 * thick and 40 <= b[0] - a[2] <= 400 and a[3] - a[1] <= 45 and b[3] - b[1] <= 45:
                y0, y1 = max(a[1], b[1]), min(a[3], b[3])
                if not M[y0:y1, a[2]:b[0]].any():
                    gaps.append((a[2], y0, b[0], y1))
            ov = min(a[2], b[2]) - max(a[0], b[0]); thick = min(a[2] - a[0], b[2] - b[0])
            if thick <= 45 and ov >= .8 * thick and 40 <= b[1] - a[3] <= 400 and a[2] - a[0] <= 45 and b[2] - b[0] <= 45:
                x0, x1 = max(a[0], b[0]), min(a[2], b[2])
                if not M[a[3]:b[1], x0:x1].any():
                    gaps.append((x0, a[3], x1, b[1]))
    gaps = sorted(set(gaps))
    framed = framed_openings(drawings, P, k, inreg, M)
    if framed:
        report.append(f'{len(framed)} opening(s) were read from their frames (jamb lines across the wall with the wall '
                      'faces drawn between them); a full line along a face marks glass.')
        gaps = []
    # a gap is an opening when a tag stands beside it; untagged gaps up to 1.3 m are taken as doors
    openings, used, open_passages = [], set(), 0
    for g, glass in framed:
        cx, cy = (g[0] + g[2]) / 2, (g[1] + g[3]) / 2
        near = sorted((math.hypot(x - cx, y - cy), t, i) for i, (t, (x, y)) in enumerate(tags))
        near = [n for n in near if n[0] <= 160]
        tag = near[0][1] if near else None
        kind = ('window' if tag.upper().startswith('W') else 'door') if tag else ('window' if glass else 'door')
        openings.append((g, kind, tag))
    for g in gaps:
        cx, cy = (g[0] + g[2]) / 2, (g[1] + g[3]) / 2
        near = sorted((math.hypot(x - cx, y - cy), t, i) for i, (t, (x, y)) in enumerate(tags) if i not in used)
        near = [n for n in near if n[0] <= 160]
        L = max(g[2] - g[0], g[3] - g[1])
        if near:
            used.add(near[0][2]); openings.append((g, 'window' if near[0][1].upper().startswith('W') else 'door', near[0][1]))
        elif L <= 130:
            openings.append((g, 'door', None))
        else:
            open_passages += 1
    if open_passages:
        report.append(f'{open_passages} wide untagged gap(s) were left open (a passage, not a door).')
    if any(o[2] is None for o in openings):
        report.append(f'{sum(1 for o in openings if o[2] is None)} untagged gap(s) up to 1.30 m were taken as doors.')

    rooms = []
    for s in spans:
        t = s['t']; cx, cy = (s['box'][0] + s['box'][2]) / 2, (s['box'][1] + s['box'][3]) / 2
        if not inreg(cx, cy) or TAG.match(t) or not re.search(r'[A-Za-z؀-ۿ]{3}', t) or re.search(r'm²|m2|sqm|scale', t, re.I):
            continue
        rooms.append((t, P(cx, cy), s['box']))
    # a name written outside the plan points into its room with a leader: a thin line from the name's edge
    from scipy import ndimage
    shut = M.copy()
    for g, _, _ in openings:
        shut[int(g[1]):int(math.ceil(g[3])) + 1, int(g[0]):int(math.ceil(g[2])) + 1] = True
    lab, _ = ndimage.label(~shut)
    outside = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    zone = lambda q: lab[min(max(int(q[1]), 0), H - 1), min(max(int(q[0]), 0), W - 1)]
    lines = [((it[1].x, it[1].y), (it[2].x, it[2].y)) for g in drawings if g['type'] == 's' for it in g['items'] if it[0] == 'l']
    led = 0
    for i, (t, q, (x0, y0, x1, y1)) in enumerate(rooms):
        if zone(q) not in outside:
            continue
        for a, b in lines:
            for near, far in ((a, b), (b, a)):
                if (x0 - 2 <= near[0] <= x1 + 2 and y0 - 2 <= near[1] <= y1 + 2 and math.hypot(far[0] - near[0], far[1] - near[1]) > 10
                        and zone(P(*far)) not in outside and zone(P(*far))):
                    z = zone(P(*far)); ys_, xs_ = np.nonzero(lab == z)
                    mid = (float(xs_.min() + xs_.max() + 1) / 2, float(ys_.min() + ys_.max() + 1) / 2)
                    rooms[i] = (t, mid if zone(mid) == z else P(*far), None); led += 1   # the label goes mid-room
                    break
            if rooms[i][2] is None:
                break
    if led:
        report.append(f'{led} room name(s) written outside the plan were placed where their leader line points.')
    rooms = [(t, q) for t, q, _ in rooms]
    return {'k': k, 'size': (W, H), 'walls': walls, 'cols': cols, 'openings': openings, 'tags': tags, 'rooms': rooms,
            'dims': [((P(s[0], s[1]), P(s[2], s[3])), v) for s, v in dims], 'report': report}


def to_dxf(r, out):
    """The plan as read, written as a plain DXF in cm (y up) for dxf_import.py."""
    doc = ezdxf.new('R2018', setup=True); doc.header['$INSUNITS'] = 5
    msp = doc.modelspace()
    Y = lambda p: (p[0], -p[1])
    for q in r['walls']:
        h = msp.add_hatch(dxfattribs={'layer': 'A-WALL'}); h.paths.add_polyline_path([Y(p) for p in q], is_closed=True)
    for q in r['cols']:
        h = msp.add_hatch(dxfattribs={'layer': 'S-COLS'}); h.paths.add_polyline_path([Y(p) for p in q], is_closed=True)
    for i, (g, kind, tag) in enumerate(r['openings']):
        name = ('Window Opening %d' if kind == 'window' else 'Door Opening %d') % i
        blk = doc.blocks.new(name)
        x0, y0, x1, y1 = g
        pts = [Y((x0, y0)), Y((x1, y0)), Y((x1, y1)), Y((x0, y1))]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            blk.add_line(a, b)
        msp.add_blockref(name, (0, 0), dxfattribs={'layer': 'A-DETL'})
    for t, p in r['tags']:
        msp.add_text(t, height=12, dxfattribs={'layer': 'A-DOOR-IDEN'}).set_placement(Y(p), align=TextEntityAlignment.MIDDLE_CENTER)
    for t, p in r['rooms']:
        msp.add_text(t, height=18, dxfattribs={'layer': 'A-AREA-IDEN'}).set_placement(Y(p), align=TextEntityAlignment.MIDDLE_CENTER)
    for (a, b), v in r['dims']:
        horiz = abs(a[1] - b[1]) < .5
        dim = msp.add_linear_dim(base=Y(a), p1=Y(a), p2=Y(b), angle=0 if horiz else 90, dxfattribs={'layer': 'A-ANNO-DIMS'})
        dim.render()
    doc.saveas(out)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pdf'); ap.add_argument('outdir')
    ap.add_argument('--page', type=int, default=1); ap.add_argument('--scale', help='1:50, if the title block does not say')
    ap.add_argument('--lat', type=float); ap.add_argument('--lon', type=float); ap.add_argument('--facing', type=float)
    ap.add_argument('--name', help="the apartment's name (default: the PDF's file name)")
    a = ap.parse_args()
    r = read_pdf(a.pdf, a.page, a.scale)
    os.makedirs(os.path.join(a.outdir, 'converted'), exist_ok=True)
    dxf = to_dxf(r, os.path.join(a.outdir, 'converted', os.path.splitext(os.path.basename(a.pdf))[0] + '.dxf'))
    A, size, src = dx.import_dxf(dxf, 'cm', None, {'lat': a.lat, 'lon': a.lon, 'facing': a.facing})
    A['import']['source'] = os.path.basename(a.pdf)
    A['import']['assumed'] = r['report'] + A['import']['assumed']
    A['about'] = 'Imported from ' + os.path.basename(a.pdf) + ' by pdf_import.py: a draft to check on check.html before it is locked.'
    A['name'] = a.name or os.path.splitext(os.path.basename(a.pdf))[0]
    p = dx.write(A, a.outdir)
    c = dx.check_page(A, size, src, a.outdir)
    print('wrote', p, 'and', c)
    print(json.dumps(A['import']['counts']))
    for x in A['import']['assumed']:
        print('assumed:', x)
    for x in A['import']['warnings']:
        print('could not read:', x)


if __name__ == '__main__':
    main()
