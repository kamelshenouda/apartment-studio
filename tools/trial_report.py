"""A trial sent from the 3D page's 2D plan ("Send to Claude"), as a report an architect can act on, and the furniture
made official when the client agrees.

  python3 tools/trial_report.py trial.json                  the report (Markdown) on the screen
  python3 tools/trial_report.py trial.json -o report.md     ... into a file
  python3 tools/trial_report.py trial.json --page site/3d.html
                                                            ... and check it was made on the plan as it is now
  python3 tools/trial_report.py trial.json --furnish        what would change in furnish.json (nothing is written)
  python3 tools/trial_report.py trial.json --furnish --write
                                                            put the trial's placed pieces in furnish.json, for its plan

trial.json is the file saved from the dialog, the text copied for Claude (the JSON block in it is found), or '-' to
read either from standard input. Inside Claude, the page's store holds the same under trials/<plan>.

Walls and doors are never changed here: they are the plan, and the plan changes only in its source, checked by the
plan lock (tools/plan_lock.py --accept "why") once the client has approved. The report lists every change with its
coordinates in plan centimetres (x to the right, y down the plan) so that it can be drawn exactly.
"""
import json, os, re, sys


def load(path):
    txt = sys.stdin.read() if path == '-' else open(path, encoding='utf-8').read()
    try:
        d = json.loads(txt)
    except ValueError:
        m = re.search(r'```json\s*(\{.*?\})\s*```', txt, re.S) or re.search(r'(\{"kind":"apartment-trial".*\})', txt, re.S)
        if not m:
            sys.exit('No trial found: give the file saved from the 2D plan, or the text copied for Claude.')
        d = json.loads(m.group(1))
    if d.get('kind') != 'apartment-trial':
        sys.exit('This is not a trial from the 2D plan (kind: apartment-trial).')
    return d


def n(v):
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


def where(o, c, a):
    return (f'y {n(c[0])}–{n(c[1])}, x {n(a[0])} to {n(a[1])}' if o == 'h' else f'x {n(c[0])}–{n(c[1])}, y {n(a[0])} to {n(a[1])}')


def rooms(r):
    r = r or []
    return ' and '.join(r) if len(r) <= 2 else ', '.join(r[:-1]) + ' and ' + r[-1]


def fingerprint(page, plan, data=None):
    """The same fingerprint the 3D page gives a plan (peKey): a trial made on another version of the plan is flagged.
    A copy of a design (plan 'copy-c-1') is fingerprinted on its design's walls (data 'c')."""
    src = open(page, encoding='utf-8').read()
    i = src.index('var ALL=') + len('var ALL=')
    ALL, _ = json.JSONDecoder().raw_decode(src[i:])
    P = ALL['layouts'][data or plan]['plan2d']
    js = lambda v: [js(x) for x in v] if isinstance(v, list) else (int(v) if isinstance(v, float) and v.is_integer() else v)   # numbers as JavaScript writes them
    s = json.dumps([[js(L['a']), js(L['c'])] for L in P['lines']], separators=(',', ':'))
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    h = h - (1 << 32) if h >= (1 << 31) else h
    u, digits, out = h & 0xFFFFFFFF, '0123456789abcdefghijklmnopqrstuvwxyz', ''
    while True:
        u, r = divmod(u, 36)
        out = digits[r] + out
        if not u:
            break
    return 'apt3d-trial2-' + plan + '-' + out


