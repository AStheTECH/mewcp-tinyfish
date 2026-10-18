"""Browser Context Profiles group: create_browser_context_profile, delete_browser_context_profile,
update_browser_context_profile, create_profile_setup_session, cancel_profile_setup_session,
save_profile_setup_session, upload_browser_context_profile_state."""

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.browser_context_profiles import (
    CancelProfileSetupSessionData,
    CancelProfileSetupSessionResult,
    CreateProfileData,
    CreateProfileResult,
    CreateProfileSetupSessionData,
    CreateProfileSetupSessionResult,
    DeleteProfileData,
    DeleteProfileDomainData,
    DeleteProfileDomainResult,
    DeleteProfileResult,
    SaveProfileSetupSessionData,
    SaveProfileSetupSessionResult,
    UpdateProfileData,
    UpdateProfileResult,
    UploadProfileStateData,
    UploadProfileStateResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.browser_context_profiles")

PROFILES_URL = "https://agent.tinyfish.ai/v1/profiles"
PROFILE_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}"
PROFILE_SETUP_SESSION_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}/setup-session"
PROFILE_SETUP_SESSION_CANCEL_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}/setup-session/cancel"
PROFILE_SAVE_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}/save"
PROFILE_UPLOAD_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}/upload"
PROFILE_DOMAIN_URL = "https://agent.tinyfish.ai/v1/profiles/{profileId}/domains/{domain}"

_PROXY_COUNTRY_CODES = ("US", "GB", "CA", "AU", "DE", "FR", "IT", "ES", "NL", "JP", "SG", "BR", "IN")


