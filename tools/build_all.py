#!/usr/bin/env python3
"""Build the whole site from apartment.json: the plan lock check, the plan page, the 3D, the home page, then the
private-word check. The GitHub Pages workflow runs exactly this.

  python3 tools/build_all.py            -> site/  (open site/index.html, or serve it: python3 -m http.server -d site)
"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
for step in ('plan_lock.py', 'build_plans.py', 'build_3d.py', 'build_site.py', 'build_studio.py', 'check_private.py'):
    r = subprocess.run([sys.executable, os.path.join(HERE, step)])
    if r.returncode:
        sys.exit(f'{step} stopped the build.')
print('site/ is ready.')
