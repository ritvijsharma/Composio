#!/usr/bin/env python3
"""
Composio Toolkit Research Agent
================================
Researches whether a given app can become an agent-callable toolkit
(auth model, self-serve vs gated, API surface, MCP availability).

Design goals (per assignment):
  - Prefer Composio's OWN SDK/MCP registry as ground truth wherever the
    app already exists as a Composio toolkit -- this is the most reliable
    signal we can get about auth scheme + action surface, because it's
    coming from the horse's mouth.
  - Fall back to free, keyless web research (DuckDuckGo HTML search +
    direct doc-page scraping) for apps not in Composio's catalog, or to
    fill gaps Composio doesn't answer (e.g. "is this partner-gated").
  - No paid LLM calls are used to *fabricate* facts. An LLM (optionally,
    any free/local model you have) is only used at the very end to
    *summarize* structured, source-backed records -- never as the source
    of the facts themselves.

Usage:
    pip install composio-core requests beautifulsoup4 lxml
    export COMPOSIO_API_KEY=...   # free tier is enough to query the catalog
    python research_agent.py --input apps.csv --output results.json

Where it needs a human:
  - Confirming "self-serve vs gated" for apps with ambiguous marketing
    copy (docs say "contact sales" but also expose a sandbox -- which is
    it, really?) often needs a human to read the actual pricing/dev page.
  - Distinguishing "has a public roadmap MCP server" from "someone's
    unofficial community MCP wrapper" needs a human judgment call about
    what counts as "existing MCP" per the assignment's bar.
  - Rate-limited / JS-rendered doc sites (Cloudflare-protected marketing
    pages, gated PitchBook research portals) need a human to open the
    page in a real browser and copy the relevant paragraph.
"""

import json
import re
import time
import argparse
import dataclasses
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"
HEADERS = {"User-Agent": "Mozilla/5.0 (research-agent; +https://composio.dev)"}


@dataclasses.dataclass
class AppRecord:
    name: str
    category: str
    one_liner: str = ""
    auth_methods: str = ""          # e.g. "OAuth2" / "API key" / "OAuth2, API key"
    self_serve: str = ""            # "self-serve" | "gated" | "mixed"
    gate_reason: str = ""           # e.g. "partner approval required"
    api_surface: str = ""           # "REST" | "GraphQL" | "REST + GraphQL" | "none public"
    api_breadth: str = ""           # rough size / maturity note
    has_mcp: str = ""               # "yes-official" | "yes-community" | "no"
    composio_toolkit: bool = False
    buildability_verdict: str = ""  # "ready today" | "possible with workaround" | "blocked"
    blocker: str = ""
    evidence_url: str = ""
    source: str = ""                # "composio" | "web-search" | "human"
    confidence: str = "unverified"  # "unverified" | "search-checked" | "human-checked"


def try_composio_lookup(app_slug: str) -> Optional[AppRecord]:
    """Query Composio's toolkit catalog for ground-truth auth/action info.

    Requires `pip install composio-core` and COMPOSIO_API_KEY. Wrapped in
    try/except because the catalog doesn't cover all 100 apps -- a miss
    here is expected and simply triggers the web-research fallback.
    """
    try:
        from composio import Composio  # type: ignore
    except ImportError:
        return None

    try:
        client = Composio()
        toolkit = client.toolkits.get(app_slug)
        if not toolkit:
            return None
        actions = client.actions.list(toolkits=[app_slug])
        return AppRecord(
            name=toolkit.name,
            category="",  # filled from the input sheet, Composio doesn't classify this way
            auth_methods=", ".join(toolkit.auth_schemes or []),
            api_surface="REST (via Composio action schema)",
            api_breadth=f"{len(actions)} actions registered in Composio",
            has_mcp="yes-official" if toolkit.supports_mcp else "no",
            composio_toolkit=True,
            evidence_url=f"https://mcp.composio.dev/{app_slug}",
            source="composio",
            confidence="search-checked",
        )
    except Exception:
        return None


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Free, keyless search via DuckDuckGo's HTML endpoint."""
    resp = requests.post(
        DUCKDUCKGO_HTML,
        data={"q": query},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for a in soup.select("a.result__a")[:max_results]:
        results.append({"title": a.get_text(strip=True), "url": a.get("href")})
    return results


def fetch_page_text(url: str, max_chars: int = 4000) -> str:
    """Grab plain text off a docs page for grep-style keyword scanning."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text())
        return text[:max_chars]
    except Exception as e:
        return f"[fetch-failed: {e}]"


AUTH_KEYWORDS = {
    "OAuth2": ["oauth 2.0", "oauth2", "authorization code flow", "oauth "],
    "API key": ["api key", "api-key", "x-api-key", "bearer token", "personal access token"],
    "Basic": ["basic auth", "basic authentication"],
}

GATE_KEYWORDS = [
    "contact sales", "request access", "partner program", "apply for access",
    "enterprise plan required", "become a partner", "approved partners",
]


def infer_auth_and_gate(text: str) -> tuple[str, str]:
    text_l = text.lower()
    auths = [name for name, kws in AUTH_KEYWORDS.items() if any(k in text_l for k in kws)]
    gated = any(k in text_l for k in GATE_KEYWORDS)
    return (", ".join(auths) or "unclear from page", "gated" if gated else "self-serve")


def research_app(name: str, category: str, hint_url: str = "") -> AppRecord:
    slug = name.lower().replace(" ", "").replace(".", "")
    record = try_composio_lookup(slug)
    if record:
        record.category = category
        return record

    # Fallback: web search + scrape
    query = f"{name} API documentation authentication"
    results = web_search(query)
    target_url = hint_url or (results[0]["url"] if results else "")
    page_text = fetch_page_text(target_url) if target_url else ""
    auth, gate = infer_auth_and_gate(page_text)

    return AppRecord(
        name=name,
        category=category,
        auth_methods=auth,
        self_serve=gate,
        api_surface="REST (see evidence link)",
        evidence_url=target_url,
        source="web-search",
        confidence="search-checked" if page_text and "fetch-failed" not in page_text else "unverified",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="CSV: name,category,hint_url")
    parser.add_argument("--output", required=True)
    parser.add_argument("--sleep", type=float, default=1.5, help="politeness delay between apps")
    args = parser.parse_args()

    import csv
    records = []
    with open(args.input) as f:
        for row in csv.DictReader(f):
            rec = research_app(row["name"], row["category"], row.get("hint_url", ""))
            records.append(dataclasses.asdict(rec))
            print(f"[done] {row['name']}: {rec.auth_methods} / {rec.self_serve}")
            time.sleep(args.sleep)

    with open(args.output, "w") as f:
        json.dump(records, f, indent=2)


if __name__ == "__main__":
    main()
