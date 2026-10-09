# Due Diligence Agent (code) — Conventions

**This repo is the implementation only.** The source of truth for scope, requirements, design, tasks,
decisions (ADRs) and status is the spec repo, the sibling folder
[`../from_dusk_till_down_unforgd_007`](https://github.com/mlomovskoy/from_dusk_till_down_unforgd_007).
Its `AGENTS.md` holds every convention (hard rules from the brief, working with Maxim, verification,
bugs, git, sessions) and **applies here unchanged**. Read it first. This file holds only what is
specific to the code repo.

## Spec-driven workflow

1. Read `docs/specs/requirements.md`, `design.md` and `tasks.md` in the spec repo.
2. Pick a task by ID (e.g. `T7`). If the work has no task, add the task to the spec repo first.
3. Implement it here and run its check. Commit with the task ID in the message (`feat(T7): ...`).
4. Tick the task and update `docs/STATUS.md` in the spec repo. Behaviour that changes the design
   changes `design.md` (or gets an ADR) **before** the code.

## Code-repo specifics

- **Run:** `python -m dd_agent serve` (web form) or `python -m dd_agent run ...` (see README.md).
- **Tests:** `python3 -m dd_agent test` runs the `python` blocks in `tests/*.md` (spec ADR-0006).
  Tests earn 🟡 at most; only a live run earns 🟢.
- **Keys** only in `.env` (git-ignored). Never print them.
- **Raw data** lives in `runs/` (git-ignored). Delete it after judging: `python -m dd_agent purge`.
- **Wanderson's repo** (`../from_dusk_till_down`) is read-only for agents (spec ADR-0001).
- **Git:** agents commit or push only when Maxim asks. Never force-push `main`. Only the latest commit
  at the 07:14 freeze is judged.
