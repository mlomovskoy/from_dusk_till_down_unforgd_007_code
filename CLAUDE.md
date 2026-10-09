# CLAUDE.md

@AGENTS.md

> **⚠️ If that import did not resolve, read [`AGENTS.md`](AGENTS.md) now, before doing anything else.**

## Claude Code specifics

- **Never read `.env`** or echo key values. To check whether a key is set, test for presence only:
  `grep -c '^OPENAI_API_KEY=.\+' .env`.
- **Live runs cost Apify and OpenAI credits.** Iterate with `--replay runs/<id>`; run live only to verify or demo.
- **Offline tests:** `python3 -m dd_agent test` (pytest is not installed).
- **Maintainers' private notes:** if a sibling folder `../from_dusk_till_down_unforgd_007` exists, read its
  `AGENTS.md` and `docs/specs/` before working. It is private, so never link to it from this repo.
