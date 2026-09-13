"""架空の帳簿→決算値→申告用CLI計算→検算を通す。ブラウザ検証は含めない。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from shinkoku.models import FiscalYearTaxProfileUpdate, JournalEntry, JournalLine
from shinkoku.tools.ledger import (
    ledger_add_journal,
    ledger_init,
    ledger_pl,
    ledger_update_fiscal_year_tax_profile,
)
from tests.helpers.tax_eligibility import verified_blue_facts, verified_invoice_facts
from tests.scripts.conftest import run_cli, write_json


def _seed_book(db_path: str, year: int, revenue: int, expense: int) -> dict:
    assert ledger_init(db_path=db_path, fiscal_year=year)["status"] == "ok"
    for month, debit, credit, amount in [
        (2, "1002", "4001", revenue),
        (3, "5200", "1002", expense),
    ]:
        if not amount:
            continue
        result = ledger_add_journal(
            db_path=db_path,
            fiscal_year=year,
            entry=JournalEntry(
                date=f"{year}-{month:02d}-01",
                description="架空の結合テスト取引",
                lines=[
                    JournalLine(side="debit", account_code=debit, amount=amount),
                    JournalLine(side="credit", account_code=credit, amount=amount),
                ],
            ),
        )
        assert result["status"] == "ok", result
    return ledger_pl(db_path=db_path, fiscal_year=year)


@pytest.mark.parametrize(
    "year,revenue,expense,salary,withheld,expected_tax",
    [
        (2025, 3000000, 1000000, 0, 0, 23900),
        (2026, 3000000, 1000000, 0, 0, 15800),
        (2026, 3000000, 1000000, 5000000, 0, 429300),
        (2026, 3000000, 1000000, 5000000, 600000, -170670),
        (2026, 0, 0, 5000000, 200000, -42256),
        (2027, 3000000, 1000000, 0, 0, 15800),
        (2027, 3000000, 1000000, 5000000, 600000, -170670),
        (2027, 0, 0, 5000000, 200000, -42256),
    ],
)
def test_book_to_income_filing_and_sanity_check(
    tmp_path: Path,
    year: int,
    revenue: int,
    expense: int,
    salary: int,
    withheld: int,
    expected_tax: int,
) -> None:
    db_path = str(tmp_path / "fictional-books.db")
    pl = _seed_book(db_path, year, revenue, expense)
    assert (pl["total_revenue"], pl["total_expense"], pl["net_income"]) == (
        revenue,
        expense,
        revenue - expense,
    )
    # 他の所得・控除はないという架空ケース。PLと外部の給与・要件資料を明示して結合する。
    params = {
        "fiscal_year": year,
        "business_revenue": pl["total_revenue"],
        "business_expenses": pl["total_expense"],
        "salary_income": salary,
        "withheld_tax": withheld,
        "blue_return_deduction": 650000 if revenue else 0,
        "calculation_mode": "filing",
        "blue_return_eligibility": verified_blue_facts().model_dump(mode="json")
        if revenue
        else None,
    }
    calculation = run_cli("tax", "calc-income", "--input", write_json(tmp_path, params))
    assert calculation.returncode == 0, calculation.stdout
    result = json.loads(calculation.stdout)
    assert result["tax_due"] == expected_tax
    assert result["calculation_mode"] == "filing"
    assert result["eligibility_checks"][0]["status"] == (
        "eligible" if revenue else "not_applicable"
    )
    check_path = write_json(tmp_path, {"input": params, "result": result}, "sanity.json")
    check = run_cli("tax", "sanity-check", "--input", check_path)
    assert check.returncode == 0, check.stdout
    assert json.loads(check.stdout)["passed"] is True
    assert ledger_pl(db_path=db_path, fiscal_year=year) == pl


@pytest.mark.parametrize(
    "year,method,total",
    [
        (2026, "special_20pct", 20000),
        (2027, "special_30pct", 30000),
        (2028, "special_30pct", 30000),
    ],
)
@pytest.mark.parametrize("interim", [False, True])
def test_book_to_consumption_filing_with_profile_readback(
    tmp_path: Path, year: int, method: str, total: int, interim: bool
) -> None:
    db_path = str(tmp_path / "fictional-consumption.db")
    # 全売上が標準税率10%、税込経理の架空ケース。汎用の税区分集計器ではない。
    pl = _seed_book(db_path, year, 1_100_000, 0)
    updated = ledger_update_fiscal_year_tax_profile(
        db_path=db_path,
        fiscal_year=year,
        update=FiscalYearTaxProfileUpdate(taxpayer_status="taxable", consumption_tax_method=method),
    )
    assert updated["status"] == "ok"
    params = {
        "fiscal_year": year,
        "method": method,
        "taxable_sales_10": pl["total_revenue"],
        "calculation_mode": "filing",
        "invoice_special_eligibility": verified_invoice_facts().model_dump(mode="json"),
    }
    if interim:
        params.update(interim_payment=10000, local_interim_payment=2000)
        total -= 12000
    result = run_cli(
        "tax", "calc-consumption", "--input", write_json(tmp_path, params), "--db-path", db_path
    )
    assert result.returncode == 0, result.stdout
    output = json.loads(result.stdout)
    assert output["total_due"] == total
    assert output["method_verified"] is True
    assert output["eligibility_checks"][0]["status"] == "eligible"
    assert output["local_interim_payment"] == (2000 if interim else 0)
    assert ledger_pl(db_path=db_path, fiscal_year=year) == pl
