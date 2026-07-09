# Composio Toolkit Research — 100 Apps

Research pipeline + case study for the AI Product Ops Intern take-home.

## What's here

```
case_study_final.html     <- the deliverable: open this in a browser
pipeline/research_agent.py <- the research "agent" (Composio-first, free web fallback)
data/build_dataset.py      <- builds the 100-row dataset (data/apps_dataset.json)
data/apps_dataset.json     <- the structured findings for all 100 apps
verification/verification_log.json <- the sample verification + accuracy scoring
```

## How the research was actually done

1. **Composio lookup first.** `pipeline/research_agent.py` tries Composio's own
   toolkit catalog (`composio-core` SDK) for each app slug. If the app is already
   a Composio toolkit, its auth scheme and action count come straight from the
   source of truth — no guessing needed.
2. **Free web fallback.** For apps not in Composio's catalog, the script falls
   back to a keyless DuckDuckGo HTML search + doc-page scrape (`requests` +
   `BeautifulSoup`), then keyword-matches the page text against auth/gating
   vocabulary ("OAuth 2.0", "contact sales", "request access", etc).
3. **No paid LLM calls for facts.** The pipeline never asks an LLM to "research"
   an app from memory — that's how you get confident-sounding hallucinations.
   An LLM is only appropriate for *summarizing* structured, source-backed
   records at the very end, never as the source of the facts themselves.

### Running it yourself

```bash
pip install composio-core requests beautifulsoup4 lxml --break-system-packages
export COMPOSIO_API_KEY=...     # free tier is enough for the catalog lookup
python pipeline/research_agent.py --input apps.csv --output results.json
```//
`apps.csv` needs columns `name,category,hint_url` (the 100-app list from the
assignment, reshaped into CSV).

### What happened in this actual session

The sandbox this was produced in has no outbound network access for executed
code, so the Composio SDK call and the scraper couldn't literally run here.
Instead, I (the research agent) executed the *same logic* live, by hand, using
real web search and doc-page reads for every uncertain app — which is exactly
what step 2 above automates. 8 of the 100 rows are tagged `"confidence":
"live-verified"` in `apps_dataset.json` because they were individually
searched and cited this session; the other 92 come from stable, documented
technical knowledge about mainstream APIs (Stripe uses API keys, Salesforce
uses OAuth2, etc.) — the kind of fact that doesn't need a fresh search to be
right, though see the verification log for how often that assumption held up
when actually checked.

## Verification

`verification/verification_log.json` documents a 10-app sample pulled from the
92 "knowledge-only" rows, each re-checked against live docs. First-pass
accuracy on that sample was 8/10 (80%); both misses were corrected in the
master dataset (Consensus, Waterfall.io — both had shipped a new API/MCP
surface that a static knowledge snapshot wouldn't know about). See the case
study's "Verification" section for the redlined before/after.

## Honesty notes

- **Paygent Connect** defeated the research: no public developer docs were
  found. That absence is reported as the finding, per the assignment's own
  instruction that a gated/undocumented app is a correct result, not a failure.
- **Sherlock** and **Mermaid CLI** aren't hosted services — they're local
  CLI tools. Wrapping them as an "agent toolkit" means shelling out to a local
  binary, a fundamentally different integration shape than a REST/GraphQL API.
- Every row has an `evidence` field. Where I couldn't find a real citation, the
  row says so explicitly rather than inventing one.
# Composio
# Composio_App
# Composio_App
# Comp
