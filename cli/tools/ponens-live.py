#!/usr/bin/env python3
"""Serve `ponens trace view` and reload the page whenever the trace changes.

`ponens trace view` builds a SELF-CONTAINED page: the trace is embedded as a JSON block and parsed
once at load, which is what makes the file shareable and what stops it from ever updating. Watching
the file and rebuilding is therefore the whole job - there is no live mode to switch on.

This does not reimplement the viewer. Every rebuild shells out to `ponens trace view -o`, so whatever
that renders is exactly what you see, and a change to the viewer needs no change here. The only thing
added to the page is a few lines that poll for the trace's modification time and reload when it moves.

    python3 ponens-live.py ~/Src/cl-sample-project/payments/.codelogician/reasoning-trace.json

Open http://127.0.0.1:8787. Leave it running beside the agent; every save redraws it.
"""
from __future__ import annotations

import argparse
import http.server
import os
import pathlib
import socketserver
import subprocess
import sys
import tempfile
import threading
import webbrowser

# Injected before </body>. Polls the mtime endpoint and reloads when it moves. Deliberately tiny and
# dependency-free: the page is the product, this is scaffolding around it.
RELOAD = """
<script>
(function () {
  var last = null;
  setInterval(function () {
    fetch('/__mtime', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (m) {
        if (last === null) { last = m; return; }
        if (m !== last) location.reload();
      })
      .catch(function () { /* the server went away; keep showing what we have */ });
  }, 1000);
})();
</script>
"""


def build(trace: pathlib.Path) -> bytes:
    """The viewer page for the trace as it is right now, with the reloader appended."""
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp) / "view.html"
        r = subprocess.run(
            [sys.executable, "-m", "ponens.cli", "trace", "view", str(trace), "-o", str(out)],
            capture_output=True, text=True,
        )
        if r.returncode != 0 or not out.exists():
            detail = (r.stderr or r.stdout or "no output").strip()[:2000]
            return (f"<pre style='padding:24px;font:13px ui-monospace,monospace;color:#fca5a5;"
                    f"background:#0f172a'>ponens trace view failed:\n\n{detail}</pre>").encode()
        html = out.read_text()
    # The LAST `</body>`, not the first. The viewer's print function builds a page inside a
    # template literal, so the file carries `</body>` twice; replacing the first dropped a
    # <script> block into a JS string, whose `</script>` closed the viewer's own script tag
    # early and spilled the rest of viewer.js onto the page as text.
    at = html.rfind("</body>")
    return (html + RELOAD if at < 0 else html[:at] + RELOAD + html[at:]).encode()


def serve(trace: pathlib.Path, port: int, open_browser: bool) -> None:
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):                                    # noqa: N802 - http.server's spelling
            if self.path.startswith("/__mtime"):
                body = str(trace.stat().st_mtime_ns if trace.exists() else 0).encode()
                self._send(body, "text/plain")
                return
            self._send(build(trace), "text/html; charset=utf-8")

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):                       # keep the console for real news only
            return

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with Server(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}"
        print(f"  watching {trace}")
        print(f"  serving  {url}   (ctrl-c to stop)")
        if open_browser:
            threading.Timer(0.4, lambda: webbrowser.open(url)).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  stopped")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trace", nargs="?", default=".codelogician/reasoning-trace.json",
                    help="the trace to watch (default: this project's record)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    a = ap.parse_args()
    trace = pathlib.Path(a.trace).expanduser().resolve()
    if not trace.exists():
        print(f"no such trace: {trace}", file=sys.stderr)
        return 1
    os.chdir(trace.parent)      # so `ponens trace view` resolves anything relative to the record
    serve(trace, a.port, not a.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
