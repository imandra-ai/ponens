// @ts-check
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const http = require('http');

/** @type {vscode.WebviewPanel | undefined} */
let panel;

/** @type {fs.FSWatcher | undefined} */
let fileWatcher;

/** @type {string} */
let currentSource = '';  // 'demo:name' or 'file:/path'

/** @type {string} */
let currentTraceJson = '';

/** @type {http.Server | undefined} */
let browserServer;

/** @type {vscode.StatusBarItem} */
let statusBarItem;

/**
 * @param {vscode.ExtensionContext} context
 */
function activate(context) {
  // Status bar
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  statusBarItem.command = 'codelogician.selectDemo';
  statusBarItem.tooltip = 'Click to change trace source';
  context.subscriptions.push(statusBarItem);

  // Command: Open Viewer
  context.subscriptions.push(
    vscode.commands.registerCommand('codelogician.openViewer', () => {
      openViewer(context);
    })
  );

  // Command: Open in Browser
  context.subscriptions.push(
    vscode.commands.registerCommand('codelogician.openInBrowser', () => {
      openInBrowser(context);
    })
  );

  // Command: Select Trace File
  context.subscriptions.push(
    vscode.commands.registerCommand('codelogician.selectTraceFile', async () => {
      const uris = await vscode.window.showOpenDialog({
        canSelectFiles: true,
        canSelectMany: false,
        filters: { 'JSON': ['json'] },
        title: 'Select a trace JSON file'
      });
      if (uris && uris.length) {
        watchTraceFile(uris[0].fsPath, context);
      }
    })
  );

  // Command: Select Demo
  context.subscriptions.push(
    vscode.commands.registerCommand('codelogician.selectDemo', async () => {
      const demoDir = path.join(context.extensionPath, 'demo-traces');
      const files = fs.readdirSync(demoDir).filter(f => f.endsWith('.json'));

      const items = [
        {
          label: '$(file) Select trace file from disk...',
          description: '',
          detail: 'Watch a local trace JSON file for changes',
          file: '',
          isDemo: false,
          kind: vscode.QuickPickItemKind.Default,
        },
        {
          label: 'Demo Traces',
          kind: vscode.QuickPickItemKind.Separator,
        },
        ...files.map(f => {
          const nameMap = {
            'stripe_v1_1.json': 'Stripe Payment Flow (v1.1)',
            'auth_xstate_v1_1.json': 'Auth XState Machine',
            'form_validation_v1_1.json': 'Form Validation',
            'api_pagination_v1_1.json': 'API Pagination',
            'cart_reducer_v1_1.json': 'Cart Reducer',
          };
          return {
            label: nameMap[f] || f.replace('.json', '').replace(/_/g, ' '),
            description: currentSource === `demo:${f}` ? '(current)' : '',
            detail: 'Demo trace',
            file: f,
            isDemo: true,
          };
        }),
      ];

      const picked = await vscode.window.showQuickPick(items, {
        placeHolder: 'Select a trace source',
        title: 'CodeLogician: Trace Source'
      });

      if (!picked) return;

      if (!picked.isDemo) {
        vscode.commands.executeCommand('codelogician.selectTraceFile');
        return;
      }

      const demoPath = path.join(demoDir, picked.file);
      loadDemo(picked.file, demoPath, context);
    })
  );

  // Command: Open from Explorer (right-click on .json file)
  context.subscriptions.push(
    vscode.commands.registerCommand('codelogician.openFromExplorer', async (uri) => {
      if (!uri || !uri.fsPath) return;

      const validation = validateTraceFile(uri.fsPath);
      if (!validation.ok) {
        vscode.window.showErrorMessage(
          `Not a valid CodeLogician trace: ${validation.error}`,
          'OK'
        );
        return;
      }

      openViewer(context);
      watchTraceFile(uri.fsPath, context);
    })
  );

  // Auto-load configured trace file or default demo
  const configPath = vscode.workspace.getConfiguration('codelogician').get('traceFile');
  if (configPath && typeof configPath === 'string' && configPath.length > 0) {
    const resolved = resolveWorkspacePath(configPath);
    if (fs.existsSync(resolved)) {
      watchTraceFile(resolved, context);
    } else {
      loadDefaultDemo(context);
    }
  } else {
    loadDefaultDemo(context);
  }
}

