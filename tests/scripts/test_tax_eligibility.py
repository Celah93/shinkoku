"""要件判定CLIと申告用計算の境界。実データ・実サイトは使わない。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.tax_eligibility import verified_blue_facts, verified_invoice_facts
from shinkoku.models import FiscalYearTaxProfileUpdate
from shinkoku.tools.ledger import ledger_init, ledger_update_fiscal_year_tax_profile

from .conftest import run_cli, write_json


def test_check_eligibility_exposes_missing_requirements(tmp_path: Path) -> None:
    path = write_json(
        tmp_path, {"scheme": "blue_return", "fiscal_year": 2026, "requested_deduction": 650000}
    )
    result = run_cli("tax", "check-eligibility", "--input", path)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "indeterminate"
    assert "blue_return_approved" in output["missing_fields"]


@pytest.mark.parametrize("scheme", ["blue_return", "special_30pct"])
def test_future_requirements_can_be_checked_without_enabling_filing(
    tmp_path: Path, scheme: str
) -> None:
    params: dict = {"scheme": scheme, "fiscal_year": 2027}
    if scheme == "blue_return":
        params.update(
            {
                "requested_deduction": 750000,
                "blue_return": verified_blue_facts(
                    qualified_electronic_books=True, electronic_books_notice_requirement_met=True
                ).model_dump(mode="json"),
            }
        )
    else:
        params["invoice_special"] = verified_invoice_facts().model_dump(mode="json")
    result = run_cli("tax", "check-eligibility", "--input", write_json(tmp_path, params))
    assert result.returncode == 0
    assert json.loads(result.stdout)["status"] == "eligible"


def test_blue_request_must_include_amount(tmp_path: Path) -> None:
    result = run_cli(
        "tax",
        "check-eligibility",
        "--input",
        write_json(
            tmp_path,
            {
                "scheme": "blue_return",
                "fiscal_year": 2026,
            },
        ),
    )
    assert result.returncode == 1
    assert "requested_deduction" in json.loads(result.stdout)["message"]


def test_filing_missing_invoice_requirements_stops_before_db(tmp_path: Path) -> None:
    db_path = tmp_path / "must-not-be-created.db"
    path = write_json(
        tmp_path,
        {
            "fiscal_year": 2026,
            "method": "special_20pct",
            "calculation_mode": "filing",
        },
    )
    result = run_cli("tax", "calc-consumption", "--input", path, "--db-path", str(db_path))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"
    assert "TAX_ELIGIBILITY_UNCONFIRMED" in output["message"]
    assert not db_path.exists()


def test_unknown_legacy_input_remains_an_explicit_estimate(tmp_path: Path) -> None:
    path = write_json(tmp_path, {"fiscal_year": 2026, "business_revenue": 3000000})
    result = run_cli("tax", "calc-income", "--input", path)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["calculation_mode"] == "estimate"
    assert output["eligibility_checks"][0]["status"] == "indeterminate"


def test_filing_income_checks_facts_and_preserves_tax(tmp_path: Path) -> None:
    params = {
        "fiscal_year": 2026,
        "business_revenue": 3000000,
        "business_expenses": 1000000,
        "calculation_mode": "filing",
        "blue_return_eligibility": verified_blue_facts().model_dump(mode="json"),
    }
    result = run_cli("tax", "calc-income", "--input", write_json(tmp_path, params))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["calculation_mode"] == "filing"
    assert output["eligibility_checks"][0]["status"] == "eligible"
    assert output["tax_due"] == 15800
    params["blue_return_eligibility"]["filing_within_deadline"] = False
    rejected = run_cli("tax", "calc-income", "--input", write_json(tmp_path, params))
    assert rejected.returncode == 1
    assert "TAX_ELIGIBILITY_INELIGIBLE" in json.loads(rejected.stdout)["message"]


@pytest.mark.parametrize(
    "profile", [None, {"taxpayer_status": "exempt"}, {"taxpayer_status": "taxable"}]
)
def test_filing_does_not_ignore_unconfirmed_or_exempt_db_profile(
    tmp_path: Path, profile: dict | None
) -> None:
    db_path = str(tmp_path / "existing-profile.db")
    ledger_init(db_path=db_path, fiscal_year=2026)
    if profile is not None:
        ledger_update_fiscal_year_tax_profile(
            db_path=db_path, fiscal_year=2026, update=FiscalYearTaxProfileUpdate(**profile)
        )
    input_path = write_json(
        tmp_path,
        {
            "fiscal_year": 2026,
            "method": "special_20pct",
            "calculation_mode": "filing",
            "invoice_special_eligibility": verified_invoice_facts().model_dump(mode="json"),
        },
    )
    result = run_cli("tax", "calc-consumption", "--input", input_path, "--db-path", db_path)
    assert result.returncode == 1
    assert "申告用計算ではDB" in json.loads(result.stdout)["message"]
