#!/bin/sh
# Builds LibreDWG's dwg2dxf for the browser (WebAssembly), the converter the studio page uses to read DWG files.
# The result is tools/studio/libredwg/dwg2dxf.js and dwg2dxf.wasm, kept in this repository so the site builds
# without a compiler. Run this again only to change the LibreDWG version.
#
# LibreDWG is free software under the GNU GPL, version 3 (tools/studio/libredwg/COPYING), and so is this build of it.
# Its complete source is the release below, unchanged; this script is how it was compiled.
#
#   sh tools/studio/build_dwg2dxf.sh          (needs git, curl, python3, make; about 10 minutes)
set -e
V=0.13.3
SHA=83f1f6e78a744777a481ff4520e4cef3f8ac4b2c1c25671077ca12fe81e8816e
EMSDK=3.1.74
OUT=$(cd "$(dirname "$0")" && pwd)/libredwg
W=$(mktemp -d)
cd "$W"

git clone -q --depth 1 https://github.com/emscripten-core/emsdk.git
./emsdk/emsdk install "$EMSDK" >/dev/null
./emsdk/emsdk activate "$EMSDK" >/dev/null
. ./emsdk/emsdk_env.sh >/dev/null 2>&1

curl -sSL -o libredwg.tar.xz "https://github.com/LibreDWG/libredwg/releases/download/$V/libredwg-$V.tar.xz"
echo "$SHA  libredwg.tar.xz" | sha256sum -c -
tar xf libredwg.tar.xz
cd "libredwg-$V"
emconfigure ./configure --disable-bindings --disable-shared --enable-static -q CFLAGS="-O2" >/dev/null
emmake make -C src -j4 >/dev/null
emcc -Oz -DHAVE_CONFIG_H -I src -I include -I . programs/dwg2dxf.c src/.libs/libredwg.a -lm -o "$OUT/dwg2dxf.js" \
  -sMODULARIZE=1 -sEXPORT_NAME=createDwg2Dxf -sALLOW_MEMORY_GROWTH=1 -sEXPORTED_RUNTIME_METHODS=FS,callMain \
  -sINVOKE_RUN=0 -sEXIT_RUNTIME=0 -sENVIRONMENT=web,worker,node -sFORCE_FILESYSTEM=1 -sSTACK_SIZE=4MB
chmod -x "$OUT/dwg2dxf.wasm"
cp COPYING "$OUT/COPYING"
rm -rf "$W"
echo "wrote $OUT/dwg2dxf.js and dwg2dxf.wasm (LibreDWG $V)"
