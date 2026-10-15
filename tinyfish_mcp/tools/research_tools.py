"""Research group: run_research_sse, start_research_async, attach_research_progress,
list_research_runs, get_research_run, cancel_research_run."""

import json
import logging
from typing import Any, Literal

import pydantic
import requests
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas import ToolError
from ..schemas.research import (
    CancelResearchRunData,
    CancelResearchRunResult,
    GetResearchRunResult,
    ListResearchRunsData,
    ListResearchRunsResult,
    ResearchRunData,
    ResearchStreamData,
    ResearchStreamResult,
    StartResearchAsyncData,
    StartResearchAsyncResult,
)
from ..service import _auth_headers
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.research")

RUN_RESEARCH_SSE_URL = "https://agent.tinyfish.ai/v1/automation/run-research"
START_RESEARCH_ASYNC_URL = "https://agent.tinyfish.ai/v1/automation/run-research-async"
ATTACH_RESEARCH_PROGRESS_URL = "https://agent.tinyfish.ai/v1/research-run/{research_run_id}/events"
RESEARCH_RUNS_URL = "https://agent.tinyfish.ai/v1/research-run"
RESEARCH_RUN_URL = "https://agent.tinyfish.ai/v1/research-run/{research_run_id}"
RESEARCH_RUN_CANCEL_URL = "https://agent.tinyfish.ai/v1/research-run/{research_run_id}/cancel"

_RESEARCH_STATUSES = ("RUNNING", "COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT", "QUEUED")


def _build_research_body(
    query, mode, stream, output_language, weak_sources_enabled, domain_type,
    after_date, before_date, recency_minutes, domain_filter, prior_run_id, session_id,
) -> dict[str, Any]:
    body: dict[str, Any] = {"query": query}
    optional = {
        "mode": mode,
        "stream": stream,
        "output_language": output_language,
        "weak_sources_enabled": weak_sources_enabled,
        "domain_type": domain_type,
        "after_date": after_date,
        "before_date": before_date,
        "recency_minutes": recency_minutes,
        "domain_filter": domain_filter,
        "prior_run_id": prior_run_id,
        "session_id": session_id,
    }
    for key, value in optional.items():
        if value is not None:
            body[key] = value
    return body


def _consume_research_stream(resp, tlog, result_class):
    """Consume an SSE research event stream to its terminal `done` event and return one result.
    Shared by run_research_sse and attach_research_progress — both read the same event catalog."""
    research_run_id: str | None = None
    result_text: str | None = None
    citations: list[str] = []
    iterations_seen: list[int] = []
    done = False

    try:
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[len("data: "):])
            except json.JSONDecodeError:
                continue
            event_type = event.get("event")
            if event_type == "created":
                research_run_id = event.get("research_run_id", research_run_id)
            elif event_type == "plan_updated":
                iteration = event.get("iteration")
                if iteration is not None:
                    iterations_seen.append(iteration)
            elif event_type == "synthesis_delta":
                continue
            elif event_type == "final_result":
                result_text = event.get("result")
                citations = event.get("citations", citations)
            elif event_type == "done":
                done = True
                break
    except Exception as exc:
        return _handle_request_exc(result_class, tlog, exc)
    finally:
        resp.close()

    if not done:
        tlog.failure("UPSTREAM_ERROR", "SSE stream ended before a done event")
        return result_class(
            success=False, statusCode=502, retriable=True,
            error=ToolError(code="UPSTREAM_ERROR", message="Research stream ended before completion"),
        )

    try:
        result_data = ResearchStreamData(
            research_run_id=research_run_id, result=result_text,
            citations=citations, iterations_seen=iterations_seen,
        )
    except pydantic.ValidationError:
        tlog.failure("UPSTREAM_ERROR", "Response validation failed")  # str(e) embeds response field values — never log it
        return result_class(
            success=False, statusCode=502, retriable=False,
            error=ToolError(code="UPSTREAM_ERROR", message="Upstream response did not match the expected schema"),
        )

    tlog.success()
    return result_class(success=True, statusCode=200, data=result_data)


