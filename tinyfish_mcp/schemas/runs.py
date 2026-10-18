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


class RunBatchItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    status: str = Field(description="One of `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`.")
    goal: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = Field(
        default=None,
        description="Error details. Null if the run succeeded or is still running.",
    )


class RunBatchGetData(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[RunBatchItem]
    not_found: list[str] | None = Field(
        default=None,
        description="Run IDs that were not found or not owned. Null if all were found.",
    )


class RunBatchGetResult(ToolResult):
    data: RunBatchGetData | None = None


class RunCancelBatchItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    status: str = Field(description="The run's actual status after the call. E.g. `CANCELLED`, or a terminal status like `COMPLETED`/`FAILED` when the run could not be cancelled.")
    cancelled_at: str | None = None
    message: str | None = Field(
        default=None,
        description="Explanatory note, e.g. \"Run already finished\". Null when there is nothing to explain.",
    )


class RunBatchCancelData(BaseModel):
    model_config = ConfigDict(extra="allow")

    results: list[RunCancelBatchItem]
    not_found: list[str] | None = Field(
        default=None,
        description="Run IDs that were not found or not owned. Null if all were found.",
    )


class RunBatchCancelResult(ToolResult):
    data: RunBatchCancelData | None = None


class StepScreenshotData(BaseModel):
    model_config = ConfigDict(extra="allow")

    content_type: str = Field(description="MIME type of the returned image. Always `image/jpeg`.")
    image_base64: str = Field(description="Base64-encoded JPEG screenshot bytes captured at this step.")


class StepScreenshotResult(ToolResult):
    data: StepScreenshotData | None = None


class StepHtmlSnapshotData(BaseModel):
    model_config = ConfigDict(extra="allow")

    content_type: str = Field(description="MIME type of the returned snapshot. Always `text/html`.")
    html: str = Field(description="Raw HTML of the full-page snapshot captured at this step.")


class StepHtmlSnapshotResult(ToolResult):
    data: StepHtmlSnapshotData | None = None
