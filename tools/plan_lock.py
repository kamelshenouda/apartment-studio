#!/usr/bin/env python3
"""The plan lock: a fingerprint of the apartment's plan and measurements, checked before anything is built.

It covers what the architect's drawing fixes, never the furnishing or the presentation:
  - the walls, columns, door swings, openings, windows, sliders, room outlines and room labels with their sizes;
  - the garden boundary, the columns and the exterior openings (sizes, sills, heights, which way each faces);
  - the survey sheet's dimensions, if apartment.json names a survey PDF;
  - the ceiling and door-head heights, and the site's position and orientation.

Furniture (furnish.json) and everything the pages add on top stay outside the lock.

  python3 tools/plan_lock.py                   check; exits 1 and shows what moved if anything changed
  python3 tools/plan_lock.py --accept "why"    record a change you meant to make (logged with the reason)

build_plans.py and build_3d.py run the check first and refuse to build if it fails. Before the first lock (a fresh
apartment), they build and say how to lock it.
"""
import datetime, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
LOCK = os.path.join(ROOT, 'plan-lock.json')
LOG = os.path.join(ROOT, 'plan-lock-log.md')
LAYOUTS = [('existing', 'as_built')]
CORE = {'door', 'opening', 'room', 'slider', 'window'}
CORE_RECT = {'wall', 'col', 'z'}          # walls (existing and new), concrete columns, room outlines


def _plain(v):
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    return v


def _fresh(name):
    """Load a plan module straight from its source, never from a cached .pyc, so the check always sees the file
    as it is on disk. The copies are private to the lock and do not replace the build's own imports."""
    import types
    path = os.path.join(HERE, name + '.py')
    m = types.ModuleType(name)
    m.__file__ = path
    exec(compile(open(path).read(), path, 'exec'), m.__dict__)
    return m


def snapshot():
    """The core plan as plain data, one part per layout plus the shared parts."""
    saved = {k: sys.modules.get(k) for k in ('apartment', 'sunpath', 'openings')}
    try:
        for k in ('apartment', 'sunpath', 'openings'):   # build_plans imports these by name
            sys.modules[k] = _fresh(k)
        ap = sys.modules['apartment']
        op = sys.modules['openings']
        bp = _fresh('build_plans')
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    parts = {}
    for key, fn in LAYOUTS:
        keep, bp.REC = bp.REC, []
        try:
            getattr(bp, fn)()
            recs = bp.REC
        finally:
            bp.REC = keep
        core = []
        for r in recs:
            if r['furn']:
                continue
            kind = r['kind']
            if kind == 'rect':
                if r.get('cls', '').split(' ')[0] not in CORE_RECT:
                    continue
            elif kind not in CORE:
                continue
            core.append(_plain({k: v for k, v in r.items() if k != 'furn'}))
        core.sort(key=lambda r: json.dumps(r, sort_keys=True))
        parts['layout:' + key] = core
    parts['garden-boundary'] = bp.GARDEN
    parts['columns'] = _plain(bp.COLUMNS)
    parts['openings-schedule'] = _plain(op.OPENINGS)
    if ap.SURVEY.get('pdf'):
        dims = bp.survey_dims()
        if not dims:
            sys.exit('PLAN LOCK: the survey dimensions could not be read from the survey PDF (is pymupdf installed? '
                     '"python3 -m pip install -r requirements.txt"). Nothing was built, so no dimension can go missing silently.')
        parts['survey-dimensions'] = sorted(set(re.findall(r'>([^<>]+)</text>', dims)))
    parts['heights'] = {'CEIL': ap.CEIL, 'HEAD': ap.HEAD}
    parts['site'] = {'lat': ap.LAT, 'lon': ap.LON, 'facing': ap.FACING}
    return parts


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _diff(name, old, new):
    lines = ['  ' + name + ':']
    if isinstance(old, list) and isinstance(new, list):
        o = {json.dumps(x, sort_keys=True) for x in old}
        n = {json.dumps(x, sort_keys=True) for x in new}
        lines += ['    - ' + x for x in sorted(o - n)[:12]] + ['    + ' + x for x in sorted(n - o)[:12]]
        more = len(o ^ n) - min(12, len(o - n)) - min(12, len(n - o))
        if more > 0:
            lines.append('    … and %d more' % more)
    else:
        lines += ['    was ' + json.dumps(old, sort_keys=True)[:300], '    now ' + json.dumps(new, sort_keys=True)[:300]]
    return lines


def check(quiet=False):
    """True when the core plan matches the lock; otherwise prints what moved and returns False."""
    new = snapshot()
    if not os.path.exists(LOCK):
        print('Plan lock: not locked yet. When the plan is checked and right, lock it with:\n'
              '  python3 tools/plan_lock.py --accept "first lock: checked against the drawing"')
        return None
    lock = json.load(open(LOCK))
    old = lock['data']
    bad = [k for k in sorted(set(old) | set(new)) if digest(old.get(k)) != digest(new.get(k))]
    if not bad:
        if not quiet:
            print('Plan lock: the core plan and measurements match (%d parts, %s).' % (len(new), lock['locked']))
        return True
    print('PLAN LOCK: the core plan or its measurements changed in %d part(s). Nothing was built.' % len(bad))
    for k in bad:
        print('\n'.join(_diff(k, old.get(k), new.get(k))))
    print('If you meant to change the plan, record it with:\n'
          '  python3 tools/plan_lock.py --accept "what changed and why"')
    return False


def guard():
    """For the build scripts: stop before building anything if the plan moved since it was locked."""
    if check(quiet=True) is False:
        sys.exit(1)


def accept(reason):
    new = snapshot()
    old = json.load(open(LOCK))['data'] if os.path.exists(LOCK) else {}
    changed = [k for k in sorted(set(old) | set(new)) if digest(old.get(k)) != digest(new.get(k))]
    today = datetime.date.today().isoformat()
    json.dump({'about': 'Fingerprint of the plan and measurements; see tools/plan_lock.py. '
                        'Change it only with --accept and a reason.',
               'locked': today, 'reason': reason,
               'parts': {k: {'sha256': digest(v), 'items': len(v) if isinstance(v, (list, dict, str)) else 1}
                         for k, v in sorted(new.items())},
               'data': new}, open(LOCK, 'w'), indent=1, sort_keys=True)
    first = not os.path.exists(LOG)
    with open(LOG, 'a') as f:
        if first:
            f.write('# Plan lock log\n\nEvery accepted change to the plan and measurements, newest last.\n\n')
        f.write('- %s: %s (%s)\n' % (today, reason, ', '.join(changed) if changed else 'no change'))
    print('Plan lock recorded: %s; parts changed: %s' % (reason, ', '.join(changed) or 'none'))


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == '--accept':
        accept(' '.join(sys.argv[2:]))
    else:
        sys.exit(0 if check() is not False else 1)
