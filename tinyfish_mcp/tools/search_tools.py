"""Search group: search_web, list_search_usage."""

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.search import (
    SearchUsageListData,
    SearchUsageListResult,
    WebSearchData,
    WebSearchResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.search")

SEARCH_WEB_URL = "https://api.search.tinyfish.ai/"
SEARCH_USAGE_URL = "https://api.search.tinyfish.ai/usage"


def register_search_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="search_web",
        description=(
            "Searches the web and returns ranked results with titles, snippets, and URLs, "
            "plus the total result count and current page. Location and language each "
            "auto-resolve from the other when only one is set (defaulting to US/en if neither "
            "is set); `page` is capped at 10; and `pub_year_min`/`pub_year_max` only apply when "
            "`domain_type` is `research_paper`."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def search_web(
        query: str = Field(description="Search query. Length 1-2000."),
        purpose: str | None = Field(
            default=None,
            description=(
                "Why this search is being run — the underlying goal or task the results will be "
                "used for. Used to better rank results against your intent. Length 1-2000."
            ),
        ),
        location: str | None = Field(
            default=None,
            description=(
                "Country code for geo-targeted results. If set without `language`, the result "
                "language auto-resolves to that country's most predominantly used language."
            ),
        ),
        language: str | None = Field(
            default=None,
            description=(
                "Language code for result language. If set without `location`, the location "
                "auto-resolves to the country where that language is most predominantly used."
            ),
        ),
        include_domains: str | None = Field(
            default=None, description="Comma-separated list of domains to restrict results to."
        ),
        exclude_domains: str | None = Field(
            default=None, description="Comma-separated list of domains to exclude from results."
        ),
        domain_type: str | None = Field(
            default=None,
            description=(
                "Type of search to perform: `web` for standard results, `news` for news "
                "articles, `research_paper` for academic papers. Defaults to `web`. "
                "Options: `web`, `news`, `research_paper`."
            ),
        ),
        after_date: str | None = Field(
            default=None, description="Return results after this date (YYYY-MM-DD)."
        ),
        before_date: str | None = Field(
            default=None, description="Return results before this date (YYYY-MM-DD)."
        ),
        recency_minutes: int | None = Field(
            default=None, description="Return results from the past N minutes (1 to 5,256,000)."
        ),
        pub_year_min: int | None = Field(
            default=None,
            description=(
                "Return research papers published on or after this year (0-9999, inclusive). "
                "Only supported for `domain_type=research_paper`."
            ),
        ),
        pub_year_max: int | None = Field(
            default=None,
            description=(
                "Return research papers published on or before this year (0-9999, inclusive). "
                "Only supported for `domain_type=research_paper`."
            ),
        ),
        page: int | None = Field(
            default=None,
            description="Page number for pagination, starting from 0 (capped at 10).",
        ),
        include_thumbnail: str | None = Field(
            default=None,
            description=(
                "When `true`, each result includes a `thumbnail_url` when available. Defaults "
                "to `false`. Options: `true`, `false`."
            ),
        ),
        fetch: str | None = Field(
            default=None,
            description="JSON-encoded fetch configuration object. Maximum string length 256.",
        ),
    ) -> WebSearchResult:
        tlog = ToolLogger(logger, "search_web")

        if not 1 <= len(query) <= 2000:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR", "query must be 1-2000 characters", 400)
        if purpose is not None and not 1 <= len(purpose) <= 2000:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR", "purpose must be 1-2000 characters", 400)
        if domain_type is not None and domain_type not in ("web", "news", "research_paper"):
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR",
                        "domain_type must be one of: web, news, research_paper", 400)
        if include_thumbnail is not None and include_thumbnail not in ("true", "false"):
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR",
                        "include_thumbnail must be one of: true, false", 400)
        if recency_minutes is not None and not 1 <= recency_minutes <= 5256000:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR",
                        "recency_minutes must be 1-5256000", 400)
        if pub_year_min is not None and not 0 <= pub_year_min <= 9999:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR", "pub_year_min must be 0-9999", 400)
        if pub_year_max is not None and not 0 <= pub_year_max <= 9999:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR", "pub_year_max must be 0-9999", 400)
        if (pub_year_min is not None or pub_year_max is not None) and domain_type != "research_paper":
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR",
                        "pub_year_min/pub_year_max only apply when domain_type=research_paper", 400)
        if page is not None and not 0 <= page <= 10:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR", "page must be 0-10", 400)
        if fetch is not None and len(fetch) > 256:
            return _err(WebSearchResult, tlog, "VALIDATION_ERROR",
                        "fetch must be at most 256 characters", 400)

        params: dict[str, Any] = {"query": query}
        if purpose is not None:
            params["purpose"] = purpose
        if location is not None:
            params["location"] = location
        if language is not None:
            params["language"] = language
        if include_domains is not None:
            params["include_domains"] = include_domains
        if exclude_domains is not None:
            params["exclude_domains"] = exclude_domains
        if domain_type is not None:
            params["domain_type"] = domain_type
        if after_date is not None:
            params["after_date"] = after_date
        if before_date is not None:
            params["before_date"] = before_date
        if recency_minutes is not None:
            params["recency_minutes"] = recency_minutes
        if pub_year_min is not None:
            params["pub_year_min"] = pub_year_min
        if pub_year_max is not None:
            params["pub_year_max"] = pub_year_max
        if page is not None:
            params["page"] = page
        if include_thumbnail is not None:
            params["include_thumbnail"] = include_thumbnail
        if fetch is not None:
            params["fetch"] = fetch

        try:
            data, status, retry_after = service.api_request(
                "GET", SEARCH_WEB_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = WebSearchData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return WebSearchResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(WebSearchResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(WebSearchResult, tlog, exc)

    @mcp.tool(
        name="list_search_usage",
        description=(
            "Lists search usage records for the authenticated user, returning paginated query "
            "details, status codes, and result counts. `limit` defaults to 100 and is capped at "
            "1000; `page` defaults to 1; filter by `status` of `completed` or `failed`."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def list_search_usage(
        start_after: str | None = Field(
            default=None,
            description="Only include usage records created at or after this timestamp (RFC 3339 date-time).",
        ),
        end_before: str | None = Field(
            default=None,
            description="Only include usage records created before this timestamp (RFC 3339 date-time).",
        ),
        status: str | None = Field(
            default=None,
            description="Filter by request status. Options: `completed`, `failed`.",
        ),
        limit: int = Field(
            default=100, description="Maximum number of records to return per page. Range 1-1000."
        ),
        page: int = Field(
            default=1, description="Page number for pagination, starting from 1."
        ),
    ) -> SearchUsageListResult:
        tlog = ToolLogger(logger, "list_search_usage")

        if status is not None and status not in ("completed", "failed"):
            return _err(SearchUsageListResult, tlog, "VALIDATION_ERROR",
                        "status must be one of: completed, failed", 400)
        if not 1 <= limit <= 1000:
            return _err(SearchUsageListResult, tlog, "VALIDATION_ERROR", "limit must be 1-1000", 400)
        if page < 1:
            return _err(SearchUsageListResult, tlog, "VALIDATION_ERROR", "page must be >= 1", 400)

        params: dict[str, Any] = {"limit": limit, "page": page}
        if start_after is not None:
            params["start_after"] = start_after
        if end_before is not None:
            params["end_before"] = end_before
        if status is not None:
            params["status"] = status

        try:
            data, status_code, retry_after = service.api_request(
                "GET", SEARCH_USAGE_URL, params=params,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status_code < 300:
                result_data = SearchUsageListData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return SearchUsageListResult(success=True, statusCode=status_code, data=result_data)
            return _upstream_err(SearchUsageListResult, tlog, status_code, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(SearchUsageListResult, tlog, exc)
