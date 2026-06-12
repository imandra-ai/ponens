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
    ForAll, Exists, ExistsUnique, FieldAccess, Compare,
    RawStructural, FuncApp, SetLiteral, Ancestors,
    ACTION_TYPES, ARTIFACT_TYPES, PREDICATES,
    STRUCTURAL_POLICIES,
)


# ================================================================
# Trace I/O
# ================================================================

def load_trace(path):
    if not os.path.exists(path):
        print(f"Error: trace file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


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

def create_empty_trace(model='claude-opus-4-6', assistant='claude-code + ponens'):
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
            return a.get('type') == name
        if name in ARTIFACT_TYPES:
            if a.get('type') == name:
                return True
            for out_id in a.get('outputs', []):
                for art in trace.get('artifacts', []):
                    if (art.get('artifact_id') == out_id or art.get('name') == out_id) and art.get('artifact_type') == name:
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
        if name == 'high_stakes_path':
            target = get_action_target(a, trace)
            return any(p in target for p in ['payments/', 'risk/', 'stripe_payment_flow'])
        keyword = name.replace('_', ' ').lower()
        text = f"{a.get('type','')} {a.get('label','')} {a.get('detail','')} {a.get('rationale','')} {a.get('result_summary','')}".lower()
        if keyword in text:
            return True
        return False

    if isinstance(node, AtomWithArgs):
        if not ctx:
            return False
        a = ctx['action']
        type_match = a.get('type') == node.name
        if not type_match:
            for out_id in a.get('outputs', []):
                for art in trace.get('artifacts', []):
                    if (art.get('artifact_id') == out_id or art.get('name') == out_id) and art.get('artifact_type') == node.name:
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


def evaluate_policy(policy, trace):
    formula_str = policy.get('formula', '')
    name = policy.get('name', '')
    if not formula_str:
        return 'unknown', 'No formula defined'
    if name in STRUCTURAL_POLICIES:
        result = evaluate_structural(name, trace)
        return ('passed' if result else 'failed'), None
    try:
        tokens = tokenize(formula_str)
        parser = Parser(tokens, formula_str, name)
        ast = parser.parse()
    except Exception as e:
        return 'unknown', f'Parse error: {e}'
    if isinstance(ast, RawStructural):
        return 'unknown', 'Formula too complex for runtime evaluation'
    try:
        result = evaluate_formula(ast, trace)
        return ('passed' if result else 'failed'), None
    except Exception as e:
        return 'unknown', f'Evaluation error: {e}'


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
            if at == 'IMLModel' and 'iml_code' in art['payload']:
                action['formalization'] = art['payload']
            elif at == 'Formalization':
                action['formalization'] = art['payload']
            elif at == 'VerificationGoal':
                action['vg_defined'] = art['payload']
            elif at == 'VerificationResult':
                action['vg_result'] = art['payload']
            elif at == 'Decomposition':
                action['decomposition'] = art['payload']
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


def cmd_check(args):
    trace = load_trace(args.trace_file)
    normalize_trace(trace)
    if args.policy_file:
        with open(args.policy_file) as f:
            policy_data = json.load(f)
        policies = policy_data if isinstance(policy_data, list) else policy_data.get('policies', [])
    else:
        policies = trace.get('policies', [])
    if not policies:
        print("No policies to check.")
        return 0
    total = len(policies)
    passed = 0
    failed = 0
    warnings = 0
    errors = []
    for p in policies:
        name = p.get('name', p.get('policy_id', '?'))
        severity = p.get('severity', 'error')
        _, syntax_errors, syntax_warnings = syntax_check_policy(p)
        if syntax_errors:
            print(f"  SYNTAX  {name}")
            for e in syntax_errors:
                print(f"          {e.message}")
            errors.append(name)
            continue
        status, note = evaluate_policy(p, trace)
        if status == 'passed':
            passed += 1
            print(f"  PASS    {name}")
        elif status == 'failed':
            failed += 1
            icon = 'FAIL' if severity == 'error' else 'WARN'
            print(f"  {icon}    {name}")
            if note:
                print(f"          {note}")
            if severity == 'error':
                errors.append(name)
            elif severity == 'warning':
                warnings += 1
        else:
            print(f"  SKIP    {name} — {note or 'could not evaluate'}")
    print(f"\n{'='*50}")
    print(f"  {total} policies checked")
    print(f"  {passed} passed, {failed} failed, {warnings} warnings")
    if errors:
        print(f"  {len(errors)} errors: {', '.join(errors)}")
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
    """List the trace's residual surface — its declared negative space (Trace Spec §13)."""
    trace = load_trace(args.trace_file)
    residuals = trace.get('residuals', [])

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
    trace_json = json.dumps(trace, ensure_ascii=False)
    loader = """
<script>
(function() {
  var _cliTrace = __PONENS_TRACE__;
  function _tryLoad() {
    if (typeof loadTrace === 'function') {
      loadTrace(_cliTrace);
      var badge = document.getElementById('demoBadge');
      if (badge) badge.style.display = 'none';
      var sel = document.getElementById('demoSelect');
      if (sel) sel.value = '';
    } else { setTimeout(_tryLoad, 50); }
  }
  setTimeout(_tryLoad, 200);
})();
</script>
""".replace('__PONENS_TRACE__', trace_json)
    return html.replace('</body>', loader + '\n</body>')


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
    return launch_viewer(load_trace(args.trace_file), args.trace_file)


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
    p.add_argument("--model", default="claude-opus-4-6", help="LLM model name")
    p.add_argument("--assistant", default="claude-code + ponens", help="Assistant name")
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

    # check
    p = trace_sub.add_parser("check", help="Check the trace against policies")
    p.add_argument("trace_file")
    p.add_argument("--policy-file", default=None, help="External policy JSON file")
    p.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    p.set_defaults(func=cmd_check)

    # status
    p = trace_sub.add_parser("status", help="Show trace summary")
    p.add_argument("trace_file")
    p.add_argument("--web", action="store_true", help="Open the rich view in a browser")
    p.set_defaults(func=cmd_status)

    # residuals
    p = trace_sub.add_parser("residuals", help="List the residual surface (declared negative space)")
    p.add_argument("trace_file")
    p.add_argument("--json", action="store_true", help="Output raw JSON")
    p.add_argument("--web", action="store_true", help="Open the rich view in a browser")
    p.set_defaults(func=cmd_residuals)

    # view
    p = trace_sub.add_parser("view", help="Open trace in the visualizer")
    p.add_argument("trace_file")
    p.set_defaults(func=cmd_view)
