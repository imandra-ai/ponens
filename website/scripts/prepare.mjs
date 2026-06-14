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

async function syncGallery() {
  const dest = resolve(site, "public/gallery/policies");
  await rm(dest, { recursive: true, force: true });
  await mkdir(dest, { recursive: true });
  await cp(resolve(root, "gallery/policies"), dest, { recursive: true });
  console.log("synced gallery → public/gallery/policies");
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
    const title = f.replace(/\.md$/, "").replace(/_/g, " ");
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
  console.log(`synced viewer → public/viewer (${manifest.samples.length} demo traces)`);
}

await syncGallery();
await syncSpecs();
await syncViewer();
