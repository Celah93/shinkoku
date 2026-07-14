"""Tests for CSV encoding detection."""

from __future__ import annotations

from pathlib import Path

from shinkoku.tools.import_data import _detect_encoding


def test_detect_encoding_cp932_extension_chars_returns_cp932(tmp_path: Path) -> None:
    """CP932拡張文字を含むファイルはcp932と判定する。"""
    csv_file = tmp_path / "cp932-extension.csv"
    csv_file.write_bytes("日付,摘要,金額\n2025/06/01,店舗①㈱髙﨑,1000\n".encode("cp932"))

    assert _detect_encoding(str(csv_file)) == "cp932"


def test_detect_encoding_pure_shift_jis_returns_cp932(tmp_path: Path) -> None:
    """純正Shift_JISファイルもcp932として読める。"""
    csv_file = tmp_path / "shift-jis.csv"
    csv_file.write_bytes("日付,摘要,金額\n2025/06/01,通常店,1000\n".encode("shift_jis"))

    assert _detect_encoding(str(csv_file)) == "cp932"


def test_detect_encoding_plain_utf8_returns_utf8(tmp_path: Path) -> None:
    """通常のUTF-8ファイルはutf-8と判定する。"""
    csv_file = tmp_path / "utf8.csv"
    csv_file.write_bytes("日付,摘要,金額\n2025/06/01,通常店,1000\n".encode("utf-8"))

    assert _detect_encoding(str(csv_file)) == "utf-8"


def test_detect_encoding_utf8_with_bom_returns_utf8_sig(tmp_path: Path) -> None:
    """BOM付きUTF-8ファイルはutf-8-sigと判定する。"""
    csv_file = tmp_path / "utf8-bom.csv"
    csv_file.write_bytes(b"\xef\xbb\xbf" + "日付,摘要,金額\n".encode("utf-8"))

    assert _detect_encoding(str(csv_file)) == "utf-8-sig"
