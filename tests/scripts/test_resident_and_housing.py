"""住民税組立て→既存上限CLI、住宅DB→単体CLIの公開JSON契約を検証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.scripts.conftest import run_cli, write_json


def _resident() -> dict:
    return dict(
        fiscal_year=2027,
        income_scope="comprehensive_only",
        income_levy_taxable=True,
        aggregate_income=3_560_000,
        total_income=3_560_000,
        social_insurance=750_000,
    )


def _home() -> dict:
    return dict(
        housing_type="new_custom",
        housing_category="energy_efficient",
        move_in_date="2028-09-01",
        year_end_balance=30_000_000,
        is_special_target_individual=False,
        building_confirmation_date="2027-12-31",
        building_completion_date="2028-07-01",
        is_disaster_red_zone=False,
        total_floor_area=8000,
        residential_floor_area=8000,
        loan_term_years=30,
    )


def test_resident_estimate_connects_to_both_existing_limit_commands(tmp_path: Path) -> None:
    output = run_cli(
        "tax", "calc-resident-tax-estimate", "--input", write_json(tmp_path, _resident())
    )
    assert output.returncode == 0, output.stdout
    data = json.loads(output.stdout)
    assert data["resident_tax_income_levy"] == 235_500
    assert data["resident_tax_assessment_year"] == 2028
    path = write_json(tmp_path, data["furusato_input"])
    detailed = run_cli("tax", "calc-furusato-limit-detailed", "--input", path)
    legacy = run_cli("tax", "calc-furusato-limit", "--input", path)
    assert detailed.returncode == legacy.returncode == 0
    assert json.loads(detailed.stdout) == data["furusato_limit"]
    assert json.loads(legacy.stdout) == {
        "estimated_limit": data["furusato_limit"]["estimated_limit"]
    }


@pytest.mark.parametrize("missing", ["income_levy_taxable", "income_scope", "aggregate_income"])
def test_unconfirmed_resident_inputs_return_error_without_tax(tmp_path: Path, missing: str) -> None:
    data = _resident()
    del data[missing]
    output = run_cli("tax", "calc-resident-tax-estimate", "--input", write_json(tmp_path, data))
    assert output.returncode == 1
    result = json.loads(output.stdout)
    assert result["status"] == "error"
    assert "furusato_limit" not in result


def test_housing_evidence_survives_cli_storage_and_calculation(tmp_path: Path) -> None:
    db = str(tmp_path / "housing.db")
    assert run_cli("ledger", "init", "--db-path", db, "--fiscal-year", "2028").returncode == 0
    saved = run_cli(
        "ledger",
        "hl-add",
        "--db-path",
        db,
        "--fiscal-year",
        "2028",
        "--input",
        write_json(tmp_path, _home()),
    )
    assert saved.returncode == 0, saved.stdout
    listed = run_cli("ledger", "hl-list", "--db-path", db, "--fiscal-year", "2028")
    assert listed.returncode == 0
    home = json.loads(listed.stdout)["details"][0]
    assert home["is_disaster_red_zone"] is False
    assert home["building_confirmation_date"] == "2027-12-31"
    # 公開された計算用フィールドを使い、DBのID等を計算に流用しない。
    params = dict(
        claim_fiscal_year=2028,
        aggregate_income=5_000_000,
        other_requirements_confirmed=True,
        housing_loan_details=[{key: home[key] for key in _home()}],
    )
    output = run_cli("tax", "calc-housing-loan", "--input", write_json(tmp_path, params))
    assert output.returncode == 0, output.stdout
    result = json.loads(output.stdout)
    assert result["housing_loan_credit"] == 140_000
    assert result["entries"][0]["credit_period"] == 10
    assert result["warnings"]
    params["housing_loan_details"][0]["is_disaster_red_zone"] = None
    invalid = run_cli("tax", "calc-housing-loan", "--input", write_json(tmp_path, params))
    assert invalid.returncode == 1
    assert json.loads(invalid.stdout)["status"] == "error"


def test_annual_income_2028_still_rejected_through_cli(tmp_path: Path) -> None:
    output = run_cli(
        "tax",
        "calc-income",
        "--input",
        write_json(tmp_path, dict(fiscal_year=2028, blue_return_deduction=0)),
    )
    assert output.returncode == 1
    assert "未対応" in json.loads(output.stdout)["message"]
