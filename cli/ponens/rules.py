"""Why a trace was rejected - not only what tripped.

`trace validate` named the violation and never the rule. "action 1 is in two meta-actions (m1 and
t1)" is a statement about your data; it is not a statement that nesting is expressed with
`parent_id` rather than by containment, which is the thing you got wrong. An author who built a
deliberate parent/child structure reads that line as a description of what they built. The rule was
in the spec the whole time and the validator never pointed at it.

So each error carries a rule: one or two sentences of the thing being enforced, and the section of
the spec that says it. Errors that break the same rule are grouped, because a single structural
mistake produced eight identical lines and the reader had to notice they were all one thing.

Nothing here decides validity. `validate_trace` owns that; this only explains what it found, so a
message can be improved without touching what is enforced.
"""

import re

SPEC = "TRACE_SPEC v1.14"


def _vocab():
    """The closed vocabularies, so a rule can SAY what was allowed.

    "invalid kind 'bounded'" leaves the author to go and find the list. Imported late: trace.py
    imports this module, so a module-level import would be circular.
    """
    from . import trace as t
    return {
        "residual-kind": ("residual kinds", t.RESIDUAL_KINDS, "§13.2 Residual semantics"),
        "residual-severity": ("severities", t.RESIDUAL_SEVERITIES, "§13.2 Residual semantics"),
        "residual-status": ("statuses", t.RESIDUAL_STATUSES, "§13.2 Residual semantics"),
        "meta-source": ("meta-action sources", t.META_SOURCES, "§8.4 Meta-actions, source and fidelity"),
        "meta-status": ("meta-action statuses", t.META_STATUSES, "§8.4 Meta-actions"),
    }


# Order matters only for readability: the first rule whose pattern matches an error claims it.
RULES = [
    {
        "id": "meta-action-membership",
        "match": r"is in two meta-actions",
        "rule": "An action belongs to at most one meta-action. Nesting is expressed by `parent_id` "
                "on the child, NOT by repeating the child's members in the parent - a parent's own "
                "`action_ids` are only the steps no child of it covers, and may be empty.",
        "cite": "§8.4 Meta-actions, \"Overlay, ordered, non-overlapping\" and \"Hierarchy via parent_id\"",
    },
    {
        "id": "meta-action-backref",
        "match": r"meta_action_id '.*' disagrees with membership",
        "rule": "An action's `meta_action_id` and its meta-action's `action_ids` are one fact written "
                "twice. Whichever you set, set both, and to the same meta-action.",
        "cite": "§8.4 Meta-actions",
    },
    {
        "id": "dangling-reference",
        "match": r"does not exist|is not a known artifact",
        "rule": "A trace is self-contained: every id it mentions must resolve inside it. A reference "
                "to something absent cannot be reviewed, so it is an error rather than a gap - record "
                "a genuine gap as a residual instead.",
        "cite": "§7.1 Canonical artifact model, §13.1 Residuals",
    },
    {
        "id": "data-flow-order",
        "match": r"consumed but never produced|produced later by action|data-flow cycle",
        "rule": "Evidence flows forward. An action's input must have been produced by an EARLIER "
                "action, so the record can be replayed in the order it happened - an input produced "
                "later, or never, means the reasoning cannot be reconstructed from the trace.",
        "cite": "§8.1 Canonical action model, §7.1 Canonical artifact model",
    },
    {
        "id": "verification-lineage",
        "match": r"does not derive from an? (VerificationGoal|IMLModel)",
        "rule": "A verdict must trace back to the thing it is about: VerificationResult -> "
                "VerificationGoal -> IMLModel. Break the chain and the trace says something was "
                "proved without saying what was proved, or about which model.",
        "cite": "§10.3 Verification goals, §10.4 Verification results",
    },
    {
        "id": "phase-coverage",
        "match": r"not grouped into any phase meta-action",
        "rule": "Under --strict every reasoning, change and test action belongs to a phase "
                "meta-action. A reviewer triages a handful of phases before drilling in, so a step "
                "outside them all is a step nobody reviews.",
        "cite": "§8.4 Meta-actions",
    },
    {
        "id": "projection-raises",
        "match": r"(enrich|grade_trace)\(\) raised",
        "rule": "A trace has to survive the projections its consumers run. This one is structurally "
                "well-typed and still crashes the tooling that reads it, which means some field "
                "holds a shape the readers do not expect.",
        "cite": "§2.2 Interchange model",
    },
    {
        "id": "duplicate-id",
        "match": r"^duplicate ",
        "rule": "Ids are unique within a trace. Lineage, membership and every reference are by id, so "
                "a repeated one silently merges two different things.",
        "cite": "§7.1 Canonical artifact model, §8.1 Canonical action model",
    },
    {
        "id": "closed-vocabulary",
        "match": r"invalid (kind|severity|status|source|defeater_kind|evidence_strength)",
        "rule": "This field is a CLOSED vocabulary, not free text. The value has to mean the same "
                "thing to everyone reading the trace, so a reviewer can count and compare across "
                "traces that different tools produced.",
        "cite": "§13.2 Residual semantics, §8.4 Meta-actions, §10.12 Oracle attribution",
        "vocab": ["residual-kind", "residual-severity", "residual-status", "meta-source", "meta-status"],
    },
    {
        "id": "evidence-honesty",
        "match": r"graded '.*', never higher|evidence_strength .* on an unestablished",
        "rule": "An oracle may not claim more strength than its mechanism can deliver. The ladder is "
                "the whole point of attribution: if anything can call itself proved, a reviewer "
                "learns nothing from the word.",
        "cite": "§10.12 Oracle attribution",
    },
    {
        "id": "missing-identity",
        "match": r"missing.*'(trace_id|id|artifact_id|policy_id|name)'|missing/non-(string|integer) 'id'",
        "rule": "Every node needs a stable id. Without one it cannot be referenced, superseded, or "
                "pointed at by a review - it can only be read once and then lost.",
        "cite": "§7.1 Canonical artifact model, §8.1 Canonical action model",
    },
    {
        "id": "missing-type",
        "match": r"missing '(type|artifact_type)'",
        "rule": "Every action and artifact is typed. The type is what lets a consumer that has never "
                "seen this producer's tooling still know what it is looking at.",
        "cite": "§7.1 Strict artifact type, §8.1 Strict action type",
    },
    {
        "id": "required-payload",
        "match": r"payload missing|payload\.oracle must be",
        "rule": "An artifact type that promises particular fields must carry them. A consumer is "
                "entitled to read them without first checking whether they are there.",
        "cite": "§10.12 Oracle attribution",
    },
    {
        "id": "shape",
        "match": r"must be a list|is not an object|is not a JSON object",
        "rule": "The container shapes are fixed by the interchange model. A trace that disagrees with "
                "them cannot be read by anything but its author.",
        "cite": "§2.2 Interchange model",
    },
]

