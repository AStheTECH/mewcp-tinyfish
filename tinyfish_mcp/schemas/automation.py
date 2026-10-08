from pydantic import BaseModel, ConfigDict
from typing import Any

from ._base import ToolResult


class BrowserAutomationSseData(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    status: str | None = None
    result: dict[str, Any] | None = None
    streaming_url: str | None = None
    progress: list[str] = []
    timestamp: str | None = None


class BrowserAutomationSseResult(ToolResult):
    data: BrowserAutomationSseData | None = None


class AutomationAsyncData(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    error: dict[str, Any] | None = None


class AutomationAsyncResult(ToolResult):
    data: AutomationAsyncData | None = None
