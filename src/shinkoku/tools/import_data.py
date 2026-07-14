"""Data import tools for the shinkoku MCP server."""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from pathlib import Path

from shinkoku.db import get_connection
from shinkoku.duplicate_detection import check_source_file_imported, record_import_source
from shinkoku.hashing import compute_file_hash


def _detect_encoding(file_path: str) -> str:
    """Detect file encoding (UTF-8 with/without BOM, or cp932 = Windows-31J)."""
    raw = Path(file_path).read_bytes()
    # Excel出力CSVのBOM。plain utf-8でもデコードは成功してしまい、
    # 1列目ヘッダに \ufeff が混入するため、utf-8判定より先に見る。
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    # BOMなしUTF-8の日本語はcp932でも文字化けしたまま読めるため、utf-8を先に試す。
    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass
    # 銀行・カード明細CSVはWindows製で、純正Shift_JISにない拡張文字を含む。
    # shift_jisで有効なバイト列はすべてcp932でも読めるため、cp932へ一本化する。
    try:
        raw.decode("cp932")
        return "cp932"
    except UnicodeDecodeError:
        pass
    # 読める保証はなく、読込時のエラーとして表面化させる。
    return "utf-8"


def _detect_date_column(headers: list[str]) -> int | None:
    """Find the column index that looks like a date column."""
    date_patterns = ["日付", "利用日", "date", "取引日", "発生日", "年月日"]
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        for pattern in date_patterns:
            if pattern in h_lower:
                return i
    return 0 if headers else None


def _detect_description_column(headers: list[str]) -> int | None:
    """Find the column index for the description."""
    desc_patterns = [
        "摘要",
        "利用店名",
        "店名",
        "description",
        "内容",
        "取引内容",
        "備考",
        "名称",
    ]
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        for pattern in desc_patterns:
            if pattern in h_lower:
                return i
    return 1 if len(headers) > 1 else None


def _detect_amount_column(headers: list[str]) -> int | None:
    """Find the column index for the amount."""
    amount_patterns = [
        "金額",
        "利用金額",
        "amount",
        "支払金額",
        "取引金額",
        "合計",
    ]
    for i, h in enumerate(headers):
        h_lower = h.lower().strip()
        for pattern in amount_patterns:
            if pattern in h_lower:
                return i
    return 2 if len(headers) > 2 else None


# 金額の許容書式: [通貨記号]数字([3桁区切り])[.0+][円]
# 記号を除去してから判定すると、場所・個数の情報が失われ、12,34や1円2などの
# 壊れた書式を正しい金額らしく見せてしまうため、文字列全体を照合する。
_AMOUNT_RE = re.compile(
    r"(?:[¥\\])?"  # 通貨記号は先頭に最大1つ
    r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)"  # 3桁区切り or 区切りなし
    r"(?:\.0+)?"  # 小数部は0のみ（整数円として解釈）
    r"円?"  # 円は末尾に最大1つ
)


def _parse_amount(value: str) -> int | None:
    """Parse an amount string to int. Returns None if unparseable.

    許容書式の全体照合で判定し、一致しない値は黙って数値化せず None を
    返す（呼び出し側で skipped_rows 行き）。
    """
    # 全角数字・カンマ・括弧・円記号・マイナスを半角へ正規化する。
    s = unicodedata.normalize("NFKC", value.strip())

    negative = False
    # 負数記号は先頭の1種類だけ。▲△とU+2212はNFKCで'-'にならないため明示する。
    if s[:1] in ("▲", "△", "−", "-"):
        negative, s = True, s[1:].lstrip()
    elif len(s) >= 2 and s[0] == "(" and s[-1] == ")":
        negative, s = True, s[1:-1].strip()
    # 末尾マイナスや二重符号は本体の全体照合に一致しないため受け付けない。
    match = _AMOUNT_RE.fullmatch(s)
    if match is None:
        return None
    amount = int(match.group(1).replace(",", ""))
    return -amount if negative else amount


