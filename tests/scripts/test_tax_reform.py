"""2027年ふるさと上限・高所得特例のJSON契約と失敗時の停止。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.scripts.conftest import run_cli, write_json


def _resident_input() -> dict:
    return dict(
        fiscal_year=2027,
        resident_tax_income_levy=10000000,
        resident_taxable_income=100000000,
        personal_deduction_difference=0,
        income_tax_basic_deduction=0,
    )


def test_detailed_furusato_and_legacy_output_shape_match(tmp_path: Path) -> None:
    path = write_json(tmp_path, _resident_input())
    detailed = run_cli("tax", "calc-furusato-limit-detailed", "--input", path)
    legacy = run_cli("tax", "calc-furusato-limit", "--input", path)
    assert detailed.returncode == legacy.returncode == 0
    data = json.loads(detailed.stdout)
    assert data["special_credit_limit"] == 1930000
    assert data["resident_tax_assessment_year"] == 2028
    assert data["estimated_limit"] > 1930000
    assert json.loads(legacy.stdout) == {"estimated_limit": data["estimated_limit"]}


@pytest.mark.parametrize("command", ["calc-furusato-limit", "calc-furusato-limit-detailed"])
def test_new_year_requires_resident_tax_inputs(tmp_path: Path, command: str) -> None:
    path = write_json(
        tmp_path, {"fiscal_year": 2027, "total_income": 5000000, "total_income_deductions": 1500000}
    )
    output = run_cli("tax", command, "--input", path)
    assert output.returncode == 1
    data = json.loads(output.stdout)
    assert data["status"] == "error"
    assert "resident_tax_income_levy" in data["message"]


def test_minimum_tax_requires_recalculation_then_returns_final_amounts(tmp_path: Path) -> None:
    params = dict(
        fiscal_year=2027,
        incomes={"comprehensive_income": 500000000},
        ordinary_income_tax=40000000,
        income_scope_confirmed=True,
        calculation_mode="filing",
        uses_nonfiling_system=True,
    )
    output = run_cli("tax", "calc-minimum-income", "--input", write_json(tmp_path, params))
    assert output.returncode == 0
    result = json.loads(output.stdout)
    assert result["status"] == "requires_recalculation"
    assert result["total_tax"] is None
    params["recalculated_income_tax"] = 40000000
    output = run_cli("tax", "calc-minimum-income", "--input", write_json(tmp_path, params))
    assert output.returncode == 0
    result = json.loads(output.stdout)
    assert result["status"] == "applicable"
    assert result["additional_income_tax"] == 59660000
    assert result["total_tax"] == 101752860


def test_unconfirmed_income_scope_does_not_produce_filing_tax(tmp_path: Path) -> None:
    params = dict(
        fiscal_year=2027,
        incomes={"comprehensive_income": 500000000},
        ordinary_income_tax=40000000,
        calculation_mode="filing",
    )
    output = run_cli("tax", "calc-minimum-income", "--input", write_json(tmp_path, params))
    assert output.returncode == 1
    assert json.loads(output.stdout)["status"] == "error"


def test_income_cli_calculates_high_income_and_sanity_checks(tmp_path: Path) -> None:
    params = dict(
        fiscal_year=2027,
        business_revenue=2000000000,
        blue_return_deduction=0,
        furusato_nozei=800000000,
        minimum_tax_income_complete=True,
        calculation_mode="filing",
    )
    output = run_cli("tax", "calc-income", "--input", write_json(tmp_path, params))
    assert output.returncode == 0, output.stdout
    result = json.loads(output.stdout)
    assert result["tax_due"] == 550585100
    check = run_cli(
        "tax", "sanity-check", "--input", write_json(tmp_path, {"input": params, "result": result})
    )
    assert check.returncode == 0
    assert json.loads(check.stdout)["passed"] is True
