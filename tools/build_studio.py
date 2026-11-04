"""The studio page (site/studio.html): anyone drops a floor plan as DWG, DXF or PDF and gets the plan, the 3D and the home page,
built inside their own browser by these same tools (Python in the page, through Pyodide). Nothing is uploaded.

  python3 tools/build_studio.py      -> site/studio.html and site/studio/ (the tools, the ezdxf wheel, LibreDWG's
                                         dwg2dxf for the browser, a file list)
"""
import glob, json, os, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
SITE = os.path.join(ROOT, 'site')
TOOLS = ['apartment.py', 'sunpath.py', 'openings.py', 'plan_lock.py', 'build_plans.py', 'plan_template.html', 'build_3d.py',
         'viewer.html', 'build_site.py', 'build_studio.py', 'index_template.html', 'dxf_import.py', 'pdf_import.py', 'catalogue.json']


def wanted():
    """The studio belongs to the template's own site (the made-up sample); an apartment's own site leaves it out,
    unless APT_STUDIO=1."""
    import sys
    sys.path.insert(0, HERE)
    import apartment
    return os.environ.get('APT_STUDIO') == '1' or apartment.NAME == 'Sample apartment'


def main():
    out = os.path.join(SITE, 'studio')
    if not wanted():
        shutil.rmtree(out, ignore_errors=True)
        if os.path.exists(os.path.join(SITE, 'studio.html')):
            os.remove(os.path.join(SITE, 'studio.html'))
        print('studio: left out (this is an apartment\'s own site; APT_STUDIO=1 adds it)')
        return
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, 'tools'))
    for f in TOOLS:
        shutil.copy(os.path.join(HERE, f), os.path.join(out, 'tools', f))
    shutil.copy(os.path.join(HERE, 'studio_driver.py'), os.path.join(out, 'driver.py'))
    wheel = sorted(glob.glob(os.path.join(HERE, 'studio', 'ezdxf-*.whl')))[-1]
    shutil.copy(wheel, out)
    shutil.copytree(os.path.join(HERE, 'studio', 'libredwg'), os.path.join(out, 'libredwg'))   # GPL-3: see its README
    vendor = os.path.join(HERE, 'vendor')
    lib = sorted(os.path.relpath(os.path.join(r, f), vendor).replace(os.sep, '/')
                 for r, _, fs in os.walk(vendor) for f in fs if not f.startswith('.') and f != 'README.md')
    json.dump({'tools': TOOLS, 'wheel': os.path.basename(wheel), 'dwg': 'libredwg/dwg2dxf.js', 'lib': lib}, open(os.path.join(out, 'files.json'), 'w'), indent=1)
    shutil.copy(os.path.join(HERE, 'studio_template.html'), os.path.join(SITE, 'studio.html'))
    print('wrote site/studio.html and site/studio/:', len(TOOLS), 'tools,', len(lib), 'library files')


if __name__ == '__main__':
    main()
