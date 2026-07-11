// ============================================================
// Theme
// ============================================================
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('ponens-theme', next);
  updateThemeButton(next);
  // Re-render views that use inline theme colors
  const activeView = document.querySelector('.top-view.active');
  if (activeView?.id === 'view-dag') renderDAGView();
  if (activeView?.id === 'view-funnel') renderFunnelView();
  if (activeView?.id === 'view-policy') renderPolicyView();
}

function updateThemeButton(theme) {
  const icon = document.getElementById('themeIcon');
  const label = document.getElementById('themeLabel');
  if (theme === 'light') {
    icon.innerHTML = '&#9728;';  // sun
    label.textContent = 'Dark';
  } else {
    icon.innerHTML = '&#9790;';  // moon
    label.textContent = 'Light';
  }
}

// Initialize theme from localStorage or system preference
{
  const saved = localStorage.getItem('ponens-theme');
  if (saved) {
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeButton(saved);
  } else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
    document.documentElement.setAttribute('data-theme', 'light');
    updateThemeButton('light');
  }
}

// ============================================================
// State
// ============================================================
let traceData = null;

// ============================================================
// Resize handle
// ============================================================
{
  const handle = document.getElementById('resizeHandle');
  const panel = document.getElementById('detailPanel');
  let dragging = false;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    dragging = true;
    handle.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });

  document.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    const mainArea = document.querySelector('.main-area');
    const rect = mainArea.getBoundingClientRect();
    const newWidth = rect.right - e.clientX;
    const clamped = Math.max(280, Math.min(newWidth, rect.width * 0.7));
    panel.style.width = clamped + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Re-render detail panel so Voronoi redraws at new width
    if (typeof _selectedActionId !== 'undefined' && _selectedActionId !== null) {
      selectAction(_selectedActionId);
    }
  });
}

// ============================================================
// Load
// ============================================================
const dropZone = document.getElementById('dropZone');
document.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('visible'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) dropZone.classList.remove('visible'); });
document.addEventListener('drop', e => {
  e.preventDefault(); dropZone.classList.remove('visible');
  const f = e.dataTransfer.files[0];
  if (f) f.text().then(t => {
    loadTrace(JSON.parse(t));
    _currentDemoFile = '';
    updateDemoBadge('');
    showFileLabel(f.name);
    const select = document.getElementById('demoSelect');
    if (select) select.value = '';
  });
});
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ============================================================
// Demo trace management
// ============================================================
// Kept in sync with examples/manifest.json (the source of truth). prepare.mjs
// copies these files into demo-traces/ at build time.
const DEMO_TRACES = [
  { name: 'Payment Idempotency (proved)', file: 'demo-traces/sample_payment_idempotency.json' },
  { name: 'Auth State Machine (reachability)', file: 'demo-traces/sample_auth_xstate.json' },
  { name: 'ETL Refactor (conformance)', file: 'demo-traces/sample_etl_refactor.json' },
  { name: 'Stripe Payment Flow', file: 'demo-traces/stripe_v1_1.json' },
  { name: 'Form Validation', file: 'demo-traces/form_validation_v1_1.json' },
  { name: 'API Pagination', file: 'demo-traces/api_pagination_v1_1.json' },
  { name: 'Cart Reducer', file: 'demo-traces/cart_reducer_v1_1.json' },
];

let _currentDemoFile = '';

function initDemoSelector() {
  const select = document.getElementById('demoSelect');
  if (!select) return;
  // Clear existing options after the placeholder
  while (select.options.length > 1) select.remove(1);
  for (const demo of DEMO_TRACES) {
    const opt = document.createElement('option');
    opt.value = demo.file;
    opt.textContent = demo.name;
    select.appendChild(opt);
  }
  // Add separator + custom file option
  const sep = document.createElement('option');
  sep.disabled = true;
  sep.textContent = '────────────';
  select.appendChild(sep);
  const custom = document.createElement('option');
  custom.value = '__drop__';
  custom.textContent = 'Select a file to view';
  select.appendChild(custom);
}

function loadDemoTrace(file) {
  if (!file || file === '__drop__') {
    // In VS Code, delegate file picking to the extension
    if (window._vscodeManaged && typeof vscodeApi !== 'undefined') {
      vscodeApi.postMessage({ type: 'selectFile' });
      document.getElementById('demoSelect').value = _currentDemoFile || '';
      return;
    }
    // Browser: open native file picker dialog
    document.getElementById('demoSelect').value = _currentDemoFile || '';
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
      const f = e.target.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        let data;
        try {
          data = JSON.parse(ev.target.result);
        } catch (err) {
          alert('Invalid JSON file: ' + err.message);
          return;
        }
        loadTrace(data);
        _currentDemoFile = '';
        updateDemoBadge('');
        showFileLabel(f.name);
        document.getElementById('demoSelect').value = '';
      };
      reader.readAsText(f);
    };
    input.click();
    return;
  }
  // If inside VS Code webview, delegate to extension
  if (window._vscodeManaged && typeof vscodeApi !== 'undefined') {
    vscodeApi.postMessage({ type: 'loadDemo', file: file });
    return;
  }
  _currentDemoFile = file;
  fetch(file)
    .then(r => { if (!r.ok) throw new Error(r.statusText); return r.json(); })
    .then(data => {
      loadTrace(data);
      updateDemoBadge(file);
    })
    .catch(e => {
      console.error('Failed to load demo:', e);
      document.getElementById('demoSelect').value = _currentDemoFile;
    });
}

function updateDemoBadge(file) {
  const badge = document.getElementById('demoBadge');
  const select = document.getElementById('demoSelect');
  const fileLabel = document.getElementById('fileLabel');
  if (!badge) return;
  const isDemo = DEMO_TRACES.some(d => d.file === file);
  badge.style.display = isDemo ? '' : 'none';
  if (isDemo && fileLabel) fileLabel.style.display = 'none';
  if (select) select.value = file;
}

function showFileLabel(name) {
  const label = document.getElementById('fileLabel');
  const badge = document.getElementById('demoBadge');
  if (label) {
    label.textContent = name;
    label.title = name;
    label.style.display = '';
  }
  if (badge) badge.style.display = 'none';
}

// Initialize
initDemoSelector();

// Load default trace (skip if managed by VS Code extension). Default to a 1.6
// sample so the meta-action zoom is visible on open.
if (!window._vscodeManaged && !window.__ponensEmbedded) {
  _currentDemoFile = 'demo-traces/sample_payment_idempotency.json';
  // Set dropdown immediately so it doesn't show placeholder
  const _sel = document.getElementById('demoSelect');
  if (_sel) _sel.value = _currentDemoFile;
  fetch(_currentDemoFile).then(r => r.json()).then(data => {
    loadTrace(data);
    updateDemoBadge(_currentDemoFile);
  }).catch(() => {
    _currentDemoFile = 'trace.json';
    if (_sel) _sel.value = 'trace.json';
    fetch('trace.json').then(r => r.json()).then(data => {
      loadTrace(data);
      updateDemoBadge('trace.json');
    }).catch(() => {});
  });
}

// ============================================================
// v1.0 / v1.1 normalization layer
// ============================================================
function normalizeTrace(data) {
  // Detect version
  const version = data.spec_version || (data.artifacts ? '1.1' : '1.0');
  data._spec_version = version;

  if (version === '1.0') return; // no normalization needed

  // Build artifact lookup
  const artifactMap = {};
  for (const art of (data.artifacts || [])) {
    artifactMap[art.artifact_id] = art;
  }
  data._artifactMap = artifactMap;

  // Hydrate reasoning payloads onto actions from artifact payloads
  for (const action of (data.actions || [])) {
    // Store original artifact IDs for lineage tracing
    action._original_inputs = action.inputs ? [...action.inputs] : [];
    action._original_outputs = action.outputs ? [...action.outputs] : [];

    for (const outId of (action.outputs || [])) {
      const art = artifactMap[outId];
      if (!art || !art.payload) continue;

      switch (art.artifact_type) {
        case 'Formalization':
          action.formalization = art.payload;
          break;
        case 'IMLModel':
          // IMLModel may carry formalization payload
          if (art.payload.iml_code) action.formalization = art.payload;
          break;
        case 'VerificationGoal':
          action.vg_defined = art.payload;
          break;
        case 'VerificationResult':
          action.vg_result = art.payload;
          break;
        case 'Decomposition':
        case 'StateSpaceAnalysisResult':
          action.decomposition = art.payload;
          // Normalize target_symbol \u2192 target_function for rendering
          if (art.payload.target_symbol && !art.payload.target_function) {
            art.payload.target_function = art.payload.target_symbol;
          }
          break;
        case 'GeneratedTests':
          action.generated_tests = art.payload;
          break;
      }
    }

    // Resolve artifact IDs to display names
    action.inputs = (action.inputs || []).map(id => {
      const art = artifactMap[id];
      return art ? (art.name || art.artifact_id) : id;
    });
    action.outputs = (action.outputs || []).map(id => {
      const art = artifactMap[id];
      return art ? (art.name || art.artifact_id) : id;
    });
  }

  // Convert policies + policy_evaluations \u2192 process_properties
  if (data.policies && !data.process_properties) {
    const policyMap = {};
    for (const p of data.policies) policyMap[p.policy_id] = p;
    const evals = data.policy_evaluations || [];
    data.process_properties = evals.map(pe => ({
      name: (policyMap[pe.policy_id] || {}).name || pe.policy_id,
      passed: pe.status === 'passed' || pe.status === 'not_applicable',
      _policy: policyMap[pe.policy_id],
      _evaluation: pe
    }));
  }

  // Normalize flat metrics
  if (data.metrics) {
    for (const k of ['total_actions','decision_points','parallel_blocks','loops','max_loop_iterations']) {
      if (data.metrics[k] != null && data[k] == null) data[k] = data.metrics[k];
    }
  }
}

function validateTrace(data) {
  if (!data || typeof data !== 'object') return 'File does not contain a valid JSON object.';
  if (!Array.isArray(data.actions) || data.actions.length === 0) return 'Missing or empty "actions" array — this does not appear to be a Ponens trace file.';
  const first = data.actions[0];
  if (!first.type && !first.label) return 'Actions are missing required fields (type, label) — unrecognized trace format.';
  return null;
}

function loadTrace(data) {
  const err = validateTrace(data);
  if (err) {
    alert(err);
    return;
  }
  normalizeTrace(data);
  traceData = data;

  // Header with optional version badge
  document.getElementById('traceMeta').innerHTML =
    `<span>LLM used: ${esc(data.model)}</span><span>Trace updated: ${esc(data.timestamp)}</span>`;
  // Show spec version next to title
  const vBadgeEl = document.getElementById('headerVersionBadge');
  if (vBadgeEl) {
    if (data._spec_version && data._spec_version !== '1.0') {
      vBadgeEl.textContent = 'v' + data._spec_version;
      vBadgeEl.style.display = '';
    } else {
      vBadgeEl.style.display = 'none';
    }
  }

  renderFlow(data);

  // Update counts
  document.getElementById('vgCount').textContent = collectVGs().length;
  document.getElementById('formalCount').textContent = collectFormalizations().length;
  document.getElementById('decompCount').textContent = collectDecomps().length;
  document.getElementById('testCount').textContent = collectTests().reduce((s, g) => s + (g.tests?.length ?? g.count ?? 0), 0);
  document.getElementById('propsCount').textContent = (data.process_properties || []).length;

  // Show policies button for v1.1 traces
  if (data.policies?.length) {
    document.getElementById('policiesBtn').style.display = '';
    document.getElementById('policiesCount').textContent = data.policies.length;
    document.getElementById('policyViewBtn').style.display = '';
  }

  // Show residuals button (v1.5 residual surface)
  if (data.residuals?.length) {
    document.getElementById('residualsBtn').style.display = '';
    document.getElementById('residualsCount').textContent = data.residuals.length;
  }

  // Show DAG view for v1.1 traces with artifacts
  if (data.artifacts?.length) {
    document.getElementById('dagViewBtn').style.display = '';
  }

  // Show reference models button
  if (data.reference_models?.length) {
    document.getElementById('refModelsBtn').style.display = '';
    document.getElementById('refModelsCount').textContent = data.reference_models.length;
  }

  // Show Goals view for v1.7 traces with declared goals (§18)
  if (data.goals?.length) {
    document.getElementById('goalsViewBtn').style.display = '';
  }
}

function esc(s) {
  if (s == null) return '';
  const d = document.createElement('div'); d.textContent = String(s); return d.innerHTML;
}

// ============================================================
// Modal
// ============================================================
function openModal(kind, focusId) {
  const overlay = document.getElementById('modalOverlay');
  const title = document.getElementById('modalTitle');
  const body = document.getElementById('modalBody');

  const renderers = { vg: renderVGModal, decomp: renderDecompModal, formal: renderFormalModal, tests: renderTestsModal, props: renderPropsModal, policies: renderPoliciesModal, refmodels: renderRefModelsModal, residuals: renderResidualsModal };
  const titles = { vg: 'Verification Goals', decomp: 'Edge Cases (Region Decomposition)', formal: 'Formalizations', tests: 'Generated Tests', props: 'Process Properties', policies: 'Policies', refmodels: 'Reference Models', residuals: 'Residual Surface' };

  title.textContent = titles[kind] || kind;
  body.innerHTML = renderers[kind] ? renderers[kind]() : '';
  overlay.classList.add('open');

  if (focusId) {
    requestAnimationFrame(() => {
      const el = document.getElementById(focusId);
      if (el) {
        el.classList.add('expanded', 'highlight');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => el.classList.remove('highlight'), 1500);
      }
    });
  }
}

function closeModal() {
  document.getElementById('modalOverlay').classList.remove('open');
}

// ============================================================
// Phase classification
// ============================================================
const PHASES = [
  { key:'research', label:'Research', icon:'\u{1F50D}', color:'#60a5fa',
    types: new Set(['SearchCode','SearchWeb','ReadFile','AnalyzeCode','ExploreDirectory','ReadDocumentation']) },
  { key:'planning', label:'Planning', icon:'\u{1F5FA}', color:'#a78bfa',
    types: new Set(['FormulatePlan','DecomposeTask','EstimateImpact']) },
  { key:'reasoning', label:'Formal Reasoning', icon:'\u{1F9E0}', color:'#a78bfa',
    match: a => a.category === 'reasoning' },
  { key:'decision', label:'Decision', icon:'\u{2666}', color:'#fb923c',
    match: a => a.category === 'gateway' },
  { key:'implementation', label:'Implementation', icon:'\u{270F}\uFE0F', color:'#34d399',
    types: new Set(['EditFile','CreateFile','DeleteFile','RenameFile','RunCommand']) },
  { key:'verification', label:'Testing', icon:'\u{2705}', color:'#22d3ee',
    types: new Set(['RunTests','TypeCheck','Lint','ManualVerification']) },
  { key:'vcs', label:'Version Control', icon:'\u{1F4BE}', color:'#f472b6',
    types: new Set(['GitCommit','GitStatus','GitDiff']) },
  { key:'communication', label:'Communication', icon:'\u{1F4AC}', color:'#fbbf24',
    types: new Set(['AskUser','ReportProgress','Explain']) },
];

function classifyAction(a) {
  for (const p of PHASES) {
    if (p.match && p.match(a)) return p;
    if (p.types && p.types.has(a.type)) return p;
  }
  return { key:'other', label:'Other', icon:'\u{25AA}', color:'#94a3b8' };
}

function activityIcon(type) {
  return {
    SearchCode:'\u{1F50D}', SearchWeb:'\u{1F310}', ReadFile:'\u{1F4C4}',
    AnalyzeCode:'\u{1F9E0}', EditFile:'\u{270F}\uFE0F', CreateFile:'\u{1F4DD}',
    DeleteFile:'\u{1F5D1}', RunTests:'\u{2705}', RunCommand:'\u{25B6}',
    GitCommit:'\u{1F4BE}', GitStatus:'\u{1F4CB}', GitDiff:'\u{1F504}',
    AskUser:'\u{1F4AC}', Explain:'\u{1F4A1}', FormulatePlan:'\u{1F5FA}',
    DecomposeTask:'\u{1F9E9}', TypeCheck:'\u{1F3AF}', Lint:'\u{1F9F9}',
    ExploreDirectory:'\u{1F4C2}', ReadDocumentation:'\u{1F4DA}',
    EstimateImpact:'\u{26A0}\uFE0F', RenameFile:'\u{1F3F7}',
    ManualVerification:'\u{1F50E}', ReportProgress:'\u{1F4CA}', SubProcess:'\u{1F500}',
    Formalize:'\u{1F4D0}', Decompose:'\u{1F9E9}', DefineVG:'\u{1F3AF}',
    Verify:'\u{2696}\uFE0F', GenerateTests:'\u{1F9EA}'
  }[type] || '\u{25AA}';
}

// ============================================================
// Flow rendering
// ============================================================
function zoomToolbar(trace) {
  const nMeta = (trace.meta_actions || []).length, nAct = (trace.actions || []).length;
  if (!nMeta) return '';
  const z = window._flowZoom;
  return `<div class="zoom-toolbar"><span class="zoom-label">Zoom</span>
    <button class="zoom-btn ${z === 'meta' ? 'active' : ''}" onclick="setFlowZoom('meta')">Steps · ${nMeta}</button>
    <button class="zoom-btn ${z === 'actions' ? 'active' : ''}" onclick="setFlowZoom('actions')">Actions · ${nAct}</button>
  </div>`;
}

function setFlowZoom(z) { window._flowZoom = z; window._focusMeta = null; renderFlow(traceData); }
function focusMeta(id) { window._focusMeta = id; renderFlow(traceData); }

function renderFocusBar(m, n) {
  const statusClass = { completed: 'ok', partial: 'warn', abandoned: 'err' }[m.status] || '';
  const srcLabel = { plan_declared: 'plan', turn_segmented: 'directive', intent_inferred: 'inferred' }[m.source] || m.source || '';
  let h = `<div class="focus-bar">
    <button class="focus-back" onclick="focusMeta(null)">‹ Steps</button>
    <span class="meta-id">${esc(m.id)}</span>
    <span class="focus-title">${esc(m.title)}</span>
    ${m.status ? `<span class="meta-status ${statusClass}">${esc(m.status)}</span>` : ''}
    ${srcLabel ? `<span class="meta-source ${esc(m.source)}">${esc(srcLabel)}</span>` : ''}
    <span class="meta-count">${n} action${n !== 1 ? 's' : ''}</span>
  </div>`;
  if (m.intent) h += `<div class="focus-intent">${esc(m.intent)}</div>`;
  if (m.outcome) h += `<div class="focus-outcome">\u2192 ${esc(m.outcome)}</div>`;
  return h;
}

