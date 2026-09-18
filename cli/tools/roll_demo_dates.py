#!/usr/bin/env python3
"""Roll a demo trace's dates forward, keeping the story it tells intact.

A showcase trace dated months in the past reads as neglect, the same way a stale spec badge did: the
flagship said `Trace updated: 2026-03-28` on a page someone opened in September. The dates are authored
fiction - there is no run behind them - so moving them is editing prose, not falsifying evidence.

Every timestamp in a file shifts by ONE offset, chosen so that file's NEWEST date lands on the target.
That preserves every interval: `stripe` carries a reference artifact from seven weeks before its run,
and seven weeks is what the reader is meant to notice. Shifting each date independently, or stamping
them all with today, would flatten exactly the structure the demo exists to show.

Files are staggered by a day or two so seven traces do not all claim to have happened this morning.

    python3 cli/tools/roll_demo_dates.py examples/*.json [--to 2026-09-18] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re

# Any ISO-8601 instant: `2026-03-28T10:00:00Z`, with or without the zone or the fraction.
STAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})(T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?)?")


def dates_in(text: str) -> list[dt.date]:
    out = []
    for m in STAMP.finditer(text):
        try:
            out.append(dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:                      # not a real date - leave whatever it is alone
            pass
    return out


def roll(text: str, days: int) -> tuple[str, int]:
    n = 0

    def shift(m: re.Match) -> str:
        nonlocal n
        try:
            d = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return m.group(0)
        n += 1
        return (d + dt.timedelta(days=days)).isoformat() + (m.group(4) or "")

    return STAMP.sub(shift, text), n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--to", default=dt.date.today().isoformat(),
                    help="the date the newest trace should carry (default: today)")
    ap.add_argument("--stagger", type=int, default=2,
                    help="days between files, newest first, so they are not all the same day")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    target = dt.date.fromisoformat(args.to)
    paths = [pathlib.Path(f) for f in args.files if pathlib.Path(f).name != "manifest.json"]

    newest = {p: max(dates_in(p.read_text()), default=None) for p in paths}

    # MANIFEST order, not original-date order. Staggering by how old a file already was put the
    # flagship - the one the demo page opens with, and the oldest of the set - furthest in the past,
    # which is the opposite of the point. The manifest is the order a reader meets them in, so the
    # first entry is the one that should look most recent.
    order: list[pathlib.Path] = []
    for base in {p.parent for p in paths}:
        mf = base / "manifest.json"
        if not mf.exists():
            continue
        import json as _json
        for s in _json.loads(mf.read_text()).get("samples") or []:
            f = base / s["file"]
            if f in paths and f not in order:
                order.append(f)
    ordered = order + [p for p in paths if p not in order]
    ordered = [p for p in ordered if newest[p]]

    for i, p in enumerate(ordered):
        want = target - dt.timedelta(days=i * args.stagger)
        days = (want - newest[p]).days
        if days == 0:
            print(f"  {p.name}: already at {want}")
            continue
        text, n = roll(p.read_text(), days)
        print(f"  {p.name}: {newest[p]} -> {want}  ({days:+d} days, {n} stamp(s))")
        if not args.dry_run:
            p.write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
