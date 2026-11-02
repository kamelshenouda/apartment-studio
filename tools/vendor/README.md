# Vendored libraries

The public site (GitHub Pages) serves the 3D viewer's libraries from here instead of a CDN, so it loads
even where cdn.jsdelivr.net is slow or blocked. `tools/build_3d.py` copies this folder to `site/lib/`
and points the viewer's import map at it. Only the modules the viewer imports, and what they import, are kept.

- three.js r169 (0.169.0), MIT licence: `three@0.169.0/LICENSE`
- three-mesh-bvh 0.8.3, MIT licence: `three-mesh-bvh@0.8.3/LICENSE`

The claude.ai artifact keeps the jsDelivr URLs: its page may load scripts only from a few CDNs.