function renderFlow(trace) {
  const panel = document.getElementById('flowPanel');
  let actions = trace.actions || [];
  const vgs = trace.verification_goals || [];
  const hasMeta = (trace.meta_actions || []).length > 0;
  if (window._flowZoom === undefined) window._flowZoom = hasMeta ? 'meta' : 'actions';

  // Meta zoom with no focus \u2192 the list of steps.
  if (hasMeta && window._flowZoom === 'meta' && !window._focusMeta) {
    panel.innerHTML = zoomToolbar(trace) + renderMetaLevel(trace);
    return;
  }

  // Drilled into one step \u2192 show ONLY that step's actions.
  let focusM = null;
  if (hasMeta && window._flowZoom === 'meta' && window._focusMeta) {
    focusM = (trace.meta_actions || []).find(x => x.id === window._focusMeta);
    if (!focusM) { window._focusMeta = null; panel.innerHTML = zoomToolbar(trace) + renderMetaLevel(trace); return; }
    actions = actions.filter(a => a.meta_action_id === window._focusMeta);
  }

  const groups = [];
  let cur = null;
  for (const a of actions) {
    const phase = classifyAction(a);
    if (!cur || cur.key !== phase.key) { cur = { ...phase, actions: [a] }; groups.push(cur); }
    else cur.actions.push(a);
  }

  const vgByAction = {};
  for (const vg of vgs) for (const aid of (vg.related_actions || [])) (vgByAction[aid] = vgByAction[aid] || []).push(vg);

  let html = focusM ? renderFocusBar(focusM, actions.length)
    : `<div class="event-bookend">
    <div class="event-dot"></div>
    <div class="event-text">${esc(trace.trigger.description || trace.trigger.type)}</div>
  </div>`;

  let prevOutputs = [];
  for (let gi = 0; gi < groups.length; gi++) {
    const group = groups[gi];
    const firstInputs = group.actions[0].inputs || [];
    const shared = prevOutputs.filter(o => firstInputs.includes(o));
    if (shared.length) {
      html += `<div class="data-connector"><span class="arrow">\u2193</span>${shared.map(s => `<span class="data-tag">${esc(s)}</span>`).join('')}</div>`;
    } else if (gi > 0) {
      html += `<div class="data-connector"><span class="arrow">\u2193</span></div>`;
    }

    const labelText = esc(group.label);

    html += `<div class="phase-lane"><div class="phase-lane-header">
      <div class="phase-color" style="background:${group.color}"></div>
      <span class="phase-icon">${group.icon}</span>
      <span class="phase-label">${labelText}</span>
    </div><div class="lane-cards">`;

    // Group consecutive actions sharing a rationale into one step \u2014 the rationale
    // is the unit of intent, so "I did N things for this one reason" reads as one
    // card instead of N near-identical ones. Gateways/reasoning stay standalone.
    const steps = [];
    for (const a of group.actions) {
      const prev = steps[steps.length - 1];
      const special = a.category === 'gateway' || a.category === 'reasoning';
      if (prev && !special && !prev.special && (a.rationale || '').length > 0 &&
          (prev.rationale || '') === (a.rationale || '')) {
        prev.items.push(a);
      } else {
        steps.push({ rationale: a.rationale || '', special, items: [a] });
      }
    }

    for (let si = 0; si < steps.length; si++) {
      if (si > 0) html += `<div class="card-arrow">\u2192</div>`;
      const step = steps[si];
      html += step.items.length === 1
        ? actionCardHTML(step.items[0], vgByAction)
        : stepGroupHTML(step.items);
    }
    const lastAction = group.actions[group.actions.length - 1];
    if (lastAction) prevOutputs = lastAction.outputs || [];

    html += `</div></div>`;
  }

  if (!focusM) {
    html += `<div class="data-connector"><span class="arrow">\u2193</span></div>`;
    html += `<div class="event-bookend">
      <div class="event-dot end"></div>
      <div class="event-text">${esc(trace.outcome.summary || trace.outcome.type)}</div>
    </div>`;
  }

  panel.innerHTML = (focusM ? '' : zoomToolbar(trace)) + html;
}

// Meta-action level (§8.4): the declared structure — each step expandable to its actions.
function renderMetaLevel(trace) {
  const metas = trace.meta_actions || [];
  const byId = {};
  for (const a of (trace.actions || [])) byId[a.id] = a;
  let html = `<div class="event-bookend">
    <div class="event-dot"></div>
    <div class="event-text">${esc(trace.trigger.description || trace.trigger.type)}</div>
  </div>`;
  for (let i = 0; i < metas.length; i++) {
    if (i > 0) html += `<div class="data-connector"><span class="arrow">↓</span></div>`;
    html += renderMetaCard(metas[i], byId);
  }
  html += `<div class="data-connector"><span class="arrow">↓</span></div>`;
  html += `<div class="event-bookend">
    <div class="event-dot end"></div>
    <div class="event-text">${esc(trace.outcome.summary || trace.outcome.type)}</div>
  </div>`;
  return html;
}

function renderMetaCard(m, byId) {
  const acts = (m.action_ids || []).map(id => byId[id]).filter(Boolean);
  const srcLabel = { plan_declared: 'plan', turn_segmented: 'directive', intent_inferred: 'inferred' }[m.source] || m.source || '';
  const statusClass = { completed: 'ok', partial: 'warn', abandoned: 'err' }[m.status] || '';
  const nGaps = (m.residual_ids || []).length;
  // Click drills into this one step (shows only its actions); see focusMeta/renderFlow.
  let h = `<div class="meta-card" onclick="focusMeta('${esc(m.id)}')">`;
  h += `<div class="meta-head">
    <span class="meta-id">${esc(m.id)}</span>
    <span class="meta-title">${esc(m.title)}</span>
    ${m.status ? `<span class="meta-status ${statusClass}">${esc(m.status)}</span>` : ''}
    ${srcLabel ? `<span class="meta-source ${esc(m.source)}">${esc(srcLabel)}</span>` : ''}
    ${nGaps ? `<span class="meta-gaps" title="declared residuals">⚠ ${nGaps}</span>` : ''}
    <span class="meta-count">${acts.length} action${acts.length !== 1 ? 's' : ''}</span>
    <span class="meta-caret">›</span>
  </div>`;
  if (m.intent) h += `<div class="meta-intent">${esc(m.intent)}</div>`;
  if (m.outcome) h += `<div class="meta-outcome">\u2192 ${esc(m.outcome)}</div>`;
  h += `</div>`;
  return h;
}

// One action \u2192 one full card (used for singleton steps and gateways/reasoning).
function actionCardHTML(a, vgByAction) {
  const isGW = a.category === 'gateway';
  const isReasoning = a.category === 'reasoning';
  const cardClass = isGW ? ' gateway-card' : isReasoning ? ' reasoning-card' : '';
  let html = `<div class="action-card${cardClass}" data-action-id="${a.id}" onclick="selectAction(${a.id})">`;
  html += `<div class="card-top">
    <span class="card-icon">${isGW ? '\u{25C7}' : activityIcon(a.type)}</span>
    <span class="card-num">#${a.id}</span>
    <span class="card-label">${esc(a.label)}</span>
  </div>`;
  html += `<div class="card-rationale">${esc(a.rationale)}</div>`;

  if (isGW && a.options) {
    html += `<div class="gw-options">`;
    for (const o of a.options) {
      html += `<div class="gw-opt ${o.chosen ? 'chosen' : ''}"><div class="gw-bullet"></div> ${esc(o.label)}`;
      if (!o.chosen && o.rejected_because) html += ` <span class="gw-opt-reason">(${esc(o.rejected_because)})</span>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  if (a.formalization) {
    html += `<span class="card-status-badge ${a.formalization.status}">${a.formalization.status}</span>`;
    html += `<div class="card-reasoning-preview iml">${highlightIML(truncate(a.formalization.iml_code, 80))}</div>`;
  }
  if (a.vg_defined) {
    if (a.vg_defined.properties && a.vg_defined.properties.length) {
      html += renderPropTags(a.vg_defined.properties, 3);
    } else {
      html += `<div class="card-reasoning-preview vg-src">${highlightIML(truncate(a.vg_defined.src, 80))}</div>`;
    }
  }
  if (a.vg_result) {
    html += `<span class="card-status-badge ${a.vg_result.status}">${a.vg_result.status}</span>`;
    if (a.vg_result.result?.proved?.properties) {
      html += renderPropTags(a.vg_result.result.proved.properties, 3);
    } else if (a.vg_result.result?.sat) {
      const src = a.vg_result.result.sat.model.src;
      html += `<div class="card-reasoning-preview result-sat">${esc(truncate(src, 80))}</div>`;
    }
  }
  if (a.decomposition) {
    const nRegions = a.decomposition.regions?.length ?? 0;
    html += `<span class="card-status-badge transparent">${nRegions} region${nRegions !== 1 ? 's' : ''}${a.decomposition.complete ? ' — complete' : ''}</span>`;
  }
  if (a.generated_tests) {
    const nTests = a.generated_tests.tests?.length ?? a.generated_tests.count ?? 0;
    html += `<span class="card-status-badge transparent">${nTests} test${nTests !== 1 ? 's' : ''} generated</span>`;
  }

  if (a.result_summary) {
    html += `<div class="card-result-summary">${esc(a.result_summary)}</div>`;
  }

  const ins = a.inputs || [], outs = a.outputs || [];
  if (ins.length || outs.length) {
    html += `<div class="card-data">`;
    for (const i of ins) html += `<span class="cd-tag cd-in">← ${esc(i)}</span>`;
    for (const o of outs) html += `<span class="cd-tag cd-out">${esc(o)} \u2192</span>`;
    html += `</div>`;
  }

  const avgs = vgByAction[a.id] || [];
  if (avgs.length) {
    html += `<div class="card-vgs">`;
    for (const vg of avgs) {
      html += `<span class="card-vg-dot ${vg.status}" onclick="event.stopPropagation();openModal('vg','mvg-${vg.goal_id}')" title="${esc(vg.description)}">VG${vg.goal_id} ${vg.status}</span>`;
    }
    html += `</div>`;
  }

  html += `</div>`;
  return html;
}

// A run of same-rationale actions \u2192 one step card: rationale once, actions as rows.
function stepGroupHTML(items) {
  const first = items[0], last = items[items.length - 1];
  let html = `<div class="action-card step-group" data-action-id="${first.id}" onclick="selectAction(${first.id})">`;
  html += `<div class="card-top">
    <span class="card-icon">${activityIcon(first.type)}</span>
    <span class="card-num">#${first.id}–#${last.id}</span>
    <span class="card-label">${esc(first.label)}</span>
    <span class="step-count">${items.length}×</span>
  </div>`;
  html += `<div class="card-rationale">${esc(first.rationale)}</div>`;
  html += `<div class="step-sublist">`;
  for (const a of items) {
    const res = a.result_summary || '';
    const isErr = res.startsWith('ERROR');
    html += `<div class="step-subrow" onclick="event.stopPropagation();selectAction(${a.id})">
      <span class="sr-icon">${activityIcon(a.type)}</span>
      <span class="sr-id">#${a.id}</span>
      <span class="sr-label">${esc(a.label)}</span>
      ${res ? `<span class="sr-result${isErr ? ' err' : ''}">${esc(truncate(res, 70))}</span>` : ''}
    </div>`;
  }
  html += `</div></div>`;
  return html;
}

// ============================================================
// Helpers
// ============================================================
function truncate(s, n) { return s && s.length > n ? s.slice(0, n) + '...' : s || ''; }

function renderPropTags(props, max) {
  const show = props.slice(0, max);
  const overflow = props.length - max;
  let html = `<div style="margin-top:6px;display:flex;flex-wrap:wrap;gap:3px;">`;
  for (const p of show) {
    const st = p.status;
    const icon = st === 'proved' ? '\u2705' : st === 'pending' ? '\u23F3' : '\u274C';
    const stClass = st === 'pending' ? 'prop-tag-pending' : st === 'proved' ? 'prop-tag-proved' : 'prop-tag-refuted';
    html += `<span class="${stClass}" style="font-size:9px;padding:1px 5px;border-radius:3px;font-family:'SF Mono','Fira Code',monospace;">${icon} ${esc(p.name.replace(/^prop_/,'').replace(/_/g,' '))}</span>`;
  }
  if (overflow > 0) {
    html += `<span style="font-size:9px;padding:1px 5px;border-radius:3px;background:#1e293b;border:1px solid #334155;color:#94a3b8;">+${overflow} more</span>`;
  }
  html += `</div>`;
  return html;
}

function formatProof(pp, properties) {
  if (!pp && !properties) return '';

  // Structured properties list
  if (properties && properties.length) {
    let html = '';
    if (pp) html += `<div style="font-size:12px;color:#94a3b8;margin-bottom:8px;">${esc(pp)}</div>`;
    html += `<div class="proof-table">`;
    // Header
    html += `<div class="proof-hdr">
      <span class="proof-hdr-icon"></span>
      <span class="proof-hdr-name">Property</span>
      <span class="proof-hdr-status">Status</span>
    </div>`;
    for (const p of properties) {
      const st = p.status;
      const icon = st === 'proved' ? '\u2705' : st === 'pending' ? '\u23F3' : '\u274C';
      const stClass = st === 'proved' ? 'clr-green' : st === 'pending' ? 'clr-pending' : 'clr-red';
      html += `<div class="proof-row">
        <div class="proof-row-main">
          <span class="proof-row-icon">${icon}</span>
          <span class="proof-row-name ${stClass}">
            ${esc(p.name)}${p.note ? `<span class="proof-row-note">(${esc(p.note)})</span>` : ''}
          </span>
          <span class="proof-row-badge status-${st}">${esc(st)}</span>
        </div>
        ${p.src ? `<div class="proof-row-src">${highlightIMLSmart(p.src)}</div>` : ''}
      </div>`;
    }
    html += `</div>`;
    return html;
  }

  // Fallback: render as IML-highlighted code block
  return `<div class="dp-code-block proof">${highlightIML(pp)}</div>`;
}

// ============================================================
// IML syntax highlighter
// ============================================================
const IML_KEYWORDS = new Set([
  'let','in','if','then','else','match','with','fun','function',
  'type','and','rec','of','begin','end','module','struct','sig',
  'val','open','include','when','as','do','done','for','to',
  'downto','while','try','exception','external','mutable',
  'nonrec','private','virtual','class','method','inherit',
  'new','object','constraint','assert','lazy','effect'
]);
const IML_VERIFY_KW = new Set([
  'verify','instance','theorem','lemma','axiom'
]);
const IML_BOOLEANS = new Set(['true','false']);

function highlightIML(code) {
  if (!code) return '';
  // Tokenize with regex, process in order
  // Order matters: comments first, then strings, then others
  const tokens = [];
  const re = /(\(\*[\s\S]*?\*\))|("(?:[^"\\]|\\.)*")|(\{l\|[\s\S]*?\|l\})|(\[\@\@?\@?[^\]]*\])|([A-Z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)|(\b[a-z_][a-z0-9_']*\b)|(\b\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d[\d_]*)?\b)|(==>|<>|>=|<=|->|::|&&|\|\||[=+\-*/<>|:;,\.\(\)\[\]\{\}~!@#\^&])/g;

  let last = 0;
  let match;
  const parts = [];

  while ((match = re.exec(code)) !== null) {
    // Text before this match (whitespace, etc.)
    if (match.index > last) {
      parts.push(esc(code.slice(last, match.index)));
    }
    last = match.index + match[0].length;

    const text = match[0];

    if (match[1]) {
      // Comment (* ... *)
      parts.push(`<span class="iml-comment">${esc(text)}</span>`);
    } else if (match[2]) {
      // String "..."
      parts.push(`<span class="iml-str">${esc(text)}</span>`);
    } else if (match[3]) {
      // Quoted string {l|...|l}
      parts.push(`<span class="iml-str">${esc(text)}</span>`);
    } else if (match[4]) {
      // Attribute [@@...]
      parts.push(`<span class="iml-attr">${esc(text)}</span>`);
    } else if (match[5]) {
      // Capitalized identifier = type constructor or module
      const t = text;
      if (t.includes('.')) {
        // Module path: Module.func or Module.Type
        const dotIdx = t.lastIndexOf('.');
        const modPart = t.slice(0, dotIdx + 1);
        const rest = t.slice(dotIdx + 1);
        const restClass = rest[0] === rest[0].toUpperCase() ? 'iml-type' : 'iml-fn';
        parts.push(`<span class="iml-module">${esc(modPart)}</span><span class="${restClass}">${esc(rest)}</span>`);
      } else {
        parts.push(`<span class="iml-type">${esc(t)}</span>`);
      }
    } else if (match[6]) {
      // Lowercase identifier
      const word = text;
      if (IML_VERIFY_KW.has(word)) {
        parts.push(`<span class="iml-kw-verify">${esc(word)}</span>`);
      } else if (IML_KEYWORDS.has(word)) {
        parts.push(`<span class="iml-kw">${esc(word)}</span>`);
      } else if (IML_BOOLEANS.has(word)) {
        parts.push(`<span class="iml-bool">${esc(word)}</span>`);
      } else {
        parts.push(`<span class="iml-param">${esc(word)}</span>`);
      }
    } else if (match[7]) {
      // Number
      parts.push(`<span class="iml-num">${esc(text)}</span>`);
    } else if (match[8]) {
      // Operator / punctuation
      parts.push(`<span class="iml-op">${esc(text)}</span>`);
    }
  }

  // Remaining text
  if (last < code.length) {
    parts.push(esc(code.slice(last)));
  }

  return parts.join('');
}

// Context-aware: detect let-bound function names and highlight them
function highlightIMLSmart(code) {
  // First pass: collect function names from let bindings
  const fnNames = new Set();
  const letRe = /\blet\s+(?:rec\s+)?([a-z_][a-z0-9_']*)/g;
  let m;
  while ((m = letRe.exec(code)) !== null) fnNames.add(m[1]);

  // Run base highlighter
  let html = highlightIML(code);

  // Second pass: promote known function names from iml-param to iml-fn
  for (const fn of fnNames) {
    // Only replace exact matches in iml-param spans
    const paramSpan = `<span class="iml-param">${esc(fn)}</span>`;
    const fnSpan = `<span class="iml-fn">${esc(fn)}</span>`;
    html = html.split(paramSpan).join(fnSpan);
  }

  return html;
}

// ============================================================
// Python syntax highlighter
// ============================================================
const PY_KEYWORDS = new Set([
  'def','class','if','elif','else','for','while','return','yield',
  'import','from','as','with','try','except','finally','raise',
  'pass','break','continue','lambda','del','global','nonlocal',
  'async','await','in','not','and','or','is','assert'
]);
const PY_BUILTINS = new Set([
  'print','len','range','int','str','float','bool','list','dict',
  'set','tuple','type','isinstance','hasattr','getattr','setattr',
  'enumerate','zip','map','filter','sorted','reversed','any','all',
  'min','max','sum','abs','round','open','super','property',
  'staticmethod','classmethod','ValueError','TypeError','KeyError',
  'RuntimeError','Exception','None'
]);
const PY_BOOLEANS = new Set(['True','False','None']);

function highlightPython(code) {
  if (!code) return '';
  const re = /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?''')|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(@\w+)|\b([A-Z]\w*)\b|\b([a-z_]\w*)\b|\b(\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b|(==|!=|<=|>=|->|:|\*\*|[=+\-*/<>|&^~%!,\.\(\)\[\]\{\}])/g;
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(code)) !== null) {
    if (m.index > last) parts.push(esc(code.slice(last, m.index)));
    last = m.index + m[0].length;
    const t = m[0];
    if (m[1]) parts.push(`<span class="py-comment">${esc(t)}</span>`);
    else if (m[2]) parts.push(`<span class="py-str">${esc(t)}</span>`);
    else if (m[3]) parts.push(`<span class="py-str">${esc(t)}</span>`);
    else if (m[4]) parts.push(`<span class="py-dec">${esc(t)}</span>`);
    else if (m[5]) {
      if (PY_BOOLEANS.has(t)) parts.push(`<span class="py-bool">${esc(t)}</span>`);
      else parts.push(`<span class="py-cls">${esc(t)}</span>`);
    }
    else if (m[6]) {
      if (t === 'self') parts.push(`<span class="py-self">${esc(t)}</span>`);
      else if (PY_KEYWORDS.has(t)) parts.push(`<span class="py-kw">${esc(t)}</span>`);
      else if (PY_BUILTINS.has(t)) parts.push(`<span class="py-builtin">${esc(t)}</span>`);
      else parts.push(`<span class="py-param">${esc(t)}</span>`);
    }
    else if (m[7]) parts.push(`<span class="py-num">${esc(t)}</span>`);
    else if (m[8]) parts.push(`<span class="py-op">${esc(t)}</span>`);
  }
  if (last < code.length) parts.push(esc(code.slice(last)));
  // Promote def-bound names to function highlights
  let html = parts.join('');
  const fnRe = /\bdef\b\s+<span class="py-param">(\w+)<\/span>/g;
  html = html.replace(fnRe, (_, name) =>
    `<span class="py-kw">def</span> <span class="py-fn">${name}</span>`
  );
  return html;
}

// ============================================================
// TypeScript syntax highlighter
// ============================================================
const TS_KEYWORDS = new Set([
  'function','const','let','var','if','else','for','while','return',
  'import','from','export','default','class','extends','implements',
  'new','this','super','try','catch','finally','throw','typeof',
  'instanceof','in','of','switch','case','break','continue',
  'async','await','yield','void','delete','do','enum','interface',
  'type','as','readonly','abstract','declare','namespace','module',
  'keyof','infer','never','unknown','any','is'
]);
const TS_BUILTINS = new Set([
  'console','Math','JSON','Array','Object','String','Number',
  'Boolean','Promise','Map','Set','Date','Error','RegExp',
  'undefined','null','NaN','Infinity','parseInt','parseFloat',
  'true','false','describe','it','expect','test','beforeEach',
  'afterEach'
]);
const TS_BOOLEANS = new Set(['true','false','null','undefined']);

function highlightTypeScript(code) {
  if (!code) return '';
  const re = /(\/\/[^\n]*|\/\*[\s\S]*?\*\/)|(`(?:[^`\\]|\\.|\$\{[^}]*\})*`)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(@\w+)|\b([A-Z]\w*)\b|\b([a-z_$]\w*)\b|\b(\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)\b|(===|!==|==|!=|<=|>=|=>|&&|\|\||[=+\-*/<>|&^~%!?:,\.\(\)\[\]\{\};])/g;
  const parts = [];
  let last = 0, m;
  while ((m = re.exec(code)) !== null) {
    if (m.index > last) parts.push(esc(code.slice(last, m.index)));
    last = m.index + m[0].length;
    const t = m[0];
    if (m[1]) parts.push(`<span class="ts-comment">${esc(t)}</span>`);
    else if (m[2]) parts.push(`<span class="ts-str">${esc(t)}</span>`);
    else if (m[3]) parts.push(`<span class="ts-str">${esc(t)}</span>`);
    else if (m[4]) parts.push(`<span class="ts-kw">${esc(t)}</span>`);
    else if (m[5]) {
      if (TS_BOOLEANS.has(t)) parts.push(`<span class="ts-bool">${esc(t)}</span>`);
      else parts.push(`<span class="ts-type">${esc(t)}</span>`);
    }
    else if (m[6]) {
      if (t === 'this') parts.push(`<span class="ts-kw" style="font-style:italic;">${esc(t)}</span>`);
      else if (TS_KEYWORDS.has(t)) parts.push(`<span class="ts-kw">${esc(t)}</span>`);
      else if (TS_BUILTINS.has(t)) parts.push(`<span class="ts-fn">${esc(t)}</span>`);
      else parts.push(`<span class="ts-param">${esc(t)}</span>`);
    }
    else if (m[7]) parts.push(`<span class="ts-num">${esc(t)}</span>`);
    else if (m[8]) parts.push(`<span class="ts-op">${esc(t)}</span>`);
  }
  if (last < code.length) parts.push(esc(code.slice(last)));
  let html = parts.join('');
  const fnRe = /\b(function)\b\s+<span class="ts-param">(\w+)<\/span>/g;
  html = html.replace(fnRe, (_, kw, name) =>
    `<span class="ts-kw">${kw}</span> <span class="ts-fn">${name}</span>`
  );
  return html;
}

// ============================================================
// Language-aware code highlighter dispatch
// ============================================================
function highlightCode(code, language) {
  if (!code) return '';
  const lang = (language || '').toLowerCase();
  if (lang === 'python' || lang === 'py') return highlightPython(code);
  if (lang === 'typescript' || lang === 'ts') return highlightTypeScript(code);
  if (lang === 'iml') return highlightIMLSmart(code);
  return esc(code); // fallback
}

// ============================================================
// Voronoi decomposition rendering
// ============================================================
const VORONOI_PALETTE = [
  [99,102,241],[52,211,153],[251,191,36],[244,114,182],
  [34,211,238],[167,139,250],[96,165,250],[248,113,113],
  [74,222,128],[253,186,116]
];

function placeSeedsRelaxed(n, w, h, pad) {
  // Start with distributed points, then relax via Lloyd's
  const seeds = [];
  const cols = Math.ceil(Math.sqrt(n * w / h));
  const rows = Math.ceil(n / cols);
  let idx = 0;
  for (let r = 0; r < rows && idx < n; r++) {
    for (let c = 0; c < cols && idx < n; c++) {
      seeds.push({
        x: pad + (c + 0.5) * (w - 2*pad) / cols + (Math.random()-0.5) * 20,
        y: pad + (r + 0.5) * (h - 2*pad) / rows + (Math.random()-0.5) * 20
      });
      idx++;
    }
  }
  // 3 iterations of Lloyd relaxation
  for (let iter = 0; iter < 3; iter++) {
    const sums = seeds.map(() => ({ x:0, y:0, count:0 }));
    const step = 4;
    for (let y = 0; y < h; y += step) {
      for (let x = 0; x < w; x += step) {
        let minD = Infinity, minI = 0;
        for (let i = 0; i < seeds.length; i++) {
          const dx = x - seeds[i].x, dy = y - seeds[i].y;
          const d = dx*dx + dy*dy;
          if (d < minD) { minD = d; minI = i; }
        }
        sums[minI].x += x; sums[minI].y += y; sums[minI].count++;
      }
    }
    for (let i = 0; i < seeds.length; i++) {
      if (sums[i].count > 0) {
        seeds[i].x = Math.max(pad, Math.min(w-pad, sums[i].x / sums[i].count));
        seeds[i].y = Math.max(pad, Math.min(h-pad, sums[i].y / sums[i].count));
      }
    }
  }
  return seeds;
}

function renderVoronoi(container, decomposition, width, height) {
  const regions = decomposition.regions || [];
  const n = regions.length;
  if (!n) return;

  const dpr = window.devicePixelRatio || 1;
  const light = isLightTheme();
  const cw = width, ch = height;

  // Outer wrapper holds diagram + detail
  const outer = document.createElement('div');

  const wrap = document.createElement('div');
  wrap.className = 'voronoi-wrap';
  wrap.style.width = '100%';
  wrap.style.maxWidth = cw + 'px';
  wrap.style.cursor = 'pointer';

  const canvas = document.createElement('canvas');
  canvas.width = cw * dpr;
  canvas.height = ch * dpr;
  canvas.style.width = cw + 'px';
  canvas.style.height = ch + 'px';
  wrap.appendChild(canvas);

  const labelsDiv = document.createElement('div');
  labelsDiv.className = 'voronoi-labels';
  wrap.appendChild(labelsDiv);

  // Detail panel below diagram
  const detailDiv = document.createElement('div');
  detailDiv.className = 'voronoi-detail';
  detailDiv.style.cssText = 'margin-top:8px;min-height:0;transition:all 0.15s;';

  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);

  const seeds = placeSeedsRelaxed(n, cw, ch, 30);
  const colors = regions.map((_, i) => VORONOI_PALETTE[i % VORONOI_PALETTE.length]);

  // Build cell ownership
  const ownership = new Int8Array(cw * ch);
  for (let py = 0; py < ch; py++) {
    for (let px = 0; px < cw; px++) {
      let minD = Infinity, minI = 0;
      for (let i = 0; i < n; i++) {
        const dx = px - seeds[i].x, dy = py - seeds[i].y;
        const d = dx*dx + dy*dy;
        if (d < minD) { minD = d; minI = i; }
      }
      ownership[py * cw + px] = minI;
    }
  }

  // Store base image for highlight redraws
  let selectedRegion = -1;

  function drawCells(highlight) {
    const imgData = ctx.createImageData(cw * dpr, ch * dpr);
    const data = imgData.data;

    for (let py = 0; py < ch * dpr; py++) {
      for (let px = 0; px < cw * dpr; px++) {
        const sx = Math.floor(px / dpr), sy = Math.floor(py / dpr);
        const cell = ownership[sy * cw + sx];
        const col = colors[cell];

        let isBorder = false;
        for (const [bx,by] of [[-1,0],[1,0],[0,-1],[0,1]]) {
          const nx = sx+bx, ny = sy+by;
          if (nx >= 0 && nx < cw && ny >= 0 && ny < ch) {
            if (ownership[ny * cw + nx] !== cell) { isBorder = true; break; }
          }
        }

        const dx = sx - seeds[cell].x, dy = sy - seeds[cell].y;
        const dist = Math.sqrt(dx*dx + dy*dy);
        const maxDist = Math.max(cw, ch) * 0.4;
        let shade = light
          ? 0.55 + 0.35 * (1 - Math.min(dist / maxDist, 1))
          : 0.35 + 0.25 * (1 - Math.min(dist / maxDist, 1));

        // Dim non-selected cells when one is selected
        if (highlight >= 0 && cell !== highlight) shade *= 0.4;
        // Brighten selected
        if (highlight >= 0 && cell === highlight) shade = Math.min(shade * 1.4, light ? 0.95 : 0.85);

        const idx = (py * cw * dpr + px) * 4;
        if (isBorder) {
          const bAlpha = (highlight >= 0 && (cell === highlight ||
            (() => { for (const [bx2,by2] of [[-1,0],[1,0],[0,-1],[0,1]]) { const nx2=sx+bx2,ny2=sy+by2; if(nx2>=0&&nx2<cw&&ny2>=0&&ny2<ch&&ownership[ny2*cw+nx2]===highlight) return true; } return false; })()
          )) ? 1 : 0.6;
          const bc = highlight >= 0 && cell === highlight
            ? (light ? [80,80,160] : [200,200,255])
            : (light ? [180,185,200] : [51,65,85]);
          data[idx] = bc[0]; data[idx+1] = bc[1]; data[idx+2] = bc[2]; data[idx+3] = Math.round(255*bAlpha);
        } else {
          data[idx]   = Math.round(col[0] * shade);
          data[idx+1] = Math.round(col[1] * shade);
          data[idx+2] = Math.round(col[2] * shade);
          data[idx+3] = 255;
        }
      }
    }
    ctx.putImageData(imgData, 0, 0);
  }

  drawCells(-1);

  // Labels at seed positions
  const labelEls = [];
  regions.forEach((r, i) => {
    const inv = r.invariant || r.invariant_str || '';

    const label = document.createElement('div');
    label.className = 'voronoi-label';
    label.style.left = seeds[i].x + 'px';
    label.style.top = seeds[i].y + 'px';
    label.style.transform = 'translate(-50%, -50%)';
    label.style.maxWidth = (cw / Math.ceil(Math.sqrt(n)) - 20) + 'px';

    label.innerHTML = `<div class="vl-idx">R${i+1}</div>`;
    labelsDiv.appendChild(label);
    labelEls.push(label);
  });

  // Click handling — detect cell from click position
  wrap.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const mx = Math.floor((e.clientX - rect.left) * (cw / rect.width));
    const my = Math.floor((e.clientY - rect.top) * (ch / rect.height));
    if (mx < 0 || mx >= cw || my < 0 || my >= ch) return;

    const clicked = ownership[my * cw + mx];
    if (clicked === selectedRegion) {
      // Deselect
      selectedRegion = -1;
      drawCells(-1);
      labelEls.forEach(l => l.style.opacity = '1');
      detailDiv.innerHTML = '';
    } else {
      selectedRegion = clicked;
      drawCells(clicked);
      labelEls.forEach((l, i) => l.style.opacity = i === clicked ? '1' : '0.3');
      showRegionDetail(clicked);
    }
  });

  function showRegionDetail(idx) {
    const r = regions[idx];
    const cons = r.constraints || r.constraints_str || [];
    const inv = r.invariant || r.invariant_str || '';
    const model = r.model || r.model_str || {};
    const meval = r.model_eval || r.model_eval_str || '';
    const wit = typeof model === 'object'
      ? Object.entries(model).map(([k,v]) => `<span class="clr-yellow">${esc(k)}</span> = <span class="clr-yellow">${esc(v)}</span>`)
      : [esc(String(model))];

    const col = colors[idx];
    const borderColor = `rgb(${col[0]},${col[1]},${col[2]})`;

    detailDiv.innerHTML = `
      <div style="background:${light ? '#f4f6f9' : '#0f172a'};border:1px solid ${borderColor};border-radius:8px;padding:12px 16px;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <div style="width:12px;height:12px;border-radius:3px;background:${borderColor};flex-shrink:0;"></div>
          <span style="font-weight:700;font-size:13px;color:${borderColor};">Region ${idx+1}</span>
          <span style="font-family:'SF Mono','Fira Code',monospace;font-size:13px;margin-left:8px;" class="clr-green">\u21D2 ${esc(inv)}</span>
        </div>
        <div style="margin-bottom:8px;">
          <div style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Constraints</div>
          <div style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;color:var(--text-primary);line-height:1.6;">
            ${cons.map(c => esc(c)).join('<br>')}
          </div>
        </div>
        <div style="margin-bottom:8px;">
          <div style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Witness</div>
          <div style="font-family:'SF Mono','Fira Code',monospace;font-size:12px;line-height:1.6;">
            ${wit.join('<br>')}
          </div>
        </div>
        <div>
          <div style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Evaluates to</div>
          <div style="font-family:'SF Mono','Fira Code',monospace;font-size:13px;color:var(--cyan);">${esc(String(meval))}</div>
        </div>
      </div>
    `;
  }

  outer.appendChild(wrap);
  outer.appendChild(detailDiv);
  container.appendChild(outer);
}

