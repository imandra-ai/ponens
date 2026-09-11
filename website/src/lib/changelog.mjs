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
function firstClause(tail, max = 110) {
  let t = plain(tail).replace(/^[\s—–:-]+/, "");
  const cut = t.search(/[.;:]\s|[.;:]$|\s[—–]\s/);
  if (cut > 0) t = t.slice(0, cut);
  t = t.trim().replace(/[.,;:]$/, "");
  if (t.length > max) {
    const sp = t.lastIndexOf(" ", max);
    t = (sp > 40 ? t.slice(0, sp) : t.slice(0, max)).replace(/[.,;:]$/, "") + "…";
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
  return { version: latest.version, headline, tail: firstClause(m[2] || "") };
}