function deactivate() {
  if (fileWatcher) {
    fileWatcher.close();
    fileWatcher = undefined;
  }
  if (browserServer) {
    browserServer.close();
    browserServer = undefined;
  }
}

// ================================================================
// Trace validation
// ================================================================

/**
 * Validate that a file is a valid CodeLogician trace.
 * Returns { ok: true } or { ok: false, error: string }.
 */
function validateTraceFile(filePath) {
  // Check file exists and is readable
  if (!fs.existsSync(filePath)) {
    return { ok: false, error: 'File does not exist.' };
  }

  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf-8');
  } catch (e) {
    return { ok: false, error: `Cannot read file: ${e.message}` };
  }

  // Check it's valid JSON
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return { ok: false, error: `Invalid JSON: ${e.message}` };
  }

  // Check it's an object
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { ok: false, error: 'JSON root must be an object.' };
  }

  // Check required trace fields
  if (!data.trace_id && !data.actions) {
    return { ok: false, error: 'Missing required fields: expected trace_id or actions. This does not look like a CodeLogician trace.' };
  }

  if (!data.actions || !Array.isArray(data.actions)) {
    return { ok: false, error: 'Missing or invalid "actions" array.' };
  }

  if (!data.trigger || typeof data.trigger !== 'object') {
    return { ok: false, error: 'Missing or invalid "trigger" event.' };
  }

  if (!data.outcome || typeof data.outcome !== 'object') {
    return { ok: false, error: 'Missing or invalid "outcome" event.' };
  }

  return { ok: true };
}

/**
 * Validate trace JSON string. Returns { ok, error, data }.
 */
function validateTraceJson(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return { ok: false, error: `Invalid JSON: ${e.message}`, data: null };
  }

  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return { ok: false, error: 'JSON root must be an object.', data: null };
  }

  if (!data.actions || !Array.isArray(data.actions)) {
    return { ok: false, error: 'Missing or invalid "actions" array.', data: null };
  }

  return { ok: true, error: null, data };
}

// ================================================================
// Trace loading
// ================================================================

function loadDefaultDemo(context) {
  const demoPath = path.join(context.extensionPath, 'demo-traces', 'stripe_v1_1.json');
  if (fs.existsSync(demoPath)) {
    loadDemo('stripe_v1_1.json', demoPath, context);
  }
}

function loadDemo(fileName, filePath, context) {
  if (fileWatcher) {
    fileWatcher.close();
    fileWatcher = undefined;
  }
  currentSource = `demo:${fileName}`;
  const data = fs.readFileSync(filePath, 'utf-8');
  currentTraceJson = data;
  updateStatusBar();
  sendTraceToPanel();
}

function watchTraceFile(filePath, context) {
  if (fileWatcher) {
    fileWatcher.close();
    fileWatcher = undefined;
  }

  // Make path workspace-relative for display
  const wsFolder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const displayPath = wsFolder && filePath.startsWith(wsFolder)
    ? filePath.slice(wsFolder.length + 1)
    : path.basename(filePath);
  currentSource = `file:${displayPath}`;
  loadTraceFromFile(filePath);

  try {
    fileWatcher = fs.watch(filePath, { persistent: false }, (eventType) => {
      if (eventType === 'change') {
        // Debounce
        setTimeout(() => {
          loadTraceFromFile(filePath);
        }, 200);
      }
    });
  } catch (e) {
    vscode.window.showWarningMessage(`Could not watch file: ${filePath}`);
  }

  updateStatusBar();
}

function loadTraceFromFile(filePath) {
  let raw;
  try {
    raw = fs.readFileSync(filePath, 'utf-8');
  } catch (e) {
    return; // file might be mid-write
  }

  const validation = validateTraceJson(raw);
  if (!validation.ok) {
    // On watch-triggered reload, show a non-intrusive warning
    // (don't block the UI — the file might be mid-save)
    if (panel) {
      panel.webview.postMessage({
        type: 'parseError',
        error: validation.error,
        source: currentSource,
      });
    }
    return;
  }

  currentTraceJson = raw;
  sendTraceToPanel();
}

function sendTraceToPanel() {
  if (panel) {
    panel.webview.postMessage({
      type: 'loadTrace',
      trace: currentTraceJson,
      source: currentSource,
    });
  }
}

