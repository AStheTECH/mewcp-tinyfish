"""Fetch group: fetch_extract_content, list_fetch_usage."""

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.fetch import (
    ExtractContentData,
    ExtractContentResult,
    FetchUsageListData,
    FetchUsageListResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.fetch")

EXTRACT_CONTENT_URL = "https://api.fetch.tinyfish.ai/"
LIST_USAGE_URL = "https://api.fetch.tinyfish.ai/usage"


def register_fetch_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="fetch_extract_content",
        description=(
            "Fetches 1-10 URLs in parallel (rendering JavaScript-heavy pages when needed) and "
            "returns clean extracted content as markdown (default), HTML, or a structured JSON "
            "document tree. Each URL is processed independently: a per-URL failure (e.g. "
            "target_http_error, page_not_found, timeout, bot_blocked, login_required, or content "
            "over the 20MB/50MB size caps) is reported in `errors` without failing the rest of the "
            "batch. `if_none_match` and `if_modified_since` are only valid when `urls` has exactly "
            "one entry. `include_selectors`/`exclude_selectors` scope or strip content per page; a "
            "page where no `include_selectors` entry matches fails with `selector_not_matched` "
            "(with `candidate_selectors` retry hints) rather than silently returning the full page, "
            "and selectors are unsupported on URLs that resolve to a direct PDF/CSV download "
            "(`selector_unsupported`)."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def fetch_extract_content(
        urls: list[str] = Field(
            description=(
                "Array of URLs to fetch (1-10). All URLs are fetched in parallel. Each URL is "
                "processed independently — if one fails, others still return successfully. "
                "Errors are reported per-URL in the `errors` array."
            )
        ),
        purpose: str | None = Field(
            default=None,
            description=(
                "Why these URLs are being fetched — the underlying goal or task the content will "
                "be used for (1-2000 characters). Used to better tailor fetching and extraction to "
                "your intent. Omit if there is no specific goal to share."
            ),
        ),
        format: str = Field(
            default="markdown",
            description=(
                "Output format for extracted content. `markdown` is ideal for LLM consumption. "
                "`html` returns cleaned semantic HTML. `json` returns a structured document tree. "
                "One of: markdown, html, json."
            ),
        ),
        links: bool = Field(
            default=False,
            description="Extract all outbound links from each page as absolute URLs, returned in each result's `links` array.",
        ),
        image_links: bool = Field(
            default=False,
            description="Extract all image URLs from each page as absolute URLs, returned in each result's `image_links` array.",
        ),
        page_metadata: bool = Field(
            default=False,
            description=(
                "Return page-head metadata for each page in the result's `page_metadata` object: "
                "canonical URL, favicon, robots directive, generator, viewport, keywords, Open "
                "Graph/Twitter card/article tags, and other named meta tags."
            ),
        ),
        ttl: int | None = Field(
            default=None,
            description=(
                "Caller freshness tolerance in seconds for a cached entry. Omit for unlimited "
                "tolerance (any cached entry is acceptable). Set to 0 to prefer a live fetch — a "
                "cached entry is still served if the origin's Cache-Control: max-age covers its age, "
                "or the host is on the operator's never-expire allowlist. Set to N > 0 to accept a "
                "cached entry younger than N seconds (max-age and the allowlist may only extend, "
                "never shorten, this tolerance). Must be >= 0."
            ),
        ),
        per_url_timeout_ms: int | None = Field(
            default=None,
            description=(
                "Wall-clock timeout budget in milliseconds applied independently to each URL "
                "(1-110000). A URL that exceeds its budget returns a per-URL timeout error while "
                "other URLs in the same request continue."
            ),
        ),
        if_none_match: str | None = Field(
            default=None,
            description=(
                "ETag validator from a prior fetch of this URL, forwarded verbatim as the "
                "`If-None-Match` header. Only valid when `urls` has exactly one entry — combined "
                "with a batch, the call is rejected. This endpoint does not persist validators; "
                "the caller owns replaying them."
            ),
        ),
        if_modified_since: str | None = Field(
            default=None,
            description=(
                "Last-Modified validator from a prior fetch of this URL, forwarded verbatim as the "
                "`If-Modified-Since` header. Only valid when `urls` has exactly one entry — "
                "combined with a batch, the call is rejected. This endpoint does not persist "
                "validators; the caller owns replaying them."
            ),
        ),
        include_etag_and_last_modified: bool = Field(
            default=False,
            description=(
                "Opt-in to receiving `etag`, `last_modified`, and `not_modified` on each result. "
                "Works with a single URL or a batch, independent of `if_none_match`/`if_modified_since`."
            ),
        ),
        include_selectors: list[str] | None = Field(
            default=None,
            description=(
                "CSS selectors (1-20 entries, each 1-1000 characters) that scope extracted content "
                "to elements matching ANY entry, concatenated in document order; bypasses automatic "
                "boilerplate removal. Page-level metadata (title, description, language, author, "
                "published_date) still comes from the full document. A URL where no entry matches "
                "fails with `selector_not_matched`; partial misses are reported in the result's "
                "`unmatched_selectors` instead. Unsupported for URLs that resolve to a direct "
                "PDF/CSV download (`selector_unsupported`)."
            ),
        ),
        exclude_selectors: list[str] | None = Field(
            default=None,
            description=(
                "CSS selectors (1-20 entries, each 1-1000 characters) for elements to remove "
                "before extraction — applied before `include_selectors` scopes what remains, so it "
                "also prunes inside selected regions. Entries that match nothing are a no-op. "
                "Unsupported for URLs that resolve to a direct PDF/CSV download (`selector_unsupported`)."
            ),
        ),
    ) -> ExtractContentResult:
        tlog = ToolLogger(logger, "fetch_extract_content")

        if not (1 <= len(urls) <= 10):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "urls must contain 1-10 entries", 400)
        if purpose is not None and not (1 <= len(purpose) <= 2000):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "purpose must be 1-2000 characters", 400)
        if format not in ("markdown", "html", "json"):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "format must be one of: markdown, html, json", 400)
        if ttl is not None and ttl < 0:
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "ttl must be >= 0", 400)
        if per_url_timeout_ms is not None and not (1 <= per_url_timeout_ms <= 110000):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "per_url_timeout_ms must be 1-110000", 400)
        if (if_none_match is not None or if_modified_since is not None) and len(urls) != 1:
            return _err(
                ExtractContentResult, tlog, "VALIDATION_ERROR",
                "if_none_match/if_modified_since are only valid when urls has exactly one entry", 400,
            )
        if include_selectors is not None and not (1 <= len(include_selectors) <= 20):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "include_selectors must contain 1-20 entries", 400)
        if exclude_selectors is not None and not (1 <= len(exclude_selectors) <= 20):
            return _err(ExtractContentResult, tlog, "VALIDATION_ERROR", "exclude_selectors must contain 1-20 entries", 400)

        body: dict[str, Any] = {
            "urls": urls,
            "format": format,
            "links": links,
            "image_links": image_links,
            "page_metadata": page_metadata,
            "include_etag_and_last_modified": include_etag_and_last_modified,
        }
        if purpose is not None:
            body["purpose"] = purpose
        if ttl is not None:
            body["ttl"] = ttl
        if per_url_timeout_ms is not None:
            body["per_url_timeout_ms"] = per_url_timeout_ms
        if if_none_match is not None:
            body["if_none_match"] = if_none_match
        if if_modified_since is not None:
            body["if_modified_since"] = if_modified_since
        if include_selectors is not None:
            body["include_selectors"] = include_selectors
        if exclude_selectors is not None:
            body["exclude_selectors"] = exclude_selectors

        try:
            data, status_code, retry_after = service.api_request(
                "POST", EXTRACT_CONTENT_URL, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                tlog.success()
                return ExtractContentResult(success=True, statusCode=status_code, data=ExtractContentData(**data))
            return _upstream_err(ExtractContentResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(ExtractContentResult, tlog, exc)

    @mcp.tool(
        name="list_fetch_usage",
        description=(
            "Lists fetch usage records for the authenticated user — URL, format, status, and "
            "metadata for each past fetch operation — with page-based pagination (`page`/`limit`, "
            "`total_pages`, `has_more`) and optional filtering by `status` (`completed` or "
            "`failed`) and time range."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def list_fetch_usage(
        start_after: str | None = Field(
            default=None,
            description=(
                "Only return usage records created after this timestamp (ISO 8601 date-time). The "
                "provider's docs do not describe the exact filtering semantics beyond the "
                "parameter name and type."
            ),
        ),
        end_before: str | None = Field(
            default=None,
            description=(
                "Only return usage records created before this timestamp (ISO 8601 date-time). The "
                "provider's docs do not describe the exact filtering semantics beyond the "
                "parameter name and type."
            ),
        ),
        status: str | None = Field(
            default=None,
            description="Filter by fetch status: `completed` or `failed`. Omit to return records of any status.",
        ),
        limit: int = Field(default=100, description="Maximum records per page (1-1000)."),
        page: int = Field(default=1, description="Page number to return, starting at 1."),
    ) -> FetchUsageListResult:
        tlog = ToolLogger(logger, "list_fetch_usage")

        if status is not None and status not in ("completed", "failed"):
            return _err(FetchUsageListResult, tlog, "VALIDATION_ERROR", "status must be one of: completed, failed", 400)
        if not (1 <= limit <= 1000):
            return _err(FetchUsageListResult, tlog, "VALIDATION_ERROR", "limit must be 1-1000", 400)
        if page < 1:
            return _err(FetchUsageListResult, tlog, "VALIDATION_ERROR", "page must be >= 1", 400)

        params: dict[str, Any] = {"limit": limit, "page": page}
        if start_after is not None:
            params["start_after"] = start_after
        if end_before is not None:
            params["end_before"] = end_before
        if status is not None:
            params["status"] = status

        try:
            data, status_code, retry_after = service.api_request(
                "GET", LIST_USAGE_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                tlog.success()
                return FetchUsageListResult(success=True, statusCode=status_code, data=FetchUsageListData(**data))
            return _upstream_err(FetchUsageListResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(FetchUsageListResult, tlog, exc)
