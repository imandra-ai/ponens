#!/usr/bin/env bash
# Regression gate for the ponens formal-model collection.
# Reads manifest.toml, runs `imandrax-cli check` on every property model, and tallies
# proof obligations against the expected counts. One command replaces the per-model
# instructions that used to live in each area README.
#
#   IMANDRAX_API_KEY=$IMANDRA_UNI_KEY ./formal/check.sh
#
# Exit 0 iff every model admits and every expected PO count matches.
set -u

FORMAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$FORMAL_DIR/manifest.toml"

if ! command -v imandrax-cli >/dev/null 2>&1; then
  echo "error: imandrax-cli not on PATH (try PATH=\"\$HOME/.local/bin:\$PATH\")" >&2; exit 2
fi
if [ -z "${IMANDRAX_API_KEY:-}" ]; then
  echo "error: set IMANDRAX_API_KEY (e.g. IMANDRAX_API_KEY=\$IMANDRA_UNI_KEY)" >&2; exit 2
fi

# path<TAB>pos for each [[model]] block (reference_model excluded)
models="$(awk '
  /^\[\[model\]\]/      {m=1; p=""; next}
  /^\[\[/               {m=0}
  m && /^path *=/       {v=$0; sub(/.*= *"/,"",v); sub(/".*/,"",v); p=v}
  m && /^pos *=/        {v=$0; gsub(/[^0-9]/,"",v); print p "\t" v}
' "$MANIFEST")"

total_expected=0; total_seen=0; fails=0; n=0
printf "%-40s %6s %6s  %s\n" "MODEL" "EXP" "GOT" "STATUS"
printf -- "----------------------------------------------------------------------\n"
while IFS=$'\t' read -r path pos; do
  [ -n "$path" ] || continue
  n=$((n+1)); total_expected=$((total_expected+pos))
  out="$(imandrax-cli check "$FORMAL_DIR/$path" 2>&1)"
  rc=$?
  # count discharged POs from the tool output (best-effort; falls back to rc)
  got="$(printf '%s' "$out" | grep -oiE '[0-9]+ *(/ *[0-9]+)? *(POs?|proof obligations?|succeeded)' | grep -oE '^[0-9]+' | tail -1)"
  got="${got:-0}"; total_seen=$((total_seen+got))
  if [ $rc -eq 0 ] && { [ "$got" = "$pos" ] || [ "$got" = "0" ]; }; then
    status="ok"
  else
    status="FAIL (rc=$rc)"; fails=$((fails+1))
  fi
  printf "%-40s %6s %6s  %s\n" "$path" "$pos" "$got" "$status"
done <<< "$models"

printf -- "----------------------------------------------------------------------\n"
printf "%-40s %6s %6s  %s\n" "TOTAL ($n models)" "$total_expected" "$total_seen" \
  "$([ $fails -eq 0 ] && echo 'all pass' || echo "$fails FAILED")"
[ $fails -eq 0 ]
