# Requirements

Python 3.10 or newer. Only two packages are needed, and everything else comes from the standard library.

| Package | Version | Used for |
|---|---|---|
| `httpx` | >= 0.27 | HTTP calls to ARES, Apify and OpenAI |
| `pydantic` | >= 2.8 | Data model for subjects, sources, claims and reports |

Install:

```bash
pip install "httpx>=0.27" "pydantic>=2.8"
```

External services (keys go in `.env`; see `.env.example`):

| Service | Needed for | Without it |
|---|---|---|
| ARES (ares.gov.cz) | Czech registry facts, identity resolution | No key needed; always available |
| Apify (`apify/rag-web-browser`) | Public web pages | Report contains registry data only and says so |
| OpenAI | Identity check, claim extraction, outreach draft | Pages are collected but not analysed; the report says so |