for _r in RULES:
    _r["re"] = re.compile(_r["match"])


def rule_for(error):
    """The rule an error breaks, or None if nothing in the table claims it."""
    for r in RULES:
        if r["re"].search(str(error)):
            return r
    return None


def group(errors):
    """[(rule_or_None, [errors])] in the order the rules first appear.

    Grouping is the point: one structural mistake produced eight identical lines and a reader had to
    work out for themselves that they were all the same thing.
    """
    order, by_id = [], {}
    for e in errors:
        r = rule_for(e)
        key = r["id"] if r else None
        if key not in by_id:
            by_id[key] = (r, [])
            order.append(key)
        by_id[key][1].append(e)
    return [by_id[k] for k in order]


def _wrap(text, width, indent):
    out, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            out.append(indent + line)
            line = word
        else:
            line = f"{line} {word}" if line else word
    if line:
        out.append(indent + line)
    return out


LABEL_W = 9  # `error:` and `rule:` share one column, so a wrapped rule lines up under its errors.


def explain(rule, errors, indent, width=88):
    """The `rule:` block for one group - the rule, the vocabulary if it has one, the citation."""
    cont = indent + " " * LABEL_W
    body = _wrap(rule["rule"], width - len(cont), cont)
    lines = [indent + "rule:".ljust(LABEL_W) + body[0][len(cont):]] + body[1:]
    cites = []
    for key in rule.get("vocab", []):
        # Only the vocabulary the reader actually tripped over, and only the section that defines
        # it. Listing all five when they got one residual kind wrong is noise pretending to be help,
        # and citing oracle attribution at somebody whose residual severity is misspelled is worse
        # than citing nothing - it sends them to the wrong page.
        if not _mentions(key, errors):
            continue
        name, values, cite = _vocab()[key]
        lines += _wrap(f"{name}: {', '.join(sorted(values))}", width - len(cont), cont)
        if cite not in cites:
            cites.append(cite)
    lines += _wrap(f"{SPEC} {'; '.join(cites) if cites else rule['cite']}", width - len(cont), cont)
    return lines


_FIELD_OF = {
    "residual-kind": ("residual", "kind"), "residual-severity": ("residual", "severity"),
    "residual-status": ("residual", "status"), "meta-source": ("meta_action", "source"),
    "meta-status": ("meta_action", "status"),
}


def _mentions(key, errors):
    owner, field = _FIELD_OF[key]
    return any(str(e).startswith(owner) and f"invalid {field} " in str(e) for e in errors)


def render(errors, label="error:", indent="  ", limit=8, show_all=False):
    """Every error, grouped by the rule it breaks, each rule stated once.

    `limit` caps how many errors breaking an already-stated rule are listed before the rest are
    counted rather than shown; the total is always reported, because a validator that quietly drops
    errors is worse than a terse one.
    """
    lines = []
    for rule, errs in group(errors):
        # Only a group that shares a RULE may be summarised. The unclaimed group is a mixed bag -
        # "and 4 more that break the same rule" would be a lie about it, and the errors it hides
        # would be the ones nothing yet explains, which are exactly the ones worth reading.
        summarisable = rule is not None and not show_all and len(errs) > limit
        shown = errs[:limit] if summarisable else errs
        for e in shown:
            lines.append(indent + label.ljust(LABEL_W) + str(e))
        if len(shown) < len(errs):
            lines.append(indent + " " * LABEL_W
                         + f"... and {len(errs) - len(shown)} more that break the same rule "
                           f"(--all to list them)")
        if rule:
            lines += explain(rule, errs, indent)
            lines.append("")
    if lines and lines[-1] == "":
        lines.pop()
    return lines
