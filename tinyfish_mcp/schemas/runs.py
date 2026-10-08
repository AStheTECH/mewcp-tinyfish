"""Runs group schemas: list_runs, get_run, cancel_run."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class RunStep(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    timestamp: str | None = None
    status: str | None = None
    action: str | None = None
    screenshot: str | None = None
    html: str | None = None
    duration: str | None = None


class RunData(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    status: str = Field(
        description="One of `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`."
    )
    goal: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    num_of_steps: int | None = None
    result: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="Structured-output schema subset originally requested for this run, or null when none was provided.",
    )
    profile_attached: bool
    profile_id: str | None = None
    error: dict[str, Any] | None = Field(
        default=None,
        description="Error details. Null if the run succeeded or is still running.",
    )
    streaming_url: str | None = Field(
        default=None,
        description="URL to watch the live browser session. Only available while the run is running.",
    )
    browser_config: dict[str, Any] | None = None
    video_url: str | None = Field(
        default=None,
        description="Presigned URL to the run's video recording, or null if none is available. Expires 15 minutes after being issued.",
    )
    steps: list[RunStep]
    profile_hint: dict[str, Any] = Field(
        description="Nudge suggesting a Browser Context Profile setup when a failed run is likely solvable that way."
    )


class RunResult(ToolResult):
    data: RunData | None = None


class RunPagination(BaseModel):
    model_config = ConfigDict(extra="allow")

    total: int
    next_cursor: str = Field(description="Pass as `cursor` on the next `list_runs` call to fetch the following page.")
    has_more: bool


class RunListData(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[RunData]
    pagination: RunPagination


class RunListResult(ToolResult):
    data: RunListData | None = None


class RunCancelData(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    status: str = Field(
        description="The run's actual status after the call. One of `CANCELLED`, `COMPLETED`, `FAILED` — on an idempotent repeat call this reflects the run's real terminal status rather than an error."
    )
    cancelled_at: str | None = None
    message: str | None = None


class RunCancelResult(ToolResult):
    data: RunCancelData | None = None
