# ponens.dev

The website for [ponens](https://github.com/imandra-ai/ponens) — built with [Astro](https://astro.build).

## Develop

```bash
cd website
npm install
npm run dev        # syncs the gallery, then starts the dev server
```

Open http://localhost:4321.

## How the gallery is served

`npm run sync-gallery` (run automatically before `dev` and `build`) copies
`../gallery/policies` into `public/gallery/policies`, so the deployed site serves
`/gallery/policies/_catalog.json` and the per-policy JSON files. That URL
(`https://ponens.dev/gallery/policies`) is the `ponens` CLI's default registry.

## Build & deploy

```bash
npm run build      # outputs static site to dist/
```

Deploy `dist/` to any static host (GitHub Pages, Vercel, Netlify). Point the
`ponens.dev` domain at it.

## Status

This is an initial scaffold — a landing page and a gallery browser over the catalog.
Spec/docs pages and the embedded trace viewer are still to be wired in.
