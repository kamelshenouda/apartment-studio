#!/usr/bin/env python3
"""Draw the sample apartment as an architect's CAD office would: a DXF in millimetres, y up, standard layers
(A-WALL, S-COLS, A-DOOR, A-GLAZ, A-AREA-IDEN, A-ANNO-DIMS, L-SITE), walls hatched solid, doors as a leaf and a swing
arc, windows and sliding doors as frames with their glass, room names, a few dimensions.

The sample is made up: a two-bedroom ground-floor flat of about 100 m² with a 49 m² garden. It exists so the template
builds something on day one, and so the importer has a drawing whose every measurement is known.

  python3 tools/make_sample.py [drawings/sample-apartment.dxf]
  python3 tools/dxf_import.py drawings/sample-apartment.dxf .        # then: apartment.json, check.html
"""
import math, os, sys
import ezdxf
from ezdxf.enums import TextEntityAlignment

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
OX, OY = 5000.0, 20000.0                       # where plan (0, 0) lands, in mm


def P(x, y):
    """plan cm (y down the sheet) -> CAD mm (y up)"""
    return (OX + x * 10, OY - y * 10)


def rect(x0, y0, x1, y1):
    return [P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)]


# plan, in cm; the garden at the top, the flat below it
WALLS = [
    # façades, 20 cm, with gaps where the openings are
    (0, 400, 120, 420), (420, 400, 880, 420), (1080, 400, 1220, 420),            # garden side: living slider, master window
    (0, 1280, 520, 1300), (620, 1280, 790, 1300), (880, 1280, 1220, 1300),       # street side: front door, bathroom window
    (0, 420, 20, 1000), (0, 1150, 20, 1280),                                     # west: kitchen window
    (1200, 420, 1220, 1050), (1200, 1200, 1220, 1280),                           # east: bedroom 2 window
    # partitions, 10 cm
    (720, 420, 730, 870), (720, 950, 730, 1280),                                 # living | master, hall | corridor door
    (730, 780, 760, 790), (850, 780, 1200, 790),                                 # master | corridor
    (730, 960, 760, 970), (840, 960, 1000, 970), (1090, 960, 1200, 970),         # corridor | bathroom, bedroom 2
    (940, 970, 950, 1280),                                                       # bathroom | bedroom 2
    (20, 850, 600, 860), (690, 850, 720, 860),                                   # living | kitchen, hall door
    (400, 860, 410, 900), (400, 990, 410, 1280),                                 # kitchen | hall
]
COLUMNS = [(0, 400, 30, 430), (1190, 1270, 1220, 1300)]
WINDOWS = [(880, 400, 1080, 420), (0, 1000, 20, 1150), (1200, 1050, 1220, 1200), (790, 1280, 880, 1300)]
SLIDERS = [(120, 400, 420, 420)]
DOORS = [  # hinge, open leaf end, closed end
    ((520, 1280), (520, 1180), (620, 1280)),     # front door, into the hall
    ((760, 780), (760, 690), (850, 780)),        # master bedroom
    ((760, 970), (760, 1050), (840, 970)),       # bathroom
    ((1090, 970), (1090, 1060), (1000, 970)),    # bedroom 2
    ((730, 870), (810, 870), (730, 950)),        # hall to corridor
    ((400, 990), (310, 990), (400, 900)),        # kitchen
    ((690, 860), (690, 950), (600, 860)),        # hall to living
]
ROOMS = [('LIVING', 370, 630), ('MASTER BEDROOM', 965, 600), ('CORRIDOR', 965, 875), ('BATHROOM', 840, 1125),
         ('BEDROOM 2', 1075, 1125), ('KITCHEN', 205, 1070), ('HALL', 565, 1070)]
GARDEN = [(0, 0), (1220, 0), (1220, 400), (0, 400)]
DIMS = [(20, 420, 720, 420, 470), (730, 420, 1200, 420, 470), (20, 860, 20, 1280, 60), (1200, 970, 1200, 1280, 1150)]


def main(out):
    doc = ezdxf.new('R2018', setup=True)
    doc.header['$INSUNITS'] = 4                                       # millimetres
    for name, col in [('A-WALL', 7), ('S-COLS', 1), ('A-DOOR', 3), ('A-GLAZ', 4), ('A-AREA-IDEN', 2),
                      ('A-ANNO-DIMS', 6), ('L-SITE', 3), ('A-ANNO-TEXT', 7)]:
        doc.layers.add(name, color=col)
    msp = doc.modelspace()

    def solid(box, layer):
        msp.add_lwpolyline(rect(*box), close=True, dxfattribs={'layer': layer})
        h = msp.add_hatch(color=256, dxfattribs={'layer': layer})
        h.paths.add_polyline_path(rect(*box), is_closed=True)

    for b in WALLS:
        solid(b, 'A-WALL')
    for b in COLUMNS:
        solid(b, 'S-COLS')
    for (hx, hy), (lx, ly), (ex, ey) in DOORS:
        msp.add_line(P(hx, hy), P(lx, ly), dxfattribs={'layer': 'A-DOOR'})
        c = P(hx, hy); rad = math.hypot(lx - hx, ly - hy) * 10
        a1 = math.degrees(math.atan2(P(lx, ly)[1] - c[1], P(lx, ly)[0] - c[0]))
        a2 = math.degrees(math.atan2(P(ex, ey)[1] - c[1], P(ex, ey)[0] - c[0]))
        start, end = (a1, a2) if (a2 - a1) % 360 <= 180 else (a2, a1)
        msp.add_arc(c, rad, start, end, dxfattribs={'layer': 'A-DOOR'})
    for x0, y0, x1, y1 in WINDOWS:
        msp.add_lwpolyline(rect(x0, y0, x1, y1), close=True, dxfattribs={'layer': 'A-GLAZ'})
        horiz = (x1 - x0) >= (y1 - y0)
        a, b = ((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)) if horiz else (((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1))
        msp.add_line(P(*a), P(*b), dxfattribs={'layer': 'A-GLAZ'})
    for x0, y0, x1, y1 in SLIDERS:                                    # two sliding panes inside the frame
        msp.add_lwpolyline(rect(x0, y0, x1, y1), close=True, dxfattribs={'layer': 'A-GLAZ'})
        L = x1 - x0; p = L / 2 + 6
        for i in range(2):
            o = i * (L - p); m = (y0 + y1) / 2 + (-2 if i else 2)
            msp.add_lwpolyline(rect(x0 + o, m - 1.6, x0 + o + p, m + 1.6), close=True, dxfattribs={'layer': 'A-GLAZ'})
    for name, x, y in ROOMS:
        t = msp.add_text(name, height=180, dxfattribs={'layer': 'A-AREA-IDEN'})
        t.set_placement(P(x, y), align=TextEntityAlignment.MIDDLE_CENTER)
    msp.add_lwpolyline([P(*q) for q in GARDEN], close=True, dxfattribs={'layer': 'L-SITE'})
    for x0, y0, x1, y1, base in DIMS:
        horiz = y0 == y1
        d = msp.add_linear_dim(base=P(x0, base) if horiz else P(base, y0), p1=P(x0, y0), p2=P(x1, y1),
                               angle=0 if horiz else 90, dxfattribs={'layer': 'A-ANNO-DIMS'})
        d.render()
    msp.add_text('SAMPLE APARTMENT - GROUND FLOOR', height=300, dxfattribs={'layer': 'A-ANNO-TEXT', 'insert': P(0, 1450)})
    doc.saveas(out)
    return out


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'drawings', 'sample-apartment.dxf')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    print('wrote', main(out))
