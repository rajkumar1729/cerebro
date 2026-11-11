try:
    from .mcp_client import ObsidianMCPClient
except ModuleNotFoundError:
    ObsidianMCPClient = None

__all__ = ["ObsidianMCPClient"]
