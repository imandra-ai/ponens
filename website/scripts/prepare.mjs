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
    if (!f.endsWith(".md")) continue;
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
  // the visualizer auto-loads demo-traces/stripe_v1_1.json on open
  await cp(resolve(root, "examples/stripe_v1_1.json"),
           resolve(dest, "demo-traces/stripe_v1_1.json"));
  console.log("synced viewer → public/viewer");
}

await syncGallery();
await syncSpecs();
await syncViewer();
