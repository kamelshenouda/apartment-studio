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
     Walls may be hatched, outlined or drawn as two parallel lines; layer names from bound references (`XREF$0$A-WALL`)
     are read by their own name. A sheet with several plans (ground floor, first floor, roof) reads the one with room
     names, else the ground floor; `--plan "First floor"` (its title, or its number) reads another.
   - PDF: `python3 tools/pdf_import.py drawings/PLAN.pdf drawings/import --lat .. --lon .. --facing ..`
   It writes `drawings/import/apartment.json` (a draft) and `drawings/import/check.html`.
4. **Check it with the owner.** Open `check.html` (take a screenshot with Playwright if you cannot show the file) and
   go through it with them:
   - the red dashed outlines are the drawing's own walls: they must sit on the black;
   - every door, window and room name; read out the "Assumed" and "Could not be read" lists;
   - door swings, window sills and heights, the ceiling and door-head heights are assumed: ask for the real ones. The
     owner can correct them on `check.html` itself (click a door to turn it or move its hinge; type sills and heights)
     and save the corrected `apartment.json`: put it in place of `drawings/import/apartment.json`. Anything else they
     say, fix by editing `drawings/import/apartment.json`.
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
- **Keep the 3D fast** when changing `tools/viewer.html`.
  - **Glass.** Any transmissive glass in view makes three.js draw the whole scene again behind it, on every scene render, so keep glass out of passes that only want depth (`withoutGlass`).
  - **Lights.** Lights shine on every pixel, so hide a light at zero rather than leaving it in.
  - **Window lights and lamps** are fixed pools, so the number of lights never changes and the shaders are never rebuilt.
  - **Extra quality.** New slow effects go behind a switch in More > Extra quality (`HQ`), off by default.
  - **Overlays** read sizes from `LAY`, never from the page, inside the frame loop.
  - **Timing.** Time changes with `?bench=1&q=fixed` (`APT3D.stats.last` then includes the graphics card's work).

- **The editable plan** (the 3D page's 2D button) works from `plan2d`, which `build_3d.py` writes for each layout,
  and from the `s` (source plan record) and `sk` (skirting) tags on the 3D items. If you change how walls, openings or
  doors are built in Python, change `pe3dScene` in `viewer.html` to match. Trials stay in the visitor's browser; the
  plan lock is untouched until the owner sends a trial and approves it.
  - **Warnings and their fixes.** `peWarnings` gives each problem a kind `k` (room, pocket, swing, thru, walk, over,
    win, front, noway, wet) and what it concerns. `peFixes` builds the card's solutions, each tried on a copy first.
    A new kind of warning needs a line in `PE_WHY` and its fixes in `peFixes`. A spot for a piece comes from
    `pfRelocate`, which takes only spots that add no warning (`pfAddsNone`).
  - **Sets per room.** `PF_STY` lists each room type's sets, the usual one first. A set function reads `X.st`. It
    sets `X.miss` to a plain reason when an asked-for set does not fit; the usual set (`X.def`) never sets one. The
    garden is the walk's room `'g'`, the largest rectangle in its outline (`pfGardenRect`). `pfGroup` places a set of
    pieces anywhere in a room.
  - **The plans are locked; changes go into copies.** A layout id `copy-<plan>-<n>` is a copy, listed in
    `<prefix>-copies` in the browser (`cpReg` builds it from its plan, with `copyOf`). `peOpen` and `setFurnish` on a plan
    start a new copy (`cpNew`); `cpDrop` deletes one, `cpBar` is its Rename · Delete bar in the panel. The plan page's part is in `plan_trial.js` (tabs, Edit, Rename, New copy, Delete). Never
    let an edit reach a plan itself.
  - **Doors and windows.** A door's `kind` is empty (hinged), `slide` (pocket), `slide2` (two parting leaves), `wall`
    (on the face), `screen` (oak slats on the face) or `open`. `peSlides`, `peNoSwing` and `peDoorOk` say how one behaves;
    `peBuildPocket` builds the wall a pocket needs. A window is an opening `[a0,a1,'win',src,{s,h}]` in its wall:
    `peWinEdit`, `peAddWin` and `peDelWin` change it, and `pe3dScene` builds it once it carries `{s,h}`. A warning the
    owner keeps goes into the trial's `keep` list (`peKeepKey`).
  - **Saving.** Every saved item (copies list, trials of copies, furniture, the trial index, the bin) is mirrored into
    the artifact's store as `saves/<key>` (`lsmPush`) and restored on opening when the browser lacks it (`lsmPull`,
    `cpRehydrate`, `cpFromFurnish`); `plan_trial.js` does the same for the plan page. Without a store nothing changes.
  - **Test handle.** `APT_PLAN.ev(src)` evaluates inside the page, so tests can reach these functions.
- **A trial sent to you** ("Send to Claude" in the 2D plan) arrives three ways:
  - in the 3D artifact's store, under the `trials` collection with the plan as the document (read it with the artifact data tool: `get`, collection `trials`, document `c`);
  - as text pasted in the chat, with a JSON block;
  - as a saved `.json` file.

  `python3 tools/trial_report.py trial.json --page site/3d.html` turns it into the report and checks it was made on
  the plan as it is now.
- **Making a sent trial official.** Walls and doors change only in the plan source, after the owner approves, then
  `tools/plan_lock.py --accept "why"`. Furniture goes into `furnish.json` with `--furnish --write`, also only once
  approved.

## Where things are

| Path | What |
|---|---|
| `apartment.json` | the apartment: site, heights, garden, openings, plan |
| `furnish.json` | furniture placed in the 3D (optional) |
| `drawings/` | the architect's drawings; `drawings/import/` is the importer's draft (not committed) |
| `tools/dxf_import.py`, `tools/pdf_import.py` | drawing → draft `apartment.json` + `check.html` |
| `tools/build_all.py` | lock check, plan page, 3D, home page, private-word check → `site/` |
| `tools/build_plans.py`, `tools/plan_template.html` | the plan page |
| `tools/trial_report.py` | a trial sent from the 2D plan as an architect's report; puts its furniture in `furnish.json` with `--furnish --write` |
| `tools/plan_trial.js` | the plan page's part of the trial: Design or Your trial, Edit in 2D (`build_plans.trial_script`, which copies in the viewer's `fSym`) |
| `tools/build_3d.py`, `tools/viewer.html` | the 3D (three.js, served from `tools/vendor`); places a project words or sets up differently are marked `<@name>default</@name>` in the viewer, and a project can give its own text for them (`build_3d.viewer_html(overrides)`) |
| `tools/build_site.py`, `tools/index_template.html` | the home page |
| `tools/plan_lock.py`, `plan-lock.json`, `plan-lock-log.md` | the plan lock and its history |
| `tools/build_studio.py`, `tools/studio_template.html`, `tools/studio_driver.py`, `tools/studio/` | the studio page (`site/studio.html`): the importers and the builders run in the visitor's browser through Pyodide 0.29.5 (PyMuPDF is one of its packages, loaded only for a PDF); a DWG is turned into DXF first by LibreDWG compiled to WebAssembly (`tools/studio/libredwg/`, GPL-3, rebuilt only by `tools/studio/build_dwg2dxf.sh`; never edit those two files by hand). Built only for the sample (or with `APT_STUDIO=1`), so an apartment's own site leaves it out |
