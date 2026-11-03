# Apartment studio

Turn your architect's floor plan into your own website: the plan with every room's size, a 3D model you can walk
through at true size, and the sun crossing your rooms at any hour of the year. You give it the drawing; it gives you
a site on GitHub Pages.

See what you get: the sample apartment, published by this repository itself, is at
**https://apartment.kamelnabil.com/** (the plan, and the 3D walkthrough).

## What you get

- **A plan page**: the plan as the architect drew it, room sizes and areas, every window and glazed door with its hours
  of direct sun on 21 June, 21 March and 21 December, and the sun's path over the site.
- **A 3D walkthrough**:
  - stand in every room at true size, with a view of each room framed for you;
  - open and close the doors, windows and shutters, all at once or one door at a time, and switch the lights room by
    room;
  - drag the sun along its real path for your site, or play the day;
  - measure anything with the tape;
  - place real-size furniture and see the gap on every side;
  - share a link that opens the same view, with the furniture you placed and the finishes you tried;
  - save the view as a picture, with a strip naming each finish in it.
  It works on a phone too.
- **A plan lock**, so nothing moves your walls by accident: every build checks the measurements against the ones you
  approved.

## Start

1. Click **Use this template** on GitHub to make your own copy, and open it in
   [Claude Code](https://claude.com/claude-code).
2. Put your floor plan in `drawings/`: a DWG or DXF, or a PDF exported from CAD (not a scan).
3. Tell Claude Code: **"build my apartment"**. It imports the drawing, goes through it with you on a check page, asks
   for what a drawing cannot say (where the site is, which way it faces, the heights), builds the site and publishes it.

The steps Claude Code follows are in [`CLAUDE.md`](CLAUDE.md); you can run them yourself too:

```bash
python3 -m pip install -r requirements.txt
python3 tools/dxf_import.py drawings/my-plan.dwg drawings/import --lat 51.5 --lon -0.12 --facing 160
#   check drawings/import/check.html, correct drawings/import/apartment.json, then:
cp drawings/import/apartment.json apartment.json
python3 tools/plan_lock.py --accept "first lock: checked against my-plan.dwg"
python3 tools/build_all.py
python3 -m http.server -d site 8000      # then open http://localhost:8000
```

Reading a DWG needs LibreDWG once: `bash tools/install_libredwg.sh`.

## Publishing

Every push to `main` builds the site and publishes it with GitHub Pages
(`.github/workflows/pages.yml`). Switch Pages on once: **Settings → Pages → Source: GitHub Actions**.

The site is public. To keep names or an address off it, add a repository secret `PRIVATE_WORDS` (comma-separated) and
the same words, one per line, in a local `.private-words` file: the build stops before publishing if any of them
appears.

## The sample

`apartment.json` holds a made-up two-bedroom flat (about 100 m², with a 49 m² garden), drawn as a CAD file by
`tools/make_sample.py` and imported like any other drawing. Replace it with yours.

## Licence

MIT, see [LICENSE](LICENSE). three.js and three-mesh-bvh (in `tools/vendor`) are MIT-licensed by their authors.
