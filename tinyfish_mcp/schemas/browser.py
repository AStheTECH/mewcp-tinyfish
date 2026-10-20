"""Browser group schemas."""

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class BrowserSessionUsageItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str
    user_id: str | None = None
    sub_user_id: str | None = None
    mode: str | None = Field(default=None, description="Browser session mode, e.g. `tf-browser` for Tetra browser sessions.")
    start_time: str | None = None
    end_time: str | None = None
    duration_ms: int | None = Field(default=None, description="Null while the session is still `running`.")
    proxy_trg_rx_bytes: int | None = Field(default=None, description="Null while the session is still `running`.")
    proxy_trg_tx_bytes: int | None = Field(default=None, description="Null while the session is still `running`.")
    status: str | None = Field(default=None, description="One of `running`, `ended`.")
    created_at: str | None = None
    updated_at: str | None = None


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


class CreateBrowserSessionData(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(description="Unique identifier for this browser session.")
    cdp_url: str = Field(
        description="WebSocket URL for browser connection — pass to Playwright's `connect_over_cdp` or any CDP client."
    )
    base_url: str = Field(
        description="HTTPS base URL for the session — used for session endpoints such as `/pages`."
    )


class CreateBrowserSessionResult(ToolResult):
    data: CreateBrowserSessionData | None = None


class TerminateBrowserSessionResult(ToolResult):
    pass
