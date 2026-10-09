"""Settings, read from the environment and an optional .env file in the project root."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY") or None


def openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def llm_backend() -> str:
    """claude-cli (default), grok-cli or openai — see dd_agent/llm.py."""
    return os.getenv("DD_LLM", "claude-cli").strip().lower()


def apify_token() -> str | None:
    return os.getenv("APIFY_API_TOKEN") or None


def results_per_query() -> int:
    return int(os.getenv("DD_RESULTS_PER_QUERY", "3"))