def report(d, page=None):
    p, L = d['plan'], []
    L.append(f"# Trial of {p['name']}")
    L.append('')
    L.append(f"{d['summary'].rstrip('.…')}.")
    L.append('')
    L.append(f"Plan `{p['id']}`" + (f", a copy of the design `{p['copyOf']}`" if p.get('copyOf') else '') + f", made in the 2D plan on {d['made'][:10]}. Plan centimetres: x to the right, y down the plan.")
    if page:
        try:
            fp = fingerprint(page, p['id'], p.get('copyOf'))
            L.append('')
            L.append('Made on the plan as it is now.' if fp == d.get('fingerprint') else
                     f'**Made on another version of the plan** ({d.get("fingerprint")}, now {fp}): check every coordinate against the drawing before using it.')
        except (ValueError, KeyError) as e:
            L.append(f'\n(The plan could not be checked against {page}: {e}.)')
    w = d['walls']
    w.setdefault('length', [])
    if any(w[k] for k in ('moved', 'added', 'removed', 'thickness', 'length')):
        L += ['', '## Walls', '', '| Change | Rooms | Where (cm) |', '|---|---|---|']
        for m in w['moved']:
            way = ('down the plan' if m['by'] > 0 else 'up the plan') if m['o'] == 'h' else ('to the right' if m['by'] > 0 else 'to the left')
            L.append(f"| Moved {n(abs(m['by']))} cm {way} | {rooms(m['rooms'])} | {where(m['o'], m['was'], m['a'])} → now {'y' if m['o'] == 'h' else 'x'} {n(m['now'][0])}–{n(m['now'][1])} |")
        for m in w['added']:
            L.append(f"| New, {n(m['t'])} cm thick, {n(m['len'])} cm long | {rooms(m['rooms'])} | {where(m['o'], m['c'], m['a'])} |")
        for m in w['removed']:
            L.append(f"| Taken out, {n(m['len'])} cm | | {where(m['o'], m['c'], m['a'])} |")
        for m in w['thickness']:
            L.append(f"| Thickness {n(m['was'])} → {n(m['now'])} cm | {rooms(m['rooms'])} | {where(m['o'], m['c'], m['a'])} |")
        for m in w['length']:
            dl = (m['now'][1] - m['now'][0]) - (m['was'][1] - m['was'][0])
            L.append(f"| {'Longer' if dl > 0 else 'Shorter'} by {n(abs(dl))} cm, now {n(m['now'][1] - m['now'][0])} cm | {rooms(m['rooms'])} | {where(m['o'], m['c'], m['now'])}, was {n(m['was'][0])} to {n(m['was'][1])} |")
    dr = d['doors']
    if any(dr[k] for k in ('added', 'removed', 'changed')):
        L += ['', '## Doors', '', '| Change | Rooms | Opening (cm) |', '|---|---|---|']
        for x in dr['added']:
            L.append(f"| New {x['kind']} door, {n(x['w'])} cm | {rooms(x['rooms'])} | {n(x['op'][0])}–{n(x['op'][1])} in the wall at {'y' if x['o'] == 'h' else 'x'} {n(x['c'][0])}–{n(x['c'][1])} |")
        for x in dr['removed']:
            L.append(f"| Taken out, {n(x['w'])} cm | {rooms(x['rooms'])} | {n(x['op'][0])}–{n(x['op'][1])} |")
        for x in dr['changed']:
            ch = []
            if x['was']['w'] != x['now']['w']:
                ch.append(f"width {n(x['was']['w'])} → {n(x['now']['w'])} cm")
            if x['was']['kind'] != x['now']['kind']:
                ch.append(x['now']['kind'])
            if abs(x['was']['op'][0] - x['now']['op'][0]) > .5:
                ch.append('moved along its wall')
            if x.get('flip'):
                ch.append('hinge on the other side')
            if x.get('swing'):
                ch.append('opens the other way')
            L.append(f"| {', '.join(ch).capitalize()} | {rooms(x['now']['rooms'])} | {n(x['was']['op'][0])}–{n(x['was']['op'][1])} → {n(x['now']['op'][0])}–{n(x['now']['op'][1])} |")
    rc = [r for r in d['rooms'] if r['was'] is None or abs(r['now'] - r['was']) >= .05]
    if rc:
        L += ['', '## Rooms (clear floor)', '', '| Room | Design, m² | Trial, m² | Change | Size, cm |', '|---|---|---|---|---|']
        for r in rc:
            ch = 'new' if r['was'] is None else ('+' if r['now'] > r['was'] else '−') + f"{abs(r['now'] - r['was']):.1f}"
            L.append(f"| {r['n']} | {'' if r['was'] is None else format(r['was'], '.1f')} | {r['now']:.1f} | {ch} | {r['w']} × {r['d']} |")
    f = d['furniture']
    if f['placed'] or f['cleared'] or f['moved']:
        L += ['', '## Furniture']
        if f['placed']:
            L += ['', '| Room | Piece | Size, cm | Centre (x, y) | Turned |', '|---|---|---|---|---|']
            for q in sorted(f['placed'], key=lambda q: (q['room'], q['name'])):
                size = f"{n(q['w'])} × {n(q['d'])}" + (f" × {n(q['h'])}" if q['h'] > 2 else '') + (f", {n(q['at'])} off the floor" if q.get('at') else '')
                L.append(f"| {q['room'] or 'Outside the rooms'} | {q['name']} | {size} | {n(q['x'])}, {n(q['y'])} | {q['r']}° |")
        if f['cleared']:
            L += ['', 'Cleared from the design: ' + ', '.join(f"{q['name'].lower()}" + (f" ({q['room']})" if q['room'] else '') for q in f['cleared']) + '.']
        if f['moved']:
            L += ['', 'Moved from where the design has them: ' + ', '.join(q['name'].lower() for q in f['moved']) + '.']
    if d['warnings']:
        L += ['', '## To check', ''] + [f'- {t}' for t in d['warnings']]
    L += ['', '## Making it official', '',
          '1. The client approves the trial, or the parts of it to keep.',
          '2. Walls and doors: change the plan source to the coordinates above (AZAD: the plan\'s function in '
          '`02-layout/tools/build_plans.py`; the template: `apartment.json`), rebuild, and compare with the trial.',
          '3. `python3 tools/plan_lock.py --accept "what changed and why"`: the plan lock refuses any change to the '
          'plan without it, and logs the reason.',
          '4. Furniture: `python3 tools/trial_report.py trial.json --furnish --write` puts the placed pieces in '
          '`furnish.json` for this plan. The design\'s own pieces that were cleared or moved change in the plan source.',
          '5. Rebuild the site and check the 3D, the plan page and the warnings.']
    return '\n'.join(L) + '\n'


