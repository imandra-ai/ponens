// Assemble the self-contained visualizer.html from the reusable core/ parts.
//
// core/ is the source of truth (viewer.css, skeleton.html, viewer.js, head.html); this script
// concatenates them into vscode-plugin/media/visualizer.html, the single self-contained file the
// VS Code plugin and the CLI (`ponens trace view`) consume. The desktop app reuses core/ directly.
//
// Run: node viewer/build.mjs   (after editing anything under viewer/core/)
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const read = (f) => readFileSync(join(here, 'core', f), 'utf8');

const head = read('head.html');
const css = read('viewer.css');
const skeleton = read('skeleton.html');
const js = read('viewer.js');

const html = `${head}<!-- GENERATED from viewer/core/ by viewer/build.mjs - do not edit directly -->
<style>
${css}</style>
</head>
<body>
${skeleton}<script>
${js}</script>
</body>
</html>
`;

const out = join(here, 'vscode-plugin', 'media', 'visualizer.html');
writeFileSync(out, html);
console.log(`built ${out} (${html.length} bytes)`);
