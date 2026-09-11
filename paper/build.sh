#!/usr/bin/env bash
# Build the technical paper (single LaTeX source). Requires: tectonic.
set -euo pipefail
cd "$(dirname "$0")"
command -v tectonic >/dev/null || { echo "need tectonic"; exit 1; }
tectonic paper.tex
echo "built $(pwd)/paper.pdf"
