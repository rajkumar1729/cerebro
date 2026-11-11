"""
ObsidianHTTPClient — read vault markdown from an already-running server.

This client targets the common Obsidian local REST/MCP-compatible HTTPS
surface at ``https://localhost:27124`` using bearer-token auth. The AI review
workflow only needs file reads because the due paths come from PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class ObsidianHTTPClient:
    """Small HTTP reader for Obsidian markdown files."""

    def __init__(
        self,
        base_url: str = "https://localhost:27124",
        token: str = "",
        *,
        vault_path: str = "",
        verify_tls: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.vault_path = str(Path(vault_path).resolve()) if vault_path else ""
        self.verify_tls = verify_tls

    def read_note(self, file_path: str) -> str:
        """
        Read a note by vault-relative path.

        Raises:
            PermissionError: when the server rejects auth.
            FileNotFoundError: when the path is not found.
            ConnectionError: when the local server cannot be reached.
        """
        vault_path = self._vault_relative_path(file_path)
        encoded = quote(vault_path, safe="/")
        body = self._request("GET", f"/vault/{encoded}")
        return self._extract_markdown(body)

    def is_available(self) -> bool:
        """Return True when the local Obsidian server responds."""
        try:
            self._request("GET", "/")
            return True
        except Exception:
            return False

    def _request(self, method: str, path: str) -> bytes:
        headers = {"Accept": "application/json, text/markdown, text/plain"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = Request(
            f"{self.base_url}{path}",
            headers=headers,
            method=method,
        )
        context = None if self.verify_tls else ssl._create_unverified_context()

        try:
            with urlopen(req, timeout=30, context=context) as resp:
                return resp.read()
        except HTTPError as err:
            if err.code in {401, 403}:
                raise PermissionError(
                    "Obsidian server rejected the bearer token. "
                    "Set OBSIDIAN_HTTP_TOKEN to your local server token."
                ) from err
            if err.code == 404:
                raise FileNotFoundError(path) from err
            raise RuntimeError(f"Obsidian HTTP error {err.code}: {err.reason}") from err
        except URLError as err:
            raise ConnectionError(
                f"Cannot reach Obsidian at {self.base_url}. "
                "Confirm the local server is running."
            ) from err

    @staticmethod
    def _extract_markdown(body: bytes) -> str:
        text = body.decode("utf-8")
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text

        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in ("content", "markdown", "text", "data"):
                value = parsed.get(key)
                if isinstance(value, str):
                    return value

        return text

    def _vault_relative_path(self, file_path: str) -> str:
        # File paths from the watcher may be absolute. The local REST API
        # expects paths relative to the vault root.
        path = Path(file_path)
        if self.vault_path and path.is_absolute():
            try:
                return str(path.resolve().relative_to(self.vault_path))
            except ValueError:
                logger.debug("Path is not under configured vault: %s", file_path)
        return file_path.replace("\\", "/").lstrip("/")
