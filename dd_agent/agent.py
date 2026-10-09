"""Due-diligence research agent: subject + anchor + goal -> report with traceable, scored claims.

Pipeline
  1. resolve   official registry (ARES) pins down WHICH entity we mean, lists look-alikes
  2. plan      the goal decides the questions and the search queries
  3. collect   Apify RAG Web Browser fetches public pages (or a cached run is replayed, labelled CACHED)
  4. identity  LLM marks each page same / possible / different entity (namesakes are excluded)
  5. extract   LLM answers each question with claims + verbatim quotes + contradictions + gaps
  6. verify    code checks every quote against the source and assigns confidence by fixed rules
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from . import config, llm
from .goals import Goal, Question, get_goal
from .models import (Claim, Contradiction, Finding, IdentityVerdict, LookAlike, Report, Source,
                     Subject)
from .sources import apify, ares
from .verify import score_claim

Log = Callable[[str], None]

PEOPLE_QUESTIONS = ("control", "leadership", "decision_makers", "roles", "experience", "role")
STATUS_QUESTIONS = ("legal_status", "stability", "profile", "roles", "experience", "role")
RISK_QUESTIONS = ("legal_risk", "stability", "legal_status")
STATUS_PREFIXES = ("Business name", "Legal form", "Date established", "Date dissolved", "Subject status",
                   "Former name", "Registered capital", "VAT ID", "Commercial register", "Registered office",
                   "Trade licence")
RISK_PREFIXES = ("Insolvency register", "Central register of bankrupts")


# ---------------------------------------------------------------- 1. resolve

class Resolution:
    def __init__(self):
        self.sources: list[Source] = []
        self.entity: dict = {}
        self.lookalikes: list[LookAlike] = []
        self.people: list[dict] = []
        self.hint = ""
        self.company = ""
        self.notes: list[str] = []


def _names_match(a: str, b: str) -> bool:
    ta, tb = set(ares.normalize_name(a).split()), set(ares.normalize_name(b).split())
    return bool(ta) and (ta <= tb or tb <= ta)


def _load_company(ico: str, res: Resolution, log: Log) -> dict | None:
    basic = ares.get_basic(ico)
    if not basic:
        res.notes.append(f"IČO {ico} was not found in the Czech registry (ARES).")
        return None
    res.sources.append(ares.basic_source(basic, "R1"))
    vr = ares.get_public_register(ico)
    if vr:
        res.sources.append(ares.register_source(vr, ico, "R2"))
        res.people = ares.people(vr)
    log(f"  registry: {basic.get('obchodniJmeno')} (IČO {ico}), {len(res.people)} officers/partners on record")
    return basic


def resolve(subject: Subject, log: Log) -> Resolution:
    res = Resolution()
    anchor = subject.anchor
    if anchor.type == "url":
        res.hint = urlparse(anchor.value if "//" in anchor.value else "//" + anchor.value).netloc.removeprefix("www.")
    elif anchor.type in ("city", "text"):
        res.hint = anchor.value

    try:
        if subject.kind == "organization":
            _resolve_org(subject, res, log)
        elif anchor.type == "ico":
            _resolve_person_by_company(subject, res, log)
    except Exception as e:  # registry outage must not kill the run
        res.notes.append(f"Registry lookup failed ({type(e).__name__}: {e}).")
    return res


def _resolve_org(subject: Subject, res: Resolution, log: Log) -> None:
    anchor = subject.anchor
    candidates = ares.search_by_name(subject.name, limit=10)
    chosen = None
    if anchor.type == "ico":
        chosen = _load_company(anchor.value, res, log)
        if chosen and not _names_match(subject.name, chosen.get("obchodniJmeno", "")):
            res.entity["warning"] = (f"Name given ('{subject.name}') differs from the registry name "
                                     f"for IČO {anchor.value} ('{chosen.get('obchodniJmeno')}').")
    else:
        pool = candidates
        if anchor.type in ("city", "text"):
            city = ares.normalize_name(anchor.value)
            pool = [c for c in candidates
                    if city in ares.normalize_name((c.get("sidlo") or {}).get("textovaAdresa", ""))] or candidates
        exact = [c for c in pool if ares.normalize_name(c.get("obchodniJmeno", "")) == ares.normalize_name(subject.name)]
        pick = exact if len(exact) == 1 else (pool if len(pool) == 1 else [])
        if pick:
            chosen = _load_company(pick[0]["ico"], res, log)
        elif candidates:
            res.notes.append(f"{len(pool)} registry entities match '{subject.name}' and the anchor does not "
                             f"single one out. Provide an IČO to resolve; registry facts are omitted.")
        else:
            res.notes.append("No Czech registry record found. Foreign registries are not covered, so legal "
                             "status is answered from web sources only.")

    if chosen:
        res.company = chosen.get("obchodniJmeno", subject.name)
        res.entity.update({"name": res.company, "ico": chosen["ico"],
                           "address": (chosen.get("sidlo") or {}).get("textovaAdresa"),
                           "established": chosen.get("datumVzniku")})
        res.hint = res.hint or (chosen.get("sidlo") or {}).get("nazevObce", "")
    for c in candidates:
        if chosen and c.get("ico") == chosen.get("ico"):
            continue
        res.lookalikes.append(LookAlike(
            name=c.get("obchodniJmeno", "?"),
            detail=f"IČO {c.get('ico')}, {(c.get('sidlo') or {}).get('textovaAdresa', 'address n/a')}, "
                   f"est. {c.get('datumVzniku', '?')}",
            reason="Different IČO than the resolved entity" if chosen else "Candidate — not disambiguated"))
    res.lookalikes = res.lookalikes[:6]


def _resolve_person_by_company(subject: Subject, res: Resolution, log: Log) -> None:
    basic = _load_company(subject.anchor.value, res, log)
    if not basic:
        return
    res.company = basic.get("obchodniJmeno", "")
    res.hint = _short_name(res.company)
    matches = [p for p in res.people if _names_match(subject.name, p["name"])]
    res.entity.update({"name": subject.name, "anchored_company": res.company, "ico": basic["ico"]})
    if matches:
        res.entity["registry_roles"] = [f"{p['role']} ({'current' if p['current'] else 'former'})" for p in matches]
    else:
        res.entity["warning"] = (f"'{subject.name}' is not listed among the registered officers/partners of "
                                 f"{res.company}. They may be an employee, or the anchor may be wrong.")


# ---------------------------------------------------------------- 2. plan

LEGAL_SUFFIX = re.compile(r",?\s+(a\.\s?s\.|s\.\s?r\.\s?o\.|spol\.\s?s\s?r\.\s?o\.|v\.\s?o\.\s?s\.|k\.\s?s\.|"
                          r"z\.\s?s\.|o\.\s?p\.\s?s\.|GmbH|AG|Inc\.?|Ltd\.?|LLC|B\.V\.|N\.V\.|SE|Co\.,? Ltd\.?)$",
                          re.IGNORECASE)


def _short_name(name: str) -> str:
    return LEGAL_SUFFIX.sub("", name.strip()).strip() or name

def plan_queries(subject: Subject, goal: Goal, res: Resolution) -> dict[str, list[str]]:
    """Returns query -> question ids."""
    plan: dict[str, list[str]] = {}

    def add(q: str, qid: str):
        q = " ".join(q.split())
        plan.setdefault(q, [])
        if qid not in plan[q]:
            plan[q].append(qid)

    name = _short_name(res.company if subject.kind == "organization" and res.company else subject.name)
    questions = goal.questions[subject.kind]
    for question in questions:
        for template in question.queries:
            add(template.format(name=name, hint=res.hint, company=res.company), question.id)

    people_q = next((q.id for q in questions if q.id in PEOPLE_QUESTIONS), None)
    if subject.kind == "organization" and people_q:
        current = [p for p in res.people if p["current"] and "IČO" not in p["name"]][:2]
        for p in current:
            add(f'"{p["name"]}" "{name}"', people_q)
    if subject.anchor.type == "url":
        add(subject.anchor.value, questions[0].id)
    return plan


# ---------------------------------------------------------------- 3. collect

def collect_web(plan: dict[str, list[str]], log: Log) -> tuple[list[Source], list[str]]:
    token = config.apify_token()
    if not token:
        return [], ["Web research did not run: APIFY_API_TOKEN is not set. Only registry data is reported."]
    notes: list[str] = []
    by_url: dict[str, Source] = {}

    def run(query: str):
        try:
            return query, apify.search(query, token, config.results_per_query()), None
        except Exception as e:
            return query, [], f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=4) as pool:  # 4 × 1 GB actor memory (sources/apify.py)
        for query, pages, err in pool.map(run, plan):
            if err:
                notes.append(f"Search failed for {query!r}: {err}")
                log(f"  ✗ {query}  ({err[:80]})")
                continue
            log(f"  ✓ {query}  → {len(pages)} pages")
            for p in pages:
                src = by_url.get(p["url"])
                if not src:
                    src = Source(id=f"W{len(by_url) + 1}", url=p["url"], title=p["title"], text=p["text"],
                                 origin="web", publisher=apify.publisher(p["url"]), query=query,
                                 snippet_only=p["snippet_only"])
                    by_url[p["url"]] = src
                for qid in plan[query]:
                    if qid not in src.question_ids:
                        src.question_ids.append(qid)
    return list(by_url.values()), notes


# ---------------------------------------------------------------- 4. identity

IDENTITY_SYSTEM = """You resolve identity for due-diligence research.
For each source decide whether it is about the SAME entity as the subject, a POSSIBLE match, or a DIFFERENT entity
(namesake, look-alike company, unrelated page). Use the anchor and registry facts. Be strict: a shared name alone
is "possible", not "same". Pages that merely list many companies or people are "possible" at best.
Return JSON: {"verdicts": [{"source_id": "W1", "match": "same|possible|different", "reason": "short reason"}]}"""


def check_identity(subject: Subject, res: Resolution, web: list[Source]) -> list[IdentityVerdict]:
    if not web:
        return []
    registry = "\n".join(s.text for s in res.sources) or "(no registry record)"
    pages = "\n\n".join(f"[{s.id}] {s.title}\nURL: {s.url}\n{s.text[:1200]}" for s in web)
    user = (f"Subject: {subject.name} ({subject.kind})\nAnchor: {subject.anchor.label()}\n"
            f"Registry facts:\n{registry}\n\nSources:\n{pages}")
    data = llm.chat_json(IDENTITY_SYSTEM, user)
    out = {}
    for v in data.get("verdicts", []):
        if v.get("source_id") in {s.id for s in web} and v.get("match") in ("same", "possible", "different"):
            out[v["source_id"]] = IdentityVerdict(**{k: v[k] for k in ("source_id", "match", "reason")})
    return [out.get(s.id) or IdentityVerdict(source_id=s.id, match="possible", reason="Not assessed by model")
            for s in web]


# ---------------------------------------------------------------- 5. extract

EXTRACT_SYSTEM = """You are a due-diligence analyst. Purpose of the research: {purpose}
Answer ONE research question about the subject using ONLY the sources provided.

