"""Unit tests for shinkoku.tools.pdf."""

from __future__ import annotations

from pathlib import Path

from shinkoku.tools.pdf import extract_text, to_images


# --- extract_text ---


def test_extract_text_file_not_found(tmp_path: Path):
    result = extract_text(file_path=str(tmp_path / "missing.pdf"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_extract_text_not_pdf(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello", encoding="utf-8")
    result = extract_text(file_path=str(txt))
    assert result["status"] == "error"
    assert "Not a PDF" in result["message"]


def test_extract_text_valid_pdf(tmp_path: Path):
    """pypdfium2 で最小限の PDF を生成してテキスト抽出を検証する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    result = extract_text(file_path=str(pdf_path))
    assert result["status"] == "ok"
    assert result["total_pages"] == 1
    assert len(result["pages"]) == 1


# --- to_images ---


def test_to_images_file_not_found(tmp_path: Path):
    result = to_images(file_path=str(tmp_path / "missing.pdf"), output_dir=str(tmp_path / "out"))
    assert result["status"] == "error"
    assert "not found" in result["message"].lower()


def test_to_images_not_pdf(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("hello", encoding="utf-8")
    result = to_images(file_path=str(txt), output_dir=str(tmp_path / "out"))
    assert result["status"] == "error"
    assert "Not a PDF" in result["message"]


def test_to_images_valid_pdf(tmp_path: Path):
    """pypdfium2 で最小限の PDF を生成して画像変換を検証する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    out_dir = tmp_path / "images"
    result = to_images(file_path=str(pdf_path), output_dir=str(out_dir))
    assert result["status"] == "ok"
    assert result["total_pages"] == 1
    assert len(result["images"]) == 1
    assert Path(result["images"][0]).exists()
    assert Path(result["images"][0]).suffix == ".png"


def test_extract_text_with_content(tmp_path: Path):
    """テキストを含む PDF からテキスト抽出できることを検証する。"""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    pdf.cell(text="Hello PDF World")
    pdf.output(str(tmp_path / "text.pdf"))

    result = extract_text(file_path=str(tmp_path / "text.pdf"))
    assert result["status"] == "ok"
    assert "Hello PDF World" in result["full_text"]


def test_to_images_creates_output_dir(tmp_path: Path):
    """output_dir が存在しない場合に自動作成されることを検証する。"""
    import pypdfium2 as pdfium

    pdf_path = tmp_path / "sample.pdf"
    pdf = pdfium.PdfDocument.new()
    page = pdf.new_page(200, 100)
    page.close()
    with open(pdf_path, "wb") as f:
        pdf.save(f)
    pdf.close()

    out_dir = tmp_path / "nested" / "deep" / "images"
    assert not out_dir.exists()
    result = to_images(file_path=str(pdf_path), output_dir=str(out_dir))
    assert result["status"] == "ok"
    assert out_dir.exists()
