#!/usr/bin/env bash
# Regression gate for the ponens formal-model collection.
# Reads manifest.toml, runs `codelogician-lite check --json` on every model file, and
# compares the proof obligations (POs) it reports with the expected counts.
#
#   IMANDRAX_ENV=prod ./formal/check.sh
#
# codelogician-lite reads IMANDRA_UNI_KEY or IMANDRAX_API_KEY. It gives up waiting after
# CODELOGICIAN_TIMEOUT seconds; this script raises the default to 600.
#
# Exit 0 iff every model is admitted, every PO is proved, and every PO count matches.
set -u

FORMAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MANIFEST="$FORMAL_DIR/manifest.toml"
export CODELOGICIAN_TIMEOUT="${CODELOGICIAN_TIMEOUT:-600}"

for tool in codelogician-lite jq; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "error: $tool not on PATH" >&2; exit 2
  fi
done
if [ -z "${IMANDRA_UNI_KEY:-}" ] && [ -z "${IMANDRAX_API_KEY:-}" ]; then
  echo "error: set IMANDRA_UNI_KEY or IMANDRAX_API_KEY" >&2; exit 2
fi

# path<TAB>pos for each [[model]] block (reference_model excluded)
models="$(awk '
  /^\[\[model\]\]/      {m=1; p=""; next}
  /^\[\[/               {m=0}
  m && /^path *=/       {v=$0; sub(/.*= *"/,"",v); sub(/".*/,"",v); p=v}
  m && /^pos *=/        {v=$0; gsub(/[^0-9]/,"",v); print p "\t" v}
' "$MANIFEST")"

# every import alias used in the collection, as a JSON list
ALIASES="$(grep -ho '^\[@@@import [A-Za-z_0-9]*' "$FORMAL_DIR"/*/*.iml "$FORMAL_DIR"/*/*/*.iml \
           | awk '{print $2}' | sort -u | jq -R . | jq -sc .)"

total_expected=0; total_seen=0; fails=0; n=0
printf "%-32s %5s %5s %5s  %s\n" "MODEL" "EXP" "GOT" "FAIL" "STATUS"
printf -- "----------------------------------------------------------------\n"
while IFS=$'\t' read -r path pos; do
  [ -n "$path" ] || continue
  n=$((n+1)); total_expected=$((total_expected+pos))
  # run from the file's directory so that [@@@import ...] paths resolve
  out="$(cd "$FORMAL_DIR/$(dirname "$path")" && codelogician-lite check --json "$(basename "$path")" 2>&1)"
  rc=$?
  # a PO from an imported file is named after the import alias (Core.Trace.wf_empty);
  # the file's own POs are the rest. A failure anywhere still fails the file.
  if summary="$(printf '%s' "$out" | jq -r --argjson al "$ALIASES" '
      .eval_res as $r
      | [ ($r.success | tostring),
          ($r.errors | length),
          ([$r.po_results[] | select(((.origin.from_sym // "") | split(".")[0]) as $h
                                     | $al | index([$h]) | not)] | length),
          ([$r.po_results[] | select((.errors | length) > 0)] | length) ]
      | @tsv' 2>/dev/null)"; then
    IFS=$'\t' read -r ok eval_errs got po_fails <<< "$summary"
  else
    ok=false; eval_errs=1; got=0; po_fails=0
  fi
  total_seen=$((total_seen+got))
  if [ $rc -ne 0 ] || [ "$ok" != "true" ] || [ "$eval_errs" -ne 0 ]; then
    status="FAIL (not admitted, rc=$rc)"; fails=$((fails+1))
  elif [ "$po_fails" -ne 0 ]; then
    status="FAIL ($po_fails POs not proved)"; fails=$((fails+1))
  elif [ "$got" != "$pos" ]; then
    status="FAIL (PO count)"; fails=$((fails+1))
  else
    status="ok"
  fi
  printf "%-32s %5s %5s %5s  %s\n" "$path" "$pos" "$got" "$po_fails" "$status"
  if [ "$status" != "ok" ] && [ -n "${VERBOSE:-}" ]; then printf '%s\n' "$out" >&2; fi
done <<< "$models"

printf -- "----------------------------------------------------------------\n"
printf "%-32s %5s %5s %5s  %s\n" "TOTAL ($n models)" "$total_expected" "$total_seen" "" \
  "$([ $fails -eq 0 ] && echo 'all pass' || echo "$fails FAILED")"
[ $fails -eq 0 ]
