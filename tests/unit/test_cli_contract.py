"""argparseから導出するCLI契約の回帰テスト。"""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from shinkoku.cli import build_parser
from tests.helpers.cli_contract import (
    EXPECTED_LEAF_COMMAND_COUNT,
    iter_leaf_parsers,
    snapshot_parser_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "cli_contract.json"


def _expected_snapshot() -> dict[str, object]:
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_parser_contract_matches_snapshot() -> None:
    assert snapshot_parser_contract(build_parser()) == _expected_snapshot()


def test_leaf_command_count_is_complete() -> None:
    leaves = iter_leaf_parsers(build_parser())

    assert len(leaves) == EXPECTED_LEAF_COMMAND_COUNT


def test_global_version_is_in_contract() -> None:
    snapshot = snapshot_parser_contract(build_parser())
    global_arguments = snapshot["global_arguments"]

    assert isinstance(global_arguments, list)
    assert any(argument["aliases"] == ["--version"] for argument in global_arguments)


def test_all_leaf_commands_render_help_in_process() -> None:
    parser = build_parser()

    for path, _ in iter_leaf_parsers(parser):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            with pytest.raises(SystemExit) as caught:
                parser.parse_args([*path, "--help"])
        assert caught.value.code == 0, " ".join(path)
        assert stdout.getvalue(), " ".join(path)
        assert stderr.getvalue() == "", " ".join(path)


def test_snapshot_detects_an_intentional_parser_change() -> None:
    parser = build_parser()
    unchanged = snapshot_parser_contract(parser)
    leaves = dict(iter_leaf_parsers(parser))

    leaves[("ledger", "bs")].add_argument("--contract-regression-probe")
    changed = snapshot_parser_contract(parser)

    assert changed != unchanged
    bs_arguments = changed["commands"]["ledger bs"]["arguments"]
    assert any(argument["aliases"] == ["--contract-regression-probe"] for argument in bs_arguments)
