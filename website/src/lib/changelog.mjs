// The front-page "New" banner, derived from CHANGELOG.md so a release never leaves it stale.
//
// Rule: take the LATEST `## [x.y.z]` section, its first `### Added` subsection, and that subsection's
// first bullet of the house shape `- **Headline.** tail…`. The bold is the headline (parentheticals and
// code spans dropped); the tail is the first clause after it, ending at the first sentence break.
// Anything that does not fit the shape yields null and the banner is simply not rendered.

/** Split the changelog into [{ version, date, body }] in file order (latest first). */
export function versionsOf(raw) {
  const out = [];
  let cur = null;
  for (const line of raw.split("\n")) {
    const m = line.match(/^## \[([^\]]+)\](?:\s*[—–-]\s*(.*))?$/);
    if (m) {
      cur = { version: m[1].trim(), date: (m[2] || "").trim(), body: [] };
      out.push(cur);
      continue;
    }
    if (cur) cur.body.push(line);
  }
  return out.map((v) => ({ ...v, body: v.body.join("\n") }));
}

/** Strip inline markdown to plain text: bold/italic markers, code spans, links. */
export function plain(s) {
  return s
    .replace(/`([^`]*)`/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/(^|[^*])\*([^*]+)\*(?!\*)/g, "$1$2")
    .replace(/\s+/g, " ")
    .trim();
}

/** The first `- **…**` bullet under the first `### Added` of a version body, joined across its
 *  continuation lines (two-space indented). */
function firstAddedBullet(body) {
  const lines = body.split("\n");
  let inAdded = false;
  let bullet = null;
  for (const line of lines) {
    if (/^### /.test(line)) {
      if (bullet) break;
      inAdded = /^### Added\b/.test(line);
      continue;
    }
    if (!inAdded) continue;
    if (/^- \*\*/.test(line)) {
      if (bullet) break;
      bullet = line.slice(2);
      continue;
    }
    if (bullet !== null) {
      if (/^\s{2,}\S/.test(line)) bullet += " " + line.trim();
      else break;
    }
  }
  return bullet;
}

/** First clause of a tail: up to the first sentence break (`.`, `:`, `;`, or ` — `), trimmed and
 *  lower-cased at the first letter (the banner reads "…headline — tail."). Long tails are cut at a
 *  word boundary. */
/** One line, beside a link, at the width the hero gives it. */
export const BANNER_MAX = 118;

function firstClause(tail, max = 110) {
  let t = plain(tail).replace(/^[\s—–:-]+/, "");
  // A single spaced hyphen is the house dash, so it is the clause break that actually occurs in this
  // changelog - matching only the em dash meant nothing ever cut and every tail ran to the ellipsis.
  const cut = t.search(/[.;:]\s|[.;:]$|\s[—–-]\s/);
  if (cut > 0) t = t.slice(0, cut);
  t = t.trim().replace(/[.,;:]$/, "");
  if (t.length > max) {
    // The ellipsis is a CHARACTER and counts against the budget. Slicing to `max` and then appending
    // it produced max + 1 every time, so the banner this budget exists to keep on one line came out
    // one character too long - and the test never saw it, because it bounded the tail alone rather
    // than the whole banner, which is the exact mistake the budget was introduced to fix.
    const room = max - 1;
    const sp = t.lastIndexOf(" ", room);
    t = (sp > 40 ? t.slice(0, sp) : t.slice(0, room)).replace(/[.,;:]$/, "") + "…";
  }
  if (/^[A-Z][a-z]/.test(t)) t = t[0].toLowerCase() + t.slice(1);
  return t;
}

/**
 * The banner for the latest release: { version, headline, tail } or null.
 *   headline — the bold lead, parentheticals and trailing punctuation removed
 *   tail     — the first clause after it (may be empty)
 */
export function latestHighlight(raw) {
  const versions = versionsOf(raw).filter((v) => /^\d/.test(v.version)); // skip [Unreleased]
  const latest = versions[0];
  if (!latest) return null;
  const bullet = firstAddedBullet(latest.body);
  if (!bullet) return null;
  const m = bullet.match(/^\*\*(.+?)\*\*\s*(.*)$/s);
  if (!m) return null;
  const headline = plain(m[1]).replace(/\s*\([^)]*\)/g, "").replace(/\s*[—–-]\s*$/, "").replace(/[.:]$/, "").trim();
  if (!headline) return null;
  // Budget the WHOLE banner, not just the tail. It is one line beside a "What's new →" link, and
  // capping the tail alone let a long headline plus a full-length tail wrap to two lines and end in a
  // mid-thought ellipsis. A tail with no room left to say anything is worse than no tail.
  const room = BANNER_MAX - headline.length - 3;          // 3 = the " — " joining them
  const tail = room >= 30 ? firstClause(m[2] || "", room) : "";
  return { version: latest.version, headline, tail };
}
