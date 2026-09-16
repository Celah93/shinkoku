"""台帳からの読取り専用計算と単発CLIの年次文脈が一致することを検証する。"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path

from shinkoku.db import get_connection
from shinkoku.tools.fixed_assets import ledger_calculate_fixed_asset_depreciation
from tests.helpers.depreciation import annual_context, depreciation_input
from tests.helpers.fixed_assets import fictional_asset
from tests.scripts.conftest import run_cli, write_json


def test_ledger_and_single_cli_share_annual_detail_without_db_writes(tmp_path: Path) -> None:
    db = str(tmp_path / "fictional-assets.db")
    # 太郎のPC: 2029年末までの累計234375円、2030年の残存簿価15625円からの最終償却。
    init = run_cli("ledger", "init", "--db-path", db, "--fiscal-year", "2030")
    assert init.returncode == 0, init.stdout
    asset = fictional_asset(origin="verified_opening", opening_accumulated_depreciation=234375)
    created = run_cli(
        "ledger",
        "fa-add",
        "--db-path",
        db,
        "--fiscal-year",
        "2030",
        "--input",
        write_json(tmp_path, asset, "asset.json"),
    )
    assert created.returncode == 0, created.stdout
    row = json.loads(created.stdout)["asset"]
    with closing(get_connection(db)) as conn:
        before = list(conn.iterdump())
    ledger = ledger_calculate_fixed_asset_depreciation(
        db_path=db, fiscal_year=2030, asset_id=row["id"]
    )
    # 台帳で確認できた同じ事実を、単発CLIには明示的な年次文脈として渡す。
    context = annual_context(
        fiscal_year=2030,
        acquisition_date=row["acquisition_date"],
        placed_in_service_date=row["placed_in_service_date"],
        opening_accumulated_depreciation=row["opening_accumulated_depreciation"],
        asset_class=row["asset_class"],
        book_basis=row["book_basis"],
        prior_private_use=row["prior_private_use"],
        additional_depreciation_applicable=row["additional_depreciation_applicable"],
        basis_confirmed=row["basis_confirmed_at"] is not None,
        annual_facts_confirmed=row["annual_facts_confirmed_at"] is not None,
    )
    payload = depreciation_input(
        method=row["method"],
        acquisition_cost=row["acquisition_cost"],
        useful_life=row["useful_life"],
        business_use_ratio=row["business_use_ratio"],
        annual_context=context,
    )
    single = run_cli(
        "tax",
        "calc-depreciation",
        "--details",
        "--input",
        write_json(tmp_path, payload, "annual.json"),
    )
    assert single.returncode == 0, single.stdout
    assert json.loads(single.stdout) == ledger.model_dump(mode="json")
    assert ledger.ordinary_amount == ledger.expense_amount == 15624
    assert ledger.opening_book_value == 15625 and ledger.closing_book_value == 1
    assert ledger.capped_to_book_value
    with closing(get_connection(db)) as conn:
        assert list(conn.iterdump()) == before
        assert conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0] == 0
