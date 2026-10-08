"""Automation group: run_browser_automation_sse, start_automation_async"""

import json
import logging
from typing import Any, Literal

import pydantic
import requests
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas import ToolError
from ..schemas.automation import (
    AutomationAsyncData,
    AutomationAsyncResult,
    BrowserAutomationSseData,
    BrowserAutomationSseResult,
)
from ..service import _auth_headers
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.automation")

RUN_SSE_ENDPOINT = "https://agent.tinyfish.ai/v1/automation/run-sse"
RUN_ASYNC_ENDPOINT = "https://agent.tinyfish.ai/v1/automation/run-async"


def _validate_automation_params(result_class, tlog, goal, webhook_url, use_vault, profile_id, credential_item_ids):
    if not goal or not goal.strip():
        return _err(result_class, tlog, "VALIDATION_ERROR", "goal must not be empty", 400)
    if webhook_url is not None and not webhook_url.lower().startswith("https://"):
        return _err(result_class, tlog, "VALIDATION_ERROR", "webhook_url must use HTTPS", 400)
    if profile_id is not None and not profile_id.strip():
        return _err(result_class, tlog, "VALIDATION_ERROR", "profile_id must not be empty", 400)
    if credential_item_ids is not None:
        if len(credential_item_ids) < 1:
            return _err(result_class, tlog, "VALIDATION_ERROR",
                        "credential_item_ids must contain at least one item", 400)
        if not use_vault:
            return _err(result_class, tlog, "VALIDATION_ERROR",
                        "credential_item_ids requires use_vault to be true", 400)
    return None


def _build_automation_body(
    url, goal, browser_profile, api_integration, agent_config, capture_config,
    webhook_url, use_vault, use_profile, profile_id, credential_item_ids,
    proxy_config, output_schema,
) -> dict[str, Any]:
    body: dict[str, Any] = {"url": url, "goal": goal}
    optional = {
        "browser_profile": browser_profile,
        "api_integration": api_integration,
        "agent_config": agent_config,
        "capture_config": capture_config,
        "webhook_url": webhook_url,
        "use_vault": use_vault,
        "use_profile": use_profile,
        "profile_id": profile_id,
        "credential_item_ids": credential_item_ids,
        "proxy_config": proxy_config,
        "output_schema": output_schema,
    }
    for key, value in optional.items():
        if value is not None:
            body[key] = value
    return body


