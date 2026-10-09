# Offline pipeline tests

These tests run the whole agent with **stubbed** Apify, OpenAI and registry responses. They need
no keys and no network, so they earn 🟡 at most (see AGENTS.md → Verification). Only a live run
earns 🟢.

Run them:

```bash
python3 -m dd_agent test
```

The command runs every `python` code block in the `tests/*.md` files, top to bottom, as one script.
Prose between the blocks is documentation only.

| Test | What it proves |
|---|---|
| `test_verify_unit` | The quote matcher accepts whitespace/case differences and rejects absent text; a verified contradiction drops confidence to low |
| `test_pipeline` | End to end: 2 independent sources → 🟢 high; contradiction with the registry → `CONTRADICTED`; fabricated quote → `UNSUPPORTED`; US namesake excluded; Art. 9 skips counted; report renders |
| `test_goal_changes_content` | `procurement`, `hiring`, `sales` and `investor` produce four different search plans; anchors parse correctly |

## Setup and stubs

The fake web has three pages: a Czech news article and a blog that both report the same fine (two
independent publishers), and a US company with a similar name (a namesake that must be excluded).
The fake LLM returns one claim with a **fabricated quote**, which the code must catch, and one claim
that contradicts the registry's founding date.

```python
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OPENAI_API_KEY"] = "test"
os.environ["DD_LLM"] = "openai"  # stubbed below; keeps the test independent of installed CLIs
os.environ["APIFY_API_TOKEN"] = "test"

from dd_agent import agent  # noqa: E402
from dd_agent.models import Anchor, Claim, Contradiction, IdentityVerdict, Source, Subject  # noqa: E402
from dd_agent.report import to_html, to_markdown  # noqa: E402
from dd_agent.verify import quote_found, score_claim  # noqa: E402

PAGES = {
    "acme_news": {"url": "https://news.example.cz/acme-fine", "title": "Acme Logistika fined",
                  "text": "In 2023 Acme Logistika s.r.o. from Brno was fined CZK 400,000 by the labour inspectorate "
                          "for unpaid overtime. The company was founded in 2009.", "snippet_only": False},
    "acme_blog": {"url": "https://blog.other.com/acme", "title": "Acme Logistika review",
                  "text": "Acme Logistika s.r.o. paid a labour inspectorate fine in 2023 after an overtime audit.",
                  "snippet_only": False},
    "namesake": {"url": "https://acme-logistics.us", "title": "Acme Logistics Inc. Texas",
                 "text": "Acme Logistics Inc. is a trucking firm in Austin, Texas, sued in 2024 for fraud.",
                 "snippet_only": False},
}


def fake_search(query, token, max_results=3):
    return list(PAGES.values())


def fake_llm(system, user, max_tokens=4000):
    if "resolve identity" in system:
        ids = {p["url"]: sid for sid, p in _ids(user).items()}
        return {"verdicts": [
            {"source_id": ids["https://news.example.cz/acme-fine"], "match": "same", "reason": "Brno s.r.o."},
            {"source_id": ids["https://blog.other.com/acme"], "match": "same", "reason": "same name, s.r.o."},
            {"source_id": ids["https://acme-logistics.us"], "match": "different", "reason": "US namesake"},
        ]}
    if "outreach" in system:
        return {"message": "Hello"}
    ids = {p["url"]: sid for sid, p in _ids(user).items()}
    news, blog = ids.get("https://news.example.cz/acme-fine"), ids.get("https://blog.other.com/acme")
    if not news:
        return {"answer": "Nothing.", "claims": [], "gaps": ["none"]}
    return {"answer": "A labour fine in 2023 is reported.", "claims": [
        {"statement": "Fined CZK 400,000 for unpaid overtime in 2023", "kind": "fact",
         "evidence": [{"source_id": news, "quote": "was fined CZK 400,000 by the labour inspectorate"},
                      {"source_id": blog, "quote": "paid a labour inspectorate fine in 2023"}],
         "relevance": "Labour compliance"},
        {"statement": "Founded in 2009", "kind": "fact",
         "evidence": [{"source_id": news, "quote": "The company was founded in 2009."}],
         "contradicted_by": [{"source_id": "R1", "quote": "Date established: 2012-05-01", "note": "registry says 2012"}]},
        {"statement": "CEO convicted of embezzlement", "kind": "fact",
         "evidence": [{"source_id": news, "quote": "the CEO was convicted of embezzlement"}]},
    ], "gaps": ["No court records checked"], "special_category_skipped": 1}


def _ids(user):
    out, cur = {}, None
    for line in user.splitlines():
        if line.startswith("[W"):
            cur = line[1:line.index("]")]
        elif cur and line.startswith("URL: "):
            out[cur] = {"url": line[5:].strip()}
    return out


def fake_resolve(subject, log):
    res = agent.Resolution()
    res.sources = [Source(id="R1", url="https://ares.gov.cz/x", title="ARES", origin="registry",
                          publisher="ares.gov.cz (official)",
                          text="Business name: Acme Logistika s.r.o.\nDate established: 2012-05-01\n"
                               "Insolvency register (IR): no record\nCurrent managing director (jednatel): Jan Novák (since 2012-05-01)")]
    res.people = [{"name": "Jan Novák", "role": "jednatel", "since": "2012", "until": None, "current": True}]
    res.company, res.hint = "Acme Logistika s.r.o.", "Brno"
    res.entity = {"name": "Acme Logistika s.r.o.", "ico": "12345678"}
    return res
```

