"""The apartment, read from apartment.json at the top of the repository: the site, the heights, the garden, the
exterior openings and the plan (walls, columns, windows, sliders, doors, rooms, zones and notes, in the order the plan
page draws them).

apartment.json is the one file that changes from one apartment to the next. tools/dxf_import.py and
tools/pdf_import.py write it from an architect's drawing; every page is built from it; tools/plan_lock.py
fingerprints it so that nothing changes its measurements by accident.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
PATH = os.environ.get('APARTMENT', os.path.join(ROOT, 'apartment.json'))

# before the first import there is no apartment yet: an empty one lets the importers run
EMPTY = {'name': 'No apartment yet', 'site': {'lat': 0, 'lon': 0, 'facing': 180},
         'heights': {'ceiling': 280, 'door_head': 230}, 'garden': '', 'openings': [], 'plan': []}
A = json.load(open(PATH, encoding='utf-8')) if os.path.exists(PATH) else EMPTY

NAME = A.get('name', 'My apartment')
SITE = A['site']
LAT, LON, FACING = SITE['lat'], SITE['lon'], SITE['facing']
# the site's UTC offset in winter and in summer (hours); if not given, the sun's own clock at that longitude
TZ = SITE.get('tz', round(LON / 15))
TZ_SUMMER = SITE.get('tz_summer', TZ)
CEIL, HEAD = A['heights']['ceiling'], A['heights']['door_head']
SURVEY = A.get('survey') or {}
# a survey PDF named in apartment.json is found relative to apartment.json itself
SURVEY = dict(SURVEY, pdf=os.path.normpath(os.path.join(os.path.dirname(PATH), SURVEY['pdf'])) if SURVEY.get('pdf') else None)
GARDEN = A.get('garden') or ''
PLAN = A['plan']
# code, room, box (x0, y0, x1, y1), sill, height, outward normal
OPENINGS = [(o['code'], o['room'], tuple(o['box']), o['sill'], o['height'], tuple(o['normal'])) for o in A.get('openings', [])]
COLUMNS = [tuple(e['box']) for e in PLAN if e['k'] == 'column']
BY_ID = {e['id']: e for e in PLAN if 'id' in e}
# neighbouring buildings that cast shade: [{name, outline [[x, y], ...] in plan cm, from, to (cm above your floor)}]
CONTEXT = A.get('context', [])


def in_set(name):
    return [e for e in PLAN if e.get('set') == name]


def extent(margin=0):
    """The plan's bounding box in cm (walls, columns, openings, the garden), with a margin."""
    xs, ys = [], []
    for e in PLAN:
        b = e.get('box') or e.get('rect')
        if b and e['k'] in ('wall', 'column', 'window', 'slider', 'zone'):
            xs += [b[0], b[2]]; ys += [b[1], b[3]]
    gx = [q[0] for q in garden_points()]; gy = [q[1] for q in garden_points()]
    xs += gx; ys += gy
    if not xs:
        return (0, 0, 1000, 1000)
    return (min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin)


def garden_points():
    """The garden outline as [(x, y), ...] (plan cm)."""
    import re
    pts, x, y = [], 0, 0
    for cmd, args in re.findall(r'([MLHVZ])([^MLHVZ]*)', GARDEN):
        v = [float(t) for t in re.findall(r'-?\d+(?:\.\d+)?', args)]
        if cmd in 'ML':
            for i in range(0, len(v) - 1, 2):
                x, y = v[i], v[i + 1]; pts.append((x, y))
        elif cmd == 'H':
            for t in v:
                x = t; pts.append((x, y))
        elif cmd == 'V':
            for t in v:
                y = t; pts.append((x, y))
    return pts
