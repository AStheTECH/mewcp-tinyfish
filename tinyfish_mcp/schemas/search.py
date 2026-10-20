from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    position: int
    site_name: str
    snippet: str
    title: str
    url: str


class WebSearchData(BaseModel):
    model_config = ConfigDict(extra="allow")

    query: str
    results: list[SearchResultItem]
    total_results: int
    page: int
    request_id: str | None = Field(
        default=None,
        description="Request correlation ID. Present only when any result carries a fetch_error.",
    )


class WebSearchResult(ToolResult):
    data: WebSearchData | None = None


class SearchUsageItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    request_id: str | None = None
    query: str | None = None
    status_code: int | None = None
    result_count: int | None = None
    results: list[SearchResultItem] | None = None
    cached: bool | None = None
    response_size_bytes: int | None = None
    created_at: str | None = None


class SearchUsageListData(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[SearchUsageItem]
    total: int
    limit: int
    page: int
    total_pages: int
    has_more: bool


class SearchUsageListResult(ToolResult):
    data: SearchUsageListData | None = None
