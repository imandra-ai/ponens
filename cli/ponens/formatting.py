"""Terminal formatting utilities: colors, tables, headings, time display."""

import os
import sys
from datetime import datetime, timezone

# ── ANSI colors ─────────────────────────────────────────────────

_NO_COLOR = os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()


def _ansi(code: str, text: str) -> str:
    if _NO_COLOR:
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(t: str) -> str:
    return _ansi("1", t)


def gray(t: str) -> str:
    return _ansi("90", t)


def red(t: str) -> str:
    return _ansi("31", t)


def green(t: str) -> str:
    return _ansi("32", t)


def yellow(t: str) -> str:
    return _ansi("33", t)


def blue(t: str) -> str:
    return _ansi("34", t)


def magenta(t: str) -> str:
    return _ansi("35", t)


def cyan(t: str) -> str:
    return _ansi("36", t)


def white(t: str) -> str:
    return _ansi("37", t)


def underline(t: str) -> str:
    return _ansi("4", t)


# ── Status coloring ─────────────────────────────────────────────

_STATUS_COLORS = {
    "draft": gray,
    "shared": blue,
    "under_review": magenta,
    "approved": green,
    "needs_attention": yellow,
    "archived": gray,
    "open": yellow,
    "acknowledged": cyan,
    "resolved": green,
    "passed": green,
    "failed": red,
    "running": cyan,
    "pending": yellow,
    "active": green,
    "superseded": gray,
    "deprecated": gray,
}


def color_status(status: str) -> str:
    fn = _STATUS_COLORS.get(status, white)
    return fn(status)


# ── Time formatting ─────────────────────────────────────────────


def time_ago(iso: str) -> str:
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso or ""
    now = datetime.now(timezone.utc)
    seconds = int((now - then).total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    m = seconds // 60
    if m < 60:
        return f"{m}m ago"
    h = m // 60
    if h < 24:
        return f"{h}h ago"
    d = h // 24
    return f"{d}d ago"


# ── Table renderer ──────────────────────────────────────────────


def _visible_len(s: str) -> int:
    """Length of string excluding ANSI escape sequences."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def table(rows: list, columns: list[dict]) -> None:
    """Print a formatted table.

    columns: list of dicts with keys:
        label: str - column header
        get: callable(row) -> str - value extractor
        color: optional callable(str) -> str - color function
    """
    if not rows:
        print(gray("  (empty)"))
        return

    # Compute column widths from raw (non-colored) values
    widths = []
    for col in columns:
        vals = [str(col["get"](r)) for r in rows]
        widths.append(max(len(col["label"]), *(len(v) for v in vals)))

    # Header
    header = "  ".join(gray(col["label"].ljust(w)) for col, w in zip(columns, widths))
    print(f"  {header}")
    print(f"  {'  '.join(gray('─' * w) for w in widths)}")

    # Rows
    for row in rows:
        parts = []
        for col, w in zip(columns, widths):
            raw = str(col["get"](row))
            if "color" in col and col["color"]:
                colored = col["color"](raw)
                # Pad based on visible length
                pad = w - _visible_len(colored)
                parts.append(colored + " " * max(0, pad))
            else:
                parts.append(raw.ljust(w))
        print(f"  {'  '.join(parts)}")


# ── Heading ─────────────────────────────────────────────────────


def heading(text: str) -> None:
    print()
    print(bold(white(text)))
    print(gray("─" * (len(text) + 4)))
