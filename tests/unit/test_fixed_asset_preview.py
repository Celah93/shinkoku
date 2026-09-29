"""台帳の診断・候補だけを返し、混在する未確認を0円へ落とさない。"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

import pytest
from pydantic import ValidationError

from shinkoku.db import get_connection
from shinkoku.models import FixedAssetCalculationInput, FixedAssetInput
import shinkoku.tools.fixed_assets as assets
from shinkoku.tools.ledger import ledger_init
from tests.helpers.fixed_assets import fictional_asset


@pytest.fixture
def asset_db(tmp_path: Path) -> str:
    path = str(tmp_path / "preview.db")
    ledger_init(db_path=path, fiscal_year=2026)
    ledger_init(db_path=path, fiscal_year=2025)
    return path


def _add(path: str, **overrides: object) -> dict:
    return assets.ledger_add_fixed_asset(
        db_path=path,
        fiscal_year=2026,
        asset=FixedAssetInput(**fictional_asset(**overrides)),
    )["asset"]


def _dump(path: str) -> list[str]:
    with closing(get_connection(path)) as conn:
        return list(conn.iterdump())


def _preview(path: str, **selection: object) -> dict:
    before = _dump(path)
    result = assets.ledger_preview_fixed_asset_depreciation(
        db_path=path,
        fiscal_year=2026,
        selection=FixedAssetCalculationInput(**selection),
    )
    assert _dump(path) == before
    return result


def _assert_blocked(row: dict) -> None:
    assert row["calculation_status"] == "blocked"
    assert row["blocking_reason"]
    for key in (
        "ordinary_amount",
        "expense_amount",
        "closing_book_value",
        "calculation",
        "statement_fields",
        "journal_candidate",
    ):
        assert row[key] is None


def test_ready_zero_and_blocked_are_kept_separate(asset_db: str) -> None:
    ready = _add(asset_db)
    zero = _add(asset_db, placed_in_service_date="2027-01-01")
    blocked = assets.ledger_add_fixed_asset(
        db_path=asset_db,
        fiscal_year=2026,
        asset=FixedAssetInput(
            name="未確認の架空PC", acquisition_date="2026-05-01", acquisition_cost=250000
        ),
    )["asset"]
    result = _preview(asset_db)
    assert result["status"] == "ok" and result["count"] == 3
    assert result["complete"] is False and result["total_expense"] is None
    assert result["calculable_subtotal"] == 46875
    assert [row["asset_id"] for row in result["assets"]] == [ready["id"], zero["id"], blocked["id"]]
    first, second, third = result["assets"]
    assert first["calculation_status"] == "ready"
    assert first["expense_amount"] == first["ordinary_amount"] == 46875
    assert first["closing_book_value"] == 203125
    assert first["statement_fields"] == {
        "name": "検証用PC",
        "quantity": "1",
        "quantity_unit": "台",
        "acquisition_date": "2026-04-01",
        "placed_in_service_date": "2026-04-01",
        "acquisition_cost": 250000,
        "treatment": "normal_depreciation",
        "method": "straight_line",
        "useful_life": 4,
        "depreciation_basis": 250000,
        "rate_numerator": 250,
        "rate_denominator": 1000,
        "months": 9,
        "ordinary_amount": 46875,
        "additional_depreciation_amount": 0,
        "total_depreciation_amount": 46875,
        "business_use_ratio": 100,
        "expense_amount": 46875,
        "closing_book_value": 203125,
        "memo": None,
    }
    candidate = first["journal_candidate"]
    assert candidate["date"] == "2026-12-31"
    assert candidate["source"] == "adjustment" and candidate["is_adjustment"] is True
    assert candidate["lines"] == [
        {
            "side": "debit",
            "account_code": "5200",
            "amount": 46875,
            "tax_category": "out_of_scope",
            "tax_amount": 0,
        },
        {
            "side": "credit",
            "account_code": "1130",
            "amount": 46875,
            "tax_category": "out_of_scope",
            "tax_amount": 0,
        },
    ]
    assert second["calculation_status"] == "no_depreciation"
    assert second["expense_amount"] == second["statement_fields"]["expense_amount"] == 0
    assert second["journal_candidate"] is None
    _assert_blocked(third)
    assert "placed_in_service_date" in third["missing_fields"]
    assert third["error_code"] == "FA_INPUT_UNCONFIRMED"
    assert _preview(asset_db) == result


def test_explicit_ids_keep_order_and_do_not_hide_missing_or_other_year_ids(asset_db: str) -> None:
    first = _add(asset_db)
    second = _add(asset_db)
    other = assets.ledger_add_fixed_asset(
        db_path=asset_db,
        fiscal_year=2025,
        asset=FixedAssetInput(
            name="別年度の架空資産", acquisition_date="2025-01-01", acquisition_cost=100000
        ),
    )["asset"]
    result = _preview(asset_db, asset_ids=[second["id"], 999, other["id"]])
    assert [row["asset_id"] for row in result["assets"]] == [second["id"], 999, other["id"]]
    assert first["id"] not in [row["asset_id"] for row in result["assets"]]
    assert result["complete"] is False and result["total_expense"] is None
    assert result["calculable_subtotal"] == 46875
    for row in result["assets"][1:]:
        _assert_blocked(row)
        assert row["error_code"] == "FA_NOT_FOUND" and row["name"] is None


def test_known_zero_empty_and_all_blocked_totals_have_different_meanings(asset_db: str) -> None:
    empty = _preview(asset_db)
    assert empty["assets"] == [] and empty["count"] == 0
    assert empty["complete"] is True and empty["total_expense"] == 0
    _add(
        asset_db,
        acquisition_date="2020-01-01",
        placed_in_service_date="2020-01-01",
        origin="verified_opening",
        opening_accumulated_depreciation=249999,
    )
    zero = _preview(asset_db)
    assert zero["complete"] is True and zero["total_expense"] == zero["calculable_subtotal"] == 0
    assert zero["assets"][0]["calculation_status"] == "no_depreciation"
    assert zero["assets"][0]["journal_candidate"] is None
    blocked = _preview(asset_db, asset_ids=[999])
    assert blocked["complete"] is False and blocked["total_expense"] is None
    assert blocked["calculable_subtotal"] == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"method": "declining_balance"},
        {"business_use_ratio": 50},
        {"business_use_ratio": 0},
        {"treatment": "pooled_depreciation"},
        {"treatment": "small_asset_special"},
        {"treatment": "immediate_expense"},
        {"asset_account_code": "1140"},
        {"asset_class": "intangible"},
        {"book_basis": "business_portion_direct"},
        {"prior_private_use": True},
        {"additional_depreciation_applicable": True},
        {"basis_confirmed": False},
        {"annual_facts_confirmed": False},
        {"opening_accumulated_depreciation": None},
        {"placed_in_service_date": None},
        {"quantity": None},
        {
            "acquisition_date": "2007-03-31",
            "placed_in_service_date": "2007-03-31",
            "origin": "verified_opening",
        },
        {
            "acquisition_date": "2020-01-01",
            "placed_in_service_date": "2020-01-01",
            "origin": "verified_opening",
            "opening_accumulated_depreciation": 250000,
        },
        {"opening_accumulated_depreciation": 1},
    ],
)
def test_stage2_rejections_become_blocked_rows(asset_db: str, overrides: dict) -> None:
    record = _add(asset_db, **overrides)
    result = _preview(asset_db, asset_ids=[record["id"]])
    _assert_blocked(result["assets"][0])
    assert result["complete"] is False and result["total_expense"] is None
    assert result["calculable_subtotal"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"asset_ids": []},
        {"asset_ids": None},
        {"asset_ids": [1, 1]},
        {"asset_ids": [0]},
        {"asset_ids": [-1]},
        {"asset_ids": [True]},
        {"asset_ids": ["1"]},
        {"asset_ids": [1.0]},
        {"asset_ids": 1},
        {"fiscal_year": 2026, "detail": {"asset_ids": [1]}},
    ],
)
def test_selection_rejects_ambiguous_or_non_integer_ids(payload: dict) -> None:
    with pytest.raises(ValidationError):
        FixedAssetCalculationInput.model_validate(payload, strict=True)


def test_calculation_uses_one_read_snapshot_and_never_attempts_a_write(
    asset_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add(asset_db)
    _add(asset_db, placed_in_service_date="2027-01-01")
    writes = []
    connections = []
    forbidden = {
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_UPDATE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_ALTER_TABLE,
    }

    def connect(path: str) -> sqlite3.Connection:
        conn = get_connection(path)
        connections.append(path)

        def authorizer(action: int, first: str | None, *_: object) -> int:
            if action in forbidden:
                writes.append((action, first))
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)
        return conn

    monkeypatch.setattr(assets, "get_connection", connect)
    assert _preview(asset_db)["complete"] is True
    assert connections == [asset_db] and writes == []


def test_query_only_also_blocks_an_accidental_write_in_a_delegate(
    asset_db: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add(asset_db)
    before = _dump(asset_db)

    def rogue(**kwargs: object) -> None:
        conn = kwargs["_connection"]
        assert isinstance(conn, sqlite3.Connection)
        conn.execute("UPDATE fixed_assets SET memo = '書き込まれてはいけない架空値'")

    monkeypatch.setattr(assets, "ledger_calculate_fixed_asset_depreciation", rogue)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        assets.ledger_preview_fixed_asset_depreciation(
            db_path=asset_db, fiscal_year=2026, selection=FixedAssetCalculationInput()
        )
    assert _dump(asset_db) == before