function renderVoronoiHierarchy(container, decompositions, width, perHeight) {
  // If multiple decompositions, show side by side with arrow showing evolution
  if (decompositions.length === 1) {
    renderVoronoi(container, decompositions[0], width, perHeight);
    return;
  }

  const hierarchy = document.createElement('div');
  hierarchy.className = 'voronoi-hierarchy';

  decompositions.forEach((dec, i) => {
    if (i > 0) {
      const arrow = document.createElement('div');
      arrow.className = 'vh-arrow';
      arrow.textContent = '\u2192';
      hierarchy.appendChild(arrow);
    }
    const item = document.createElement('div');
    item.className = 'vh-item';
    const title = document.createElement('div');
    title.className = 'vh-title';
    title.innerHTML = `<span>${esc(dec.target_function)}</span>`;
    if (dec.complete) title.innerHTML += `<span class="dp-status transparent" style="font-size:9px;">complete</span>`;
    item.appendChild(title);
    const itemWidth = Math.max(200, Math.floor((width - 60) / decompositions.length));
    renderVoronoi(item, dec, itemWidth, perHeight);
    hierarchy.appendChild(item);
  });

  container.appendChild(hierarchy);
}

// ============================================================
// Action selection -> detail panel
// ============================================================
let _selectedActionId = null;

