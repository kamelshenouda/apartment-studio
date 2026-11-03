"""The site's home page (site/index.html): the apartment's name, its key numbers, the plan, and the way into the 3D.

  python3 tools/build_site.py
"""
import datetime, html as htmlmod, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apartment  # noqa: E402
import build_plans as bp  # noqa: E402
import sunpath  # noqa: E402

ROOT = apartment.ROOT


def facts():
    rooms = [e for e in apartment.PLAN if e['k'] == 'room' and e.get('rect')]
    area = sum((e['rect'][2] - e['rect'][0]) * (e['rect'][3] - e['rect'][1]) for e in rooms) / 1e4
    pts = apartment.garden_points()
    garden = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))) / 2e4 if pts else 0
    out = [('Rooms', f'{area:.0f} m²'), ('Rooms named', str(len(rooms)))]
    if garden:
        out.append(('Garden', f'{garden:.0f} m²'))
    out.append(('Windows and glazed doors', str(len(apartment.OPENINGS))))
    out.append(('Top of the plan faces', f'{round(sunpath.FACING)}° {sunpath.compass(sunpath.FACING)}'))
    return out


def page():
    tpl = open(os.path.join(HERE, 'index_template.html')).read()
    f = ''.join(f'<div><dt>{k}</dt><dd>{v}</dd></div>' for k, v in facts())
    day = lambda d: f'{d.day} {d:%b %Y}'
    lock = os.path.join(ROOT, 'plan-lock.json')                      # where tools/plan_lock.py keeps it
    locked = (f"Plan measurements approved {day(datetime.date.fromisoformat(json.load(open(lock))['locked']))}"
              if os.path.exists(lock) else 'The plan is not locked yet')
    return (tpl.replace('{{NAME}}', htmlmod.escape(apartment.NAME))
               .replace('{{BUILT}}', day(datetime.date.today())).replace('{{LOCKED}}', locked)
               .replace('{{FACTS}}', f)
               .replace('{{PLAN}}', bp.svg(bp.with_placed(bp.as_built(), 'existing'))))


if __name__ == '__main__':
    out = os.path.join(ROOT, 'site', 'index.html')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    h = page()
    open(out, 'w').write(h)
    print('wrote', os.path.relpath(out, ROOT), len(h))