def _normalize_date(value: str) -> str | None:
    """Normalize date to YYYY-MM-DD format."""
    value = value.strip()
    # Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value
    # YYYY/MM/DD
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", value)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None


def import_csv(*, file_path: str) -> dict:
    """Parse a CSV file and return CSVImportCandidate list.

    Supports UTF-8 (with/without BOM) and cp932 (Windows-31J) encoding.
    Does not guess account codes (that is left to Claude/Skills).
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    encoding = _detect_encoding(file_path)
    try:
        text = path.read_text(encoding=encoding)
    except Exception as e:
        return {"status": "error", "message": f"Read error: {e}"}

    reader = csv.reader(io.StringIO(text))
    rows = list(reader)

    if not rows:
        return {
            "status": "ok",
            "file_path": file_path,
            "encoding": encoding,
            "total_rows": 0,
            "candidates": [],
            "skipped_rows": [],
            "errors": [],
        }

    # First row is headers
    headers = [h.strip() for h in rows[0]]
    date_col = _detect_date_column(headers)
    desc_col = _detect_description_column(headers)
    amount_col = _detect_amount_column(headers)

    candidates = []
    skipped_rows = []
    errors: list[str] = []

    for i, row in enumerate(rows[1:], start=2):
        # Skip empty rows
        if not row or all(not cell.strip() for cell in row):
            continue

        try:
            # Validate we have enough columns
            if (
                date_col is not None
                and date_col >= len(row)
                or desc_col is not None
                and desc_col >= len(row)
                or amount_col is not None
                and amount_col >= len(row)
            ):
                skipped_rows.append(i)
                continue

            date_val = _normalize_date(row[date_col]) if date_col is not None else None
            desc_val = row[desc_col].strip() if desc_col is not None else ""
            amount_val = _parse_amount(row[amount_col]) if amount_col is not None else None

            if date_val is None or amount_val is None:
                skipped_rows.append(i)
                continue

            # Build original_data dict from headers
            original = {}
            for j, h in enumerate(headers):
                if j < len(row):
                    original[h] = row[j].strip()

            candidates.append(
                {
                    "row_number": i,
                    "date": date_val,
                    "description": desc_val,
                    "amount": amount_val,
                    "original_data": original,
                }
            )
        except (IndexError, ValueError):
            skipped_rows.append(i)

    # ファイルハッシュ（重複インポート検出用）
    file_hash = compute_file_hash(file_path)

    return {
        "status": "ok",
        "file_path": file_path,
        "file_hash": file_hash,
        "encoding": encoding,
        "total_rows": len(candidates),
        "candidates": candidates,
        "skipped_rows": skipped_rows,
        "errors": errors,
    }


def import_receipt(*, file_path: str) -> dict:
    """Check file existence and return a ReceiptData template.

    OCR is performed by Claude Vision, so this tool only verifies the file
    exists and returns an empty template for Claude to fill in.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    return {
        "status": "ok",
        "file_path": file_path,
        "date": None,
        "vendor": None,
        "total_amount": None,
        "items": [],
        "tax_included": True,
    }


def _extract_pdf_text(file_path: str) -> str:
    """Extract text from a PDF using tools/pdf.extract_text()."""
    from shinkoku.tools.pdf import extract_text

    result = extract_text(file_path=file_path)
    if result.get("status") == "ok":
        return result.get("full_text", "")
    return ""


def import_invoice(*, file_path: str) -> dict:
    """請求書の読み取り。PDF の場合はテキスト抽出し、画像の場合は Claude Vision に委任する。"""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    extracted_text = ""
    if path.suffix.lower() == ".pdf":
        extracted_text = _extract_pdf_text(file_path)

    return {
        "status": "ok",
        "file_path": file_path,
        "extracted_text": extracted_text,
        "vendor": None,
        "invoice_number": None,
        "date": None,
        "total_amount": None,
        "tax_amount": None,
    }


