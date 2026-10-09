"""Render a Report as Markdown and as a self-contained HTML page."""
from collections import Counter
from html import escape

from .models import Claim, Report

CONF_ICON = {"high": "🟢", "medium": "🟡", "low": "🔴"}


def _mode_summary(report: Report) -> str:
    counts = Counter(s.mode for s in report.sources)
    return ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "no sources"


def _identity(report: Report) -> dict:
    return {v.source_id: v for v in report.identity}


# ------------------------------------------------------------------ Markdown

def to_markdown(r: Report) -> str:
    s = r.subject
    ident = _identity(r)
    out = [f"# Due-diligence report: {s.name}",
           "",
           f"- **Goal:** {r.goal_label} — {r.goal_purpose}",
           f"- **Subject type:** {s.kind}  |  **Anchor:** {s.anchor.label()}",
           f"- **Run:** `{r.run_id}`  |  generated {r.generated_at}  |  sources {_mode_summary(r)}",
           "",
           "Confidence: 🟢 high = official registry or 2+ independent publishers · 🟡 medium = single publisher "
           "or interpretation · 🔴 low = unsupported, contradicted, or may be a different entity. "
           "Confidence is computed by code, not by the language model.",
           "",
           "## Identity resolution"]
    if r.resolved_entity:
        for k, v in r.resolved_entity.items():
            out.append(f"- **{k.replace('_', ' ')}:** {', '.join(v) if isinstance(v, list) else v}")
    else:
        out.append("- Entity could not be pinned to an official registry record.")
    if r.lookalikes:
        out += ["", "**Look-alike registry entities (not the subject):**" if r.resolved_entity.get("ico")
                else "**Registry candidates — the anchor did not single one out:**"]
        out += [f"- {l.name} — {l.detail} ({l.reason})" for l in r.lookalikes]
    excluded = [v for v in r.identity if v.match == "different"]
    if excluded:
        out += ["", "**Sources excluded as a different person/company:**"]
        src = {x.id: x for x in r.sources}
        out += [f"- [{v.source_id}] {src[v.source_id].title} — {v.reason}" for v in excluded]

    for f in r.findings:
        out += ["", f"## {f.question}", "", f"_{f.answer}_", ""]
        for c in f.claims:
            out.append(_md_claim(c, ident))
        if f.gaps:
            out += ["", "**Unknown / gaps:**"] + [f"- {g}" for g in f.gaps]

    if r.outreach_draft:
        out += ["", "## Draft outreach (NOT sent — for human review)", "", "> " + r.outreach_draft.replace("\n", "\n> ")]

    out += ["", "## Sources", ""]
    for x in r.sources:
        v = ident.get(x.id)
        tag = f" · identity: {v.match}" if v else ""
        out.append(f"- **[{x.id}]** `{x.mode}` [{x.title}]({x.url}) — {x.publisher}{tag} · fetched {x.fetched_at}"
                   + (" · snippet only" if x.snippet_only else ""))
    out += ["", "## Limitations & honesty notes", ""]
    if r.suppressed_special_category:
        out.append(f"- {r.suppressed_special_category} item(s) of GDPR Art. 9 special-category data were skipped.")
    out += [f"- {l}" for l in r.limitations]
    out.append("- This report gives no trustworthiness, personality or credit score by design.")
    return "\n".join(out) + "\n"


def _md_claim(c: Claim, ident) -> str:
    cites = ", ".join(f"[{sid}]{'' if ok else ' ⚠quote not found'}" for sid, ok in zip(c.source_ids, c.quote_verified))
    flags = f" `{' · '.join(c.flags)}`" if c.flags else ""
    line = f"- {CONF_ICON[c.confidence]} **{c.statement}** {cites}{flags}  \n  _{c.confidence}: {c.confidence_reason}_"
    for q, sid in zip(c.quotes, c.source_ids):
        if not sid.startswith("R"):
            line += f"\n  > [{sid}] “{q}”"
    for x in c.contradicted_by:
        line += f"\n  - ⚡ contradicted by [{x.source_id}]: “{x.quote}” — {x.note}"
    return line


