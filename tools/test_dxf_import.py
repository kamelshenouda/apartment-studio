#!/usr/bin/env python3
"""Compare an imported apartment (dxf_import.py) with the locked as-built (apartment.json), element by element.

  python3 tools/test_dxf_import.py IMPORTED/apartment.json [--shift DX DY] [--ref apartment.json]

Walls are compared as solid area on a 1 cm grid (the import may split them into different pieces); doors by hinge,
leaf and closed end; windows, glazed doors and columns by their boxes; rooms by name and size. --shift moves the
import onto the plan's frame when the drawing has no site outline to fix the origin (it is found automatically if
not given).
"""
import json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def records(A):
    import build_plans as bp, openings as op
    keep_open = op.OPENINGS
    op.OPENINGS = [(o['code'], o['room'], tuple(o['box']), o['sill'], o['height'], tuple(o['normal'])) for o in A['openings']]
    bp.REC = []
    try:
        ''.join(bp.draw(e) for e in A['plan'] if e['k'] != 'survey_dims')
        return bp.REC
    finally:
        bp.REC = None
        op.OPENINGS = keep_open


def mask(recs, W=2000, H=2000, dx=0, dy=0):
    m = np.zeros((H, W), bool)
    for r in recs:
        if r['kind'] == 'rect' and r['cls'].split(' ')[0] == 'wall':
            x0, y0, x1, y1 = r['box']
            m[int(round(y0 + dy)):int(round(y1 + dy)), int(round(x0 + dx)):int(round(x1 + dx))] = True
    return m


def compare(imp, ref, shift=None):
    ri, rr = records(imp), records(ref)
    if shift is None:                                   # the offset that lays the most wall onto wall
        import collections
        bi = [r['box'] for r in ri if r['kind'] in ('window', 'slider') or r['kind'] == 'rect' and r['cls'] == 'col']
        br = [r['box'] for r in rr if r['kind'] in ('window', 'slider') or r['kind'] == 'rect' and r['cls'] == 'col']
        votes = collections.Counter((round((q[0] - p[0]) * 2) / 2, round((q[1] - p[1]) * 2) / 2) for p in bi for q in br)
        b0 = mask(rr)
        shift = max((c for c, _ in votes.most_common(40)), key=lambda c: (mask(ri, dx=c[0], dy=c[1]) & b0).sum())
    dx, dy = shift
    out = {'shift': [round(dx, 2), round(dy, 2)]}
    a, b = mask(ri, dx=dx, dy=dy), mask(rr)
    out['walls'] = {'area_m2_import': round(a.sum() / 1e4, 2), 'area_m2_plan': round(b.sum() / 1e4, 2),
                    'overlap_pct': round(100 * (a & b).sum() / max(1, (a | b).sum()), 2),
                    'cm2_only_in_import': int((a & ~b).sum()), 'cm2_only_in_plan': int((b & ~a).sum())}
    mv = lambda p: (round(p[0] + dx, 1), round(p[1] + dy, 1))
    di = {(mv(r['hinge']), mv(r['leaf']), mv(r['shut'])) for r in ri if r['kind'] == 'door'}
    dr = {(tuple(map(float, r['hinge'])), tuple(map(float, r['leaf'])), tuple(map(float, r['shut']))) for r in rr if r['kind'] == 'door'}
    dr = {tuple((round(p[0], 1), round(p[1], 1)) for p in d) for d in dr}
    gap = lambda d: frozenset([d[0], d[2]])           # the opening, whichever way the door swings
    out['doors'] = {'import': len(di), 'plan': len(dr), 'exact': len(di & dr),
                    'same_opening': len({gap(d) for d in di} & {gap(d) for d in dr}),
                    'missing': sorted(map(str, dr - di))[:8], 'extra': sorted(map(str, di - dr))[:8]}
    bx = lambda r: (round(r['box'][0] + dx, 1), round(r['box'][1] + dy, 1), round(r['box'][2] + dx, 1), round(r['box'][3] + dy, 1))
    for kind in ('window', 'slider'):
        si = {bx(r) for r in ri if r['kind'] == kind}
        sr = {tuple(round(v, 1) for v in r['box']) for r in rr if r['kind'] == kind}
        out[kind + 's'] = {'import': len(si), 'plan': len(sr), 'exact': len(si & sr), 'missing': sorted(sr - si), 'extra': sorted(si - sr)}
    ci = {bx(r) for r in ri if r['kind'] == 'rect' and r['cls'] == 'col'}
    cr = {tuple(round(v, 1) for v in r['box']) for r in rr if r['kind'] == 'rect' and r['cls'] == 'col'}
    out['columns'] = {'import': len(ci), 'plan': len(cr), 'exact': len(ci & cr), 'missing': sorted(cr - ci), 'extra': sorted(ci - cr)}
    roi = {r['name'].lower(): r for r in ri if r['kind'] == 'room'}
    ror = {r['name'].lower(): r for r in rr if r['kind'] == 'room'}
    rows = []
    for n, r in ror.items():
        i = roi.get(n)
        if not i:
            rows.append((r['name'], 'missing'))
            continue
        a_ = tuple(round(v, 1) for v in r['rect']) if r.get('rect') else None
        b_ = bx({'box': i['rect']}) if i.get('rect') else None
        rows.append((r['name'], 'same size and place' if a_ == b_ else f'plan {a_}, import {b_}'))
    out['rooms'] = {'import': len(roi), 'plan': len(ror), 'same': sum(1 for _, v in rows if v == 'same size and place'),
                    'differences': [x for x in rows if x[1] != 'same size and place']}
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='Compare an imported apartment.json with the locked one.')
    ap.add_argument('imported')
    ap.add_argument('--shift', nargs=2, type=float, metavar=('DX', 'DY'))
    ap.add_argument('--ref', default=os.path.join(HERE, '..', 'apartment.json'), help='the apartment.json to compare with')
    a = ap.parse_args()
    imp = json.load(open(a.imported, encoding='utf-8'))
    ref = json.load(open(a.ref, encoding='utf-8'))
    print(json.dumps(compare(imp, ref, tuple(a.shift) if a.shift else None), indent=1, ensure_ascii=False, default=str))