def register_browser_context_profiles_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="create_browser_context_profile",
        description=(
            "Creates a new Browser Context Profile — a reusable, isolated browser identity (cookies, "
            "local storage, fingerprint) that automation runs can attach to. Returns the created "
            "profile's ID and metadata."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def create_browser_context_profile(
        name: str = Field(description="Display name for the profile. Length 1-100 characters."),
        set_as_default: bool | None = Field(
            default=None, description="Make this the account's default profile. Omit to leave the current default unchanged."
        ),
        proxy_country_code: str | None = Field(
            default=None,
            description=f"Proxy country code: one of {', '.join(_PROXY_COUNTRY_CODES)}. Omit for no fixed proxy country.",
        ),
    ) -> CreateProfileResult:
        tlog = ToolLogger(logger, "create_browser_context_profile")

        if not (1 <= len(name) <= 100):
            return _err(CreateProfileResult, tlog, "VALIDATION_ERROR", "name must be 1-100 characters", 400)
        if proxy_country_code is not None and proxy_country_code not in _PROXY_COUNTRY_CODES:
            return _err(CreateProfileResult, tlog, "VALIDATION_ERROR",
                        f"proxy_country_code must be one of {', '.join(_PROXY_COUNTRY_CODES)}", 400)

        body: dict[str, Any] = {"name": name}
        if set_as_default is not None:
            body["set_as_default"] = set_as_default
        if proxy_country_code is not None:
            body["proxy_country_code"] = proxy_country_code

        try:
            data, status, retry_after = service.api_request(
                "POST", PROFILES_URL, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = CreateProfileData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return CreateProfileResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(CreateProfileResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(CreateProfileResult, tlog, exc)

    @mcp.tool(
        name="delete_browser_context_profile",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Permanently deletes the Browser Context Profile identified by `profileId`, including "
            "all its saved cookies, local storage, and session storage for every domain. "
            "This action is irreversible — the saved browser state cannot be recovered. "
            "NEVER call this tool autonomously or as part of an automated flow. "
            "You MUST stop, tell the user exactly what will be deleted and that it is permanent, "
            "and wait for their explicit written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def delete_browser_context_profile(
        profileId: str = Field(description="Browser Context Profile ID to delete, e.g. `prof_abc123def4567890`."),
    ) -> DeleteProfileResult:
        tlog = ToolLogger(logger, "delete_browser_context_profile")

        if not profileId.strip():
            return _err(DeleteProfileResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "DELETE", PROFILE_URL.format(profileId=profileId),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = DeleteProfileData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return DeleteProfileResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(DeleteProfileResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(DeleteProfileResult, tlog, exc)

    @mcp.tool(
        name="update_browser_context_profile",
        description=(
            "Updates a Browser Context Profile's name, default status, or proxy country, returning "
            "the full updated profile. Only the fields you provide are changed — others keep their "
            "current value. A 'before' snapshot isn't available: this bundle has no confirmed "
            "endpoint yet for fetching a single profile ahead of the update."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def update_browser_context_profile(
        profileId: str = Field(description="Browser Context Profile ID to update, e.g. `prof_abc123def4567890`."),
        name: str | None = Field(
            default=None, description="New display name, 1-100 characters. Omit to leave the current name unchanged."
        ),
        set_as_default: bool | None = Field(
            default=None, description="Make this the account's default profile. Omit to leave the current default unchanged."
        ),
        proxy_country_code: str | None = Field(
            default=None,
            description=f"Proxy country code: one of {', '.join(_PROXY_COUNTRY_CODES)}. Omit to leave the current proxy country unchanged.",
        ),
    ) -> UpdateProfileResult:
        tlog = ToolLogger(logger, "update_browser_context_profile")

        if not profileId.strip():
            return _err(UpdateProfileResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if name is not None and not (1 <= len(name) <= 100):
            return _err(UpdateProfileResult, tlog, "VALIDATION_ERROR", "name must be 1-100 characters", 400)
        if proxy_country_code is not None and proxy_country_code not in _PROXY_COUNTRY_CODES:
            return _err(UpdateProfileResult, tlog, "VALIDATION_ERROR",
                        f"proxy_country_code must be one of {', '.join(_PROXY_COUNTRY_CODES)}", 400)

        body: dict[str, Any] = {}
        if name is not None:
            body["name"] = name
        if set_as_default is not None:
            body["set_as_default"] = set_as_default
        if proxy_country_code is not None:
            body["proxy_country_code"] = proxy_country_code

        try:
            data, status, retry_after = service.api_request(
                "PATCH", PROFILE_URL.format(profileId=profileId), body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = UpdateProfileData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return UpdateProfileResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(UpdateProfileResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(UpdateProfileResult, tlog, exc)

    @mcp.tool(
        name="create_profile_setup_session",
        description=(
            "Starts a temporary setup browser for a Browser Context Profile, returning a `cdp_url` "
            "to drive it with Playwright, Puppeteer, or any CDP client. Log in during the session, "
            "then call `save_profile_setup_session` with the returned `session_id` to persist it — "
            "unsaved state is discarded if the session is cancelled or expires."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def create_profile_setup_session(
        profileId: str = Field(description="Browser Context Profile ID to set up, e.g. `prof_abc123def4567890`."),
        url: str | None = Field(
            default=None,
            description="Target URL the browser session navigates to on startup. Bare domains are automatically prefixed with `https://`. Omit to start at `about:blank`.",
        ),
        timeout_seconds: int | None = Field(
            default=None,
            description="Inactivity timeout in seconds, 5-86400. Omit, pass null, or exceed your plan maximum to use the plan maximum instead.",
        ),
    ) -> CreateProfileSetupSessionResult:
        tlog = ToolLogger(logger, "create_profile_setup_session")

        if not profileId.strip():
            return _err(CreateProfileSetupSessionResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if timeout_seconds is not None and not (5 <= timeout_seconds <= 86400):
            return _err(CreateProfileSetupSessionResult, tlog, "VALIDATION_ERROR",
                        "timeout_seconds must be between 5 and 86400", 400)

        body: dict[str, Any] = {}
        if url is not None:
            body["url"] = url
        if timeout_seconds is not None:
            body["timeout_seconds"] = timeout_seconds

        try:
            data, status, retry_after = service.api_request(
                "POST", PROFILE_SETUP_SESSION_URL.format(profileId=profileId), body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = CreateProfileSetupSessionData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return CreateProfileSetupSessionResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(CreateProfileSetupSessionResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(CreateProfileSetupSessionResult, tlog, exc)

    @mcp.tool(
        name="cancel_profile_setup_session",
        description=(
            "Cancels a running Browser Context Profile setup session and discards any unsaved "
            "setup state. Requires the `session_id` returned by `create_profile_setup_session`."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def cancel_profile_setup_session(
        profileId: str = Field(description="Browser Context Profile ID the setup session belongs to."),
        session_id: str = Field(description="Setup session ID returned by create_profile_setup_session."),
    ) -> CancelProfileSetupSessionResult:
        tlog = ToolLogger(logger, "cancel_profile_setup_session")

        if not profileId.strip():
            return _err(CancelProfileSetupSessionResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if not session_id.strip():
            return _err(CancelProfileSetupSessionResult, tlog, "VALIDATION_ERROR", "session_id must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "POST", PROFILE_SETUP_SESSION_CANCEL_URL.format(profileId=profileId),
                body={"session_id": session_id},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = CancelProfileSetupSessionData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return CancelProfileSetupSessionResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(CancelProfileSetupSessionResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(CancelProfileSetupSessionResult, tlog, exc)

    @mcp.tool(
        name="save_profile_setup_session",
        description=(
            "Captures cookies, local storage, and session storage from a running setup session into "
            "the Browser Context Profile. Requires the `session_id` returned by "
            "`create_profile_setup_session`; writes/merges domain state into the existing profile "
            "rather than creating a new one."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def save_profile_setup_session(
        profileId: str = Field(description="Browser Context Profile ID the setup session belongs to."),
        session_id: str = Field(description="Setup session ID returned by create_profile_setup_session."),
        signed_in_sites: list[str] | None = Field(
            default=None,
            description=(
                "Sites the user says they signed into during this setup, as hosts or URLs (max 20 "
                "entries, 253 characters each). Each is recorded as signed in only if this save wrote "
                "cookies for it. Ignored when sign-in tracking is not enabled for the account. Omit if "
                "no sign-ins occurred during setup."
            ),
        ),
    ) -> SaveProfileSetupSessionResult:
        tlog = ToolLogger(logger, "save_profile_setup_session")

        if not profileId.strip():
            return _err(SaveProfileSetupSessionResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if not session_id.strip():
            return _err(SaveProfileSetupSessionResult, tlog, "VALIDATION_ERROR", "session_id must not be empty", 400)
        if signed_in_sites is not None:
            if len(signed_in_sites) > 20:
                return _err(SaveProfileSetupSessionResult, tlog, "VALIDATION_ERROR",
                            "signed_in_sites must contain at most 20 entries", 400)
            if any(len(site) > 253 for site in signed_in_sites):
                return _err(SaveProfileSetupSessionResult, tlog, "VALIDATION_ERROR",
                            "each signed_in_sites entry must be at most 253 characters", 400)

        body: dict[str, Any] = {"session_id": session_id}
        if signed_in_sites is not None:
            body["signed_in_sites"] = signed_in_sites

        try:
            data, status, retry_after = service.api_request(
                "POST", PROFILE_SAVE_URL.format(profileId=profileId), body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = SaveProfileSetupSessionData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return SaveProfileSetupSessionResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(SaveProfileSetupSessionResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(SaveProfileSetupSessionResult, tlog, exc)

    @mcp.tool(
        name="upload_browser_context_profile_state",
        description=(
            "Uploads cookies, local storage, and session storage directly into a Browser Context "
            "Profile, without running a live setup browser session. Writes/merges the given domain "
            "state into the existing profile."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def upload_browser_context_profile_state(
        profileId: str = Field(description="Browser Context Profile ID to upload state into."),
        cookies: list[dict[str, Any]] = Field(
            description=(
                "Cookies to upload (max 3000 entries). Each entry requires `name`, `value`, `domain`, "
                "`path`; optional: `httpOnly`, `secure`, `expires`, `sourceScheme`, `sourcePort`, "
                "`partitionKey`."
            )
        ),
        localStorage: list[dict[str, Any]] | None = Field(
            default=None,
            description=(
                "Local storage entries to upload (max 100 entries). Each entry requires `origin` and "
                "`items` (a list of `{name, value}` objects). Omit if there is no local storage to upload."
            ),
        ),
        sessionStorage: list[dict[str, Any]] | None = Field(
            default=None,
            description=(
                "Session storage entries to upload (max 100 entries). Each entry requires `origin` and "
                "`items` (a list of `{name, value}` objects). Omit if there is no session storage to upload."
            ),
        ),
    ) -> UploadProfileStateResult:
        tlog = ToolLogger(logger, "upload_browser_context_profile_state")

        if not profileId.strip():
            return _err(UploadProfileStateResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if len(cookies) > 3000:
            return _err(UploadProfileStateResult, tlog, "VALIDATION_ERROR", "cookies must contain at most 3000 entries", 400)
        if localStorage is not None and len(localStorage) > 100:
            return _err(UploadProfileStateResult, tlog, "VALIDATION_ERROR",
                        "localStorage must contain at most 100 entries", 400)
        if sessionStorage is not None and len(sessionStorage) > 100:
            return _err(UploadProfileStateResult, tlog, "VALIDATION_ERROR",
                        "sessionStorage must contain at most 100 entries", 400)

        body: dict[str, Any] = {"cookies": cookies}
        if localStorage is not None:
            body["localStorage"] = localStorage
        if sessionStorage is not None:
            body["sessionStorage"] = sessionStorage

        try:
            data, status, retry_after = service.api_request(
                "POST", PROFILE_UPLOAD_URL.format(profileId=profileId), body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = UploadProfileStateData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return UploadProfileStateResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(UploadProfileStateResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(UploadProfileStateResult, tlog, exc)

    @mcp.tool(
        name="delete_profile_domain",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Permanently removes one domain's saved state (e.g. cookies for that site) from a "
            "Browser Context Profile, leaving the rest of the profile untouched. This action is "
            "irreversible — the saved state for that domain cannot be recovered. NEVER call this "
            "tool autonomously or as part of an automated flow. You MUST stop, tell the user "
            "exactly which domain will be removed from which profile and that it is permanent, "
            "and wait for their explicit written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def delete_profile_domain(
        profileId: str = Field(description="Browser Context Profile ID, e.g. `prof_abc123def4567890`."),
        domain: str = Field(description="Domain to remove from the profile, e.g. `example.com`."),
    ) -> DeleteProfileDomainResult:
        tlog = ToolLogger(logger, "delete_profile_domain")

        if not profileId.strip():
            return _err(DeleteProfileDomainResult, tlog, "VALIDATION_ERROR", "profileId must not be empty", 400)
        if not domain.strip():
            return _err(DeleteProfileDomainResult, tlog, "VALIDATION_ERROR", "domain must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "DELETE", PROFILE_DOMAIN_URL.format(profileId=profileId, domain=domain),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = DeleteProfileDomainData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return DeleteProfileDomainResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(DeleteProfileDomainResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(DeleteProfileDomainResult, tlog, exc)
