"""2028〜2030年入居の単体計算、建築日の経過措置と立地の確認境界。"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from shinkoku.db import init_db
from shinkoku.models import HousingLoanCalculationInput, HousingLoanDetailInput, IncomeTaxInput
from shinkoku.tools.housing_loan import calc_housing_loan
from shinkoku.tools.ledger import ledger_add_housing_loan_detail, ledger_list_housing_loan_details
from shinkoku.tools.tax_calc import calc_income_tax


def _detail(**changes: object) -> dict:
    return (
        dict(
            housing_type="new_custom",
            housing_category="energy_efficient",
            move_in_date="2028-09-01",
            year_end_balance=60_000_000,
            is_special_target_individual=False,
            building_confirmation_date="2027-12-31",
            building_completion_date="2028-07-01",
            is_disaster_red_zone=False,
            total_floor_area=8000,
            residential_floor_area=8000,
            loan_term_years=30,
        )
        | changes
    )


def _input(details: list[dict] | None = None, **changes: object) -> HousingLoanCalculationInput:
    return HousingLoanCalculationInput.model_validate(
        dict(
            claim_fiscal_year=2028,
            aggregate_income=5_000_000,
            other_requirements_confirmed=True,
            housing_loan_details=details if details is not None else [_detail()],
        )
        | changes,
        strict=True,
    )


@pytest.mark.parametrize("year", [2028, 2029, 2030])
def test_new_energy_transition_has_ten_year_period(year: int) -> None:
    result = calc_housing_loan(
        _input([_detail(move_in_date=f"{year}-09-01")], claim_fiscal_year=year)
    )
    assert result.housing_loan_credit == 140_000
    entry = result.entries[0]
    assert (entry.balance_limit, entry.credit_period, entry.status) == (20_000_000, 10, "active")


@pytest.mark.parametrize(
    "confirmation,completion,expected",
    [
        ("2027-12-31", "2028-07-01", 140_000),
        ("2028-01-01", "2028-06-30", 140_000),
        ("2028-01-01", "2028-07-01", 0),
        (None, "2028-06-30", 140_000),
        ("2027-12-31", None, 140_000),
    ],
)
def test_both_routes_and_deadline_boundaries(
    confirmation: str | None, completion: str | None, expected: int
) -> None:
    result = calc_housing_loan(
        _input(
            [_detail(building_confirmation_date=confirmation, building_completion_date=completion)]
        )
    )
    assert result.housing_loan_credit == expected


@pytest.mark.parametrize(
    "confirmation,completion", [(None, None), ("2028-01-01", None), (None, "2028-07-01")]
)
def test_unknown_transition_is_not_false(confirmation: str | None, completion: str | None) -> None:
    with pytest.raises(ValueError, match="未確認"):
        calc_housing_loan(
            _input(
                [
                    _detail(
                        building_confirmation_date=confirmation, building_completion_date=completion
                    )
                ]
            )
        )


@pytest.mark.parametrize(
    "red_zone,rebuilding,expected",
    [
        (False, None, 140_000),
        (True, False, 0),
        (True, True, 140_000),
    ],
)
def test_red_zone_and_rebuilding(red_zone: bool, rebuilding: bool | None, expected: int) -> None:
    result = calc_housing_loan(
        _input([_detail(is_disaster_red_zone=red_zone, is_rebuilding=rebuilding)])
    )
    assert result.housing_loan_credit == expected


@pytest.mark.parametrize(
    "change",
    [{"is_disaster_red_zone": None}, {"is_disaster_red_zone": True, "is_rebuilding": None}],
)
def test_unknown_location_conditions_stop(change: dict) -> None:
    with pytest.raises(ValueError, match="確認"):
        calc_housing_loan(_input([_detail(**change)]))


@pytest.mark.parametrize("special,expected", [(False, 140_000), (True, 210_000)])
@pytest.mark.parametrize("kind", ["used", "broker_renovated_resale"])
def test_existing_energy_home_does_not_use_new_building_transition(
    kind: str, special: bool, expected: int
) -> None:
    result = calc_housing_loan(
        _input(
            [
                _detail(
                    housing_type=kind,
                    is_special_target_individual=special,
                    building_confirmation_date=None,
                    building_completion_date=None,
                    is_disaster_red_zone=True,
                    is_rebuilding=False,
                )
            ]
        )
    )
    assert result.housing_loan_credit == expected
    assert result.entries[0].credit_period == 13


@pytest.mark.parametrize(
    "kind,category,normal,special",
    [
        ("new_custom", "certified", 315_000, 350_000),
        ("new_subdivision", "zeh", 245_000, 315_000),
        ("broker_renovated_resale", "certified", 315_000, 350_000),
        ("used", "certified", 245_000, 315_000),
        ("used", "zeh", 245_000, 315_000),
        ("renovation", "certified", 140_000, 140_000),
    ],
)
def test_acquisition_categories_remain_distinct(
    kind: str, category: str, normal: int, special: int
) -> None:
    for status, expected in ((False, normal), (True, special)):
        result = calc_housing_loan(
            _input(
                [
                    _detail(
                        housing_type=kind,
                        housing_category=category,
                        is_special_target_individual=status,
                    )
                ]
            )
        )
        assert result.housing_loan_credit == expected


@pytest.mark.parametrize(
    "area,income,expected",
    [
        (3999, 5_000_000, 0),
        (4000, 10_000_000, 315_000),
        (4999, 10_000_001, 0),
        (5000, 10_000_001, 350_000),
        (5000, 20_000_000, 350_000),
        (5000, 20_000_001, 0),
    ],
)
def test_floor_area_and_income_gate(area: int, income: int, expected: int) -> None:
    result = calc_housing_loan(
        _input(
            [
                _detail(
                    housing_category="certified",
                    is_special_target_individual=True,
                    total_floor_area=area,
                    residential_floor_area=area,
                )
            ],
            aggregate_income=income,
        )
    )
    assert result.housing_loan_credit == expected


@pytest.mark.parametrize(
    "residential,term,expected",
    [(3999, 30, 0), (4000, 30, 140_000), (8000, 9, 0), (8000, 10, 140_000)],
)
def test_residential_share_and_loan_term(residential: int, term: int, expected: int) -> None:
    assert (
        calc_housing_loan(
            _input([_detail(residential_floor_area=residential, loan_term_years=term)])
        ).housing_loan_credit
        == expected
    )


@pytest.mark.parametrize("kind,last_year", [("new_custom", 2037), ("used", 2040)])
def test_last_claim_year_and_expiration(kind: str, last_year: int) -> None:
    details = [_detail(housing_type=kind)]
    assert (
        calc_housing_loan(_input(details, claim_fiscal_year=last_year)).housing_loan_credit
        == 140_000
    )
    expired = calc_housing_loan(_input(details, claim_fiscal_year=last_year + 1))
    assert expired.housing_loan_credit == 0
    assert expired.entries[0].status == "expired"


def test_household_derivation_for_future_year_does_not_use_income_tax_year_gate() -> None:
    data = _input(
        [_detail(housing_category="certified", is_special_target_individual=None)],
        dependents=[
            dict(
                name="子",
                birth_date="2010-01-02",
                relationship="子",
                income=620_000,
            )
        ],
    )
    assert calc_housing_loan(data).housing_loan_credit == 350_000
    data = _input(
        [_detail(housing_category="certified", is_special_target_individual=None)],
        dependents=[
            dict(
                name="子",
                birth_date="2010-01-01",
                relationship="子",
                income=620_000,
            )
        ],
    )
    assert calc_housing_loan(data).housing_loan_credit == 315_000


def test_dual_group_proration_with_mixed_periods_preserves_balance() -> None:
    details = [
        _detail(
            housing_type="used",
            housing_category="certified",
            dual_application_group="shared",
            cost_for_proration=30_000_000,
        ),
        _detail(
            housing_type="renovation",
            dual_application_group="shared",
            cost_for_proration=10_000_000,
        ),
    ]
    first = calc_housing_loan(_input(details))
    assert sum(e.prorated_balance for e in first.entries) == 60_000_000
    assert first.housing_loan_credit == 245_000
    later = calc_housing_loan(_input(details, claim_fiscal_year=2038))
    assert [e.status for e in later.entries] == ["active", "expired"]
    assert later.housing_loan_credit == 245_000


@pytest.mark.parametrize(
    "change,root",
    [
        ({"loan_term_years": None}, {}),
        ({"total_floor_area": 0}, {}),
        ({"residential_floor_area": 9000}, {}),
        ({"building_completion_date": "2028-10-01"}, {}),
        ({"move_in_date": "2031-01-01"}, {"claim_fiscal_year": 2031}),
        ({}, {"claim_fiscal_year": 2027}),
        ({}, {"other_requirements_confirmed": False}),
    ],
)
def test_unconfirmed_and_inconsistent_inputs_stop(change: dict, root: dict) -> None:
    with pytest.raises(ValueError):
        calc_housing_loan(_input([_detail(**change)], **root))


def test_invalid_dates_and_integer_coercion_rejected() -> None:
    for changes in (
        {"building_confirmation_date": "2027-02-30"},
        {"is_disaster_red_zone": "false"},
        {"year_end_balance": 1.2},
    ):
        with pytest.raises(ValidationError):
            _input([_detail(**changes)])


def test_annual_income_tax_does_not_open_2028() -> None:
    with pytest.raises(ValueError, match="未対応"):
        calc_income_tax(IncomeTaxInput(fiscal_year=2028, salary_income=5_000_000))


def test_python_api_also_rejects_nested_coercions_and_unknown_fields() -> None:
    params = dict(
        claim_fiscal_year=2028, aggregate_income=5_000_000, other_requirements_confirmed=True
    )
    for changes in ({"year_end_balance": "30000000"}, {"loan_term_years": True}, {"pre_r10": True}):
        with pytest.raises(ValidationError):
            HousingLoanCalculationInput(**params, housing_loan_details=[_detail(**changes)])


def test_evidence_round_trip_and_missing_fields_stay_unknown(tmp_path: Path) -> None:
    db = str(tmp_path / "housing.db")
    conn = init_db(db)
    conn.execute("INSERT INTO fiscal_years(year) VALUES (2028)")
    conn.commit()
    conn.close()
    saved = ledger_add_housing_loan_detail(
        db_path=db, fiscal_year=2028, detail=HousingLoanDetailInput(**_detail(is_rebuilding=False))
    )
    row = ledger_list_housing_loan_details(db_path=db, fiscal_year=2028)["details"][0]
    assert row["id"] == saved["housing_loan_detail_id"]
    assert row["building_confirmation_date"] == "2027-12-31"
    assert row["building_completion_date"] == "2028-07-01"
    assert row["is_disaster_red_zone"] is False and row["is_rebuilding"] is False
    assert row["loan_term_years"] == 30
    ledger_add_housing_loan_detail(
        db_path=db,
        fiscal_year=2028,
        detail=HousingLoanDetailInput(
            **_detail(
                building_confirmation_date=None,
                building_completion_date=None,
                is_disaster_red_zone=None,
                is_rebuilding=None,
                loan_term_years=None,
            )
        ),
    )
    row = ledger_list_housing_loan_details(db_path=db, fiscal_year=2028)["details"][1]
    for name in (
        "building_confirmation_date",
        "building_completion_date",
        "is_disaster_red_zone",
        "is_rebuilding",
        "loan_term_years",
    ):
        assert row[name] is None
