"""Exterior openings (windows and glazed doors) from apartment.json, with their facing and their direct sun.

normal: the outward direction in plan coordinates (plan -y is the plan's top edge, which faces site.facing).
"""
import datetime as dt, math
import sunpath as sp
import apartment

OPENINGS = apartment.OPENINGS


def facing(normal):
    """Compass bearing the opening faces."""
    nx, ny = normal
    rel = math.degrees(math.atan2(nx, -ny))      # 0 = plan up
    return round((sp.FACING + rel) % 360)


def exterior_face(o):
    """The outside face line of the opening: (x0, y0, x1, y1) at the façade."""
    _, _, (x0, y0, x1, y1), _, _, (nx, ny) = o
    if ny:
        y = y0 if ny < 0 else y1
        return x0, y, x1, y
    x = x0 if nx < 0 else x1
    return x, y0, x, y1


def sunlit(o, el, az):
    """Direct sun on the middle of the glass: the sun is in front of it and no neighbour hides it."""
    if el <= 0:
        return False
    nx, ny = o[5]
    rel = math.radians(az - sp.FACING)
    dx, dy = math.sin(rel), -math.cos(rel)
    if dx * nx + dy * ny <= 0.02:
        return False
    fx0, fy0, fx1, fy1 = exterior_face(o)
    px, py = (fx0 + fx1) / 2 + nx * 3, (fy0 + fy1) / 2 + ny * 3
    return sp.shaded_by(px, py, o[3] + o[4] / 2, el, az) is None


def sun_hours():
    """{code: {day: (hours, first, last)}} of direct sun on each opening."""
    out = {}
    for o in OPENINGS:
        out[o[0]] = {}
        for key, label, date, tz, _ in sp.DAYS:
            lit = []
            for m in range(0, 24 * 60, 5):
                el, az = sp.sun(dt.datetime(*date) + dt.timedelta(minutes=m - tz * 60))
                if sunlit(o, el, az):
                    lit.append(m)
            out[o[0]][key] = (len(lit) * 5 / 60, sp.hm(lit[0]) if lit else '', sp.hm(lit[-1]) if lit else '')
    return out


if __name__ == '__main__':
    h = sun_hours()
    for o in OPENINGS:
        print(o[0], o[1], facing(o[5]), {k: (round(v[0], 1), v[1], v[2]) for k, v in h[o[0]].items()})
