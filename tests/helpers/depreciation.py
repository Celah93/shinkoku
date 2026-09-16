"""償却計算用の確認済み架空事実。金額の期待値は含めない。"""

from __future__ import annotations


def annual_context(**overrides: object) -> dict:
    return {
        "fiscal_year": 2026,
        "acquisition_date": "2026-04-01",
        "placed_in_service_date": "2026-04-01",
        "opening_accumulated_depreciation": 0,
        "asset_class": "tangible",
        "book_basis": "full_cost_direct",
        "prior_private_use": False,
        "additional_depreciation_applicable": False,
        "basis_confirmed": True,
        "annual_facts_confirmed": True,
        **overrides,
    }


def depreciation_input(**overrides: object) -> dict:
    return {
        "method": "straight_line",
        "acquisition_cost": 250000,
        "useful_life": 4,
        "business_use_ratio": 100,
        **overrides,
    }
