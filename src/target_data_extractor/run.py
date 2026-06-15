"""One-shot CLI: give it a URL, get everything.

Usage:
  python -m target_data_extractor.run "https://hackerone.com/uber"
  python -m target_data_extractor.run "https://immunefi.com/bounty/aave" --out aave.md
  python -m target_data_extractor.run "https://bugcrowd.com/tesla" --format json
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from target_data_extractor.bypass import BypassClient, BypassConfig
from target_data_extractor.exceptions import ExtractorError
from target_data_extractor.models import BountyProgram
from target_data_extractor.output import to_html, to_json, to_markdown, to_yaml
from target_data_extractor.platforms import detect_platform, get_platform


async def fetch(url: str, strategy: str = "auto") -> BountyProgram:
    platform_name = detect_platform(url)
    bypass = BypassClient(BypassConfig(strategy=strategy))
    platform = get_platform(platform_name, bypass=bypass)
    try:
        return await platform.extract(url)
    finally:
        bypass.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract bug bounty program data from a URL.")
    parser.add_argument("url", help="Program URL (any of 7 platforms)")
    parser.add_argument("--format", "-f", choices=["json", "yaml", "markdown", "html", "summary"], default="summary")
    parser.add_argument("--out", "-o", help="Write to file (else print to stdout)")
    parser.add_argument("--strategy", default="auto", choices=["auto", "curl_cffi", "cloudscraper", "playwright"])
    args = parser.parse_args()

    try:
        program = asyncio.run(fetch(args.url, strategy=args.strategy))
    except ExtractorError as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 2

    if args.format == "summary":
        out = program.to_summary()
        import json
        text = json.dumps(out, indent=2, default=str)
    elif args.format == "json":
        text = to_json(program, include_raw=False)
    elif args.format == "yaml":
        text = to_yaml(program)
    elif args.format == "markdown":
        text = to_markdown(program)
    elif args.format == "html":
        text = to_html(program)
    else:
        text = to_json(program)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"[OK] wrote {args.out} ({len(text)} bytes)")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