function updateStatusBar() {
  if (currentSource.startsWith('demo:')) {
    const name = currentSource.replace('demo:', '').replace('.json', '').replace(/_/g, ' ');
    statusBarItem.text = `$(beaker) Demo: ${name}`;
    statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
  } else if (currentSource.startsWith('file:')) {
    const name = path.basename(currentSource.replace('file:', ''));
    statusBarItem.text = `$(file) Trace: ${name}`;
    statusBarItem.backgroundColor = undefined;
  } else {
    statusBarItem.text = `$(eye) CodeLogician`;
    statusBarItem.backgroundColor = undefined;
  }
  statusBarItem.show();
}

// ================================================================
// Webview panel
// ================================================================

function openViewer(context) {
  if (panel) {
    panel.reveal();
    sendTraceToPanel();
    return;
  }

  panel = vscode.window.createWebviewPanel(
    'codelogicianViewer',
    'CodeLogician Trace Viewer',
    vscode.ViewColumn.Beside,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [
        vscode.Uri.file(path.join(context.extensionPath, 'media')),
      ],
    }
  );

  panel.webview.html = getWebviewContent(context, panel.webview);

  panel.webview.onDidReceiveMessage((msg) => {
    if (msg.type === 'openInBrowser') {
      openInBrowser(context);
    } else if (msg.type === 'selectDemo') {
      vscode.commands.executeCommand('codelogician.selectDemo');
    } else if (msg.type === 'selectFile') {
      vscode.commands.executeCommand('codelogician.selectTraceFile');
    } else if (msg.type === 'loadDemo') {
      // Load a demo by filename from the dropdown
      // Strip 'demo-traces/' prefix if present (shared visualizer uses full relative paths)
      const demoFile = msg.file.replace(/^demo-traces\//, '');
      const demoDir = path.join(context.extensionPath, 'demo-traces');
      const demoPath = path.join(demoDir, demoFile);
      if (fs.existsSync(demoPath)) {
        loadDemo(demoFile, demoPath, context);
      } else {
        vscode.window.showWarningMessage(`Demo trace not found: ${demoFile}`);
      }
    } else if (msg.type === 'ready') {
      sendTraceToPanel();
    }
  });

  panel.onDidDispose(() => {
    panel = undefined;
  });
}

