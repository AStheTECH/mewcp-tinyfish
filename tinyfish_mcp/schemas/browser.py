"""Browser group schemas."""

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class BrowserSessionUsageItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    user_id: str
    sub_user_id: str
    mode: str = Field(description="Browser session mode, e.g. `tf-browser` for Tetra browser sessions.")
    start_time: str
    end_time: str | None = None
    duration_ms: int
    proxy_trg_rx_bytes: int
    proxy_trg_tx_bytes: int
    status: str = Field(description="One of `running`, `ended`.")
    created_at: str
    updated_at: str


class ListBrowserSessionUsageData(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[BrowserSessionUsageItem]
    total: int
    limit: int
    page: int
    total_pages: int
    has_more: bool


class ListBrowserSessionUsageResult(ToolResult):
    data: ListBrowserSessionUsageData | None = None
