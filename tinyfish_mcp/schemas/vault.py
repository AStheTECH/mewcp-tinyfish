"""Vault group schemas."""

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class VaultItemFieldMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    fieldId: str
    label: str
    type: str = Field(description="Indicator of the field's concealment type, e.g. `CONCEALED` — never the raw secret value.")


class VaultItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    itemId: str = Field(
        description="Credential URI, e.g. `cred:conn-123:Personal:item-abc123`. Pass as a `credential_item_ids` entry to automation tools."
    )
    connectionId: str
    label: str
    vaultName: str
    domains: list[str]
    fieldMetadata: list[VaultItemFieldMetadata]
    hasTotp: bool


class ConnectVaultProviderData(BaseModel):
    model_config = ConfigDict(extra="allow")

    connectionId: str
    connected: bool
    provider: str = Field(description="One of `1password`, `bitwarden`.")
    items: list[VaultItem] = Field(description="Display-safe metadata for every item synced on connection — never the raw secret values.")


class ConnectVaultProviderResult(ToolResult):
    data: ConnectVaultProviderData | None = None


class DisconnectVaultProviderData(BaseModel):
    model_config = ConfigDict(extra="allow")

    disconnected: bool
    connectionId: str


class DisconnectVaultProviderResult(ToolResult):
    data: DisconnectVaultProviderData | None = None


class VaultSyncSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    added: int
    updated: int
    removed: int


class SyncVaultItemsData(BaseModel):
    model_config = ConfigDict(extra="allow")

    items: list[VaultItem] = Field(description="Merged item state across every connected provider after the sync.")
    sync_summary: VaultSyncSummary


class SyncVaultItemsResult(ToolResult):
    data: SyncVaultItemsData | None = None
