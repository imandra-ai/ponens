# Trace schema bundle

Machine-readable projections of the Trace Specification — JSON Schema for wire
validation, plus the IML schema the JSON is derived from.

```
trace.v1_0/  schema.json + example.json
trace.v1_1/  schema.json + examples/
trace.v1_4/  schema.json + schema.iml + concretize.iml + concrete_schema.iml + Makefile
```

The canonical prose specs live one level up in [`../`](..) (`TRACE_SPEC_v1_6.md` etc.);
these are the derived schemas (see Trace Spec §16, "Interchange Projection").

Provenance: imported from the `imandra-ai/reasoning-policies` repository.

> **Note:** `trace.v1_4/schema.json` does **not** yet include the **residual surface**
> added in Trace Spec v1.5 (§13). Regenerate the JSON schema from `schema.iml` (with a
> `residuals` field) to produce a `trace.v1_5/` bundle.
