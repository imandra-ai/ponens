"""Local trace management commands (init, trigger, action, artifact, complete, check, status, view)."""

import argparse
import json
import os
import sys
import tempfile
import uuid
import webbrowser
import http.server
import threading
from datetime import datetime, timezone

from .policy_compiler import (
    tokenize, Parser, ParseError,
    check_policy as syntax_check_policy,
    Globally, Finally, Previously, Historically, Next,
    PTarget, PChain, SinceLast, Since, Until,
    Implies, And, Or, Not,
    Atom, AtomWithArgs, FieldNeEmpty, StartEvent, EndEvent,
    ForAll, Exists, ExistsUnique, FieldAccess, Compare, Count,
    RawStructural, FuncApp, SetLiteral, Ancestors,
    ACTION_TYPES, ARTIFACT_TYPES, PREDICATES,
    STRUCTURAL_POLICIES,
)
from . import goals as goalops


# ================================================================
# Trace I/O
# ================================================================

def _require_yaml():
    try:
        import yaml
        return yaml
    except ImportError:
        print("Error: YAML support needs PyYAML — `pip install pyyaml` (or `pip install ponens[yaml]`).",
              file=sys.stderr)
        sys.exit(1)


def _dump_yaml(trace):
    """YAML with block scalars for multiline strings (readable embedded code)."""
    yaml = _require_yaml()

    def _str_rep(dumper, data):
        style = '|' if '\n' in data else None
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style=style)

    yaml.SafeDumper.add_representer(str, _str_rep)
    return yaml.safe_dump(trace, sort_keys=False, allow_unicode=True, default_flow_style=False)