def register_automation_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="run_browser_automation_sse",
        description=(
            "Runs a browser automation task and streams its Server-Sent Events to completion "
            "synchronously, blocking until a terminal `COMPLETE` event arrives, then returns the "
            "run ID, final status, result payload, streaming URL (if the upstream sent one), "
            "accumulated progress messages, and completion timestamp. `webhook_url` must be "
            "HTTPS, `credential_item_ids` requires `use_vault: true`, `output_schema` is "
            "validated before the run is accepted, and `use_profile` returns a 400 if enabled but "
            "no default Browser Context Profile is set."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def run_browser_automation_sse(
        url: str = Field(description="Target website URL to automate."),
        goal: str = Field(description="Natural language description of what to accomplish on the website."),
        browser_profile: Literal["lite", "stealth"] | None = Field(
            default=None,
            description="Browser profile for execution. `lite` uses the standard browser; `stealth` uses an anti-detection browser.",
        ),
        api_integration: str | None = Field(
            default=None,
            description='Name of the integration making this API call (e.g. "dify", "zapier", "n8n"), used for analytics.',
        ),
        agent_config: dict[str, Any] | None = Field(
            default=None,
            description="Agent behavior configuration, e.g. `mode`, `cursor_style`, `max_steps`, `max_duration_seconds`. Omit to use the provider's default agent behavior.",
        ),
        capture_config: dict[str, Any] | None = Field(
            default=None,
            description="Configures which data to capture during the run, e.g. `elements`, `snapshots`, `screenshots`, `recording`, `html`. Omit to capture nothing extra beyond the default.",
        ),
        webhook_url: str | None = Field(
            default=None,
            description="HTTPS URL to receive webhook notifications for run lifecycle events. Must use HTTPS.",
        ),
        use_vault: bool | None = Field(
            default=None,
            description="Opt in to include enabled vault credentials for this run. Defaults to false when omitted.",
        ),
        use_profile: bool | None = Field(
            default=None,
            description="Opt in to the default Browser Context Profile when Browser Context Profiles are enabled; silently ignored for legacy callers when the profiles feature is disabled.",
        ),
        profile_id: str | None = Field(
            default=None,
            description="Browser Context Profile ID to use when `use_profile` is true.",
        ),
        credential_item_ids: list[str] | None = Field(
            default=None,
            description="Scopes vault credentials to specific credential URIs. Requires `use_vault` to be true; if omitted while `use_vault` is true, all enabled vault items are used.",
        ),
        proxy_config: dict[str, Any] | None = Field(
            default=None,
            description="Proxy configuration for the automation run, as a provider-defined object (no documented sub-keys). Omit to run without a proxy.",
        ),
        output_schema: dict[str, Any] | None = Field(
            default=None,
            description="Provider-supported structured-output JSON Schema subset for the run result (e.g. `type`, `properties`, `required`). Unsupported schema fields are rejected before the request is accepted. Omit to skip structured-output validation.",
        ),
    ) -> BrowserAutomationSseResult:
        tlog = ToolLogger(logger, "run_browser_automation_sse")

        err = _validate_automation_params(
            BrowserAutomationSseResult, tlog, goal, webhook_url, use_vault, profile_id, credential_item_ids,
        )
        if err:
            return err

        body = _build_automation_body(
            url, goal, browser_profile, api_integration, agent_config, capture_config,
            webhook_url, use_vault, use_profile, profile_id, credential_item_ids,
            proxy_config, output_schema,
        )

        try:
            resp = requests.post(
                RUN_SSE_ENDPOINT, headers=_auth_headers(), json=body,
                stream=True, timeout=(CONNECT_TIMEOUT, 600),  # long-running stream, not the READ_TIMEOUT default
            )
        except Exception as exc:
            return _handle_request_exc(BrowserAutomationSseResult, tlog, exc)

        if not 200 <= resp.status_code < 300:
            try:
                data = resp.json()
            except Exception:
                data = {"error": resp.text or "Empty response body"}
            return _upstream_err(BrowserAutomationSseResult, tlog, resp.status_code, data)

        run_id: str | None = None
        status_value: str | None = None
        result_value: dict[str, Any] | None = None
        streaming_url: str | None = None
        progress: list[str] = []
        timestamp: str | None = None
        completed = False

        try:
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[len("data: "):])
                except json.JSONDecodeError:
                    continue
                event_type = event.get("type")
                if event_type == "STARTED":
                    run_id = event.get("run_id")
                    timestamp = event.get("timestamp")
                elif event_type == "STREAMING_URL":
                    streaming_url = event.get("streaming_url")
                elif event_type == "PROGRESS":
                    purpose = event.get("purpose")
                    if purpose is not None:
                        progress.append(purpose)
                elif event_type == "HEARTBEAT":
                    continue
                elif event_type == "COMPLETE":
                    run_id = event.get("run_id", run_id)
                    status_value = event.get("status")
                    result_value = event.get("result")
                    timestamp = event.get("timestamp")
                    completed = True
                    break
        except Exception as exc:
            return _handle_request_exc(BrowserAutomationSseResult, tlog, exc)
        finally:
            resp.close()

        if not completed:
            tlog.failure("UPSTREAM_ERROR", "SSE stream ended before a COMPLETE event")
            return BrowserAutomationSseResult(
                success=False, statusCode=502, retriable=True,
                error=ToolError(code="UPSTREAM_ERROR",
                                message="Automation stream ended before completion"),
            )

        try:
            result = BrowserAutomationSseResult(
                success=True, statusCode=200,
                data=BrowserAutomationSseData(
                    run_id=run_id, status=status_value, result=result_value,
                    streaming_url=streaming_url, progress=progress, timestamp=timestamp,
                ),
            )
        except pydantic.ValidationError as e:  # must precede ValueError — it subclasses it
            tlog.failure("UPSTREAM_ERROR", "Response validation failed")  # str(e) embeds response field values — never log it
            return BrowserAutomationSseResult(
                success=False, statusCode=502, retriable=False,
                error=ToolError(code="UPSTREAM_ERROR",
                                message="Upstream response did not match the expected schema"),
            )

        tlog.success()
        return result

    @mcp.tool(
        name="start_automation_async",
        description=(
            "Creates and enqueues a browser automation run, returning its `run_id` immediately "
            "without waiting for the run to finish. Poll a separate status tool with the "
            "`run_id`, or supply an HTTPS `webhook_url` for push notifications instead; "
            "`credential_item_ids` requires `use_vault: true`, `output_schema` is validated "
            "before the run is accepted, and `use_profile` returns a 400 if enabled but no "
            "default Browser Context Profile is set."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def start_automation_async(
        url: str = Field(description="Target website URL to automate."),
        goal: str = Field(description="Natural language description of what to accomplish on the website."),
        browser_profile: Literal["lite", "stealth"] | None = Field(
            default=None,
            description="Browser profile for execution. `lite` uses the standard browser; `stealth` uses an anti-detection browser.",
        ),
        api_integration: str | None = Field(
            default=None,
            description='Name of the integration making this API call (e.g. "dify", "zapier", "n8n"), used for analytics.',
        ),
        agent_config: dict[str, Any] | None = Field(
            default=None,
            description="Agent behavior configuration, e.g. `mode`, `cursor_style`, `max_steps`, `max_duration_seconds`. Omit to use the provider's default agent behavior.",
        ),
        capture_config: dict[str, Any] | None = Field(
            default=None,
            description="Configures which data to capture during the run, e.g. `elements`, `snapshots`, `screenshots`, `recording`, `html`. Omit to capture nothing extra beyond the default.",
        ),
        webhook_url: str | None = Field(
            default=None,
            description="HTTPS URL to receive webhook notifications for run lifecycle events. Must use HTTPS.",
        ),
        use_vault: bool | None = Field(
            default=None,
            description="Opt in to include enabled vault credentials for this run. Defaults to false when omitted.",
        ),
        use_profile: bool | None = Field(
            default=None,
            description="Opt in to the default Browser Context Profile when Browser Context Profiles are enabled; silently ignored for legacy callers when the profiles feature is disabled.",
        ),
        profile_id: str | None = Field(
            default=None,
            description="Browser Context Profile ID to use when `use_profile` is true.",
        ),
        credential_item_ids: list[str] | None = Field(
            default=None,
            description="Scopes vault credentials to specific credential URIs. Requires `use_vault` to be true; if omitted while `use_vault` is true, all enabled vault items are used.",
        ),
        proxy_config: dict[str, Any] | None = Field(
            default=None,
            description="Proxy configuration for the automation run, as a provider-defined object (no documented sub-keys). Omit to run without a proxy.",
        ),
        output_schema: dict[str, Any] | None = Field(
            default=None,
            description="Provider-supported structured-output JSON Schema subset for the run result (e.g. `type`, `properties`, `required`). Unsupported schema fields are rejected before the request is accepted. Omit to skip structured-output validation.",
        ),
    ) -> AutomationAsyncResult:
        tlog = ToolLogger(logger, "start_automation_async")

        err = _validate_automation_params(
            AutomationAsyncResult, tlog, goal, webhook_url, use_vault, profile_id, credential_item_ids,
        )
        if err:
            return err

        body = _build_automation_body(
            url, goal, browser_profile, api_integration, agent_config, capture_config,
            webhook_url, use_vault, use_profile, profile_id, credential_item_ids,
            proxy_config, output_schema,
        )

        try:
            data, status, retry_after = service.api_request(
                "POST", RUN_ASYNC_ENDPOINT, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                tlog.success()
                return AutomationAsyncResult(success=True, statusCode=status, data=AutomationAsyncData(**data))
            return _upstream_err(AutomationAsyncResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(AutomationAsyncResult, tlog, exc)
