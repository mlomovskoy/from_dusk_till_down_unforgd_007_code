"""Tiny local web UI: a form that runs the agent and shows the report. Standard library only."""
import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from . import config
from .goals import GOALS
from .models import Anchor, Subject

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Due Diligence Agent</title><style>
:root{{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#7a1f2b}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#141413;--card:#1e1e1c;--text:#ecebe6;
--muted:#a3a29b;--line:#33322f;--accent:#e2808d}}}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 -apple-system,Segoe UI,Inter,sans-serif}}
main{{max-width:720px;margin:0 auto;padding:32px 16px}}h1{{margin:0 0 4px}}p{{color:var(--muted)}}
form,.runs{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:16px 0}}
label{{display:block;font-weight:600;margin:12px 0 4px}}input,select{{width:100%;padding:9px 10px;
border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font:inherit}}
button{{margin-top:16px;padding:10px 18px;border:0;border-radius:8px;background:var(--accent);color:#fff;
font-weight:700;font:inherit;cursor:pointer}}button[disabled]{{opacity:.6}}a{{color:var(--accent)}}
.hint{{font-size:12px;color:var(--muted)}}pre{{white-space:pre-wrap;font-size:12px;color:var(--muted)}}
</style></head><body><main>
<h1>🧛 Due Diligence Agent</h1>
<p>Subject + one anchor + a goal → report where every claim links to a source, facts are split from inference,
and gaps are stated.</p>
<form method="post" action="/run" onsubmit="this.querySelector('button').disabled=true;
this.querySelector('button').textContent='Researching… (1–3 min)'">
<label>Subject name</label><input name="name" required placeholder="Etnetera Activate a.s. / Jana Nováková">
<label>Subject type</label><select name="kind"><option value="organization">Organization</option>
<option value="person">Person</option></select>
<label>Anchor</label><input name="anchor" required placeholder="ico:02713209 · https://example.cz · city:Prague">
<div class="hint">One fact that pins down WHICH entity: Czech IČO, website, city, or employer.</div>
<label>Goal</label><select name="goal">{goals}</select>
<button type="submit">Run research</button>
<div class="hint" style="margin-top:8px">Apify {apify} · LLM {openai}</div>
</form>
<div class="runs"><b>Previous runs</b><ul>{runs}</ul></div>
</main></body></html>"""


def _runs() -> str:
    if not config.RUNS_DIR.exists():
        return "<li class='hint'>none yet</li>"
    items = []
    for d in sorted(config.RUNS_DIR.iterdir(), reverse=True)[:20]:
        if (d / "report.html").exists():
            items.append(f"<li><a href='/runs/{escape(d.name)}/report.html'>{escape(d.name)}</a></li>")
    return "".join(items) or "<li class='hint'>none yet</li>"


def _llm_label() -> str:
    from . import llm
    ok, reason = llm.available()
    return f"✓ {reason}" if ok else f"✗ {reason} (no analysis)"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            goals = "".join(f"<option value='{g.id}'>{escape(g.label)}</option>" for g in GOALS.values())
            self._send(200, PAGE.format(goals=goals, runs=_runs(),
                                        apify="✓" if config.apify_token() else "✗ (registry only)",
                                        openai=_llm_label()))
            return
        if self.path.startswith("/runs/"):
            parts = self.path.split("/")
            if len(parts) == 4 and parts[3] in ("report.html", "report.md", "report.json") and ".." not in parts[2]:
                f = config.RUNS_DIR / parts[2] / parts[3]
                if f.exists():
                    ctype = {"html": "text/html", "md": "text/markdown", "json": "application/json"}[f.suffix[1:]]
                    self._send(200, f.read_text(encoding="utf-8"), ctype + "; charset=utf-8")
                    return
        self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path != "/run":
            self._send(404, "not found", "text/plain")
            return
        form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()).items()}
        try:
            from .__main__ import run_and_save
            subject = Subject(name=form["name"].strip(), kind=form["kind"], anchor=Anchor.parse(form["anchor"]),
                              goal=form["goal"])
            run_dir = run_and_save(subject)
        except Exception as e:
            self._send(500, f"<pre>Run failed: {escape(type(e).__name__)}: {escape(str(e))}</pre>"
                            f"<a href='/'>back</a>")
            return
        self.send_response(303)
        self.send_header("Location", f"/runs/{run_dir.name}/report.html")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass


def serve(port: int) -> None:
    print(f"Due Diligence Agent on http://localhost:{port}")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
