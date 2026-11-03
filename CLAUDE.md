# Apartment studio: instructions for Claude Code

This repository turns an architect's drawing of an apartment into a small website: a plan page, a walk-through 3D
model at true size, and the sun over the site. Everything is built from one file, `apartment.json`. The owner is
usually not a programmer: do the work yourself, explain in plain words, and show them what you built.

## "Build my apartment"

When the owner asks for this (or anything like it), go through these steps in order.

1. **Find the drawing.** Look in `drawings/` for a `.dwg`, `.dxf` or `.pdf`. If there is none, ask the owner to add the
   floor plan their architect gave them (DWG, DXF, or a PDF exported from CAD; a scan or photo will not work).
   - DWG needs LibreDWG once: `bash tools/install_libredwg.sh` (it builds `dwg2dxf` into `~/.local/libredwg`).
   - Python packages: `python3 -m pip install -r requirements.txt`.
2. **Ask about the site.** The importer cannot read these from a drawing:
   - the address or the latitude and longitude (look the coordinates up from the address if you can);
   - which compass bearing the top edge of the plan faces (`facing`). Help the owner find it from a map: the top of
     the drawing usually shows one façade; which way does that façade look?
   - the UTC offset in winter and in summer (`tz`, `tz_summer`).
3. **Import.**
   - DWG or DXF: `python3 tools/dxf_import.py drawings/PLAN.dwg drawings/import --lat .. --lon .. --facing ..`
   - PDF: `python3 tools/pdf_import.py drawings/PLAN.pdf drawings/import --lat .. --lon .. --facing ..`
   It writes `drawings/import/apartment.json` (a draft) and `drawings/import/check.html`.
4. **Check it with the owner.** Open `check.html` (take a screenshot with Playwright if you cannot show the file) and
   go through it with them:
   - the red dashed outlines are the drawing's own walls: they must sit on the black;
   - every door, window and room name; read out the "Assumed" and "Could not be read" lists;
   - fix what they say by editing `drawings/import/apartment.json`. Door swings, window sills and heights, the ceiling
     and door-head heights are assumed: ask for the real ones.
   Never round or "tidy" a coordinate: keep the drawing's values exactly.
5. **Make it the apartment.** When the owner says it is right, copy the draft to `apartment.json` at the top of the
   repository, set `name`, put `tz` and `tz_summer` in `site`, remove the `import` block, and lock it:
   `python3 tools/plan_lock.py --accept "first lock: checked with the owner against <drawing>"`.
   Remove the sample's `furnish.json` (or empty it to `{}`) and the sample drawing `drawings/sample-apartment.dxf`.
6. **Privacy.** Ask which words must never appear on the public site (family names, a flat number, a phone number).
   Put them, one per line, in `.private-words` (git ignores it), and ask the owner to add the same words,
   comma-separated, as a repository secret named `PRIVATE_WORDS` (Settings → Secrets and variables → Actions). Keep
   them out of `apartment.json` too: a room called "Sarah's room" becomes "Bedroom 2".
7. **Build and show.** `python3 tools/build_all.py`, then serve it (`python3 -m http.server -d site 8000`) and show the
   owner the home page, the plan and the 3D (screenshots, desktop and phone width).
8. **Publish.** Commit and push to `main`. The workflow `.github/workflows/pages.yml` builds the site and publishes it
   on GitHub Pages. The first time, Pages must be switched on: try
   `gh api -X POST repos/OWNER/REPO/pages -f build_type=workflow`; if that is not possible, ask the owner to open
   Settings → Pages and set Source to "GitHub Actions". Then give them the address
   (`https://OWNER.github.io/REPO/`).

## Rules

- **The plan lock.** `tools/plan_lock.py` fingerprints the plan's measurements; every build checks it first and stops
  if anything moved. Change walls, doors, windows, columns, rooms, heights or the site only when the owner asks for that
  change, then record it with their words: `python3 tools/plan_lock.py --accept "what changed, who asked"`.
- **Furniture** is outside the lock. The 3D's Furnish tab places real-size pieces; its "Copy list" ends with a line
  "For furnish.json: {...}". When the owner pastes it, save that JSON as `furnish.json` and rebuild: the plan draws it
  and the 3D opens with it.
- **Coordinates** are centimetres, x to the right of the sheet, y down the sheet; the plan's top edge faces
  `site.facing`. Exterior openings carry their sill, height and outward normal in `openings`.
- **Test the importers** after changing them: `python3 tools/make_sample.py`, import the sample, then
  `python3 tools/test_dxf_import.py drawings/import/apartment.json` should show walls about 100 % and every door,
  window and column exact.

## Where things are

| Path | What |
|---|---|
| `apartment.json` | the apartment: site, heights, garden, openings, plan |
| `furnish.json` | furniture placed in the 3D (optional) |
| `drawings/` | the architect's drawings; `drawings/import/` is the importer's draft (not committed) |
| `tools/dxf_import.py`, `tools/pdf_import.py` | drawing → draft `apartment.json` + `check.html` |
| `tools/build_all.py` | lock check, plan page, 3D, home page, private-word check → `site/` |
| `tools/build_plans.py`, `tools/plan_template.html` | the plan page |
| `tools/build_3d.py`, `tools/viewer.html` | the 3D (three.js, served from `tools/vendor`); places a project words or sets up differently are marked `<@name>default</@name>` in the viewer, and a project can give its own text for them (`build_3d.viewer_html(overrides)`) |
| `tools/build_site.py`, `tools/index_template.html` | the home page |
| `tools/plan_lock.py`, `plan-lock.json`, `plan-lock-log.md` | the plan lock and its history |
| `tools/build_studio.py`, `tools/studio_template.html`, `tools/studio_driver.py`, `tools/studio/` | the studio page (`site/studio.html`): the importer and the builders run in the visitor's browser through Pyodide. Built only for the sample (or with `APT_STUDIO=1`), so an apartment's own site leaves it out |
