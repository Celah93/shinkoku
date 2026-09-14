"""計算機能ごとの対応年分。個別の税制定数の存在とは分けて管理する。"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal, Mapping

TaxCalculation = Literal[
    "income_tax",
    "income_deductions",
    "consumption_tax",
    "consumption_special_30pct",
    "furusato_limit",
    "minimum_income_tax",
    "resident_tax_estimate",
]


@dataclass(frozen=True)
class TaxYearSupport:
    """対象範囲内で計算を許可する年分。申告全体の適格性は別途確認する。"""

    label: str
    supported_years: frozenset[int]


# 機能ごとに制度一式と境界テストを確認してから、その機能の年分だけを追加する。
TAX_YEAR_SUPPORT: Final[Mapping[TaxCalculation, TaxYearSupport]] = MappingProxyType(
    {
        "income_tax": TaxYearSupport("所得税計算・検算", frozenset({2025, 2026, 2027})),
        "income_deductions": TaxYearSupport("所得税の控除集計", frozenset({2025, 2026, 2027})),
        "consumption_tax": TaxYearSupport("消費税計算", frozenset({2025, 2026})),
        "consumption_special_30pct": TaxYearSupport("消費税3割特例", frozenset({2027, 2028})),
        "furusato_limit": TaxYearSupport("ふるさと納税の上限推定", frozenset({2025, 2026, 2027})),
        "resident_tax_estimate": TaxYearSupport(
            "住民税控除・所得割の推定", frozenset({2025, 2026, 2027})
        ),
        "minimum_income_tax": TaxYearSupport(
            "特定の基準所得金額の課税特例", frozenset({2025, 2026, 2027})
        ),
    }
)


def require_supported_tax_year(fiscal_year: int, calculation: TaxCalculation) -> None:
    """未対応年分を旧制度で計算せず、既存CLI契約のValueErrorとして返す。"""
    support = TAX_YEAR_SUPPORT[calculation]
    if type(fiscal_year) is not int or fiscal_year not in support.supported_years:
        raise ValueError(
            f"fiscal_year={fiscal_year} は未対応です（{support.label}）。"
            f"対応年分: {sorted(support.supported_years)}。"
            "未対応年分の制度を旧制度で計算しないため、処理を停止しました。"
        )


def require_supported_consumption_tax_year(fiscal_year: int, method: str) -> None:
    """完成した方式だけをその対象年に許可し、他方式の年分を一緒に開放しない。"""
    calculation: TaxCalculation = (
        "consumption_special_30pct" if method == "special_30pct" else "consumption_tax"
    )
    require_supported_tax_year(fiscal_year, calculation)
