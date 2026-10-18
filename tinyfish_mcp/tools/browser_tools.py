"""Browser group: list_browser_session_usage, create_browser_session, terminate_browser_session."""

import logging
import re
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.browser import (
    CreateBrowserSessionData,
    CreateBrowserSessionResult,
    ListBrowserSessionUsageData,
    ListBrowserSessionUsageResult,
    TerminateBrowserSessionResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.browser")

BROWSER_SESSION_USAGE_URL = "https://api.browser.tinyfish.ai/usage"
BROWSER_SESSION_URL = "https://api.browser.tinyfish.ai/"
BROWSER_SESSION_TERMINATE_URL = "https://api.browser.tinyfish.ai/{sessionId}"

_PROXY_TYPES = ("tinyfish", "custom")
_COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


def _validate_proxy_config(proxy_config: dict[str, Any]) -> str | None:
    proxy_type = proxy_config.get("type")
    if proxy_type is not None and proxy_type not in _PROXY_TYPES:
        return "proxy_config.type must be one of 'tinyfish', 'custom'"
    country_code = proxy_config.get("country_code")
    if country_code is not None and not _COUNTRY_CODE_PATTERN.fullmatch(country_code):
        return "proxy_config.country_code must be a 2-letter uppercase ISO 3166-1 alpha-2 code"
    return None


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

    @mcp.tool(
        name="create_browser_session",
        description=(
            "Creates a remote browser session and returns CDP connection details — connect via "
            "Playwright's `connect_over_cdp` or any CDP client at the returned `cdp_url`. Egresses "
            "through the TinyFish residential proxy in the US by default, pinned to one exit IP "
            "for the life of the session; pass `proxy_config` to use a different TinyFish proxy "
            "country or bring your own. Call `terminate_browser_session` with the returned "
            "`session_id` to release the session early instead of waiting for the inactivity timeout."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def create_browser_session(
        url: str | None = Field(
            default=None,
            description="Target URL the session navigates to on startup. Bare domains (e.g. `tinyfish.ai`) are auto-prefixed with `https://`. Omit to start at `about:blank`.",
        ),
        timeout_seconds: int | None = Field(
            default=None,
            description="Inactivity timeout in seconds, 5-86400. Omit, pass null, or exceed your plan maximum to use the plan maximum instead (15 min free tier, 60 min paid).",
        ),
        proxy_config: dict[str, Any] | None = Field(
            default=None,
            description=(
                "Proxy for the session. Omit to use the TinyFish proxy in the US. Fields: "
                "`enabled` (bool), `type` (`tinyfish` for TinyFish's own proxy network or "
                "`custom` to bring your own), `country_code` (ISO 3166-1 alpha-2, TinyFish proxy "
                "only), `url`/`username`/`password` (custom proxy only)."
            ),
        ),
    ) -> CreateBrowserSessionResult:
        tlog = ToolLogger(logger, "create_browser_session")

        if timeout_seconds is not None and not (5 <= timeout_seconds <= 86400):
            return _err(CreateBrowserSessionResult, tlog, "VALIDATION_ERROR",
                        "timeout_seconds must be between 5 and 86400", 400)
        if proxy_config is not None:
            proxy_error = _validate_proxy_config(proxy_config)
            if proxy_error is not None:
                return _err(CreateBrowserSessionResult, tlog, "VALIDATION_ERROR", proxy_error, 400)

        body: dict[str, Any] = {}
        if url is not None:
            body["url"] = url
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds
        if proxy_config is not None:
            body["proxy_config"] = proxy_config

        try:
            data, status, retry_after = service.api_request(
                "POST", BROWSER_SESSION_URL, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = CreateBrowserSessionData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return CreateBrowserSessionResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(CreateBrowserSessionResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(CreateBrowserSessionResult, tlog, exc)

    @mcp.tool(
        name="terminate_browser_session",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Immediately terminates a remote browser session, releasing its resources instead of "
            "waiting for its inactivity timeout to expire. This ends the live CDP connection and "
            "any in-progress browser activity on that session — it cannot be resumed, only "
            "replaced by creating a new session with create_browser_session. Idempotent: calling "
            "it again on an already-ended session still returns success rather than an error. "
            "NEVER call this tool autonomously or as part of an automated flow. You MUST stop, "
            "tell the user exactly which session will be terminated, and wait for their explicit "
            "written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def terminate_browser_session(
        sessionId: str = Field(
            description="Session ID to terminate — the `session_id` returned by create_browser_session."
        ),
    ) -> TerminateBrowserSessionResult:
        tlog = ToolLogger(logger, "terminate_browser_session")

        if not sessionId.strip():
            return _err(TerminateBrowserSessionResult, tlog, "VALIDATION_ERROR", "sessionId must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "DELETE", BROWSER_SESSION_TERMINATE_URL.format(sessionId=sessionId),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                tlog.success()  # no response body (204) — nothing to construct
                return TerminateBrowserSessionResult(success=True, statusCode=status)
            return _upstream_err(TerminateBrowserSessionResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(TerminateBrowserSessionResult, tlog, exc)
