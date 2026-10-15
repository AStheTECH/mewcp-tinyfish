"""Browser group: list_browser_session_usage."""

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.browser import ListBrowserSessionUsageData, ListBrowserSessionUsageResult
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.browser")

BROWSER_SESSION_USAGE_URL = "https://api.browser.tinyfish.ai/usage"


def register_browser_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="list_browser_session_usage",
        description=(
            "Lists Tetra browser session usage for the authenticated user — duration, data "
            "transfer, mode, and status for each session — with page-based pagination and "
            "optional filtering by session ID, status, and time range."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def list_browser_session_usage(
        session_id: str | None = Field(
            default=None, description="Filter to a single browser session ID. Omit to include all sessions."
        ),
        start_after: str | None = Field(
            default=None,
            description="Only include sessions started at or after this timestamp (RFC 3339 date-time). Omit to not filter by a lower bound.",
        ),
        end_before: str | None = Field(
            default=None,
            description="Only include sessions started before this timestamp (RFC 3339 date-time). Omit to not filter by an upper bound.",
        ),
        status: str | None = Field(
            default=None, description="Filter by session status. One of `running`, `ended`. Omit to include both."
        ),
        limit: int = Field(default=100, description="Maximum number of records to return per page. Range 1-1000. Defaults to 100."),
        page: int = Field(default=1, description="Page number for pagination, starting from 1. Defaults to 1."),
    ) -> ListBrowserSessionUsageResult:
        tlog = ToolLogger(logger, "list_browser_session_usage")

        if status is not None and status not in ("running", "ended"):
            return _err(ListBrowserSessionUsageResult, tlog, "VALIDATION_ERROR",
                        "status must be one of: running, ended", 400)
        if not (1 <= limit <= 1000):
            return _err(ListBrowserSessionUsageResult, tlog, "VALIDATION_ERROR", "limit must be 1-1000", 400)
        if page < 1:
            return _err(ListBrowserSessionUsageResult, tlog, "VALIDATION_ERROR", "page must be >= 1", 400)

        params: dict[str, Any] = {"limit": limit, "page": page}
        if session_id is not None:
            params["session_id"] = session_id
        if start_after is not None:
            params["start_after"] = start_after
        if end_before is not None:
            params["end_before"] = end_before
        if status is not None:
            params["status"] = status

        try:
            data, status_code, retry_after = service.api_request(
                "GET", BROWSER_SESSION_USAGE_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = ListBrowserSessionUsageData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return ListBrowserSessionUsageResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(ListBrowserSessionUsageResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(ListBrowserSessionUsageResult, tlog, exc)