Rules:
- Every claim cites at least one source_id and copies an EXACT verbatim quote (5-40 words) from that source.
  Never paraphrase inside a quote. If you cannot quote it, do not claim it.
- kind = "fact" if the source states it directly, "inference" if you interpret or combine sources.
- If sources disagree with each other or with the registry, record the conflicting source and its exact quote in
  "contradicted_by" of the affected claim.
- Keep only claims that matter for the purpose; explain why in "relevance".
- Registry facts (sources R*) are already in the report: do NOT restate them, only use them to spot contradictions.
- NEVER report or infer special-category data (health, political opinions, religion, ethnicity, sexual orientation,
  trade-union membership, biometric or genetic data). Skip it and count it in "special_category_skipped".
- NEVER produce personality, credit or trustworthiness scores or judgements of character.
- List what the sources leave unknown in "gaps".

Return JSON:
{{"answer": "2-4 sentences that state uncertainty explicitly",
  "claims": [{{"statement": "...", "kind": "fact|inference",
              "evidence": [{{"source_id": "W1", "quote": "exact text"}}],
              "relevance": "...",
              "contradicted_by": [{{"source_id": "W2", "quote": "exact text", "note": "how it conflicts"}}]}}],
  "gaps": ["..."],
  "special_category_skipped": 0}}"""


def extract(subject: Subject, goal: Goal, question: Question, sources: list[Source]) -> dict:
    blocks = "\n\n".join(f"[{s.id}] {s.title}\nURL: {s.url}\n{s.text}" for s in sources)
    user = (f"Subject: {subject.name} ({subject.kind}); anchor {subject.anchor.label()}\n"
            f"Question: {question.text}\n\nSources:\n{blocks}")
    return llm.chat_json(EXTRACT_SYSTEM.format(purpose=goal.purpose), user)


def _target(questions: list[Question], preferred: tuple[str, ...]) -> str | None:
    ids = [q.id for q in questions]
    return next((p for p in preferred if p in ids), None) or next((q.id for q in questions if q.uses_registry), None)


def registry_claims(res: Resolution, questions: list[Question], subject: Subject) -> list[Claim]:
    claims: list[Claim] = []
    status_q, risk_q, people_q = (_target(questions, STATUS_QUESTIONS), _target(questions, RISK_QUESTIONS),
                                  _target(questions, PEOPLE_QUESTIONS))
    for src in res.sources:
        former_people = 0
        for line in src.text.splitlines():
            if line.startswith(RISK_PREFIXES):
                if subject.kind == "person":  # company flags say nothing about the person
                    continue
                qid = risk_q
            elif line.startswith(STATUS_PREFIXES):
                if subject.kind == "person" and not line.startswith(("Business name", "Subject status")):
                    continue
                qid = status_q
            elif line.startswith(("Current ", "Former ")):
                if subject.kind == "person" and not _names_match(subject.name, line.split(": ", 1)[-1].split(" (")[0]):
                    continue
                if line.startswith("Former "):
                    former_people += 1
                    if former_people > 4:
                        continue
                qid = people_q
            else:
                continue
            if qid:
                claims.append(Claim(id="", question_id=qid, statement=line, kind="fact",
                                    source_ids=[src.id], quotes=[line],
                                    relevance="Official registry record"))
    return claims


def _claims_from_llm(data: dict, qid: str) -> list[Claim]:
    claims = []
    for c in data.get("claims", []) or []:
        evidence = [e for e in c.get("evidence", []) or [] if e.get("source_id") and e.get("quote")]
        if not c.get("statement"):
            continue
        claims.append(Claim(
            id="", question_id=qid, statement=c["statement"],
            kind="inference" if c.get("kind") == "inference" else "fact",
            source_ids=[e["source_id"] for e in evidence], quotes=[e["quote"] for e in evidence],
            relevance=c.get("relevance", ""),
            contradicted_by=[Contradiction(source_id=x["source_id"], quote=x["quote"], note=x.get("note", ""))
                             for x in c.get("contradicted_by", []) or [] if x.get("source_id") and x.get("quote")],
        ))
    return claims


OUTREACH_SYSTEM = """Draft a short, respectful first outreach message (max 120 words) to the subject for a sales
conversation. Use only the verified findings given. Reference one concrete, professional detail. No flattery, no
personal-life details, no special-category data. Return JSON {"message": "..."}"""


# ---------------------------------------------------------------- run

def run(subject: Subject, replay: Path | None = None, log: Log = print) -> tuple[Report, Path]:
    goal = get_goal(subject.goal)
    questions = goal.questions[subject.kind]
    slug = re.sub(r"[^a-z0-9]+", "-", ares.normalize_name(subject.name)).strip("-")[:40]
    run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}-{goal.id}"
    run_dir = config.RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    limitations: list[str] = []
    use_llm, llm_reason = llm.available()

    log(f"▶ {subject.name} ({subject.kind}) | {subject.anchor.label()} | goal: {goal.label}")
    log("1/6 resolving identity in official registry")
    res = resolve(subject, log)
    limitations += res.notes

    log("2/6 planning goal-specific searches")
    plan = plan_queries(subject, goal, res)
    for q, qids in plan.items():
        log(f"  · {q}  [{', '.join(qids)}]")

    log("3/6 collecting public web sources")
    if replay:
        raw = json.loads((replay / "raw_sources.json").read_text(encoding="utf-8"))
        web = [Source(**{**s, "mode": "CACHED"}) for s in raw if s["origin"] == "web"]
        limitations.append(f"Web sources are a CACHED replay of run {replay.name} (fetched "
                           f"{min((s.fetched_at for s in web), default='n/a')}), not fetched live.")
        log(f"  replayed {len(web)} cached pages from {replay.name}")
    else:
        web, notes = collect_web(plan, log)
        limitations += notes
    sources = res.sources + web
    (run_dir / "raw_sources.json").write_text(
        json.dumps([s.model_dump() for s in sources], ensure_ascii=False, indent=1), encoding="utf-8")

    log("4/6 checking identity of each source (namesakes / look-alikes)")
    identity: list[IdentityVerdict] = []
    if web and use_llm:
        try:
            identity = check_identity(subject, res, web)
        except Exception as e:
            limitations.append(f"Identity check failed ({e}); all web sources treated as uncertain.")
    if web and not identity:
        identity = [IdentityVerdict(source_id=s.id, match="unassessed", reason="No LLM available") for s in web]
    id_map = {v.source_id: v for v in identity}
    for v in identity:
        log(f"  {v.source_id} {v.match:<9} {v.reason[:90]}")

    log("5/6 extracting claims per question")
    by_id = {s.id: s for s in sources}
    claims_by_q: dict[str, list[Claim]] = {q.id: [] for q in questions}
    answers: dict[str, str] = {}
    gaps: dict[str, list[str]] = {q.id: [] for q in questions}
    suppressed = 0
    for c in registry_claims(res, questions, subject):
        claims_by_q[c.question_id].append(c)

    def work(question: Question):
        usable = [s for s in web if question.id in s.question_ids and id_map.get(s.id) and
                  id_map[s.id].match in ("same", "possible")]
        if not usable:
            return question, None, "no relevant web sources about this entity"
        return question, extract(subject, goal, question, res.sources + usable), None

    if use_llm and web:
        with ThreadPoolExecutor(max_workers=4) as pool:
            for question, data, err in pool.map(lambda q: _safe(work, q), questions):
                if err:
                    gaps[question.id].append(err[0].upper() + err[1:] + "." if data is None and "no relevant" in err
                                             else f"Web analysis failed: {err}")
                    continue
                answers[question.id] = data.get("answer", "")
                gaps[question.id] += [g for g in data.get("gaps", []) or [] if isinstance(g, str)]
                suppressed += int(data.get("special_category_skipped") or 0)
                claims_by_q[question.id] += _claims_from_llm(data, question.id)
                log(f"  {question.id}: {len(claims_by_q[question.id])} claims")
    elif web:
        limitations.append(f"LLM step unavailable ({llm_reason}): web pages were collected but not analysed. "
                           "Only registry facts are reported as claims.")

    log("6/6 verifying quotes and scoring confidence")
    findings = []
    n = 0
    for q in questions:
        scored = []
        for c in claims_by_q[q.id]:
            n += 1
            c.id = f"C{n}"
            scored.append(score_claim(c, by_id, id_map))
        order = {"high": 0, "medium": 1, "low": 2}
        scored.sort(key=lambda c: (order[c.confidence], "UNSUPPORTED" in c.flags))
        if not scored:
            gaps[q.id].insert(0, "No public evidence found for this question." if web else
                              "Not researched: web search did not run (see limitations).")
        answer = answers.get(q.id) or (
            "Answered from the official registry only." if scored else "Unknown.")
        findings.append(Finding(question_id=q.id, question=q.text, answer=answer, claims=scored, gaps=gaps[q.id]))
    unsupported = sum("UNSUPPORTED" in c.flags for f in findings for c in f.claims)
    log(f"  {n} claims, {unsupported} flagged UNSUPPORTED (quote not found in source)")

    outreach = None
    if goal.outreach and use_llm:
        solid = [c.statement for f in findings for c in f.claims if c.confidence in ("high", "medium")]
        if solid:
            try:
                outreach = llm.chat_json(OUTREACH_SYSTEM, f"Subject: {subject.name}\nFindings:\n- " +
                                         "\n- ".join(solid[:15])).get("message")
            except Exception as e:
                limitations.append(f"Outreach draft failed: {e}")

    if use_llm:
        limitations.append(f"LLM step: {llm_reason}. Identity checks and claim extraction are model output; "
                           "every quote was checked against its source by code.")
    limitations.append("Coverage: Czech registry (ARES) + Google results via Apify. Courts, sanctions lists and "
                       "foreign registries are only covered where they appear in web results.")
    limitations.append("Raw scraped page text is stored in raw_sources.json for this run only; delete it with "
                       "`python -m dd_agent purge` after judging.")

    report = Report(run_id=run_id, subject=subject, goal_label=goal.label, goal_purpose=goal.purpose,
                    resolved_entity=res.entity, lookalikes=res.lookalikes, identity=identity,
                    findings=findings, sources=sources, suppressed_special_category=suppressed,
                    outreach_draft=outreach, limitations=limitations)
    return report, run_dir


def _safe(fn, q):
    try:
        return fn(q)
    except Exception as e:
        return q, None, f"{type(e).__name__}: {e}"