function selectAction(actionId) {
  _selectedActionId = actionId;
  document.querySelectorAll('.action-card.selected').forEach(c => c.classList.remove('selected'));
  const card = document.querySelector(`.action-card[data-action-id="${actionId}"]`);
  if (card) card.classList.add('selected');

  const d = traceData.actions.find(a => a.id === actionId);
  if (!d) return;
  const dp = document.getElementById('detailPanel');
  let html = '';

  // Header + rationale (always)
  const icon = d.category === 'gateway' ? '\u{25C7}' : activityIcon(d.type);
  if (d.category === 'gateway') {
    html += `<div class="detail-section"><h3>Decision</h3><p>${esc(d.label)}</p></div>`;
    html += `<div class="detail-section"><p class="label">Rationale</p><p>${esc(d.rationale || d.detail)}</p></div>`;
    if (d.options) {
      html += `<div class="detail-section"><p class="label">Options</p>`;
      for (const o of d.options) html += `<div class="option-row ${o.chosen ? 'chosen' : ''}">${esc(o.label)}</div>`;
      html += `</div>`;
    }
  } else {
    html += `<div class="detail-section"><h3>${esc(d.type)}</h3><p>${esc(d.label)}</p></div>`;
    html += `<div class="detail-section"><p class="label">Rationale</p><p>${esc(d.rationale)}</p></div>`;
    if (d.detail) html += `<div class="detail-section"><p class="label">Detail</p><p>${esc(d.detail)}</p></div>`;
  }

  // ---- Formalization detail ----
  if (d.formalization) {
    const f = d.formalization;
    html += `<div class="detail-section">
      <p class="label">Formalization</p>
      <span class="dp-status ${f.status}">${f.status}</span>`;
    html += `<p class="label" style="margin-top:8px;">Source (${esc(f.src_lang)})</p>
      <div class="dp-code-block src">${highlightCode(f.src_code, f.src_lang)}</div>`;
    html += `<div class="dp-arrow-label">\u2193 formalized to IML</div>`;
    html += `<div class="dp-code-block iml">${highlightIMLSmart(f.iml_code)}</div>`;
    // Symbols omitted — the IML source is the authoritative listing
    html += `</div>`;
  }

  // ---- VG definition detail ----
  if (d.vg_defined) {
    const vg = d.vg_defined;
    html += `<div class="detail-section">
      <p class="label">Property Defined <span style="color:#94a3b8;text-transform:lowercase;font-weight:400;">(${esc(vg.kind)})</span></p>
      <p style="font-size:13px;color:var(--text-primary);margin-bottom:6px;">${esc(vg.description)}</p>`;
    if (vg.properties && vg.properties.length) {
      html += formatProof(null, vg.properties);
    } else {
      html += `<div class="dp-code-block vg-src">${highlightIMLSmart(vg.src)}</div>`;
    }
    html += `</div>`;
  }

  // ---- VG result detail ----
  if (d.vg_result) {
    const vr = d.vg_result;
    html += `<div class="detail-section">
      <p class="label">Verification Result</p>
      <span class="dp-status ${vr.status}">${vr.status}</span>`;
    if (vr.result?.proved) {
      html += formatProof(vr.result.proved.proof_pp, vr.result.proved.properties);
    }
    if (vr.result?.sat) {
      html += `<p style="font-size:10px;color:#64748b;text-transform:uppercase;margin-top:6px;">Instance found</p>`;
      html += `<div class="dp-code-block instance">${esc(vr.result.sat.model.src)}</div>`;
    }
    if (vr.result?.refuted) {
      html += `<p style="font-size:10px;color:#64748b;text-transform:uppercase;margin-top:6px;">Counterexample</p>`;
      const refText = typeof vr.result.refuted === 'string' ? vr.result.refuted : vr.result.refuted.counterexample || JSON.stringify(vr.result.refuted, null, 2);
      html += `<div class="dp-code-block instance clr-red">${highlightIML(refText)}</div>`;
    }
    html += `</div>`;
  }

  // ---- Decomposition detail ----
  if (d.decomposition) {
    const dec = d.decomposition;
    html += `<div class="detail-section">
      <p class="label">Edge Cases (Region Decomposition): <span class="clr-purple" style="font-family:'SF Mono','Fira Code',monospace;text-transform:none;">${esc(dec.target_function)}</span></p>
      <span class="dp-status transparent">${dec.regions.length} region${dec.regions.length !== 1 ? 's' : ''}${dec.complete ? ' \u2014 complete' : ''}</span>
      <div id="dp-voronoi-${d.id}"></div>
    </div>`;
    // Deferred Voronoi rendering after DOM update
    requestAnimationFrame(() => {
      const vc = document.getElementById('dp-voronoi-' + d.id);
      if (vc) {
        const pw = vc.closest('.detail-panel')?.clientWidth - 40 || 380;
        renderVoronoi(vc, dec, pw, 220);
      }
    });
  }

  // ---- Generated tests detail ----
  if (d.generated_tests) {
    const gt = d.generated_tests;
    const gtLabel = gt.function ? esc(gt.function) + (gt.language ? ` (${esc(gt.language)})` : '') : esc(gt.summary || `${gt.count ?? 0} tests`);
    html += `<div class="detail-section">
      <p class="label">Generated Tests: <span class="clr-purple" style="font-family:'SF Mono','Fira Code',monospace;text-transform:none;">${gtLabel}</span></p>`;
    for (const t of (gt.tests || [])) {
      html += `<div class="dp-test-item" onclick="this.querySelector('.dp-code-block')?.classList.toggle('collapsed')">
        <div class="dp-test-name">${esc(t.name)}</div>
        <div class="dp-test-meta">R${t.region_index + 1}: ${(t.constraints || []).join(' AND ')} \u2192 expected: ${esc(String(t.expected))}</div>
        <div class="dp-code-block test-code">${highlightCode(t.code, gt.language)}</div>
      </div>`;
    }
    html += `</div>`;
  }

  // ---- Data flow ----
  if (d.inputs?.length) html += `<div class="detail-section"><p class="label">Inputs</p>${d.inputs.map(i => `<span class="dtag">${esc(i)}</span>`).join(' ')}</div>`;
  if (d.outputs?.length) html += `<div class="detail-section"><p class="label">Outputs</p>${d.outputs.map(o => `<span class="dtag">${esc(o)}</span>`).join(' ')}</div>`;

  // ---- Execution metadata (v1.1) ----
  if (d.execution) {
    const ex = d.execution;
    html += `<div class="detail-section"><p class="label">Execution</p><div class="dp-exec-meta">`;
    if (ex.tool) html += `<span>${esc(ex.tool)}</span>`;
    if (ex.version) html += `<span>v${esc(ex.version)}</span>`;
    if (ex.duration_ms != null) html += `<span>${ex.duration_ms}ms</span>`;
    if (ex.determinism) html += `<span>${esc(ex.determinism)}</span>`;
    if (ex.cost != null) html += `<span>cost: ${ex.cost}</span>`;
    html += `</div></div>`;
  }

  // ---- Evidence ----
  if (d.evidence?.length) {
    html += `<div class="detail-section"><p class="label">Evidence</p>`;
    for (const e of d.evidence) html += `<div class="evidence-item">${esc(e.type)}: ${esc(e.ref)}</div>`;
    html += `</div>`;
  }

  // ---- Observations (v1.1) ----
  if (d.observations?.length) {
    html += `<div class="detail-section"><p class="label">Observations</p>`;
    for (const obs of d.observations) {
      html += `<div class="dp-observation"><p>${esc(obs.statement)}</p>`;
      if (obs.confidence) html += `<span class="dp-obs-confidence">${esc(obs.confidence)}</span>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  dp.innerHTML = `<h2>${icon} Action #${d.id}</h2>` + html;
}

// ============================================================
// Lineage tracing
// ============================================================

function buildOutputIndex() {
  // Map: output name/ID \u2192 action that produces it
  // Use original artifact IDs for v1.1, display names for v1.0
  const idx = {};
  for (const a of (traceData?.actions || [])) {
    const outs = a._original_outputs || a.outputs || [];
    for (const o of outs) {
      idx[o] = a;
    }
    // Also index by display name for v1.0 compatibility
    if (a._original_outputs) {
      for (const o of (a.outputs || [])) {
        if (!idx[o]) idx[o] = a;
      }
    }
  }
  return idx;
}

function traceLineage(actionId) {
  const outputIdx = buildOutputIndex();
  const actions = traceData?.actions || [];
  const target = actions.find(a => a.id === actionId);
  if (!target) return [];

  // BFS backwards through data dependencies
  const visited = new Set();
  const chain = [];
  const queue = [target];

  while (queue.length) {
    const current = queue.shift();
    if (visited.has(current.id)) continue;
    visited.add(current.id);
    chain.push(current);

    // Use original artifact IDs for v1.1
    const inputs = current._original_inputs || current.inputs || [];
    for (const inp of inputs) {
      const producer = outputIdx[inp];
      if (producer && !visited.has(producer.id)) {
        queue.push(producer);
      }
    }
  }

  // Reverse so earliest dependency comes first
  return chain.reverse();
}

// ============================================================
// Top-level view switcher
// ============================================================
function switchView(view) {
  // Match button by data-view or text content
  document.querySelectorAll('.view-switcher button').forEach(b => {
    const bView = b.getAttribute('onclick')?.match(/switchView\('(\w+)'\)/)?.[1];
    b.classList.toggle('active', bView === view);
  });
  document.querySelectorAll('.top-view').forEach(v => v.classList.remove('active'));
  document.getElementById('view-' + view).classList.add('active');
  if (view === 'grade') renderGradeView();
  if (view === 'goals') renderGoalsView();
  if (view === 'lineage') renderLineageView();
  if (view === 'dag') renderDAGView();
  if (view === 'funnel') renderFunnelView();
  if (view === 'policy') renderPolicyView();
}

// ============================================================
// Lineage view — lists all artifacts with dependency chains
// ============================================================
function collectArtifacts() {
  const actions = traceData?.actions || [];
  const groups = {
    formalizations: { label: 'Formalizations', icon: '\u{1F4D0}', items: [] },
    verifications: { label: 'Verification Results', icon: '\u{2696}\uFE0F', items: [] },
    decompositions: { label: 'Edge Cases (Region Decomposition)', icon: '\u{1F9E9}', items: [] },
    tests: { label: 'Generated Tests', icon: '\u{1F9EA}', items: [] },
    changes: { label: 'Code Changes', icon: '\u{270F}\uFE0F', items: [] },
    commits: { label: 'Commits', icon: '\u{1F4BE}', items: [] },
  };

  for (const a of actions) {
    if (a.formalization) {
      groups.formalizations.items.push({
        action: a,
        label: a.label,
        badge: a.formalization.status,
        meta: (a.formalization.symbols || []).join(', ')
      });
    }
    if (a.vg_result) {
      groups.verifications.items.push({
        action: a,
        label: a.label,
        badge: a.vg_result.status,
        meta: a.vg_result.result?.proved?.properties ? a.vg_result.result.proved.properties.length + ' properties' : ''
      });
    }
    if (a.decomposition) {
      groups.decompositions.items.push({
        action: a,
        label: 'Decomposed function: ' + a.decomposition.target_function,
        badge: a.decomposition.complete ? 'complete' : 'partial',
        meta: (a.decomposition.regions?.length ?? 0) + ' regions'
      });
    }
    if (a.generated_tests) {
      const gt = a.generated_tests;
      groups.tests.items.push({
        action: a,
        label: gt.function ? 'Function under test: ' + gt.function : (gt.summary || 'Generated tests'),
        badge: gt.language,
        meta: (gt.tests?.length ?? gt.count ?? 0) + ' tests'
      });
    }
    if (a.type === 'EditFile' || a.type === 'CreateFile' || a.type === 'DeleteFile') {
      groups.changes.items.push({ action: a, label: a.label, meta: a.detail || '' });
    }
    if (a.type === 'GitCommit') {
      groups.commits.items.push({ action: a, label: a.label, meta: '' });
    }
  }

  return Object.values(groups).filter(g => g.items.length > 0);
}

function renderLineageChain(chain, targetId) {
  let html = `<div class="lineage-chain-title">${chain.length} step${chain.length !== 1 ? 's' : ''} in dependency chain</div>`;
  html += `<div class="lineage-chain">`;
  for (let i = 0; i < chain.length; i++) {
    const a = chain[i];
    const isTarget = a.id === targetId;
    const icon = a.category === 'gateway' ? '\u{25C7}' : activityIcon(a.type);

    const sharedData = (a.outputs || []).filter(o => {
      for (let j = i + 1; j < chain.length; j++) {
        if ((chain[j].inputs || []).includes(o)) return true;
      }
      return false;
    });

    html += `<div class="lineage-step ${isTarget ? 'current' : ''}" onclick="switchView('flow');selectAction(${a.id})">
      <span class="ls-icon">${icon}</span>
      <span class="ls-id">#${a.id}</span>
      <div class="ls-body">
        <div class="ls-label">${esc(a.label)}</div>
        <div class="ls-type">${esc(a.category)} / ${esc(a.type)}</div>
        ${sharedData.length ? `<div class="ls-data">${sharedData.map(d => `<span class="ls-data-tag">${esc(d)}</span>`).join('')}</div>` : ''}
      </div>
    </div>`;

    if (i < chain.length - 1 && sharedData.length) {
      html += `<div class="lineage-arrow">\u2193 ${sharedData.map(d => `<span style="font-family:'SF Mono','Fira Code',monospace;font-size:10px;color:var(--accent);">${esc(d)}</span>`).join(', ')}</div>`;
    } else if (i < chain.length - 1) {
      html += `<div class="lineage-arrow">\u2193</div>`;
    }
  }
  html += `</div>`;
  return html;
}

function renderLineageView() {
  const el = document.getElementById('view-lineage');
  const groups = collectArtifacts();

  if (!groups.length) {
    el.innerHTML = `<div style="padding:48px 32px;max-width:640px;margin:0 auto;text-align:center;color:var(--text-dim);">
      <div style="font-size:32px;margin-bottom:12px;opacity:.5;">◇</div>
      <div style="font-size:15px;color:var(--text);margin-bottom:8px;">No lineage in this trace yet</div>
      <p style="font-size:13px;line-height:1.6;margin:0 0 16px;">
        Lineage shows how each result traces back to what produced it. This trace records
        <em>what the agent did</em>, but the actions don't declare the artifacts they consumed or
        produced, so there's no dependency chain to follow.
      </p>
      <p style="font-size:12px;line-height:1.6;margin:0;opacity:.8;">
        Have the agent emit artifacts and wire <code>inputs</code>/<code>outputs</code> between actions
        to make the data flow visible here.
      </p>
    </div>`;
    return;
  }

  let html = '';
  for (const group of groups) {
    html += `<div class="artifact-group">`;
    html += `<div class="artifact-group-header">
      <span class="ag-icon">${group.icon}</span>
      ${esc(group.label)}
      <span class="ag-count">${group.items.length}</span>
    </div>`;

    for (const item of group.items) {
      const chain = traceLineage(item.action.id);
      const badgeClass = item.badge || '';

      html += `<div class="artifact-card" onclick="this.classList.toggle('expanded')">
        <div class="artifact-card-header">
          <span class="ac-icon">${activityIcon(item.action.type)}</span>
          <span class="ac-label">${esc(item.label)}</span>
          <span class="ac-meta">${esc(item.meta)}</span>
          ${item.badge ? `<span class="ac-badge ${badgeClass}">${esc(item.badge)}</span>` : ''}
          <span class="ac-chevron">\u25B8</span>
        </div>
        <div class="artifact-card-body">
          ${renderLineageChain(chain, item.action.id)}
        </div>
      </div>`;
    }

    html += `</div>`;
  }

  el.innerHTML = html;
}

// ============================================================
// Modal renderers
// ============================================================

// Collect VGs from inline reasoning actions
function collectVGs() {
  const vgs = [];
  for (const a of (traceData?.actions || [])) {
    if (a.vg_defined) {
      const result = traceData.actions.find(r => r.vg_result?.goal_id === a.vg_defined.goal_id);
      vgs.push({
        ...a.vg_defined,
        status: result?.vg_result?.status || 'pending',
        result: result?.vg_result?.result || null,
        defined_in: a.id,
        verified_in: result?.id || null
      });
    }
  }
  return vgs;
}

// Collect decompositions from inline reasoning actions
function collectDecomps() {
  return (traceData?.actions || []).filter(a => a.decomposition).map(a => ({
    ...a.decomposition,
    action_id: a.id
  }));
}

// Collect generated tests from inline reasoning actions
function collectTests() {
  return (traceData?.actions || []).filter(a => a.generated_tests).map(a => ({
    ...a.generated_tests,
    action_id: a.id,
    action_label: a.label,
  }));
}

// Collect formalizations
function collectFormalizations() {
  return (traceData?.actions || []).filter(a => a.formalization).map(a => ({
    ...a.formalization,
    action_id: a.id,
    label: a.label
  }));
}

function renderVGModal() {
  const vgs = collectVGs();
  if (!vgs.length) return '<p style="color:#64748b">No verification goals in this trace.</p>';
  let html = '';
  for (const vg of vgs) {
    const status = vg.status || 'pending';
    let body = '';
    if (vg.src) body += `<div class="mvg-src">${highlightIMLSmart(vg.src)}</div>`;
    if (vg.result?.proved) {
      body += `<div style="font-size:10px;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Proof</div>`;
      body += formatProof(vg.result.proved.proof_pp, vg.result.proved.properties);
    }
    if (vg.result?.sat) {
      body += `<div style="font-size:10px;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Instance Found</div>`;
      body += `<div class="mvg-instance">${esc(vg.result.sat.model.src)}</div>`;
    }
    if (vg.result?.refuted) {
      body += `<div style="font-size:10px;color:#64748b;text-transform:uppercase;margin-bottom:4px;">Counterexample</div>`;
      const refText2 = typeof vg.result.refuted === 'string' ? vg.result.refuted : vg.result.refuted.counterexample || JSON.stringify(vg.result.refuted, null, 2);
      body += `<div class="mvg-instance clr-red">${highlightIML(refText2)}</div>`;
    }
    const links = [];
    if (vg.defined_in) links.push(`defined in <a href="#" onclick="event.stopPropagation();closeModal();switchView('flow');selectAction(${vg.defined_in});document.querySelector('.action-card[data-action-id=&quot;${vg.defined_in}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="color:var(--accent);text-decoration:none;">#${vg.defined_in}</a>`);
    if (vg.verified_in) links.push(`verified in <a href="#" onclick="event.stopPropagation();closeModal();switchView('flow');selectAction(${vg.verified_in});document.querySelector('.action-card[data-action-id=&quot;${vg.verified_in}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="color:var(--accent);text-decoration:none;">#${vg.verified_in}</a>`);
    if (links.length) body += `<div class="mvg-meta">${links.join(' \u2022 ')}</div>`;

    const actionLinks = [];
    if (vg.defined_in) actionLinks.push(`<a href="#" onclick="event.stopPropagation();closeModal();switchView('flow');selectAction(${vg.defined_in});document.querySelector('.action-card[data-action-id=&quot;${vg.defined_in}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="color:var(--accent);text-decoration:none;font-size:10px;">#${vg.defined_in}</a>`);
    if (vg.verified_in) actionLinks.push(`<a href="#" onclick="event.stopPropagation();closeModal();switchView('flow');selectAction(${vg.verified_in});document.querySelector('.action-card[data-action-id=&quot;${vg.verified_in}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="color:var(--accent);text-decoration:none;font-size:10px;">#${vg.verified_in}</a>`);
    const actionLinksHtml = actionLinks.length ? `<span style="font-size:10px;color:var(--text-dim);margin-left:4px;">Actions ${actionLinks.join(', ')}</span>` : '';

    html += `<div class="mvg-card" id="mvg-${vg.goal_id}" onclick="this.classList.toggle('expanded')">
      <div class="mvg-header">
        <span class="mvg-kind">${esc(vg.kind || 'verify')}</span>
        <span class="mvg-desc">${esc(vg.description)}</span>
        ${actionLinksHtml}
        <span class="mvg-badge ${status}">${status}</span>
        <span class="mvg-chevron">\u25B8</span>
      </div>
      <div class="mvg-body">${body}</div>
    </div>`;
  }
  return html;
}

function renderDecompModal() {
  const decs = collectDecomps();
  if (!decs.length) return '<p style="color:#64748b">No decompositions in this trace.</p>';

  let html = '';
  for (let di = 0; di < decs.length; di++) {
    const dec = decs[di];
    if (di > 0) {
      html += `<hr style="border:none;border-top:1px solid var(--border);margin:24px 0;">`;
    }
    html += `<div class="mdec-card"><div class="mdec-header">
      <span class="mdec-fn">Decomposed function: <span style="font-weight:700;">${esc(dec.target_function)}</span></span>
      <span class="mdec-desc">${esc(dec.description || '')}</span>
      <span style="font-size:11px;margin-left:auto;"><a href="#" onclick="event.preventDefault();closeModal();switchView('flow');selectAction(${dec.action_id});document.querySelector('.action-card[data-action-id=&quot;${dec.action_id}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="color:var(--accent);text-decoration:none;">Action #${dec.action_id} \u2192</a></span>
      <span class="mdec-complete ${dec.complete ? 'yes' : 'no'}">${dec.complete ? 'Complete' : 'Partial'}</span>
    </div>`;

    // Voronoi diagram for this decomposition
    html += `<div id="modal-voronoi-${di}" style="padding:12px;"></div>`;

    // Region table
    html += `<table class="mdec-table"><thead><tr>
      <th>Region</th><th>Constraints</th><th>Invariant</th><th>Witness</th><th>Eval</th>
    </tr></thead><tbody>`;
    dec.regions.forEach((r, idx) => {
      const cons = r.constraints || r.constraints_str || [];
      const inv = r.invariant || r.invariant_str || '';
      const model = r.model || r.model_str || {};
      const meval = r.model_eval || r.model_eval_str || '';
      const wit = typeof model === 'object' ? Object.entries(model).map(([k, v]) => `${k} = ${v}`).join('\n') : String(model);
      html += `<tr><td class="r-idx">R${idx + 1}</td><td class="r-cons">${cons.map(c => esc(c)).join('<br>')}</td><td class="r-inv">${esc(inv)}</td><td class="r-wit">${esc(wit)}</td><td class="r-eval">${esc(String(meval))}</td></tr>`;
    });
    html += `</tbody></table></div>`;
  }

  // Deferred: render Voronoi inside each card after modal DOM is ready
  requestAnimationFrame(() => {
    decs.forEach((dec, di) => {
      const vc = document.getElementById('modal-voronoi-' + di);
      if (vc) renderVoronoi(vc, dec, 820, 240);
    });
  });

  return html;
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Copied!';
    setTimeout(() => btn.textContent = orig, 1500);
  });
}

