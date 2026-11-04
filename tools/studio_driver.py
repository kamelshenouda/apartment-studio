"""Runs the apartment studio's own tools inside the visitor's browser (Pyodide): each step as if it were a fresh
process, then the finished site as a zip. Loaded by site/studio.html; nothing here touches the network."""
import contextlib, io, json, os, runpy, sys, time, zipfile

TOOLS = '/app/tools'
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)


def fresh():
    for k, m in list(sys.modules.items()):
        if (getattr(m, '__file__', None) or '').startswith(TOOLS):
            del sys.modules[k]


def step(script, args, env):
    """(ok, what it printed, seconds) for one step of the build."""
    fresh(); sys.argv = [os.path.join(TOOLS, script), *list(args)]
    for k, v in dict(env).items():
        os.environ[k] = v
    out = io.StringIO(); t0 = time.time(); ok = True
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            runpy.run_path(os.path.join(TOOLS, script), run_name='__main__')
        except SystemExit as e:
            if e.code not in (None, 0):
                ok = False; print(e.code)
        except Exception:
            import traceback; traceback.print_exc(); ok = False
    return ok, out.getvalue(), round(time.time() - t0, 1)


README = """{name}: your apartment as a website
====================================

Made with Apartment studio ({studio}) from your drawing, entirely in your browser.

  index.html   the home page: the key numbers and the plan
  plan.html    the plan: room sizes and areas, the windows' hours of sun, the sun's path over the site
  3d.html      the 3D: stand in every room at true size, open the doors, move the sun, place furniture
  lib/         three.js and three-mesh-bvh (MIT), so the 3D needs nothing from elsewhere
  apartment.json  the apartment as data: walls, doors, windows, rooms, the site

To publish it, upload this folder to any web host. On GitHub: make a new repository, upload these files,
then Settings, Pages, Deploy from a branch.

Door swings, window sills and heights and the ceiling corrected on the check page are already in it. To change
anything else and keep the site up to date, use the template with Claude Code: https://github.com/kamelshenouda/apartment-studio
Put this apartment.json at the top of your copy and ask Claude Code to "build my apartment".
"""


def make_zip(name, studio):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk('/app/site'):
            for f in sorted(fs):
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, '/app/site'))
        z.write('/app/apartment.json', 'apartment.json')
        z.writestr('README.txt', README.format(name=name, studio=studio))
    return buf.getvalue()