def import_withholding(*, file_path: str) -> dict:
    """源泉徴収票の読み取り。PDF の場合はテキスト抽出し、画像の場合は Claude Vision に委任する。"""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    extracted_text = ""
    if path.suffix.lower() == ".pdf":
        extracted_text = _extract_pdf_text(file_path)

    return {
        "status": "ok",
        "file_path": file_path,
        "extracted_text": extracted_text,
        "payer_name": None,
        "payment_amount": 0,
        "withheld_tax": 0,
        "social_insurance": 0,
        "life_insurance_deduction": 0,
        "earthquake_insurance_deduction": 0,
        "housing_loan_deduction": 0,
    }


def import_furusato_receipt(*, file_path: str) -> dict:
    """Check receipt file existence and return FurusatoReceiptData template.

    OCR is performed by Claude Vision, so this tool only verifies the file
    exists and returns an empty template for Claude to fill in.
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    return {
        "status": "ok",
        "file_path": file_path,
        "municipality_name": None,
        "municipality_prefecture": None,
        "address": None,
        "amount": None,
        "date": None,
        "receipt_number": None,
    }


def import_payment_statement(*, file_path: str) -> dict:
    """Check payment statement file and return template for data extraction.

    支払調書（報酬、料金、契約金及び賞金の支払調書）の読み取り。
    PDF の場合はテキスト抽出し、画像の場合は Claude Vision に委任する。
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    extracted_text = ""
    if path.suffix.lower() == ".pdf":
        extracted_text = _extract_pdf_text(file_path)

    return {
        "status": "ok",
        "file_path": file_path,
        "extracted_text": extracted_text,
        "payer_name": None,
        "category": None,  # 区分（報酬/料金/契約金等）
        "gross_amount": None,  # 支払金額
        "withholding_tax": None,  # 源泉徴収税額
    }


def import_deduction_certificate(*, file_path: str) -> dict:
    """Check deduction certificate file and return template for OCR.

    控除証明書（生命保険料・地震保険料・社会保険料・小規模企業共済等）の
    読み取りテンプレートを返す。画像の場合は Claude Vision で OCR する。
    """
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    extracted_text = ""
    if path.suffix.lower() == ".pdf":
        extracted_text = _extract_pdf_text(file_path)

    return {
        "status": "ok",
        "file_path": file_path,
        "extracted_text": extracted_text,
        # 以下は Claude Vision / Claude が OCR 結果から埋める
        "certificate_type": None,  # life_insurance / earthquake_insurance / social_insurance / small_business_mutual_aid
        "policy_type": None,  # new / old (生命保険の新旧制度)
        "category": None,  # general / medical_care / annuity (生命保険の区分)
        "company_name": None,  # 保険会社名・機関名
        "policy_number": None,  # 証券番号
        "annual_premium": None,  # 年間保険料（円）
        "is_old_long_term": None,  # 旧長期損害保険かどうか
        "insurance_type": None,  # 社会保険の種別
        "sub_type": None,  # 小規模企業共済の種別（ideco / small_business / disability）
    }


def import_check_csv_imported(*, db_path: str, fiscal_year: int, file_path: str) -> dict:
    """Check if a CSV file has already been imported."""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    file_hash = compute_file_hash(file_path)
    conn = get_connection(db_path)
    try:
        record = check_source_file_imported(conn, fiscal_year, file_hash)
        if record:
            return {
                "status": "already_imported",
                "file_path": file_path,
                "file_hash": file_hash,
                "import_record": record,
            }
        return {
            "status": "not_imported",
            "file_path": file_path,
            "file_hash": file_hash,
        }
    finally:
        conn.close()


def import_record_source(
    *, db_path: str, fiscal_year: int, file_path: str, row_count: int = 0
) -> dict:
    """Record that a file has been imported."""
    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    file_hash = compute_file_hash(file_path)
    file_name = path.name
    conn = get_connection(db_path)
    try:
        source_id = record_import_source(
            conn,
            fiscal_year,
            file_hash,
            file_name,
            file_path=file_path,
            row_count=row_count,
        )
        return {
            "status": "ok",
            "import_source_id": source_id,
            "file_hash": file_hash,
            "file_name": file_name,
        }
    finally:
        conn.close()
