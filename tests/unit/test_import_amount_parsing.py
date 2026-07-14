"""Tests for CSV amount parsing."""

from __future__ import annotations

import pytest

from shinkoku.tools.import_data import _parse_amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("▲1,234", -1_234),
        ("△5,000", -5_000),
        ("－2,000", -2_000),
        ("−1,000", -1_000),
        ("-3,000", -3_000),
        ("(1,234)", -1_234),
        ("（１，２３４）", -1_234),
        ("▲ 1,234", -1_234),
        ("▲¥1,234", -1_234),
    ],
)
def test_parse_amount_accepts_supported_negative_formats(value: str, expected: int) -> None:
    assert _parse_amount(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1234", 1_234),
        ("１２３４", 1_234),
        ("¥1,000", 1_000),
        ("\\1,000", 1_000),
        ("1,234円", 1_234),
        ("¥1,234円", 1_234),
        ("1,234.00", 1_234),
        ("1,234,567", 1_234_567),
        ("0", 0),
    ],
)
def test_parse_amount_accepts_supported_positive_formats(value: str, expected: int) -> None:
    assert _parse_amount(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "1,234.56",
        "1.5",
        "備考123",
        "1円2",
        "1¥2",
        "¥1¥2",
        "1,,234",
        "12,34",
        ",123",
        "123,",
        "▲-1,234",
        "(-1,234)",
        "1,234円円",
        "円1,234",
        "¥-1,234",
        "1,000-",
        "",
        "-",
    ],
)
def test_parse_amount_rejects_ambiguous_or_malformed_formats(value: str) -> None:
    assert _parse_amount(value) is None
