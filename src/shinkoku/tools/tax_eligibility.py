"""青色控除とインボイス特例の適用判定。確認済み事実と不明を区別する。"""

from __future__ import annotations

from typing import Literal

from shinkoku.models import (
    BlueReturnEligibilityFacts,
    InvoiceSpecialEligibilityFacts,
    TaxEligibilityCheck,
)
from shinkoku.tax_constants import SPECIAL_30PCT_YEARS


class _Checks:
    def __init__(self) -> None:
        self.missing: list[str] = []
        self.failures: list[str] = []

    def require(self, field: str, value: object, expected: object) -> None:
        if value is None:
            self.missing.append(field)
        elif value != expected:
            self.failures.append(f"{field}: {expected!r} の要件を満たしていません")

    def any_path(self, label: str, paths: list[dict[str, bool | None]]) -> None:
        if any(all(value is True for value in path.values()) for path in paths):
            return
        possible = [path for path in paths if not any(value is False for value in path.values())]
        if not possible:
            self.failures.append(f"{label}: いずれの要件も満たしていません")
            return
        for path in possible:
            self.missing.extend(field for field, value in path.items() if value is None)

    def result(
        self,
        scheme: Literal["blue_return", "special_20pct", "special_30pct"],
        fiscal_year: int,
    ) -> TaxEligibilityCheck:
        status: Literal["eligible", "ineligible", "indeterminate"] = "eligible"
        if self.failures:
            status = "ineligible"
        elif self.missing:
            status = "indeterminate"
        return TaxEligibilityCheck(
            scheme=scheme,
            fiscal_year=fiscal_year,
            status=status,
            missing_fields=sorted(set(self.missing)),
            reasons=self.failures,
        )


def check_blue_return_eligibility(
    fiscal_year: int,
    requested_deduction: int,
    facts: BlueReturnEligibilityFacts | None,
) -> TaxEligibilityCheck:
    """控除の申告要件を判定する。利益による上限計算や申告の承認は行わない。

    根拠: 国税庁No.2072、2026年8月の75万円控除リーフレット。
    保存要件のフラグは、優良帳簿の全要件・必要な届出を確認した値を渡す。
    """
    if type(fiscal_year) is not int or type(requested_deduction) is not int:
        raise ValueError("fiscal_year と requested_deduction は整数で指定してください")
    if fiscal_year not in (2025, 2026, 2027):
        return TaxEligibilityCheck(
            scheme="blue_return",
            fiscal_year=fiscal_year,
            status="unsupported",
            reasons=["この年分の青色申告特別控除の要件判定は未対応です"],
        )
    if requested_deduction == 0:
        return TaxEligibilityCheck(
            scheme="blue_return", fiscal_year=fiscal_year, status="not_applicable"
        )
    maximum = 750_000 if fiscal_year == 2027 else 650_000
    if requested_deduction < 0 or requested_deduction > maximum:
        return TaxEligibilityCheck(
            scheme="blue_return",
            fiscal_year=fiscal_year,
            status="ineligible",
            reasons=[f"この年分の控除額は0円以上{maximum:,}円以下です"],
        )

    facts = facts or BlueReturnEligibilityFacts()
    checks = _Checks()
    checks.require("blue_return_approved", facts.blue_return_approved, True)
    checks.require("eligible_business_income", facts.eligible_business_income, True)

    if requested_deduction <= 100_000:
        if fiscal_year == 2027:
            if facts.bookkeeping is None:
                checks.missing.append("bookkeeping")
            elif facts.bookkeeping == "simple":
                revenue = facts.prior_prior_year_business_revenue
                if revenue is None:
                    checks.missing.append("prior_prior_year_business_revenue")
                elif revenue > 10_000_000:
                    # 現金主義特例との併用関係は、この資料だけで適格と断定しない。
                    if facts.cash_basis_special is not False:
                        return TaxEligibilityCheck(
                            scheme="blue_return",
                            fiscal_year=fiscal_year,
                            status="unsupported",
                            reasons=[
                                "簡易記帳・収入1,000万円超と現金主義特例の関係は追加確認が必要です"
                            ],
                        )
                    checks.failures.append("簡易記帳で前々年の事業収入が1,000万円を超えています")
        return checks.result("blue_return", fiscal_year)

    checks.require("bookkeeping", facts.bookkeeping, "double_entry")
    checks.require("cash_basis_special", facts.cash_basis_special, False)
    checks.require("filing_within_deadline", facts.filing_within_deadline, True)
    checks.require("required_statements_included", facts.required_statements_included, True)
    checks.require("deduction_claim_recorded", facts.deduction_claim_recorded, True)

    books_path = {
        "qualified_electronic_books": facts.qualified_electronic_books,
        "electronic_books_notice_requirement_met": facts.electronic_books_notice_requirement_met,
    }
    if fiscal_year <= 2026 and requested_deduction > 550_000:
        checks.any_path(
            "65万円控除の電子申告又は優良帳簿",
            [
                {"etax_filing": facts.etax_filing},
                books_path,
            ],
        )
    elif fiscal_year == 2027:
        checks.require("etax_filing", facts.etax_filing, True)
        if requested_deduction > 650_000:
            checks.any_path(
                "75万円控除の保存・届出",
                [
                    books_path,
                    {
                        "digital_seamless_recordkeeping": facts.digital_seamless_recordkeeping,
                        "digital_notice_requirement_met": facts.digital_notice_requirement_met,
                    },
                ],
            )
    return checks.result("blue_return", fiscal_year)


