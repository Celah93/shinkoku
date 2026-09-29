"""台帳の事実・確認状態とCRUDの境界を検証する。"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from shinkoku.db import get_connection, init_db
from shinkoku.models import FixedAssetInput, FixedAssetListInput, FixedAssetUpdateInput
from shinkoku.tools.fixed_assets import (
    ledger_add_fixed_asset,
    ledger_delete_fixed_asset,
    ledger_list_fixed_assets,
    ledger_update_fixed_asset,
)
from shinkoku.tools.ledger import ledger_init, ledger_pl, ledger_bs
from tests.helpers.fixed_assets import fictional_asset, make_legacy_asset_db


@pytest.fixture
def asset_db(tmp_path: Path) -> str:
    path = str(tmp_path / "assets.db")
    ledger_init(db_path=path, fiscal_year=2026)
    ledger_init(db_path=path, fiscal_year=2025)
    return path


def _add(path: str, **overrides: object) -> dict:
    return ledger_add_fixed_asset(
        db_path=path, fiscal_year=2026, asset=FixedAssetInput(**fictional_asset(**overrides))
    )["asset"]


def _list(path: str, year: int = 2026, **filters: object) -> dict:
    return ledger_list_fixed_assets(
        db_path=path, fiscal_year=year, filters=FixedAssetListInput(**filters)
    )


def _update(path: str, asset_id: int, **patch: object) -> dict:
    return ledger_update_fixed_asset(
        db_path=path, fiscal_year=2026, asset_id=asset_id, update=FixedAssetUpdateInput(**patch)
    )


def test_crud_retains_types_uid_and_does_not_create_journals(asset_db: str) -> None:
    before_pl = ledger_pl(db_path=asset_db, fiscal_year=2026)
    before_bs = ledger_bs(db_path=asset_db, fiscal_year=2026)
    first = _add(asset_db)
    second = _add(asset_db)
    assert first["asset_uid"] != second["asset_uid"]
    assert str(UUID(first["asset_uid"])) == first["asset_uid"]
    assert first["missing_fields"] == []
    assert first["calculation_available"] is True
    assert first["accumulated_depreciation"] is None
    assert first["opening_accumulated_depreciation"] == 0
    assert first["prior_private_use"] is False
    assert first["additional_depreciation_applicable"] is False
    assert first["basis_confirmed_at"] is not None
    assert _list(asset_db)["count"] == 2
    assert _list(asset_db, asset_uid=first["asset_uid"])["assets"] == [first]
    assert _list(asset_db, 2025)["count"] == 0
    assert _list(asset_db, asset_id=second["id"])["assets"] == [second]

    updated = _update(asset_db, first["id"], memo="架空の補足")["asset"]
    assert updated["asset_uid"] == first["asset_uid"]
    assert updated["basis_confirmed_at"] == first["basis_confirmed_at"]
    assert ledger_delete_fixed_asset(db_path=asset_db, fiscal_year=2026, asset_id=second["id"]) == {
        "status": "ok",
        "deleted_id": second["id"],
    }
    assert _list(asset_db)["count"] == 1
    assert ledger_pl(db_path=asset_db, fiscal_year=2026) == before_pl
    assert ledger_bs(db_path=asset_db, fiscal_year=2026) == before_bs
    conn = get_connection(asset_db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0] == 0
    finally:
        conn.close()


def test_unknown_false_and_zero_and_patch_omission_are_distinct(asset_db: str) -> None:
    minimal = FixedAssetInput(name="架空PC", acquisition_date="2026-04-01", acquisition_cost=250000)
    saved = ledger_add_fixed_asset(db_path=asset_db, fiscal_year=2026, asset=minimal)["asset"]
    for key in (
        "business_use_ratio",
        "opening_accumulated_depreciation",
        "prior_private_use",
        "additional_depreciation_applicable",
    ):
        assert saved[key] is None
        assert key in saved["missing_fields"]
    result = _update(
        asset_db,
        saved["id"],
        business_use_ratio=0,
        opening_accumulated_depreciation=0,
        prior_private_use=False,
        additional_depreciation_applicable=False,
    )["asset"]
    assert type(result["business_use_ratio"]) is int and result["business_use_ratio"] == 0
    assert (
        type(result["opening_accumulated_depreciation"]) is int
        and result["opening_accumulated_depreciation"] == 0
    )
    assert result["prior_private_use"] is False
    result = _update(asset_db, saved["id"], memo="架空の確認")["asset"]
    assert result["prior_private_use"] is False
    assert result["business_use_ratio"] == 0
    result = _update(asset_db, saved["id"], prior_private_use=None)["asset"]
    assert result["prior_private_use"] is None
    assert result["business_use_ratio"] == 0


def test_changed_facts_clear_old_confirmation_unless_explicitly_reconfirmed(asset_db: str) -> None:
    saved = _add(asset_db)
    updated = _update(asset_db, saved["id"], business_use_ratio=60)["asset"]
    assert updated["basis_confirmed_at"] is None
    assert updated["annual_facts_confirmed_at"] is None
    updated = _update(
        asset_db,
        saved["id"],
        business_use_ratio=100,
        basis_confirmed=True,
        annual_facts_confirmed=True,
    )["asset"]
    assert updated["basis_confirmed_at"] is not None
    assert updated["annual_facts_confirmed_at"] is not None
    updated = _update(asset_db, saved["id"], basis_confirmed=False, annual_facts_confirmed=None)[
        "asset"
    ]
    assert updated["basis_confirmed_at"] is updated["annual_facts_confirmed_at"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {"acquisition_date": "2026-05-01"},
        {"opening_accumulated_depreciation": 250001},
        {"asset_account_code": "5200"},
        {"asset_account_code": "1002"},
        {"asset_account_code": "1199"},
        {"acquisition_date": "2025-04-01"},
    ],
)
def test_partial_update_validates_merged_facts_and_does_not_write(
    asset_db: str, patch: dict
) -> None:
    saved = _add(asset_db)
    with pytest.raises(ValueError):
        _update(asset_db, saved["id"], **patch)
    assert _list(asset_db)["assets"] == [saved]


@pytest.mark.parametrize(
    "payload",
    [
        {"acquisition_cost": "250000"},
        {"acquisition_cost": True},
        {"acquisition_cost": 0},
        {"business_use_ratio": True},
        {"business_use_ratio": 101},
        {"prior_private_use": 0},
        {"method": "unknown"},
        {"name": " "},
        {"placed_in_service_date": "2026-02-30"},
        {"acquisition_date": "20260401"},
        {"placed_in_service_date": "2025-12-31"},
        {"quantity": "NaN"},
        {"quantity": "0"},
        {"quantity": 1},
        {"useful_life": 0},
        {"fiscal_year": 2026},
        {"detail": {}},
        {"asset_uid": "caller-chosen"},
        {"accumulated_depreciation": 0},
        {"previous_asset_id": 7},
    ],
)
def test_input_rejects_types_dates_readonly_fields_and_wrappers(payload: dict) -> None:
    with pytest.raises(ValidationError):
        FixedAssetInput.model_validate(fictional_asset(**payload), strict=True)


@pytest.mark.parametrize(
    "patch", [{}, {"name": None}, {"acquisition_date": None}, {"acquisition_cost": None}]
)
def test_patch_rejects_empty_input_and_cleared_identity(patch: dict) -> None:
    with pytest.raises(ValidationError):
        FixedAssetUpdateInput(**patch)


def test_wrong_year_missing_id_and_successor_are_protected(asset_db: str) -> None:
    saved = _add(asset_db)
    assert (
        ledger_update_fixed_asset(
            db_path=asset_db,
            fiscal_year=2025,
            asset_id=saved["id"],
            update=FixedAssetUpdateInput(memo="別年"),
        )["code"]
        == "FA_NOT_FOUND"
    )
    assert (
        ledger_delete_fixed_asset(db_path=asset_db, fiscal_year=2025, asset_id=saved["id"])["code"]
        == "FA_NOT_FOUND"
    )
    assert _update(asset_db, 999, memo="不明")["code"] == "FA_NOT_FOUND"
    conn = get_connection(asset_db)
    try:
        conn.execute("INSERT INTO fiscal_years (year) VALUES (2027)")
        conn.execute(
            "INSERT INTO fixed_assets (name, acquisition_date, acquisition_cost, fiscal_year, previous_asset_id) VALUES ('架空の後続行', '2026-04-01', 250000, 2027, ?)",
            (saved["id"],),
        )
        conn.commit()
    finally:
        conn.close()
    assert _update(asset_db, saved["id"], memo="変更")["code"] == "FA_HAS_SUCCESSOR"
    assert (
        ledger_delete_fixed_asset(db_path=asset_db, fiscal_year=2026, asset_id=saved["id"])["code"]
        == "FA_HAS_SUCCESSOR"
    )
    assert _list(asset_db)["assets"] == [saved]


def test_legacy_values_are_read_without_confirmation_or_auto_uid(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    make_legacy_asset_db(path)
    init_db(str(path)).close()
    rows = _list(str(path))["assets"]
    assert len(rows) == 1
    saved = rows[0]
    assert saved["id"] == 42 and saved["asset_uid"] is None
    assert saved["accumulated_depreciation"] is None
    assert saved["legacy_values"] == {"accumulated_depreciation": 62500}
    assert saved["opening_accumulated_depreciation"] is None
    assert saved["state"] == "legacy_unverified"
    assert _list(str(path))["assets"] == [saved]
    updated = _update(
        str(path), 42, opening_accumulated_depreciation=62500, prior_private_use=False
    )["asset"]
    assert updated["asset_uid"] is not None
    assert updated["basis_confirmed_at"] is None
    assert updated["legacy_values"] == {"accumulated_depreciation": 62500}


def test_missing_unmigrated_and_wrong_year_databases_are_not_initialised(
    tmp_path: Path, asset_db: str
) -> None:
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(ValueError, match="DBが存在しません"):
        _list(str(missing))
    assert not missing.exists()
    legacy = tmp_path / "unmigrated.db"
    original = make_legacy_asset_db(legacy)
    with pytest.raises(ValueError, match="未移行"):
        _list(str(legacy))
    conn = get_connection(str(legacy))
    try:
        assert [
            tuple(row) for row in conn.execute("SELECT * FROM fixed_assets ORDER BY id")
        ] == original
    finally:
        conn.close()
    with pytest.raises(ValueError, match="年度2027がありません"):
        _list(asset_db, 2027)
