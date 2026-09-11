// The front-page "New" banner is derived from CHANGELOG.md — these pin the rule against the real file
// and against the shapes past releases used, so a release cannot leave the banner stale or malformed.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { latestHighlight, versionsOf, plain } from "../src/lib/changelog.mjs";

const raw = readFileSync(new URL("../../CHANGELOG.md", import.meta.url), "utf8");
const pyver = (readFileSync(new URL("../../cli/pyproject.toml", import.meta.url), "utf8")
  .match(/^version\s*=\s*"([^"]+)"/m) || [])[1];

// 1. The real changelog: latest section = the package version, and it yields a usable banner.
{
  const h = latestHighlight(raw);
  assert.ok(h, "latest release has a bold-led Added bullet");
  assert.equal(h.version, pyver, "banner tracks the released version");
  assert.ok(h.headline.length > 3 && h.headline.length < 80, `headline reasonable: ${h.headline}`);
  assert.ok(!/[*`\[\]]/.test(h.headline + h.tail), "no markdown leaks into the banner");
  assert.ok(h.tail.length <= 112, `tail is a clause, not a paragraph: ${h.tail}`);
  console.log(`latest → ${h.version}: "${h.headline}" — ${h.tail}`);
}

// 2. The shapes past releases used.
{
  const sample = `# Changelog

## [Unreleased]

### Added
- **Not yet shipped.** ignore me.

## [1.9.0] — 2026-08-07

### Added
- **Cryptographic sign-off (\`ponens trace sign\` / \`ponens trace verify\`)** — non-repudiable,
  tamper-evident approval over the trace's \`content_hash\`. Choose a backend.
- **RFC-3161 trusted timestamps.** later bullet.

### Changed
- **Something changed.** not a highlight.

## [1.8.0] — 2026-08-01
`;
  const vs = versionsOf(sample);
  assert.deepEqual(vs.map((v) => v.version), ["Unreleased", "1.9.0", "1.8.0"]);
  assert.equal(vs[1].date, "2026-08-07");
  const h = latestHighlight(sample);
  assert.deepEqual(h, {
    version: "1.9.0",
    headline: "Cryptographic sign-off",
    tail: "non-repudiable, tamper-evident approval over the trace's content_hash",
  });
}

// 3. A headline ending in a period inside the bold, with a tail that opens on a clause break.
{
  const sample = `## [2.0.0] — 2026-10-01\n\n### Added\n- **Oracles are a generic type (\`ORACLE_SPEC_v0_2\`).** An oracle is fixed by its\n  contract, not its mechanism: a formal reasoner, a test runner.\n`;
  assert.deepEqual(latestHighlight(sample), {
    version: "2.0.0",
    headline: "Oracles are a generic type",
    tail: "an oracle is fixed by its contract, not its mechanism",
  });
}

// 4. No Added section, or no bold-led bullet → null (the banner is not rendered, never garbage).
assert.equal(latestHighlight("## [3.0.0] — 2026-11-01\n\n### Fixed\n- a fix\n"), null);
assert.equal(latestHighlight("## [3.0.0]\n\n### Added\n- plain bullet without a bold lead\n"), null);
assert.equal(latestHighlight("no versions here"), null);
assert.equal(plain("**a** *b* `c` [d](e)"), "a b c d");

console.log("changelog.test.mjs: ok");
