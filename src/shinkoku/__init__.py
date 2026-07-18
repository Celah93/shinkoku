"""shinkoku - 確定申告自動化 Claude Code Plugin MCP Server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("shinkoku")
except PackageNotFoundError:
    __version__ = "0+unknown"
