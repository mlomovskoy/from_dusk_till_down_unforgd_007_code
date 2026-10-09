# Due Diligence Agent: Case 01, Social Media Deep Research

You give it a **subject**, **one anchor** and a **goal**. It returns a report in which every claim
links to a source, has a confidence level, and is marked as fact or inference. The report also
lists contradictions between sources and the questions it could not answer.

```
subject + anchor + goal
   │
   ├─1 resolve   Czech registry (ARES) pins down WHICH entity; lists look-alike companies
   ├─2 plan      the goal decides the questions and the search queries
   ├─3 collect   Apify RAG Web Browser (existing actor) fetches public pages
   ├─4 identity  LLM marks each page same / possible / different entity → namesakes excluded
   ├─5 extract   LLM answers each question: claims + verbatim quotes + contradictions + gaps
   └─6 verify    CODE checks each quote really is in the source and assigns confidence by rules
```

## How it works

- **Identity first.** The Czech registry (ARES) pins down *which* entity is meant. Same-name companies are
  listed as look-alikes. If the name and anchor still match several records, the agent does **not
  guess**: it lists the candidates and says so.
- **The goal drives the research.** Each goal (`procurement`, `hiring`, `sales`) has its own questions and
  its own search queries (`dd_agent/goals.py`). The same subject with a different goal gives a different report.
- **Namesakes are excluded.** Each web page is marked same / possible / different entity before any
  claim is taken from it.
- **Evidence, not summaries.** Every claim must carry a verbatim quote. Code checks that the quote is
  really in the source (`dd_agent/verify.py`), and a claim that fails is kept and flagged `UNSUPPORTED`.
- **Confidence is set in code, not by the LLM:** 🟢 high = official registry or 2+ independent publishers ·
  🟡 medium = single publisher, or an inference · 🔴 low = unsupported, contradicted, or possibly a
  different entity.
- **Honest about gaps.** "Web search did not run" is never shown as "no evidence found". Every source is
  labelled `LIVE`, `CACHED` or `MOCK`.

## Setup

```bash
cd from_dusk_till_down_unforgd_007_code
pip install "httpx>=0.27" "pydantic>=2.8"   # see requirements.md
cp .env.example .env                     # add OPENAI_API_KEY and APIFY_API_TOKEN
```

The agent runs without keys, but reports only the registry data. Each missing key is
stated in the report's limitations section.

## Run

```bash
python -m dd_agent serve                                   # web form → http://localhost:8008
python -m dd_agent run "Etnetera Activate" --kind organization --anchor ico:02713209 --goal procurement
python -m dd_agent run "<Full Name>" --kind person --anchor ico:<IČO of their company> --goal hiring
python -m dd_agent run "Etnetera" --kind organization --anchor city:Praha --goal sales   # ambiguous → candidates
python -m dd_agent run ... --replay runs/<run_id>          # re-analyse cached pages, labelled CACHED
python -m dd_agent goals                                   # goals and their questions
python -m dd_agent purge                                   # delete raw scraped data after judging
python -m dd_agent test                                    # offline tests in tests/*.md (Apify + OpenAI stubbed)
```

Each run writes its output to `runs/<run_id>/`: `report.html`, `report.md`, `report.json` and `raw_sources.json`.

## How the briefing rules are covered

| Briefing rule | How the agent meets it |
|---|---|
| Inputs: entity, one anchor, a goal | `name`, `--kind`, `--anchor` (`ico:` / URL / `city:` / text), `--goal` |
| Every claim links to a source | Each claim cites source IDs and verbatim quotes, and the sources table links to the URLs |
| Facts are split from inference | Each claim is marked `fact` or `inference`; an inference never gets more than medium confidence |
| Gaps are stated explicitly | Each question has an "Unknown / gaps" list. If the web search didn't run, the report says so instead of "nothing found" |
| Switching the goal changes the content | `procurement`, `hiring` and `sales` ask different questions and run different queries. `sales` also adds an outreach draft |
| Identity resolution (namesakes, look-alikes) | A registry IČO pins down the entity, other companies with the same name are listed, and web pages about a different entity are excluded |
| Contradictions are flagged | Conflicting quotes are checked against their sources, and a confirmed conflict sets the claim to `CONTRADICTED` with low confidence |
| Confidence level per claim | Computed by code, not by the LLM: 🟢 official registry or 2+ independent publishers · 🟡 single publisher · 🔴 unsupported, contradicted or uncertain identity |
| Use existing Apify actors, no own scrapers | `apify/rag-web-browser`. ARES is an official public API |
| No trustworthiness, personality or credit scores | None are produced; the prompt forbids them and the report says so |
| No GDPR Art. 9 inference | The prompt forbids it, skipped items are counted in the report, and home addresses and birth dates from the registry are dropped |
| Raw data deleted after judging | `python -m dd_agent purge` |
| Live vs cached vs mock labelling | Every source is labelled `LIVE`, `CACHED` or `MOCK`. There is no mock data |

**Hallucination check:** if the LLM cites a quote that doesn't appear in the source, the claim stays
in the report but is flagged `UNSUPPORTED` and marked 🔴. That makes hallucinations visible instead
of hiding them.

## Known limitations
- Registry coverage is Czech only (ARES). For foreign entities, legal status comes from web sources only.
- Courts, sanctions lists and LinkedIn are covered only where they show up in Google results. The agent never logs in anywhere.
- The identity check and claim extraction depend on the LLM. The quote check limits the damage when the LLM is wrong, but it can't catch a correct quote that has been misread.

## License

[MIT](LICENSE). Built during From Dusk Till Dawn #01 (Agents 0.0.7, Prague, 8–9 Oct 2026) by team UNFORGD.
