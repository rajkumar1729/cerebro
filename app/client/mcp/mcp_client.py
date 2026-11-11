"""
ObsidianMCPClient — Wrapper around the MCP Python SDK.

Manages the connection lifecycle with the Obsidian MCP server
and provides typed methods for note operations.
"""

import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ...config import CerebroConfig

logger = logging.getLogger(__name__)


class ObsidianMCPClient:
    """
    MCP client for interacting with an Obsidian vault through an MCP server.
    """

    def __init__(self, config: CerebroConfig):
        self.config = config
        self._session: Optional[ClientSession] = None
        self._exit_stack: Optional[AsyncExitStack] = None
        logger.debug("ObsidianMCPClient initialized with vault: %s", config.vault_path)

    # ─── Lifecycle ──────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect to the Obsidian MCP server."""
        if self._session is not None:
            logger.debug("Already connected to MCP server")
            return

        logger.info("Connecting to Obsidian MCP server | cmd=%s", self.config.mcp_command)

        server_params = StdioServerParameters(
            command=self.config.mcp_command,
            args=self.config.mcp_args,
            env=None,
        )

        self._exit_stack = AsyncExitStack()

        try:
            transport = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(transport[0], transport[1])
            )
            await self._session.initialize()
            logger.info("✅ Connected to Obsidian MCP server")
            print("✅ Connected to Obsidian MCP server")
        except Exception as err:
            await self._cleanup()
            logger.error(
                "Failed to connect to MCP server | cmd=%s | error=%s",
                self.config.mcp_command,
                err,
                exc_info=True,
            )
            raise ConnectionError(
                f"Failed to connect to Obsidian MCP server.\n"
                f"Command: {self.config.mcp_command} {' '.join(self.config.mcp_args)}\n"
                f"Error: {err}"
            ) from err

    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        logger.info("Disconnecting from Obsidian MCP server")
        await self._cleanup()
        logger.debug("MCP server disconnected")
        print("🔌 Disconnected from Obsidian MCP server")

    async def _cleanup(self) -> None:
        if self._exit_stack:
            await self._exit_stack.aclose()
        self._session = None
        self._exit_stack = None

    # ─── Discovery ──────────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """List all tools exposed by the Obsidian MCP server."""
        logger.debug("Listing available MCP tools")
        self._ensure_connected()
        result = await self._session.list_tools()  # type: ignore
        tools = [
            {"name": t.name, "description": getattr(t, "description", "")}
            for t in result.tools
        ]
        logger.info("Listed %d MCP tools", len(tools))
        return tools

    async def list_resources(self) -> list[Any]:
        """List all resources exposed by the Obsidian MCP server."""
        logger.debug("Listing available MCP resources")
        self._ensure_connected()
        try:
            result = await self._session.list_resources()  # type: ignore
            logger.info("Listed %d MCP resources", len(result.resources))
            return result.resources
        except Exception as e:
            logger.warning("Failed to list resources: %s", e, exc_info=True)
            return []

    # ─── Note Operations ────────────────────────────────────────

    async def list_notes(self, path: Optional[str] = None) -> Any:
        """List notes/files in the vault at a given path."""
        target_path = path or self.config.notes_dir
        logger.debug("Listing notes at path: %s", target_path)
        return await self.call_tool("list_files_in_vault", {
            "path": target_path,
        })

    async def read_note(self, file_path: str) -> str:
        """Read the content of a specific note."""
        result = await self.call_tool("read_note", {"path": file_path})
        return self._extract_text_content(result)

    async def create_note(self, file_path: str, content: str) -> Any:
        """Create a new note in the vault."""
        return await self.call_tool("create_note", {
            "path": file_path,
            "content": content,
        })

    async def update_note(self, file_path: str, content: str) -> Any:
        """Update an existing note."""
        return await self.call_tool("update_note", {
            "path": file_path,
            "content": content,
        })

    async def search_notes(self, query: str) -> Any:
        """Search for notes in the vault."""
        return await self.call_tool("search_vault", {"query": query})

    # ─── Schedule Operations ────────────────────────────────────

    async def read_schedule(self) -> dict:
        """Read the schedule file from the vault."""
        try:
            content = await self.read_note(self.config.schedule_file)
            return json.loads(content)
        except Exception:
            # If schedule doesn't exist, return empty structure
            return {
                "intervals": self.config.review_intervals,
                "notes": {},
            }

    async def write_schedule(self, schedule: dict) -> None:
        """Write the schedule file to the vault."""
        content = json.dumps(schedule, indent=2)
        try:
            await self.update_note(self.config.schedule_file, content)
        except Exception:
            await self.create_note(self.config.schedule_file, content)

    async def read_review_log(self, date: str) -> Optional[str]:
        """Read a review log for a specific date."""
        try:
            log_path = f"{self.config.review_log_dir}/{date}.md"
            return await self.read_note(log_path)
        except Exception:
            return None

    async def write_review_log(self, date: str, content: str) -> None:
        """Write a review log entry."""
        log_path = f"{self.config.review_log_dir}/{date}.md"
        try:
            await self.update_note(log_path, content)
        except Exception:
            await self.create_note(log_path, content)

    # ─── Generic Tool Call ──────────────────────────────────────

    async def call_tool(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """
        Call any tool on the MCP server by name.
        Useful for tools that vary across Obsidian MCP server implementations.
        """
        self._ensure_connected()
        try:
            result = await self._session.call_tool(name, arguments=args or {})  # type: ignore
            return result
        except Exception as err:
            raise RuntimeError(
                f"Tool call failed: {name}\n"
                f"Args: {json.dumps(args)}\n"
                f"Error: {err}"
            ) from err

    # ─── Helpers ────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if self._session is None:
            raise RuntimeError("Not connected. Call connect() first.")

    @staticmethod
    def _extract_text_content(result: Any) -> str:
        """
        Extract text content from an MCP tool result.
        MCP responses can contain multiple content blocks; this grabs the text.
        """
        if not hasattr(result, "content"):
            return ""

        for block in result.content:
            if getattr(block, "type", None) == "text":
                return getattr(block, "text", "")

        return ""