def load_trace(path):
    if not os.path.exists(path):
        print(f"Error: trace file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        text = f.read()
    if path.endswith((".yaml", ".yml")):
        yaml = _require_yaml()
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as e:
            print(f"Error: {path} is not valid YAML: {e}", file=sys.stderr)
            sys.exit(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(f"Error: {path} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def save_trace(path, trace):
    trace['timestamp'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    dir_name = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.json')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(trace, f, indent=2, ensure_ascii=False)
            f.write('\n')
        os.rename(tmp_path, path)
    except:
        os.unlink(tmp_path)
        raise


# ================================================================
# Trace Construction
# ================================================================

def create_empty_trace(model='example-model', assistant='ponens'):
    return {
        'trace_id': f'trace-{uuid.uuid4().hex[:12]}',
        'spec_version': '1.1',
        'assistant': assistant,
        'model': model,
        'timestamp': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'trigger': {},
        'actions': [],
        'outcome': {},
        'artifacts': [],
        'policies': [],
        'policy_evaluations': [],
        'residuals': [],
        'goals': [],
        'files_modified': [],
        'metrics': {},
    }


def next_action_id(trace):
    actions = trace.get('actions', [])
    if not actions:
        return 1
    return max(a['id'] for a in actions) + 1


def next_artifact_id(trace):
    arts = trace.get('artifacts', [])
    return f'a{len(arts) + 1}'


def get_action_target(action, trace):
    for ev in action.get('evidence', []):
        if ev.get('type') == 'FileRef':
            return ev.get('ref', '')
    req = action.get('request', {})
    if req.get('path'):
        return req['path']
    for out_id in action.get('outputs', []):
        for art in trace.get('artifacts', []):
            if art.get('artifact_id') == out_id or art.get('name') == out_id:
                return art.get('name', '')
    return ''


def get_target_lineage(action, trace):
    targets = set()
    direct_target = get_action_target(action, trace)
    if direct_target:
        targets.add(direct_target)
    for out_id in action.get('outputs', []) + action.get('inputs', []):
        ancestor_ids = get_ancestors(out_id, trace)
        ancestor_ids.add(out_id)
        for art in trace.get('artifacts', []):
            if art.get('artifact_id') in ancestor_ids:
                if art.get('name'):
                    targets.add(art['name'])
                pid = art.get('producer_action_id')
                if pid is not None:
                    for a in trace.get('actions', []):
                        if a['id'] == pid:
                            t = get_action_target(a, trace)
                            if t:
                                targets.add(t)
    return targets


def get_ancestors(artifact_id, trace, visited=None):
    if visited is None:
        visited = set()
    if artifact_id in visited:
        return set()
    visited.add(artifact_id)
    result = set()
    for art in trace.get('artifacts', []):
        if art['artifact_id'] == artifact_id:
            for parent_id in art.get('derived_from', []):
                result.add(parent_id)
                result |= get_ancestors(parent_id, trace, visited)
    return result


def in_dependency_chain(earlier_action, current_action, trace):
    current_inputs = current_action.get('outputs', []) + current_action.get('inputs', [])
    all_ancestors = set()
    for aid in current_inputs:
        all_ancestors.add(aid)
        all_ancestors |= get_ancestors(aid, trace)
    earlier_outputs = set(earlier_action.get('outputs', []))
    return bool(all_ancestors & earlier_outputs)


# ================================================================
# Runtime Policy Evaluator
# ================================================================

_SEVERITY_RANK = {'info': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}


def _field_value(node, ctx):
    """Resolve a comparison operand to a concrete value."""
    if isinstance(node, FieldAccess):
        obj = (ctx or {}).get(node.var)
        return obj.get(node.field) if isinstance(obj, dict) else None
    if isinstance(node, Atom):
        return node.name
    return None


def _eval_compare(node, ctx):
    left = _field_value(node.left, ctx)
    right = node.right.name if isinstance(node.right, Atom) else None
    op = node.op

    if right == 'EMPTY':
        empty = left in (None, '', [], {}) or (isinstance(left, str) and not left.strip())
        return empty if op == '=' else (not empty)

    lval = left.lower() if isinstance(left, str) else left
    rval = right.lower() if isinstance(right, str) else right
    if op == '=':
        return lval == rval
    if op == '!=':
        return lval != rval
    # ordered comparison (severity ranking)
    lr, rr = _SEVERITY_RANK.get(lval), _SEVERITY_RANK.get(rval)
    if lr is None or rr is None:
        return False
    return {'>=': lr >= rr, '>': lr > rr, '<=': lr <= rr, '<': lr < rr}.get(op, False)


# The full v1.4-schema formal-reasoning type names ← their back-compat aliases.
# Atom matching compares canonical forms so a policy written with either spelling
# (e.g. `Decomposition` or `StateSpaceAnalysisResult`) matches either artifact.
TYPE_SYNONYMS = {
    'DefineVerificationGoal': 'DefineVG',
    'StateSpaceAnalysis': 'Decompose',
    'StateSpaceAnalysisResult': 'Decomposition',
    'FormalModel': 'IMLModel',
}


def _canon_type(name):
    return TYPE_SYNONYMS.get(name, name)


def evaluate_formula(node, trace, ctx=None):
    if isinstance(node, (ForAll, Exists, ExistsUnique)):
        coll = trace.get(node.set_name, []) if node.set_name else []
        base = dict(ctx) if ctx else {}
        results = [evaluate_formula(node.body, trace, {**base, node.var: item}) for item in coll]
        if isinstance(node, ForAll):
            return all(results)
        if isinstance(node, ExistsUnique):
            return sum(1 for r in results if r) == 1
        return any(results)

    if isinstance(node, Count):
        c = sum(1 for a in trace.get('actions', [])
                if evaluate_formula(node.body, trace, {'action': a}))
        n, op = node.n, node.op
        return {'>=': c >= n, '<=': c <= n, '>': c > n, '<': c < n,
                '=': c == n, '!=': c != n}[op]

    if isinstance(node, Compare):
        return _eval_compare(node, ctx)

    if isinstance(node, FieldAccess):
        obj = (ctx or {}).get(node.var)
        return bool(obj.get(node.field)) if isinstance(obj, dict) else False

    if isinstance(node, Globally):
        return all(evaluate_formula(node.body, trace, {'action': a}) for a in trace['actions'])

    if isinstance(node, Finally):
        return any(evaluate_formula(node.body, trace, {'action': a}) for a in trace['actions'])

    if isinstance(node, Previously):
        if not ctx:
            return False
        current = ctx['action']
        return any(
            evaluate_formula(node.body, trace, {'action': b})
            for b in trace['actions'] if b['id'] < current['id']
        )

    if isinstance(node, Historically):
        if not ctx:
            return True
        current = ctx['action']
        return all(
            evaluate_formula(node.body, trace, {'action': b})
            for b in trace['actions'] if b['id'] < current['id']
        )

    if isinstance(node, PTarget):
        if not ctx:
            return False
        current = ctx['action']
        current_targets = get_target_lineage(current, trace)
        if not current_targets:
            return False
        return any(
            evaluate_formula(node.body, trace, {'action': b})
            for b in trace['actions']
            if b['id'] < current['id'] and (
                get_action_target(b, trace) in current_targets or
                bool(get_target_lineage(b, trace) & current_targets)
            )
        )

    if isinstance(node, PChain):
        if not ctx:
            return False
        current = ctx['action']
        return any(
            evaluate_formula(node.body, trace, {'action': b})
            for b in trace['actions']
            if b['id'] < current['id'] and in_dependency_chain(b, current, trace)
        )

    if isinstance(node, SinceLast):
        if not ctx:
            return False
        current = ctx['action']
        before = [b for b in trace['actions'] if b['id'] < current['id']]
        boundary = 0
        for b in before:
            if evaluate_formula(node.right, trace, {'action': b}):
                boundary = max(boundary, b['id'])
        return any(
            evaluate_formula(node.left, trace, {'action': b})
            for b in before if b['id'] > boundary
        )

    if isinstance(node, Next):
        # X φ: φ holds at the immediately following action (strong next: false at the end)
        if not ctx:
            return False
        seq = sorted(trace.get('actions', []), key=lambda a: a['id'])
        nxt = next((a for a in seq if a['id'] > ctx['action']['id']), None)
        return False if nxt is None else evaluate_formula(node.body, trace, {**ctx, 'action': nxt})

    if isinstance(node, Until):
        # φ U ψ: ψ holds at some position k ≥ here, and φ holds at every position from here to k-1
        seq = sorted(trace.get('actions', []), key=lambda a: a['id'])
        start = 0 if not ctx else next((i for i, a in enumerate(seq) if a['id'] == ctx['action']['id']), None)
        if start is None:
            return False
        for k in range(start, len(seq)):
            if evaluate_formula(node.right, trace, {**(ctx or {}), 'action': seq[k]}):
                if all(evaluate_formula(node.left, trace, {**(ctx or {}), 'action': seq[j]})
                       for j in range(start, k)):
                    return True
        return False

    if isinstance(node, Since):
        # φ S ψ: ψ held at some position k ≤ here, and φ held at every position from k+1 to here
        seq = sorted(trace.get('actions', []), key=lambda a: a['id'])
        end = (len(seq) - 1) if not ctx else next((i for i, a in enumerate(seq) if a['id'] == ctx['action']['id']), None)
        if end is None or end < 0:
            return False
        for k in range(end, -1, -1):
            if evaluate_formula(node.right, trace, {**(ctx or {}), 'action': seq[k]}):
                if all(evaluate_formula(node.left, trace, {**(ctx or {}), 'action': seq[j]})
                       for j in range(k + 1, end + 1)):
                    return True
        return False

    if isinstance(node, Implies):
        left = evaluate_formula(node.left, trace, ctx)
        if not left:
            return True
        return evaluate_formula(node.right, trace, ctx)

    if isinstance(node, And):
        return evaluate_formula(node.left, trace, ctx) and evaluate_formula(node.right, trace, ctx)

    if isinstance(node, Or):
        return evaluate_formula(node.left, trace, ctx) or evaluate_formula(node.right, trace, ctx)

    if isinstance(node, Not):
        return not evaluate_formula(node.body, trace, ctx)

    if isinstance(node, Atom):
        if not ctx:
            return False
        a = ctx['action']
        name = node.name
        if name in ACTION_TYPES:
            return _canon_type(a.get('type')) == _canon_type(name)
        if name in ARTIFACT_TYPES:
            if _canon_type(a.get('type')) == _canon_type(name):
                return True
            for out_id in a.get('outputs', []):
                for art in trace.get('artifacts', []):
                    if (art.get('artifact_id') == out_id or art.get('name') == out_id) and _canon_type(art.get('artifact_type')) == _canon_type(name):
                        return True
            return False
        if name in ('gateway', 'reasoning', 'activity'):
            return a.get('category') == name
        if name == 'action':
            return True
        if name == 'completed':
            return a.get('result_summary', '').lower().find('pass') >= 0 or a.get('result_summary', '').lower().find('completed') >= 0
        if name == 'failed':
            return a.get('result_summary', '').lower().find('fail') >= 0
        if name == 'proved':
            vr = a.get('vg_result', {})
            return vr.get('status') == 'proved'
        if name == 'refuted':
            vr = a.get('vg_result', {})
            return vr.get('status') == 'refuted'
        if name == 'sat':
            vr = a.get('vg_result', {})
            return vr.get('status') == 'sat'
        if name in ('passed', 'partial'):
            # Conformance (model<->code fidelity) status.
            return a.get('conformance', {}).get('status') == name
        if name in ('matched', 'mismatched'):
            # Co-simulation (model-vs-implementation replay) status.
            return a.get('cosimulation', {}).get('status') == name
        if name == 'high_stakes_path':
            # "Where it makes sense": data-driven high-stakes surface. A producer (e.g. a
            # formalization-target scan) sets trace['high_stakes_paths'] to the path fragments that
            # warrant formal methods; matching is by substring. Falls back to the demo defaults so
            # existing traces without the field keep working.
            target = get_action_target(a, trace)
            stakes = trace.get('high_stakes_paths') or ['payments/', 'risk/', 'stripe_payment_flow']
            return any(p in target for p in stakes)
        # A CamelCase atom names a specific action/artifact type. If it matched no
        # known type above it simply does not hold here — exact-match semantics,
        # matching the browser evaluator. Only lowercase atoms fall through to the
        # keyword substring match (custom domain predicates against action text).
        if name[:1].isupper():
            return False
        keyword = name.replace('_', ' ').lower()
        text = f"{a.get('type','')} {a.get('label','')} {a.get('detail','')} {a.get('rationale','')} {a.get('result_summary','')}".lower()
        if keyword in text:
            return True
        return False

    if isinstance(node, AtomWithArgs):
        if not ctx:
            return False
        a = ctx['action']
        type_match = _canon_type(a.get('type')) == _canon_type(node.name)
        if not type_match:
            for out_id in a.get('outputs', []):
                for art in trace.get('artifacts', []):
                    if (art.get('artifact_id') == out_id or art.get('name') == out_id) and _canon_type(art.get('artifact_type')) == _canon_type(node.name):
                        type_match = True
                        break
                if type_match:
                    break
        if not type_match:
            return False
        if node.args:
            vr = a.get('vg_result', {})
            for arg in node.args:
                if isinstance(arg, Atom):
                    if vr.get('status') == arg.name:
                        return True
                    for out_id in a.get('outputs', []):
                        for art in trace.get('artifacts', []):
                            if (art.get('artifact_id') == out_id or art.get('name') == out_id):
                                payload = art.get('payload', {})
                                if payload.get('status') == arg.name:
                                    return True
                elif isinstance(arg, Or):
                    if evaluate_formula(arg, trace, ctx):
                        return True
                elif evaluate_formula(arg, trace, ctx):
                    return True
            return False
        return True

    if isinstance(node, FieldNeEmpty):
        if not ctx:
            return False
        val = ctx['action'].get(node.field, '')
        return isinstance(val, str) and len(val) > 0

    if isinstance(node, StartEvent):
        trigger = trace.get('trigger', {})
        return trigger.get('type') in ('TaskReceived', 'TriggeredByEvent')

    if isinstance(node, EndEvent):
        outcome = trace.get('outcome', {})
        return outcome.get('type') in ('ProcessCompleted', 'ProcessAborted', 'ProcessInterrupted')

    if isinstance(node, RawStructural):
        return evaluate_structural(node.policy_name, trace)

    if isinstance(node, FuncApp):
        if not ctx:
            return False
        a = ctx['action']
        if node.func == 'ref_model':
            ref_id = node.arg
            req = a.get('request', {})
            if req.get('reference_model_id') == ref_id:
                return True
            for p in trace.get('policies', []):
                if p.get('reference_model_id') == ref_id:
                    return True
            return False
        keyword = node.func.replace('_', ' ').lower()
        text = f"{a.get('type','')} {a.get('label','')} {a.get('detail','')}".lower()
        return keyword in text

    return True


def evaluate_structural(policy_name, trace):
    if policy_name == 'data_flow_integrity':
        actions = sorted(trace.get('actions', []), key=lambda a: a['id'])
        output_map = {}
        for a in actions:
            outs = a.get('_original_outputs', a.get('outputs', []))
            for o in outs:
                output_map[o] = a['id']
        for art in trace.get('artifacts', []):
            pid = art.get('producer_action_id')
            if pid is not None:
                output_map[art['artifact_id']] = pid
        for a in actions:
            inputs = a.get('_original_inputs', a.get('inputs', []))
            for inp in inputs:
                if inp not in output_map:
                    return False
                if output_map[inp] >= a['id']:
                    return False
        return True

    if policy_name == 'goals_reference_valid_artifacts':
        artifacts = trace.get('artifacts', [])
        iml_ids = {a['artifact_id'] for a in artifacts if a.get('artifact_type') == 'IMLModel'}
        for art in artifacts:
            if art.get('artifact_type') == 'VerificationGoal':
                payload = art.get('payload', {})
                target = payload.get('target_artifact_id')
                if target and target not in iml_ids:
                    return False
        return True

    if policy_name == 'files_modified_consistent':
        actions = trace.get('actions', [])
        code_types = {'EditFile', 'CreateFile', 'DeleteFile'}
        actual = set()
        for a in actions:
            if a.get('type') in code_types:
                for ev in a.get('evidence', []):
                    if ev.get('type') == 'FileRef':
                        actual.add(ev['ref'])
        declared = set(trace.get('files_modified', []))
        return actual == declared

    if policy_name == 'generated_tests_require_decomposition':
        artifacts = trace.get('artifacts', [])
        for art in artifacts:
            if art.get('artifact_type') == 'GeneratedTests':
                ancestors = get_ancestors(art['artifact_id'], trace)
                has_decomp = any(
                    a.get('artifact_type') in ('Decomposition', 'Decomposition_Art')
                    for a in artifacts if a['artifact_id'] in ancestors
                )
                if not has_decomp:
                    return False
        return True

    # --- residual surface policies (quantify over trace.residuals — Trace Spec §13) ---
    residuals = trace.get('residuals', [])
    sev_rank = {'info': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}

    if policy_name == 'no_open_critical_residuals':
        # ¬∃ r ∈ residuals . r.severity = Critical ∧ r.status = Open
        for r in residuals:
            if r.get('severity') == 'critical' and r.get('status', 'open') == 'open':
                return False
        return True

    if policy_name == 'high_severity_residuals_acknowledged_before_commit':
        # G(GitCommit → ∀ r ∈ residuals . r.severity ≥ High → r.status ≠ Open)
        if not any(a.get('type') == 'GitCommit' for a in trace.get('actions', [])):
            return True  # vacuously satisfied: no commit
        for r in residuals:
            if sev_rank.get(r.get('severity'), 0) >= sev_rank['high'] and r.get('status', 'open') == 'open':
                return False
        return True

    if policy_name == 'unverified_residuals_have_suggested_check':
        # ∀ r ∈ residuals . r.kind = Unverified → r.suggested_check ≠ ∅
        for r in residuals:
            if r.get('kind') == 'unverified':
                sc = r.get('suggested_check')
                if not (isinstance(sc, str) and sc.strip()):
                    return False
        return True

    if policy_name == 'assumptions_are_located':
        # ∀ r ∈ residuals . r.kind = Assumption → (r.target ≠ ∅ ∨ r.related_artifact_ids ≠ ∅)
        for r in residuals:
            if r.get('kind') == 'assumption':
                if not (r.get('target') or r.get('related_artifact_ids')):
                    return False
        return True

    return True


def _temporal_witnesses(ast, trace):
    """Best-effort per-action evidence for the common `G(...)` shapes:
      - G(ante → cons): the actions where the trigger fires, split into satisfying (evidence) and
        breaking (violating);
      - G(¬x): actions where x holds are violating;
      - G(x): actions split by whether x holds.
    Returns (evidence_action_ids, violating_action_ids). Empty for shapes we don't decompose."""
    ev, vi = [], []
    if not isinstance(ast, Globally):
        return ev, vi
    body = ast.body
    for a in sorted(trace.get('actions', []), key=lambda x: x['id']):
        ctx = {'action': a}
        try:
            if isinstance(body, Implies):
                if not evaluate_formula(body.left, trace, ctx):
                    continue  # trigger did not fire here — not relevant
                (ev if evaluate_formula(body.right, trace, ctx) else vi).append(a['id'])
            elif isinstance(body, Not):
                if evaluate_formula(body.body, trace, ctx):
                    vi.append(a['id'])
            else:
                (ev if evaluate_formula(body, trace, ctx) else vi).append(a['id'])
        except Exception:
            continue
    return ev, vi


def _structural_witnesses(name, trace):
    """Evidence for structural policies. For `data_flow_integrity`: actions whose inputs all resolve
    to a producer are evidence; an action with a dangling input is violating."""
    ev, vi = [], []
    if name == 'data_flow_integrity':
        actions = sorted(trace.get('actions', []), key=lambda a: a['id'])
        output_map = {}
        for a in actions:
            for o in a.get('_original_outputs', a.get('outputs', [])):
                output_map[o] = a['id']
        for art in trace.get('artifacts', []):
            if art.get('producer_action_id') is not None:
                output_map[art['artifact_id']] = art['producer_action_id']
        for a in actions:
            inputs = a.get('_original_inputs', a.get('inputs', []))
            if not inputs:
                continue
            (vi if any(inp not in output_map for inp in inputs) else ev).append(a['id'])
    return ev, vi


def evaluate_policy_full(policy, trace):
    """Like `evaluate_policy`, plus best-effort evidence: the action ids that support the pass
    (`evidence`) or break it (`violating`). Returns (status, note, evidence_ids, violating_ids)."""
    formula_str = policy.get('formula', '')
    name = policy.get('name', '')
    if not formula_str:
        return 'unknown', 'No formula defined', [], []
    if name in STRUCTURAL_POLICIES:
        result = evaluate_structural(name, trace)
        ev, vi = _structural_witnesses(name, trace)
        return ('passed' if result else 'failed'), None, ev, vi
    try:
        ast = Parser(tokenize(formula_str), formula_str, name).parse()
    except Exception as e:
        return 'unknown', f'Parse error: {e}', [], []
    if isinstance(ast, RawStructural):
        return 'unknown', 'Formula too complex for runtime evaluation', [], []
    try:
        result = evaluate_formula(ast, trace)
        ev, vi = _temporal_witnesses(ast, trace)
        return ('passed' if result else 'failed'), None, ev, vi
    except Exception as e:
        return 'unknown', f'Evaluation error: {e}', [], []


def evaluate_policy(policy, trace):
    """(status, note) — the compliance verdict. See `evaluate_policy_full` for evidence."""
    status, note, _ev, _vi = evaluate_policy_full(policy, trace)
    return status, note


# ================================================================
# Normalizer
# ================================================================

def normalize_trace(trace):
    if not trace.get('artifacts'):
        return
    art_map = {a['artifact_id']: a for a in trace['artifacts']}
    for action in trace.get('actions', []):
        for out_id in action.get('outputs', []):
            art = art_map.get(out_id)
            if not art or 'payload' not in art:
                continue
            at = art['artifact_type']
            if at in ('IMLModel', 'FormalModel') and 'iml_code' in art['payload']:
                action['formalization'] = art['payload']
            elif at in ('Formalization', 'FormalModel'):
                action['formalization'] = art['payload']
            elif at == 'VerificationGoal':
                action['vg_defined'] = art['payload']
            elif at == 'VerificationResult':
                action['vg_result'] = art['payload']
            elif at in ('Decomposition', 'StateSpaceAnalysisResult'):
                action['decomposition'] = art['payload']
            elif at == 'ConformanceResult':
                action['conformance'] = art['payload']
            elif at == 'CoSimulationResult':
                action['cosimulation'] = art['payload']
            elif at == 'GeneratedTests':
                action['generated_tests'] = art['payload']


# ================================================================
# Commands
# ================================================================

def cmd_init(args):
    if os.path.exists(args.trace_file):
        print(f"Error: {args.trace_file} already exists. Use a different name or delete it.", file=sys.stderr)
        return 1
    trace = create_empty_trace(model=args.model, assistant=args.assistant)
    save_trace(args.trace_file, trace)
    print(f"Created trace: {trace['trace_id']}")
    print(f"  File: {args.trace_file}")
    return 0


def cmd_trigger(args):
    trace = load_trace(args.trace_file)
    trace['trigger'] = {
        'type': args.type,
        'description': args.description,
    }
    if args.from_user:
        trace['trigger']['from_user'] = args.from_user
    save_trace(args.trace_file, trace)
    print(f"Trigger set: {args.type} — {args.description}")
    return 0


def cmd_action(args):
    trace = load_trace(args.trace_file)
    action_id = next_action_id(trace)
    action = {
        'id': action_id,
        'category': args.category,
        'type': args.type,
        'label': args.label,
        'rationale': args.rationale,
    }
    if args.inputs:
        action['inputs'] = [x.strip() for x in args.inputs.split(',')]
    else:
        action['inputs'] = []
    if args.outputs:
        action['outputs'] = [x.strip() for x in args.outputs.split(',')]
    else:
        action['outputs'] = []
    if args.detail:
        action['detail'] = args.detail
    if args.result_summary:
        action['result_summary'] = args.result_summary
    if args.evidence:
        action['evidence'] = [{'type': 'FileRef', 'ref': args.evidence}]
    trace['actions'].append(action)
    save_trace(args.trace_file, trace)
    print(f"Action #{action_id}: {args.type} — {args.label}")
    return 0


def cmd_artifact(args):
    trace = load_trace(args.trace_file)
    artifact = {
        'artifact_id': args.id or next_artifact_id(trace),
        'artifact_type': args.type,
        'name': args.name,
    }
    if args.derived_from:
        artifact['derived_from'] = [x.strip() for x in args.derived_from.split(',')]
    if args.producer_action_id:
        artifact['producer_action_id'] = args.producer_action_id
    if args.format:
        artifact['format'] = args.format
    if args.summary:
        artifact['summary'] = args.summary
    trace['artifacts'].append(artifact)
    save_trace(args.trace_file, trace)
    print(f"Artifact: {artifact['artifact_id']} ({args.type}) — {args.name}")
    return 0


def cmd_complete(args):
    trace = load_trace(args.trace_file)
    trace['outcome'] = {
        'type': 'ProcessCompleted',
        'summary': args.summary or '',
    }
    trace['metrics'] = {
        'total_actions': len(trace.get('actions', [])),
    }
    save_trace(args.trace_file, trace)
    print(f"Trace completed: {args.summary or '(no summary)'}")
    return 0


RESIDUAL_KINDS = {'assumption', 'unverified', 'out_of_scope', 'limitation', 'open_question'}
RESIDUAL_SEVERITIES = {'info', 'low', 'medium', 'high', 'critical'}
RESIDUAL_STATUSES = {'open', 'acknowledged', 'addressed', 'waived'}
META_SOURCES = {'plan_declared', 'turn_segmented', 'intent_inferred', 'curated'}
META_STATUSES = {'completed', 'partial', 'abandoned'}


def validate_trace(trace):
    """Structural validation of a trace. Returns (errors, warnings).

    Errors are malformations that make the trace unsound (wrong types, missing ids,
    invalid enums). Warnings are incompleteness (no trigger/outcome/rationale) — fine
    while a trace is being authored. This is a structural check, not full JSON-Schema
    validation (the formal schema lives in spec/schema)."""
    errors, warnings = [], []
    if not isinstance(trace, dict):
        return ["trace is not a JSON object"], []

    if not (isinstance(trace.get('trace_id'), str) and trace.get('trace_id')):
        errors.append("missing or non-string 'trace_id'")

    actions = trace.get('actions', [])
    if not isinstance(actions, list):
        errors.append("'actions' must be a list")
        actions = []
    artifacts = trace.get('artifacts', [])
    if not isinstance(artifacts, list):
        errors.append("'artifacts' must be a list")
        artifacts = []

    seen = set()
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            errors.append(f"action #{i} is not an object")
            continue
        aid = a.get('id')
        if not isinstance(aid, int):
            errors.append(f"action #{i} has missing/non-integer 'id'")
        elif aid in seen:
            errors.append(f"duplicate action id {aid}")
        else:
            seen.add(aid)
        if not (isinstance(a.get('type'), str) and a.get('type')):
            errors.append(f"action {aid}: missing 'type'")
        if not a.get('rationale'):
            warnings.append(f"action {aid}: no rationale")

    for i, art in enumerate(artifacts):
        if not isinstance(art, dict):
            errors.append(f"artifact #{i} is not an object")
            continue
        if not art.get('artifact_id'):
            errors.append(f"artifact #{i} missing 'artifact_id'")
        if not art.get('artifact_type'):
            errors.append(f"artifact {art.get('artifact_id', '?')}: missing 'artifact_type'")

    if not (trace.get('trigger') or {}).get('type'):
        warnings.append("trigger has no 'type' (trace may be incomplete)")
    if not (trace.get('outcome') or {}).get('type'):
        warnings.append("outcome has no 'type' (trace may be incomplete)")

    for i, r in enumerate(trace.get('residuals', []) or []):
        if not isinstance(r, dict):
            errors.append(f"residual #{i} is not an object")
            continue
        rid = r.get('residual_id', f'#{i}')
        if r.get('kind') and r['kind'] not in RESIDUAL_KINDS:
            errors.append(f"residual {rid}: invalid kind '{r['kind']}'")
        if r.get('severity') and r['severity'] not in RESIDUAL_SEVERITIES:
            errors.append(f"residual {rid}: invalid severity '{r['severity']}'")
        if r.get('status') and r['status'] not in RESIDUAL_STATUSES:
            errors.append(f"residual {rid}: invalid status '{r['status']}'")

    for i, p in enumerate(trace.get('policies', []) or []):
        if not isinstance(p, dict):
            errors.append(f"policy #{i} is not an object")
            continue
        if not (p.get('name') or p.get('policy_id')):
            errors.append(f"policy #{i}: missing 'name'/'policy_id'")
        if not p.get('formula'):
            warnings.append(f"policy {p.get('name', i)}: no formula")

    # Meta-action overlay (§8.4): well-formed, ids resolve, no action in two
    # meta-actions, and the meta_action_id back-references stay consistent.
    metas = trace.get('meta_actions', []) or []
    meta_ids, claimed = set(), {}
    for i, m in enumerate(metas):
        if not isinstance(m, dict):
            errors.append(f"meta_action #{i} is not an object")
            continue
        mid = m.get('id')
        if not (isinstance(mid, str) and mid):
            errors.append(f"meta_action #{i}: missing/non-string 'id'")
        elif mid in meta_ids:
            errors.append(f"duplicate meta_action id '{mid}'")
        else:
            meta_ids.add(mid)
        if m.get('source') and m['source'] not in META_SOURCES:
            errors.append(f"meta_action {mid}: invalid source '{m['source']}'")
        if m.get('status') and m['status'] not in META_STATUSES:
            errors.append(f"meta_action {mid}: invalid status '{m['status']}'")
        member_ids = m.get('action_ids', [])
        if not isinstance(member_ids, list):
            errors.append(f"meta_action {mid}: 'action_ids' must be a list")
            member_ids = []
        for aid in member_ids:
            if aid not in seen:
                errors.append(f"meta_action {mid}: action_id {aid} does not exist")
            elif aid in claimed:
                errors.append(f"action {aid} is in two meta-actions ({claimed[aid]} and {mid})")
            else:
                claimed[aid] = mid
        if member_ids and list(member_ids) != sorted(member_ids):
            warnings.append(f"meta_action {mid}: action_ids are not in timeline order")
    for m in metas:
        if isinstance(m, dict) and m.get('parent_id') and m['parent_id'] not in meta_ids:
            errors.append(f"meta_action {m.get('id')}: parent_id '{m['parent_id']}' does not exist")
    for a in actions:
        if not isinstance(a, dict):
            continue
        mref = a.get('meta_action_id')
        if mref is None:
            continue
        if mref not in meta_ids:
            errors.append(f"action {a.get('id')}: meta_action_id '{mref}' does not exist")
        elif claimed.get(a.get('id')) != mref:
            errors.append(f"action {a.get('id')}: meta_action_id '{mref}' disagrees with membership")

    return errors, warnings


_VALID_VERDICTS = {'proved', 'refuted', 'unknown'}
# Producing/reasoning actions the exporter groups into phase meta-actions (§8.4).
_GROUPED_ACTION_TYPES = {
    'Verify', 'EditFile', 'GenerateTests', 'StateSpaceAnalysis', 'ConformanceCheck', 'Decompose',
}


def soundness_errors(trace, strict=False):
    """Deeper *semantic* invariants beyond structure (validate_trace) — the checks that catch a
    mis-generated trace even when it is structurally well-typed:

      - reference resolution: every derived_from / input / output / producer / related / produced id
        resolves to a real artifact or action;
      - data-flow ordering: every consumed input was produced by an EARLIER action (no cycles,
        nothing consumed-but-never-produced);
      - verification lineage: VerificationResult -> VerificationGoal -> IMLModel, valid status;
      - enrich() and grade_trace() run without raising on this trace.

    With strict=True it also enforces the exporter convention that every reasoning/change/test
    action is grouped into a phase meta-action (§8.4). Returns a list of error strings (empty ==
    sound). Note: whether a refuted verdict is recorded by a residual is intentionally NOT checked
    here -- a curated trace may resolve a refutation later -- it is asserted on fresh export output
    by the exporter's own unit tests."""
    import copy
    errs = []
    actions = trace.get('actions', []) or []
    artifacts = trace.get('artifacts', []) or []
    art_by_id = {a.get('artifact_id'): a for a in artifacts if isinstance(a, dict)}
    ref_ids = {a.get('artifact_id') for a in (trace.get('reference_artifacts', []) or []) if isinstance(a, dict)}
    known_art = set(art_by_id) | ref_ids
    act_ids = {a.get('id') for a in actions if isinstance(a, dict)}

    producer = {}
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        pid = a.get('producer_action_id')
        if pid is not None:
            if pid not in act_ids:
                errs.append(f"artifact {a.get('artifact_id')}: producer_action_id {pid} does not exist")
            producer[a.get('artifact_id')] = pid
        for parent in a.get('derived_from', []) or []:
            if parent not in known_art:
                errs.append(f"artifact {a.get('artifact_id')}: derived_from '{parent}' does not exist")

    for a in actions:
        if not isinstance(a, dict):
            continue
        aid = a.get('id')
        for inp in a.get('inputs', []) or []:
            if inp not in known_art:
                errs.append(f"action {aid}: input '{inp}' is not a known artifact")
                continue
            pid = producer.get(inp)
            if pid is None:
                if inp not in ref_ids:
                    errs.append(f"action {aid}: input '{inp}' is consumed but never produced")
            elif isinstance(aid, int) and isinstance(pid, int) and pid >= aid:
                errs.append(f"action {aid}: input '{inp}' is produced later by action {pid} (data-flow cycle)")
        for out in a.get('outputs', []) or []:
            if out not in known_art:
                errs.append(f"action {aid}: output '{out}' is not a known artifact")

    for r in trace.get('residuals', []) or []:
        if isinstance(r, dict):
            for rid in r.get('related_artifact_ids', []) or []:
                if rid not in known_art:
                    errs.append(f"residual {r.get('residual_id')}: related_artifact_id '{rid}' does not exist")
    for m in trace.get('meta_actions', []) or []:
        if isinstance(m, dict):
            for pid in m.get('produced_artifact_ids', []) or []:
                if pid not in known_art:
                    errs.append(f"meta_action {m.get('id')}: produced_artifact_id '{pid}' does not exist")

    # Verification lineage chain.
    for a in artifacts:
        if not isinstance(a, dict):
            continue
        t = a.get('artifact_type')
        if t == 'VerificationResult':
            status = (a.get('payload') or {}).get('status')
            if status not in _VALID_VERDICTS:
                errs.append(f"VerificationResult {a.get('artifact_id')}: invalid status '{status}'")
            if not any(art_by_id.get(p, {}).get('artifact_type') == 'VerificationGoal'
                       for p in (a.get('derived_from') or [])):
                errs.append(f"VerificationResult {a.get('artifact_id')}: does not derive from a VerificationGoal")
        elif t == 'VerificationGoal':
            model_ok = any(art_by_id.get(p, {}).get('artifact_type') == 'IMLModel'
                           for p in (a.get('derived_from') or []))
            tgt = (a.get('payload') or {}).get('target_artifact_id')
            if tgt and art_by_id.get(tgt, {}).get('artifact_type') == 'IMLModel':
                model_ok = True
            if not model_ok:
                errs.append(f"VerificationGoal {a.get('artifact_id')}: does not derive from an IMLModel")

    # Derived projections must not blow up on this trace.
    try:
        from . import goals as _goals
        _goals.enrich(copy.deepcopy(trace))
    except Exception as e:  # noqa: BLE001 - surface any failure as a soundness error
        errs.append(f"enrich() raised {type(e).__name__}: {e}")
    try:
        grade_trace(copy.deepcopy(trace))
    except Exception as e:  # noqa: BLE001
        errs.append(f"grade_trace() raised {type(e).__name__}: {e}")

    if strict:
        for a in actions:
            if isinstance(a, dict) and a.get('type') in _GROUPED_ACTION_TYPES and a.get('meta_action_id') is None:
                errs.append(f"action {a.get('id')} ({a.get('type')}): not grouped into any phase meta-action")
    return errs


def cmd_validate(args):
    trace = load_trace(args.trace_file)
    errors, warnings = validate_trace(trace)
    if getattr(args, 'strict', False):
        errors = errors + soundness_errors(trace, strict=True)
    for w in warnings:
        print(f"  warning: {w}")
    for e in errors:
        print(f"  error:   {e}")
    if errors:
        print(f"\nInvalid trace: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1
    print(f"Valid trace ({len(warnings)} warning(s)).")
    return 0


def _grade_dimensions(trace):
    """Score a trace on the dimensions that make it useful to a reviewer. Each
    dimension is 0..1; weights sum to 100. Mechanical — no model involved."""
    actions = trace.get("actions", []) or []
    artifacts = trace.get("artifacts", []) or []
    residuals = trace.get("residuals", []) or []
    errors, _ = validate_trace(trace)
    has_trigger = bool((trace.get("trigger") or {}).get("type"))
    has_outcome = bool((trace.get("outcome") or {}).get("type"))
    outcome_sum = (trace.get("outcome") or {}).get("summary", "") or ""

    # 1. Structure — is it a sound, complete record?
    struct = (0.4 if not errors else 0.0) + (0.3 if has_trigger else 0.0) + (0.3 if has_outcome else 0.0)
    snote = f"{len(errors)} structural error(s)" if errors else ("valid; trigger + outcome present"
            if has_trigger and has_outcome else "missing trigger/outcome")

    # 2. Rationale coverage — are the steps explained at all? (coverage, NOT a
    #    judgment of whether the reasoning is sound — that needs a reviewer/LLM-judge)
    real = [a for a in actions if a.get("rationale") and len(a["rationale"]) >= 30
            and not a["rationale"].startswith("(")]
    rat_frac = len(real) / len(actions) if actions else 0.0
    has_decisions = any(a.get("category") == "gateway" for a in actions)
    reason = 0.7 * rat_frac + 0.15 * (1 if has_decisions else 0) + 0.15 * (1 if len(outcome_sum) >= 25 else 0)

    # 3. Negative space — are the gaps declared?
    if not residuals:
        neg, nnote = 0.0, "no residuals declared"
    else:
        wc = sum(1 for r in residuals if r.get("suggested_check")) / len(residuals)
        wt = sum(1 for r in residuals if r.get("target") or r.get("related_artifact_ids")) / len(residuals)
        sd = min(len({r.get("severity") for r in residuals}) / 3, 1)
        neg = 0.4 + 0.2 * wc + 0.2 * wt + 0.2 * sd
        nnote = f"{len(residuals)} declared, {int(wc*100)}% with a suggested check"

    # 4. Reproducibility — can a reviewer re-run / re-derive it?
    cmdish = [a for a in actions if a.get("type") in
              ("RunCommand", "RunTests", "GitDiff", "GitStatus", "GitCommit")]
    repro_acts = [a for a in actions if a.get("reproducibility")]
    repro_frac = (len(repro_acts) / len(cmdish)) if cmdish else 0.0
    has_vgoals = any(a.get("artifact_type") in ("VerificationGoal", "VerificationResult") for a in artifacts)
    base = max(repro_frac, 0.6 if has_vgoals else 0.0)
    bound = bool(trace.get("commit_sha"))
    repro = 0.5 * min(base, 1) + 0.25 * (1 if trace.get("reproducibility") else 0) + 0.25 * (1 if bound else 0)
    rnote = f"{len(repro_acts)} replayable action(s)" + ("" if bound else "; not bound to a commit")

    # 5. Verification evidence — was it actually checked? (substance)
    art_types = {a.get("artifact_type") for a in artifacts}
    has_proofs = "VerificationResult" in art_types
    has_tests = ("GeneratedTests" in art_types) or any(
        a.get("type") == "RunTests" and a.get("result_summary") for a in actions)
    has_results = any(a.get("result_summary") for a in actions)
    evidence = (0.5 if has_proofs else 0.0) + (0.25 if has_tests else 0.0) + (0.25 if has_results else 0.0)
    parts = [n for n, ok in [("proofs", has_proofs), ("tests", has_tests), ("results", has_results)] if ok]
    enote = ", ".join(parts) if parts else "no verification evidence"

    # 6. Lineage / integrity — run the structural checks over the artifact DAG.
    #    Only meaningful when there ARE artifacts; a vacuous pass earns no credit (N/A).
    if artifacts:
        checks = [evaluate_structural("data_flow_integrity", trace)]
        if any(a.get("artifact_type") == "VerificationGoal" for a in artifacts):
            checks.append(evaluate_structural("goals_reference_valid_artifacts", trace))
        if any(a.get("artifact_type") == "GeneratedTests" for a in artifacts):
            checks.append(evaluate_structural("generated_tests_require_decomposition", trace))
        passed = sum(1 for c in checks if c)
        lineage = {"name": "Lineage / integrity", "score": passed / len(checks), "weight": 15,
                   "note": f"{passed}/{len(checks)} structural checks pass", "applicable": True}
    else:
        lineage = {"name": "Lineage / integrity", "score": 0.0, "weight": 15,
                   "note": "0 artifacts — lineage not visualizable", "applicable": False}

    return [
        {"name": "Structure", "score": struct, "weight": 15, "note": snote},
        {"name": "Rationale coverage", "score": reason, "weight": 20,
         "note": f"{int(rat_frac*100)}% of actions carry a non-trivial rationale"},
        {"name": "Negative space", "score": neg, "weight": 20, "note": nnote},
        {"name": "Reproducibility", "score": repro, "weight": 20, "note": rnote},
        {"name": "Verification evidence", "score": evidence, "weight": 25, "note": enote},
        lineage,
    ]


def _policy_compliance(trace):
    """Run the trace's attached policies — a separate compliance axis, NOT folded
    into the quality grade (compliance is org-relative; quality is not)."""
    policies = trace.get("policies", []) or []
    if not policies:
        return {"applicable": False}
    passed, failed = 0, []
    for p in policies:
        status, _ = evaluate_policy(p, trace)
        if status == "passed":
            passed += 1
        elif status == "failed":
            failed.append(p.get("name", p.get("policy_id", "?")))
    return {"applicable": True, "passed": passed, "total": len(policies), "failed": failed}


def grade_trace(trace):
    normalize_trace(trace)
    dims = _grade_dimensions(trace)
    applicable = [d for d in dims if d.get("applicable", True)]
    total = sum(d["weight"] for d in applicable) or 1
    overall = round(sum(d["score"] * d["weight"] for d in applicable) / total * 100)
    letter = ("A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70
              else "D" if overall >= 60 else "F")
    by = {d["name"]: d["score"] for d in applicable}
    suggestions = []
    if by.get("Negative space", 1) < 0.5:
        suggestions.append("Declare the gaps with `ponens trace residual add` (assumptions / unverified / out-of-scope / …)")
    if by.get("Rationale coverage", 1) < 0.6:
        suggestions.append("Thin rationale coverage — explain each step (emit captures it; or enrich by hand)")
    if by.get("Reproducibility", 1) < 0.6:
        suggestions.append("Record commands + expected output and `ponens bind` to a commit so it can be reproduced")
    if by.get("Verification evidence", 1) < 0.5:
        suggestions.append("No verification — run tests or prove key properties so the claims are checkable")
    lineage_dim = next((d for d in dims if d["name"] == "Lineage / integrity"), None)
    if lineage_dim and not lineage_dim.get("applicable", True):
        suggestions.append("No artifacts — lineage isn't visualizable. Have the agent declare what it "
                           "produced/consumed (and wire inputs/outputs) so the data flow shows in the viewer.")
    elif by.get("Lineage / integrity", 1) < 1.0:
        suggestions.append("Artifact lineage is broken — a consumed artifact has no valid producer (data flow integrity)")
    compliance = _policy_compliance(trace)
    if compliance.get("applicable") and compliance["failed"]:
        suggestions.append(f"Policy compliance: failing {', '.join(compliance['failed'])} (governance gate, separate from quality)")
    return {"overall": overall, "grade": letter, "dimensions": dims,
            "applicable_weight": total, "compliance": compliance, "suggestions": suggestions}


def cmd_grade(args):
    trace = load_trace(args.trace_file)
    g = grade_trace(trace)
    if getattr(args, "json", False):
        print(json.dumps(g, indent=2, ensure_ascii=False))
        return 0
    c = g["compliance"]
    comp = (f"Policy compliance: {c['passed']}/{c['total']} passed" if c.get("applicable")
            else "Policy compliance: none attached")
    print(f"Trace grade: {g['grade']}  ({g['overall']}/100)      {comp}\n")
    total = g["applicable_weight"]
    for d in g["dimensions"]:
        if not d.get("applicable", True):
            print(f"  {d['name']:22s} {'·' * 12}  n/a   {d['note']}")
            continue
        filled = int(round(d["score"] * 12))
        bar = "█" * filled + "·" * (12 - filled)
        share = round(d["weight"] / total * 100)
        print(f"  {d['name']:22s} {bar} {int(d['score']*100):3d}%  ({share}%)  {d['note']}")
    if c.get("applicable"):
        mark = "✓" if not c["failed"] else "✗"
        tail = f"  —  failed: {', '.join(c['failed'])}" if c["failed"] else ""
        print(f"\n  Policy compliance {mark}  {c['passed']}/{c['total']} passed{tail}   (separate axis — not in the quality score)")
    if g["suggestions"]:
        print("\n  To improve:")
        for s in g["suggestions"]:
            print(f"    • {s}")
    return 0


_SEV_EMOJI = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🔵", "info": "⚪"}


def cmd_report(args):
    """Emit a Markdown summary of a trace — the body of a PR comment: grade, policy
    compliance, declared gaps, and the size of the reasoning record."""
    trace = load_trace(args.trace_file)
    g = grade_trace(trace)
    residuals = trace.get("residuals", []) or []
    metas = trace.get("meta_actions", []) or []
    arts = trace.get("artifacts", []) or []
    repro = sum(1 for a in (trace.get("actions") or []) if a.get("reproducibility"))
    title = (trace.get("title") or (trace.get("trigger") or {}).get("description")
             or trace.get("trace_id") or "reasoning trace")

    out = [f"### 🧭 Ponens reasoning trace — {title}", ""]
    head = [f"**Grade {g['grade']} ({g['overall']}/100)**"]
    c = g["compliance"]
    if c.get("applicable"):
        head.append(f"policies {c['passed']}/{c['total']}" + (" ✓" if not c["failed"] else " ✗"))
    head.append(f"{len(metas)} steps")
    if arts:
        head.append(f"{len(arts)} artifacts")
    if repro:
        head.append(f"{repro} replayable")
    out += [" · ".join(head), ""]

    out.append("<details><summary>Scorecard</summary>\n")
    out += ["| Dimension | Score |", "|---|---|"]
    for d in g["dimensions"]:
        score = f"{int(d['score'] * 100)}%" if d.get("applicable", True) else "n/a"
        out.append(f"| {d['name']} | {score} |")
    out += ["\n</details>", ""]

    if residuals:
        out.append("**Declared gaps (residuals):**")
        for r in sorted(residuals, key=lambda r: -_SEVERITY_RANK.get(r.get("severity"), 0))[:6]:
            em = _SEV_EMOJI.get(r.get("severity"), "•")
            chk = f" — *check:* {r['suggested_check']}" if r.get("suggested_check") else ""
            out.append(f"- {em} **{r.get('severity', '?')}** — {r.get('statement', '')}{chk}")
        if len(residuals) > 6:
            out.append(f"- …and {len(residuals) - 6} more")
    else:
        out.append("⚠️ **No residuals declared** — the negative space (assumptions / "
                   "unverified claims / out-of-scope) is undeclared. A clean trace *declares* its gaps.")
    print("\n".join(out))
    return 0


# Commands safe to replay during reproduction (read-only / verification only).
_REPRO_SAFE = ("pytest", "npm test", "npm run build", "npm run lint", "go test",
               "cargo test", "make test", "make check", "git status", "git diff",
               "git log", "ls ", "cat ", "grep ")
_REPRO_DANGER = ("rm ", "git push", "git commit", "sudo", " > ", ">>", "mv ", "dd ",
                 "curl", "wget", "chmod", "kill", "npm publish", "pip install", "git reset")


def _repro_command(action):
    return ((action.get("reproducibility") or {}).get("procedure") or {}).get("command")


def _repro_safe(cmd):
    c = (cmd or "").lower()
    if any(d in c for d in _REPRO_DANGER):
        return False
    return any(p in c for p in _REPRO_SAFE)


def cmd_reproduce(args):
    """Replay a trace's reproducible commands and report where the result diverges
    from what the trace recorded — the feedback a reviewing agent gives by reproducing.

    Execution is opt-in (--run) and limited to read-only / verification commands."""
    import subprocess
    trace = load_trace(args.trace_file)
    repro = [a for a in trace.get("actions", []) if _repro_command(a)]
    if not repro:
        print("No reproducible actions (no recorded commands) in this trace.")
        return 0
    safe = [a for a in repro if _repro_safe(_repro_command(a))]
    print(f"{len(repro)} reproducible command(s); {len(safe)} safe to replay"
          f"{'' if args.run else ' (dry run)'}.")

    if not args.run:
        for a in safe:
            print(f"  would replay #{a['id']}: {_repro_command(a)[:80]}")
        print("  pass --run to execute the safe commands and check for divergence.")
        return 0

    diverged = 0
    for a in safe:
        cmd = _repro_command(a)
        expected = ((a.get("reproducibility") or {}).get("expected_output") or {}).get("result_summary", "")
        try:
            r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            actual = " ".join((r.stdout + r.stderr).split())
        except Exception as e:
            actual = f"(execution failed: {e})"
        exp = expected.replace("ERROR: ", "").strip().strip("…")
        ok = bool(exp) and exp[:60] in actual
        print(f"  {'✓ reproduced' if ok else '✗ DIVERGED '} #{a['id']}: {cmd[:64]}")
        if not ok:
            diverged += 1
            print(f"      expected: {expected[:80]}")
            print(f"      actual:   {actual[:80]}")
    print(f"\n{len(safe)} replayed · {diverged} diverged.")
    return 1 if diverged else 0


def _save_trace_fmt(path, trace):
    """Write a trace back in its own format (JSON or YAML)."""
    if path.endswith((".yaml", ".yml")):
        with open(path, "w") as f:
            f.write(_dump_yaml(trace))
    else:
        save_trace(path, trace)


def cmd_residual_add(args):
    """Declare a residual — a gap the trace does NOT establish. This is the part of
    the negative space that only the agent (or author) can report; emission can't
    derive it."""
    trace = load_trace(args.trace_file)
    residuals = trace.setdefault("residuals", [])
    rid = f"r{len(residuals) + 1}"
    r = {"residual_id": rid, "kind": args.kind, "severity": args.severity,
         "statement": args.statement, "source": "agent_declared", "status": args.status}
    if args.target_type:
        r["target"] = {"target_type": args.target_type, "target_id": args.target_id}
    if getattr(args, "related", None):
        r["related_artifact_ids"] = args.related
    if args.suggested_check:
        r["suggested_check"] = args.suggested_check
    if getattr(args, "tag", None):
        r["tags"] = args.tag
    residuals.append(r)
    if trace.get("spec_version", "1.1") < "1.5":
        trace["spec_version"] = "1.5"
    _save_trace_fmt(args.trace_file, trace)
    print(f"Declared residual {rid} ({args.severity} {args.kind}) in {args.trace_file}")
    return 0


# --- meta-action curation (scrub the narrative; the atomic actions stay ground truth) ---

def _find_meta(trace, mid):
    for m in trace.get("meta_actions", []) or []:
        if m.get("id") == mid:
            return m
    return None


def cmd_meta_ls(args):
    """List the meta-actions (the narrative layer) and how curated each is. The
    `turn_segmented` ones are drafts seeded from the user's directives — scrub those."""
    trace = load_trace(args.trace_file)
    metas = trace.get("meta_actions", []) or []
    if not metas:
        print("No meta-actions in this trace.")
        return 0
    draft = sum(1 for m in metas if m.get("source") == "turn_segmented")
    for m in metas:
        src = m.get("source", "?")
        flag = "  draft" if src == "turn_segmented" else ("✎ curated" if src == "curated" else "")
        print(f"  {m['id']:5} [{src:14}] {len(m.get('action_ids', [])):3} actions  "
              f"{m.get('title', '')[:70]}  {flag}")
    print(f"\n{len(metas)} meta-actions · {draft} draft (raw from your directives — scrub with "
          f"`ponens trace meta set …`)")
    return 0


def cmd_meta_set(args):
    """Rewrite a meta-action's narrative — title / intent / outcome / status. Marks it
    `curated` (higher fidelity than the inferred draft). The atomic actions are untouched."""
    trace = load_trace(args.trace_file)
    m = _find_meta(trace, args.meta_id)
    if m is None:
        print(f"Error: no meta-action '{args.meta_id}' in {args.trace_file}", file=sys.stderr)
        return 1
    changed = []
    for field in ("title", "intent", "outcome", "status"):
        val = getattr(args, field, None)
        if val is not None:
            if field == "status" and val not in META_STATUSES:
                print(f"Error: invalid status '{val}' (one of {', '.join(sorted(META_STATUSES))})",
                      file=sys.stderr)
                return 1
            m[field] = val
            changed.append(field)
    if not changed:
        print("Nothing to set — pass --title / --intent / --outcome / --status.", file=sys.stderr)
        return 1
    m["source"] = "curated"
    _save_trace_fmt(args.trace_file, trace)
    print(f"Curated {args.meta_id} ({', '.join(changed)}) in {args.trace_file}")
    return 0


def cmd_meta_merge(args):
    """Fold dead-ends / false starts into one meta-action: move the others' actions
    (and artifacts/residuals) into `into`, then drop them. The result is marked curated."""
    trace = load_trace(args.trace_file)
    into = _find_meta(trace, args.into)
    if into is None:
        print(f"Error: no meta-action '{args.into}' in {args.trace_file}", file=sys.stderr)
        return 1
    others = []
    for mid in args.meta_ids:
        m = _find_meta(trace, mid)
        if m is None:
            print(f"Error: no meta-action '{mid}'", file=sys.stderr)
            return 1
        others.append(m)
    for m in others:
        into.setdefault("action_ids", []).extend(m.get("action_ids", []))
        into.setdefault("produced_artifact_ids", []).extend(m.get("produced_artifact_ids", []))
        into.setdefault("residual_ids", []).extend(m.get("residual_ids", []))
    into["action_ids"] = sorted(set(into["action_ids"]))
    for key in ("produced_artifact_ids", "residual_ids"):
        if into.get(key):
            into[key] = list(dict.fromkeys(into[key]))
    drop = {m["id"] for m in others}
    trace["meta_actions"] = [m for m in trace["meta_actions"] if m["id"] not in drop]
    for a in trace.get("actions", []):
        if a.get("meta_action_id") in drop:
            a["meta_action_id"] = into["id"]
    into["source"] = "curated"
    _save_trace_fmt(args.trace_file, trace)
    print(f"Merged {', '.join(args.meta_ids)} into {args.into} in {args.trace_file}")
    return 0


def cmd_meta_drop(args):
    """Remove a meta-action from the narrative; its atomic actions remain (ungrouped)."""
    trace = load_trace(args.trace_file)
    m = _find_meta(trace, args.meta_id)
    if m is None:
        print(f"Error: no meta-action '{args.meta_id}' in {args.trace_file}", file=sys.stderr)
        return 1
    trace["meta_actions"] = [x for x in trace["meta_actions"] if x["id"] != args.meta_id]
    for a in trace.get("actions", []):
        if a.get("meta_action_id") == args.meta_id:
            a.pop("meta_action_id", None)
    _save_trace_fmt(args.trace_file, trace)
    print(f"Dropped meta-action {args.meta_id} (its {len(m.get('action_ids', []))} actions remain) "
          f"in {args.trace_file}")
    return 0


def cmd_retitle(args):
    """Set the trace's top-level title and/or outcome summary (the headline narrative)."""
    trace = load_trace(args.trace_file)
    if args.title is not None:
        trace["title"] = args.title
    if args.outcome is not None:
        trace.setdefault("outcome", {})["summary"] = args.outcome
    _save_trace_fmt(args.trace_file, trace)
    print(f"Updated trace title/outcome in {args.trace_file}")
    return 0


def cmd_review_ready(args):
    """Is this trace ready to hand to a reviewer? Beyond structural validity, this
    insists the negative space is present — the agent must declare its gaps (or it is
    not review-ready)."""
    trace = load_trace(args.trace_file)
    errors, _ = validate_trace(trace)
    actions = trace.get("actions", [])
    no_rationale = [a.get("id") for a in actions if not a.get("rationale")]
    has_outcome = bool((trace.get("outcome") or {}).get("type"))
    residuals = trace.get("residuals", []) or []

    checks = [
        ("structure valid", not errors, f"{len(errors)} structural error(s)" if errors else ""),
        ("outcome recorded", has_outcome, "" if has_outcome else "no outcome.type"),
        ("actions have rationale", not no_rationale,
         f"{len(no_rationale)} action(s) without rationale" if no_rationale else ""),
        ("residual surface declared", bool(residuals),
         f"{len(residuals)} declared" if residuals else
         "no residuals — declare the gaps (assumptions / unverified / out-of-scope / "
         "limitations / open questions) with `ponens trace residual add`, or there are none to find"),
    ]
    print(f"Review-readiness: {args.trace_file}")
    for label, passed, note in checks:
        print(f"  {'✓' if passed else '✗'} {label}" + (f"  — {note}" if note else ""))

    ready = not errors and has_outcome and not no_rationale and bool(residuals)
    print("\n" + ("READY for review." if ready else
                  "NOT review-ready — address the ✗ items (especially the negative space)."))
    return 0 if ready else 1


def cmd_fmt(args):
    """Convert a trace between JSON and YAML (the same content, a different projection)."""
    trace = load_trace(args.trace_file)
    out = _dump_yaml(trace) if args.to == "yaml" else (json.dumps(trace, indent=2, ensure_ascii=False) + "\n")
    if args.output:
        with open(args.output, "w") as f:
            f.write(out)
        print(f"Wrote {args.output}")
    else:
        sys.stdout.write(out)
    return 0


def cmd_check(args):
    trace = load_trace(args.trace_file)
    errors, _ = validate_trace(trace)
    if errors:
        print("Error: cannot check an invalid trace:", file=sys.stderr)
        for e in errors[:10]:
            print(f"  - {e}", file=sys.stderr)
        return 1
    normalize_trace(trace)
    if args.policy_file:
        with open(args.policy_file) as f:
            policy_data = json.load(f)
        policies = policy_data if isinstance(policy_data, list) else policy_data.get('policies', [])
    else:
        policies = trace.get('policies', [])
    if not policies:
        print("[]" if getattr(args, 'json', False) else "No policies to check.")
        return 0
    total = len(policies)
    passed = 0
    failed = 0
    warnings = 0
    errors = []
    # policy_evaluation records (Trace Spec §7) accumulated for --json / --write.
    evaluations = []
    as_json = getattr(args, 'json', False)
    emit = (lambda *a, **k: None) if as_json else print  # suppress human output in machine mode
    last_action_id = max((a['id'] for a in trace.get('actions', [])), default=None)

    # Output artifact ids produced by a set of action ids — so evidence highlights DAG nodes too.
    _arts_by_action = {}
    for a in trace.get('actions', []):
        _arts_by_action[a['id']] = list(a.get('_original_outputs', a.get('outputs', [])))

    def _arts_of(action_ids):
        out = []
        for aid in action_ids:
            for art in _arts_by_action.get(aid, []):
                if art not in out:
                    out.append(art)
        return out

    def record_eval(pid, status, note, ev_actions=None, vi_actions=None):
        ev = {'policy_id': pid, 'status': status}
        if last_action_id is not None:
            ev['checked_at_action_id'] = last_action_id
        if note:
            ev['note'] = note
        if ev_actions:
            ev['evidence_action_ids'] = ev_actions
            arts = _arts_of(ev_actions)
            if arts:
                ev['evidence_artifact_ids'] = arts
        if vi_actions:
            ev['violating_action_ids'] = vi_actions
            arts = _arts_of(vi_actions)
            if arts:
                ev['violating_artifact_ids'] = arts
        evaluations.append(ev)

    for p in policies:
        pid = p.get('policy_id', p.get('name', '?'))
        name = p.get('name', pid)
        severity = p.get('severity', 'error')
        _, syntax_errors, syntax_warnings = syntax_check_policy(p)
        if syntax_errors:
            emit(f"  SYNTAX  {name}")
            for e in syntax_errors:
                emit(f"          {e.message}")
            errors.append(name)
            record_eval(pid, 'unknown', f'Syntax error: {syntax_errors[0].message}')
            continue
        status, note, ev_actions, vi_actions = evaluate_policy_full(p, trace)
        record_eval(pid, status, note, ev_actions, vi_actions)
        if status == 'passed':
            passed += 1
            emit(f"  PASS    {name}")
        elif status == 'failed':
            failed += 1
            icon = 'FAIL' if severity == 'error' else 'WARN'
            emit(f"  {icon}    {name}")
            if note:
                emit(f"          {note}")
            if severity == 'error':
                errors.append(name)
            elif severity == 'warning':
                warnings += 1
        else:
            emit(f"  SKIP    {name} — {note or 'could not evaluate'}")

    if getattr(args, 'write', False):
        trace['policy_evaluations'] = evaluations
        save_trace(args.trace_file, trace)
        if not as_json:
            print(f"  wrote {len(evaluations)} policy_evaluations to {args.trace_file}")

    if as_json:
        print(json.dumps(evaluations, indent=2, ensure_ascii=False))
        return 0

    emit(f"\n{'='*50}")
    emit(f"  {total} policies checked")
    emit(f"  {passed} passed, {failed} failed, {warnings} warnings")
    if errors:
        emit(f"  {len(errors)} errors: {', '.join(errors)}")
        return 1
    if args.strict and (failed > 0 or warnings > 0):
        return 1
    return 0


def cmd_status(args):
    trace = load_trace(args.trace_file)
    if getattr(args, 'web', False):
        return launch_viewer(trace, args.trace_file)
    print(f"Trace: {trace.get('trace_id', 'N/A')}")
    print(f"  Spec:      v{trace.get('spec_version', '?')}")
    print(f"  Model:     {trace.get('model', 'N/A')}")
    print(f"  Assistant:  {trace.get('assistant', 'N/A')}")
    print(f"  Timestamp: {trace.get('timestamp', 'N/A')}")
    trigger = trace.get('trigger', {})
    if trigger:
        print(f"  Trigger:   {trigger.get('type', '?')} — {trigger.get('description', '')}")
    else:
        print(f"  Trigger:   (not set)")
    outcome = trace.get('outcome', {})
    if outcome.get('type'):
        print(f"  Outcome:   {outcome['type']} — {outcome.get('summary', '')}")
    else:
        print(f"  Outcome:   (incomplete)")
    actions = trace.get('actions', [])
    artifacts = trace.get('artifacts', [])
    policies = trace.get('policies', [])
    print(f"  Actions:   {len(actions)}")
    print(f"  Artifacts: {len(artifacts)}")
    print(f"  Policies:  {len(policies)}")
    if actions:
        print(f"\n  Action log:")
        for a in actions:
            print(f"    #{a['id']:3d}  {a['type']:20s}  {a['label'][:60]}")
    if policies:
        evals = {e['policy_id']: e for e in trace.get('policy_evaluations', [])}
        print(f"\n  Policy status:")
        for p in policies:
            ev = evals.get(p['policy_id'], {})
            status = ev.get('status', 'not evaluated')
            print(f"    {p['name']:40s}  {status}")
    return 0


def cmd_residuals(args):
    """List the trace's residual surface — its negative space (Trace Spec §13). With --derived,
    also include computed stale-evidence residuals."""
    trace = load_trace(args.trace_file)
    residuals = list(trace.get('residuals', []))
    if getattr(args, 'derived', False):
        seen = {r.get('residual_id') for r in residuals}
        residuals += [r for r in goalops.stale_evidence(trace) if r.get('residual_id') not in seen]

    if getattr(args, 'web', False):
        return launch_viewer(trace, args.trace_file)
    if getattr(args, 'json', False):
        print(json.dumps(residuals, indent=2, ensure_ascii=False))
        return 0

    if not residuals:
        print("No residuals declared (empty negative space).")
        return 0

    rank = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1, 'info': 0}
    ordered = sorted(residuals, key=lambda r: rank.get(r.get('severity', 'info'), 0), reverse=True)

    counts = {}
    for r in residuals:
        counts[r.get('severity', 'info')] = counts.get(r.get('severity', 'info'), 0) + 1
    summary = "  ".join(f"{counts[s]} {s}" for s in ['critical', 'high', 'medium', 'low', 'info'] if s in counts)

    print(f"Residual surface: {trace.get('trace_id', '?')}   ({len(residuals)} declared)")
    print(f"  {summary}\n")
    for r in ordered:
        print(f"  [{r.get('severity', 'info').upper()}] {r.get('residual_id', '?')}  "
              f"{r.get('kind', '?')} · {r.get('status', 'open')}")
        if r.get('statement'):
            print(f"      {r['statement']}")
        loc = []
        tgt = r.get('target')
        if tgt:
            loc.append(f"target: {tgt.get('target_type', '?')}:{tgt.get('target_id', '?')}")
        if r.get('related_artifact_ids'):
            loc.append(f"related: {', '.join(r['related_artifact_ids'])}")
        if loc:
            print(f"      {'   '.join(loc)}")
        if r.get('suggested_check'):
            print(f"      check:  {r['suggested_check']}")
        print()
    return 0


def _apply_goals_file(trace, goals_path):
    """Merge an external goals file (a list, or {goals: [...]}) into the trace's `goals`.

    Lets the desktop keep authoring goals app-side and hand them to ponens per call, without
    surgically editing the emitted trace.
    """
    if not goals_path:
        return
    data = load_trace(goals_path)
    goals = data.get('goals') if isinstance(data, dict) else data
    if goals is not None:
        trace['goals'] = goals


def cmd_resolve(args):
    """Resolve each goal's acceptance items against the trace evidence (status + evidence pointer)."""
    trace = load_trace(args.trace_file)
    _apply_goals_file(trace, getattr(args, 'goals', None))
    out = []
    for g in trace.get('goals', []):
        items = []
        for item in g.get('acceptance', []):
            r = goalops.resolve_item(item, trace)
            items.append({**item, 'status': r['status'], 'from_trace': r['from_trace'],
                          'evidence': r['evidence']})
        out.append({'id': g.get('id'), 'intent': g.get('intent'),
                    'progress': goalops.progress_of(items), 'acceptance': items})
    if getattr(args, 'json', False):
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    marks = {'done': '✓', 'blocked': '✗', 'doing': '◐', 'todo': '○'}
    for g in out:
        print(f"{g['id']}  {int(round(g['progress'] * 100))}%  {g['intent']}")
        for it in g['acceptance']:
            src = ' (trace)' if it.get('from_trace') else ''
            print(f"  {marks.get(it['status'], '?')} [{it.get('kind')}] {it.get('label')}{src}")
    return 0


def cmd_enrich(args):
    """Augment the trace with all derived views (resolved acceptance, derived residuals, per-goal
    relevance cone, exploration) — one projection a thin viewer can render without re-implementing
    the logic. The source trace is not modified."""
    trace = load_trace(args.trace_file)
    _apply_goals_file(trace, getattr(args, 'goals', None))
    text = json.dumps(goalops.enrich(trace), indent=2, ensure_ascii=False)
    out_path = getattr(args, 'output', None)
    if out_path:
        with open(out_path, 'w') as f:
            f.write(text + '\n')
        print(f"Wrote enriched trace -> {out_path}", file=sys.stderr)
    else:
        print(text)
    return 0


def _find_visualizer():
    here = os.path.dirname(__file__)
    candidates = [
        os.path.join(here, '..', '..', 'viewer', 'vscode-plugin', 'media', 'visualizer.html'),
        os.path.join(here, '..', '..', 'visualizer.html'),
        os.path.join(here, 'visualizer.html'),
        'visualizer.html',
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return None


def _render_viewer_html(trace):
    viz = _find_visualizer()
    if not viz:
        return None
    with open(viz) as f:
        html = f.read()
    # Embed in a NON-executable application/json block and JSON.parse it. Escape
    # every '<' to < so no </script, <script or <!-- can ever appear in the
    # block (those drive the HTML script-data tokenizer and would mis-end the tag);
    # JSON.parse handles U+2028/U+2029 natively, so the data can hold anything.
    trace_json = json.dumps(trace, ensure_ascii=False).replace('<', '\\u003c')
    try:
        grade_json = json.dumps(grade_trace(trace), ensure_ascii=False).replace('<', '\\u003c')
    except Exception:
        grade_json = 'null'
    loader = """
<script id="ponens-trace-data" type="application/json">__PONENS_TRACE__</script>
<script id="ponens-grade-data" type="application/json">__PONENS_GRADE__</script>
<script>
(function() {
  function _banner(msg, ok) {
    var p = document.getElementById('flowPanel');
    if (p) p.innerHTML = '<div style="padding:24px;color:' + (ok ? '#86efac' : '#fca5a5') +
      ';font:13px ui-monospace,monospace;white-space:pre-wrap;line-height:1.5;">' + msg + '</div>';
  }
  var _cliTrace;
  try {
    _cliTrace = JSON.parse(document.getElementById('ponens-trace-data').textContent);
  } catch (e) {
    var emsg = 'Failed to parse embedded trace JSON:\\n\\n' + (e && e.message || e);
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() { _banner(emsg, false); });
    else _banner(emsg, false);
    return;
  }
  function _go() {
    if (typeof loadTrace !== 'function') { setTimeout(_go, 50); return; }
    try {
      loadTrace(_cliTrace);
      var b = document.getElementById('demoBadge'); if (b) b.style.display = 'none';
      var s = document.getElementById('demoSelect'); if (s) s.value = '';
      // A CLI-rendered trace is a specific trace, not the demo gallery — hide the demo picker.
      var sel = document.getElementById('demoSelector'); if (sel) sel.style.display = 'none';
      // Surface the Grade tab (computed by the CLI) and open it first.
      try { window.__ponensGrade = JSON.parse(document.getElementById('ponens-grade-data').textContent); } catch (e) {}
      var gb = document.getElementById('gradeViewBtn'); if (gb) gb.style.display = '';
      if (window.__ponensGrade && typeof switchView === 'function') switchView('grade');
      var p = document.getElementById('flowPanel');
      if (!p || !p.innerHTML.trim()) {
        if ((_cliTrace.actions || []).length === 0) {
          if (p) p.innerHTML = '<div style="padding:28px;color:#8b949e;font:14px ui-sans-serif,system-ui;">No recorded activity in this session yet.</div>';
        } else {
          _banner('loadTrace ran but produced no flow.\\nactions=' + ((_cliTrace.actions || []).length) +
                  '  spec_version=' + _cliTrace.spec_version, false);
        }
      }
    } catch (e) {
      _banner('Viewer failed to render this trace:\\n\\n' + (e && e.stack || e), false);
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function() { setTimeout(_go, 50); });
  else setTimeout(_go, 50);
})();
</script>
""".replace('__PONENS_TRACE__', trace_json).replace('__PONENS_GRADE__', grade_json)
    # Inject before the LAST </body> only — an earlier one lives inside a JS
    # template literal in the visualizer, and replacing it would splay our
    # <script> (with its </script>) into the page's main script and corrupt it.
    head, sep, tail = html.rpartition('</body>')
    if not sep:
        return html + loader
    return head + loader + '\n' + sep + tail


def _can_open_browser():
    """Heuristic: can we usefully open a browser here, or are we headless?"""
    if os.environ.get('PONENS_NO_BROWSER'):
        return False
    if sys.platform == 'darwin' or sys.platform.startswith('win'):
        return True
    return bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))


def launch_viewer(trace, trace_file=None):
    """Escalate to the rich view: the collaborative hub page if the trace has been
    pushed, otherwise the local self-contained visualizer. Headless-safe — never
    blocks, and prints the URL/path when no browser can be opened."""
    # Smart target: a pushed trace opens the hub's collaborative view.
    if trace_file:
        try:
            from .sync import load_sidecar
            from .client import hub_url
            side = load_sidecar(trace_file)
            if side and side.get('hub_trace_id'):
                url = f"{hub_url()}/traces/{side['hub_trace_id']}"
                print(f"Hub view: {url}")
                if _can_open_browser():
                    webbrowser.open(url)
                return 0
        except Exception:
            pass

    html = _render_viewer_html(trace)
    if html is None:
        print("Error: visualizer.html not found (expected under viewer/vscode-plugin/media/).",
              file=sys.stderr)
        return 1
    fd, path = tempfile.mkstemp(suffix='.html', prefix='ponens-trace-')
    with os.fdopen(fd, 'w') as f:
        f.write(html)
    url = 'file://' + path
    if _can_open_browser():
        print(f"Opening trace viewer: {url}")
        webbrowser.open(url)
    else:
        print(f"Trace viewer written to {path}")
        print("  (headless environment — open this file in a browser)")
    return 0


def cmd_view(args):
    trace = load_trace(args.trace_file)
    if getattr(args, "out", None):
        html = _render_viewer_html(trace)
        if html is None:
            print("Error: visualizer.html not found (expected under viewer/vscode-plugin/media/).",
                  file=sys.stderr)
            return 1
        with open(args.out, "w") as f:
            f.write(html)
        print(f"Wrote self-contained viewer → {args.out}")
        return 0
    return launch_viewer(trace, args.trace_file)


# ================================================================
# Register subcommands under "trace" group
# ================================================================

def register(subparsers):
    """Register the 'trace' command group on the given subparsers object."""
    trace_parser = subparsers.add_parser("trace", help="Local trace management (init, build, check, view)")
    trace_sub = trace_parser.add_subparsers(dest="trace_command", required=True)

    # init
    p = trace_sub.add_parser("init", help="Create a new trace file")
    p.add_argument("trace_file", help="Path to trace JSON file")
    p.add_argument("--model", default="example-model", help="LLM model name")
    p.add_argument("--assistant", default="ponens", help="Assistant name")
    p.set_defaults(func=cmd_init)

    # trigger
    p = trace_sub.add_parser("trigger", help="Set the trigger event")
    p.add_argument("trace_file")
    p.add_argument("--type", required=True, choices=["TaskReceived", "TriggeredByEvent"])
    p.add_argument("--description", required=True)
    p.add_argument("--from-user", default=None)
    p.set_defaults(func=cmd_trigger)

    # action
    p = trace_sub.add_parser("action", help="Append an action to the trace")
    p.add_argument("trace_file")
    p.add_argument("--type", required=True, help="Action type (e.g. ReadFile, EditFile, Formalize)")
    p.add_argument("--label", required=True, help="Short description")
    p.add_argument("--rationale", required=True, help="Why this action was taken")
    p.add_argument("--category", default="activity", choices=["activity", "gateway", "reasoning"])
    p.add_argument("--inputs", default=None, help="Comma-separated input artifact IDs")
    p.add_argument("--outputs", default=None, help="Comma-separated output artifact IDs")
    p.add_argument("--detail", default=None, help="Extended description")
    p.add_argument("--result-summary", default=None, help="One-line result summary")
    p.add_argument("--evidence", default=None, help="File path for evidence (FileRef)")
    p.set_defaults(func=cmd_action)

    # artifact
    p = trace_sub.add_parser("artifact", help="Add an artifact to the trace")
    p.add_argument("trace_file")
    p.add_argument("--id", default=None, help="Artifact ID (auto-generated if omitted)")
    p.add_argument("--type", required=True, help="Artifact type (e.g. SourceCode, IMLModel)")
    p.add_argument("--name", required=True, help="Human-readable name")
    p.add_argument("--derived-from", default=None, help="Comma-separated parent artifact IDs")
    p.add_argument("--producer-action-id", type=int, default=None, help="Action that produced this")
    p.add_argument("--format", default=None, help="Format (e.g. python, iml, json)")
    p.add_argument("--summary", default=None, help="Brief description")
    p.set_defaults(func=cmd_artifact)

    # complete
    p = trace_sub.add_parser("complete", help="Mark the trace as completed")
    p.add_argument("trace_file")
    p.add_argument("--summary", default=None, help="Outcome summary")
    p.set_defaults(func=cmd_complete)

    # validate
    p = trace_sub.add_parser("validate", help="Validate the trace's structure")
    p.add_argument("trace_file")
    p.add_argument("--strict", action="store_true",
                   help="also check deep soundness: reference resolution, data-flow ordering, "
                        "verification lineage, phase coverage, and that enrich/grade run clean")
    p.set_defaults(func=cmd_validate)

    # fmt
    p = trace_sub.add_parser("fmt", help="Convert a trace between JSON and YAML")
    p.add_argument("trace_file")
    p.add_argument("--to", choices=["json", "yaml"], required=True, help="Target format")
    p.add_argument("-o", "--output", help="Write to this file (default: stdout)")
    p.set_defaults(func=cmd_fmt)

    # check
    p = trace_sub.add_parser("check", help="Check the trace against policies")
    p.add_argument("trace_file")
    p.add_argument("--policy-file", default=None, help="External policy JSON file")
    p.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    p.add_argument("--json", action="store_true", help="Emit policy_evaluations as JSON (machine-readable; suppresses human output)")
    p.add_argument("--write", action="store_true", help="Stamp policy_evaluations into the trace file in place")
    p.set_defaults(func=cmd_check)

    # status
    p = trace_sub.add_parser("status", help="Show trace summary")
    p.add_argument("trace_file")
    p.add_argument("--web", action="store_true", help="Open the rich view in a browser")
    p.set_defaults(func=cmd_status)

    # residuals (view)
    p = trace_sub.add_parser("residuals", help="List the residual surface (declared negative space)")
    p.add_argument("trace_file")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--derived", action="store_true", help="Also include computed stale-evidence residuals")
    p.add_argument("--web", action="store_true", help="Open the rich view in a browser")
    p.set_defaults(func=cmd_residuals)

    # resolve (goal acceptance -> live status against the trace)
    p = trace_sub.add_parser("resolve", help="Resolve each goal's acceptance items against the trace")
    p.add_argument("trace_file")
    p.add_argument("--goals", help="External goals file to merge before resolving")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_resolve)

    # enrich (one projection carrying all derived views for a thin viewer)
    p = trace_sub.add_parser("enrich", help="Augment the trace with resolved acceptance, derived residuals, cones")
    p.add_argument("trace_file")
    p.add_argument("--goals", help="External goals file to merge before enriching")
    p.add_argument("-o", "--output", help="Write the enriched trace here (default: stdout)")
    p.set_defaults(func=cmd_enrich)

    # residual (declare)
    rp = trace_sub.add_parser("residual", help="Declare a residual (a gap the trace does not establish)")
    rp_sub = rp.add_subparsers(dest="residual_command", required=True)
    p = rp_sub.add_parser("add", help="Declare a residual")
    p.add_argument("trace_file")
    p.add_argument("--kind", required=True, choices=sorted(RESIDUAL_KINDS))
    p.add_argument("--severity", default="medium", choices=["info", "low", "medium", "high", "critical"])
    p.add_argument("--statement", required=True, help="The gap, in plain language")
    p.add_argument("--target-type", choices=["trace", "action", "artifact", "policy"])
    p.add_argument("--target-id")
    p.add_argument("--suggested-check", help="How a reviewer could close it")
    p.add_argument("--related", action="append", help="Related artifact id (repeatable)")
    p.add_argument("--status", default="open", choices=sorted(RESIDUAL_STATUSES))
    p.add_argument("--tag", action="append", help="Tag (repeatable)")
    p.set_defaults(func=cmd_residual_add)

    # meta (curate the narrative layer)
    mp = trace_sub.add_parser("meta", help="Curate the meta-action narrative (scrub the raw directives)")
    mp_sub = mp.add_subparsers(dest="meta_command", required=True)
    q = mp_sub.add_parser("ls", help="List meta-actions and how curated each is")
    q.add_argument("trace_file")
    q.set_defaults(func=cmd_meta_ls)
    q = mp_sub.add_parser("set", help="Rewrite a meta-action's title/intent/outcome (marks it curated)")
    q.add_argument("trace_file")
    q.add_argument("meta_id")
    q.add_argument("--title")
    q.add_argument("--intent")
    q.add_argument("--outcome")
    q.add_argument("--status", choices=sorted(META_STATUSES))
    q.set_defaults(func=cmd_meta_set)
    q = mp_sub.add_parser("merge", help="Fold dead-ends into one meta-action")
    q.add_argument("trace_file")
    q.add_argument("into", help="The meta-action to keep")
    q.add_argument("meta_ids", nargs="+", help="Meta-actions to fold in and remove")
    q.set_defaults(func=cmd_meta_merge)
    q = mp_sub.add_parser("drop", help="Remove a meta-action (its actions remain, ungrouped)")
    q.add_argument("trace_file")
    q.add_argument("meta_id")
    q.set_defaults(func=cmd_meta_drop)

    # retitle (top-level narrative)
    p = trace_sub.add_parser("retitle", help="Set the trace's title and/or outcome summary")
    p.add_argument("trace_file")
    p.add_argument("--title")
    p.add_argument("--outcome")
    p.set_defaults(func=cmd_retitle)

    # review-ready
    p = trace_sub.add_parser("review-ready", help="Check the trace is complete enough to review (incl. the negatives)")
    p.add_argument("trace_file")
    p.set_defaults(func=cmd_review_ready)

    # reproduce
    p = trace_sub.add_parser("reproduce", help="Replay reproducible commands and report divergence from the record")
    p.add_argument("trace_file")
    p.add_argument("--run", action="store_true", help="Execute the safe commands (default: dry run)")
    p.set_defaults(func=cmd_reproduce)

    # grade
    p = trace_sub.add_parser("grade", help="Grade the trace's quality across dimensions")
    p.add_argument("trace_file")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.set_defaults(func=cmd_grade)

    # report (Markdown summary — e.g. a PR comment body)
    p = trace_sub.add_parser("report", help="Markdown summary of the trace (grade, gaps) for a PR comment")
    p.add_argument("trace_file")
    p.set_defaults(func=cmd_report)

    # view
    p = trace_sub.add_parser("view", help="Open trace in the visualizer")
    p.add_argument("trace_file")
    p.add_argument("-o", "--out", help="Write the self-contained viewer HTML here instead of launching")
    p.set_defaults(func=cmd_view)
