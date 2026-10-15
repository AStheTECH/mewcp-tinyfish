"""Wallet group: get_wallet, request_wallet_topup, confirm_wallet_topup"""

import logging
import re

import pydantic
import requests
from fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas import ToolError
from ..schemas.wallet import (
    WalletData,
    WalletResult,
    WalletTopupChallengeData,
    WalletTopupChallengeResult,
    WalletTopupConfirmData,
    WalletTopupConfirmResult,
)
from ..service import _auth_headers
from ._helpers import _err, _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.wallet")

WALLET_TOPUP_URL = "https://agent.tinyfish.ai/v1/wallet/top-up"
_AMOUNT_PATTERN = re.compile(r"^(?=.*[1-9])(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$")


def _parse_www_authenticate(header: str) -> dict[str, str]:
    return dict(re.findall(r'(\w+)="([^"]*)"', header))


def register_wallet_tools(mcp: FastMCP) -> None:

    @mcp.tool(
        name="get_wallet",
        description=(
            "Retrieves the caller's wallet: current balance, auto-reload configuration, "
            "per-product contract rates, and any in-flight top-up. `auto_reload: null` means "
            "the auto-reload contract read failed (not that auto-reload is unconfigured — that "
            "state lives inside the object itself); `pending_top_up: null` and `rates: null` "
            "are each ambiguous between a normal empty state and a backend read failure. "
            "`agent_top_up_url` is present only when the agent can add funds itself, by posting "
            "there to pay the 402 MPP challenge."
        ),
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True),
    )
    def get_wallet() -> WalletResult:
        tlog = ToolLogger(logger, "get_wallet")

        try:
            data, status, retry_after = service.api_request(
                "GET", "https://agent.tinyfish.ai/v1/wallet",
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if 200 <= status < 300:
                result_data = WalletData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return WalletResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(WalletResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(WalletResult, tlog, exc)

    @mcp.tool(
        name="request_wallet_topup",
        description=(
            "Starts a wallet top-up for a USD `amount` and returns a payment challenge — this call "
            "alone never moves money, and is as safe as a read despite its CREATE tier. Hand the "
            "challenge to the caller's own external MPP-speaking wallet (e.g. Stripe's Link agent "
            "wallet) to obtain a `Payment-Authorization` credential — this tool cannot produce one "
            "itself — then call `confirm_wallet_topup` with the same amount and that credential to "
            "actually settle the charge. The challenge expires 30 minutes after this call."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def request_wallet_topup(
        amount: str = Field(
            description='Amount to add in USD, from "10.00" to "500.00", at most 2 decimal places, e.g. "25.00". Must be passed again, identical, to confirm_wallet_topup.'
        ),
    ) -> WalletTopupChallengeResult:
        tlog = ToolLogger(logger, "request_wallet_topup")

        if not _AMOUNT_PATTERN.fullmatch(amount):
            return _err(WalletTopupChallengeResult, tlog, "VALIDATION_ERROR",
                        "amount must be a positive decimal string with at most 2 decimal places", 400)
        amount_value = float(amount)
        if not (10.00 <= amount_value <= 500.00):
            return _err(WalletTopupChallengeResult, tlog, "VALIDATION_ERROR",
                        "amount must be between 10.00 and 500.00", 400)

        try:
            resp = requests.post(
                WALLET_TOPUP_URL, headers=_auth_headers(), json={"amount": amount},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
        except Exception as exc:
            return _handle_request_exc(WalletTopupChallengeResult, tlog, exc)

        www_auth = resp.headers.get("WWW-Authenticate")
        if resp.status_code == 402 and www_auth:
            challenge = _parse_www_authenticate(www_auth)
            try:
                body = resp.json()
            except Exception:
                body = {}
            try:
                result_data = WalletTopupChallengeData(
                    challenge_id=challenge.get("id", ""),
                    realm=challenge.get("realm", ""),
                    method=challenge.get("method", ""),
                    intent=challenge.get("intent", ""),
                    request_token=challenge.get("request", ""),
                    expires_at=challenge.get("expires", ""),
                    payment_header_name=challenge.get("header", "Payment-Authorization"),
                    type=body.get("type"),
                    title=body.get("title"),
                    detail=body.get("detail"),
                    hint=body.get("hint"),
                )
            except pydantic.ValidationError:
                tlog.failure("UPSTREAM_ERROR", "Response validation failed")  # str(e) embeds response field values — never log it
                return WalletTopupChallengeResult(
                    success=False, statusCode=502, retriable=False,
                    error=ToolError(code="UPSTREAM_ERROR", message="Upstream response did not match the expected schema"),
                )
            tlog.success()
            return WalletTopupChallengeResult(success=True, statusCode=402, data=result_data)

        # Any other outcome (400 invalid amount, 404 feature not available, or a 402 without a
        # parseable challenge) is a real error, not the expected challenge response.
        try:
            err_data = resp.json()
        except Exception:
            err_data = {"error": resp.text or "Empty response body"}
        return _upstream_err(WalletTopupChallengeResult, tlog, resp.status_code, err_data)

    @mcp.tool(
        name="confirm_wallet_topup",
        description=(
            "Settles a wallet top-up previously started with `request_wallet_topup`, using a "
            "`payment_authorization` credential obtained from the caller's own external "
            "MPP-speaking wallet for that specific challenge. Requires calling "
            "`request_wallet_topup` first — this tool cannot be used cold and cannot generate a "
            "credential on its own. A `402` response here (without a fresh challenge) means the "
            "payment was sent but not accepted — never retry this call on your own in that case; "
            "a replayed credential is never charged twice, but stop and check the wallet balance "
            "before starting a new top-up."
        ),
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True),
    )
    def confirm_wallet_topup(
        amount: str = Field(
            description='Must be identical to the amount passed to request_wallet_topup for the challenge being paid, e.g. "25.00".'
        ),
        payment_authorization: str = Field(
            description='The payment credential for the challenge from request_wallet_topup, format "Payment <base64url>". Obtained from the caller\'s own MPP-speaking wallet (e.g. Stripe\'s Link agent wallet) — this tool cannot construct this value.'
        ),
    ) -> WalletTopupConfirmResult:
        tlog = ToolLogger(logger, "confirm_wallet_topup")

        if not _AMOUNT_PATTERN.fullmatch(amount):
            return _err(WalletTopupConfirmResult, tlog, "VALIDATION_ERROR",
                        "amount must be a positive decimal string with at most 2 decimal places", 400)
        if not payment_authorization or not payment_authorization.strip():
            return _err(WalletTopupConfirmResult, tlog, "VALIDATION_ERROR",
                        "payment_authorization must not be empty", 400)

        try:
            data, status, retry_after = service.api_request(
                "POST", WALLET_TOPUP_URL, body={"amount": amount},
                extra_headers={"Payment-Authorization": payment_authorization},
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            )
            if status in (200, 202):
                result_data = WalletTopupConfirmData(**data)  # construct before logging success — can still raise ValidationError
                tlog.success()
                return WalletTopupConfirmResult(success=True, statusCode=status, data=result_data)
            return _upstream_err(WalletTopupConfirmResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(WalletTopupConfirmResult, tlog, exc)
