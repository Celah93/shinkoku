"""候補取得CLIの選択・部分成功・エラーと、DB無変更を確認する。"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path

import pytest

from shinkoku.db import get_connection
from shinkoku.models import FixedAssetInput
from shinkoku.tools.fixed_assets import ledger_add_fixed_asset
from shinkoku.tools.ledger import ledger_init
from tests.helpers.cli_contract import scan_skill_json_contract
from tests.helpers.fixed_assets import fictional_asset
from tests.scripts.conftest import run_cli, write_json


@pytest.mark.parametrize("selected", [False, True])
def test_preview_cli_and_skill_example_leave_database_unchanged(
    tmp_path: Path, selected: bool
) -> None:
    db = str(tmp_path / "fictional.db")
    ledger_init(db_path=db, fiscal_year=2026)
    first = ledger_add_fixed_asset(
        db_path=db, fiscal_year=2026, asset=FixedAssetInput(**fictional_asset())
    )["asset"]
    ledger_add_fixed_asset(
        db_path=db,
        fiscal_year=2026,
        asset=FixedAssetInput(**fictional_asset(basis_confirmed=False)),
    )
    with closing(get_connection(db)) as conn:
        before = list(conn.iterdump())
    args = ["ledger", "fa-depreciation", "--db-path", db, "--fiscal-year", "2026"]
    if selected:
        scan = scan_skill_json_contract(Path(__file__).resolve().parents[2])
        example = next(
            item for item in scan.examples if item.command_path == ("ledger", "fa-depreciation")
        )
        payload = json.loads(example.text)
        assert payload["asset_ids"] == [first["id"]]
        args.extend(["--input", write_json(tmp_path, payload)])
    response = run_cli(*args)
    assert response.returncode == 0, response.stdout
    result = json.loads(response.stdout)
    assert result["status"] == "ok" and result["complete"] is selected
    assert result["count"] == (1 if selected else 2)
    assert result["total_expense"] == (46875 if selected else None)
    assert result["calculable_subtotal"] == 46875
    with closing(get_connection(db)) as conn:
        assert list(conn.iterdump()) == before
        assert conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0] == 0


@pytest.mark.parametrize(
    "payload", [{"asset_ids": []}, {"asset_ids": [1, 1]}, {"asset_ids": ["1"]}]
)
def test_bad_selection_is_rejected_before_opening_database(tmp_path: Path, payload: dict) -> None:
    db = tmp_path / "missing.db"
    response = run_cli(
        "ledger",
        "fa-depreciation",
        "--db-path",
        str(db),
        "--fiscal-year",
        "2026",
        "--input",
        write_json(tmp_path, payload),
    )
    assert response.returncode == 1
    assert json.loads(response.stdout)["status"] == "error"
    assert not db.exists()


def test_missing_id_is_blocked_but_missing_database_is_an_error(tmp_path: Path) -> None:
    db = tmp_path / "preview.db"
    args = ["ledger", "fa-depreciation", "--db-path", str(db), "--fiscal-year", "2026"]
    absent = run_cli(*args)
    assert absent.returncode == 1 and not db.exists()
    ledger_init(db_path=str(db), fiscal_year=2026)
    result = run_cli(*args, "--input", write_json(tmp_path, {"asset_ids": [999]}))
    assert result.returncode == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["complete"] is False and payload["total_expense"] is None
    assert payload["assets"][0]["error_code"] == "FA_NOT_FOUND"
