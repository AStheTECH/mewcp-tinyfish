"""Browser Context Profiles group schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class CreateProfileData(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Browser Context Profile ID.")
    name: str = Field(description="Browser Context Profile display name.")
    created_at: str
    proxy_country_code: str | None = Field(
        default=None,
        description="Proxy country code, one of `US`, `GB`, `CA`, `AU`, `DE`, `FR`, `IT`, `ES`, `NL`, `JP`, `SG`, `BR`, `IN`, or null.",
    )
    is_default: bool
    fingerprint_seed: str
    domain_count: int
    updated_at: str


class CreateProfileResult(ToolResult):
    data: CreateProfileData | None = None


class DeleteProfileData(BaseModel):
    model_config = ConfigDict(extra="allow")

    deleted: bool


class DeleteProfileResult(ToolResult):
    data: DeleteProfileData | None = None


class UpdateProfileData(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(description="Browser Context Profile ID.")
    name: str = Field(description="Browser Context Profile display name.")
    created_at: str
    domains: list[dict[str, Any]] = Field(
        description="Per-domain saved state: each entry carries `domain`, `cookie_count`, `local_storage_origin_count`, `last_accessed_at`, `last_written_at`, `last_written_by_run_id`."
    )
    proxy_country_code: str | None = Field(
        default=None,
        description="Proxy country code, one of `US`, `GB`, `CA`, `AU`, `DE`, `FR`, `IT`, `ES`, `NL`, `JP`, `SG`, `BR`, `IN`, or null.",
    )
    is_default: bool
    fingerprint_seed: str
    domain_count: int
    updated_at: str


class UpdateProfileResult(ToolResult):
    data: UpdateProfileData | None = None


class CreateProfileSetupSessionData(BaseModel):
    model_config = ConfigDict(extra="allow")

    session_id: str = Field(description="Unique identifier for this browser setup session.")
    cdp_url: str = Field(
        description="WebSocket URL for browser connection. Pass to Playwright's `connect_over_cdp` or any WebSocket-based CDP client."
    )
    base_url: str = Field(description="HTTPS base URL for the session, used to access session endpoints such as `/pages`.")
    timeout_seconds: int
    expires_at: str


class CreateProfileSetupSessionResult(ToolResult):
    data: CreateProfileSetupSessionData | None = None


class CancelProfileSetupSessionData(BaseModel):
    model_config = ConfigDict(extra="allow")

    cancelled: bool


class CancelProfileSetupSessionResult(ToolResult):
    data: CancelProfileSetupSessionData | None = None


class SaveProfileSetupSessionData(BaseModel):
    model_config = ConfigDict(extra="allow")

    domains_updated: list[str]
    domains_failed: list[str]
    cookie_count: int
    domains_skipped: dict[str, Any] = Field(
        description="Breakdown of skipped writes: `cookies_skipped`, `local_storage_skipped`, `session_storage_skipped`, `blob_too_large`."
    )
    pages_captured: int | None = None
    target_reads_skipped: int | None = None
    cleanup_failed: bool
    cleanup_kind: str | None = None
    signed_in_sites: list[str] | None = Field(
        default=None,
        description="Sites this save recorded as signed in, from sign-in cookies set during setup. Omitted when sign-in tracking is not enabled for the account.",
    )
    sign_in: dict[str, Any] | None = Field(
        default=None,
        description="Whether TinyFish saw a sign-in to the site setup started on; `unverifiable` when it cannot tell. Omitted when sign-in tracking is not enabled for the account.",
    )
    user_confirmed_sites: dict[str, Any] | None = Field(
        default=None,
        description="Present when the request sent `signed_in_sites` and sign-in tracking is enabled: domains recorded as signed in, and sites rejected with a reason.",
    )


class SaveProfileSetupSessionResult(ToolResult):
    data: SaveProfileSetupSessionData | None = None


class UploadProfileStateData(BaseModel):
    model_config = ConfigDict(extra="allow")

    domains_updated: list[str]
    domains_failed: list[str]
    cookie_count: int
    domains_skipped: dict[str, Any] = Field(
        description="Breakdown of skipped writes: `cookies_skipped`, `local_storage_skipped`, `session_storage_skipped`, `blob_too_large`."
    )


class UploadProfileStateResult(ToolResult):
    data: UploadProfileStateData | None = None


class DeleteProfileDomainData(BaseModel):
    model_config = ConfigDict(extra="allow")

    deleted: bool


class DeleteProfileDomainResult(ToolResult):
    data: DeleteProfileDomainData | None = None