function renderFormalModal() {
  const formalizations = collectFormalizations();
  if (!formalizations.length) return '<p style="color:var(--text-dim)">No formalization data in this trace.</p>';
  let html = '';
  for (let i = 0; i < formalizations.length; i++) {
    const f = formalizations[i];
    if (i > 0) {
      html += `<hr style="border:none;border-top:1px solid var(--border);margin:24px 0;">`;
    }
    html += `<div style="margin-bottom:24px;">`;
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
      <span style="font-size:13px;font-weight:600;color:var(--text-primary);">${esc(f.label)}</span>
      <span class="status-badge ${f.status}" style="font-size:10px;">${f.status}</span>
      <a href="#" onclick="event.preventDefault();closeModal();switchView('flow');selectAction(${f.action_id});document.querySelector('.action-card[data-action-id=&quot;${f.action_id}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="font-size:11px;color:var(--accent);text-decoration:none;margin-left:auto;">Action #${f.action_id} \u2192</a>
    </div>`;
    const srcId = 'formal-src-' + i;
    const imlId = 'formal-iml-' + i;
    html += `<div class="mformal-panes">
      <div class="mformal-pane">
        <div class="mformal-pane-header">
          Source <span class="lang">${esc(f.src_lang)}</span>
          <button class="copy-btn" onclick="event.stopPropagation();var t=document.getElementById('${srcId}');copyToClipboard(t.textContent,this)">Copy</button>
        </div>
        <pre id="${srcId}" style="display:none;">${esc(f.src_code)}</pre>
        <div class="mformal-pane-body src">${highlightCode(f.src_code, f.src_lang)}</div>
      </div>
      <div class="mformal-arrow">\u2192</div>
      <div class="mformal-pane">
        <div class="mformal-pane-header">
          IML <span class="lang">iml</span>
          <button class="copy-btn" onclick="event.stopPropagation();var t=document.getElementById('${imlId}');copyToClipboard(t.textContent,this)">Copy</button>
        </div>
        <pre id="${imlId}" style="display:none;">${esc(f.iml_code)}</pre>
        <div class="mformal-pane-body iml">${highlightIMLSmart(f.iml_code)}</div>
      </div>
    </div>`;
    // Symbols omitted — the IML source is the authoritative listing
    html += `</div>`;
  }
  return html;
}

function renderTestsModal() {
  const groups = collectTests();
  if (!groups.length) return '<p style="color:#64748b">No generated tests in this trace.</p>';
  let html = '';
  for (const g of groups) {
    html += `<div class="mtest-group">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
        <div class="mtest-group-hdr" style="margin-bottom:0;">Function under test: <span style="font-weight:700;">${esc(g.function)}</span></div>
        ${g.action_id ? `<a href="#" onclick="event.preventDefault();closeModal();switchView('flow');selectAction(${g.action_id});document.querySelector('.action-card[data-action-id=&quot;${g.action_id}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="font-size:11px;color:var(--accent);text-decoration:none;margin-left:auto;">Action #${g.action_id} \u2192</a>` : ''}
      </div>
      <div class="mtest-group-lang">Language: ${esc(g.language)}</div>`;
    for (const t of g.tests) {
      const inputs = typeof t.inputs === 'object' ? Object.entries(t.inputs).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(', ') : String(t.inputs);
      html += `<div class="mtest-card" onclick="this.classList.toggle('expanded')">
        <div class="mtest-header">
          <span class="mtest-name">${esc(t.name)}</span>
          <span class="mtest-region">R${t.region_index + 1}</span>
          <span class="mtest-chevron">\u25B8</span>
        </div>
        <div class="mtest-body">
          <div class="mtest-cons">${(t.constraints || []).map(c => esc(c)).join(' AND ')}</div>
          <div class="mtest-io">
            <div><div class="lbl">Inputs</div><div class="val">${esc(inputs)}</div></div>
            <div><div class="lbl">Expected</div><div class="val">${esc(String(t.expected))}</div></div>
          </div>
          <div class="mtest-code">${highlightCode(t.code, g.language)}</div>
        </div>
      </div>`;
    }
    html += `</div>`;
  }
  return html;
}

const PROP_DESCRIPTIONS = {
  research_before_edit: 'Every edit preceded by research',
  all_decisions_justified: 'All gateways have rationale',
  tests_before_commit: 'Tests run before any commit',
  tests_pass_before_commit: 'Zero test failures before commit',
  destructive_actions_confirmed: 'Deletes are user-confirmed',
  all_actions_have_rationale: 'Every action has a rationale',
  data_flow_integrity: 'All inputs traceable to prior outputs',
  goals_reference_valid_actions: 'VG action refs are valid',
  goals_reference_valid_artifacts: 'VG artifact refs are valid',
  trace_has_proper_lifecycle: 'Start event + end event present',
  files_modified_consistent: 'files_modified matches edits',
  reasoning_required_for_high_stakes_changes: 'High-stakes edits need formal reasoning',
  generated_tests_require_decomposition: 'Tests must derive from decomposition',
};

function renderPropsModal() {
  const props = traceData?.process_properties || [];
  if (!props.length) return '<p style="color:#64748b">No process properties in this trace.</p>';
  const allPass = props.every(p => p.passed);
  let html = `<div class="mprop-summary" style="color:${allPass ? 'var(--green)' : 'var(--red)'}">${allPass ? 'All properties pass' : 'Some properties failed'}</div>`;
  for (const p of props) {
    html += `<div class="mprop-row">
      <div class="mprop-icon">${p.passed ? '\u2705' : '\u274C'}</div>
      <div class="mprop-name">${esc(p.name)}</div>
      <div class="mprop-desc">${esc(PROP_DESCRIPTIONS[p.name] || '')}</div>
    </div>`;
  }
  return html;
}

function renderPoliciesModal() {
  const policies = traceData?.policies || [];
  if (!policies.length) return '<p style="color:var(--text-dim)">No policies declared in this trace.</p>';

  const evals = traceData?.policy_evaluations || [];
  const evalMap = {};
  for (const e of evals) evalMap[e.policy_id] = e;

  const applicable = policies.filter(p => (evalMap[p.policy_id]?.status || 'unknown') !== 'not_applicable');
  const passed = evals.filter(e => e.status === 'passed').length;
  const failed = evals.filter(e => e.status === 'failed').length;
  const na = evals.filter(e => e.status === 'not_applicable').length;

  const sevLabels = { error: 'Critical', warning: 'Moderate', info: 'Informational' };
  const sevOrder = ['error', 'warning', 'info'];

  let html = `<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;">
    <div class="mprop-summary" style="color:${failed ? 'var(--red)' : 'var(--green)'};margin:0;">${passed}/${applicable.length} applicable passed${failed ? `, ${failed} failed` : ''}${na ? ` (${na} Not Applicable)` : ''}</div>
    <label style="margin-left:auto;font-size:11px;color:var(--text-muted);display:flex;align-items:center;gap:4px;cursor:pointer;">
      <input type="checkbox" id="policyModalHideNA" checked onchange="document.querySelectorAll('.mpolicy-na-row').forEach(r=>r.style.display=this.checked?'none':'')"> Hide non-applicable
    </label>
  </div>`;

  for (const sev of sevOrder) {
    const group = policies.filter(p => p.severity === sev);
    if (!group.length) continue;

    const groupApplicable = group.filter(p => (evalMap[p.policy_id]?.status || 'unknown') !== 'not_applicable').length;

    html += `<div style="margin-bottom:16px;">
      <div style="font-size:10px;font-weight:700;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">
        ${sevLabels[sev] || sev} <span style="font-weight:400;color:var(--text-dim);">(${groupApplicable}/${group.length} applicable)</span>
      </div>`;

    for (const p of group) {
      const ev = evalMap[p.policy_id];
      const status = ev?.status || 'unknown';
      const isNA = status === 'not_applicable';
      const icon = status === 'passed' ? '\u2705' : status === 'failed' ? '\u274C' : isNA ? '\u2796' : '\u2753';
      const rowClass = isNA ? 'mpolicy-row mpolicy-na-row' : 'mpolicy-row';
      const rowStyle = isNA ? 'style="display:none;opacity:0.6;"' : '';

      html += `<div class="${rowClass}" ${rowStyle}>
        <div class="mpolicy-icon">${icon}</div>
        <div class="mpolicy-body">
          <div class="mpolicy-name">${esc(p.name)}${isNA ? ' <span style="font-size:9px;color:var(--text-dim);font-weight:400;font-family:inherit;">(non-applicable)</span>' : ''}</div>
          ${p.description ? `<div class="mpolicy-desc">${esc(p.description)}</div>` : ''}
          ${ev?.note ? `<div class="mpolicy-note">${esc(ev.note)}</div>` : ''}
        </div>
        <span class="mpolicy-severity ${p.severity || ''}">${esc(sevLabels[p.severity] || p.severity || '')}</span>
      </div>`;
    }

    html += `</div>`;
  }
  return html;
}

// ============================================================
// Residual Surface Modal (v1.5 negative space)
// ============================================================
function renderResidualsModal() {
  const residuals = traceData?.residuals || [];
  if (!residuals.length) return '<p style="color:var(--text-dim)">No residuals declared — empty negative space.</p>';

  const sevColor = { critical: 'var(--red)', high: '#f59e0b', medium: '#eab308', low: 'var(--text-muted)', info: 'var(--text-dim)' };
  const sevRank = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
  const kindLabel = { assumption: 'Assumption', unverified: 'Unverified', out_of_scope: 'Out of scope', limitation: 'Limitation', open_question: 'Open question' };
  const statusIcon = { open: '⚠️', acknowledged: '\u{1F441}️', addressed: '✅', waived: '➖' };

  const ordered = [...residuals].sort((a, b) => (sevRank[b.severity] || 0) - (sevRank[a.severity] || 0));
  const openCount = residuals.filter(r => (r.status || 'open') === 'open').length;

  let html = `<div class="mprop-summary" style="margin:0 0 6px;">${residuals.length} declared · ${openCount} open</div>
    <p style="color:var(--text-dim);font-size:11px;margin:0 0 16px;">What the trace did <b>not</b> establish &mdash; assumptions, unverified claims, out-of-scope items, limitations, and open questions.</p>`;

  for (const r of ordered) {
    const sev = r.severity || 'info';
    const color = sevColor[sev] || 'var(--text-dim)';
    const status = r.status || 'open';
    const icon = statusIcon[status] || '❓';
    const loc = [];
    if (r.target) loc.push('target: ' + esc((r.target.target_type || '') + ':' + (r.target.target_id || '')));
    if (r.related_artifact_ids?.length) loc.push('related: ' + esc(r.related_artifact_ids.join(', ')));

    html += `<div class="mpolicy-row">
      <div class="mpolicy-icon">${icon}</div>
      <div class="mpolicy-body">
        <div class="mpolicy-name">${esc(kindLabel[r.kind] || r.kind || 'residual')} <span style="font-size:9px;color:var(--text-dim);font-weight:400;font-family:inherit;">· ${esc(status)}</span></div>
        ${r.statement ? `<div class="mpolicy-desc">${esc(r.statement)}</div>` : ''}
        ${loc.length ? `<div class="mpolicy-note">${loc.join('&nbsp;&nbsp;&nbsp;')}</div>` : ''}
        ${r.suggested_check ? `<div class="mpolicy-note">check: ${esc(r.suggested_check)}</div>` : ''}
      </div>
      <span style="font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:0.04em;color:${color};border:1px solid ${color};border-radius:4px;padding:2px 6px;white-space:nowrap;height:fit-content;">${esc(sev)}</span>
    </div>`;
  }
  return html;
}

// ============================================================
// Reference Models Modal
// ============================================================
function renderRefModelsModal() {
  const models = traceData?.reference_models || [];
  if (!models.length) return '<p style="color:var(--text-dim)">No reference models in this trace.</p>';

  const policies = traceData?.policies || [];
  const evals = traceData?.policy_evaluations || [];
  const evalMap = {};
  for (const e of evals) evalMap[e.policy_id] = e;

  let html = '';
  for (let i = 0; i < models.length; i++) {
    const m = models[i];
    if (i > 0) html += `<hr style="border:none;border-top:1px solid var(--border);margin:24px 0;">`;

    // Find policies that reference this model
    const linkedPolicies = policies.filter(p => p.reference_model_id === m.reference_model_id);

    html += `<div style="margin-bottom:24px;">`;

    // Header
    html += `<div style="display:flex;align-items:flex-start;gap:12px;margin-bottom:14px;">
      <div style="flex:1;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="font-size:16px;font-weight:700;color:var(--text-primary);">${esc(m.name)}</span>
          ${m.version ? `<span class="version-badge">${esc(m.version)}</span>` : ''}
        </div>
        ${m.description ? `<div style="font-size:12px;color:var(--text-secondary);line-height:1.5;margin-bottom:6px;">${esc(m.description)}</div>` : ''}
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <span style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-inset);border:1px solid var(--border);color:var(--text-muted);">Domain: ${esc(m.domain)}</span>
          ${m.source ? `<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-inset);border:1px solid var(--border);color:var(--text-muted);">Source: ${esc(m.source)}</span>` : ''}
          <span style="font-size:10px;padding:2px 8px;border-radius:4px;background:var(--bg-inset);border:1px solid var(--border);color:var(--text-muted);">ID: ${esc(m.reference_model_id)}</span>
        </div>
      </div>
    </div>`;

    // IML source
    const imlId = 'refmodel-iml-' + i;
    html += `<div style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
        <span style="font-size:11px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;">Reference Model (IML)</span>
        <button class="copy-btn" onclick="event.stopPropagation();var t=document.getElementById('${imlId}');copyToClipboard(t.textContent,this)">Copy</button>
      </div>
      <pre id="${imlId}" style="display:none;">${esc(m.iml)}</pre>
      <div class="dp-code-block iml" style="max-height:300px;overflow-y:auto;">${highlightIMLSmart(m.iml)}</div>
    </div>`;

    // Symbols
    // Symbols omitted for reference models — the IML source is the authoritative listing

    // Verification goals
    if (m.verification_goals?.length) {
      html += `<div style="margin-bottom:16px;">
        <span style="font-size:11px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;display:block;margin-bottom:8px;">Reference Verification Goals (${m.verification_goals.length})</span>`;
      for (const vg of m.verification_goals) {
        const kindColors = { conformance: 'var(--accent)', invariant: 'var(--green)', refinement: 'var(--purple)' };
        html += `<div style="background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;padding:10px 14px;margin-bottom:6px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px;text-transform:uppercase;background:var(--bg-deep);border:1px solid ${kindColors[vg.kind] || 'var(--border)'};color:${kindColors[vg.kind] || 'var(--text-muted)'};">${esc(vg.kind)}</span>
            <span style="font-size:12px;color:var(--text-primary);">${esc(vg.description)}</span>
          </div>
          <div class="dp-code-block iml" style="margin:4px 0 0 0;max-height:80px;font-size:11px;">${highlightIMLSmart(vg.iml)}</div>
        </div>`;
      }
      html += `</div>`;
    }

    // Linked policies
    if (linkedPolicies.length) {
      html += `<div>
        <span style="font-size:11px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.05em;display:block;margin-bottom:8px;">Linked Policies</span>`;
      for (const p of linkedPolicies) {
        const ev = evalMap[p.policy_id];
        const st = ev?.status || 'unknown';
        const icon = st === 'passed' ? '\u2705' : st === 'failed' ? '\u274C' : st === 'not_applicable' ? '\u2796' : '\u2753';
        html += `<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;background:var(--bg-inset);border:1px solid var(--border);border-radius:6px;margin-bottom:4px;">
          <span>${icon}</span>
          <span style="font-family:'SF Mono','Fira Code',monospace;font-size:11px;color:var(--text-primary);flex:1;">${esc(p.name)}</span>
          <span style="font-size:10px;color:var(--text-muted);">${esc(p.description || '')}</span>
        </div>`;
      }
      html += `</div>`;
    }

    html += `</div>`;
  }
  return html;
}

// ============================================================
// Artifact DAG View
// ============================================================
const DAG_TYPE_COLORS_DARK = {
  UserInstruction: { bg: '#1c1e26', border: '#6a7080', text: '#a0a4b0' },
  SourceCode: { bg: '#141822', border: '#4a78c0', text: '#90b0d8' },
  Documentation: { bg: '#141822', border: '#5888c0', text: '#90b0d8' },
  SearchResults: { bg: '#141822', border: '#5888c0', text: '#90b0d8' },
  AnalysisNote: { bg: '#181620', border: '#7858c0', text: '#b0a0d0' },
  Plan: { bg: '#181620', border: '#8870b8', text: '#b0a0d0' },
  Formalization: { bg: '#1a1428', border: '#6848b0', text: '#b0a0d0' },
  IMLModel: { bg: '#1a1428', border: '#8870b8', text: '#b0a0d0' },
  VerificationGoal: { bg: '#161428', border: '#5858b8', text: '#9898d0' },
  VerificationResult: { bg: '#141e14', border: '#3a9860', text: '#80c8a0' },
  Decomposition: { bg: '#1e1c10', border: '#b89828', text: '#d8c870' },
  GeneratedTests: { bg: '#101c1e', border: '#2890a0', text: '#68b8c8' },
  CommandResult: { bg: '#1c1e26', border: '#6a7080', text: '#a0a4b0' },
  Diff: { bg: '#141e1a', border: '#38a880', text: '#80c8b0' },
  Commit: { bg: '#1e1420', border: '#b85888', text: '#d898b8' },
  UserApproval: { bg: '#1e1c14', border: '#c09830', text: '#d8c870' },
  ReferenceModel: { bg: '#141820', border: '#5090c0', text: '#90b8d8' },
};

const DAG_TYPE_COLORS_LIGHT = {
  UserInstruction: { bg: '#f0f1f4', border: '#8a8f9c', text: '#4a5060' },
  SourceCode: { bg: '#eaf0fa', border: '#3868b0', text: '#2050a0' },
  Documentation: { bg: '#eaf0fa', border: '#4878b0', text: '#2050a0' },
  SearchResults: { bg: '#eaf0fa', border: '#4878b0', text: '#2050a0' },
  AnalysisNote: { bg: '#f0ecfa', border: '#6848a8', text: '#4830a0' },
  Plan: { bg: '#f0ecfa', border: '#7860a0', text: '#4830a0' },
  Formalization: { bg: '#eee8fa', border: '#5838a0', text: '#4030a0' },
  IMLModel: { bg: '#eee8fa', border: '#7860a0', text: '#4030a0' },
  VerificationGoal: { bg: '#eceafa', border: '#4848a8', text: '#3030a0' },
  VerificationResult: { bg: '#e8f5ec', border: '#208848', text: '#186838' },
  Decomposition: { bg: '#f8f4e0', border: '#987810', text: '#685010' },
  GeneratedTests: { bg: '#e4f4f6', border: '#107888', text: '#106070' },
  CommandResult: { bg: '#f0f1f4', border: '#8a8f9c', text: '#4a5060' },
  Diff: { bg: '#e8f5f0', border: '#208860', text: '#186848' },
  Commit: { bg: '#faeef2', border: '#a83868', text: '#882050' },
  UserApproval: { bg: '#faf6e8', border: '#a08010', text: '#786010' },
  ReferenceModel: { bg: '#e8f0fa', border: '#3070a0', text: '#1a4878' },
};

function isLightTheme() {
  return document.documentElement.getAttribute('data-theme') === 'light';
}

function dagTypeColor(type) {
  const palette = isLightTheme() ? DAG_TYPE_COLORS_LIGHT : DAG_TYPE_COLORS_DARK;
  return palette[type] || (isLightTheme()
    ? { bg: '#f0f1f4', border: '#b0b4bc', text: '#4a5060' }
    : { bg: '#1c1e26', border: '#3e4350', text: '#a0a4b0' });
}

function renderDAGView() {
  const el = document.getElementById('view-dag');
  const artifacts = traceData?.artifacts || [];
  if (!artifacts.length) {
    el.innerHTML = `<div style="padding:48px 32px;max-width:640px;margin:0 auto;text-align:center;color:var(--text-dim);">
      <div style="font-size:32px;margin-bottom:12px;opacity:.5;">◇</div>
      <div style="font-size:15px;color:var(--text);margin-bottom:8px;">No lineage in this trace yet</div>
      <p style="font-size:13px;line-height:1.6;margin:0 0 16px;">
        This trace records <em>what the agent did</em>, but not the artifacts it produced or
        consumed &mdash; models, verification goals, generated tests, decompositions &mdash; so there is
        no data-flow graph to draw. The reasoning is in <strong>Flow</strong>; the gaps are in <strong>Residuals</strong>.
      </p>
      <p style="font-size:12px;line-height:1.6;margin:0;opacity:.8;">
        To see lineage here, have the agent emit artifacts and link them
        (<code>inputs</code>/<code>outputs</code>) so each result traces back to what produced it.
      </p>
    </div>`;
    return;
  }

  // Inject reference models as pseudo-artifacts
  const refModels = traceData?.reference_models || [];
  const allArtifacts = [...artifacts];
  for (const rm of refModels) {
    allArtifacts.push({
      artifact_id: rm.reference_model_id,
      artifact_type: 'ReferenceModel',
      name: rm.name,
      format: 'iml',
      revision: null,
      derived_from: [],
      summary: rm.description,
      _isRefModel: true,
    });
  }

  // Find policies that reference a model and link to conformance VG artifacts
  const policies = traceData?.policies || [];
  for (const p of policies) {
    if (p.reference_model_id) {
      // Find VG artifacts produced by actions that reference this model
      for (const a of (traceData?.actions || [])) {
        if (a.request?.reference_model_id === p.reference_model_id) {
          for (const outId of (a._original_outputs || a.outputs || [])) {
            const art = allArtifacts.find(x => x.artifact_id === outId || x.name === outId);
            if (art && !art.derived_from?.includes(p.reference_model_id)) {
              art.derived_from = art.derived_from || [];
              if (!art.derived_from.includes(p.reference_model_id)) {
                art.derived_from.push(p.reference_model_id);
              }
            }
          }
        }
      }
    }
  }

  // Build dependency graph
  const artMap = {};
  for (const a of allArtifacts) artMap[a.artifact_id] = a;

  // Topological sort for Y positioning
  const levels = {};
  function getLevel(id, visited) {
    if (levels[id] != null) return levels[id];
    if (!visited) visited = new Set();
    if (visited.has(id)) return 0;
    visited.add(id);
    const art = artMap[id];
    if (!art) return 0;
    const parents = art.derived_from || [];
    if (!parents.length) { levels[id] = 0; return 0; }
    let maxParent = 0;
    for (const pid of parents) {
      maxParent = Math.max(maxParent, getLevel(pid, visited));
    }
    levels[id] = maxParent + 1;
    return levels[id];
  }
  for (const a of allArtifacts) getLevel(a.artifact_id);

  // Group by level
  const byLevel = {};
  for (const a of allArtifacts) {
    const lv = levels[a.artifact_id] || 0;
    if (!byLevel[lv]) byLevel[lv] = [];
    byLevel[lv].push(a);
  }

  const maxLevel = Math.max(...Object.keys(byLevel).map(Number), 0);
  const nodeW = 150, nodeH = 70, gapX = 30, gapY = 80, padX = 60, padY = 60;

  // Compute positions
  const positions = {};
  let maxCols = 0;
  for (let lv = 0; lv <= maxLevel; lv++) {
    const arts = byLevel[lv] || [];
    maxCols = Math.max(maxCols, arts.length);
  }
  const graphW = Math.max(800, maxCols * (nodeW + gapX) + padX * 2);
  const graphH = (maxLevel + 1) * (nodeH + gapY) + padY * 2;

  for (let lv = 0; lv <= maxLevel; lv++) {
    const arts = byLevel[lv] || [];
    const totalW = arts.length * nodeW + (arts.length - 1) * gapX;
    const startX = (graphW - totalW) / 2;
    arts.forEach((a, i) => {
      positions[a.artifact_id] = {
        x: startX + i * (nodeW + gapX) + nodeW / 2,
        y: padY + lv * (nodeH + gapY) + nodeH / 2
      };
    });
  }

  // Render wrapper with pan/zoom
  let html = `<div class="dag-canvas-wrap" id="dagWrap">`;
  html += `<div class="dag-inner" id="dagInner" style="width:${graphW}px;height:${graphH}px;">`;

  // SVG for edges
  html += `<svg width="${graphW}" height="${graphH}" style="position:absolute;inset:0;pointer-events:none;">`;
  for (const a of allArtifacts) {
    const to = positions[a.artifact_id];
    if (!to) continue;
    for (const pid of (a.derived_from || [])) {
      const from = positions[pid];
      if (!from) continue;
      const isRef = artMap[pid]?._isRefModel;
      const isSup = a.supersedes === pid;
      const light = isLightTheme();
      const color = isSup ? (light ? '#a08010' : '#c09830') : (light ? '#b0b4bc' : '#3e4350');
      const dash = isSup ? 'stroke-dasharray="6,3"' : '';
      const midY = (from.y + to.y) / 2;
      html += `<path d="M${from.x},${from.y + nodeH/2} C${from.x},${midY} ${to.x},${midY} ${to.x},${to.y - nodeH/2}"
        fill="none" stroke="${color}" stroke-width="2" ${dash} opacity="0.7"/>`;
      html += `<polygon points="${to.x},${to.y - nodeH/2} ${to.x-5},${to.y - nodeH/2 - 9} ${to.x+5},${to.y - nodeH/2 - 9}"
        fill="${color}" opacity="0.7"/>`;
    }
  }
  html += `</svg>`;

  // Nodes
  for (const a of allArtifacts) {
    const pos = positions[a.artifact_id];
    if (!pos) continue;
    const col = dagTypeColor(a.artifact_type);
    const isSuperseded = allArtifacts.some(other => other.supersedes === a.artifact_id);
    const supClass = isSuperseded ? ' superseded' : '';
    const refStyle = a._isRefModel ? 'border-style:dashed;border-width:2px;' : '';

    html += `<div class="dag-node${supClass}" data-artifact-id="${esc(a.artifact_id)}"
      style="left:${pos.x - nodeW/2}px;top:${pos.y - nodeH/2}px;width:${nodeW}px;height:${nodeH}px;
      background:${col.bg};border-color:${col.border};${refStyle}"
      onclick="event.stopPropagation();selectDAGNode('${esc(a.artifact_id)}')">
      <span class="dn-type" style="background:${col.border}33;color:${col.text};">${esc(a.artifact_type)}</span>
      <span class="dn-name" title="${esc(a.name || a.artifact_id)}">${esc(a.name || a.artifact_id)}</span>
      ${a.revision ? `<span class="dn-rev">rev ${a.revision}</span>` : ''}
    </div>`;
  }

  html += `</div>`; // dag-inner

  // Detail panel
  html += `<div class="dag-detail" id="dagDetail" style="display:none;"></div>`;

  // Controls
  html += `<div class="dag-controls">
    <button onclick="dagZoom(1.2)" title="Zoom in">+</button>
    <button onclick="dagZoom(0.8)" title="Zoom out">\u2212</button>
    <button onclick="dagFit()" title="Fit to view">\u2922</button>
  </div>`;

  // Legend
  const usedTypes = [...new Set(artifacts.map(a => a.artifact_type))];
  html += `<div class="dag-legend">`;
  for (const t of usedTypes) {
    const col = dagTypeColor(t);
    html += `<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:${col.bg};border:1px solid ${col.border};color:${col.text};">${esc(t)}</span>`;
  }
  const supColor = isLightTheme() ? '#a08010' : '#c09830';
  const supBg = isLightTheme() ? '#faf6e8' : '#1e1c14';
  html += `<span style="font-size:10px;padding:2px 8px;border-radius:4px;background:${supBg};border:1px dashed ${supColor};color:${supColor};">--- supersedes</span>`;
  html += `</div>`;

  html += `</div>`; // dag-canvas-wrap
  el.innerHTML = html;

  // Initialize pan/zoom
  _dagState = { scale: 1, panX: 0, panY: 0, dragging: false, startX: 0, startY: 0, graphW, graphH };
  dagFit();
  initDAGPanZoom();
}