def register_research_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="run_research_sse",
        description=(
            "Runs a research task — searching, evaluating sources, and synthesizing a cited report "
            "— and streams its progress to completion synchronously, blocking until the terminal "
            "`done` event. Returns the research run ID, the synthesized report, its citations, and "
            "the plan iterations seen along the way. Always streams, even when `stream` is false; "
            "`prior_run_id` and `session_id` are mutually exclusive."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def run_research_sse(
        query: str = Field(description="Research question. Length 1-2000 characters."),
        mode: Literal["auto", "standard", "deep", "max"] | None = Field(
            default=None,
            description="Depth of research. Omit to use `deep`; the legacy `auto` value selects `standard`.",
        ),
        stream: bool | None = Field(
            default=None,
            description="Emit report text through `synthesis_delta` events as it's written. This tool blocks until completion regardless of this flag, so streamed deltas are consumed internally and not surfaced. Omit to use the provider's default.",
        ),
        output_language: str | None = Field(
            default=None, description="BCP 47 language tag for the report, e.g. `ja`. Omit to use the provider's default language."
        ),
        weak_sources_enabled: bool | None = Field(
            default=None, description="Allow relevant social and community sources. Omit to use the provider's default."
        ),
        domain_type: Literal["web", "news", "research_paper"] | None = Field(
            default=None, description="Source pool to research over. Omit to use the provider's default."
        ),
        after_date: str | None = Field(
            default=None,
            description="Include results on or after this date (YYYY-MM-DD). Not combinable with recency_minutes. Omit to not filter by a lower date bound.",
        ),
        before_date: str | None = Field(
            default=None,
            description="Include results on or before this date (YYYY-MM-DD). Not combinable with recency_minutes. Omit to not filter by an upper date bound.",
        ),
        recency_minutes: int | None = Field(
            default=None,
            description="Include results from the last 1-5,256,000 minutes. Not combinable with after_date/before_date. Omit to not filter by recency.",
        ),
        domain_filter: dict[str, Any] | None = Field(
            default=None, description="Domain preferences; each list accepts at most 150 entries. Omit to not filter by domain."
        ),
        prior_run_id: str | None = Field(
            default=None,
            description="Seed this run with a completed report and its evidence. Mutually exclusive with session_id. Omit to start fresh.",
        ),
        session_id: str | None = Field(
            default=None,
            description="Continue a standard-mode session (UUID). Mutually exclusive with prior_run_id. Omit to start a new session.",
        ),
    ) -> ResearchStreamResult:
        tlog = ToolLogger(logger, "run_research_sse")

        if not query or not query.strip():
            return _err(ResearchStreamResult, tlog, "VALIDATION_ERROR", "query must not be empty", 400)
        if prior_run_id is not None and session_id is not None:
            return _err(ResearchStreamResult, tlog, "VALIDATION_ERROR",
                        "prior_run_id and session_id are mutually exclusive", 400)

        body = _build_research_body(
            query, mode, stream, output_language, weak_sources_enabled, domain_type,
            after_date, before_date, recency_minutes, domain_filter, prior_run_id, session_id,
        )

        try:
            resp = requests.post(
                RUN_RESEARCH_SSE_URL, headers=_auth_headers(), json=body,
                stream=True, timeout=(CONNECT_TIMEOUT, 600),  # long-running stream, not the READ_TIMEOUT default
            )
        except Exception as exc:
            return _handle_request_exc(ResearchStreamResult, tlog, exc)

        if not 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except Exception:
                data = {"error": resp.text or "Empty response body"}
            return _upstream_err(ResearchStreamResult, tlog, resp.status_code, data)

        return _consume_research_stream(resp, tlog, ResearchStreamResult)

    @mcp.tool(
        name="start_research_async",
        description=(
            "Enqueues a research task and returns its `research_run_id` immediately after durable "
            "dispatch, without waiting for completion. Poll `get_research_run` or attach with "
            "`attach_research_progress` for results."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def start_research_async(
        query: str = Field(description="Research question. Length 1-2000 characters."),
        mode: Literal["auto", "standard", "deep", "max"] | None = Field(
            default=None,
            description="Depth of research. Omit to use `deep`; the legacy `auto` value selects `standard`.",
        ),
        stream: bool | None = Field(
            default=None, description="Emit report text through synthesis_delta events on the attach/events endpoint as it's written. Omit to use the provider's default."
        ),
        output_language: str | None = Field(
            default=None, description="BCP 47 language tag for the report, e.g. `ja`. Omit to use the provider's default language."
        ),
        weak_sources_enabled: bool | None = Field(
            default=None, description="Allow relevant social and community sources. Omit to use the provider's default."
        ),
        domain_type: Literal["web", "news", "research_paper"] | None = Field(
            default=None, description="Source pool to research over. Omit to use the provider's default."
        ),
        after_date: str | None = Field(
            default=None,
            description="Include results on or after this date (YYYY-MM-DD). Not combinable with recency_minutes. Omit to not filter by a lower date bound.",
        ),
        before_date: str | None = Field(
            default=None,
            description="Include results on or before this date (YYYY-MM-DD). Not combinable with recency_minutes. Omit to not filter by an upper date bound.",
        ),
        recency_minutes: int | None = Field(
            default=None,
            description="Include results from the last 1-5,256,000 minutes. Not combinable with after_date/before_date. Omit to not filter by recency.",
        ),
        domain_filter: dict[str, Any] | None = Field(
            default=None, description="Domain preferences; each list accepts at most 150 entries. Omit to not filter by domain."
        ),
        prior_run_id: str | None = Field(
            default=None,
            description="Seed this run with a completed report and its evidence. Mutually exclusive with session_id. Omit to start fresh.",
        ),
        session_id: str | None = Field(
            default=None,
            description="Continue a standard-mode session (UUID). Mutually exclusive with prior_run_id. Omit to start a new session.",
        ),
    ) -> StartResearchAsyncResult:
        tlog = ToolLogger(logger, "start_research_async")

        if not query or not query.strip():
            return _err(StartResearchAsyncResult, tlog, "VALIDATION_ERROR", "query must not be empty", 400)
        if prior_run_id is not None and session_id is not None:
            return _err(StartResearchAsyncResult, tlog, "VALIDATION_ERROR",
                        "prior_run_id and session_id are mutually exclusive", 400)

        body = _build_research_body(
            query, mode, stream, output_language, weak_sources_enabled, domain_type,
            after_date, before_date, recency_minutes, domain_filter, prior_run_id, session_id,
        )

        try:
            data, status, retry_after = service.api_request(
                "POST", START_RESEARCH_ASYNC_URL, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = StartResearchAsyncData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return StartResearchAsyncResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(StartResearchAsyncResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(StartResearchAsyncResult, tlog, exc)

    @mcp.tool(
        name="attach_research_progress",
        description=(
            "Reconnects to a research run's live progress stream and blocks until the terminal "
            "`done` event, returning the same shape as `run_research_sse`: research run ID, "
            "synthesized report, citations, and plan iterations seen. Pass `last_event_id` to "
            "resume after a dropped connection without missing events. Disconnecting does not "
            "cancel the research; once the stream is gone, poll `get_research_run` instead."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def attach_research_progress(
        research_run_id: str = Field(description="Research run identifier to attach to."),
        last_event_id: str | None = Field(
            default=None,
            description="Resume the stream after this event ID. Omit to attach from the current point in the stream.",
        ),
    ) -> ResearchStreamResult:
        tlog = ToolLogger(logger, "attach_research_progress")

        if not research_run_id.strip():
            return _err(ResearchStreamResult, tlog, "VALIDATION_ERROR", "research_run_id must not be empty", 400)

        headers = _auth_headers()
        if last_event_id is not None:
            headers["Last-Event-ID"] = last_event_id

        try:
            resp = requests.get(
                ATTACH_RESEARCH_PROGRESS_URL.format(research_run_id=research_run_id),
                headers=headers, stream=True, timeout=(CONNECT_TIMEOUT, 600),  # long-running stream, not the READ_TIMEOUT default
            )
        except Exception as exc:
            return _handle_request_exc(ResearchStreamResult, tlog, exc)

        if not 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except Exception:
                data = {"error": resp.text or "Empty response body"}
            return _upstream_err(ResearchStreamResult, tlog, resp.status_code, data)

        return _consume_research_stream(resp, tlog, ResearchStreamResult)

    @mcp.tool(
        name="list_research_runs",
        description=(
            "Lists saved research runs with optional filtering by status, query text, and creation "
            "date range. Returns paginated run summaries plus a total count, sorted newest-first by "
            "default; pass the `cursor` from a previous response's `pagination.next_cursor` (with "
            "the same `sort_direction` used to generate it) to page through further results."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def list_research_runs(
        status: str | None = Field(
            default=None,
            description=f"Filter by research run status. One of {', '.join(_RESEARCH_STATUSES)}. Omit to include all statuses.",
        ),
        query: str | None = Field(
            default=None,
            description="Filter by query text, case-insensitive partial match. Maximum 500 characters. Omit to not filter by query text.",
        ),
        created_after: str | None = Field(
            default=None, description="Only include runs created after this ISO 8601 timestamp. Omit to not filter by a lower bound."
        ),
        created_before: str | None = Field(
            default=None, description="Only include runs created before this ISO 8601 timestamp. Omit to not filter by an upper bound."
        ),
        sort_direction: Literal["asc", "desc"] | None = Field(
            default=None, description="Sort order by `created_at`. Defaults to `desc` (newest first)."
        ),
        cursor: str | None = Field(
            default=None,
            description="Pagination cursor from a previous response's `pagination.next_cursor`. Must be replayed with the same `sort_direction` that produced it. Omit to start from the first page.",
        ),
        limit: int = Field(default=20, description="Maximum number of results to return (1-100). Defaults to 20."),
    ) -> ListResearchRunsResult:
        tlog = ToolLogger(logger, "list_research_runs")

        if status is not None and status not in _RESEARCH_STATUSES:
            return _err(ListResearchRunsResult, tlog, "VALIDATION_ERROR",
                        f"status must be one of {', '.join(_RESEARCH_STATUSES)}", 400)
        if sort_direction is not None and sort_direction not in ("asc", "desc"):
            return _err(ListResearchRunsResult, tlog, "VALIDATION_ERROR",
                        "sort_direction must be one of 'asc', 'desc'", 400)
        if query is not None and len(query) > 500:
            return _err(ListResearchRunsResult, tlog, "VALIDATION_ERROR", "query must be at most 500 characters", 400)
        if not (1 <= limit <= 100):
            return _err(ListResearchRunsResult, tlog, "VALIDATION_ERROR", "limit must be between 1 and 100", 400)

        params = {
            "status": status,
            "query": query,
            "created_after": created_after,
            "created_before": created_before,
            "sort_direction": sort_direction,
            "cursor": cursor,
            "limit": limit,
        }
        params = {k: v for k, v in params.items() if v is not None}

        try:
            data, status_code, retry_after = service.api_request(
                "GET", RESEARCH_RUNS_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = ListResearchRunsData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return ListResearchRunsResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(ListResearchRunsResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(ListResearchRunsResult, tlog, exc)

    @mcp.tool(
        name="get_research_run",
        description=(
            "Retrieves one saved research run by ID: its status, quick and deep results, research "
            "plan, gathered evidence, and iteration count. `error` here is the run's own terminal "
            "outcome (why it failed or was cancelled), not an error from the underlying content or "
            "search providers."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def get_research_run(
        research_run_id: str = Field(description="Research run identifier."),
    ) -> GetResearchRunResult:
        tlog = ToolLogger(logger, "get_research_run")

        if not research_run_id.strip():
            return _err(GetResearchRunResult, tlog, "VALIDATION_ERROR", "research_run_id must not be empty", 400)

        try:
            data, status_code, retry_after = service.api_request(
                "GET", RESEARCH_RUN_URL.format(research_run_id=research_run_id),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = ResearchRunData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return GetResearchRunResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(GetResearchRunResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(GetResearchRunResult, tlog, exc)

    @mcp.tool(
        name="cancel_research_run",
        description=(
            "Cancels a running research run by ID. This call is idempotent: calling it again on an "
            "already-terminal run still returns 200 with `cancelled: false` and the run's actual "
            "current status, instead of an error."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def cancel_research_run(
        research_run_id: str = Field(description="Research run identifier to cancel."),
    ) -> CancelResearchRunResult:
        tlog = ToolLogger(logger, "cancel_research_run")

        if not research_run_id.strip():
            return _err(CancelResearchRunResult, tlog, "VALIDATION_ERROR", "research_run_id must not be empty", 400)

        try:
            data, status_code, retry_after = service.api_request(
                "POST", RESEARCH_RUN_CANCEL_URL.format(research_run_id=research_run_id),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = CancelResearchRunData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return CancelResearchRunResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(CancelResearchRunResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(CancelResearchRunResult, tlog, exc)
