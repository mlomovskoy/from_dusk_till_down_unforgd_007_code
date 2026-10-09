"""CLI.

  python -m dd_agent run "Etnetera Activate" --kind organization --anchor ico:02713209 --goal procurement
  python -m dd_agent run "Jan Novak" --kind person --anchor ico:02713209 --goal hiring
  python -m dd_agent run ... --replay runs/<run_id>      # re-analyse cached pages (labelled CACHED)
  python -m dd_agent serve                                # web form on http://localhost:8008
  python -m dd_agent purge                                # delete raw scraped data
  python -m dd_agent test                                 # run the python blocks in tests/*.md
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

from . import config
from .goals import GOALS
from .models import Anchor, Subject


def run_and_save(subject: Subject, replay: Path | None = None, log=print) -> Path:
    from .agent import run
    from .report import to_html, to_markdown
    report, run_dir = run(subject, replay=replay, log=log)
    (run_dir / "report.json").write_text(report.model_dump_json(indent=1), encoding="utf-8")
    (run_dir / "report.md").write_text(to_markdown(report), encoding="utf-8")
    (run_dir / "report.html").write_text(to_html(report), encoding="utf-8")
    log(f"✔ report: {run_dir / 'report.html'}")
    return run_dir


def purge(remove_all: bool) -> None:
    if not config.RUNS_DIR.exists():
        print("nothing to purge")
        return
    for run_dir in sorted(config.RUNS_DIR.iterdir()):
        if remove_all:
            shutil.rmtree(run_dir)
            print(f"deleted {run_dir.name}")
            continue
        raw = run_dir / "raw_sources.json"
        if raw.exists():
            raw.unlink()
            print(f"deleted raw data of {run_dir.name}")
        rep = run_dir / "report.json"
        if rep.exists():  # quotes stay, full page text goes
            data = json.loads(rep.read_text(encoding="utf-8"))
            for s in data.get("sources", []):
                s["text"] = ""
            rep.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def run_md_tests() -> int:
    """Tests live in Markdown: every ```python block of tests/*.md runs, in order, as one script."""
    import re
    files = sorted((config.ROOT / "tests").glob("*.md"))
    if not files:
        print("no tests/*.md files found")
        return 1
    for f in files:
        blocks = re.findall(r"^```python\n(.*?)^```", f.read_text(encoding="utf-8"), re.S | re.M)
        if not blocks:
            print(f"{f.name}: no python blocks")
            return 1
        print(f"== {f.name} ({len(blocks)} blocks)")
        code = compile("\n\n".join(blocks), str(f), "exec")
        exec(code, {"__name__": "__main__", "__file__": str(f)})
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="dd_agent", description="Goal-driven due-diligence research agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="research a subject")
    r.add_argument("name")
    r.add_argument("--kind", choices=["person", "organization"], required=True)
    r.add_argument("--anchor", required=True,
                   help="one disambiguating fact: ico:12345678 | https://site | city:Prague | free text")
    r.add_argument("--goal", choices=list(GOALS), required=True)
    r.add_argument("--replay", type=Path, help="re-use web pages from a previous run dir (labelled CACHED)")

    s = sub.add_parser("serve", help="local web form")
    s.add_argument("--port", type=int, default=8008)

    g = sub.add_parser("purge", help="delete raw scraped data (required after judging)")
    g.add_argument("--all", action="store_true", help="delete whole run folders, reports included")

    sub.add_parser("goals", help="list goals and their questions")
    sub.add_parser("test", help="run the offline tests in tests/*.md")

    a = p.parse_args(argv)
    if a.cmd == "run":
        subject = Subject(name=a.name, kind=a.kind, anchor=Anchor.parse(a.anchor), goal=a.goal)
        run_and_save(subject, replay=a.replay)
    elif a.cmd == "serve":
        from .web import serve
        serve(a.port)
    elif a.cmd == "purge":
        purge(a.all)
    elif a.cmd == "test":
        return run_md_tests()
    elif a.cmd == "goals":
        for goal in GOALS.values():
            print(f"\n{goal.id}: {goal.label}\n  {goal.purpose}")
            for kind, qs in goal.questions.items():
                print(f"  [{kind}]")
                for q in qs:
                    print(f"    - {q.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
