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


class BrowserAutomationSyncData(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str | None = None
    status: str = Field(description="Final status of the run. One of `COMPLETED`, `FAILED`.")
    started_at: str | None = None
    finished_at: str | None = None
    num_of_steps: int | None = Field(
        default=None,
        description="Number of steps taken during the automation. Null while the run is still in progress.",
    )
    result: dict[str, Any] | None = Field(
        default=None, description="Structured JSON result extracted from the automation. Null if the run failed."
    )
    error: dict[str, Any] | None = Field(default=None, description="Error details. Null if the run succeeded.")
    profile_hint: dict[str, Any] | None = Field(
        default=None,
        description="Nudge suggesting a Browser Context Profile setup when a failed run is likely solvable that way. Omitted when not applicable.",
    )


class BrowserAutomationSyncResult(ToolResult):
    data: BrowserAutomationSyncData | None = None
