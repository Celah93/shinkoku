"""Tests for import CLI."""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import run_cli


def run_import(*args: str):
    return run_cli("import", *args)


# --- csv ---


def test_import_csv(tmp_path: Path):
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("日付,摘要,金額\n2025-01-15,テスト,1000\n", encoding="utf-8")
    result = run_import("csv", "--file-path", str(csv_file))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert len(output["candidates"]) == 1
    assert output["candidates"][0]["amount"] == 1000


def test_import_csv_cp932_with_extension_chars_parses(tmp_path: Path):
    """CP932拡張文字を含む摘要を文字化けさせずに取り込む。"""
    csv_file = tmp_path / "cp932-extension.csv"
    csv_file.write_bytes("日付,摘要,金額\n2025/06/01,店舗①㈱髙﨑,1000\n".encode("cp932"))

    result = run_import("csv", "--file-path", str(csv_file))

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["encoding"] == "cp932"
    assert output["candidates"][0]["description"] == "店舗①㈱髙﨑"
    assert output["candidates"][0]["amount"] == 1000


def test_import_csv_utf8_bom_header_has_no_feff(tmp_path: Path):
    """BOM付きUTF-8の先頭ヘッダへU+FEFFを残さない。"""
    csv_file = tmp_path / "utf8-bom.csv"
    csv_file.write_bytes(
        b"\xef\xbb\xbf" + "日付,摘要,金額\n2025/06/01,BOM店,1000\n".encode("utf-8")
    )

    result = run_import("csv", "--file-path", str(csv_file))

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["encoding"] == "utf-8-sig"
    original_data = output["candidates"][0]["original_data"]
    assert "日付" in original_data
    assert "\ufeff日付" not in original_data


def test_import_csv_cp932_fullwidth_minus_amount_parses_negative(tmp_path: Path):
    """CP932の全角マイナスをFix #04の正規化へつなぎ、負数として取り込む。"""
    csv_file = tmp_path / "cp932-negative.csv"
    csv_file.write_bytes("日付,摘要,金額\n2025/06/01,返金,－1000\n".encode("cp932"))

    result = run_import("csv", "--file-path", str(csv_file))

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["encoding"] == "cp932"
    assert output["candidates"][0]["amount"] == -1000


def test_import_csv_negative_triangle_amount_kept_negative(tmp_path: Path):
    csv_file = tmp_path / "negative.csv"
    csv_file.write_text(
        '日付,摘要,金額\n2025-01-15,返金,"▲1,000"\n',
        encoding="utf-8",
    )
    result = run_import("csv", "--file-path", str(csv_file))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["candidates"][0]["amount"] == -1_000


def test_import_csv_unparseable_amount_goes_to_skipped_rows(tmp_path: Path):
    csv_file = tmp_path / "unparseable.csv"
    csv_file.write_text(
        '日付,摘要,金額\n2025-01-15,書式崩れ,"12,34"\n',
        encoding="utf-8",
    )
    result = run_import("csv", "--file-path", str(csv_file))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["candidates"] == []
    assert output["total_rows"] == 0
    assert output["skipped_rows"] == [2]


def test_import_csv_file_not_found(tmp_path: Path):
    result = run_import("csv", "--file-path", str(tmp_path / "nonexistent.csv"))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


def test_import_csv_empty(tmp_path: Path):
    csv_file = tmp_path / "empty.csv"
    csv_file.write_text("", encoding="utf-8")
    result = run_import("csv", "--file-path", str(csv_file))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["total_rows"] == 0


# --- receipt ---


def test_import_receipt(tmp_path: Path):
    img = tmp_path / "receipt.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0dummy")
    result = run_import("receipt", "--file-path", str(img))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["file_path"] == str(img)
    assert output["date"] is None


def test_import_receipt_file_not_found(tmp_path: Path):
    result = run_import("receipt", "--file-path", str(tmp_path / "nonexistent.jpg"))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


# --- invoice ---


