"""年分ガードのCLI出力契約と、DB照合前の停止を検証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shinkoku.models import IncomeTaxInput
from shinkoku.tools.tax_calc import calc_income_tax

from .conftest import run_cli, write_json


@pytest.mark.parametrize(
    "command,params",
    [
        ("calc-income", {"salary_income": 5_000_000}),
        ("calc-deductions", {"total_income": 3_000_000, "widow_status": "single_parent"}),
        ("calc-consumption", {"method": "standard"}),
        ("calc-consumption", {"method": "simplified", "simplified_business_type": 5}),
        ("calc-consumption", {"method": "special_20pct"}),
        ("calc-furusato-limit", {"total_income": 5_000_000, "total_income_deductions": 1_500_000}),
    ],
)
def test_unsupported_year_returns_error_json(tmp_path: Path, command: str, params: dict) -> None:
    input_path = write_json(tmp_path, {**params, "fiscal_year": 2027})
    result = run_cli("tax", command, "--input", input_path)

    assert result.returncode == 1
    assert result.stderr == ""
    output = json.loads(result.stdout)
    assert set(output) == {"status", "message"}
    assert output["status"] == "error"
    assert "fiscal_year=2027 は未対応" in output["message"]
    assert "対応年分: [2025, 2026]" in output["message"]


def test_unsupported_year_stops_before_opening_profile_db(tmp_path: Path) -> None:
    db_path = tmp_path / "must-not-be-created.db"
    input_path = write_json(tmp_path, {"fiscal_year": 2027, "method": "special_20pct"})

    result = run_cli("tax", "calc-consumption", "--input", input_path, "--db-path", str(db_path))

    assert result.returncode == 1
    assert "fiscal_year=2027 は未対応" in json.loads(result.stdout)["message"]
    assert not db_path.exists()


def test_sanity_check_does_not_validate_saved_2027_result(tmp_path: Path) -> None:
    input_data = IncomeTaxInput(fiscal_year=2026, salary_income=5_000_000, blue_return_deduction=0)
    result_data = calc_income_tax(input_data).model_dump()
    result_data["fiscal_year"] = 2027
    input_path = write_json(tmp_path, {"input": input_data.model_dump(), "result": result_data})

    result = run_cli("tax", "sanity-check", "--input", input_path)

    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"
    assert "fiscal_year=2027 は未対応" in output["message"]


def test_furusato_explicit_2026_year_keeps_existing_output(tmp_path: Path) -> None:
    input_path = write_json(
        tmp_path,
        {"fiscal_year": 2026, "total_income": 5_000_000, "total_income_deductions": 1_500_000},
    )
    result = run_cli("tax", "calc-furusato-limit", "--input", input_path)
    assert result.returncode == 0
    assert json.loads(result.stdout) == {"estimated_limit": 102_574}