def furnish(d, path, write):
    k = d['plan'].get('copyOf') or d['plan']['id']      # a copy's furniture goes to the design it was copied from
    new = d['furniture']['furnish_json'].get(d['plan']['id'], {'pieces': []})
    cur = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
    was = (cur.get(k) or {}).get('pieces', [])
    print(f'{path}: plan {k} has {len(was)} piece(s); the trial has {len(new["pieces"])}.')
    if not write:
        print('Nothing written: add --write to put the trial\'s pieces in, once the client has agreed.')
        return
    cur[k] = {'pieces': new['pieces']}
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(cur, fh, indent=1, ensure_ascii=False)
        fh.write('\n')
    print(f'Written: {len(new["pieces"])} piece(s) for plan {k}. Rebuild the site to see them.')


def main(argv):
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return
    d = load(argv[0])
    out = argv[argv.index('-o') + 1] if '-o' in argv else None
    page = argv[argv.index('--page') + 1] if '--page' in argv else None
    if '--furnish' in argv:
        i = argv.index('--furnish')
        path = argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('-') else next(
            (q for q in ('02-layout/furnish.json', 'furnish.json') if os.path.exists(q)), 'furnish.json')
        furnish(d, path, '--write' in argv)
        return
    md = report(d, page)
    if out:
        open(out, 'w', encoding='utf-8').write(md)
        print('wrote', out)
    else:
        sys.stdout.write(md)


if __name__ == '__main__':
    main(sys.argv[1:])
