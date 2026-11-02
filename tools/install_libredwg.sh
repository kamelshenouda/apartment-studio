#!/bin/sh
# Builds LibreDWG's dwg2dxf into ~/.local/libredwg, so dxf_import.py can read DWG files without AutoCAD.
# LibreDWG is free software (GPL-3.0); it is downloaded and built here, not stored in this repository.
set -e
V=0.13.3
D=$(mktemp -d)
cd "$D"
curl -sSL -o libredwg.tar.xz "https://github.com/LibreDWG/libredwg/releases/download/$V/libredwg-$V.tar.xz"
tar xf libredwg.tar.xz
cd "libredwg-$V"
./configure --disable-bindings --prefix="$HOME/.local/libredwg" -q
make -j4 >/dev/null
make install >/dev/null
echo "dwg2dxf installed: $HOME/.local/libredwg/bin/dwg2dxf"
