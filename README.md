# target-data-extractor 🛡️

> **Send a bug bounty program link. Get structured program data. Across 7 platforms.**

Extract program scope, rules, bounty table, and asset details from any of:
**HackerOne**, **Bugcrowd**, **Intigriti**, **Immunefi**, **YesWeHack**, **Bugrap**, **HackenProof**.

## Why?

Bug bounty hunters waste time copy-pasting scope from 7 different UIs.
This tool normalizes them into one schema. Send a link, get JSON / Markdown / HTML.

```bash
$ tde extract "https://hackerone.com/security"
{
  "platform": "hackerone",
  "program_name": "GitHub Security",
  "max_bounty_usd": 60000,
  "scope": { "in_scope_count": 42, "wildcards": ["*.github.com"], ... },
  ...
}
```

## Install

```bash
pip install target-data-extractor
```

(Or `pip install -e ".[dev]"` from source.)

## CLI

```bash
tde detect <URL>                        # which platform?
tde platforms                           # list all 7 supported platforms
tde extract <URL>                       # print JSON to stdout
tde extract <URL> -o program.json       # write JSON
tde extract <URL> -f markdown -o p.md   # write Markdown
tde extract <URL> -f html -o p.html     # write self-contained HTML
tde list hackerone --limit 10           # list public programs
tde --version
```

### Options

- `-f` / `--format`: `json` (default), `yaml`, `markdown`, `html`
- `-o` / `--output`: write to file (format inferred from extension)
- `--include-raw`: include the original platform response in output
- `--bypass-strategy`: `auto` (default) | `curl_cffi` | `cloudscraper` | `playwright`
- `-v` / `--verbose`: debug logging

## Python API

```python
import asyncio
from target_data_extractor import detect_platform, get_platform

async def main():
    url = "https://hackerone.com/security"
    platform_name = detect_platform(url)
    platform = get_platform(platform_name)

    # If platform supports API, set token in env first:
    # export HACKERONE_API_TOKEN="..."
    # export BUGCROWD_API_KEY="..."
    # export INTIGRITI_API_TOKEN="..."
    # export YESWEHACK_TOKEN="..."

    program = await platform.extract(url)
    print(program.program_name, program.max_bounty_usd)
    print("Wildcards:", [a.target for a in program.scope.wildcards])
    print("Smart contracts:", [a.target for a in program.scope.smart_contracts])

asyncio.run(main())
```

## How it Works

### Two-tier fetch strategy

| Tier | Strategy | Platforms | Why |
|------|----------|-----------|-----|
| **1 — API** | Official REST/GraphQL with auth token | HackerOne, Bugcrowd (YesWeHack with bearer) | Reliable, no scraping |
| **2 — Scrape** | Bypass client (curl_cffi → cloudscraper → playwright) | Intigriti, Immunefi, YesWeHack, Bugrap, HackenProof | No public API |

Every API-backed extractor automatically falls back to scrape if the API call fails.

### Anti-bot bypass layer

`BypassClient` auto-escalates through 3 strategies:

1. **curl_cffi** — TLS/HTTP2 fingerprint impersonation (chrome120, firefox123, ...)
2. **cloudscraper** — Cloudflare-specific JS challenge solver
3. **playwright + stealth** — real headless Chromium with anti-fingerprint flags

Configure via:
- `BypassConfig(strategy="playwright")` — force heavy mode
- `BypassConfig(proxy="http://user:pass@host:port")` — route through proxy
- `BypassConfig(rotate_proxies=[...])` — pool

### Output schema (normalized)

Every platform returns the same `BountyProgram`:

```python
BountyProgram(
    platform="hackerone",          # one of 7
    program_handle="security",     # URL-safe slug
    program_name="GitHub Security",
    program_url=HttpUrl(...),
    bounty_table=[BountyRange(...)],   # severity → min/max
    max_bounty_usd=60000.0,
    is_paid=True, is_private=False,
    program_type="bug_bounty",     # or "smart_contract"
    scope=ProgramScope(
        in_scope=[ScopeAsset(target, asset_type, in_scope, max_severity, description), ...],
        out_of_scope=[...],
    ),
    rules=ProgramRules(
        safe_harbor=bool,
        disclosure_policy=str,
        requires_kyc=bool,
        rules_text=str,
    ),
    description=str,
    tags=[str, ...],
    source_url=HttpUrl(...),
    extracted_at=datetime,
    extractor_version="0.1.0",
)
```

Output formats: `JSON`, `YAML`, `Markdown`, `self-contained HTML` (Jinja2 + python-markdown).

## Authentication (optional but recommended)

Set tokens via env vars for **full data** from API-backed platforms:

```bash
export HACKERONE_API_TOKEN="..."        # https://hackerone.com/settings/api_token/edit
export BUGCROWD_API_KEY="..."           # request from Bugcrowd support
export INTIGRITI_API_TOKEN="..."        # researcher access token
export YESWEHACK_TOKEN="..."            # bearer token
```

Without tokens, all platforms still work via scrape — but scope data may be limited on JS-heavy pages (HackerOne, Intigriti).

## Coverage matrix

| Platform   | API path | Scrape path | Anti-bot tested | Notes |
|------------|----------|-------------|-----------------|-------|
| HackerOne  | ✅       | ✅ fallback | yes             | requires H1 token for full scope |
| Bugcrowd   | ✅       | ✅ fallback | yes             | requires BC key for full scope |
| Intigriti  | ❌       | ✅          | yes             | JS-heavy; needs playwright |
| Immunefi   | partial  | ✅          | yes             | Web3-first; smart contract scope |
| YesWeHack  | ✅       | ✅ fallback | yes             | requires bearer for full data |
| Bugrap     | ❌       | ✅          | yes             | small platform; scope works |
| HackenProof| ❌       | ✅          | yes             | small platform; scope works |

## Anti-bot reality check (2026)

Cloudflare + DataDome are real obstacles. We respect platform rate limits
and terms of service. The bypass layer is for **personal research use** —
don't hammer paid bounty programs at scale. See `docs/ETHICS.md`.

## Roadmap

- [x] v0.1.0 — 7 platforms, API+scrape, JSON/MD/HTML output
- [ ] v0.2.0 — Caching layer (etag/If-Modified-Since) for repeated queries
- [ ] v0.3.0 — Diff mode: compare scope changes between scrapes
- [ ] v0.4.0 — CLI for batch extraction from URL lists
- [ ] v0.5.0 — Web UI (Gradio/Streamlit)
- [ ] v1.0.0 — Stable, all platforms green, <2s average extraction

## License

MIT — see `LICENSE`.

## Contributing

See `CONTRIBUTING.md`. PRs welcome for new platform support and bug fixes.
