"""
Technology & Regulatory Intelligence Agent (Agent 3) — orchestration.

Three phases. Market Insights' shape (research, then one streamed call per
report) with one phase inserted between them:

  1. research()              — one multi-round conversation with live web
                               search, scoped by the applicability envelope.
  2. extract_candidate_work() — ONE structured, schema-validated,
                               completeness-checked call. The authoritative
                               record of candidate work for the run.
  3. synthesize()            — one streamed call per report, narrating the
                               validated candidate work.

**Why phase 2 exists, and why it is before phase 3.** Candidate work appears
in report prose and as structured rows. Generating it structurally first and
narrating it afterwards means Agent 5 reads rows and never parses prose --
no second parser of an undocumented contract, which is a failure this
codebase has already hit twice (the Word export markdown parser, and
Agent 5's own report consumption). Doing it the other way round -- writing
reports then extracting candidate work from them -- would reintroduce
exactly that.

There is no deterministic compute module here, unlike Agent 5: no scores, no
utilisation, no arithmetic. The model researches and writes.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from anthropic import Anthropic
from pydantic import ValidationError

from tech_regulation import prompts
from tech_regulation.config import WEB_SEARCH_TOOL_TYPE, Settings
from tech_regulation.reports import REPORTS, ReportSpec
from tech_regulation.schemas import CandidateWorkItem, CandidateWorkOutput
from tech_regulation.scoping import (
    ScopingEnvelope,
    operating_state,
    operating_state_statement,
    render_envelope_text,
    report_title,
)
from tech_regulation.validation import partition_candidate_work

logger = logging.getLogger(__name__)


class CandidateWorkError(Exception):
    """Raised when the structured candidate-work call is unusable twice --
    truncated at the ceiling, schema-invalid, or missing its tool call.

    This fails the run rather than proceeding with nothing. Candidate work is
    this agent's primary contribution downstream, and nine reports narrating
    an empty payload is the Agent 5 Arden failure in a new costume: output
    that looks complete, reads confidently, and is silently missing the part
    that mattered."""


# The ceiling for the structured call, and the four lessons from Agent 5's
# Pass 1 failure (fff5b4a) that this module applies:
#
#   1. STREAM IT. A non-streamed request with a ceiling this size risks an
#      HTTP timeout before it risks truncation.
#   2. An ADEQUATE ceiling, sized from the payload rather than guessed. A
#      candidate work item with its applicability and evidence basis runs
#      300-450 output tokens; a scoped run over a full envelope plausibly
#      surfaces 30-40 of them, so a complete payload is 10-18k. 32k leaves
#      room above that without being so loose that a runaway goes unnoticed.
#   3. REJECT max_tokens BEFORE PARSING. A truncated tool input comes back
#      coerced to a fragment of the JSON the model was still writing, and
#      parsing it yields silent emptiness rather than an error.
#   4. VALIDATE COMPLETENESS, not just schema -- in validation.py.
#
# Belt and braces on (3) and (4): CandidateWorkOutput.items has no default,
# so the fragment that defeated Pass 1 fails schema validation here even if
# the stop_reason check were ever removed.
CANDIDATE_WORK_MAX_TOKENS = 32000

# Mirrors market_insights: research turns are non-streamed with pause_turn
# resumption (a proven path with the web-search tool), synthesis is streamed.
RESEARCH_MAX_TOKENS = 16000
SYNTHESIS_MAX_TOKENS = 20000


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


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
    """An item the model emitted that was not ready to emit. Kept in the
    result rather than discarded silently: "the model tried to surface this
    and could not complete it" is information, and the alternative is a
    finding disappearing with no trace."""
    candidate_key: str
    gaps: list[str]


@dataclass
class AgentRunResult:
    operating_state: str
    operating_state_line: str
    generated_at: str
    model: str
    web_search_queries: list[str]
    research_sources: list[Source]
    research_brief: str
    candidate_work: list[CandidateWorkItem] = field(default_factory=list)
    candidate_work_dropped: list[DroppedCandidateWork] = field(default_factory=list)
    reports: list[Report] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operating_state": self.operating_state,
            "operating_state_line": self.operating_state_line,
            "generated_at": self.generated_at,
            "model": self.model,
            "web_search_queries": self.web_search_queries,
            "research_sources": [asdict(s) for s in self.research_sources],
            "research_brief": self.research_brief,
            "candidate_work": [item.model_dump() for item in self.candidate_work],
            "candidate_work_dropped": [asdict(d) for d in self.candidate_work_dropped],
            "reports": [asdict(r) for r in self.reports],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class TechRegulationAgent:
    def __init__(self, settings: Settings, *, progress: ProgressFn | None = None):
        self._settings = settings
        self._model = settings.model
        self._client = Anthropic(api_key=settings.anthropic_api_key, timeout=900.0)
        self._progress = progress or _noop

    # -- public entrypoint -------------------------------------------------

    def run(
        self,
        envelope: ScopingEnvelope,
        *,
        max_searches: int = 16,
        research_rounds: int = 2,
        only_reports: list[int] | None = None,
    ) -> AgentRunResult:
        state = operating_state(envelope)
        state_line = operating_state_statement(envelope)
        self._progress(f"Operating state: {state}")

        brief, sources, queries = self.research(
            envelope, max_searches=max_searches, rounds=research_rounds
        )

        self._progress("Extracting candidate work (structured)")
        candidate_work, dropped = self.extract_candidate_work(envelope, brief)
        self._progress(
            f"Candidate work: {len(candidate_work)} item(s) emitted"
            + (f", {len(dropped)} dropped as incomplete" if dropped else "")
        )

        envelope_text = render_envelope_text(envelope)
        specs = [s for s in REPORTS if only_reports is None or s.number in only_reports]
        reports: list[Report] = []
        for spec in specs:
            title = report_title(state, spec.title)
            self._progress(f"Writing Report {spec.number} - {title}")
            reports.append(
                self._synthesize_one(spec, title, envelope_text, brief, candidate_work, state_line)
            )

        return AgentRunResult(
            operating_state=state,
            operating_state_line=state_line,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            model=self._model,
            web_search_queries=queries,
            research_sources=sources,
            research_brief=brief,
            candidate_work=candidate_work,
            candidate_work_dropped=[
                DroppedCandidateWork(candidate_key=key, gaps=gaps) for key, gaps in dropped
            ],
            reports=reports,
        )

    # -- phase 1: research -------------------------------------------------

    def research(
        self, envelope: ScopingEnvelope, *, max_searches: int = 16, rounds: int = 2
    ) -> tuple[str, list[Source], list[str]]:
        tools = [{"type": WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_searches}]
        envelope_text = render_envelope_text(envelope)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompts.research_user_prompt(envelope_text)}
        ]

        brief_chunks: list[str] = []
        sources: dict[str, Source] = {}
        queries: list[str] = []

        for round_idx in range(max(1, rounds)):
            if round_idx > 0:
                messages.append({"role": "user", "content": prompts.RESEARCH_FOLLOWUP_PROMPT})

            self._progress(f"Research round {round_idx + 1}/{max(1, rounds)} - searching the web")
            text, msg_content = self._research_turn(messages, tools)
            messages.append({"role": "assistant", "content": msg_content})
            if text.strip():
                brief_chunks.append(text.strip())
            self._collect_sources_and_queries(msg_content, sources, queries)

        brief = self._assemble_brief(envelope_text, brief_chunks)
        self._progress(
            f"Research complete - {len(sources)} unique sources, {len(queries)} searches"
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
                        sources[url] = Source(title=getattr(cit, "title", "") or "", url=url)

    @staticmethod
    def _assemble_brief(envelope_text: str, chunks: list[str]) -> str:
        header = (
            "RESEARCH BRIEF — technology and regulatory intelligence, gathered against the "
            "applicability envelope below by live web search.\n"
            "Every row should carry its own source, source type, dates, confidence and "
            "FACT/OBSERVATION/INTERPRETATION/FORECAST/UNKNOWN label, plus the technology "
            "evidence label where it applies.\n\n"
            f"{envelope_text}\n"
        )
        body = "\n\n".join(
            f"----- research pass {i + 1} -----\n{c}" for i, c in enumerate(chunks)
        )
        return f"{header}\n{body}".strip()

    # -- phase 2: candidate work (structured) ------------------------------

    def extract_candidate_work(
        self, envelope: ScopingEnvelope, research_brief: str
    ) -> tuple[list[CandidateWorkItem], list[tuple[str, list[str]]]]:
        """The structured call. Returns (emittable items, dropped items).

        Retry policy, and why it differs between failure kinds:

        * Truncated, schema-invalid, or no tool call -- the payload is
          unusable as a whole, so retry once and then fail the run.
        * Individual items incomplete -- the payload is usable, just not
          entirely. Retry once with the specific gaps named, giving the model
          a chance to complete them from evidence it already has; on the
          second attempt keep whatever is valid and record the rest. Failing
          nine reports because one item of thirty lacked a date would be the
          wrong trade, and prompt_draft_v2 Part 3 specifies dropping the item
          rather than failing.
        """
        envelope_text = render_envelope_text(envelope)
        user_prompt = prompts.candidate_work_user_prompt(envelope_text, research_brief)
        tool_name = prompts.CANDIDATE_WORK_TOOL_NAME
        tool_def = {
            "name": tool_name,
            "description": (
                "Return every piece of candidate work this run's evidence implies for this "
                "customer: driver, date, applicability, work implied and evidence basis."
            ),
            "input_schema": CandidateWorkOutput.model_json_schema(),
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

            # Logged on every attempt, not only failures. Agent 5's empty Arden
            # payload was undiagnosable after the fact precisely because
            # nothing recorded stop_reason or how much of the ceiling was used.
            logger.info(
                "Candidate work attempt %d: stop_reason=%s, output_tokens=%s of %s",
                attempt,
                response.stop_reason,
                response.usage.output_tokens,
                CANDIDATE_WORK_MAX_TOKENS,
            )

            block = next(
                (b for b in response.content if b.type == "tool_use" and b.name == tool_name), None
            )

            if response.stop_reason == "max_tokens":
                # Checked before the block is parsed at all.
                last_error = (
                    f"output hit the {CANDIDATE_WORK_MAX_TOKENS}-token ceiling "
                    f"(stop_reason=max_tokens, {response.usage.output_tokens} output tokens); "
                    "the tool input is a truncated fragment, not an answer"
                )
            elif block is None:
                last_error = (
                    f"no matching tool_use block in response (stop_reason={response.stop_reason})"
                )
            else:
                try:
                    output = CandidateWorkOutput.model_validate(block.input)
                except ValidationError as e:
                    last_error = f"failed schema validation: {e}"
                else:
                    kept, dropped = partition_candidate_work(output)
                    if not dropped:
                        return kept, []

                    last_error = "items were not ready to emit -- " + "; ".join(
                        f"{key}: {', '.join(gaps)}" for key, gaps in dropped
                    )
                    if attempt == 2:
                        logger.warning(
                            "Candidate work: keeping %d item(s), dropping %d after retry: %s",
                            len(kept),
                            len(dropped),
                            last_error,
                        )
                        return kept, dropped

            if attempt == 1:
                logger.warning("Candidate work rejected on attempt 1: %s", last_error)
                self._progress("Candidate work rejected on attempt 1 - retrying once")
                user_prompt = prompts.candidate_work_retry_prompt(user_prompt, last_error)

        raise CandidateWorkError(f"Candidate work call unusable twice: {last_error}")

    # -- phase 3: synthesis ------------------------------------------------
    #
    # A report is a Markdown document, not a bag of struct fields, so it is
    # streamed plain text rather than a forced tool call -- the same reasoning
    # market_insights records: the forced-tool path truncates at max_tokens
    # with the whole `content` string unparseable.

    _CONF_HEADING = re.compile(r"\n#+\s*Confidence\s+Summary\b[^\n]*\n", re.IGNORECASE)
    _LEADING_TITLE_H1 = re.compile(r"\A#\s+Report\s+\d+\b[^\n]*\n+", re.IGNORECASE)

    def _synthesize_one(
        self,
        spec: ReportSpec,
        title: str,
        envelope_text: str,
        research_brief: str,
        candidate_work: list[CandidateWorkItem],
        operating_state_line: str,
    ) -> Report:
        with self._client.messages.stream(
            model=self._model,
            max_tokens=SYNTHESIS_MAX_TOKENS,
            system=prompts.synthesis_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": prompts.synthesis_user_prompt(
                        spec,
                        envelope_text,
                        research_brief,
                        candidate_work,
                        operating_state_line,
                        title,
                    ),
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
            confidence_summary=self._extract_confidence_summary(text),
        )

    @classmethod
    def _extract_confidence_summary(cls, text: str) -> str:
        m = cls._CONF_HEADING.search(text)
        if not m:
            return ""
        tail = text[m.end():]
        nxt = re.search(r"\n#+\s", tail)
        return (tail[: nxt.start()] if nxt else tail).strip()
