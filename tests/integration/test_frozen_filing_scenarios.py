"""独立した凍結原簿から、実際のCLIで2人分の申告用計算とDB照合まで通す。"""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import pytest
import yaml

from shinkoku.db import get_connection
from tests.scripts.conftest import run_cli, write_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "scenarios"
YEAR = 2026


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_subset(expected: Any, actual: Any) -> None:
    """DBが付加するID等を除き、入力の全値と型が読戻しに残ることを確かめる。"""
    assert type(actual) is type(expected), (expected, actual)
    if isinstance(expected, dict):
        for key, value in expected.items():
            _assert_subset(value, actual[key])
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for want, got in zip(expected, actual, strict=True):
            _assert_subset(want, got)
    else:
        assert actual == expected


class ScenarioCLI:
    """run_cliを使い、テスト用ディレクトリに再現用の入出力と所要時間を残す。"""

    def __init__(self, tmp_path: Path) -> None:
        self.root = tmp_path
        self.db_path = str(tmp_path / "fictional-books.db")
        self.calls: list[dict] = []

    def call(self, *args: str, data: Any = None, exit_code: int = 0) -> dict:
        name = f"{len(self.calls) + 1:03d}-{args[0]}-{args[1]}"
        if data is not None:
            args = (*args, "--input", write_json(self.root, data, name + ".input.json"))
        started = perf_counter()
        response = run_cli(*args)
        self.calls.append(
            {
                "command": list(args),
                "seconds": perf_counter() - started,
                "exit_code": response.returncode,
            }
        )
        write_json(self.root, self.calls, "calls.json")
        assert response.returncode == exit_code, (args, response.stdout, response.stderr)
        result = json.loads(response.stdout)
        write_json(self.root, result, name + ".output.json")
        if exit_code == 0:
            assert result.get("status") not in {"error", "warning"}, result
        return result

    def ledger(self, command: str, *, data: Any = None, year: int = YEAR, **kwargs: Any) -> dict:
        return self.call(
            "ledger",
            command,
            "--db-path",
            self.db_path,
            "--fiscal-year",
            str(year),
            data=data,
            **kwargs,
        )

    def journals(self) -> dict:
        return self.call(
            "ledger", "search", "--db-path", self.db_path, data={"fiscal_year": YEAR, "limit": 1000}
        )

    def details(self, add: str, listing: str, key: str, records: list[dict]) -> list[dict]:
        for record in records:
            self.ledger(add, data=record)
        saved = self.ledger(listing)[key]
        # 日付の降順など、明細ごとの既存の表示順には依存しない。
        assert len(saved) == len(records)
        for record in records:
            matches = [row for row in saved if all(row[k] == v for k, v in record.items())]
            assert len(matches) == 1, (add, record, saved)
            _assert_subset(record, matches[0])
            assert matches[0]["fiscal_year"] == YEAR
        return saved


def _register_journals(cli: ScenarioCLI, entries: list[dict], provenance: dict) -> None:
    rejected = cli.ledger("journal-batch-add", data=entries, exit_code=1)
    assert rejected["status"] == "error" and "重複" in rejected["message"]
    assert cli.journals()["total_count"] == 0
    # 原簿の同日同額は別取引先への請求である。確認できた12組だけをforceの根拠にする。
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for entry in entries:
        lines = tuple(sorted((x["side"], x["account_code"], x["amount"]) for x in entry["lines"]))
        groups[(entry["date"], lines)].append(entry)
    duplicates = [group for group in groups.values() if len(group) > 1]
    assert len(duplicates) == provenance["duplicate_pairs"] == 12
    assert all(len(group) == len({x["counterparty"] for x in group}) == 2 for group in duplicates)
    saved = cli.call(
        "ledger",
        "journal-batch-add",
        "--db-path",
        cli.db_path,
        "--fiscal-year",
        str(YEAR),
        "--force",
        data=entries,
    )
    assert saved["count"] == len(entries) == provenance["daily_journal_count"]
    assert len([x for x in saved["warnings"] if x["match_type"] == "exact"]) == 12


def _taro_details(cli: ScenarioCLI, evidence: dict) -> dict:
    cli.details("rd-add", "rd-list", "details", [evidence["rent"]])
    social = cli.details("si-add", "si-list", "items", evidence["social_insurance"])
    policies = cli.details("ip-add", "ip-list", "items", evidence["insurance_policies"])
    medical = cli.details("me-add", "me-list", "details", evidence["medical"])
    bw = cli.details("bw-add", "bw-list", "details", evidence["payment_statements"])
    for record in evidence["donations"]:
        cli.call("furusato", "add", "--db-path", cli.db_path, data=record)
    donations = cli.call("furusato", "list", "--db-path", cli.db_path, "--fiscal-year", str(YEAR))
    _assert_subset(evidence["donations"], donations["donations"])
    return {
        "business_withheld_tax": sum(row["withholding_tax"] for row in bw),
        "social_insurance": sum(row["amount"] for row in social),
        "life_insurance_detail": {"general_new": sum(row["premium"] for row in policies)},
        "medical_expenses": sum(row["amount"] - row["insurance_reimbursement"] for row in medical),
        "ideco_contribution": evidence["ideco"]["annual_paid"],
        "furusato_nozei": sum(row["amount"] for row in donations["donations"]),
    }


