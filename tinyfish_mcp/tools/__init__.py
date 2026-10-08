"""MewCP Tinyfish tool registration."""

from fastmcp import FastMCP

from .automation_tools import register_automation_tools
from .runs_tools import register_runs_tools
from .search_tools import register_search_tools
from .fetch_tools import register_fetch_tools
from .wallet_tools import register_wallet_tools


def register_tools(mcp: FastMCP) -> None:
    register_automation_tools(mcp)
    register_runs_tools(mcp)
    register_search_tools(mcp)
    register_fetch_tools(mcp)
    register_wallet_tools(mcp)
