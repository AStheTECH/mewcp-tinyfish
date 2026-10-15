"""MewCP Tinyfish tool registration."""

from fastmcp import FastMCP

from .automation_tools import register_automation_tools
from .runs_tools import register_runs_tools
from .search_tools import register_search_tools
from .fetch_tools import register_fetch_tools
from .wallet_tools import register_wallet_tools
from .browser_context_profiles_tools import register_browser_context_profiles_tools
from .vault_tools import register_vault_tools
from .research_tools import register_research_tools
from .browser_tools import register_browser_tools


def register_tools(mcp: FastMCP) -> None:
    register_automation_tools(mcp)
    register_runs_tools(mcp)
    register_search_tools(mcp)
    register_fetch_tools(mcp)
    register_wallet_tools(mcp)
    register_browser_context_profiles_tools(mcp)
    register_vault_tools(mcp)
    register_research_tools(mcp)
    register_browser_tools(mcp)
