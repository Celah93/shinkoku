"""架空の読取り済みJSONから、実CLIで申告計算と給与証憑の照合を行う。"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.helpers.withholding import withholding_input
from tests.scripts.conftest import run_cli, write_json


@pytest.mark.parametrize("year,total,tax_due", [(2025, 2040000, 23000), (2026, 2400000, 22400)])
def test_withholding_json_to_filing_and_salary_ledger(
    tmp_path: Path, year: int, total: int, tax_due: int
) -> None:
    db = str(tmp_path / "fictional.db")

    def call(*args, data=None):
        if data is not None:
            args = (*args, "--input", write_json(tmp_path, data))
        completed = run_cli(*args)
        assert completed.returncode == 0, completed.stdout
        return json.loads(completed.stdout)

    raw = withholding_input(f"{year}-specific")
    checked = call("ledger", "ws-check", "--fiscal-year", str(year), data=raw)
    assert checked["validation"]["calculated_total"] == total
    assert checked["validation"]["ready_for_calculation"] is True
    call("ledger", "init", "--db-path", db, "--fiscal-year", str(year))
    saved = call("ledger", "ws-save", "--db-path", db, "--fiscal-year", str(year), data=raw)
    slip = call("ledger", "ws-list", "--db-path", db, "--fiscal-year", str(year))["slips"][0]
    assert slip["validation"]["ready_for_calculation"] is True
    params = {
        "fiscal_year": year,
        "calculation_mode": "filing",
        "minimum_tax_income_complete": True,
        "salary_income": slip["payment_amount"],
        "withheld_tax": slip["withheld_tax"],
        "social_insurance": 750000,
        "misc_income": 440000,
        "blue_return_deduction": 0,
        "dependents": [
            {
                "name": "架空親族",
                "relationship": "子",
                "birth_date": f"{year - 22}-06-01",
                "income": 880000,
                "cohabiting": True,
                "other_taxpayer_dependent": False,
            }
        ],
    }
    result = call("tax", "calc-income", data=params)
    assert result["salary_income_after_deduction"] == 3560000
    assert result["total_income_deductions"] == total
    assert result["tax_due"] == tax_due
    evidence = {
        "slip_ids": [saved["withholding_slip_id"]],
        "selection_confirmed": True,
        "additional_social_insurance": 0,
    }
    with sqlite3.connect(db) as conn:
        before = list(conn.iterdump())
    sanity = call(
        "tax",
        "sanity-check",
        "--db-path",
        db,
        data={"input": params, "result": result, "salary_evidence": evidence},
    )
    assert sanity["passed"] is True
    assert sanity["error_count"] == sanity["warning_count"] == 0
    with sqlite3.connect(db) as conn:
        assert list(conn.iterdump()) == before
    bad = {**raw, "social_insurance": 610000}
    completed = run_cli(
        "ledger",
        "ws-save",
        "--db-path",
        db,
        "--fiscal-year",
        str(year),
        "--input",
        write_json(tmp_path, bad),
    )
    assert completed.returncode == 1
    assert json.loads(completed.stdout)["code"] == "WS_DEDUCTION_TOTAL_MISMATCH"