def _jiro_details(cli: ScenarioCLI, evidence: dict) -> tuple[dict, dict]:
    salary = cli.details("ws-save", "ws-list", "slips", [evidence["salary_slip"]])[0]
    cli.ledger("spouse-set", data=evidence["spouse"])
    spouse = cli.ledger("spouse-get")["spouse"]
    _assert_subset(evidence["spouse"], spouse)
    dependent = cli.details("dep-add", "dep-list", "dependents", [evidence["dependent"]])[0]
    bw = cli.details("bw-add", "bw-list", "details", [evidence["business_withholding"]])
    pf = cli.details("pf-add", "pf-list", "fees", [evidence["professional_fee"]])
    loss = cli.details("lc-add", "lc-list", "details", [evidence["loss"]])
    donations = cli.details("don-add", "don-list", "items", [evidence["npo_donation"]])
    other = cli.details("oi-add", "oi-list", "items", [evidence["other_income"]])
    crypto = cli.details("ci-add", "ci-list", "records", [evidence["crypto"]])
    # DBのdate_of_birthを計算入力のbirth_dateへ対応付ける。金額や型は変換しない。
    relative = {key: value for key, value in dependent.items() if key in evidence["dependent"]}
    relative["birth_date"] = relative.pop("date_of_birth")
    return {
        "salary_income": salary["payment_amount"],
        "withheld_tax": salary["withheld_tax"],
        "social_insurance": salary["social_insurance"],
        "spouse_income": spouse["income"],
        "spouse_birth_date": spouse["date_of_birth"],
        "dependents": [relative],
        "donations": donations,
        "furusato_nozei": 0,
        # pfの源泉は税理士側の税額であり、本人の源泉へ合算しない。
        "business_withheld_tax": sum(row["withholding_tax"] for row in bw),
        "misc_income": sum(row["revenue"] - row["expenses"] for row in other)
        + sum(row["gains"] - row["expenses"] for row in crypto),
        "other_income_withheld_tax": sum(row["withheld_tax"] for row in other),
        "loss_carryforward_amount": sum(row["remaining"] for row in loss),
    }, {"spouse": spouse, "dependent": dependent, "pf": pf, "other": other}


def _resident_relative(row: dict) -> dict:
    return {
        "name": row["name"],
        "birth_date": row["date_of_birth"],
        "income": row["income"],
        "eligible": True,
        "cohabiting": row["cohabiting"],
        "other_taxpayer_dependent": row["other_taxpayer_dependent"],
    }


