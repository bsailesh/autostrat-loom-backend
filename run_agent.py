"""
Phase 1 entry point for the Market Insights agent.

    python run_agent.py --subject "electric off-highway equipment powertrains"

Runs live web-search research on the subject, then produces the 9 required
reports and writes them to ./output/ as both JSON (for later phases) and
Markdown (for a human to read and judge against the hand-built samples).

No web server, no database, no auth — that is all later phases by design.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from market_insights.agent import MarketInsightsAgent, Source
from market_insights.config import Settings


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s or "market")[:60]


def _parse_reports(value: str | None) -> list[int] | None:
    if not value:
        return None
    out: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not (1 <= int(part) <= 9):
            raise argparse.ArgumentTypeError(
                f"--only-reports takes numbers 1-9, got {part!r}"
            )
        out.append(int(part))
    return out or None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the Market Insights agent (Phase 1) against a subject."
    )
    parser.add_argument(
        "--subject", default=None,
        help='Market / industry topic, e.g. "marine propulsion electrification". '
             "Required unless --from-research supplies it.",
    )
    parser.add_argument(
        "--model", default=None,
        help="Override the synthesis model (default: claude-opus-5 or "
             "MARKET_INSIGHTS_MODEL). Use claude-sonnet-5 for cheaper iteration.",
    )
    parser.add_argument(
        "--output-dir", default="output",
        help="Directory for the JSON + Markdown output (default: ./output).",
    )
    parser.add_argument(
        "--max-searches", type=int, default=16,
        help="Cap on web searches during research (default: 16).",
    )
    parser.add_argument(
        "--research-rounds", type=int, default=2,
        help="Research passes; round 2+ targets the weakest areas (default: 2).",
    )
    parser.add_argument(
        "--only-reports", type=_parse_reports, default=None,
        help="Comma-separated report numbers to generate, e.g. 1,2,6 "
             "(default: all 9). Useful when iterating on prompts.",
    )
    parser.add_argument(
        "--from-research", metavar="PATH", default=None,
        help="Reuse the research_brief + sources from a prior run's JSON and skip "
             "the (slow, paid) web-search phase. For iterating on synthesis "
             "prompts. --subject is taken from the file unless overridden.",
    )
    parser.add_argument(
        "--print", dest="print_md", action="store_true",
        help="Also print the full Markdown bundle to stdout.",
    )
    args = parser.parse_args(argv)

    prior_research = None
    if args.from_research:
        try:
            data = json.loads(Path(args.from_research).read_text(encoding="utf-8"))
            prior_research = (
                data["research_brief"],
                [Source(**s) for s in data["research_sources"]],
                list(data.get("web_search_queries", [])),
            )
            if not args.subject:
                args.subject = data["subject"]
        except (OSError, KeyError, ValueError, TypeError) as e:
            print(f"error: could not load --from-research file: {e}", file=sys.stderr)
            return 2

    if not args.subject:
        print("error: --subject is required (unless --from-research supplies it)",
              file=sys.stderr)
        return 2

    try:
        settings = Settings.load(model_override=args.model)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    def progress(msg: str) -> None:
        print(f"  - {msg}", file=sys.stderr, flush=True)

    print(f"Market Insights agent - subject: {args.subject!r}", file=sys.stderr)
    print(f"Model: {settings.model}", file=sys.stderr)

    agent = MarketInsightsAgent(settings, progress=progress)
    try:
        result = agent.run(
            args.subject,
            max_searches=args.max_searches,
            research_rounds=args.research_rounds,
            only_reports=args.only_reports,
            prior_research=prior_research,
        )
    except Exception as e:  # noqa: BLE001 - surface any failure clearly at the CLI
        print(f"\nagent run failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = result.generated_at.replace(":", "").replace("-", "")
    base = f"{_slug(args.subject)}-{stamp}"
    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"
    json_path.write_text(result.to_json(), encoding="utf-8")
    md_path.write_text(result.to_markdown(), encoding="utf-8")

    print("", file=sys.stderr)
    print(f"Wrote {len(result.reports)} report(s):", file=sys.stderr)
    print(f"  JSON     {json_path}", file=sys.stderr)
    print(f"  Markdown {md_path}", file=sys.stderr)
    print(f"  Sources  {len(result.research_sources)} consulted, "
          f"{len(result.web_search_queries)} searches", file=sys.stderr)

    if args.print_md:
        print(result.to_markdown())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
