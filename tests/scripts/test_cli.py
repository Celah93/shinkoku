"""Tests for the top-level CLI."""

from __future__ import annotations

from shinkoku import __version__

from .conftest import run_cli


def test_version() -> None:
    result = run_cli("--version")

    assert result.returncode == 0
    assert result.stdout.strip() == f"shinkoku {__version__}"
    assert result.stderr == ""