def _verify_book(
    cli: ScenarioCLI, entries: list[dict], journals: dict, bs: dict, monthly: int
) -> None:
    assert journals["total_count"] == len(journals["journals"]) == len(entries)
    by_description = {row["description"]: row for row in journals["journals"]}
    assert len(by_description) == len(entries)
    sales: dict[str, int] = defaultdict(int)
    for entry in entries:
        saved = by_description[entry["description"]]
        _assert_subset(entry, saved)
        assert saved["fiscal_year"] == YEAR
        debit = sum(x["amount"] for x in saved["lines"] if x["side"] == "debit")
        credit = sum(x["amount"] for x in saved["lines"] if x["side"] == "credit")
        assert debit == credit
        for line in saved["lines"]:
            if line["account_code"] == "4001":
                sales[saved["date"][:7]] += line["amount"] * (1 if line["side"] == "credit" else -1)
    assert dict(sales) == {f"{YEAR}-{month:02d}": monthly for month in range(1, 13)}
    assert bs["total_assets"] == bs["total_liabilities"] + bs["total_equity"]
    trial = cli.ledger("trial-balance")
    assert trial["total_debit"] == trial["total_credit"]
    with closing(get_connection(cli.db_path)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()


def _db_digest(db_path: str) -> str:
    with closing(get_connection(db_path)) as conn:
        return hashlib.sha256("\n".join(conn.iterdump()).encode()).hexdigest()


def _r6_negative(cli: ScenarioCLI, params: dict, pf: list[dict]) -> None:
    fee_withholding = sum(row["withheld_tax"] for row in pf)
    assert fee_withholding == 20420  # expected.md / 帳簿の検算・税理士報酬の預り源泉
    bad_input = {
        **params,
        "business_withheld_tax": params["business_withheld_tax"] + fee_withholding,
    }
    bad_result = cli.call("tax", "calc-income", data=bad_input)
    assert bad_result["tax_due"] == -229232  # 正しい還付208,812円に20,420円を誤加算した負例
    payload = {"input": bad_input, "result": bad_result}
    original_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    original_db = _db_digest(cli.db_path)
    check = cli.call("tax", "sanity-check", "--db-path", cli.db_path, data=payload)
    assert check["passed"] is False and check["error_count"] == 1
    assert "PROFESSIONAL_FEE_WITHHOLDING_MIXED" in [row["code"] for row in check["items"]]
    assert json.dumps(payload, ensure_ascii=False, sort_keys=True) == original_payload
    assert _read(Path(cli.calls[-1]["command"][-1])) == payload
    assert _db_digest(cli.db_path) == original_db


def _compare_expected(fixture: Path, observed: dict, count: int) -> None:
    expected = _read(fixture / "expected.json")
    assert len(expected) == len({row["path"] for row in expected}) == count
    errors = []
    for row in expected:
        assert (fixture / row["source_file"]).is_file() and row["source_item"]
        actual: Any = observed
        for key in row["path"].split("."):
            actual = actual[key]
        if actual != row["value"] or type(actual) is not type(row["value"]):
            errors.append({**row, "actual": actual})
    assert not errors, errors


@pytest.mark.parametrize("name,comparison_count", [("taro", 49), ("jiro", 45)])
def test_frozen_scenario_to_filing(tmp_path: Path, name: str, comparison_count: int) -> None:
    fixture = FIXTURES / name
    evidence = _read(fixture / "evidence.json")
    facts = _read(fixture / "eligibility-facts.json")
    provenance = _read(fixture / "provenance.json")
    entries = _read(fixture / "journal-entries.json")
    settlement = _read(fixture / "settlement-entries.json")
    config = _read(fixture / "config.json")
    cli = ScenarioCLI(tmp_path)
    config.update(db_path=cli.db_path, output_dir=str(tmp_path / "output"))
    config_path = tmp_path / "shinkoku.config.yaml"
    config_path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    profile = cli.call("profile", "--config", str(config_path))
    for section in ("family", "housing_loan", "estimated_tax"):
        _assert_subset(config[section], profile[section])
    assert profile["db_path"] == cli.db_path
    assert profile["housing_loan"]["applicable"] is False
    assert profile["estimated_tax"]["amount"] is not None
    assert not Path(cli.db_path).exists()
    cli.ledger("init")
    cli.ledger("ob-set-batch", data=evidence["opening_balances"])
    _register_journals(cli, entries, provenance)

    before = cli.ledger("pl")
    if name == "jiro":
        cli.details("inv-set", "inv-list", "records", evidence["inventory"])
        assert cli.ledger("pl") == before  # R7: 明細の保存だけではPLは変わらない。
        assert before["total_expense"] == 1018000  # 仕入240,000＋その他経費778,000
    else:
        pc = evidence["pc"]
        depreciation = cli.call(
            "tax",
            "calc-depreciation",
            data={
                key: pc[key]
                for key in (
                    "method",
                    "acquisition_cost",
                    "useful_life",
                    "business_use_ratio",
                    "months",
                )
            },
        )
        assert depreciation["depreciation_amount"] == 46875
        assert settlement[0]["lines"][0]["amount"] == depreciation["depreciation_amount"]
    adjusted = cli.ledger("journal-batch-add", data=settlement)
    assert adjusted["count"] == len(settlement) == provenance["settlement_journal_count"]
    pl, bs, journals = cli.ledger("pl"), cli.ledger("bs"), cli.journals()
    _verify_book(cli, entries + settlement, journals, bs, provenance["monthly_sales"])
    if name == "jiro":
        assert before["total_expense"] - pl["total_expense"] == 100000
        personal, details = _jiro_details(cli, evidence)
    else:
        personal, details = _taro_details(cli, evidence), {}

    params = {
        "fiscal_year": YEAR,
        "calculation_mode": "filing",
        "minimum_tax_income_complete": True,
        "business_revenue": pl["total_revenue"],
        "business_expenses": pl["total_expense"],
        "blue_return_deduction": profile["filing"]["blue_return_deduction"],
        "blue_return_eligibility": facts["blue_return"],
        "taxpayer_birth_date": profile["taxpayer"]["date_of_birth"],
        "housing_loan_balance": 0,
        "estimated_tax_payment": profile["estimated_tax"]["amount"],
        **personal,
    }
    income = cli.call("tax", "calc-income", data=params)
    assert income["calculation_mode"] == "filing"
    assert [x["status"] for x in income["eligibility_checks"]] == ["eligible"]

    tax_profile = {
        "taxpayer_status": "taxable",
        "consumption_tax_method": provenance["consumption_method"],
        "simplified_business_type": provenance["simplified_business_type"],
    }
    cli.ledger("fiscal-year-update", data=tax_profile)
    saved_profile = cli.ledger("fiscal-year-show")
    _assert_subset(tax_profile, saved_profile)
    sales = sum(
        line["amount"] * (1 if line["side"] == "credit" else -1)
        for journal in journals["journals"]
        for line in journal["lines"]
        if line["account_code"] == "4001" and line["tax_category"] == "taxable_10"
    )
    assert sales == pl["total_revenue"]
    # 二郎の原稿料は継続的な課税役務であり、所得明細から税込収入を加える。
    extra_sales = sum(row["revenue"] for row in details.get("other", []))
    consumption_params = {
        "fiscal_year": YEAR,
        "calculation_mode": "filing",
        "method": saved_profile["consumption_tax_method"],
        "simplified_business_type": saved_profile["simplified_business_type"],
        "taxable_sales_10": sales + extra_sales,
    }
    if name == "taro":
        consumption_params["invoice_special_eligibility"] = facts["invoice_special"]
    consumption = cli.call(
        "tax", "calc-consumption", "--db-path", cli.db_path, data=consumption_params
    )
    assert consumption["calculation_mode"] == "filing" and consumption["method_verified"] is True
    assert consumption["method"] == provenance["consumption_method"]

    resident_params = {
        "fiscal_year": YEAR,
        "income_scope": "comprehensive_only",
        "income_levy_taxable": True,
        "aggregate_income": income["aggregate_income_before_loss_carryforward"],
        "total_income": income["total_income"],
        "social_insurance": params["social_insurance"],
    }
    if name == "taro":
        resident_params.update(
            small_business_mutual_aid=params["ideco_contribution"],
            life_insurance=params["life_insurance_detail"],
            medical_method="medical",
            medical_expenses_net=params["medical_expenses"],
            spouse=None,
            dependents=[],
        )
    else:
        resident_params.update(
            spouse=_resident_relative(details["spouse"]),
            dependents=[_resident_relative(details["dependent"])],
            medical_method="none",
        )
        assert income["donation_selection"]["npo"] == "credit"
    resident = cli.call("tax", "calc-resident-tax-estimate", data=resident_params)
    limit = cli.call("tax", "calc-furusato-limit-detailed", data=resident["furusato_input"])
    assert resident["furusato_limit"] == limit
    summary = cli.call(
        "furusato",
        "summary",
        "--db-path",
        cli.db_path,
        "--fiscal-year",
        str(YEAR),
        "--estimated-limit",
        str(limit["estimated_limit"]),
    )
    assert summary["total_amount"] == params["furusato_nozei"]
    if name == "jiro":
        assert summary["total_amount"] == summary["deduction_amount"] == 0

    # 別年度の同額明細をCLIで追加して、DB照合が2026年のbw/pfだけを集計することを確かめる。
    cli.ledger("init", year=2025)
    bw_record = (
        evidence["business_withholding"] if name == "jiro" else evidence["payment_statements"][0]
    )
    cli.ledger("bw-add", year=2025, data=bw_record)
    if name == "jiro":
        cli.ledger("pf-add", year=2025, data=evidence["professional_fee"])
    sanity = cli.call(
        "tax", "sanity-check", "--db-path", cli.db_path, data={"input": params, "result": income}
    )
    assert sanity["passed"] is True
    assert sanity["error_count"] == sanity["warning_count"] == 0
    assert cli.ledger("pl") == pl

    expenses = {row["account_code"]: row["amount"] for row in pl["expenses"]}
    observed = {
        "pl": pl,
        "bs": bs,
        "journals": journals,
        "income_input": params,
        "income": income,
        "consumption": consumption,
        "resident": resident,
        "limit": limit,
        "summary": summary,
        "sanity": sanity,
        "expenses": expenses,
        "deductions": {
            row["type"]: row["amount"] for row in income["deductions_detail"]["income_deductions"]
        },
        "assets": {row["account_code"]: row["amount"] for row in bs["assets"]},
        "liabilities": {row["account_code"]: row["amount"] for row in bs["liabilities"]},
        "derived": {
            "liabilities_and_equity": bs["total_liabilities"] + bs["total_equity"],
            "other_business_expenses": pl["total_expense"] - expenses.get("5001", 0),
            "income_eligibility": [x["status"] for x in income["eligibility_checks"]],
            "consumption_eligibility": [x["status"] for x in consumption["eligibility_checks"]],
        },
    }
    _compare_expected(fixture, observed, comparison_count)
    if name == "jiro":
        _r6_negative(cli, params, details["pf"])
