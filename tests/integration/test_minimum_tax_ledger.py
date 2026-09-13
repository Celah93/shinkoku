"""架空PL・寄附入力から高所得特例を含む計算・検算まで通す。"""

from __future__ import annotations

import json
from pathlib import Path

from tests.integration.test_ledger_to_tax_calculation import _seed_book
from tests.scripts.conftest import run_cli, write_json


def test_ledger_to_minimum_tax_filing(tmp_path: Path) -> None:
    pl = _seed_book(str(tmp_path / "fictional-high-income.db"), 2027, 2000000000, 0)
    data = dict(
        fiscal_year=2027,
        business_revenue=pl["total_revenue"],
        business_expenses=pl["total_expense"],
        blue_return_deduction=0,
        furusato_nozei=800000000,
        calculation_mode="filing",
        minimum_tax_income_complete=True,
    )
    response = run_cli("tax", "calc-income", "--input", write_json(tmp_path, data))
    assert response.returncode == 0, response.stdout
    result = json.loads(response.stdout)
    assert result["minimum_tax_detail"]["base_income_amount"] == 2000000000
    assert result["minimum_tax_additional_income_tax"] == 4055798
    assert result["tax_due"] == 550585100
    check = run_cli(
        "tax", "sanity-check", "--input", write_json(tmp_path, {"input": data, "result": result})
    )
    assert check.returncode == 0, check.stdout
    assert json.loads(check.stdout)["passed"]