def check_invoice_special_eligibility(
    fiscal_year: int,
    method: Literal["special_20pct", "special_30pct"],
    facts: InvoiceSpecialEligibilityFacts | None,
) -> TaxEligibilityCheck:
    """国内個人の暦年課税を対象に2割・3割特例の要件を判定する。

    除外事由のフラグは、その年分に制限が適用されるかを確認した結果。
    高額資産の取得歴があることだけでTrueにせず、適用期間等を確認する。
    """
    if method not in ("special_20pct", "special_30pct"):
        raise ValueError("method は special_20pct 又は special_30pct を指定してください")
    if type(fiscal_year) is not int:
        raise ValueError("fiscal_year は整数で指定してください")
    years = (2025, 2026) if method == "special_20pct" else SPECIAL_30PCT_YEARS
    if fiscal_year not in years:
        return TaxEligibilityCheck(
            scheme=method,
            fiscal_year=fiscal_year,
            status="unsupported",
            reasons=[f"この方式の要件判定に対応する年分は{list(years)}です"],
        )
    facts = facts or InvoiceSpecialEligibilityFacts()
    if facts.domestic_individual is False:
        return TaxEligibilityCheck(
            scheme=method,
            fiscal_year=fiscal_year,
            status="unsupported",
            reasons=["この判定は国内の個人事業者を対象とします"],
        )
    checks = _Checks()
    checks.require("domestic_individual", facts.domestic_individual, True)
    checks.require("invoice_registration_effective", facts.invoice_registration_effective, True)
    if (
        facts.invoice_registration_date is not None
        and facts.invoice_registration_date.year > fiscal_year
    ):
        checks.failures.append("invoice_registration_date が対象年分より後です")
    if facts.base_period_taxable_sales is None:
        checks.missing.append("base_period_taxable_sales")
    elif facts.base_period_taxable_sales > 10_000_000:
        checks.failures.append("基準期間の課税売上高が1,000万円を超えています")
    for field in (
        "specific_period_taxation_applies",
        "asset_tax_exemption_restriction",
        "other_tax_exemption_restriction",
        "shortened_tax_period",
    ):
        checks.require(field, getattr(facts, field), False)

    if facts.inheritance_taxation_applies is None:
        checks.missing.append("inheritance_taxation_applies")
    elif facts.inheritance_taxation_applies:
        if method == "special_30pct":
            return TaxEligibilityCheck(
                scheme=method,
                fiscal_year=fiscal_year,
                status="unsupported",
                reasons=["相続による免税制限と3割特例の例外は追加確認が必要です"],
            )
        if facts.inheritance_date is None:
            checks.missing.append("inheritance_date")
        if facts.invoice_registration_date is None:
            checks.missing.append("invoice_registration_date")
        if facts.inheritance_date is not None and facts.invoice_registration_date is not None:
            # Q&A問115: 相続のあった年に、登録が相続日以前なら、この事由だけで除外しない。
            if (
                facts.inheritance_date.year != fiscal_year
                or facts.invoice_registration_date > facts.inheritance_date
            ):
                checks.failures.append("相続による免税制限があり、登録日の例外を満たしていません")
    return checks.result(method, fiscal_year)


def enforce_tax_eligibility(
    check: TaxEligibilityCheck, calculation_mode: Literal["estimate", "filing"]
) -> None:
    """不適格は試算でも拒否し、申告用計算では未確認も拒否する。"""
    if check.status in ("eligible", "not_applicable"):
        return
    if check.status == "indeterminate" and calculation_mode == "estimate":
        return
    code = {
        "indeterminate": "TAX_ELIGIBILITY_UNCONFIRMED",
        "ineligible": "TAX_ELIGIBILITY_INELIGIBLE",
        "unsupported": "TAX_ELIGIBILITY_UNSUPPORTED",
    }[check.status]
    details = "; ".join(check.reasons)
    if check.missing_fields:
        details += " 未確認: " + ", ".join(check.missing_fields)
    raise ValueError(f"{code}: {check.scheme} ({check.fiscal_year}年分): {details}")
