"""
MarketInsightsAgent — the Phase 1 core.

Two phases:

  1. research()   — one multi-round conversation with live web search enabled.
                    Produces a plain-text research brief plus a de-duplicated
                    list of the sources actually consulted.

  2. synthesize() — for each of the 9 required reports, one streamed call that
                    returns the report as plain Markdown. No web search here:
                    synthesis draws only on the research brief, so "nothing is
                    fabricated" is enforceable. The JSON shape the briefing asks
                    for (report_number, title, content, confidence_summary) is
                    assembled from that Markdown.

run() does both and returns an AgentRunResult that serializes straight to the
JSON shape the briefing asks for.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable

from anthropic import Anthropic

from market_insights.config import Settings, WEB_SEARCH_TOOL_TYPE
from market_insights import prompts
from market_insights.reports import REPORTS, ReportSpec


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Source:
    title: str
    url: str
    page_age: str | None = None  # relative age string the search tool returns, if any


@dataclass
class Report:
    report_number: int
    title: str
    content: str
    confidence_summary: str


@dataclass
class AgentRunResult:
    subject: str
    generated_at: str
    model: str
    web_search_queries: list[str]
    research_sources: list[Source]
    research_brief: str
    reports: list[Report]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "generated_at": self.generated_at,
            "model": self.model,
            "web_search_queries": self.web_search_queries,
            "research_sources": [asdict(s) for s in self.research_sources],
            "research_brief": self.research_brief,
            "reports": [asdict(r) for r in self.reports],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"# Market Insights — {self.subject}")
        lines.append("")
        lines.append(f"*Generated {self.generated_at} · model `{self.model}` · "
                     f"{len(self.research_sources)} sources consulted*")
        lines.append("")
        for r in self.reports:
            lines.append("---")
            lines.append("")
            lines.append(f"# Report {r.report_number} — {r.title}")
            lines.append("")
            lines.append(r.content.strip())
            lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## Appendix — Sources consulted during research")
        lines.append("")
        for i, s in enumerate(self.research_sources, 1):
            age = f" ({s.page_age})" if s.page_age else ""
            lines.append(f"{i}. [{s.title or s.url}]({s.url}){age}")
        return "\n".join(lines)


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class MarketInsightsAgent:
    def __init__(self, settings: Settings, *, progress: ProgressFn | None = None):
        self._settings = settings
        self._model = settings.model
        self._client = Anthropic(api_key=settings.anthropic_api_key, timeout=900.0)
        self._progress = progress or _noop

    # -- public entrypoint -------------------------------------------------

    def run(
        self,
        subject: str,
        *,
        max_searches: int = 16,
        research_rounds: int = 2,
        only_reports: list[int] | None = None,
        prior_research: tuple[str, list[Source], list[str]] | None = None,
    ) -> AgentRunResult:
        if prior_research is not None:
            brief, sources, queries = prior_research
            self._progress(
                f"Reusing prior research - {len(sources)} sources, skipping web search"
            )
        else:
            brief, sources, queries = self.research(
                subject, max_searches=max_searches, rounds=research_rounds
            )
        specs = [s for s in REPORTS if only_reports is None or s.number in only_reports]
        reports: list[Report] = []
        for spec in specs:
            self._progress(f"Synthesizing Report {spec.number} - {spec.title}")
            reports.append(self._synthesize_one(subject, spec, brief))

        return AgentRunResult(
            subject=subject,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model=self._model,
            web_search_queries=queries,
            research_sources=sources,
            research_brief=brief,
            reports=reports,
        )

    # -- phase 1: research ----------------------------------------------------

    def research(
        self, subject: str, *, max_searches: int = 16, rounds: int = 2
    ) -> tuple[str, list[Source], list[str]]:
        """Run the web-search research conversation. Returns (brief, sources, queries)."""
        tools = [{
            "type": WEB_SEARCH_TOOL_TYPE,
            "name": "web_search",
            "max_uses": max_searches,
        }]
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompts.research_user_prompt(subject)}
        ]

        brief_chunks: list[str] = []
        sources: dict[str, Source] = {}
        queries: list[str] = []

        for round_idx in range(max(1, rounds)):
            if round_idx > 0:
                messages.append({
                    "role": "user",
                    "content": (
                        "Now review what you have gathered. Identify the 3-4 weakest "
                        "or thinnest areas (least evidence, stalest sources, or "
                        "unresolved contradictions) and run additional web searches "
                        "to strengthen them. Then output ONLY the new or revised "
                        "evidence rows, grouped under the same headings. If an area "
                        "genuinely has no more public evidence, say so explicitly."
                    ),
                })

            self._progress(
                f"Research round {round_idx + 1}/{max(1, rounds)} - searching the web"
            )
            text, msg_content = self._research_turn(messages, tools)
            messages.append({"role": "assistant", "content": msg_content})
            if text.strip():
                brief_chunks.append(text.strip())
            self._collect_sources_and_queries(msg_content, sources, queries)

        brief = self._assemble_brief(subject, brief_chunks)
        self._progress(
            f"Research complete - {len(sources)} unique sources, "
            f"{len(queries)} searches"
        )
        return brief, list(sources.values()), queries

    def _research_turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> tuple[str, list[Any]]:
        """One assistant turn, transparently resuming across `pause_turn`."""
        collected: list[Any] = []
        text_parts: list[str] = []
        working = list(messages)

        while True:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=16000,
                system=prompts.RESEARCH_SYSTEM_PROMPT,
                messages=working,
                tools=tools,
            )
            collected.extend(resp.content)
            for block in resp.content:
                if getattr(block, "type", None) == "text":
                    text_parts.append(block.text)

            if resp.stop_reason == "pause_turn":
                working = working + [{"role": "assistant", "content": resp.content}]
                continue
            break

        return "\n".join(text_parts), collected

    @staticmethod
    def _collect_sources_and_queries(
        content: list[Any], sources: dict[str, Source], queries: list[str]
    ) -> None:
        for block in content:
            btype = getattr(block, "type", None)

            if btype == "server_tool_use" and getattr(block, "name", None) == "web_search":
                q = (getattr(block, "input", None) or {})
                if isinstance(q, dict) and q.get("query"):
                    queries.append(str(q["query"]))

            elif btype == "web_search_tool_result":
                results = getattr(block, "content", None)
                if not isinstance(results, list):
                    continue  # error object, not a result list
                for item in results:
                    if getattr(item, "type", None) != "web_search_result":
                        continue
                    url = getattr(item, "url", None)
                    if not url or url in sources:
                        continue
                    sources[url] = Source(
                        title=getattr(item, "title", "") or "",
                        url=url,
                        page_age=getattr(item, "page_age", None),
                    )

            elif btype == "text":
                for cit in getattr(block, "citations", None) or []:
                    url = getattr(cit, "url", None)
                    if url and url not in sources:
                        sources[url] = Source(
                            title=getattr(cit, "title", "") or "",
                            url=url,
                        )

    @staticmethod
    def _assemble_brief(subject: str, chunks: list[str]) -> str:
        header = (
            f"RESEARCH BRIEF — market intelligence on: {subject}\n"
            f"Compiled by live web search. Every row below should carry its own "
            f"source, dates, source type, confidence, and FACT/OBSERVATION/"
            f"INTERPRETATION/FORECAST/UNKNOWN label.\n"
        )
        body = "\n\n".join(
            f"----- research pass {i + 1} -----\n{c}" for i, c in enumerate(chunks)
        )
        return f"{header}\n{body}".strip()

    # -- phase 2: synthesis -------------------------------------------------
    #
    # A report is a Markdown document, not a bag of struct fields, so we ask for
    # it as plain streamed text rather than forcing a single giant tool call —
    # the forced-tool path truncates at max_tokens with the whole `content`
    # string unparseable. The structured JSON shape the briefing wants
    # (report_number / title / content / confidence_summary) is assembled here
    # from the returned Markdown: `content` is the body, `confidence_summary` is
    # sliced out of the report's own closing section.

    _CONF_HEADING = re.compile(
        r"\n#+\s*Confidence\s+Summary\b[^\n]*\n", re.IGNORECASE
    )
    # The model tends to re-print its own "# Report N — Title" H1 even when told
    # not to; strip a leading title H1 so it doesn't double the one to_markdown()
    # adds.
    _LEADING_TITLE_H1 = re.compile(r"\A#\s+Report\s+\d+\b[^\n]*\n+", re.IGNORECASE)

    def _synthesize_one(
        self, subject: str, spec: ReportSpec, research_brief: str
    ) -> Report:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=20000,
            system=prompts.synthesis_system_prompt(),
            messages=[{
                "role": "user",
                "content": prompts.synthesis_user_prompt(subject, spec, research_brief),
            }],
            thinking={"type": "adaptive"},
        ) as stream:
            final = stream.get_final_message()

        text = "".join(
            b.text for b in final.content if getattr(b, "type", None) == "text"
        ).strip()

        if not text:
            raise RuntimeError(
                f"Report {spec.number}: model returned no text "
                f"(stop_reason={final.stop_reason})."
            )
        if final.stop_reason == "max_tokens":
            text += "\n\n_[Note: generation hit the length ceiling; this report may be truncated.]_"

        text = self._LEADING_TITLE_H1.sub("", text, count=1).strip()

        return Report(
            report_number=spec.number,
            title=spec.title,
            content=text,
            confidence_summary=self._extract_confidence_summary(text),
        )

    @classmethod
    def _extract_confidence_summary(cls, text: str) -> str:
        m = cls._CONF_HEADING.search(text)
        if not m:
            return ""
        tail = text[m.end():]
        # stop at the next heading, if any
        nxt = re.search(r"\n#+\s", tail)
        return (tail[: nxt.start()] if nxt else tail).strip()
