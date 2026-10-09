# CLAUDE.md

@AGENTS.md
@../from_dusk_till_down_unforgd_007/AGENTS.md

> **⚠️ If those imports did not resolve, read [`AGENTS.md`](AGENTS.md) and
> `../from_dusk_till_down_unforgd_007/AGENTS.md` now, before doing anything else.**

## Claude Code specifics

- **Never read `.env`** or echo key values. To check whether a key is set, test for presence only:
  `grep -c '^OPENAI_API_KEY=.\+' .env`.
- **Live runs cost Apify and OpenAI credits.** Iterate with `--replay runs/<id>`; run live only to verify or demo.
- **Offline tests:** `python3 -m dd_agent test` (pytest is not installed).
