"""Research group schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class ResearchStreamData(BaseModel):
    """Shared by run_research_sse and attach_research_progress — both consume the same
    research event catalog to the same terminal state and produce an identical shape."""

    model_config = ConfigDict(extra="allow")

    research_run_id: str | None = None
    result: str | None = Field(
        default=None, description="The synthesized cited report text, from the terminal `final_result` event."
    )
    citations: list[str] = Field(
        default_factory=list, description="Citation list from the terminal `final_result` event."
    )
    iterations_seen: list[int] = Field(
        default_factory=list,
        description="Iteration numbers seen via `plan_updated` events while the research was running.",
    )


class ResearchStreamResult(ToolResult):
    data: ResearchStreamData | None = None


class StartResearchAsyncData(BaseModel):
    model_config = ConfigDict(extra="allow")

    research_run_id: str = Field(description="The queued run's identifier.")
    error: dict[str, Any] | None = Field(default=None, description="Error details. Null when the run was queued successfully.")


class StartResearchAsyncResult(ToolResult):
    data: StartResearchAsyncData | None = None


class ResearchRunData(BaseModel):
    model_config = ConfigDict(extra="allow")

    research_run_id: str
    status: str = Field(description="One of `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `QUEUED`.")
    query: str
    quick_result: dict[str, Any] | None = Field(
        default=None, description="Quick answer with citations and stats, available before deep research completes."
    )
    quick_result_summary: str | None = None
    deep_result: dict[str, Any] | None = Field(
        default=None, description="Deep research report with citations and a freshness report, available after the run completes."
    )
    run_ids: list[str] = Field(description="IDs of the agent runs spawned by this research run.")
    created_at: str | None = None
    completed_at: str | None = Field(default=None, description="Null while the run is still in progress.")
    error: dict[str, Any] | None = Field(
        default=None,
        description="The run's own terminal outcome (e.g. why it failed or was cancelled) — not an error from the underlying content/search providers.",
    )
    research_plan: dict[str, Any] | None = Field(
        default=None, description="Subquestions and searches the run planned, including a `review` sub-object for plan review workflows."
    )
    evidence: list[dict[str, Any]] | None = Field(
        default=None, description="Sources gathered, with the claims they support and per-source confidence."
    )
    iterations: int | None = Field(default=None, description="Number of plan-search-synthesize iterations the run completed.")


class GetResearchRunResult(ToolResult):
    data: ResearchRunData | None = None


class ResearchRunPagination(BaseModel):
    model_config = ConfigDict(extra="allow")

    total: int
    next_cursor: str = Field(description="Pass as `cursor` on the next `list_research_runs` call to fetch the following page.")
    has_more: bool


class ListResearchRunsData(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: list[ResearchRunData]
    pagination: ResearchRunPagination


class ListResearchRunsResult(ToolResult):
    data: ListResearchRunsData | None = None


class CancelResearchRunData(BaseModel):
    model_config = ConfigDict(extra="allow")

    research_run_id: str
    status: str = Field(description="Status of the run after this request. One of `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`, `QUEUED`.")
    cancelled: bool = Field(
        description="Whether this request changed the run to `CANCELLED`. False on an idempotent repeat call against an already-terminal run."
    )


class CancelResearchRunResult(ToolResult):
    data: CancelResearchRunData | None = None
