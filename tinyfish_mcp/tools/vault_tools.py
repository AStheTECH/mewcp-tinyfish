"""Vault group: connect_vault_provider, disconnect_vault_provider, sync_vault_items."""

import logging
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.vault import (
    ConnectVaultProviderData,
    ConnectVaultProviderResult,
    DisconnectVaultProviderData,
    DisconnectVaultProviderResult,
    SyncVaultItemsData,
    SyncVaultItemsResult,
)
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.vault")

VAULT_CONNECTIONS_URL = "https://agent.tinyfish.ai/v1/vault/connections"
VAULT_CONNECTION_URL = "https://agent.tinyfish.ai/v1/vault/connections/{connectionId}"
VAULT_SYNC_URL = "https://agent.tinyfish.ai/v1/vault/items/sync"

_PROVIDERS = ("1password", "bitwarden")


def register_vault_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="connect_vault_provider",
        description=(
            "Connects a supported password manager (1Password or Bitwarden) and immediately syncs "
            "its display-safe credential metadata. Returned items carry only metadata (labels, "
            "domains, field types) — actual secret values are never included."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def connect_vault_provider(
        provider: str = Field(description="Vault provider to connect. One of `1password`, `bitwarden`."),
        token: str | None = Field(
            default=None,
            description="1Password service account token. Required when `provider` is `1password`; omit otherwise.",
        ),
        clientId: str | None = Field(
            default=None,
            description="Bitwarden client ID. Required when `provider` is `bitwarden`; omit otherwise.",
        ),
        clientSecret: str | None = Field(
            default=None,
            description="Bitwarden client secret. Required when `provider` is `bitwarden`; omit otherwise.",
        ),
        masterPassword: str | None = Field(
            default=None,
            description="Bitwarden master password. Required when `provider` is `bitwarden`; omit otherwise.",
        ),
        serverUrl: str | None = Field(
            default=None,
            description="Optional self-hosted Bitwarden server URL. Omit to use Bitwarden's default cloud server.",
        ),
    ) -> ConnectVaultProviderResult:
        tlog = ToolLogger(logger, "connect_vault_provider")

        if provider not in _PROVIDERS:
            return _err(ConnectVaultProviderResult, tlog, "VALIDATION_ERROR",
                        f"provider must be one of {', '.join(_PROVIDERS)}", 400)
        if provider == "1password" and not token:
            return _err(ConnectVaultProviderResult, tlog, "VALIDATION_ERROR",
                        "token is required when provider is '1password'", 400)
        if provider == "bitwarden" and not (clientId and clientSecret and masterPassword):
            return _err(ConnectVaultProviderResult, tlog, "VALIDATION_ERROR",
                        "clientId, clientSecret, and masterPassword are all required when provider is 'bitwarden'", 400)

        body: dict[str, Any] = {"provider": provider}
        if token is not None:
            body["token"] = token
        if clientId is not None:
            body["clientId"] = clientId
        if clientSecret is not None:
            body["clientSecret"] = clientSecret
        if masterPassword is not None:
            body["masterPassword"] = masterPassword
        if serverUrl is not None:
            body["serverUrl"] = serverUrl

        try:
            data, status, retry_after = service.api_request(
                "POST", VAULT_CONNECTIONS_URL, body=body,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = ConnectVaultProviderData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return ConnectVaultProviderResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(ConnectVaultProviderResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(ConnectVaultProviderResult, tlog, exc)

    @mcp.tool(
        name="disconnect_vault_provider",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Permanently disconnects the vault provider connection identified by `connectionId` and "
            "removes all of its stored enabled items. This action is irreversible — the connection "
            "and its synced item metadata cannot be recovered; reconnecting requires the provider's "
            "credentials again. NEVER call this tool autonomously or as part of an automated flow. "
            "You MUST stop, tell the user exactly what will be disconnected and that it is permanent, "
            "and wait for their explicit written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def disconnect_vault_provider(
        connectionId: str = Field(description="Vault connection ID to disconnect, e.g. `conn_123`."),
    ) -> DisconnectVaultProviderResult:
        tlog = ToolLogger(logger, "disconnect_vault_provider")

        if not connectionId.strip():
            return _err(DisconnectVaultProviderResult, tlog, "VALIDATION_ERROR", "connectionId must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "DELETE", VAULT_CONNECTION_URL.format(connectionId=connectionId),
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = DisconnectVaultProviderData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return DisconnectVaultProviderResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(DisconnectVaultProviderResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(DisconnectVaultProviderResult, tlog, exc)

    @mcp.tool(
        name="sync_vault_items",
        description=(
            "DESTRUCTIVE — REQUIRES EXPLICIT USER CONFIRMATION BEFORE CALLING. "
            "Re-syncs items across every connected vault provider in one bulk call, returning the "
            "full merged item list plus added/updated/removed counts. This overwrites the current "
            "item state for every connected provider — the original per-item values before this "
            "sync are not returned and cannot be recovered from this call. There is no way to "
            "target a single provider or item. NEVER call this tool autonomously or as part of an "
            "automated flow. You MUST stop, tell the user that this will re-sync all connected "
            "vault providers, and wait for their explicit written confirmation before proceeding."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True),
    )
    def sync_vault_items() -> SyncVaultItemsResult:
        tlog = ToolLogger(logger, "sync_vault_items")

        try:
            data, status, retry_after = service.api_request(
                "POST", VAULT_SYNC_URL,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = SyncVaultItemsData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return SyncVaultItemsResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(SyncVaultItemsResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(SyncVaultItemsResult, tlog, exc)
