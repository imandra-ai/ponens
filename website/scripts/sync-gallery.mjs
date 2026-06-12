// Copies the policy gallery into the site's public/ dir so the deployed site
// serves /gallery/policies/_catalog.json (the CLI's default registry URL) and
// the per-policy JSON files. Run automatically before `dev` and `build`.
import { cp, rm, mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = resolve(here, "../../gallery/policies");
const dest = resolve(here, "../public/gallery/policies");

await rm(dest, { recursive: true, force: true });
await mkdir(dest, { recursive: true });
await cp(src, dest, { recursive: true });
console.log(`synced gallery → ${dest}`);
