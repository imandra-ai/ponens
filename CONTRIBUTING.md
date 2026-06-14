# Contributing to ponens

Thanks for your interest in contributing! This project defines open standards and tooling for auditable AI agent behavior — the trace/policy specifications, the policy gallery, and the `ponens` CLI. Community input is essential to making them broadly useful.

## Ways to contribute

### Adding a new policy

Policies live in `gallery/policies/` as JSON files. To add one:

1. Fork the repo and create a branch.
2. Create a new JSON file in `gallery/policies/` following the schema of existing policies. The filename must be `<id>.json`. At minimum, each policy needs:
   - `id` — unique snake_case identifier (must match the filename)
   - `name` — human-readable name
   - `category` — one of: auditability, communication, conformance, reasoning, safety, security, structural, workflow
   - `severity` — error, warning, or info
   - `description` — what the policy enforces and why
   - `formula` — the LTL formula encoding the policy
   - `domain` — the applicable domain (e.g., general, payments, react, xstate)
   - `rationale` — why this policy matters
   - `examples` — both a passing and a failing example (`passes` and `fails`)
3. Add your policy's ID to `gallery/policies/_index.json`.
4. Regenerate the machine-readable catalog and commit it:
   ```bash
   python3 scripts/build_index.py
   ```
   This validates every policy and rebuilds `gallery/policies/_catalog.json` — the
   denormalized, content-hashed index that tooling (e.g. the `ponens` CLI) pulls
   and searches. The file is generated; do not hand-edit it.
5. Open a pull request with a clear description of what the policy enforces.

CI runs `python3 scripts/build_index.py --check` on every PR: it fails if a policy
is malformed, if its ID is missing from `_index.json`, or if `_catalog.json` is out
of date. If the reference compiler (`ponens`) is available, each `formula` is also
compiled; policies that need a newer compiler are recorded in the catalog as
`reference_compiler: "unsupported"` rather than rejected.

### Improving the specification

The specifications live in `spec/` (the Trace, Policy, and Review-Case specs, the CLI
sync model, and the IML/ImandraX formal model under `spec/iml-model/`). If you'd like
to propose changes:

- **Clarifications and typo fixes** — open a PR directly.
- **Substantive changes** (new fields, changed semantics, new artifact types) — open an issue first to discuss the motivation and design before writing a PR.

### Improving the CLI

The CLI lives in `cli/`. Install it with `pip install -e ./cli` and run `pytest` from
`cli/`. Note: the hub-integration tests require a running hub backend; the local
toolchain (compiler, registry, `trace check`) is exercised offline in CI.

## Development

The website lives in `website/` (see its README to run it locally).

The one generated artifact is `gallery/policies/_catalog.json`, rebuilt from the
individual policy files with `python3 scripts/build_index.py` (pure stdlib). Run it
after adding or editing a policy and commit the result.

## Pull request guidelines

- Keep PRs focused — one policy, one spec change, or one fix per PR.
- For policies, include realistic examples (both passing and failing traces).
- Run `python3 scripts/build_index.py` after gallery changes and commit the catalog.
- Use clear commit messages describing what changed and why.

## Reporting issues

Use [GitHub Issues](https://github.com/imandra-ai/ponens/issues) for:

- Bugs in the site or policies
- Requests for new policy domains or categories
- Spec ambiguities or gaps
- Questions about how to use the policy language

## Code of conduct

Be respectful and constructive. We're building shared standards — good-faith disagreement on design decisions is welcome, personal attacks are not.