## test_verify_unit: the quote check and the confidence rules

```python
def test_verify_unit():
    assert quote_found("fined  CZK 400,000", "was Fined CZK 400,000 by")
    assert not quote_found("convicted of embezzlement", "was fined CZK 400,000")
    src = {"W1": Source(id="W1", url="u", title="t", text="alpha beta gamma delta", origin="web", publisher="a.com")}
    c = score_claim(Claim(id="C", question_id="q", statement="s", kind="fact", source_ids=["W1"],
                          quotes=["beta gamma"]), src, {"W1": IdentityVerdict(source_id="W1", match="same", reason="")})
    assert c.confidence == "medium"
    c = score_claim(Claim(id="C", question_id="q", statement="s", kind="fact", source_ids=["W1"], quotes=["beta gamma"],
                          contradicted_by=[Contradiction(source_id="W1", quote="delta", note="")]), src,
                    {"W1": IdentityVerdict(source_id="W1", match="same", reason="")})
    assert c.confidence == "low" and "CONTRADICTED" in c.flags
```

## test_pipeline: full run with stubs

```python
def test_pipeline():
    agent.apify.search = fake_search
    agent.llm.chat_json = fake_llm
    agent.resolve = fake_resolve
    subject = Subject(name="Acme Logistika", kind="organization", anchor=Anchor.parse("city:Brno"), goal="procurement")
    report, run_dir = agent.run(subject, log=lambda *_: None)

    claims = {c.statement: c for f in report.findings for c in f.claims}
    fine = claims["Fined CZK 400,000 for unpaid overtime in 2023"]
    assert fine.confidence == "high", fine            # 2 independent publishers, both verified
    founded = claims["Founded in 2009"]
    assert founded.confidence == "low" and "CONTRADICTED" in founded.flags
    fake = claims["CEO convicted of embezzlement"]
    assert fake.confidence == "low" and "UNSUPPORTED" in fake.flags   # hallucinated quote caught
    assert any(v.match == "different" for v in report.identity)       # namesake excluded
    assert report.suppressed_special_category >= 1
    assert all("acme-logistics.us" not in s.url for f in report.findings for c in f.claims
               for s in report.sources if s.id in c.source_ids)
    html, md = to_html(report), to_markdown(report)
    assert "UNSUPPORTED" in html and "Acme Logistics Inc. Texas" in md
    assert "How this report was built" in md and "How this report was built" in html  # R12 / A9
    import re as _re
    assert int(_re.search(r"(\d+) claim\(s\) whose quote was not found", md).group(1)) >= 1
    (run_dir / "report.html").write_text(html, encoding="utf-8")
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    print("report:", run_dir / "report.html")
```

## test_goal_changes_content: the goal changes the research, not just the headings

```python
def test_goal_changes_content():
    s = lambda g, k="organization": Subject(name="Acme", kind=k, anchor=Anchor.parse("city:Brno"), goal=g)
    plans = {g: set(agent.plan_queries(s(g), agent.get_goal(g), fake_resolve(None, None))) for g in
             ("procurement", "hiring", "sales", "investor")}
    assert len({frozenset(v) for v in plans.values()}) == 4  # every goal plans different searches
    assert Anchor.parse("02713209").type == "ico" and Anchor.parse("https://x.cz").type == "url"
```

## test_llm_backends: JSON extraction and backend selection (ADR-0011)

Every backend must yield one JSON object. The extractor tolerates code fences and surrounding prose,
and refuses replies with no object. `available()` reports an unknown backend or a missing key instead
of failing later.

```python
def test_llm_backends():
    from dd_agent import llm
    assert llm.extract_json('{"a": 1}') == {"a": 1}
    assert llm.extract_json('Sure!\n```json\n{"a": [1, 2]}\n```\nDone.') == {"a": [1, 2]}
    assert llm.extract_json('text before {"a": {"b": "}"}} text after') == {"a": {"b": "}"}}
    for bad in ("no json here", "[1, 2]"):
        try:
            llm.extract_json(bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError:
            pass
    old = os.environ.get("DD_LLM")
    try:
        os.environ["DD_LLM"] = "nonsense"
        ok, reason = llm.available()
        assert not ok and "unknown" in reason
        os.environ["DD_LLM"] = "openai"
        saved = os.environ.pop("OPENAI_API_KEY", None)
        ok, reason = llm.available()
        assert not ok and "OPENAI_API_KEY" in reason
        if saved is not None:
            os.environ["OPENAI_API_KEY"] = saved
    finally:
        os.environ["DD_LLM"] = old or "openai"
```

## Runner

```python
if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
```
