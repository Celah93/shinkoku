"""settlementの4つのJSON例を、実際のCLIで新規DBへ通す。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shinkoku.db import get_connection
from tests.helpers.cli_contract import scan_skill_json_contract
from tests.helpers.fixed_assets import fictional_asset, make_legacy_asset_db
from tests.scripts.conftest import run_cli, write_json


ROOT = Path(__file__).resolve().parents[2]


def _ledger(
    tmp_path: Path,
    command: str,
    *,
    data: dict | None = None,
    year: int = 2026,
    extra: tuple[str, ...] = (),
    code: int = 0,
) -> dict:
    args = [
        "ledger",
        command,
        "--db-path",
        str(tmp_path / "assets.db"),
        "--fiscal-year",
        str(year),
        *extra,
    ]
    if data is not None:
        args.extend(["--input", write_json(tmp_path, data, command + ".json")])
    result = run_cli(*args)
    assert result.returncode == code, (result.stdout, result.stderr)
    payload = json.loads(result.stdout)
    assert payload["status"] == ("ok" if code == 0 else "error"), payload
    return payload


def test_skill_crud_examples_execute_without_format_adjustments(tmp_path: Path) -> None:
    scan = scan_skill_json_contract(ROOT)
    assert not scan.violations
    examples = {
        example.command_path[1]: json.loads(example.text)
        for example in scan.examples
        if example.command_path[1] in {"fa-add", "fa-list", "fa-update", "fa-delete"}
    }
    assert set(examples) == {"fa-add", "fa-list", "fa-update", "fa-delete"}
    _ledger(tmp_path, "init")
    saved = _ledger(tmp_path, "fa-add", data=examples["fa-add"])["asset"]
    assert saved["id"] == examples["fa-list"]["asset_id"] == examples["fa-delete"]["asset_id"]
    listing = _ledger(tmp_path, "fa-list", data=examples["fa-list"])
    assert listing["assets"] == [saved]
    assert saved["prior_private_use"] is False
    assert saved["opening_accumulated_depreciation"] == 0
    updated = _ledger(
        tmp_path, "fa-update", data=examples["fa-update"], extra=("--asset-id", str(saved["id"]))
    )["asset"]
    assert updated["asset_uid"] == saved["asset_uid"]
    assert updated["annual_facts_confirmed_at"] is None
    assert updated["basis_confirmed_at"] == saved["basis_confirmed_at"]
    _ledger(tmp_path, "fa-delete", data=examples["fa-delete"])
    assert _ledger(tmp_path, "fa-list")["count"] == 0
    conn = get_connection(str(tmp_path / "assets.db"))
    try:
        assert conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM opening_balances").fetchone()[0] == 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    "data,fragment",
    [
        ({"fiscal_year": 2026, "detail": fictional_asset()}, "detail"),
        (fictional_asset(acquisition_cost="250000"), "acquisition_cost"),
        (fictional_asset(method="invalid"), "straight_line"),
        (fictional_asset(placed_in_service_date="2026-02-30"), "placed_in_service_date"),
    ],
)
def test_invalid_json_is_rejected_before_database_access(
    tmp_path: Path, data: dict, fragment: str
) -> None:
    result = _ledger(tmp_path, "fa-add", data=data, code=1)
    assert fragment in result["message"]
    assert not (tmp_path / "assets.db").exists()


def test_wrong_year_delete_and_invalid_merged_update_do_not_change_asset(tmp_path: Path) -> None:
    _ledger(tmp_path, "init")
    _ledger(tmp_path, "init", year=2025)
    saved = _ledger(tmp_path, "fa-add", data=fictional_asset())["asset"]
    rejected = _ledger(tmp_path, "fa-delete", data={"asset_id": saved["id"]}, year=2025, code=1)
    assert rejected["code"] == "FA_NOT_FOUND"
    _ledger(
        tmp_path,
        "fa-update",
        data={"acquisition_date": "2026-05-01"},
        extra=("--asset-id", str(saved["id"])),
        code=1,
    )
    assert _ledger(tmp_path, "fa-list")["assets"] == [saved]


def test_cli_migration_is_explicit_and_old_accumulated_value_is_unconfirmed(tmp_path: Path) -> None:
    make_legacy_asset_db(tmp_path / "assets.db")
    before = _ledger(tmp_path, "fa-list", code=1)
    assert "未移行" in before["message"]
    _ledger(tmp_path, "init")
    row = _ledger(tmp_path, "fa-list")["assets"][0]
    assert row["id"] == 42
    assert row["asset_uid"] is None
    assert row["opening_accumulated_depreciation"] is None
    assert row["accumulated_depreciation"] is None
    assert row["legacy_values"]["accumulated_depreciation"] == 62500
