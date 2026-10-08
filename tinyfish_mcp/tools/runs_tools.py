"""Runs group: list_runs, get_run, cancel_run."""

import logging
import re

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.runs import (
    RunCancelData,
    RunCancelResult,
    RunData,
    RunListData,
    RunListResult,
    RunResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.runs")

RUNS_URL = "https://agent.tinyfish.ai/v1/runs"
RUN_URL = "https://agent.tinyfish.ai/v1/runs/{id}"
RUN_CANCEL_URL = "https://agent.tinyfish.ai/v1/runs/{id}/cancel"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_RUN_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")


def register_runs_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="list_runs",
        description=(
            "Lists automation runs with optional filtering by status, goal text, and creation date range. "
            "Returns paginated run summaries plus a total count, sorted newest-first by default; pass the "
            "`cursor` from a previous response's `pagination.next_cursor` to page through further results."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    def list_runs(
        status: str | None = Field(
            default=None,
            description="Filter by run status. One of `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`. Omit to include all statuses.",
        ),
        goal: str | None = Field(
            default=None,
            description="Filter runs by goal text, case-insensitive partial match. Maximum length 500 characters.",
        ),
        created_after: str | None = Field(
            default=None,
            description="Only include runs created after this ISO 8601 timestamp.",
        ),
        created_before: str | None = Field(
            default=None,
            description="Only include runs created before this ISO 8601 timestamp.",
        ),
        sort_direction: str | None = Field(
            default=None,
            description="Sort order by `created_at`. One of `asc`, `desc`. Defaults to `desc` (newest first).",
        ),
        cursor: str | None = Field(
            default=None,
            description="Pagination cursor from a previous response's `pagination.next_cursor`. Omit to start from the first page.",
        ),
        limit: int = Field(
            default=20,
            description="Maximum number of results to return (1-100). Defaults to 20.",
        ),
    ) -> RunListResult:
        tlog = ToolLogger(logger, "list_runs")

        if status is not None and status not in _RUN_STATUSES:
            return _err(RunListResult, tlog, "VALIDATION_ERROR",
                        f"status must be one of {', '.join(_RUN_STATUSES)}", 400)
        if sort_direction is not None and sort_direction not in ("asc", "desc"):
            return _err(RunListResult, tlog, "VALIDATION_ERROR",
                        "sort_direction must be one of 'asc', 'desc'", 400)
        if goal is not None and len(goal) > 500:
            return _err(RunListResult, tlog, "VALIDATION_ERROR",
                        "goal must be at most 500 characters", 400)
        if limit < 1 or limit > 100:
            return _err(RunListResult, tlog, "VALIDATION_ERROR",
                        "limit must be between 1 and 100", 400)

        params = {
            "status": status,
            "goal": goal,
            "created_after": created_after,
            "created_before": created_before,
            "sort_direction": sort_direction,
            "cursor": cursor,
            "limit": limit,
        }
        params = {k: v for k, v in params.items() if v is not None}

        try:
            data, status_code, retry_after = service.api_request(
                "GET", RUNS_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                tlog.success()
                return RunListResult(success=True, statusCode=status_code, data=RunListData(**data))
            return _upstream_err(RunListResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunListResult, tlog, exc)

    @mcp.tool(
        name="get_run",
        description=(
            "Retrieves full details for a single automation run by ID, including its status, goal, "
            "extracted result, step-by-step trace, and any error information. Use `screenshots` and "
            "`html` to control whether screenshot and HTML snapshot URLs are included in the response."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
    )
    def get_run(
        id: str = Field(description="Run ID to retrieve."),
        screenshots: str | None = Field(
            default=None,
            description="Screenshot delivery mode. One of `url` (absolute image URLs), `base64` (inline data URIs), `none` (omit screenshots). Defaults to `url`.",
        ),
        html: str | None = Field(
            default=None,
            description="HTML snapshot delivery mode. One of `url` (absolute snapshot URLs, only non-null when the run had HTML capture enabled), `none` (omit HTML URLs). Defaults to `url`.",
        ),
    ) -> RunResult:
        tlog = ToolLogger(logger, "get_run")

        if not _ID_PATTERN.fullmatch(id):
            return _err(RunResult, tlog, "VALIDATION_ERROR", "id must match ^[A-Za-z0-9_-]+$", 400)
        if screenshots is not None and screenshots not in ("url", "base64", "none"):
            return _err(RunResult, tlog, "VALIDATION_ERROR",
                        "screenshots must be one of 'url', 'base64', 'none'", 400)
        if html is not None and html not in ("url", "none"):
            return _err(RunResult, tlog, "VALIDATION_ERROR", "html must be one of 'url', 'none'", 400)

        params = {k: v for k, v in {"screenshots": screenshots, "html": html}.items() if v is not None}

        try:
            data, status_code, retry_after = service.api_request(
                "GET", RUN_URL.format(id=id), params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                tlog.success()
                return RunResult(success=True, statusCode=status_code, data=RunData(**data))
            return _upstream_err(RunResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunResult, tlog, exc)

    @mcp.tool(
        name="cancel_run",
        description=(
            "Cancels an in-progress automation run by ID. Only runs started via the async or SSE automation "
            "endpoints can be cancelled — a run started via the synchronous automation endpoint cannot be. "
            "This call is idempotent: calling it again on a run that is already cancelled or already finished "
            "still returns 200, with the run's actual current status and an explanatory `message` instead of an error."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def cancel_run(
        id: str = Field(description="Run ID to cancel."),
    ) -> RunCancelResult:
        tlog = ToolLogger(logger, "cancel_run")

        if not _ID_PATTERN.fullmatch(id):
            return _err(RunCancelResult, tlog, "VALIDATION_ERROR", "id must match ^[A-Za-z0-9_-]+$", 400)

        try:
            data, status_code, retry_after = service.api_request(
                "POST", RUN_CANCEL_URL.format(id=id),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                tlog.success()
                return RunCancelResult(success=True, statusCode=status_code, data=RunCancelData(**data))
            return _upstream_err(RunCancelResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunCancelResult, tlog, exc)
