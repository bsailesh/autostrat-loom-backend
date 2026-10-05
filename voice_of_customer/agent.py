"""
Voice of Customer Agent (Agent 1) — orchestration.

Two phases, Tech & Regulation's shape minus its structured candidate-work
call, because this agent emits no candidate work:

  1. research()   — one multi-round conversation with live web search, for
                    the PUBLIC side only. It never sees the customer evidence
                    or the named customers.
  2. synthesize() — one streamed call per report. Context, evidence and the
                    research brief are one cached prefix shared by all nine.

After each report is written, the output attribution check
(attribution.py) runs over it; after all nine, its note is appended to
Report 1. Both are deterministic -- not model output -- so the note is
always present and always accurate about what was checked.

Report 1 must carry the two sections other parts of the platform depend on:
"Testing your stated beliefs" (the customer looks for it) and "Findings for
synthesis" (Agent 5 extracts it by heading). A Report 1 missing either is
retried once with the gap named, then fails the run -- nine reports that
read as complete and silently lack the part that mattered is the failure
this codebase keeps having to design against.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from anthropic import Anthropic

from voice_of_customer import prompts
from voice_of_customer.attribution import (
    NameEntry,
    apply_attribution_check,
    attribution_check_note,
)
from voice_of_customer.config import WEB_SEARCH_TOOL_TYPE, Settings
from voice_of_customer.context import (
    CustomerContext,
    operating_tier,
    operating_tier_statement,
    render_context_text,
    report_title,
)
from voice_of_customer.reports import (
    BELIEF_TESTING_HEADING,
    FINDINGS_FOR_SYNTHESIS_HEADING,
    REPORTS,
    ReportSpec,
)

logger = logging.getLogger(__name__)

RESEARCH_MAX_TOKENS = 16000
SYNTHESIS_MAX_TOKENS = 20000


class ReportStructureError(Exception):
    """Report 1 came back twice without a section other parts of the
    platform depend on."""


@dataclass
class Source:
    title: str
    url: str
    page_age: str | None = None


@dataclass
class Report:
    report_number: int
    title: str
    content: str
    confidence_summary: str


@dataclass
class AgentRunResult:
    operating_tier: str
    operating_tier_line: str
    generated_at: str
    model: str
    web_search_queries: list[str]
    research_sources: list[Source]
    research_brief: str
    attribution_policy: str
    names_checked: int
    attribution_replacements: dict[int, int] = field(default_factory=dict)
    reports: list[Report] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operating_tier": self.operating_tier,
            "operating_tier_line": self.operating_tier_line,
            "generated_at": self.generated_at,
            "model": self.model,
            "web_search_queries": self.web_search_queries,
            "research_sources": [asdict(s) for s in self.research_sources],
            "research_brief": self.research_brief,
            "attribution_policy": self.attribution_policy,
            "names_checked": self.names_checked,
            "attribution_replacements": self.attribution_replacements,
            "reports": [asdict(r) for r in self.reports],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def missing_required_sections(spec: ReportSpec, content: str) -> list[str]:
    if spec.number != 1:
        return []
    headings = {line.strip().lower() for line in content.splitlines() if line.startswith("#")}
    return [
        h for h in (BELIEF_TESTING_HEADING, FINDINGS_FOR_SYNTHESIS_HEADING)
        if h.lower() not in headings
    ]


class VoiceOfCustomerAgent:
    def __init__(self, settings: Settings, *, progress: ProgressFn | None = None):
        self._settings = settings
        self._model = settings.model
        self._client = Anthropic(api_key=settings.anthropic_api_key, timeout=900.0)
        self._progress = progress or _noop

    # -- public entrypoint -------------------------------------------------

    def run(
        self,
        context: CustomerContext,
        evidence_text: str,
        *,
        name_entries: list[NameEntry] | None = None,
        max_searches: int = 12,
        research_rounds: int = 2,
        only_reports: list[int] | None = None,
    ) -> AgentRunResult:
        tier = operating_tier(context)
        tier_line = operating_tier_statement(context)
        names = name_entries or []
        self._progress(f"Operating tier: {tier}")

        brief, sources, queries = self.research(
            context, max_searches=max_searches, rounds=research_rounds
        )

        shared = prompts.synthesis_shared_block(
            tier_line, render_context_text(context, include_customers=True), evidence_text, brief
        )
        specs = [s for s in REPORTS if only_reports is None or s.number in only_reports]
        reports: list[Report] = []
        replacements: dict[int, int] = {}
        for spec in specs:
            title = report_title(tier, spec.title)
            self._progress(f"Writing Report {spec.number} - {title}")
            report = self._synthesize_checked(spec, title, shared)
            content, n = apply_attribution_check(report.content, names, context.attribution_policy)
            replacements[spec.number] = n
            reports.append(
                Report(
                    report_number=report.report_number,
                    title=report.title,
                    content=content,
                    confidence_summary=self._extract_confidence_summary(content),
                )
            )

        note = attribution_check_note(
            context.attribution_policy, len(names), sum(replacements.values())
        )
        for r in reports:
            if r.report_number == 1:
                r.content = f"{r.content}\n\n{note}"

        return AgentRunResult(
            operating_tier=tier,
            operating_tier_line=tier_line,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model=self._model,
            web_search_queries=queries,
            research_sources=sources,
            research_brief=brief,
            attribution_policy=context.attribution_policy,
            names_checked=len(names),
            attribution_replacements=replacements,
            reports=reports,
        )

    # -- phase 1: research -------------------------------------------------

    def research(
        self, context: CustomerContext, *, max_searches: int = 12, rounds: int = 2
    ) -> tuple[str, list[Source], list[str]]:
        tools = [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_searches}]
        # Named customers withheld: this prompt drives live search queries.
        context_text = render_context_text(context, include_customers=False)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompts.research_user_prompt(context_text)}
        ]

        chunks: list[str] = []
        sources: dict[str, Source] = {}
        queries: list[str] = []
        for round_idx in range(max(1, rounds)):
            if round_idx > 0:
                messages.append({"role": "user", "content": prompts.RESEARCH_FOLLOWUP_PROMPT})
            self._progress(f"Research round {round_idx + 1}/{max(1, rounds)} - searching the web")
            text, content = self._research_turn(messages, tools)
            messages.append({"role": "assistant", "content": content})
            if text.strip():
                chunks.append(text.strip())
            self._collect_sources_and_queries(content, sources, queries)

        header = (
            "RESEARCH BRIEF — public evidence only, gathered by live web search. Every row "
            "should carry its own source, source type, dates, confidence and "
            "FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN label."
        )
        body = "\n\n".join(f"----- research pass {i + 1} -----\n{c}" for i, c in enumerate(chunks))
        return f"{header}\n\n{body}".strip(), list(sources.values()), queries

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
                max_tokens=RESEARCH_MAX_TOKENS,
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
                q = getattr(block, "input", None) or {}
                if isinstance(q, dict) and q.get("query"):
                    queries.append(str(q["query"]))
            elif btype == "web_search_tool_result":
                results = getattr(block, "content", None)
                if not isinstance(results, list):
                    continue
                for item in results:
                    if getattr(item, "type", None) != "web_search_result":
                        continue
                    url = getattr(item, "url", None)
                    if url and url not in sources:
                        sources[url] = Source(
                            title=getattr(item, "title", "") or "",
                            url=url,
                            page_age=getattr(item, "page_age", None),
                        )
            elif btype == "text":
                for cit in getattr(block, "citations", None) or []:
                    url = getattr(cit, "url", None)
                    if url and url not in sources:
                        sources[url] = Source(title=getattr(cit, "title", "") or "", url=url)

    # -- phase 2: synthesis ------------------------------------------------

    _CONF_HEADING = re.compile(r"\n#+\s*Confidence\s+Summary\b[^\n]*\n", re.IGNORECASE)
    _LEADING_TITLE_H1 = re.compile(r"\A#\s+Report\s+\d+\b[^\n]*\n+", re.IGNORECASE)

    def _synthesize_checked(self, spec: ReportSpec, title: str, shared: str) -> Report:
        correction = ""
        for attempt in (1, 2):
            report = self._synthesize_one(spec, title, shared, correction)
            missing = missing_required_sections(spec, report.content)
            if not missing:
                return report
            logger.warning(
                "Report %d attempt %d missing required section(s): %s",
                spec.number, attempt, ", ".join(missing),
            )
            correction = (
                "\n\n## Your previous draft of this report was rejected\n\n"
                f"It did not contain these required headings, exactly as written: "
                f"{'; '.join(repr(m) for m in missing)}. Both must appear, in every run, "
                "including Tier 2. Write the complete report again."
            )
        raise ReportStructureError(
            f"Report {spec.number} was generated twice without required section(s): "
            f"{', '.join(missing)}"
        )

    def _synthesize_one(self, spec: ReportSpec, title: str, shared: str, correction: str = "") -> Report:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=SYNTHESIS_MAX_TOKENS,
            system=prompts.synthesis_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": [
                        # Identical across all nine calls: one cached prefix.
                        {"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}},
                        {"type": "text", "text": prompts.synthesis_report_instruction(spec, title) + correction},
                    ],
                }
            ],
            thinking={"type": "adaptive"},
        ) as stream:
            final = stream.get_final_message()

        text = "".join(
            b.text for b in final.content if getattr(b, "type", None) == "text"
        ).strip()
        if not text:
            raise RuntimeError(
                f"Report {spec.number}: model returned no text (stop_reason={final.stop_reason})."
            )
        if final.stop_reason == "max_tokens":
            text += "\n\n_[Note: generation hit the length ceiling; this report may be truncated.]_"
        text = self._LEADING_TITLE_H1.sub("", text, count=1).strip()
        return Report(
            report_number=spec.number,
            title=title,
            content=text,
            confidence_summary="",
        )

    @classmethod
    def _extract_confidence_summary(cls, text: str) -> str:
        m = cls._CONF_HEADING.search(text)
        if not m:
            return ""
        tail = text[m.end():]
        nxt = re.search(r"\n#+\s", tail)
        return (tail[: nxt.start()] if nxt else tail).strip()