let _dagState = null;

function dagApplyTransform() {
  const inner = document.getElementById('dagInner');
  if (!inner || !_dagState) return;
  inner.style.transform = `translate(${_dagState.panX}px, ${_dagState.panY}px) scale(${_dagState.scale})`;
}

function dagZoom(factor) {
  if (!_dagState) return;
  const wrap = document.getElementById('dagWrap');
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect();
  const cx = rect.width / 2, cy = rect.height / 2;
  // Zoom around center of viewport
  const newScale = Math.max(0.15, Math.min(3, _dagState.scale * factor));
  const ratio = newScale / _dagState.scale;
  _dagState.panX = cx - ratio * (cx - _dagState.panX);
  _dagState.panY = cy - ratio * (cy - _dagState.panY);
  _dagState.scale = newScale;
  dagApplyTransform();
}

function dagFit() {
  if (!_dagState) return;
  const wrap = document.getElementById('dagWrap');
  if (!wrap) return;
  const rect = wrap.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const scaleX = rect.width / _dagState.graphW;
  const scaleY = rect.height / _dagState.graphH;
  _dagState.scale = Math.min(scaleX, scaleY) * 0.9;
  _dagState.panX = (rect.width - _dagState.graphW * _dagState.scale) / 2;
  _dagState.panY = (rect.height - _dagState.graphH * _dagState.scale) / 2;
  dagApplyTransform();
}

function initDAGPanZoom() {
  const wrap = document.getElementById('dagWrap');
  if (!wrap) return;

  wrap.addEventListener('mousedown', (e) => {
    if (e.target.closest('.dag-node') || e.target.closest('.dag-detail') || e.target.closest('.dag-controls')) return;
    _dagState.dragging = true;
    _dagState.startX = e.clientX - _dagState.panX;
    _dagState.startY = e.clientY - _dagState.panY;
    wrap.classList.add('dragging');
    e.preventDefault();
  });

  window.addEventListener('mousemove', (e) => {
    if (!_dagState?.dragging) return;
    _dagState.panX = e.clientX - _dagState.startX;
    _dagState.panY = e.clientY - _dagState.startY;
    dagApplyTransform();
  });

  window.addEventListener('mouseup', () => {
    if (!_dagState) return;
    _dagState.dragging = false;
    wrap.classList.remove('dragging');
  });

  wrap.addEventListener('wheel', (e) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.1 : 0.9;
    const rect = wrap.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    const newScale = Math.max(0.15, Math.min(3, _dagState.scale * factor));
    const ratio = newScale / _dagState.scale;
    _dagState.panX = mx - ratio * (mx - _dagState.panX);
    _dagState.panY = my - ratio * (my - _dagState.panY);
    _dagState.scale = newScale;
    dagApplyTransform();
  }, { passive: false });
}

let _selectedDAGNode = null;
function selectDAGNode(artifactId) {
  _selectedDAGNode = artifactId;
  document.querySelectorAll('.dag-node.selected').forEach(n => n.classList.remove('selected'));
  const node = document.querySelector(`.dag-node[data-artifact-id="${artifactId}"]`);
  if (node) node.classList.add('selected');

  // Check if it's a reference model
  const refModel = (traceData?.reference_models || []).find(rm => rm.reference_model_id === artifactId);
  const art = refModel ? null : traceData._artifactMap?.[artifactId];

  if (!art && !refModel) return;
  const detail = document.getElementById('dagDetail');
  detail.style.display = '';

  if (refModel) {
    // Render reference model detail
    const col = dagTypeColor('ReferenceModel');
    let html = `<h3 style="color:${col.text};">${esc(refModel.name)}</h3>`;
    html += `<div class="dd-field"><span class="dn-type" style="background:${col.border}33;color:${col.text};display:inline-block;margin-bottom:4px;">ReferenceModel</span></div>`;
    html += `<div class="dd-field">ID: <span>${esc(refModel.reference_model_id)}</span></div>`;
    html += `<div class="dd-field">Domain: <span>${esc(refModel.domain)}</span></div>`;
    if (refModel.version) html += `<div class="dd-field">Version: <span>${esc(refModel.version)}</span></div>`;
    if (refModel.source) html += `<div class="dd-field">Source: <span>${esc(refModel.source)}</span></div>`;
    if (refModel.description) html += `<div class="dd-field" style="margin-top:6px;font-size:11px;">${esc(refModel.description)}</div>`;
    if (refModel.verification_goals?.length) {
      html += `<div class="dd-field" style="margin-top:6px;">VGs: <span>${refModel.verification_goals.length} reference goals</span></div>`;
    }
    html += `<div style="margin-top:10px;">
      <button onclick="event.stopPropagation();openModal('refmodels');" style="background:var(--bg-deep);border:1px solid var(--accent);color:var(--accent);font-size:10px;padding:4px 10px;border-radius:4px;cursor:pointer;display:flex;align-items:center;gap:4px;">
        Open Reference Model \u2192
      </button>
    </div>`;

    // Show downstream artifacts that depend on this reference model
    const allArts = traceData.artifacts || [];
    const downstream = allArts.filter(a => (a.derived_from || []).includes(artifactId));
    if (downstream.length) {
      html += `<div class="dd-label">Used By</div>`;
      for (const d of downstream) {
        html += `<div class="dd-field" style="cursor:pointer;color:var(--accent);" onclick="selectDAGNode('${esc(d.artifact_id)}')">\u2192 ${esc(d.name || d.artifact_id)}</div>`;
      }
    }

    detail.innerHTML = html;
    return;
  }

  const col = dagTypeColor(art.artifact_type);
  let html = `<h3 style="color:${col.text};">${esc(art.name || art.artifact_id)}</h3>`;
  html += `<div class="dd-field"><span class="dn-type" style="background:${col.border}33;color:${col.text};display:inline-block;margin-bottom:4px;">${esc(art.artifact_type)}</span></div>`;
  html += `<div class="dd-field">ID: <span>${esc(art.artifact_id)}</span></div>`;
  if (art.revision) html += `<div class="dd-field">Revision: <span>${art.revision}</span></div>`;
  if (art.format) html += `<div class="dd-field">Format: <span>${esc(art.format)}</span></div>`;
  if (art.producer_action_id != null) html += `<div class="dd-field" style="display:flex;align-items:center;gap:6px;">Producer: <span>Action #${art.producer_action_id}</span> <button onclick="event.stopPropagation();switchView('flow');selectAction(${art.producer_action_id});document.querySelector('.action-card[data-action-id=&quot;${art.producer_action_id}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});" style="background:var(--bg-deep);border:1px solid var(--accent);color:var(--accent);font-size:10px;padding:2px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;">View in Flow \u2192</button></div>`;
  if (art.summary) html += `<div class="dd-field" style="margin-top:6px;">${esc(art.summary)}</div>`;

  // Host embedding (desktop): open the materialized artifact file in an editor tab.
  if (typeof window.__ponensOpenArtifact === 'function') {
    html += `<div style="margin-top:8px;"><button onclick="event.stopPropagation();window.__ponensOpenArtifact('${esc(art.artifact_id)}');" style="background:var(--bg-deep);border:1px solid var(--accent);color:var(--accent);font-size:10px;padding:4px 10px;border-radius:4px;cursor:pointer;">Open file \u2192</button></div>`;
  }

  if (art.derived_from?.length) {
    html += `<div class="dd-label">Derived From</div>`;
    for (const pid of art.derived_from) {
      const parent = traceData._artifactMap?.[pid];
      const refParent = (traceData?.reference_models || []).find(rm => rm.reference_model_id === pid);
      const parentName = parent?.name || refParent?.name || pid;
      html += `<div class="dd-field" style="cursor:pointer;color:var(--accent);" onclick="selectDAGNode('${esc(pid)}')">\u2190 ${esc(parentName)}</div>`;
    }
  }
  if (art.supersedes) {
    const sup = traceData._artifactMap?.[art.supersedes];
    html += `<div class="dd-label">Supersedes</div>`;
    html += `<div class="dd-field" style="cursor:pointer;color:var(--yellow-bright);" onclick="selectDAGNode('${esc(art.supersedes)}')">\u21BB ${esc(sup?.name || art.supersedes)}</div>`;
  }

  // Show downstream
  const downstream = (traceData.artifacts || []).filter(a => (a.derived_from || []).includes(artifactId));
  if (downstream.length) {
    html += `<div class="dd-label">Consumed By</div>`;
    for (const d of downstream) {
      html += `<div class="dd-field" style="cursor:pointer;color:var(--accent);" onclick="selectDAGNode('${esc(d.artifact_id)}')">\u2192 ${esc(d.name || d.artifact_id)}</div>`;
    }
  }

  detail.innerHTML = html;
}

