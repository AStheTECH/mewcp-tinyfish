from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ._base import ToolResult


class WalletData(BaseModel):
    model_config = ConfigDict(extra="allow")

    available_balance: str = Field(
        description="Current spendable balance as a decimal string in `currency`. A negative value means the wallet is overdrawn."
    )
    currency: str = Field(description='Settlement currency code; currently always "USD".')
    as_of: str
    auto_reload: dict[str, Any] | None = Field(
        description=(
            "Auto-reload configuration, with its own state carried inside the object "
            '(e.g. `{"state": "unconfigured"}`). `null` means the auto-reload contract read '
            "failed, not that auto-reload is unconfigured."
        )
    )
    pending_top_up: dict[str, Any] | None = Field(
        description="In-flight top-up details, if any. `null` means no in-flight top-up, or the ledger read failed."
    )
    rates: dict[str, Any] | None = Field(
        description="Per-product contract rates. `null` means the rates read failed, or the wallet has no rate contract yet."
    )
    agent_top_up_url: str | None = Field(
        default=None,
        description=(
            "URL to POST a top-up request to and pay the 402 MPP challenge. Present only when "
            "an agent can add funds to the wallet itself."
        ),
    )


class WalletResult(ToolResult):
    data: WalletData | None = None
