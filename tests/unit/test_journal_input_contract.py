"""仕訳入力の列挙値がDBの既存CHECK制約と一致することを検証する。"""

from __future__ import annotations

import re
from typing import Literal, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError

from shinkoku.db import SCHEMA_PATH
from shinkoku.models import JournalEntry, JournalLine


def _schema_values(table: str, column: str) -> set[str]:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    table_match = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", schema, re.S)
    assert table_match is not None
    values = re.search(rf"{column} IN \((.*?)\)", table_match.group(1), re.S)
    assert values is not None
    return set(re.findall(r"'([^']+)'", values.group(1)))


def _journal() -> dict:
    return {
        "date": "2026-01-15",
        "lines": [
            {"side": "debit", "account_code": "5190", "amount": 1100},
            {"side": "credit", "account_code": "1002", "amount": 1100},
        ],
    }


@pytest.mark.parametrize(
    ("model", "table", "field"),
    [(JournalLine, "journal_lines", "tax_category"), (JournalEntry, "journals", "source")],
)
def test_journal_enum_matches_sql_check(model: type[BaseModel], table: str, field: str) -> None:
    options = get_args(model.model_fields[field].annotation)
    actual = {
        value for option in options if get_origin(option) is Literal for value in get_args(option)
    }

    assert actual == _schema_values(table, field)


@pytest.mark.parametrize("value", [None, *sorted(_schema_values("journal_lines", "tax_category"))])
def test_existing_tax_categories_remain_valid(value: str | None) -> None:
    line = {**_journal()["lines"][0], "tax_category": value}

    assert JournalLine.model_validate(line, strict=True).tax_category == value


@pytest.mark.parametrize("value", [None, *sorted(_schema_values("journals", "source"))])
def test_existing_sources_remain_valid(value: str | None) -> None:
    entry = {**_journal(), "source": value}

    assert JournalEntry.model_validate(entry, strict=True).source == value


@pytest.mark.parametrize(
    ("field", "value"),
    [("tax_category", "taxable"), ("tax_category", ""), ("source", "scenario_csv"), ("source", "")],
)
def test_invalid_journal_enum_is_rejected_with_allowed_values(field: str, value: str) -> None:
    data = _journal()
    if field == "tax_category":
        data["lines"][0][field] = value
    else:
        data[field] = value

    with pytest.raises(ValidationError) as caught:
        JournalEntry.model_validate(data, strict=True)

    table = "journal_lines" if field == "tax_category" else "journals"
    assert all(allowed in str(caught.value) for allowed in _schema_values(table, field))