// ============================================================
// Reasoning Funnel View
// ============================================================
function renderFunnelView() {
  const el = document.getElementById('view-funnel');
  const actions = traceData?.actions || [];
  const artifacts = traceData?.artifacts || [];

  // Count by stage — use both inline (v1.0) and artifact-based (v1.1) detection
  const formalizations = actions.filter(a => a.formalization);
  const vgDefs = actions.filter(a => a.vg_defined);
  const verifications = actions.filter(a => a.vg_result);
  const decompositions = actions.filter(a => a.decomposition);
  const testGens = actions.filter(a => a.generated_tests);

  // VG result breakdown
  const proved = verifications.filter(a => a.vg_result?.status === 'proved');
  const refuted = verifications.filter(a => a.vg_result?.status === 'refuted');
  const sat = verifications.filter(a => a.vg_result?.status === 'sat');
  const unknown = verifications.filter(a => a.vg_result?.status === 'unknown');

  // Total tests generated
  const totalTests = testGens.reduce((s, a) => s + (a.generated_tests?.tests?.length || 0), 0);
  // Total regions
  const totalRegions = decompositions.reduce((s, a) => s + (a.decomposition?.regions?.length || 0), 0);

  // Count properties proved (from batch VGs)
  let totalPropsProved = 0;
  for (const a of proved) {
    const props = a.vg_result?.result?.proved?.properties;
    totalPropsProved += props ? props.filter(p => p.status === 'proved').length : 1;
  }

  const stages = [
    { label: 'Formalizations', count: formalizations.length, color: '#7c3aed', icon: '\u{1F4D0}' },
    { label: 'Goals Defined', count: vgDefs.length, color: '#6366f1', icon: '\u{1F3AF}' },
    { label: 'Verifications', count: verifications.length, color: '#22c55e', icon: '\u{2696}\uFE0F' },
    { label: 'Edge Cases', count: decompositions.length, color: '#eab308', icon: '\u{1F9E9}' },
    { label: 'Test Generations', count: testGens.length, color: '#06b6d4', icon: '\u{1F9EA}' },
  ];

  const maxCount = Math.max(...stages.map(s => s.count), 1);

  let html = `<h2 style="font-size:14px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:20px;">Formal Reasoning Funnel</h2>`;

  // Bar chart
  html += `<div class="funnel-stages">`;
  stages.forEach((s, i) => {
    // no arrows between bars
    const barH = Math.max(8, (s.count / maxCount) * 180);
    html += `<div class="funnel-stage">
      <div class="funnel-bar-wrap">
        <div class="funnel-bar" style="height:${barH}px;background:${s.color}33;border:2px solid ${s.color};">
          <div class="funnel-count" style="color:${s.color};">${s.count}</div>
        </div>
      </div>
      <div class="funnel-label">${s.icon} ${esc(s.label)}</div>
    </div>`;
  });
  html += `</div>`;

  // Breakdown cards
  html += `<div class="funnel-breakdown">`;

  // Verification outcomes
  html += `<div class="funnel-breakdown-card">
    <h4>Verification Outcomes</h4>
    <div class="fb-row"><span class="fb-icon">\u2705</span><span class="fb-label">Proved</span><span class="fb-count clr-green">${proved.length}</span></div>
    <div class="fb-row"><span class="fb-icon">\u274C</span><span class="fb-label">Refuted</span><span class="fb-count clr-red">${refuted.length}</span></div>
    <div class="fb-row"><span class="fb-icon">\u{1F50D}</span><span class="fb-label">Instance (sat)</span><span class="fb-count clr-blue">${sat.length}</span></div>
    ${unknown.length ? `<div class="fb-row"><span class="fb-icon">\u2753</span><span class="fb-label">Unknown</span><span class="fb-count clr-yellow">${unknown.length}</span></div>` : ''}
    <div style="border-top:1px solid #334155;margin-top:6px;padding-top:6px;">
      <div class="fb-row"><span class="fb-icon">\u{1F3C6}</span><span class="fb-label">Properties proved</span><span class="fb-count clr-green">${totalPropsProved}</span></div>
    </div>
  </div>`;

  // Decomposition & tests
  html += `<div class="funnel-breakdown-card">
    <h4>Coverage</h4>
    <div class="fb-row"><span class="fb-icon">\u{1F9E9}</span><span class="fb-label">Total regions</span><span class="fb-count">${totalRegions}</span></div>
    <div class="fb-row"><span class="fb-icon">\u{1F9EA}</span><span class="fb-label">Total tests</span><span class="fb-count">${totalTests}</span></div>
    ${totalRegions > 0 ? `<div class="fb-row"><span class="fb-icon">\u{1F4CA}</span><span class="fb-label">Tests/region</span><span class="fb-count">${(totalTests / totalRegions).toFixed(1)}</span></div>` : ''}
  </div>`;

  // Execution stats (v1.1)
  const reasoningActions = actions.filter(a => a.category === 'reasoning' && a.execution?.duration_ms);
  if (reasoningActions.length) {
    const totalMs = reasoningActions.reduce((s, a) => s + a.execution.duration_ms, 0);
    const engines = [...new Set(reasoningActions.map(a => a.execution.tool).filter(Boolean))];
    html += `<div class="funnel-breakdown-card">
      <h4>Execution</h4>
      <div class="fb-row"><span class="fb-icon">\u23F1</span><span class="fb-label">Total reasoning time</span><span class="fb-count">${(totalMs / 1000).toFixed(1)}s</span></div>
      <div class="fb-row"><span class="fb-icon">\u{2699}\uFE0F</span><span class="fb-label">Reasoning steps</span><span class="fb-count">${reasoningActions.length}</span></div>
      <div class="fb-row"><span class="fb-icon">\u{1F4A1}</span><span class="fb-label">Avg per step</span><span class="fb-count">${Math.round(totalMs / reasoningActions.length)}ms</span></div>
      ${engines.length ? `<div style="border-top:1px solid #334155;margin-top:6px;padding-top:6px;">
        <div class="fb-row"><span class="fb-icon">\u{1F527}</span><span class="fb-label">Engines</span><span class="fb-count">${engines.map(e => esc(e)).join(', ')}</span></div>
      </div>` : ''}
    </div>`;
  }

  // Formalization status
  const transparentCount = formalizations.filter(a => a.formalization?.status === 'transparent').length;
  const opaqueCount = formalizations.filter(a => a.formalization?.status === 'opaque').length;
  const failedCount = formalizations.filter(a => a.formalization?.status === 'failed').length;
  if (formalizations.length) {
    html += `<div class="funnel-breakdown-card">
      <h4>Formalization Quality</h4>
      <div class="fb-row"><span class="fb-icon clr-green">\u25CF</span><span class="fb-label">Transparent</span><span class="fb-count clr-green">${transparentCount}</span></div>
      ${opaqueCount ? `<div class="fb-row"><span class="fb-icon clr-yellow">\u25CF</span><span class="fb-label">Opaque</span><span class="fb-count clr-yellow">${opaqueCount}</span></div>` : ''}
      ${failedCount ? `<div class="fb-row"><span class="fb-icon clr-red">\u25CF</span><span class="fb-label">Failed</span><span class="fb-count clr-red">${failedCount}</span></div>` : ''}
    </div>`;
  }

  html += `</div>`;

  // Reasoning steps list with links to Flow
  const stageGroups = [
    { label: 'Formalizations', actions: formalizations, color: 'var(--purple)' },
    { label: 'Goals Defined', actions: vgDefs, color: 'var(--accent)' },
    { label: 'Verifications', actions: verifications, color: 'var(--green)' },
    { label: 'Edge Cases', actions: decompositions, color: 'var(--yellow-bright)' },
    { label: 'Test Generations', actions: testGens, color: 'var(--cyan)' },
  ];

  const hasSteps = stageGroups.some(g => g.actions.length > 0);
  if (hasSteps) {
    html += `<h2 style="font-size:14px;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.06em;margin:28px 0 14px 0;">Reasoning Steps</h2>`;
    html += `<div style="display:flex;flex-wrap:wrap;gap:16px;">`;

    for (const group of stageGroups) {
      if (!group.actions.length) continue;
      html += `<div class="funnel-breakdown-card" style="min-width:220px;">
        <h4 style="border-left:3px solid ${group.color};padding-left:8px;">${group.label}</h4>`;
      for (const a of group.actions) {
        const statusBadge = a.vg_result ? `<span class="badge badge-${a.vg_result.status}" style="font-size:8px;margin-left:6px;">${a.vg_result.status}</span>` :
          a.formalization ? `<span class="badge badge-${a.formalization.status}" style="font-size:8px;margin-left:6px;">${a.formalization.status}</span>` : '';
        html += `<div class="fb-row" style="cursor:pointer;" onclick="switchView('flow');selectAction(${a.id});document.querySelector('.action-card[data-action-id=&quot;${a.id}&quot;]')?.scrollIntoView({behavior:'smooth',block:'center'});">
          <span class="fb-icon" style="font-size:10px;color:var(--text-dim);">#${a.id}</span>
          <span class="fb-label" style="flex:1;font-size:11px;">${esc(a.label)}${statusBadge}</span>
          <span style="color:var(--accent);font-size:10px;">\u2192</span>
        </div>`;
      }
      html += `</div>`;
    }

    html += `</div>`;
  }

  el.innerHTML = html;
}

// ============================================================
// Policy rendering helpers
// ============================================================
function renderSelector(sel) {
  if (!sel || !Object.keys(sel).length) return '<span style="color:#64748b;font-size:10px;">all actions</span>';
  let html = '<div class="pc-selector-table">';
  for (const [k, v] of Object.entries(sel)) {
    if (Array.isArray(v)) {
      html += `<span class="pc-selector-chip"><span class="sc-key">${esc(k)}:</span> <span class="sc-val">${v.map(x => esc(x)).join(', ')}</span></span>`;
    } else {
      html += `<span class="pc-selector-chip"><span class="sc-key">${esc(k)}:</span> <span class="sc-val">${esc(String(v))}</span></span>`;
    }
  }
  html += '</div>';
  return html;
}

function highlightLTL(formula) {
  if (!formula) return '';
  // Temporal operators
  let html = esc(formula);
  // Order matters: longer tokens first
  const ops = [
    // Temporal operators — scoped variants first (longer match)
    [/\bP_target\b/g, '<span class="ltl-op">P<sub>target</sub></span>'],
    [/\bP_chain\b/g, '<span class="ltl-op">P<sub>chain</sub></span>'],
    [/\bH_target\b/g, '<span class="ltl-op">H<sub>target</sub></span>'],
    [/\bH_chain\b/g, '<span class="ltl-op">H<sub>chain</sub></span>'],
    [/\bS_last\b/g, '<span class="ltl-op">S<sub>last</sub></span>'],
    // Standard temporal operators
    [/\bG\b/g, '<span class="ltl-op">G</span>'],        // Globally (always)
    [/\bF\b/g, '<span class="ltl-op">F</span>'],        // Finally (eventually)
    [/\bX\b/g, '<span class="ltl-op">X</span>'],        // Next
    [/\bU\b/g, '<span class="ltl-op">U</span>'],        // Until
    [/\bP\b/g, '<span class="ltl-op">P</span>'],        // Previously (past)
    [/\bH\b/g, '<span class="ltl-op">H</span>'],        // Historically (past)
    [/\bS\b/g, '<span class="ltl-op">S</span>'],        // Since (past)
    // Logical connectives (Unicode)
    [/¬/g, '<span class="ltl-logic">\u00AC</span>'],
    [/∧/g, '<span class="ltl-logic">\u2227</span>'],
    [/∨/g, '<span class="ltl-logic">\u2228</span>'],
    [/\u2192/g, '<span class="ltl-logic">\u2192</span>'],
    [/↔/g, '<span class="ltl-logic">\u2194</span>'],
    // Set/quantifier operators
    [/∀/g, '<span class="ltl-logic">\u2200</span>'],
    [/∃!/g, '<span class="ltl-logic">\u2203!</span>'],
    [/∃/g, '<span class="ltl-logic">\u2203</span>'],
    [/∈/g, '<span class="ltl-logic">\u2208</span>'],
    [/≠/g, '<span class="ltl-logic">\u2260</span>'],
    [/∅/g, '<span class="ltl-logic">\u2205</span>'],
    // Parentheses
    [/\(/g, '<span class="ltl-paren">(</span>'],
    [/\)/g, '<span class="ltl-paren">)</span>'],
    [/\{/g, '<span class="ltl-paren">{</span>'],
    [/\}/g, '<span class="ltl-paren">}</span>'],
    [/\[/g, '<span class="ltl-paren">[</span>'],
    [/\]/g, '<span class="ltl-paren">]</span>'],
  ];
  for (const [re, rep] of ops) html = html.replace(re, rep);

  // Known action/artifact types as propositions
  const types = ['EditFile','ReadFile','ReadDocumentation','SearchCode','AnalyzeCode',
    'GitCommit','RunTests','DeleteFile','CreateFile','TypeCheck','Lint',
    'VerificationGoal','VerificationResult','IMLModel','Decomposition',
    'GeneratedTests','UserApproval','Formalize','Verify','DefineVG'];
  for (const t of types) {
    html = html.replace(new RegExp(`\\b${t}\\b`, 'g'), `<span class="ltl-prop">${t}</span>`);
  }

  // Known predicates/fields
  const preds = ['completed','failed','proved','sat','refuted','unknown',
    'gateway','action','high_stakes_path','start_event','end_event',
    'rationale','files_modified','target','inputs','outputs',
    'ancestors','derived_from','target_artifact_id'];
  for (const p of preds) {
    html = html.replace(new RegExp(`\\b${p}\\b`, 'g'), `<span class="ltl-field">${p}</span>`);
  }

  return html;
}

function renderPolicyDefinition(p) {
  let html = '<div class="pc-definition">';

  if (p.applies_when && Object.keys(p.applies_when).length) {
    html += `<div class="pc-def-section">
      <div class="pc-def-label">Scope</div>
      ${renderSelector(p.applies_when)}
    </div>`;
  }

  if (p.formula) {
    html += `<div class="pc-def-section">
      <div class="pc-def-label">Formula</div>
      <div class="pc-rule-block">${highlightLTL(p.formula)}</div>
    </div>`;
  }

  if (p.formal_src) {
    html += `<div class="pc-def-section">
      <div class="pc-def-label">IML Encoding</div>
      <div class="pc-rule-block clr-purple">${highlightIML(p.formal_src)}</div>
    </div>`;
  }

  html += '</div>';
  return html;
}

// ============================================================
// Policy Dashboard View
// ============================================================
function renderGradeView() {
  const el = document.getElementById('view-grade');
  if (!el) return;
  const g = window.__ponensGrade;
  if (!g) { el.innerHTML = '<div style="color:var(--text-secondary);padding:8px;">Grade is computed by the ponens CLI.</div>'; return; }
  const residuals = (traceData && traceData.residuals) || [];
  const sevColor = { critical: '#e5534b', high: '#e5534b', medium: '#e0a458', low: '#6ea8fe', info: 'var(--text-secondary)' };
  const gColor = g.overall >= 70 ? '#57ab5a' : g.overall >= 60 ? '#e0a458' : '#e5534b';
  let h = '<div style="max-width:900px;">';
  h += '<div style="display:flex;gap:20px;align-items:flex-start;">';
  h += '<div style="flex:none;width:110px;height:110px;border-radius:14px;border:1px solid var(--border);background:var(--bg-surface);display:flex;flex-direction:column;align-items:center;justify-content:center;">'
     + '<div style="font-size:44px;font-weight:800;color:' + gColor + ';">' + esc(g.grade) + '</div>'
     + '<div style="font-size:12px;color:var(--text-secondary);">' + g.overall + '/100</div></div>';
  h += '<div style="flex:1;min-width:0;display:flex;flex-direction:column;gap:10px;">';
  for (const d of (g.dimensions || [])) {
    const na = d.applicable === false, pct = Math.round((d.score || 0) * 100);
    h += '<div><div style="display:flex;gap:8px;font-size:13px;align-items:baseline;"><b>' + esc(d.name) + '</b>'
       + '<span style="margin-left:auto;color:var(--text-primary);">' + (na ? 'n/a' : pct + '%') + '</span>'
       + '<span style="color:var(--text-secondary);font-size:11px;">w' + d.weight + '</span></div>'
       + '<div style="height:6px;background:var(--border);border-radius:3px;overflow:hidden;margin:3px 0;"><div style="height:100%;width:' + (na ? 0 : pct) + '%;background:var(--accent);"></div></div>'
       + '<div style="color:var(--text-secondary);font-size:11.5px;">' + esc(d.note || '') + '</div></div>';
  }
  h += '</div></div>';
  h += '<div style="margin-top:22px;"><div style="font-weight:700;margin-bottom:8px;">Residual surface (declared gaps)</div>';
  if (!residuals.length) h += '<div style="color:var(--text-secondary);">No residuals declared - a trace with no declared gaps is suspicious, not clean.</div>';
  else for (const r of residuals) {
    h += '<div style="display:flex;gap:8px;align-items:baseline;padding:6px 0;border-bottom:1px solid var(--border);font-size:12.5px;">'
       + '<span style="font-size:10.5px;font-weight:700;text-transform:uppercase;color:' + (sevColor[r.severity] || 'var(--text-secondary)') + ';border:1px solid var(--border);border-radius:4px;padding:1px 6px;">' + esc(r.severity || 'info') + '</span>'
       + '<span style="font-family:ui-monospace,monospace;color:var(--accent);">' + esc(r.kind || '') + '</span>'
       + '<span>' + esc(r.statement || '') + '</span></div>';
  }
  h += '</div></div>';
  el.innerHTML = h;
}

// Goals view (§18): declared intent + acceptance, with resolved status when the trace is enriched.
function renderGoalsView() {
  const el = document.getElementById('view-goals');
  const goals = traceData?.goals || [];
  if (!goals.length) {
    el.innerHTML = '<p style="color:var(--text-muted);padding:32px;">No goals declared in this trace.</p>';
    return;
  }
  const norm = (s) => String(s || 'todo').toLowerCase().replace(/^accept/, '');
  const glyph = { done: '✓', doing: '◐', blocked: '✗', todo: '○' };
  let html = '<div class="goals-wrap">';
  for (const g of goals) {
    const acc = g.acceptance || [];
    const doneN = acc.filter((a) => norm(a.status) === 'done').length;
    const prog = (g.progress != null) ? g.progress : (acc.length ? doneN / acc.length : 0);
    const pct = Math.round(prog * 100);
    const gaps = g.open_gaps || 0;
    const coneN = Array.isArray(g.cone) ? g.cone.length : null;
    const accHtml = acc.map((a) => {
      const st = norm(a.status);
      return `<li class="goal-acc-item ga-${st}">`
        + `<span class="goal-acc-glyph">${glyph[st] || '○'}</span>`
        + `<span class="goal-acc-kind gk-${esc(a.kind)}">${esc(a.kind)}</span>`
        + `<span class="goal-acc-label">${esc(a.label || '')}</span>`
        + (a.evidence ? `<span class="goal-acc-ev" title="Resolved from ${esc(String(a.evidence))}">${esc(String(a.evidence))}</span>` : '')
        + `</li>`;
    }).join('');
    html += `<div class="goal-block">`
      + `<div class="goal-block-head">`
      + `<div class="goal-prog"><div class="goal-prog-bar" style="width:${pct}%"></div></div>`
      + `<div class="goal-prog-pct">${pct}%</div>`
      + `<div class="goal-block-text">`
      + `<div class="goal-block-intent">${esc(g.intent || '(untitled goal)')}</div>`
      + `<div class="goal-block-meta">${doneN}/${acc.length} done`
      + (gaps ? ` · <span class="goal-gaps-n">${gaps} open ${gaps === 1 ? 'gap' : 'gaps'}</span>` : '')
      + (coneN != null ? ` · ${coneN} steps` : '')
      + `</div>`
      + ((g.scope || []).length ? `<div class="goal-scopes">${g.scope.map((s) => `<span class="goal-scope-chip">${esc(s)}</span>`).join('')}</div>` : '')
      + `</div></div>`
      + `<ul class="goal-acc">${accHtml}</ul>`
      + `</div>`;
  }
  html += '</div>';
  el.innerHTML = html;
}

// Expand + scroll to a specific policy card in the policy dashboard (host embedding: select()).
function selectPolicy(policyId) {
  const card = document.querySelector(`.policy-card[data-policy-id="${policyId}"]`);
  if (!card) return;
  card.classList.add('expanded', 'highlight');
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => card.classList.remove('highlight'), 1500);
}

