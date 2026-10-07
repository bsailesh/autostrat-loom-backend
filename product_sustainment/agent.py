"""
Product Sustainment Agent (Agent 4) — orchestration.

  0. compute         — compute.py, deterministic. Before anything else, so
                       research can be aimed at what the numbers flag.
  1. research()      — multi-round web search: lifecycle notices, supplier
                       risk, candidate alternates.
  2. extract_candidate_work() — ONE structured, schema-validated call. The
                       model supplies judgement; validation.py merges in the
                       computed date, quantity and applicability.
  3. synthesize()    — one streamed call per report, nine in all, sharing one
                       cached prefix. Computed tables are appended in code.

The structured call applies every lesson from Agent 5's Pass 1 failure
(fff5b4a, dd475f6): streamed with an adequate ceiling; max_tokens rejected
BEFORE parsing; stop_reason and output tokens logged at WARNING on every
attempt; no default on `items`; extra="forbid" so a misnamed field fails by
name and that name reaches the retry; a single wrapper key unwrapped rather
than retried; completeness checked per item.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable

from anthropic import Anthropic
from pydantic import ValidationError

from product_sustainment import prompts, results
from product_sustainment.compute import SustainmentResult, compute_sustainment
from product_sustainment.config import WEB_SEARCH_TOOL_TYPE, Settings
from product_sustainment.reports import REPORTS, ReportSpec
from product_sustainment.schemas import CandidateWorkItem, ModelCandidateWorkOutput
from product_sustainment.structure import (
    SustainmentData,
    compute_inputs,
    operating_tier,
    operating_tier_statement,
    render_structure_text,
    report_title,
)
from product_sustainment.validation import merge_and_partition

logger = logging.getLogger(__name__)

# A candidate work item with alternates and evidence runs 400-700 output
# tokens; a large BOM plausibly surfaces 30-40 at-risk parts, so 12-28k.
CANDIDATE_WORK_MAX_TOKENS = 32000
RESEARCH_MAX_TOKENS = 16000
SYNTHESIS_MAX_TOKENS = 20000


class CandidateWorkError(Exception):
    """The structured call was unusable twice -- truncated, schema-invalid or
    missing its tool call. Fails the run: nine reports narrating an empty
    payload is the Agent 5 Arden failure in a new costume."""


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
class DroppedCandidateWork:
    candidate_key: str
    gaps: list[str]


@dataclass
class AgentRunResult:
    operating_tier: str
    operating_tier_line: str
    generated_at: str
    model: str
    computation: SustainmentResult
    web_search_queries: list[str]
    research_sources: list[Source]
    research_brief: str
    candidate_work: list[CandidateWorkItem] = field(default_factory=list)
    candidate_work_dropped: list[DroppedCandidateWork] = field(default_factory=list)
    reports: list[Report] = field(default_factory=list)


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def unwrap_candidate_work_input(tool_input: Any) -> Any:
    """Recover `{"wrapper": {"items": [...]}}` -- a complete answer in the
    wrong place. Only the unambiguous shape: exactly one key, not `items`,
    with a dict under it that has `items`. Anything else is left for
    validation to reject by name."""
    if not isinstance(tool_input, dict) or len(tool_input) != 1:
        return tool_input
    (key, inner), = tool_input.items()
    if key == "items" or not isinstance(inner, dict) or "items" not in inner:
        return tool_input
    logger.warning("Candidate work arrived nested under %r; unwrapped", key)
    return inner


class ProductSustainmentAgent:
    def __init__(self, settings: Settings, *, progress: ProgressFn | None = None):
        self._model = settings.model
        self._client = Anthropic(api_key=settings.anthropic_api_key, timeout=900.0)
        self._progress = progress or _noop

    def run(
        self,
        data: SustainmentData,
        *,
        today: date,
        evidence_text: str = "",
        operational_text: str = "",
        max_searches: int = 16,
        research_rounds: int = 2,
        only_reports: list[int] | None = None,
    ) -> AgentRunResult:
        tier = operating_tier(data)
        tier_line = operating_tier_statement(data)
        self._progress(f"Operating tier: {tier}")

        computation = compute_sustainment(compute_inputs(data, today))
        results_text = results.render_results_text(computation, data)
        structure_text = render_structure_text(data, focus_parts=results.focus_parts(computation, data))

        priority = results.flagged_parts(computation, data)
        brief, sources, queries = self.research(
            structure_text, results_text, priority, max_searches=max_searches, rounds=research_rounds
        )

        self._progress("Extracting candidate work (structured)")
        kept, dropped = self.extract_candidate_work(structure_text, results_text, brief, computation, data)

        shared = prompts.synthesis_shared_block(
            tier_line,
            structure_text,
            results_text,
            evidence_text or "(no reliability or quality documents supplied)",
            operational_text or "(no fleet, maintenance or configuration data supplied)",
            brief,
            json.dumps([i.model_dump() for i in kept], indent=1),
        )
        specs = [s for s in REPORTS if only_reports is None or s.number in only_reports]
        reports: list[Report] = []
        for spec in specs:
            title = report_title(tier, spec.title)
            self._progress(f"Writing Report {spec.number} - {title}")
            text = self._synthesize_one(spec, title, shared)
            if spec.computed == "candidate_work":
                text = f"{text}\n\n{results.candidate_work_table(kept)}"
            elif spec.computed:
                text = f"{text}\n\n{results.computed_section(spec.computed, computation, data)}"
            reports.append(Report(spec.number, title, text, self._extract_confidence_summary(text)))

        return AgentRunResult(
            operating_tier=tier,
            operating_tier_line=tier_line,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model=self._model,
            computation=computation,
            web_search_queries=queries,
            research_sources=sources,
            research_brief=brief,
            candidate_work=kept,
            candidate_work_dropped=[DroppedCandidateWork(k, g) for k, g in dropped],
            reports=reports,
        )

    # -- research ----------------------------------------------------------

    def research(self, structure_text: str, results_text: str, priority: list[str], *,
                 max_searches: int = 16, rounds: int = 2) -> tuple[str, list[Source], list[str]]:
        tools = [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_searches}]
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompts.research_user_prompt(structure_text, results_text, priority)}
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
            self._collect(content, sources, queries)
        body = "\n\n".join(f"----- research pass {i + 1} -----\n{c}" for i, c in enumerate(chunks))
        header = "RESEARCH BRIEF — public evidence only, gathered by live web search."
        return f"{header}\n\n{body}".strip(), list(sources.values()), queries

    def _research_turn(self, messages, tools) -> tuple[str, list[Any]]:
        collected: list[Any] = []
        text_parts: list[str] = []
        working = list(messages)
        while True:
            resp = self._client.messages.create(
                model=self._model, max_tokens=RESEARCH_MAX_TOKENS,
                system=prompts.RESEARCH_SYSTEM_PROMPT, messages=working, tools=tools,
            )
            collected.extend(resp.content)
            text_parts += [b.text for b in resp.content if getattr(b, "type", None) == "text"]
            if resp.stop_reason == "pause_turn":
                working = working + [{"role": "assistant", "content": resp.content}]
                continue
            return "\n".join(text_parts), collected

    @staticmethod
    def _collect(content, sources: dict[str, Source], queries: list[str]) -> None:
        for block in content:
            btype = getattr(block, "type", None)
            if btype == "server_tool_use" and getattr(block, "name", None) == "web_search":
                q = getattr(block, "input", None) or {}
                if isinstance(q, dict) and q.get("query"):
                    queries.append(str(q["query"]))
            elif btype == "web_search_tool_result" and isinstance(getattr(block, "content", None), list):
                for item in block.content:
                    url = getattr(item, "url", None)
                    if getattr(item, "type", None) == "web_search_result" and url and url not in sources:
                        sources[url] = Source(getattr(item, "title", "") or "", url, getattr(item, "page_age", None))

    # -- candidate work (structured) ---------------------------------------

    def extract_candidate_work(
        self, structure_text: str, results_text: str, research_brief: str,
        computation: SustainmentResult, data: SustainmentData,
    ) -> tuple[list[CandidateWorkItem], list[tuple[str, list[str]]]]:
        """Retry policy: an unusable payload (truncated, schema-invalid, no
        tool call) is retried once, then fails the run. Incomplete items are
        retried once with their gaps named; on the second attempt the valid
        ones are kept and the rest recorded."""
        user_prompt = prompts.candidate_work_user_prompt(structure_text, results_text, research_brief)
        tool_name = prompts.CANDIDATE_WORK_TOOL_NAME
        tool_def = {
            "name": tool_name,
            "description": "Return candidate work for each at-risk part: driver, work implied, candidate "
                           "alternates with evidence, classification, confidence. No dates or quantities.",
            "input_schema": ModelCandidateWorkOutput.model_json_schema(),
        }
        last_error = "unknown error"
        for attempt in (1, 2):
            with self._client.messages.stream(
                model=self._model,
                max_tokens=CANDIDATE_WORK_MAX_TOKENS,
                system=prompts.CANDIDATE_WORK_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[tool_def],
                tool_choice={"type": "tool", "name": tool_name},
            ) as stream:
                response = stream.get_final_message()

            # WARNING on every attempt, not only failures: an empty payload
            # is undiagnosable afterwards without stop_reason and token use.
            logger.warning(
                "Candidate work attempt %d: stop_reason=%s, output_tokens=%s of %s",
                attempt, response.stop_reason, response.usage.output_tokens, CANDIDATE_WORK_MAX_TOKENS,
            )
            block = next((b for b in response.content if b.type == "tool_use" and b.name == tool_name), None)

            if response.stop_reason == "max_tokens":
                last_error = (
                    f"output hit the {CANDIDATE_WORK_MAX_TOKENS}-token ceiling (stop_reason=max_tokens, "
                    f"{response.usage.output_tokens} output tokens); the tool input is a truncated fragment"
                )
            elif block is None:
                last_error = f"no matching tool_use block (stop_reason={response.stop_reason})"
            else:
                try:
                    output = ModelCandidateWorkOutput.model_validate(unwrap_candidate_work_input(block.input))
                except ValidationError as e:
                    last_error = f"failed schema validation: {e}"
                else:
                    kept, dropped = merge_and_partition(output, computation, data)
                    if not dropped or attempt == 2:
                        if dropped:
                            logger.warning("Candidate work: keeping %d, dropping %d after retry", len(kept), len(dropped))
                        return kept, dropped
                    last_error = "items were not ready to emit -- " + "; ".join(
                        f"{k}: {', '.join(g)}" for k, g in dropped
                    )
            if attempt == 1:
                self._progress("Candidate work rejected on attempt 1 - retrying once")
                user_prompt = prompts.candidate_work_retry_prompt(user_prompt, last_error)
        raise CandidateWorkError(f"Candidate work call unusable twice: {last_error}")

    # -- synthesis ---------------------------------------------------------

    _CONF_HEADING = re.compile(r"\n#+\s*Confidence\s+Summary\b[^\n]*\n", re.IGNORECASE)
    _LEADING_TITLE_H1 = re.compile(r"\A#\s+Report\s+\d+\b[^\n]*\n+", re.IGNORECASE)

    def _synthesize_one(self, spec: ReportSpec, title: str, shared: str) -> str:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=SYNTHESIS_MAX_TOKENS,
            system=prompts.synthesis_system_prompt(),
            messages=[{"role": "user", "content": [
                {"type": "text", "text": shared, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": prompts.synthesis_report_instruction(spec, title)},
            ]}],
            thinking={"type": "adaptive"},
        ) as stream:
            final = stream.get_final_message()
        text = "".join(b.text for b in final.content if getattr(b, "type", None) == "text").strip()
        if not text:
            raise RuntimeError(f"Report {spec.number}: model returned no text (stop_reason={final.stop_reason}).")
        if final.stop_reason == "max_tokens":
            text += "\n\n_[Note: generation hit the length ceiling; this report may be truncated.]_"
        return self._LEADING_TITLE_H1.sub("", text, count=1).strip()

    @classmethod
    def _extract_confidence_summary(cls, text: str) -> str:
        m = cls._CONF_HEADING.search(text)
        if not m:
            return ""
        tail = text[m.end():]
        nxt = re.search(r"\n#+\s", tail)
        return (tail[: nxt.start()] if nxt else tail).strip()