function getWebviewContent(context, webview) {
  // Read the shared visualizer HTML (canonical source at repo root, fallback to bundled copy)
  const sharedPath = path.join(context.extensionPath, '..', 'visualizer.html');
  const bundledPath = path.join(context.extensionPath, 'media', 'visualizer.html');
  const vizPath = fs.existsSync(sharedPath) ? sharedPath : bundledPath;
  let html = fs.readFileSync(vizPath, 'utf-8');

  // Inject the VS Code API bridge and source banner
  const bridgeScript = `
<script>
  // VS Code webview API
  window.vscodeApi = acquireVsCodeApi();

  // Override the default fetch-based loading
  // Instead, wait for trace data via postMessage
  window._skipDefaultFetch = true;

  window.addEventListener('message', (event) => {
    const msg = event.data;
    if (msg.type === 'loadTrace') {
      try {
        const data = JSON.parse(msg.trace);
        loadTrace(data);
        updateSourceBanner(msg.source);
        hideError();
        // Sync dropdown state
        if (typeof updateDemoBadge === 'function') {
          if (msg.source && msg.source.startsWith('demo:')) {
            var demoFile = msg.source.replace('demo:', '');
            // Match DEMO_TRACES entries which use 'demo-traces/' prefix
            var vizFile = 'demo-traces/' + demoFile;
            _currentDemoFile = vizFile;
            updateDemoBadge(vizFile);
          } else if (msg.source && msg.source.startsWith('file:')) {
            _currentDemoFile = '';
            updateDemoBadge('');
            if (typeof showFileLabel === 'function') {
              showFileLabel(msg.source.replace('file:', ''));
            }
          } else {
            _currentDemoFile = '';
            updateDemoBadge('');
          }
        }
      } catch(e) {
        console.error('Failed to load trace:', e);
        showError('Failed to parse trace: ' + e.message);
      }
    }
    if (msg.type === 'parseError') {
      showError(msg.error);
    }
  });

  function updateSourceBanner(source) {
    const banner = document.getElementById('sourceBanner');
    if (!banner) return;
    if (source && source.startsWith('demo:')) {
      const name = source.replace('demo:', '').replace('.json', '').replace(/_/g, ' ');
      banner.style.display = 'flex';
      banner.innerHTML = '<span class="sb-icon">&#9881;</span> <span>Demo: ' + name + '</span>' +
        '<button onclick="vscodeApi.postMessage({type:\\'selectDemo\\'})" class="sb-btn">Change</button>';
    } else if (source && source.startsWith('file:')) {
      const name = source.split('/').pop().split('\\\\').pop();
      banner.style.display = 'flex';
      banner.className = 'source-banner file';
      banner.innerHTML = '<span class="sb-icon">&#128196;</span> <span>Watching: ' + name + '</span>' +
        '<button onclick="vscodeApi.postMessage({type:\\'selectDemo\\'})" class="sb-btn">Change</button>';
    } else {
      banner.style.display = 'none';
    }
  }

  function showError(msg) {
    const banner = document.getElementById('errorBanner');
    const msgEl = document.getElementById('errorMsg');
    if (banner && msgEl) {
      msgEl.textContent = msg;
      banner.style.display = 'flex';
    }
  }

  function hideError() {
    const banner = document.getElementById('errorBanner');
    if (banner) banner.style.display = 'none';
  }

  // Signal ready
  setTimeout(() => vscodeApi.postMessage({ type: 'ready' }), 100);
</script>
`;

  // Inject source banner CSS
  const bannerCSS = `
<style>
  .source-banner {
    display: none; align-items: center; gap: 8px;
    padding: 4px 16px; font-size: 11px; font-weight: 600;
    background: #3a3520; color: #e0d090; border-bottom: 1px solid #4a4530;
  }
  .error-banner {
    display: none; align-items: center; gap: 8px;
    padding: 8px 16px; font-size: 12px; font-weight: 500;
    background: #3a2020; color: #e0a0a0; border-bottom: 1px solid #4a3030;
  }
  .error-banner .eb-icon { font-size: 14px; }
  .error-banner .eb-msg { flex: 1; }
  .error-banner .eb-dismiss {
    background: none; border: none; color: #e0a0a0; font-size: 16px;
    cursor: pointer; opacity: 0.6; padding: 0 4px;
  }
  .error-banner .eb-dismiss:hover { opacity: 1; }
  .source-banner.file {
    background: var(--bg-elevated); color: var(--text-muted);
    border-bottom: 1px solid var(--border);
  }
  .source-banner .sb-icon { font-size: 13px; }
  .source-banner .sb-btn {
    margin-left: auto; background: none; border: 1px solid currentColor;
    color: inherit; padding: 1px 8px; border-radius: 3px; font-size: 10px;
    cursor: pointer; opacity: 0.7;
  }
  .source-banner .sb-btn:hover { opacity: 1; }

  /* Hide elements not needed in VS Code webview */
  .source-banner { display: none !important; }
  .report-btn { display: none !important; }

  /* Open in browser button */
  .browser-btn {
    background: var(--bg-deep); border: 1px solid var(--border);
    color: var(--text-muted); padding: 4px 10px; border-radius: 4px;
    font-size: 12px; cursor: pointer; transition: all 0.15s;
    display: flex; align-items: center; gap: 4px; margin-left: 4px;
  }
  .browser-btn:hover { border-color: var(--border-hover); color: var(--text-primary); }
</style>
`;

  // Add "Open in Browser" button before closing header
  html = html.replace(
    '</header>',
    `  <button class="browser-btn" onclick="vscodeApi.postMessage({type:'openInBrowser'})" title="Open full UI in browser">&#127760; Browser</button>\n</header>`
  );

  // Add banner after header
  html = html.replace('</header>', `</header>\n<div class="source-banner" id="sourceBanner"></div>\n<div class="error-banner" id="errorBanner"><span class="eb-icon">&#9888;</span><span class="eb-msg" id="errorMsg"></span><button class="eb-dismiss" onclick="hideError()">&times;</button></div>`);

  // Disable the default demo loading by removing the initDemoSelector call
  // and fetch. We inject a script that suppresses the default and waits for postMessage.
  const suppressScript = `
<script>
  // Suppress default trace loading — VS Code extension sends trace via postMessage
  window._vscodeManaged = true;
</script>
`;
  html = html.replace('<script>', suppressScript + '\n<script>', );

  // Inject bridge script before the LAST </body> (not the one inside the PDF report template)
  const lastBodyIdx = html.lastIndexOf('</body>');
  if (lastBodyIdx !== -1) {
    html = html.slice(0, lastBodyIdx) + bridgeScript + '\n' + html.slice(lastBodyIdx);
  }

  // Inject banner CSS before closing style
  html = html.replace('</style>', bannerCSS + '\n</style>');

  return html;
}

