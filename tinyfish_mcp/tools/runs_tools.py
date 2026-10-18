"""Runs group: list_runs, get_run, cancel_run, get_step_screenshot, get_step_html_snapshot."""

import base64
import logging
import re

import pydantic
import requests
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas import ToolError
from ..schemas.runs import (
    RunBatchCancelData,
    RunBatchCancelResult,
    RunBatchGetData,
    RunBatchGetResult,
    RunCancelData,
    RunCancelResult,
    RunData,
    RunListData,
    RunListResult,
    RunResult,
    StepHtmlSnapshotData,
    StepHtmlSnapshotResult,
    StepScreenshotData,
    StepScreenshotResult,
)
from ..service import _auth_headers
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.runs")

RUNS_URL = "https://agent.tinyfish.ai/v1/runs"
RUN_URL = "https://agent.tinyfish.ai/v1/runs/{id}"
RUN_CANCEL_URL = "https://agent.tinyfish.ai/v1/runs/{id}/cancel"
RUNS_BATCH_URL = "https://agent.tinyfish.ai/v1/runs/batch"
RUNS_BATCH_CANCEL_URL = "https://agent.tinyfish.ai/v1/runs/batch/cancel"
STEP_SCREENSHOT_URL = "https://agent.tinyfish.ai/v1/runs/{id}/steps/{stepId}/screenshot"
STEP_HTML_SNAPSHOT_URL = "https://agent.tinyfish.ai/v1/runs/{id}/steps/{stepId}/html"

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
            description="Filter runs by goal text, case-insensitive partial match. Maximum length 500 characters. Omit to not filter by goal text.",
        ),
        created_after: str | None = Field(
            default=None,
            description="Only include runs created after this ISO 8601 timestamp. Omit to not filter by a lower bound.",
        ),
        created_before: str | None = Field(
            default=None,
            description="Only include runs created before this ISO 8601 timestamp. Omit to not filter by an upper bound.",
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
                result_data = RunListData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return RunListResult(success=True, statusCode=status_code, data=result_data)
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
        id: str = Field(description="Run ID to retrieve. Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
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
                result_data = RunData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return RunResult(success=True, statusCode=status_code, data=result_data)
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
        id: str = Field(description="Run ID to cancel. Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
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
                result_data = RunCancelData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return RunCancelResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(RunCancelResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunCancelResult, tlog, exc)

    @mcp.tool(
        name="get_runs_by_ids",
        description=(
            "Retrieves multiple automation runs by ID in a single request, returning each found "
            "run's status, goal, result, and error alongside a list of any IDs that were not found "
            "or not owned by the caller. Accepts 1-100 IDs per call."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def get_runs_by_ids(
        run_ids: list[str] = Field(
            description="Run IDs to fetch, 1-100 entries. Each must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."
        ),
    ) -> RunBatchGetResult:
        tlog = ToolLogger(logger, "get_runs_by_ids")

        if not (1 <= len(run_ids) <= 100):
            return _err(RunBatchGetResult, tlog, "VALIDATION_ERROR",
                        "run_ids must contain between 1 and 100 entries", 400)
        if not all(_ID_PATTERN.fullmatch(rid) for rid in run_ids):
            return _err(RunBatchGetResult, tlog, "VALIDATION_ERROR",
                        "each run_ids entry must match ^[A-Za-z0-9_-]+$", 400)

        try:
            data, status_code, retry_after = service.api_request(
                "POST", RUNS_BATCH_URL, body={"run_ids": run_ids},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = RunBatchGetData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return RunBatchGetResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(RunBatchGetResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunBatchGetResult, tlog, exc)

    @mcp.tool(
        name="cancel_runs_by_ids",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Cancels multiple in-progress automation runs by ID in a single bulk call (1-100 IDs). "
            "Only runs started via the async or SSE automation endpoints can be cancelled this way. "
            "This is idempotent per run — a run already in a terminal state (e.g. `COMPLETED`) is "
            "reported with its actual current status and an explanatory message rather than an "
            "error — but a per-run before-state is not returned and cannot be recovered from this "
            "call. NEVER call this tool autonomously or as part of an automated flow. You MUST "
            "stop, tell the user exactly which runs will be cancelled, and wait for their explicit "
            "written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def cancel_runs_by_ids(
        run_ids: list[str] = Field(
            description="Run IDs to cancel, 1-100 entries. Each must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."
        ),
    ) -> RunBatchCancelResult:
        tlog = ToolLogger(logger, "cancel_runs_by_ids")

        if not (1 <= len(run_ids) <= 100):
            return _err(RunBatchCancelResult, tlog, "VALIDATION_ERROR",
                        "run_ids must contain between 1 and 100 entries", 400)
        if not all(_ID_PATTERN.fullmatch(rid) for rid in run_ids):
            return _err(RunBatchCancelResult, tlog, "VALIDATION_ERROR",
                        "each run_ids entry must match ^[A-Za-z0-9_-]+$", 400)

        try:
            data, status_code, retry_after = service.api_request(
                "POST", RUNS_BATCH_CANCEL_URL, body={"run_ids": run_ids},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = RunBatchCancelData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return RunBatchCancelResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(RunBatchCancelResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(RunBatchCancelResult, tlog, exc)

    @mcp.tool(
        name="get_step_screenshot",
        description=(
            "Retrieves the JPEG screenshot captured at a specific automation run step, "
            "authenticated with the API key. Returns the image as base64-encoded bytes "
            "with its content type."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def get_step_screenshot(
        id: str = Field(description="Run ID. Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
        stepId: str = Field(description="Step ID (event ID). Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
    ) -> StepScreenshotResult:
        tlog = ToolLogger(logger, "get_step_screenshot")

        if not _ID_PATTERN.fullmatch(id):
            return _err(StepScreenshotResult, tlog, "VALIDATION_ERROR", "id must match ^[A-Za-z0-9_-]+$", 400)
        if not _ID_PATTERN.fullmatch(stepId):
            return _err(StepScreenshotResult, tlog, "VALIDATION_ERROR", "stepId must match ^[A-Za-z0-9_-]+$", 400)

        url = STEP_SCREENSHOT_URL.format(id=id, stepId=stepId)
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except Exception as exc:
            return _handle_request_exc(StepScreenshotResult, tlog, exc)

        if not 200 <= resp.status_code < 300:
            try:
                err_data = resp.json()
            except Exception:
                err_data = {"error": resp.text or "Empty response body"}
            return _upstream_err(StepScreenshotResult, tlog, resp.status_code, err_data)

        try:
            result_data = StepScreenshotData(
                content_type=resp.headers.get("Content-Type", "image/jpeg"),
                image_base64=base64.b64encode(resp.content).decode("ascii"),
            )
        except pydantic.ValidationError:
            tlog.failure("UPSTREAM_ERROR", "Response validation failed")  # str(e) embeds response field values — never log it
            return StepScreenshotResult(
                success=False, statusCode=502, retriable=False,
                error=ToolError(code="UPSTREAM_ERROR", message="Upstream response did not match the expected schema"),
            )

        tlog.success()
        return StepScreenshotResult(success=True, statusCode=resp.status_code, data=result_data)

    @mcp.tool(
        name="get_step_html_snapshot",
        description=(
            "Retrieves the full-page HTML snapshot captured at a specific automation run step, "
            "authenticated with the API key. Only available when the run was started with "
            "`capture_config.html: true`."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def get_step_html_snapshot(
        id: str = Field(description="Run ID. Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
        stepId: str = Field(description="Step ID (event ID). Must match `^[A-Za-z0-9_-]+$` (alphanumeric, underscore, hyphen)."),
    ) -> StepHtmlSnapshotResult:
        tlog = ToolLogger(logger, "get_step_html_snapshot")

        if not _ID_PATTERN.fullmatch(id):
            return _err(StepHtmlSnapshotResult, tlog, "VALIDATION_ERROR", "id must match ^[A-Za-z0-9_-]+$", 400)
        if not _ID_PATTERN.fullmatch(stepId):
            return _err(StepHtmlSnapshotResult, tlog, "VALIDATION_ERROR", "stepId must match ^[A-Za-z0-9_-]+$", 400)

        url = STEP_HTML_SNAPSHOT_URL.format(id=id, stepId=stepId)
        try:
            resp = requests.get(url, headers=_auth_headers(), timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        except Exception as exc:
            return _handle_request_exc(StepHtmlSnapshotResult, tlog, exc)

        if not 200 <= resp.status_code < 300:
            try:
                err_data = resp.json()
            except Exception:
                err_data = {"error": resp.text or "Empty response body"}
            return _upstream_err(StepHtmlSnapshotResult, tlog, resp.status_code, err_data)

        try:
            result_data = StepHtmlSnapshotData(
                content_type=resp.headers.get("Content-Type", "text/html"),
                html=resp.text,
            )
        except pydantic.ValidationError:
            tlog.failure("UPSTREAM_ERROR", "Response validation failed")  # str(e) embeds response field values — never log it
            return StepHtmlSnapshotResult(
                success=False, statusCode=502, retriable=False,
                error=ToolError(code="UPSTREAM_ERROR", message="Upstream response did not match the expected schema"),
            )

        tlog.success()
        return StepHtmlSnapshotResult(success=True, statusCode=resp.status_code, data=result_data)
