// The viewer's half of the three-way derivation check.
//
// The rule that decides whether a gap is open lives in three places: `lineage.apply_resolutions`
// (Python, what `ponens trace check` uses), `_applyResolutions` here, and `residualsOf` in the agent.
// A viewer showing a gap as open while `check` passes it - or the reverse - is worse than either
// alone, because the disagreement is invisible to both. Same fixtures, same expected answer.
//
//   node viewer/parity.test.mjs
import { readFileSync, readdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const fixtures = join(root, 'cli/tests/fixtures/derivation');

// Load viewer.js in a sandbox with just enough DOM for its module-level statements.
const noop = () => {};
const el = () => ({
  classList: { add: noop, remove: noop, contains: () => false }, style: {}, addEventListener: noop,
  appendChild: noop, remove: noop, querySelector: () => null, querySelectorAll: () => [],
  setAttribute: noop, options: { length: 0 }, add: noop, innerHTML: '', scrollIntoView: noop,
  set textContent(v) { this.innerHTML = String(v); }, get textContent() { return this.innerHTML; },
});
const ctx = {
  console,
  document: { addEventListener: noop, getElementById: () => el(), querySelector: () => null,
    querySelectorAll: () => [], createElement: el, body: el() },
  window: { addEventListener: noop, matchMedia: () => ({ matches: false, addEventListener: noop }),
    location: { search: '', hash: '' } },
  requestAnimationFrame: noop, setTimeout: noop, localStorage: { getItem: () => null, setItem: noop },
  fetch: () => new Promise(() => {}),
};
ctx.globalThis = ctx;
vm.createContext(ctx);
const faith = readFileSync(join(root, 'viewer/core/faithfulness.mjs'), 'utf8').replace(/^export\s+/gm, '');
vm.runInContext(`${faith}\n${readFileSync(join(root, 'viewer/core/viewer.js'), 'utf8')}`, ctx);

const KEYS = ['residual_id', 'status', 'declared_status', 'resolution_contested_by'];

function derive(trace) {
  ctx.__t = trace;
  const surface = vm.runInContext('traceData = __t; normalizeTrace(traceData); traceData.residuals;', ctx);
  // The surface comes out of the vm's realm, so its objects have a different Object prototype than the
  // host's and `deepEqual` reports every one of them as different while printing identical JSON. Bring
  // them across before comparing.
  return JSON.parse(JSON.stringify(surface)).map((r) => {
    const row = {};
    for (const k of KEYS) if (r[k] != null) row[k] = r[k];
    if (r.resolutions?.length) {
      row.resolutions = r.resolutions.map((h) => ({
        resolution_id: h.resolution_id, status: h.status,
        contested_by: [...(h.contested_by || [])].sort(),
      }));
    }
    return row;
  }).sort((a, b) => String(a.residual_id).localeCompare(String(b.residual_id)));
}

const expected = JSON.parse(readFileSync(join(fixtures, 'expected.json'), 'utf8'));
let n = 0;
let bad = 0;
for (const name of Object.keys(expected).sort()) {
  const trace = JSON.parse(readFileSync(join(fixtures, `${name}.json`), 'utf8'));
  n += 1;
  try {
    assert.deepEqual(derive(trace), expected[name]);
  } catch (e) {
    bad += 1;
    console.error(`  ${name}: viewer disagrees with ponens`);
    console.error(`    expected ${JSON.stringify(expected[name])}`);
    console.error(`    got      ${JSON.stringify(derive(trace))}`);
  }
}
console.log(`${bad ? 'FAIL' : 'OK'} - ${n} fixture(s), the viewer derives what ponens derives`
  + (bad ? `, ${bad} disagreement(s)` : ''));
process.exit(bad ? 1 : 0);
