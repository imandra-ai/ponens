// Prepares generated inputs for the site (run before dev/build):
//   1. the policy gallery   -> public/gallery        (served as /gallery/policies/*.json)
//   2. the spec markdown     -> src/pages/spec/*.md    (rendered as /spec/* pages)
//   3. the trace visualizer  -> public/viewer          (embedded demo at /viewer.html)
import { cp, rm, mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");        // repo root
const site = resolve(here, "..");              // website/

// Turn a spec FILENAME into a readable title for the nav/sidebar/tab (e.g. TRACE_SPEC_v1_9.md ->
// "Trace Spec v1.9"). Generic rules cover most files; a few irregular names are listed explicitly.
// Tokens whose UPPERCASE form is a known acronym stay uppercase; a `vN_M` pair renders as `vN.M`.
const SPEC_ACRONYMS = new Set([
  "PROV", "CLI", "NIST", "AI", "RMF", "SSDF", "ESMA", "IOSCO", "CMS", "JSF", "AV", "MISRA", "CERT",
  "IML", "VG", "API", "SSDLC",
]);
const SPEC_TITLE_OVERRIDES = {
  "DO_178C_PACK.md": "DO-178C Pack",
  "JSF_AV_CPP_PACK.md": "JSF AV C++ Pack",
  "ESMA_MIFID_AI_PACK.md": "ESMA MiFID AI Pack",
  "TRACE_POLICY_REVIEWCASE_SEMANTICS_v0_2.md": "Trace · Policy · Review-case Semantics v0.2",
};
function prettifySpecTitle(file) {
  if (SPEC_TITLE_OVERRIDES[file]) return SPEC_TITLE_OVERRIDES[file];
  const toks = file.replace(/\.md$/, "").split("_");
  const out = [];
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (/^v\d+$/i.test(t) && i + 1 < toks.length && /^\d+$/.test(toks[i + 1])) {
      out.push(`v${t.slice(1)}.${toks[i + 1]}`);   // v1 + 9 -> v1.9
      i++;
      continue;
    }
    if (SPEC_ACRONYMS.has(t.toUpperCase())) { out.push(t.toUpperCase()); continue; }
    out.push(t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());
  }
  return out.join(" ");
}

async function syncGallery() {
  for (const sub of ["policies", "reasoners", "packs", "organizations"]) {
    const dest = resolve(site, `public/gallery/${sub}`);
    await rm(dest, { recursive: true, force: true });
    await mkdir(dest, { recursive: true });
    await cp(resolve(root, `gallery/${sub}`), dest, { recursive: true });
  }
  console.log("synced gallery → public/gallery/{policies,reasoners,packs,organizations}");
}

async function syncSpecs() {
  const src = resolve(root, "spec");
  const dest = resolve(site, "src/pages/spec");
  // remove only generated .md (keep index.astro)
  await mkdir(dest, { recursive: true });
  for (const f of await readdir(dest)) {
    if (f.endsWith(".md")) await rm(resolve(dest, f));
  }
  for (const f of await readdir(src)) {
    if (!f.endsWith(".md") || f === "README.md") continue;   // README is the repo's spec index; the site has its own
    const body = await readFile(resolve(src, f), "utf8");
    const title = prettifySpecTitle(f);
    const fm = `---\nlayout: ../../layouts/SpecLayout.astro\ntitle: ${JSON.stringify(title)}\nfile: ${JSON.stringify(f)}\n---\n\n`;
    await writeFile(resolve(dest, f), fm + body);
  }
  console.log("synced specs → src/pages/spec");
}

async function syncViewer() {
  const dest = resolve(site, "public/viewer");
  await rm(dest, { recursive: true, force: true });
  await mkdir(resolve(dest, "demo-traces"), { recursive: true });
  await cp(resolve(root, "viewer/vscode-plugin/media/visualizer.html"),
           resolve(dest, "visualizer.html"));

  // examples/ is the single source of truth; sync the manifest's samples into the
  // viewer's demo-traces dirs (here and the plugin's media — both build outputs).
  const manifest = JSON.parse(await readFile(resolve(root, "examples/manifest.json"), "utf8"));
  const pluginDemos = resolve(root, "viewer/vscode-plugin/media/demo-traces");
  await mkdir(pluginDemos, { recursive: true });
  for (const s of manifest.samples) {
    const from = resolve(root, "examples", s.file);
    await cp(from, resolve(dest, "demo-traces", s.file));
    await cp(from, resolve(pluginDemos, s.file));
  }

  // Internal goal-contract gallery: the /internal page deep-links each example into the viewer via
  // ?trace=demo-traces/goal-contract/<file>, so sync that whole dir too.
  const gcSrc = resolve(root, "examples/goal-contract");
  const gcManifest = JSON.parse(await readFile(resolve(gcSrc, "manifest.json"), "utf8"));
  const gcCount = gcManifest.groups.reduce((n, g) => n + g.examples.length, 0);
  await cp(gcSrc, resolve(dest, "demo-traces", "goal-contract"), { recursive: true });
  console.log(`synced viewer → public/viewer (${manifest.samples.length} demo + ${gcCount} goal-contract traces)`);
}

await syncGallery();
await syncSpecs();
await syncViewer();
