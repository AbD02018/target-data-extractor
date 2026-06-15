"""CLI entry point for target-data-extractor.

Usage:
  tde extract <URL>                       # print JSON to stdout
  tde extract <URL> -o program.json        # write to file
  tde extract <URL> -f markdown           # human-readable markdown
  tde detect <URL>                        # just show which platform
  tde platforms                           # list all supported platforms
  tde version
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from target_data_extractor import __version__
from target_data_extractor.bypass import BypassClient, BypassConfig
from target_data_extractor.exceptions import ExtractorError
from target_data_extractor.models import BountyProgram
from target_data_extractor.output import to_json, to_markdown
from target_data_extractor.platforms import detect_platform, get_platform, list_platforms

console = Console()
err_console = Console(stderr=True)


def _async_run(coro: Any) -> Any:
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    if loop.is_running():
        # already in async context
        return coro
    return loop.run_until_complete(coro)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.option("--strategy", default="auto", type=click.Choice(["auto", "curl_cffi", "cloudscraper", "playwright"]), help="Bypass strategy")
@click.version_option(__version__, prog_name="tde")
def main(verbose: bool, strategy: str) -> None:
    """target-data-extractor: extract bug bounty program data from any of 7 platforms."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@main.command()
@click.argument("url")
def detect(url: str) -> None:
    """Detect which platform a URL belongs to."""
    try:
        platform = detect_platform(url)
        console.print(f"[green]✓[/green] {url}\n  → platform: [bold]{platform}[/bold]")
    except ExtractorError as exc:
        err_console.print(f"[red]✗[/red] {exc}")
        sys.exit(2)


@main.command(name="platforms")
def platforms_cmd() -> None:
    """List all supported platforms."""
    table = Table(title="Supported platforms", show_header=True, header_style="bold")
    table.add_column("Platform", style="cyan")
    table.add_column("Strategy", style="green")
    table.add_column("Auth required", style="yellow")
    for name in list_platforms():
        cls = type(get_platform(name))
        # Map to rough strategy
        if name in ("hackerone", "bugcrowd"):
            strat = "API + scrape fallback"
        else:
            strat = "scrape + bypass"
        try:
            auth = "Yes (for full data)" if getattr(cls, "requires_auth", False) else "No"
        except Exception:
            auth = "?"
        table.add_row(name, strat, auth)
    console.print(table)


@main.command()
@click.argument("url")
@click.option("-o", "--output", "output_path", type=click.Path(), default=None, help="Write to file (format from extension)")
@click.option("-f", "--format", "fmt", type=click.Choice(["json", "yaml", "markdown", "html"]), default="json", help="Output format (default: json)")
@click.option("--include-raw", is_flag=True, help="Include raw_data in output (debugging)")
@click.option("--bypass-strategy", default=None, type=click.Choice(["auto", "curl_cffi", "cloudscraper", "playwright"]), help="Override bypass strategy")
def extract(url: str, output_path: str | None, fmt: str, include_raw: bool, bypass_strategy: str | None) -> None:
    """Extract program data from a bug bounty URL.

    URL can be from HackerOne, Bugcrowd, Intigriti, Immunefi, YesWeHack, Bugrap, or HackenProof.
    """
    try:
        platform_name = detect_platform(url)
    except ExtractorError as exc:
        err_console.print(f"[red]✗[/red] {exc}")
        sys.exit(2)

    config = BypassConfig(strategy=bypass_strategy or "auto")
    bypass = BypassClient(config)
    platform = get_platform(platform_name, bypass=bypass)

    try:
        program: BountyProgram = asyncio.run(platform.extract(url))
    except ExtractorError as exc:
        err_console.print(f"[red]✗[/red] Extraction failed: {exc}")
        sys.exit(1)

    if output_path:
        from target_data_extractor.output import write_output
        path = write_output(program, output_path, fmt=fmt)
        console.print(f"[green]✓[/green] Wrote [bold]{program.program_name}[/bold] → {path}")
    else:
        if fmt == "json":
            console.print(to_json(program, include_raw=include_raw))
        elif fmt == "markdown":
            console.print(to_markdown(program))
        else:
            # For yaml/html without -o, default to json-on-stdout
            console.print(to_json(program, include_raw=include_raw))


@main.command()
@click.argument("platform_name")
@click.option("--limit", default=10, type=int, help="Max programs to extract")
@click.option("--format", "fmt", type=click.Choice(["json", "markdown"]), default="json")
def list(platform_name: str, limit: int, fmt: str) -> None:
    """List public programs for a platform (rate-limited; auth tokens preferred)."""
    try:
        platform = get_platform(platform_name)
    except ExtractorError as exc:
        err_console.print(f"[red]✗[/red] {exc}")
        sys.exit(2)

    try:
        programs: list[BountyProgram] = asyncio.run(platform.list_programs())
    except ExtractorError as exc:
        err_console.print(f"[red]✗[/red] {exc}")
        sys.exit(1)

    programs = programs[:limit]
    if fmt == "json":
        items = [p.to_summary() for p in programs]
        console.print_json(data=items)
    else:
        table = Table(title=f"{platform_name} programs (limit {limit})", show_header=True, header_style="bold")
        for col in ("program", "handle", "is_paid", "max_bounty_usd", "in_scope_count"):
            table.add_column(col)
        for p in programs:
            s = p.to_summary()
            table.add_row(
                str(s.get("program", "")),
                str(s.get("handle", "")),
                "✅" if s.get("is_paid") else "—",
                f"${s['max_bounty_usd']:,.0f}" if s.get("max_bounty_usd") else "—",
                str(s.get("in_scope_count", 0)),
            )
        console.print(table)


if __name__ == "__main__":
    main(obj={})
