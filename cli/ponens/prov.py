"""PROV-O interchange — export a ponens trace as W3C PROV (PROV-JSON).

Maps the trace's typed-artifact lineage onto the standard provenance vocabulary so a trace
interoperates with the PROV tooling ecosystem. The mapping is the normative profile in
`spec/PROV_INTERCHANGE_v0_1.md`; in brief:

    artifact              -> prov:Entity          (prov:type = ponens:<ArtifactType>)
    action                -> prov:Activity        (prov:type = ponens:<category>/<type>)
    assistant/model       -> prov:Agent
    artifact.producer_action_id -> wasGeneratedBy (entity <- activity)
    action.inputs[i]      -> used                 (activity -> entity)
    artifact.derived_from -> wasDerivedFrom       (generatedEntity <- usedEntity)
    artifact.supersedes   -> wasDerivedFrom {prov:type: prov:Revision}   (wasRevisionOf)
    artifact              -> wasAttributedTo agent
    action                -> wasAssociatedWith agent
    the trace itself      -> prov:Entity {prov:type: prov:Bundle}  (provenance-of-provenance)

ponens-native semantics PROV has no vocabulary for — residual `kind`/`defeater_kind`/`severity`/
`status`, verification verdicts, freshness — ride as `ponens:` attributes on the entities; their
meaning stays in ponens. Output is PROV-JSON:
https://www.w3.org/Submission/2013/SUBM-prov-json-20130424/
"""

PONENS_NS = "https://ponens.dev/ns#"
PREFIX = {"prov": "http://www.w3.org/ns/prov#", "ponens": PONENS_NS}


def _payload(a):
    return (a or {}).get("payload") or {}


def _eid(aid):
    return f"ponens:{aid}"


def _act(aid):
    return f"ponens:act-{aid}"


def _slug(s):
    return "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(s or "agent")) or "agent"


def _entity_attrs(a):
    """PROV + ponens attributes for an artifact entity. Native semantics ride as `ponens:` keys."""
    attrs = {"prov:type": f"ponens:{a.get('artifact_type', 'Artifact')}"}
    label = a.get("name") or a.get("summary")
    if label:
        attrs["prov:label"] = label
    if a.get("revision") is not None:
        attrs["ponens:revision"] = a["revision"]
    p = _payload(a)
    # Carry the load-bearing native fields so a PROV consumer at least SEES them (opaque to PROV).
    for k in ("kind", "defeater_kind", "severity", "status", "source", "analysis_kind"):
        if p.get(k) is not None:
            attrs[f"ponens:{k}"] = p[k]
    if p.get("status") is not None and a.get("artifact_type") == "VerificationResult":
        attrs["ponens:verdict"] = p["status"]
    return attrs


def to_prov_json(trace):
    """Return the PROV-JSON dict for `trace`."""
    arts = trace.get("artifacts", []) or []
    actions = trace.get("actions", []) or []
    art_ids = {a.get("artifact_id") for a in arts}
    act_ids = {a.get("id") for a in actions}

    doc = {"prefix": dict(PREFIX)}
    entity, activity, agent = {}, {}, {}
    wasGeneratedBy, used, wasDerivedFrom, wasAttributedTo, wasAssociatedWith = {}, {}, {}, {}, {}

    # Agent: the assistant that produced the trace (model recorded as an attribute).
    agent_id = f"ponens:agent-{_slug(trace.get('assistant') or 'agent')}"
    agent[agent_id] = {"prov:type": "prov:SoftwareAgent"}
    if trace.get("assistant"):
        agent[agent_id]["prov:label"] = trace["assistant"]
    if trace.get("model"):
        agent[agent_id]["ponens:model"] = trace["model"]

    # The trace itself is a Bundle entity — provenance-of-provenance.
    bundle_id = _eid(f"trace-{trace.get('trace_id', 'trace')}")
    bundle_attrs = {"prov:type": "prov:Bundle"}
    if trace.get("spec_version"):
        bundle_attrs["ponens:spec_version"] = trace["spec_version"]
    if trace.get("timestamp"):
        bundle_attrs["prov:generatedAtTime"] = trace["timestamp"]
    entity[bundle_id] = bundle_attrs
    wasAttributedTo[f"_:att-bundle"] = {"prov:entity": bundle_id, "prov:agent": agent_id}

    # Activities (actions).
    for a in actions:
        aid = a.get("id")
        cat, typ = a.get("category"), a.get("type")
        act_attrs = {"prov:type": f"ponens:{cat}/{typ}" if cat and typ else "ponens:Action"}
        if a.get("label"):
            act_attrs["prov:label"] = a["label"]
        activity[_act(aid)] = act_attrs
        wasAssociatedWith[f"_:assoc-{aid}"] = {"prov:activity": _act(aid), "prov:agent": agent_id}
        for i, inp in enumerate(a.get("inputs", []) or []):
            if inp in art_ids:
                used[f"_:u-{aid}-{i}"] = {"prov:activity": _act(aid), "prov:entity": _eid(inp)}

    # Entities (artifacts) + generation/derivation/attribution.
    for a in arts:
        aid = a.get("artifact_id")
        entity[_eid(aid)] = _entity_attrs(a)
        wasAttributedTo[f"_:att-{aid}"] = {"prov:entity": _eid(aid), "prov:agent": agent_id}
        pid = a.get("producer_action_id")
        if pid in act_ids:
            wasGeneratedBy[f"_:wgb-{aid}"] = {"prov:entity": _eid(aid), "prov:activity": _act(pid)}
        for i, parent in enumerate(a.get("derived_from", []) or []):
            if parent in art_ids:
                wasDerivedFrom[f"_:wdf-{aid}-{i}"] = {
                    "prov:generatedEntity": _eid(aid), "prov:usedEntity": _eid(parent)}
        sup = a.get("supersedes")
        if sup in art_ids:
            wasDerivedFrom[f"_:rev-{aid}"] = {
                "prov:generatedEntity": _eid(aid), "prov:usedEntity": _eid(sup),
                "prov:type": "prov:Revision"}

    for key, val in (("entity", entity), ("activity", activity), ("agent", agent),
                     ("wasGeneratedBy", wasGeneratedBy), ("used", used),
                     ("wasDerivedFrom", wasDerivedFrom), ("wasAttributedTo", wasAttributedTo),
                     ("wasAssociatedWith", wasAssociatedWith)):
        if val:
            doc[key] = val
    return doc
