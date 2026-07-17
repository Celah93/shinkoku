"""年度別の納税者・消費税プロファイルのモデルと保持処理を検証する。"""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from shinkoku.models import FiscalYearTaxProfile, FiscalYearTaxProfileUpdate
from shinkoku.tools.ledger import (
    ledger_get_fiscal_year_tax_profile,
    ledger_init,
    ledger_update_fiscal_year_tax_profile,
)


def _initialize_profile_db(tmp_path, fiscal_year: int = 2025) -> str:
    db_path = str(tmp_path / "profile.db")
    ledger_init(db_path=db_path, fiscal_year=fiscal_year)
    return db_path


def test_profile_model_accepts_valid_states() -> None:
    assert FiscalYearTaxProfile().model_dump() == {
        "taxpayer_status": None,
        "consumption_tax_method": None,
        "simplified_business_type": None,
    }
    assert (
        FiscalYearTaxProfile(
            taxpayer_status="taxable",
            consumption_tax_method="simplified",
            simplified_business_type=5,
        ).simplified_business_type
        == 5
    )
    assert FiscalYearTaxProfile(taxpayer_status="exempt").taxpayer_status == "exempt"


@pytest.mark.parametrize(
    "patch",
    [
        {"taxpayer_status": "unknown"},
        {"consumption_tax_method": "special_30pct"},
        {"simplified_business_type": 0},
        {"simplified_business_type": 7},
    ],
)
def test_update_model_rejects_values_outside_allowed_range(patch: dict) -> None:
    with pytest.raises(ValidationError):
        FiscalYearTaxProfileUpdate(**patch)


@pytest.mark.parametrize(
    "profile",
    [
        {"consumption_tax_method": "simplified"},
        {"taxpayer_status": "exempt", "consumption_tax_method": "standard"},
        {"consumption_tax_method": "standard", "simplified_business_type": 5},
        {"simplified_business_type": 5},
    ],
)
def test_profile_model_rejects_invalid_correlations(profile: dict) -> None:
    with pytest.raises(ValidationError):
        FiscalYearTaxProfile(**profile)


def test_profile_show_and_update_round_trip(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)

    initial = ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)
    assert initial == {
        "status": "ok",
        "fiscal_year": 2025,
        "taxpayer_status": None,
        "consumption_tax_method": None,
        "simplified_business_type": None,
    }

    result = ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="taxable",
            consumption_tax_method="simplified",
            simplified_business_type=5,
        ),
    )
    assert result["before"]["taxpayer_status"] is None
    assert result["after"] == {
        "taxpayer_status": "taxable",
        "consumption_tax_method": "simplified",
        "simplified_business_type": 5,
    }
    assert (
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)[
            "simplified_business_type"
        ]
        == 5
    )


def test_partial_update_preserves_omitted_keys_and_explicit_null_clears_value(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="taxable",
            consumption_tax_method="simplified",
            simplified_business_type=5,
        ),
    )

    partial = ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(consumption_tax_method="simplified"),
    )
    assert partial["after"] == {
        "taxpayer_status": "taxable",
        "consumption_tax_method": "simplified",
        "simplified_business_type": 5,
    }

    cleared = ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            consumption_tax_method=None,
            simplified_business_type=None,
        ),
    )
    assert cleared["after"] == {
        "taxpayer_status": "taxable",
        "consumption_tax_method": None,
        "simplified_business_type": None,
    }


def test_empty_patch_is_rejected(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    with pytest.raises(ValueError, match="更新する項目がありません"):
        ledger_update_fiscal_year_tax_profile(
            db_path=db_path,
            fiscal_year=2025,
            update=FiscalYearTaxProfileUpdate(),
        )


def test_invalid_partial_updates_are_rejected_without_changing_database(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="taxable",
            consumption_tax_method="simplified",
            simplified_business_type=5,
        ),
    )

    # method=simplified のまま事業区分だけ消すと、最終状態が不正になる。
    with pytest.raises(ValidationError):
        ledger_update_fiscal_year_tax_profile(
            db_path=db_path,
            fiscal_year=2025,
            update=FiscalYearTaxProfileUpdate(simplified_business_type=None),
        )
    assert (
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)[
            "simplified_business_type"
        ]
        == 5
    )

    # method確定済みのまま免税へ変える更新も拒否する。
    with pytest.raises(ValidationError):
        ledger_update_fiscal_year_tax_profile(
            db_path=db_path,
            fiscal_year=2025,
            update=FiscalYearTaxProfileUpdate(taxpayer_status="exempt"),
        )
    assert (
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)["taxpayer_status"]
        == "taxable"
    )


def test_exempt_reclassification_accepts_explicit_three_key_patch(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="taxable",
            consumption_tax_method="simplified",
            simplified_business_type=5,
        ),
    )

    result = ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="exempt",
            consumption_tax_method=None,
            simplified_business_type=None,
        ),
    )
    assert result["after"] == {
        "taxpayer_status": "exempt",
        "consumption_tax_method": None,
        "simplified_business_type": None,
    }


def test_ledger_init_rerun_preserves_profile(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=2025,
        update=FiscalYearTaxProfileUpdate(
            taxpayer_status="taxable",
            consumption_tax_method="standard",
        ),
    )

    ledger_init(db_path=db_path, fiscal_year=2025)

    profile = ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)
    assert profile["taxpayer_status"] == "taxable"
    assert profile["consumption_tax_method"] == "standard"


def test_direct_sql_invalid_value_is_rejected_when_read(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE fiscal_years SET taxpayer_status = ? WHERE year = ?",
        ("unknown", 2025),
    )
    conn.commit()
    conn.close()

    with pytest.raises(ValidationError):
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2025)


def test_missing_fiscal_year_is_rejected_for_show_and_update(tmp_path) -> None:
    db_path = _initialize_profile_db(tmp_path)
    with pytest.raises(ValueError, match="Fiscal year 2024 not found"):
        ledger_get_fiscal_year_tax_profile(db_path=db_path, fiscal_year=2024)
    with pytest.raises(ValueError, match="Fiscal year 2024 not found"):
        ledger_update_fiscal_year_tax_profile(
            db_path=db_path,
            fiscal_year=2024,
            update=FiscalYearTaxProfileUpdate(taxpayer_status="taxable"),
        )
