# LibreDWG's dwg2dxf, for the browser

The studio page (`site/studio.html`) reads DWG drawings with these two files: LibreDWG's `dwg2dxf` program compiled to
WebAssembly. The page turns the DWG into a DXF inside the visitor's own browser, then reads the DXF with
`dxf_import.py` as usual. Nothing is uploaded.

- **What:** LibreDWG 0.13.3, `programs/dwg2dxf.c` and the library, unchanged.
- **Licence:** GNU General Public License, version 3 ([COPYING](COPYING)). LibreDWG is © the Free Software Foundation.
  These two files are covered by the GPL; the rest of this template keeps its own licence. The page that loads them
  only passes a file in and reads a file out.
- **Source:** the complete source is the LibreDWG 0.13.3 release,
  <https://github.com/LibreDWG/libredwg/releases/download/0.13.3/libredwg-0.13.3.tar.xz>
  (sha256 `83f1f6e78a744777a481ff4520e4cef3f8ac4b2c1c25671077ca12fe81e8816e`), and
  <https://www.gnu.org/software/libredwg/>.
- **How it was built:** [`../build_dwg2dxf.sh`](../build_dwg2dxf.sh), with Emscripten 3.1.74. Run it to rebuild.

In JavaScript:

```js
const m = await createDwg2Dxf({ print() {}, printErr() {} });   // a fresh copy for each drawing
m.FS.writeFile('/in.dwg', bytes);
m.callMain(['-y', '-o', '/out.dxf', '/in.dwg']);                 // returns 0 when it worked
const dxf = m.FS.readFile('/out.dxf');
```

Checked against the same version built natively: the architect's DWG of a real apartment (AutoCAD 2018 format) gives
the same DXF, apart from true colours (group codes 420/421) written as signed rather than unsigned 32-bit numbers,
which DXF readers treat alike; `dxf_import.py` reads the same walls, doors, windows and rooms from both.
