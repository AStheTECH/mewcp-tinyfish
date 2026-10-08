"""Wallet group: get_wallet"""

import logging

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .. import service
from ..config import CONNECT_TIMEOUT, READ_TIMEOUT
from ..logging_utils import ToolLogger
from ..schemas.wallet import WalletData, WalletResult
from ._helpers import _handle_request_exc, _upstream_err

logger = logging.getLogger("tinyfish-mcp.tools.wallet")


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
                tlog.success()
                return WalletResult(success=True, statusCode=status, data=WalletData(**data))
            return _upstream_err(WalletResult, tlog, status, data, retry_after)
        except Exception as exc:
            return _handle_request_exc(WalletResult, tlog, exc)
