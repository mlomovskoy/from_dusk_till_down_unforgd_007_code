# Contributor and agent guide

Applies to humans and AI coding agents working in this repo.

## Hard rules (from the Case 01 brief, non-negotiable)

1. **Public data only.** No logins, fake accounts, CAPTCHA bypassing, or breach/leak databases.
2. **Use existing Apify actors** for anything an actor already covers. Don't write scrapers.
   Official public APIs (such as ARES) are fine.
3. **Never infer GDPR Art. 9 data** (health, politics, religion, ethnicity, sexuality).
4. **No personality, credit or "trustworthiness" score** of a person, and no overall risk score.
5. **Outreach is drafted and shown, never sent.** No code path may contact a research subject.
6. **Label every source** `LIVE`, `CACHED` or `MOCK`. Mock data only for an unreachable source.
7. **Minimise personal data:** registry home addresses and birth dates are dropped before storage.
8. **Delete raw scraped data** when you no longer need it: `python -m dd_agent purge`.

## Secrets

Keys live only in `.env` (git-ignored; see `.env.example`). Never commit, print or log them.

## Verification

- 🟢 verified by a real live run · 🟡 verified by tests or stubs only · 🔴 open or broken.
- `python3 -m dd_agent test` runs the `python` blocks in `tests/*.md`. Tests earn 🟡 at most.
- A skipped step must never look like a clean result, and counters must count what actually happened.
- Make every new check fail on purpose once before trusting it.

## Automated gates

Versioned git hooks in `.githooks/` enforce the rules. Enable them once per clone:
`git config core.hooksPath .githooks`.

- **pre-commit** blocks `.env`, `runs/` and `__pycache__`, staged text that looks like an API key, and
  links to private repos. It also runs `python3 -m dd_agent test`, which must pass.
- **commit-msg** requires a conventional prefix. `feat` and `fix` must name a task, e.g. `feat(T9): ...`.
- **Never use `git commit --no-verify`.** If a gate is wrong, fix the gate in its own commit and say why.

## Git

- Conventional commit prefixes: `feat:`, `fix:`, `docs:`, `test:`, `chore:`.
- Never force-push `main`. Never commit `.env`, `runs/` or `__pycache__/`.
- AI agents commit or push only when a maintainer asks.