function renderPolicyView() {
  const el = document.getElementById('view-policy');
  const policies = traceData?.policies || [];
  const evals = traceData?.policy_evaluations || [];
  const props = traceData?.process_properties || [];

  // If no policies (v1.0), fall back to process_properties display
  if (!policies.length && !props.length) {
    el.innerHTML = '<p style="color:#64748b;padding:32px;">No policies or process properties in this trace.</p>';
    return;
  }

  // v1.0 fallback: render process_properties as a simple dashboard
  if (!policies.length && props.length) {
    const passed = props.filter(p => p.passed).length;
    const failed = props.length - passed;
    let html = `<h2 style="font-size:14px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:20px;">Process Properties</h2>`;
    html += `<div class="policy-summary-bar">
      <div class="policy-stat"><div class="ps-num" style="color:#f1f5f9;">${props.length}</div><div class="ps-label">Total</div></div>
      <div class="policy-stat"><div class="ps-num clr-green">${passed}</div><div class="ps-label">Passed</div></div>
      <div class="policy-stat"><div class="ps-num" style="color:${failed ? '#fca5a5' : '#64748b'};">${failed}</div><div class="ps-label">Failed</div></div>
    </div>`;
    for (const p of props) {
      html += `<div class="policy-card">
        <div class="pc-icon">${p.passed ? '\u2705' : '\u274C'}</div>
        <div class="pc-body">
          <div class="pc-name">${esc(p.name)}</div>
          <div class="pc-desc">${esc(PROP_DESCRIPTIONS[p.name] || '')}</div>
        </div>
        <span class="pc-status-badge ${p.passed ? 'passed' : 'failed'}">${p.passed ? 'passed' : 'failed'}</span>
      </div>`;
    }
    el.innerHTML = html;
    return;
  }

  // v1.1: full policy dashboard
  const evalMap = {};
  for (const e of evals) evalMap[e.policy_id] = e;

  const passed = evals.filter(e => e.status === 'passed').length;
  const failed = evals.filter(e => e.status === 'failed').length;
  const na = evals.filter(e => e.status === 'not_applicable').length;
  const unk = evals.filter(e => e.status === 'unknown').length;

  let html = `<h2 style="font-size:14px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:20px;">Policy Compliance Dashboard</h2>`;

  // Summary stats
  html += `<div class="policy-summary-bar">
    <div class="policy-stat"><div class="ps-num" style="color:#f1f5f9;">${policies.length}</div><div class="ps-label">Policies</div></div>
    <div class="policy-stat"><div class="ps-num clr-green">${passed}</div><div class="ps-label">Passed</div></div>
    <div class="policy-stat"><div class="ps-num" style="color:${failed ? '#fca5a5' : '#64748b'};">${failed}</div><div class="ps-label">Failed</div></div>
    <div class="policy-stat"><div class="ps-num" style="color:#94a3b8;">${na}</div><div class="ps-label">Not Applicable</div></div>
    ${unk ? `<div class="policy-stat"><div class="ps-num clr-yellow">${unk}</div><div class="ps-label">Unknown</div></div>` : ''}
  </div>`;

  // Group by severity
  const severityOrder = ['error', 'warning', 'info'];
  const severityColors = { error: '#ef4444', warning: '#f59e0b', info: '#3b82f6' };
  const severityIcons = { error: '\u{1F6E1}\uFE0F', warning: '\u{26A0}\uFE0F', info: '\u{2139}\uFE0F' };
  const severityLabels = { error: 'Critical', warning: 'Moderate', info: 'Informational' };

  for (const sev of severityOrder) {
    const group = policies.filter(p => p.severity === sev);
    if (!group.length) continue;

    html += `<div class="policy-group">
      <div class="policy-group-header">
        ${severityIcons[sev]} ${severityLabels[sev].toUpperCase()} <span style="color:#475569;font-weight:400;">(${group.length})</span>
      </div>`;

    for (const p of group) {
      const ev = evalMap[p.policy_id];
      const status = ev?.status || 'unknown';
      const statusIcon = status === 'passed' ? '\u2705' : status === 'failed' ? '\u274C' : status === 'not_applicable' ? '\u2796' : '\u2753';
      const hasDef = p.applies_when || p.formula || p.formal_src;

      html += `<div class="policy-card" data-policy-id="${esc(p.policy_id)}" onclick="this.classList.toggle('expanded')">
        <div class="pc-icon">${statusIcon}</div>
        <div class="pc-body">
          <div class="pc-name">${esc(p.name)}</div>
          ${p.description ? `<div class="pc-desc">${esc(p.description)}</div>` : ''}
          <div class="pc-meta">
            <span class="pc-tag scope">${esc(p.scope)}</span>
            <span class="pc-tag kind">${esc(p.kind)}</span>
          </div>
          ${ev?.note ? `<div class="pc-note">${esc(ev.note)}</div>` : ''}
          ${ev?.evidence_action_ids?.length ? `<div class="pc-evidence">Evidence: actions ${ev.evidence_action_ids.map(id => '#' + id).join(', ')}</div>` : ''}
          ${ev?.evidence_artifact_ids?.length ? `<div class="pc-evidence">Evidence: artifacts ${ev.evidence_artifact_ids.map(id => esc(id)).join(', ')}</div>` : ''}
          ${ev?.violating_action_ids?.length ? `<div class="pc-evidence clr-red">Violations: actions ${ev.violating_action_ids.map(id => '#' + id).join(', ')}</div>` : ''}
          ${ev?.violating_artifact_ids?.length ? `<div class="pc-evidence clr-red">Violations: artifacts ${ev.violating_artifact_ids.map(id => esc(id)).join(', ')}</div>` : ''}
          ${hasDef ? renderPolicyDefinition(p) : ''}
        </div>
        <span class="pc-status-badge ${status.replace(/ /g,'_')}">${esc(status)}</span>
        ${hasDef ? '<span class="pc-expand-icon">\u25B8</span>' : ''}
      </div>`;
    }
    html += `</div>`;
  }

  el.innerHTML = html;
}

// ============================================================
// PDF Report Generation
// ============================================================
function generateReport() {
  if (!traceData) {
    alert('No trace loaded.');
    return;
  }

  const d = traceData;
  const actions = d.actions || [];
  const artifacts = d.artifacts || [];
  const policies = d.policies || [];
  const evals = d.policy_evaluations || [];
  const props = d.process_properties || [];

  // Collect reasoning stats
  const formalizations = actions.filter(a => a.formalization);
  const vgDefs = actions.filter(a => a.vg_defined);
  const verifications = actions.filter(a => a.vg_result);
  const decompositions = actions.filter(a => a.decomposition);
  const testGens = actions.filter(a => a.generated_tests);
  const proved = verifications.filter(a => a.vg_result?.status === 'proved');
  const refuted = verifications.filter(a => a.vg_result?.status === 'refuted');
  const sat = verifications.filter(a => a.vg_result?.status === 'sat');
  const totalTests = testGens.reduce((s, a) => s + (a.generated_tests?.tests?.length || 0), 0);
  const totalRegions = decompositions.reduce((s, a) => s + (a.decomposition?.regions?.length || 0), 0);

  let totalPropsProved = 0;
  for (const a of proved) {
    const ps = a.vg_result?.result?.proved?.properties;
    totalPropsProved += ps ? ps.filter(p => p.status === 'proved').length : 1;
  }

  // Policy stats
  const evalMap = {};
  for (const e of evals) evalMap[e.policy_id] = e;
  const polPassed = evals.filter(e => e.status === 'passed').length;
  const polFailed = evals.filter(e => e.status === 'failed').length;
  const polNA = evals.filter(e => e.status === 'not_applicable').length;

  // Execution timing
  const reasoningActions = actions.filter(a => a.category === 'reasoning' && a.execution?.duration_ms);
  const totalMs = reasoningActions.reduce((s, a) => s + a.execution.duration_ms, 0);

  // Build report HTML
  const now = new Date().toISOString().split('T')[0];

  let html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Ponens Trace Report</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #0c2340; background: #fff; padding: 40px 50px; font-size: 11px; line-height: 1.5;
  }
  @page { margin: 30px 40px; size: A4; }

  .report-header {
    display: flex; align-items: flex-start; justify-content: space-between;
    border-bottom: 3px solid #0088b8; padding-bottom: 16px; margin-bottom: 24px;
  }
  .report-header h1 { font-size: 20px; color: #0c2340; font-weight: 700; }
  .report-header .subtitle { font-size: 11px; color: #3d5670; margin-top: 4px; }
  .report-header .meta { text-align: right; font-size: 10px; color: #6a7a8c; }
  .report-header .meta div { margin-bottom: 2px; }

  h2 {
    font-size: 14px; font-weight: 700; color: #0c2340;
    border-bottom: 1px solid #cdd2dc; padding-bottom: 4px; margin: 20px 0 10px 0;
  }
  h3 { font-size: 12px; font-weight: 600; color: #1e3a56; margin: 12px 0 6px 0; }

  .stats-grid {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 16px;
  }
  .stat-box {
    border: 1px solid #cdd2dc; border-radius: 6px; padding: 10px 14px; text-align: center;
  }
  .stat-box .num { font-size: 22px; font-weight: 700; }
  .stat-box .label { font-size: 9px; color: #6a7a8c; text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
  .stat-green { color: #0a7a4a; }
  .stat-red { color: #b82030; }
  .stat-blue { color: #0088b8; }
  .stat-gray { color: #6a7a8c; }

  table { width: 100%; border-collapse: collapse; margin: 8px 0 16px 0; font-size: 10px; }
  th {
    text-align: left; padding: 6px 8px; background: #eef1f5; color: #3d5670;
    font-size: 9px; text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid #cdd2dc;
  }
  td { padding: 5px 8px; border-bottom: 1px solid #eef1f5; vertical-align: top; }
  tr:hover { background: #f8f9fb; }

  .badge {
    display: inline-block; font-size: 8px; font-weight: 700; padding: 1px 6px;
    border-radius: 3px; text-transform: uppercase;
  }
  .badge-proved { background: #e6f5ee; color: #085a38; }
  .badge-refuted { background: #fde8ea; color: #8a1520; }
  .badge-sat { background: #e6f0fa; color: #084880; }
  .badge-pending { background: #faf3dc; color: #5a4508; }
  .badge-passed { background: #e6f5ee; color: #085a38; }
  .badge-failed { background: #fde8ea; color: #8a1520; }
  .badge-na { background: #eef1f5; color: #6a7a8c; }
  .badge-unknown { background: #faf3dc; color: #5a4508; }
  .badge-error { background: #fde8ea; color: #8a1520; }
  .badge-warning { background: #faf3dc; color: #5a4508; }
  .badge-info { background: #e6f0fa; color: #084880; }
  .badge-transparent { background: #e6f5ee; color: #085a38; }

  .code {
    font-family: 'SF Mono', 'Fira Code', monospace; font-size: 10px;
    background: #f4f6f9; border: 1px solid #e4e8ee; border-radius: 4px;
    padding: 6px 8px; white-space: pre-wrap; margin: 4px 0;
  }

  .action-row td:first-child { font-weight: 600; white-space: nowrap; }
  .section { page-break-inside: avoid; }
  .page-break { page-break-before: always; }

  .footer {
    margin-top: 30px; padding-top: 10px; border-top: 1px solid #cdd2dc;
    font-size: 9px; color: #6a7a8c; display: flex; justify-content: space-between;
  }
</style>
</head>
<body>

<div class="report-header">
  <div style="display:flex;align-items:flex-start;gap:12px;">
    <svg width="32" height="32" viewBox="0 0 24 24" style="flex:none;display:block;margin-top:2px;" aria-hidden="true"><defs><linearGradient id="pvm2" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#6ea8fe"/><stop offset="1" stop-color="#9d7bff"/></linearGradient></defs><circle cx="12" cy="6" r="3" fill="url(#pvm2)"/><circle cx="6" cy="17.5" r="3" fill="url(#pvm2)"/><circle cx="18" cy="17.5" r="3" fill="url(#pvm2)"/></svg>
    <div>
      <h1>Ponens Trace Report</h1>
      <div class="subtitle"><strong>Objective:</strong> ${esc(d.trigger?.description || 'Agent trace report')}</div>
    </div>
  </div>
  <div class="meta">
    <div><strong>Trace ID:</strong> ${esc(d.trace_id || 'N/A')}</div>
    <div><strong>Model:</strong> ${esc(d.model || 'N/A')}</div>
    <div><strong>Timestamp:</strong> ${esc(d.timestamp || 'N/A')}</div>
    ${d.spec_version ? `<div><strong>Spec:</strong> v${esc(d.spec_version)}</div>` : ''}
    <div><strong>Report generated:</strong> ${now}</div>
  </div>
</div>

<h2>Summary</h2>
<div class="stats-grid">
  <div class="stat-box"><div class="num stat-blue">${actions.length}</div><div class="label">Actions</div></div>
  <div class="stat-box"><div class="num stat-green">${totalPropsProved}</div><div class="label">Properties Proved</div></div>
  <div class="stat-box"><div class="num stat-blue">${totalRegions}</div><div class="label">Regions Decomposed</div></div>
  <div class="stat-box"><div class="num stat-blue">${totalTests}</div><div class="label">Tests Generated</div></div>
</div>

<div class="stats-grid">
  <div class="stat-box"><div class="num stat-green">${proved.length}</div><div class="label">Proofs</div></div>
  <div class="stat-box"><div class="num stat-red">${refuted.length}</div><div class="label">Refutations</div></div>
  <div class="stat-box"><div class="num stat-blue">${sat.length}</div><div class="label">Instances</div></div>
  <div class="stat-box"><div class="num stat-gray">${reasoningActions.length > 0 ? (totalMs / 1000).toFixed(1) + 's' : 'N/A'}</div><div class="label">Reasoning Time</div></div>
</div>

<h2>Action Trace</h2>
<table>
<thead><tr><th>#</th><th>Type</th><th>Label</th><th>Category</th><th>Rationale</th></tr></thead>
<tbody>`;

  for (const a of actions) {
    html += `<tr class="action-row">
      <td>${a.id}</td>
      <td>${esc(a.type)}</td>
      <td>${esc(a.label)}</td>
      <td>${esc(a.category)}</td>
      <td>${esc(a.rationale)}</td>
    </tr>`;
  }

  html += `</tbody></table>`;

  // Verification Goals
  const vgs = collectVGs();
  if (vgs.length) {
    html += `<h2 class="page-break">Verification Goals</h2>
    <table>
    <thead><tr><th>ID</th><th>Kind</th><th>Description</th><th>Status</th></tr></thead>
    <tbody>`;
    for (const vg of vgs) {
      const st = vg.status || 'pending';
      html += `<tr>
        <td>VG${vg.goal_id}</td>
        <td>${esc(vg.kind)}</td>
        <td>${esc(vg.description)}</td>
        <td><span class="badge badge-${st}">${st}</span></td>
      </tr>`;
    }
    html += `</tbody></table>`;

    // VG details
    for (const vg of vgs) {
      html += `<div class="section">
        <h3>VG${vg.goal_id}: ${esc(vg.description)}</h3>
        <div class="code">${esc(vg.src)}</div>`;
      if (vg.result?.proved?.properties) {
        html += `<table><thead><tr><th>Property</th><th>Status</th></tr></thead><tbody>`;
        for (const p of vg.result.proved.properties) {
          html += `<tr><td style="font-family:monospace;">${esc(p.name)}</td><td><span class="badge badge-${p.status}">${p.status}</span></td></tr>`;
        }
        html += `</tbody></table>`;
      }
      if (vg.result?.refuted) {
        html += `<h3 style="color:#b82030;">Counterexample</h3>
        <div class="code">${esc(vg.result.refuted.counterexample || JSON.stringify(vg.result.refuted))}</div>`;
      }
      if (vg.result?.sat) {
        html += `<h3 style="color:#0088b8;">Instance Found</h3>
        <div class="code">${esc(vg.result.sat.model?.src || '')}</div>`;
      }
      html += `</div>`;
    }
  }

  // Formalizations
  if (formalizations.length) {
    html += `<h2 class="page-break">Formalizations</h2>`;
    for (const a of formalizations) {
      const f = a.formalization;
      html += `<div class="section">
        <h3>${esc(a.label)} <span class="badge badge-${f.status}">${f.status}</span></h3>
        <div style="display:flex;gap:16px;">
          <div style="flex:1;"><strong>Source (${esc(f.src_lang)})</strong><div class="code">${esc(f.src_code)}</div></div>
          <div style="flex:1;"><strong>IML</strong><div class="code">${esc(f.iml_code)}</div></div>
        </div>
        ${f.symbols?.length ? `<div style="margin-top:4px;font-size:10px;color:#6a7a8c;">Symbols: <span style="font-family:monospace;">${f.symbols.join(', ')}</span></div>` : ''}
      </div>`;
    }
  }

  // Decompositions
  if (decompositions.length) {
    html += `<h2 class="page-break">Region Decompositions</h2>`;
    for (const a of decompositions) {
      const dec = a.decomposition;
      html += `<div class="section">
        <h3>${esc(dec.target_function)} — ${dec.regions.length} regions ${dec.complete ? '(complete)' : '(partial)'}</h3>
        <table><thead><tr><th>Region</th><th>Constraints</th><th>Invariant</th><th>Witness</th></tr></thead><tbody>`;
      dec.regions.forEach((r, idx) => {
        const wit = typeof r.model === 'object' ? Object.entries(r.model).map(([k,v]) => k+'='+v).join(', ') : String(r.model);
        html += `<tr>
          <td>R${idx+1}</td>
          <td style="font-family:monospace;font-size:9px;">${(r.constraints||[]).join(', ')}</td>
          <td style="font-family:monospace;">${esc(r.invariant)}</td>
          <td style="font-family:monospace;font-size:9px;">${esc(wit)}</td>
        </tr>`;
      });
      html += `</tbody></table></div>`;
    }
  }

  // Policies
  if (policies.length || props.length) {
    html += `<h2 class="page-break">Policy Compliance</h2>`;

    if (policies.length) {
      html += `<div class="stats-grid" style="grid-template-columns:repeat(3,1fr);">
        <div class="stat-box"><div class="num stat-green">${polPassed}</div><div class="label">Passed</div></div>
        <div class="stat-box"><div class="num stat-red">${polFailed}</div><div class="label">Failed</div></div>
        <div class="stat-box"><div class="num stat-gray">${polNA}</div><div class="label">N/A</div></div>
      </div>`;

      html += `<table><thead><tr><th>Policy</th><th>Severity</th><th>Status</th><th>Formula</th><th>Notes</th></tr></thead><tbody>`;
      for (const p of policies) {
        const ev = evalMap[p.policy_id] || {};
        const st = ev.status || 'unknown';
        const sevLabel = {error:'Critical',warning:'Moderate',info:'Info'}[p.severity] || p.severity;
        html += `<tr>
          <td><strong>${esc(p.name)}</strong><br><span style="font-size:9px;color:#6a7a8c;">${esc(p.description || '')}</span></td>
          <td><span class="badge badge-${p.severity}">${sevLabel}</span></td>
          <td><span class="badge badge-${st === 'not_applicable' ? 'na' : st}">${st}</span></td>
          <td style="font-family:monospace;font-size:9px;">${esc(p.formula || '')}</td>
          <td style="font-size:9px;">${esc(ev.note || '')}</td>
        </tr>`;
      }
      html += `</tbody></table>`;
    } else if (props.length) {
      html += `<table><thead><tr><th>Property</th><th>Status</th></tr></thead><tbody>`;
      for (const p of props) {
        html += `<tr>
          <td>${esc(p.name)}</td>
          <td><span class="badge badge-${p.passed ? 'passed' : 'failed'}">${p.passed ? 'passed' : 'failed'}</span></td>
        </tr>`;
      }
      html += `</tbody></table>`;
    }
  }

  // Outcome
  html += `<h2>Outcome</h2>
  <p><strong>${esc(d.outcome?.type || 'N/A')}</strong></p>
  <p>${esc(d.outcome?.summary || '')}</p>`;

  if (d.files_modified?.length) {
    html += `<h3>Files Modified</h3><ul>`;
    for (const f of d.files_modified) html += `<li style="font-family:monospace;">${esc(f)}</li>`;
    html += `</ul>`;
  }

  html += `
<div class="footer">
  <span>Generated by Ponens</span>
  <span>${esc(d.trace_id || '')} | ${now}</span>
</div>
</body></html>`;

  // Open in new window and trigger print
  const win = window.open('', '_blank');
  win.document.write(html);
  win.document.close();
  // Give it a moment to render, then print
  setTimeout(() => win.print(), 400);
}

// ============================================================
// Embedding API (PonensViewer)
// ============================================================
// Lets a host app (e.g. the CodeLogician desktop) mount the viewer into any element and drive it,
// instead of loading the standalone page. Usage from the host:
//   window.__ponensEmbedded = true;          // set BEFORE this script loads (skips demo auto-load)
//   host.innerHTML = <core/skeleton.html>;    // put the DOM skeleton in a container
//   <load core/viewer.css and this file>      // classic <script>, so these fns stay global
//   PonensViewer.mount(host, trace, { theme: 'dark' });
//   PonensViewer.switchView('policy'); PonensViewer.select(actionId);
window.PonensViewer = {
  mount: function (rootEl, trace, opts) {
    opts = opts || {};
    if (opts.theme) document.documentElement.setAttribute('data-theme', opts.theme);
    var sel = document.getElementById('demoSelector');
    if (sel) sel.style.display = 'none'; // a mounted trace is specific, not the demo gallery
    if (trace) loadTrace(trace);
    return window.PonensViewer;
  },
  loadTrace: function (t) { loadTrace(t); return this; },
  switchView: function (v) { switchView(v); return this; },
  select: function (id) {
    var av = document.querySelector('.top-view.active');
    var vid = av && av.id;
    if (vid === 'view-dag') selectDAGNode(id);
    else if (vid === 'view-policy') selectPolicy(id);
    else selectAction(id);
    return this;
  },
  openModal: function (kind, id) { openModal(kind, id); return this; },
  setTheme: function (t) { document.documentElement.setAttribute('data-theme', t); return this; },
  destroy: function (rootEl) { if (rootEl) rootEl.innerHTML = ''; },
};
