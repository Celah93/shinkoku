"""詳細フラグと年次文脈は明示入力だけに効き、従来の出力を変えない。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers.depreciation import annual_context, depreciation_input
from tests.scripts.conftest import run_cli, write_json


@pytest.mark.parametrize("details", [False, True])
def test_optional_details_and_annual_context(tmp_path: Path, details: bool) -> None:
    payload = depreciation_input(annual_context=annual_context())
    args = ("--details",) if details else ()
    result = run_cli("tax", "calc-depreciation", *args, "--input", write_json(tmp_path, payload))
    assert result.returncode == 0, result.stdout
    output = json.loads(result.stdout)
    if details:
        assert output["expense_amount"] == output["ordinary_amount"] == 46875
        assert output["closing_book_value"] == 203125
        assert output["memo_value_constraint_applied"] is True
    else:
        assert output == {
            "method": "straight_line",
            "depreciation_amount": 46875,
            "acquisition_cost": 250000,
            "useful_life": 4,
            "business_use_ratio": 100,
            "months": 9,
        }


def test_details_without_context_does_not_invent_an_annual_balance(tmp_path: Path) -> None:
    result = run_cli(
        "tax",
        "calc-depreciation",
        "--details",
        "--input",
        write_json(tmp_path, depreciation_input()),
    )
    assert result.returncode == 0, result.stdout
    output = json.loads(result.stdout)
    assert output["expense_amount"] == 62500
    assert output["closing_book_value"] is None
    assert output["memo_value_constraint_applied"] is False


def test_explicit_wrong_months_are_json_error(tmp_path: Path) -> None:
    data = depreciation_input(months=12, annual_context=annual_context())
    result = run_cli("tax", "calc-depreciation", "--details", "--input", write_json(tmp_path, data))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error" and "一致しません" in output["message"]


def test_small_asset_details_keep_the_existing_selection_output(tmp_path: Path) -> None:
    data = {
        "method": "small_asset_treatment",
        "acquisition_date": "2026-04-01",
        "placed_in_service_date": "2026-04-01",
        "acquisition_cost": 150001,
        "useful_life": 4,
        "is_lending_use": False,
        "is_main_business_lending": False,
        "special_cap_used": 0,
    }
    path = write_json(tmp_path, data)
    old = run_cli("tax", "calc-depreciation", "--input", path)
    details = run_cli("tax", "calc-depreciation", "--details", "--input", path)
    assert old.returncode == details.returncode == 0
    output = json.loads(details.stdout)
    assert output["selection"] == json.loads(old.stdout)
    assert output["calculations"]["pooled_depreciation"]["expense_amount"] == 50001
    invalid = write_json(tmp_path, {**data, "annual_context": annual_context()}, "unsupported.json")
    refused = run_cli("tax", "calc-depreciation", "--details", "--input", invalid)
    assert refused.returncode == 1 and "未対応" in json.loads(refused.stdout)["message"]
