"""The sun over the apartment: its position at any time, its path on three days of the year, and which neighbouring
building (if any are given in apartment.json) stands between a point and the sun. The chart is drawn the same way up
as the plan: the plan's top edge faces site.facing (a compass bearing)."""
import datetime as dt, math

import apartment
LAT, LON, FACING = apartment.LAT, apartment.LON, apartment.FACING
SOUTH = LAT < 0
# key, label, date, UTC offset, colour class. Summer time follows the hemisphere.
DAYS = [
    ('jun', '21 June', (2026, 6, 21), apartment.TZ if SOUTH else apartment.TZ_SUMMER, 'sp-jun'),
    ('mar', '21 March', (2026, 3, 21), apartment.TZ, 'sp-mar'),
    ('dec', '21 December', (2026, 12, 21), apartment.TZ_SUMMER if SOUTH else apartment.TZ, 'sp-dec'),
]
# the neighbours: name, outline, from, to (cm above your floor)
CONTEXT = [(c['name'], [tuple(q) for q in c['outline']], c.get('from', 0), c.get('to', 1500)) for c in apartment.CONTEXT]
TOP = max([c[3] for c in CONTEXT] + [0])


def sun(t_utc):
    """Elevation and azimuth in degrees (low-precision solar position, good to about 0.5°)."""
    d = (t_utc - dt.datetime(2000, 1, 1, 12)).total_seconds() / 86400
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    L = math.radians((q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360)
    e = math.radians(23.439 - 0.00000036 * d)
    ra = math.atan2(math.cos(e) * math.sin(L), math.cos(L))
    dec = math.asin(math.sin(e) * math.sin(L))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    ha = math.radians((gmst * 15 + LON) % 360) - ra
    lat = math.radians(LAT)
    el = math.asin(math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha))
    az = math.atan2(-math.sin(ha), math.tan(dec) * math.cos(lat) - math.sin(lat) * math.cos(ha))
    return math.degrees(el), math.degrees(az) % 360


def day(date, tz, step=5):
    """[(clock minutes, el, az)] for every step minutes the sun is up."""
    out = []
    for m in range(0, 24 * 60, step):
        el, az = sun(dt.datetime(*date) + dt.timedelta(minutes=m - tz * 60))
        if el > -0.5:
            out.append((m, el, az))
    return out


def _inside(x, y, poly):
    c = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            c = not c
    return c


def shaded_by(px, py, pz, el, az):
    """Which neighbouring building stands between the point (pz cm above the floor) and the sun, or None."""
    if el <= 0 or not CONTEXT:
        return None
    rel = math.radians(az - FACING)
    dx, dy, k = math.sin(rel), -math.cos(rel), math.tan(math.radians(el))
    t = 0
    while pz + t * k <= TOP and t < 20000:
        t += 10
        z = pz + t * k
        for name, poly, lo, hi in CONTEXT:
            if lo <= z <= hi and _inside(px + dx * t, py + dy * t, poly):
                return name
    return None


def on_side(az, facing=FACING):
    return math.cos(math.radians(az - facing)) > 0


def hm(m):
    return '%02d:%02d' % divmod(int(round(m)), 60)


def compass(b):
    return ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'][round(b % 360 / 22.5) % 16]


def facts():
    """Per day: sunrise, sunset, the noon height, and when the sun is on the side the plan's top edge faces."""
    out = {}
    for key, label, date, tz, _ in DAYS:
        pts = day(date, tz, 1)
        up = [p for p in pts if p[1] > 0]
        lit = [p for p in up if on_side(p[2])]
        top = max(up, key=lambda p: p[1])
        out[key] = dict(label=label, rise=hm(up[0][0]), set=hm(up[-1][0]), noon=round(top[1]),
                        lit_from=hm(lit[0][0]) if lit else '', lit_to=hm(lit[-1][0]) if lit else '', lit_h=round(len(lit) / 60, 1))
    return out


def svg(top=None, bottom=None):
    """Polar sun-path chart, turned so the plan's top edge is at the top. top and bottom name the two sides."""
    W, C, R = 560, 280, 220
    back = (FACING + 180) % 360

    def xy(az, el):
        r = R * (90 - max(el, 0)) / 90
        a = math.radians(az - FACING)
        return C + r * math.sin(a), C - r * math.cos(a)

    s = [f'<svg class="sunpath" viewBox="0 -24 {W} {W + 48}" role="img" aria-label="Sun path over the apartment on 21 June, 21 March and 21 December" xmlns="http://www.w3.org/2000/svg">']
    s.append(f'<path d="M{C - R} {C} A{R} {R} 0 0 1 {C + R} {C} Z" class="sp-lit"/>')
    for el in (0, 30, 60):
        r = R * (90 - el) / 90
        s.append(f'<circle cx="{C}" cy="{C}" r="{r:.1f}" class="{"sp-hor" if el == 0 else "sp-ring"}"/>')
        if el:
            s.append(f'<text x="{C + 4}" y="{C + r - 4:.1f}" class="sp-el">{el}°</text>')
    for b in range(0, 360, 15):
        x0, y0 = xy(b, 0)
        a = math.radians(b - FACING)
        k = 10 if b % 45 == 0 else 5
        s.append(f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x0 + k * math.sin(a):.1f}" y2="{y0 - k * math.cos(a):.1f}" class="sp-tick"/>')
    for b, n in zip(range(0, 360, 45), ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']):
        a = math.radians(b - FACING)
        x, y = C + (R + 26) * math.sin(a), C - (R + 26) * math.cos(a)
        s.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" class="sp-dir{" sp-n" if n == "N" else ""}">{n}</text>')
    s.append(f'<line x1="{C - R}" y1="{C}" x2="{C + R}" y2="{C}" class="sp-facade"/>')
    top = top or f'↑ TOP OF THE PLAN · FACES {round(FACING)}° {compass(FACING)}'
    bottom = bottom or f'↓ BOTTOM OF THE PLAN · FACES {round(back)}° {compass(back)}'
    s.append(f'<text x="{C}" y="-6" class="sp-side">{top}</text>')
    s.append(f'<text x="{C}" y="{W + 16}" class="sp-side">{bottom}</text>')
    for key, label, date, tz, cls in DAYS:
        pts = day(date, tz)
        d = ' '.join(('M' if i == 0 else 'L') + '%.1f %.1f' % xy(az, el) for i, (m, el, az) in enumerate(pts))
        s.append(f'<path d="{d}" class="sp-arc {cls}"/>')
        for m, el, az in pts:
            if m % 60 == 0 and el > 0:
                x, y = xy(az, el)
                s.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" class="sp-dot {cls}"/>')
                if (m // 60) % 2 == 0 and not (el < 3 and az > 180):   # a sunset dot sits on the W label
                    # label on the side of the arc away from the centre
                    dx, dy = x - C, y - C
                    L = math.hypot(dx, dy) or 1
                    s.append(f'<text x="{x + dx / L * 13:.1f}" y="{y + dy / L * 13 + 4:.1f}" class="sp-h {cls}">{m // 60}</text>')
    s.append('</svg>')
    return ''.join(s)