// ================================================================
// Open in Browser
// ================================================================

function openInBrowser(context) {
  // Start a tiny HTTP server and open in browser
  if (browserServer) {
    browserServer.close();
  }

  const sharedVizPath = path.join(context.extensionPath, '..', 'visualizer.html');
  const bundledVizPath = path.join(context.extensionPath, 'media', 'visualizer.html');
  const vizPath = fs.existsSync(sharedVizPath) ? sharedVizPath : bundledVizPath;
  let html = fs.readFileSync(vizPath, 'utf-8');

  // Inject a script that loads the trace data after the page initializes.
  // This runs after all the visualizer JS, so loadTrace is guaranteed to exist.
  // It overrides whatever the default demo loading does.
  const traceJson = currentTraceJson || 'null';
  const sourceStr = JSON.stringify(currentSource || '');
  const loaderScript = `
<script>
(function() {
  var _extensionTrace = ${traceJson};
  var _extensionSource = ${sourceStr};
  if (_extensionTrace) {
    function _tryLoad() {
      if (typeof loadTrace === 'function') {
        loadTrace(_extensionTrace);
        // Sync dropdown/badge/file label to match extension state
        if (_extensionSource.startsWith('demo:')) {
          var demoFile = 'demo-traces/' + _extensionSource.replace('demo:', '');
          _currentDemoFile = demoFile;
          if (typeof updateDemoBadge === 'function') updateDemoBadge(demoFile);
        } else if (_extensionSource.startsWith('file:')) {
          _currentDemoFile = '';
          if (typeof updateDemoBadge === 'function') updateDemoBadge('');
          if (typeof showFileLabel === 'function') showFileLabel(_extensionSource.replace('file:', ''));
        }
      } else {
        setTimeout(_tryLoad, 50);
      }
    }
    setTimeout(_tryLoad, 200);
  }
})();
</script>
`;
  // Inject before the LAST </body> (not the one inside the PDF report template)
  const lastBodyIdx = html.lastIndexOf('</body>');
  if (lastBodyIdx !== -1) {
    html = html.slice(0, lastBodyIdx) + loaderScript + '\n' + html.slice(lastBodyIdx);
  }

  const demoDir = path.join(context.extensionPath, 'demo-traces');

  function handleRequest(req, res) {
    // Serve demo trace JSON files
    if (req.url && req.url.startsWith('/demo-traces/') && req.url.endsWith('.json')) {
      const fileName = path.basename(req.url);
      const filePath = path.join(demoDir, fileName);
      if (fs.existsSync(filePath)) {
        res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
        res.end(fs.readFileSync(filePath, 'utf-8'));
        return;
      }
    }
    // Default: serve the HTML page
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end(html);
  }

  function startServer(html, preferredPort) {
    browserServer = http.createServer(handleRequest);

    browserServer.on('error', () => {
      // Port in use — pick a random one
      browserServer = http.createServer(handleRequest);
      browserServer.listen(0, '127.0.0.1', () => {
        const addr = browserServer.address();
        vscode.env.openExternal(vscode.Uri.parse(`http://127.0.0.1:${addr.port}`));
      });
    });

    browserServer.listen(preferredPort, '127.0.0.1', () => {
      vscode.env.openExternal(vscode.Uri.parse(`http://127.0.0.1:${preferredPort}`));
      vscode.window.showInformationMessage(`CodeLogician Traces opened in browser at http://127.0.0.1:${preferredPort}`);
    });
  }

  startServer(html, 18923);
}

// ================================================================
// Helpers
// ================================================================

function resolveWorkspacePath(p) {
  if (path.isAbsolute(p)) return p;
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length) {
    return path.join(folders[0].uri.fsPath, p);
  }
  return p;
}

module.exports = { activate, deactivate };
