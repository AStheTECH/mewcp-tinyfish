from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class ExtractContentResultItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    final_url: str | None = None
    title: str | None = None
    description: str | None = None
    language: str | None = None
    format: str | None = None
    text: str | None = None
    author: str | None = None
    published_date: str | None = None
    links: list[str] | None = None
    image_links: list[str] | None = None
    page_metadata: dict[str, Any] | None = None
    latency_ms: float | None = None
    not_modified: bool | None = None
    etag: str | None = None
    last_modified: str | None = None
    unmatched_selectors: list[str] | None = Field(
        default=None,
        description="include_selectors entries that matched no elements on this page (partial miss, not an error).",
    )


class ExtractContentErrorItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    url: str
    error: str | None = Field(
        default=None,
        description=(
            "Per-URL failure code, e.g. target_http_error, page_not_found, target_unreachable, "
            "timeout, proxy_error, bot_blocked, empty_content, login_required, content_too_large, "
            "invalid_url, invalid_redirect_url, conditional_unsupported, selector_not_matched, "
            "selector_unsupported."
        ),
    )
    status: int | None = Field(
        default=None, description="Raw HTTP status code from the target, present for target_http_error/page_not_found."
    )
    unmatched_selectors: list[str] | None = None
    candidate_selectors: list[str] | None = Field(
        default=None,
        description="Suggested alternative selectors, present when error is selector_not_matched.",
    )


class ExtractContentData(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[ExtractContentResultItem] = Field(default_factory=list)
    errors: list[ExtractContentErrorItem] = Field(default_factory=list)
    request_id: str | None = Field(
        default=None, description="Request correlation ID, present only when errors is non-empty."
    )


class ExtractContentResult(ToolResult):
    data: ExtractContentData | None = None


class FetchUsageItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    url: str
    final_url: str | None = None
    title: str | None = None
    description: str | None = None
    language: str | None = None
    author: str | None = None
    published_date: str | None = None
    format: str | None = None
    status: str | None = Field(default=None, description="completed or failed.")
    request_origin: str | None = None
    request_id: str | None = None
    text_length: int | None = None
    links_count: int | None = None
    image_links_count: int | None = None
    latency_ms: float | None = None
    created_at: str | None = None
    error: str | None = None


class FetchUsageListData(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[FetchUsageItem] = Field(default_factory=list)
    total: int
    limit: int
    page: int
    total_pages: int
    has_more: bool


class FetchUsageListResult(ToolResult):
    data: FetchUsageListData | None = None
