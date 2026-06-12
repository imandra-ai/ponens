import { defineConfig } from "astro/config";

// ponens.dev — static site. The policy gallery is synced into public/gallery
// (see scripts/sync-gallery.mjs) so the CLI's default registry URL
// (https://ponens.dev/gallery/policies/_catalog.json) is served from here.
export default defineConfig({
  site: "https://ponens.dev",
});
