"""Output formatters for extracted bug bounty program data.

Supports: JSON, YAML, Markdown, HTML (Jinja2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from target_data_extractor.models import BountyProgram


def to_json(program: BountyProgram, *, indent: int = 2, include_raw: bool = False) -> str:
    """Serialize a BountyProgram to JSON. By default excludes raw_data."""
    if include_raw:
        data = program.model_dump(mode="json")
    else:
        data = program.model_dump(mode="json", exclude={"raw_data"})
    return json.dumps(data, indent=indent, ensure_ascii=False, default=str)


def to_yaml(program: BountyProgram, *, include_raw: bool = False) -> str:
    if include_raw:
        data = program.model_dump(mode="json")
    else:
        data = program.model_dump(mode="json", exclude={"raw_data"})
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)


def to_markdown(program: BountyProgram) -> str:
    """Render a BountyProgram as a human-readable Markdown report."""
    lines: list[str] = []
    lines.append(f"# {program.program_name}")
    lines.append("")
    lines.append(f"- **Platform:** `{program.platform}`")
    lines.append(f"- **Handle:** `{program.program_handle}`")
    lines.append(f"- **URL:** {program.program_url}")
    lines.append(f"- **Type:** {program.program_type or 'n/a'}")
    lines.append(f"- **Paid:** {'✅ Yes' if program.is_paid else '❌ No'}")
    lines.append(f"- **Private:** {'🔒 Yes' if program.is_private else '🌐 No'}")
    if program.max_bounty_usd is not None:
        lines.append(f"- **Max bounty:** ${program.max_bounty_usd:,.0f}")
    if program.min_bounty_usd is not None:
        lines.append(f"- **Min bounty:** ${program.min_bounty_usd:,.0f}")
    lines.append(f"- **Extracted:** {program.extracted_at.isoformat()}Z")
    lines.append(f"- **Extractor:** target-data-extractor v{program.extractor_version}")
    lines.append("")

    if program.description:
        lines.append("## Description")
        lines.append("")
        lines.append(program.description)
        lines.append("")

    if program.bounty_table:
        lines.append("## Bounty Table")
        lines.append("")
        lines.append("| Severity | Min | Max | Currency |")
        lines.append("|----------|-----|-----|----------|")
        for br in program.bounty_table:
            lo = f"${br.min_amount:,.0f}" if br.min_amount is not None else "-"
            hi = f"${br.max_amount:,.0f}" if br.max_amount is not None else "-"
            lines.append(f"| {br.severity.value} | {lo} | {hi} | {br.currency} |")
        lines.append("")

    if program.tags:
        lines.append("## Tags")
        lines.append("")
        lines.append(", ".join(f"`{t}`" for t in program.tags))
        lines.append("")

    if program.scope.in_scope:
        lines.append(f"## In-Scope ({len(program.scope.in_scope)} assets)")
        lines.append("")
        for a in program.scope.in_scope:
            sev = f" — max: {a.max_severity.value}" if a.max_severity.value != "unknown" else ""
            desc = f" — {a.description}" if a.description else ""
            lines.append(f"- `{a.target}` [{a.asset_type.value}]{sev}{desc}")
        lines.append("")

    if program.scope.out_of_scope:
        lines.append(f"## Out-of-Scope ({len(program.scope.out_of_scope)} assets)")
        lines.append("")
        for a in program.scope.out_of_scope:
            desc = f" — {a.description}" if a.description else ""
            lines.append(f"- `{a.target}` [{a.asset_type.value}]{desc}")
        lines.append("")

    rules = program.rules
    if rules.rules_text or rules.disclosure_policy or rules.safe_harbor is not None:
        lines.append("## Rules")
        lines.append("")
        if rules.rules_text:
            lines.append(rules.rules_text)
            lines.append("")
        if rules.disclosure_policy:
            lines.append(f"- **Disclosure policy:** {rules.disclosure_policy}")
        if rules.safe_harbor is not None:
            lines.append(f"- **Safe harbor:** {'Yes' if rules.safe_harbor else 'No'}")
        if rules.requires_kyc is not None:
            lines.append(f"- **Requires KYC:** {'Yes' if rules.requires_kyc else 'No'}")
        if rules.requires_nda is not None:
            lines.append(f"- **Requires NDA:** {'Yes' if rules.requires_nda else 'No'}")
        if rules.managed_program is not None:
            lines.append(f"- **Managed program:** {'Yes' if rules.managed_program else 'No'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def to_html(program: BountyProgram) -> str:
    """Render as a self-contained HTML doc with embedded CSS."""
    md = to_markdown(program)
    try:
        import markdown as md_lib
        body = md_lib.markdown(md, extensions=["tables", "fenced_code"])
    except ImportError:
        body = f"<pre>{md}</pre>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{program.program_name} - Bug Bounty Program</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 980px; margin: 2em auto; padding: 0 1em; color: #1a1a1a; line-height: 1.55; }}
  h1 {{ border-bottom: 2px solid #e1e4e8; padding-bottom: 0.3em; }}
  h2 {{ margin-top: 1.5em; border-bottom: 1px solid #eaecef; padding-bottom: 0.2em; }}
  table {{ border-collapse: collapse; margin: 1em 0; }}
  th, td {{ border: 1px solid #dfe2e5; padding: 0.4em 0.8em; }}
  th {{ background: #f6f8fa; }}
  code {{ background: #f0f0f0; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; }}
  pre {{ background: #f6f8fa; padding: 1em; border-radius: 5px; overflow-x: auto; }}
  ul li {{ margin: 0.2em 0; }}
  .meta {{ color: #586069; font-size: 0.92em; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def write_output(program: BountyProgram, path: str | Path, fmt: str | None = None) -> Path:
    """Write the program to a file. Format inferred from extension if not given."""
    p = Path(path)
    fmt = (fmt or p.suffix.lstrip(".")).lower()
    content: str
    if fmt in ("json",):
        content = to_json(program)
    elif fmt in ("yaml", "yml"):
        content = to_yaml(program)
    elif fmt in ("md", "markdown"):
        content = to_markdown(program)
    elif fmt in ("html", "htm"):
        content = to_html(program)
    else:
        raise ValueError(f"Unsupported output format: {fmt!r}")
    p.write_text(content, encoding="utf-8")
    return p


__all__ = ["to_json", "to_yaml", "to_markdown", "to_html", "write_output"]
