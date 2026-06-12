# ponens.dev

The website for [ponens](https://github.com/imandra-ai/ponens) — built with [Astro](https://astro.build).

## Develop

```bash
cd website
npm install
npm run dev        # prepares inputs, then starts the dev server (http://localhost:4321)
```

## Pages

| Route | What |
|---|---|
| `/` | Landing |
| `/gallery` | Searchable policy gallery (reads `_catalog.json`); cards link to detail pages |
| `/policies/:id` | Per-policy detail (formula, examples, rationale, how to use) |
| `/docs` | Getting started — create → inspect → view → share |
| `/spec` + `/spec/:doc` | The rendered specifications |
| `/viewer` | The embedded trace visualizer (Stripe example, with its residual surface) |

## Generated inputs (`npm run prepare-site`, run automatically before dev/build)

`scripts/prepare.mjs` syncs three things out of the repo so the site is self-contained:

1. **gallery** → `public/gallery/policies` — so the deployed site serves
   `/gallery/policies/_catalog.json`, which is the `ponens` CLI's default registry URL
   (`https://ponens.dev/gallery/policies`).
2. **specs** → `src/pages/spec/*.md` — the `spec/*.md` files, wrapped for rendering.
3. **viewer** → `public/viewer` — the trace visualizer + the Stripe demo trace it auto-loads.

These are generated and git-ignored.

## Build & deploy

```bash
npm run build      # → dist/  (static)
```

Deploy `dist/` to any static host (GitHub Pages, Vercel, Netlify) and point the `ponens.dev`
domain at it. The gallery served at `/gallery/policies` is what the CLI pulls.