# ------------------------------------------------------------------ HTML

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--text:#1d1d1b;--muted:#6b6b66;--line:#e4e3de;--accent:#7a1f2b;
--hi:#1f7a4d;--hi-bg:#e6f4ec;--md:#8a6100;--md-bg:#fbf1d9;--lo:#b0283a;--lo-bg:#fbe6e9;--code:#f0efea}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#141413;--card:#1e1e1c;--text:#ecebe6;
--muted:#a3a29b;--line:#33322f;--accent:#e2808d;--hi:#6fd3a0;--hi-bg:#173226;--md:#e8c06a;--md-bg:#3a2f14;
--lo:#f08a98;--lo-bg:#3d1c22;--code:#2a2a27}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:980px;margin:0 auto;padding:28px 16px 80px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:0 0 10px}
.meta{color:var(--muted);font-size:13px}.card{background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:18px 20px;margin:16px 0}
.badge{display:inline-block;font-size:11px;font-weight:700;letter-spacing:.03em;padding:2px 8px;border-radius:999px;
border:1px solid var(--line);margin-right:4px;white-space:nowrap}
.high{color:var(--hi);background:var(--hi-bg);border-color:transparent}
.medium{color:var(--md);background:var(--md-bg);border-color:transparent}
.low{color:var(--lo);background:var(--lo-bg);border-color:transparent}
.LIVE{color:var(--hi)}.CACHED{color:var(--md)}.MOCK{color:var(--lo)}
.claim{border-top:1px solid var(--line);padding:10px 0}.claim:first-of-type{border-top:0}
.stmt{font-weight:600}.why{color:var(--muted);font-size:13px}
blockquote{margin:6px 0 0;padding:4px 10px;border-left:3px solid var(--line);color:var(--muted);font-size:13px}
.contra{margin-top:6px;padding:6px 10px;border-radius:8px;background:var(--lo-bg);color:var(--lo);font-size:13px}
.answer{font-style:italic;margin-bottom:8px}.gaps{margin-top:10px;font-size:13px;color:var(--muted)}
.gaps b{color:var(--text)}a{color:var(--accent)}code{background:var(--code);padding:1px 5px;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:left;padding:6px 8px;
border-top:1px solid var(--line);vertical-align:top}th{color:var(--muted);font-weight:600}
.warn{padding:8px 12px;border-radius:8px;background:var(--md-bg);color:var(--md);margin:8px 0}
.legend span{margin-right:12px}.cite{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.draft{white-space:pre-wrap;padding:12px;border:1px dashed var(--line);border-radius:8px}
.table-wrap{overflow-x:auto}
"""


def _b(cls: str, text: str) -> str:
    return f'<span class="badge {escape(cls)}">{escape(text)}</span>'


def to_html(r: Report) -> str:
    s = r.subject
    ident = _identity(r)
    src = {x.id: x for x in r.sources}
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
             f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Due Diligence Report</title><style>{CSS}</style></head><body><main>",
             f"<h1>{escape(s.name)}</h1>",
             f"<div class='meta'>{escape(r.goal_label)} · {escape(s.kind)} · {escape(s.anchor.label())} · "
             f"run <code>{escape(r.run_id)}</code> · {escape(r.generated_at)}</div>",
             f"<div class='meta'>Purpose: {escape(r.goal_purpose)} · Sources: "
             + " ".join(_b(m, f"{m} {n}") for m, n in sorted(Counter(x.mode for x in r.sources).items())) + "</div>",
             "<div class='card legend'><span>" + _b("high", "HIGH") + "official registry or 2+ independent publishers"
             "</span><span>" + _b("medium", "MEDIUM") + "single publisher or interpretation</span><span>"
             + _b("low", "LOW") + "unsupported, contradicted or possibly another entity</span>"
             "<div class='meta' style='margin-top:6px'>Every quote is checked against its source by code; "
             "confidence is computed by rules, not by the language model.</div></div>"]

    # identity
    parts.append("<div class='card'><h2>Identity resolution</h2>")
    if r.resolved_entity:
        warn = r.resolved_entity.get("warning")
        rows = "".join(f"<tr><th>{escape(k.replace('_', ' '))}</th><td>"
                       f"{escape(', '.join(v) if isinstance(v, list) else str(v))}</td></tr>"
                       for k, v in r.resolved_entity.items() if k != "warning")
        parts.append(f"<table>{rows}</table>")
        if warn:
            parts.append(f"<div class='warn'>⚠ {escape(warn)}</div>")
    else:
        parts.append("<div class='warn'>Entity could not be pinned to an official registry record.</div>")
    if r.lookalikes:
        head = ("Look-alike registry entities — not the subject" if r.resolved_entity.get("ico")
                else "Registry candidates — the anchor did not single one out; add an IČO")
        parts.append(f"<p class='meta'><b>{head}:</b></p><ul>"
                     + "".join(f"<li>{escape(l.name)} <span class='meta'>— {escape(l.detail)}</span></li>"
                               for l in r.lookalikes) + "</ul>")
    excluded = [v for v in r.identity if v.match == "different"]
    if excluded:
        parts.append("<p class='meta'><b>Sources excluded as a different person/company:</b></p><ul>"
                     + "".join(f"<li><span class='cite'>[{v.source_id}]</span> "
                               f"<a href='{escape(src[v.source_id].url)}'>{escape(src[v.source_id].title)}</a>"
                               f" <span class='meta'>— {escape(v.reason)}</span></li>" for v in excluded) + "</ul>")
    parts.append("</div>")

    # findings
    for f in r.findings:
        parts.append(f"<div class='card'><h2>{escape(f.question)}</h2><div class='answer'>{escape(f.answer)}</div>")
        for c in f.claims:
            parts.append(_html_claim(c, src))
        if f.gaps:
            parts.append("<div class='gaps'><b>Unknown / gaps</b><ul>"
                         + "".join(f"<li>{escape(g)}</li>" for g in f.gaps) + "</ul></div>")
        parts.append("</div>")

    if r.outreach_draft:
        parts.append("<div class='card'><h2>Draft outreach " + _b("low", "NOT SENT") + "</h2>"
                     f"<div class='draft'>{escape(r.outreach_draft)}</div>"
                     "<p class='meta'>Draft for human review only. The agent never contacts the subject.</p></div>")

    # sources
    rows = []
    for x in r.sources:
        v = ident.get(x.id)
        rows.append(f"<tr id='{x.id}'><td class='cite'>{x.id}</td><td>{_b(x.mode, x.mode)}</td>"
                    f"<td><a href='{escape(x.url)}'>{escape(x.title[:110])}</a><div class='meta'>{escape(x.publisher)}"
                    f"{' · snippet only' if x.snippet_only else ''}</div></td>"
                    f"<td>{escape(v.match) if v else 'registry'}<div class='meta'>{escape(v.reason) if v else ''}</div></td>"
                    f"<td class='meta'>{escape(x.fetched_at)}</td></tr>")
    parts.append("<div class='card'><h2>Sources</h2><div class='table-wrap'><table><tr><th>ID</th><th>Mode</th>"
                 "<th>Source</th><th>Identity</th><th>Fetched</th></tr>" + "".join(rows) + "</table></div></div>")

    lim = list(r.limitations)
    if r.suppressed_special_category:
        lim.insert(0, f"{r.suppressed_special_category} item(s) of GDPR Art. 9 special-category data were skipped.")
    lim.append("No trustworthiness, personality or credit score is produced, by design.")
    parts.append("<div class='card'><h2>Limitations &amp; honesty notes</h2><ul>"
                 + "".join(f"<li>{escape(l)}</li>" for l in lim) + "</ul></div></main></body></html>")
    return "".join(parts)


def _html_claim(c: Claim, src) -> str:
    cites = " ".join(
        f"<a class='cite' href='#{sid}' title='{escape(src[sid].title) if sid in src else ''}'>[{sid}]</a>"
        + ("" if ok else _b("low", "quote not found"))
        for sid, ok in zip(c.source_ids, c.quote_verified))
    flags = "".join(_b("low" if f in ("UNSUPPORTED", "CONTRADICTED") else "medium", f) for f in c.flags)
    html = (f"<div class='claim'>{_b(c.confidence, c.confidence.upper())}{flags}"
            f"<span class='stmt'>{escape(c.statement)}</span> {cites}"
            f"<div class='why'>{escape(c.confidence_reason)}"
            + (f" · {escape(c.relevance)}" if c.relevance and c.relevance != "Official registry record" else "")
            + "</div>")
    for q, sid in zip(c.quotes, c.source_ids):
        if not sid.startswith("R"):
            html += f"<blockquote><span class='cite'>[{sid}]</span> “{escape(q)}”</blockquote>"
    for x in c.contradicted_by:
        html += (f"<div class='contra'>⚡ Contradicted by <span class='cite'>[{x.source_id}]</span>: "
                 f"“{escape(x.quote)}” — {escape(x.note)}</div>")
    return html + "</div>"
