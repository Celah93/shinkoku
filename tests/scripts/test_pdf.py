"""CLI integration tests for pdf subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from .conftest import run_cli


def run_pdf(*args: str):
    return run_cli("pdf", *args)


# --- extract-text ---


def test_extract_text_file_not_found(tmp_path: Path):
    result = run_pdf("extract-text", "--file-path", str(tmp_path / "missing.pdf"))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


def test_extract_text_not_pdf(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello", encoding="utf-8")
    result = run_pdf("extract-text", "--file-path", str(txt))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


def test_extract_text_valid_pdf(tmp_path: Path):
    """pypdfium2 で PDF を生成し CLI 経由でテキスト抽出する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    result = run_pdf("extract-text", "--file-path", str(pdf_path))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["total_pages"] == 1


# --- to-image ---


def test_to_image_file_not_found(tmp_path: Path):
    result = run_pdf(
        "to-image",
        "--file-path",
        str(tmp_path / "missing.pdf"),
        "--output-dir",
        str(tmp_path / "out"),
    )
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


def test_to_image_not_pdf(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello", encoding="utf-8")
    result = run_pdf("to-image", "--file-path", str(txt), "--output-dir", str(tmp_path / "out"))
    assert result.returncode == 1
    output = json.loads(result.stdout)
    assert output["status"] == "error"


def test_to_image_valid_pdf(tmp_path: Path):
    """pypdfium2 で PDF を生成し CLI 経由で画像変換する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    out_dir = tmp_path / "images"
    result = run_pdf("to-image", "--file-path", str(pdf_path), "--output-dir", str(out_dir))
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"
    assert output["total_pages"] == 1
    assert len(output["images"]) == 1
    assert Path(output["images"][0]).exists()


def test_to_image_custom_dpi(tmp_path: Path):
    """DPI オプションが正しく渡されることを検証する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    out_dir = tmp_path / "images"
    result = run_pdf(
        "to-image",
        "--file-path",
        str(pdf_path),
        "--output-dir",
        str(out_dir),
        "--dpi",
        "72",
    )
    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert output["status"] == "ok"


# --- no subcommand ---


def test_no_subcommand():
    result = run_pdf()
    assert result.returncode == 1
