# ponens

**Author, govern, and validate the reasoning traces of AI coding agents.**

`ponens` is an open, reasoner-agnostic toolchain for capturing what an AI agent
actually did — its actions, artifacts, proofs, and counterexamples — and checking
that work against computable governance policies. It turns a reasoning trace from a
throwaway log into an auditable, policy-governed object.

The name is from *modus ponens* — the rule of inference that derives a conclusion
from its premises (`P → Q`, `P ⊢ Q`). That is exactly what the tool does to a trace:
given the policies and the recorded work, it derives whether the reasoning holds.

> Website & policy gallery: **https://ponens.dev**

---

## What's in this repo

This is the monorepo for the whole open ecosystem:

| Path | What it is |
|---|---|
| [`cli/`](cli/) | The `ponens` command-line tool — trace authoring, the LTL policy compiler, the policy registry client, and the git/hub sync model. |
| [`gallery/`](gallery/) | The community policy gallery — versioned, content-hashed policy definitions and the generated `_catalog.json` the CLI pulls. |
| [`spec/`](spec/) | The open standards — the Trace, Policy, and Review-Case specifications, the CLI sync model, and the IML/ImandraX formal model. |
| [`viewer/`](viewer/) | The interactive trace visualizer (flow, lineage, DAG, reasoning funnel, policies dashboard). |
| [`examples/`](examples/) | Sample reasoning traces. |
| [`website/`](website/) | The `ponens.dev` site. |
| [`scripts/`](scripts/) | Build tooling (the gallery catalog builder). |

The CLI talks to a **TraceHub** backend for hosted collaboration, but TraceHub is just
one backend — the trace format, policies, and local gate are all backend-agnostic.

---

## Install

```bash
# from PyPI (once published)
pip install ponens

# or from this repo
pip install "ponens @ git+https://github.com/imandra-ai/ponens.git#subdirectory=cli"

# or for local development
pip install -e ./cli
```

## Quickstart

```bash
# pull the policy gallery and search it
ponens registry update
ponens policies search payments

# add a policy to a trace and check it — fully offline
ponens policies add tests_before_commit --into ./trace.json
ponens trace check ./trace.json

# bind the trace to the current commit and push to a TraceHub backend
ponens bind && ponens push
```

The local gate (`ponens trace check`) runs with no server — the hub is only for
sharing and governing the result. See [`spec/CLI_SYNC_MODEL_v0_1.md`](spec/CLI_SYNC_MODEL_v0_1.md)
for the full git/hub sync model and [`AGENT_PROMPT.md`](AGENT_PROMPT.md) for driving the
whole workflow from an AI agent.

## Contributing

New policies, spec improvements, and tooling fixes are welcome — see
[`CONTRIBUTING.md`](CONTRIBUTING.md). Every gallery policy is validated (and, when the
reference compiler is available, compiled) in CI before it merges.

## License

MIT — see [`LICENSE`](LICENSE).