def test_import_invoice(tmp_path: Path):
    # テキストファイルで代用（pdfplumber は空文字を返す）
    f = tmp_path / "invoice.txt"
    f.write_text("dummy invoice", encoding="utf-8")
    result = run_import("invoice", "--file-path", str(f))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"


def test_import_invoice_not_found(tmp_path: Path):
    result = run_import("invoice", "--file-path", str(tmp_path / "missing.pdf"))
    assert result.returncode == 1


def test_import_invoice_image_file(tmp_path: Path):
    img = tmp_path / "invoice.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0dummy")
    result = run_import("invoice", "--file-path", str(img))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["extracted_text"] == ""


# --- withholding ---


def test_import_withholding(tmp_path: Path):
    f = tmp_path / "withholding.txt"
    f.write_text("dummy", encoding="utf-8")
    result = run_import("withholding", "--file-path", str(f))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"


def test_import_withholding_not_found(tmp_path: Path):
    result = run_import("withholding", "--file-path", str(tmp_path / "missing.pdf"))
    assert result.returncode == 1


def test_import_withholding_image_file(tmp_path: Path):
    img = tmp_path / "withholding.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\ndummy")
    result = run_import("withholding", "--file-path", str(img))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["extracted_text"] == ""


# --- furusato-receipt ---


def test_import_furusato_receipt(tmp_path: Path):
    f = tmp_path / "furusato.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0dummy")
    result = run_import("furusato-receipt", "--file-path", str(f))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["municipality_name"] is None


def test_import_furusato_receipt_not_found(tmp_path: Path):
    result = run_import("furusato-receipt", "--file-path", str(tmp_path / "missing.jpg"))
    assert result.returncode == 1


# --- payment-statement ---


def test_import_payment_statement(tmp_path: Path):
    f = tmp_path / "statement.txt"
    f.write_text("dummy payment statement", encoding="utf-8")
    result = run_import("payment-statement", "--file-path", str(f))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"


def test_import_payment_statement_not_found(tmp_path: Path):
    result = run_import("payment-statement", "--file-path", str(tmp_path / "missing.pdf"))
    assert result.returncode == 1


# --- deduction-certificate ---


def test_import_deduction_certificate(tmp_path: Path):
    f = tmp_path / "cert.txt"
    f.write_text("dummy certificate", encoding="utf-8")
    result = run_import("deduction-certificate", "--file-path", str(f))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["certificate_type"] is None


def test_import_deduction_certificate_not_found(tmp_path: Path):
    result = run_import("deduction-certificate", "--file-path", str(tmp_path / "missing.pdf"))
    assert result.returncode == 1


# --- check-imported ---


def test_check_imported_not_imported(db_path: str, tmp_path: Path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("日付,摘要,金額\n2025-01-15,テスト,1000\n", encoding="utf-8")
    result = run_import(
        "check-imported",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(csv_file),
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "not_imported"


def test_check_imported_already_imported(db_path: str, tmp_path: Path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("日付,摘要,金額\n2025-01-15,テスト,1000\n", encoding="utf-8")
    # まず record-source で記録
    run_import(
        "record-source",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(csv_file),
        "--row-count",
        "1",
    )
    # check-imported で確認
    result = run_import(
        "check-imported",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(csv_file),
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "already_imported"


def test_check_imported_file_not_found(db_path: str, tmp_path: Path):
    result = run_import(
        "check-imported",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(tmp_path / "missing.csv"),
    )
    assert result.returncode == 1


# --- record-source ---


def test_record_source(db_path: str, tmp_path: Path):
    csv_file = tmp_path / "data.csv"
    csv_file.write_text("test data", encoding="utf-8")
    result = run_import(
        "record-source",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(csv_file),
        "--row-count",
        "5",
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["import_source_id"] >= 1


def test_record_source_file_not_found(db_path: str, tmp_path: Path):
    result = run_import(
        "record-source",
        "--db-path",
        db_path,
        "--fiscal-year",
        "2025",
        "--file-path",
        str(tmp_path / "missing.csv"),
    )
    assert result.returncode == 1


# --- no subcommand ---


def test_no_subcommand():
    result = run_import()
    assert result.returncode == 1
