# Ethics & Responsible Use

This tool is built for **personal bug bounty research**. Before you use it at scale, read this.

## What this tool does

- Fetches public bug bounty program data from 7 platforms.
- Normalizes the data into one schema.
- Outputs JSON / Markdown / HTML.

## What's NOT okay

- **Hammering platforms at scale.** Rate limits exist for a reason.
- **Bypassing authentication that protects private data.** This tool does not crack logins.
- **Reselling extracted data.** Most platforms' Terms of Service prohibit it.
- **Using this to spam bug reports.** One report per real finding.
- **Scraping private programs** you don't have access to. The tool's scrape path uses public pages only.

## Anti-bot: a reality check

Some platforms (Immunefi, Intigriti, HackerOne) use Cloudflare or DataDome.
The bypass layer is included so you can use the tool without owning
enterprise proxy infrastructure. But:

- **The CFAA (US) and similar laws in other jurisdictions** make bypassing
  "technical protection measures" a gray area, even for public data.
- **Comply with each platform's robots.txt.**
- **Don't bypass access controls to get private program data** — that's not a "bypass", that's unauthorized access.

## When in doubt

If your use case involves anything beyond a hunter reading one or two public
program pages per day, talk to the platform first. Most have public APIs or
partnership programs for security researchers.

## Reporting concerns

If you find this tool being used for abuse, contact the maintainers via
GitHub issues. We will not support abuse.
