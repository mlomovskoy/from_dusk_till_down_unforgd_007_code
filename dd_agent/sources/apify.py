"""Web search + page content through Apify's existing RAG Web Browser actor (no custom scrapers).

https://apify.com/apify/rag-web-browser — takes a Google query (or a URL), returns page markdown.
Public pages only; the actor does not log in anywhere.
"""
from urllib.parse import urlparse

import httpx

ACTOR = "apify~rag-web-browser"
ENDPOINT = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
MAX_CHARS = 8000


def publisher(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def search(query: str, token: str, max_results: int = 3) -> list[dict]:
    """Returns [{url, title, text, snippet_only}] for one query or URL."""
    payload = {
        "query": query,
        "maxResults": max_results,
        "outputFormats": ["markdown"],
        "scrapingTool": "raw-http",
        "requestTimeoutSecs": 40,
    }
    r = httpx.post(ENDPOINT, params={"token": token, "timeout": 120}, json=payload, timeout=150)
    r.raise_for_status()
    pages = []
    for item in r.json():
        meta = item.get("metadata") or {}
        sr = item.get("searchResult") or {}
        url = meta.get("url") or sr.get("url")
        if not url:
            continue
        body = (item.get("markdown") or item.get("text") or "").strip()
        snippet = (sr.get("description") or "").strip()
        pages.append({
            "url": url,
            "title": (meta.get("title") or sr.get("title") or url).strip(),
            "text": (body or snippet)[:MAX_CHARS],
            "snippet_only": not body,
        })
    return [p for p in pages if p["text"]]
