#!/usr/bin/env python3
"""Render each FIX AI WG demo trace with the ponens visualizer and build a browsable index.

Produces `examples/fix_ai_wg/viewer/<slug>_{pass,fail}.html` (each a self-contained visualizer page)
plus `viewer/index.html`, and opens the index in a browser.

Run from anywhere:  python3 examples/fix_ai_wg/view.py [--no-open]
"""
import json
import os
import subprocess
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "viewer")

TITLES = {
    "stale_decisions": "1 · Latency-induced stale decisions",
    "tool_failures": "2 · Tool failures during execution",
    "memory_contamination": "3 · Memory contamination",
    "objective_change": "4 · Dynamic objective changes",
    "multi_agent": "5 · Multi-agent responsibility",
    "reasoning_provenance": "6 · Missing reasoning provenance",
}


def render(trace_file, out_html):
    r = subprocess.run(["ponens", "trace", "view", os.path.join(HERE, trace_file), "-o", out_html],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! failed to render {trace_file}: {r.stderr.strip()[:160]}", file=sys.stderr)


def main():
    os.makedirs(OUT, exist_ok=True)
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    rows = []
    for c in manifest["cases"]:
        slug = c["slug"]
        ph, fh = f"{slug}_pass.html", f"{slug}_fail.html"
        render(c["pass_file"], os.path.join(OUT, ph))
        render(c["fail_file"], os.path.join(OUT, fh))
        rows.append((TITLES.get(slug, slug), c["policy"], ph, fh))

    cards = "\n".join(f'''
      <div class="card">
        <div class="ct">{title}</div>
        <div class="cp"><code>{policy}</code></div>
        <div class="cl">
          <a class="pass" href="{ph}">✅ passing trace</a>
          <a class="fail" href="{fh}">❌ failing trace</a>
        </div>
      </div>''' for title, policy, ph, fh in rows)

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>FIX AI WG · six points — trace viewer</title>
<style>
 body{{font-family:Inter,-apple-system,"Segoe UI",Roboto,sans-serif;background:#f7f8fc;color:#1c1e2b;margin:0;padding:40px}}
 h1{{font-size:26px;margin:0 0 6px}} .sub{{color:#6b7280;margin:0 0 24px;max-width:760px}}
 .sub code{{background:#eef0f7;border-radius:4px;padding:1px 5px;font-size:.9em}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:16px;max-width:1120px}}
 .card{{background:#fff;border:1px solid #e6e8f0;border-radius:12px;padding:16px 18px}}
 .ct{{font-weight:700;font-size:15px;margin-bottom:8px}}
 .cp code{{background:#f4f5fa;border:1px solid #e6e8f0;border-radius:5px;padding:1px 6px;font-size:12px;color:#7c3aed}}
 .cl{{display:flex;gap:10px;margin-top:14px}}
 .cl a{{flex:1;text-align:center;text-decoration:none;padding:9px;border-radius:8px;font-size:13px;font-weight:600}}
 .pass{{background:#e8f7ee;color:#1a7f37;border:1px solid #b7e0c4}}
 .fail{{background:#fdecec;color:#cf222e;border:1px solid #f3c0c0}}
 .cl a:hover{{filter:brightness(.97)}}
</style></head><body>
 <h1>FIX AI WG · the six points — trace viewer</h1>
 <p class="sub">Each case rendered in the ponens visualizer — a passing and a failing trace, each stamped
 with its <code>policy_evaluations</code> by <code>ponens trace check</code>. Open a trace to explore its
 actions, lineage DAG, and policy verdict.</p>
 <div class="grid">{cards}</div>
</body></html>"""
    idx = os.path.join(OUT, "index.html")
    open(idx, "w").write(html)
    print(f"  wrote {os.path.relpath(idx, ROOT)}  (+ {len(rows) * 2} trace views)")
    if "--no-open" not in sys.argv:
        webbrowser.open("file://" + idx)
    return 0


if __name__ == "__main__":
    sys.exit(main())
