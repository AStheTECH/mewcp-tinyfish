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


class WalletTopupChallengeData(BaseModel):
    model_config = ConfigDict(extra="allow")

    challenge_id: str = Field(description="Challenge identifier. Matches the 402 body's `challengeId`.")
    realm: str = Field(description="Always `agent.tinyfish.ai`.")
    method: str = Field(description="Payment method this challenge accepts, e.g. `stripe`.")
    intent: str = Field(description="Always `charge`.")
    request_token: str = Field(description="Opaque token identifying this specific payment request.")
    expires_at: str = Field(description="Challenge expiry — 30 minutes from issuance.")
    payment_header_name: str = Field(
        description="Name of the header to retry with on `confirm_wallet_topup`, always `Payment-Authorization`."
    )
    type: str | None = Field(default=None, description="Problem-type URI from the 402 response body.")
    title: str | None = Field(default=None, description="Short human-readable summary from the 402 response body.")
    detail: str | None = Field(default=None, description="Longer explanation from the 402 response body.")
    hint: str | None = Field(default=None, description="Guidance for the caller from the 402 response body.")


class WalletTopupChallengeResult(ToolResult):
    data: WalletTopupChallengeData | None = None


class WalletTopupConfirmData(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = Field(
        description="`settled`: the wallet is credited. `pending` (HTTP 202): the card was charged and the credit lands shortly via webhook — do not pay again."
    )
    amount: str
    currency: str = Field(description='Settlement currency code; currently always "USD".')
    payment_reference: str = Field(description="Stripe PaymentIntent that settled this top-up.")
    ledger_entry_id: str | None = None
    available_balance: str | None = Field(
        default=None, description="Spendable balance after the credit landed; null when pending or unreadable."
    )
    hint: str | None = Field(default=None, description="On a 202 (`pending`) response: do not pay again.")


class WalletTopupConfirmResult(ToolResult):
    data: WalletTopupConfirmData | None = None
