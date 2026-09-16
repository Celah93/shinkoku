"""固定資産台帳のCRUDと読取り専用の詳細計算。仕訳・年度繰越は行わない。"""

from __future__ import annotations

from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator
from uuid import uuid4

from shinkoku.db import get_connection
from shinkoku.models import (
    FixedAssetInput,
    FixedAssetListInput,
    FixedAssetUpdateInput,
    DepreciationAnnualContext,
    DepreciationCalculationInput,
    DepreciationDetailResult,
    FixedAssetCalculationInput,
    FixedAssetDepreciationResult,
    FixedAssetDepreciationRowResult,
    FixedAssetStatementFields,
    JournalEntry,
    JournalLine,
)
from shinkoku.tools.depreciation import depreciation_details_from_input


_CONFIRMATIONS = {
    "basis_confirmed": "basis_confirmed_at",
    "annual_facts_confirmed": "annual_facts_confirmed_at",
}
_BOOL_FIELDS = ("prior_private_use", "additional_depreciation_applicable")
_FACT_FIELDS = tuple(key for key in FixedAssetInput.model_fields if key not in _CONFIRMATIONS)
_REQUIRED_FACTS = (
    "origin",
    "placed_in_service_date",
    "useful_life",
    "method",
    "business_use_ratio",
    "asset_class",
    "asset_account_code",
    "quantity",
    "quantity_unit",
    "treatment",
    "opening_accumulated_depreciation",
    "book_basis",
    "prior_private_use",
    "additional_depreciation_applicable",
    "basis_confirmed_at",
    "annual_facts_confirmed_at",
)


@contextmanager
def _asset_db(db_path: str, fiscal_year: int) -> Iterator[sqlite3.Connection]:
    if not Path(db_path).is_file():
        raise ValueError("DBが存在しません。ledger initで新規DBを準備してください")
    conn = get_connection(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(fixed_assets)")}
        required = (
            set(_FACT_FIELDS)
            | set(_CONFIRMATIONS.values())
            | {
                "asset_uid",
                "previous_asset_id",
                "accumulated_depreciation",
            }
        )
        if not required <= columns:
            raise ValueError("固定資産台帳が未移行です。ledger initで既存DBを移行してください")
        if (
            conn.execute("SELECT year FROM fiscal_years WHERE year = ?", (fiscal_year,)).fetchone()
            is None
        ):
            raise ValueError(f"年度{fiscal_year}がありません。ledger initで年度を準備してください")
        yield conn
    finally:
        conn.close()


def _error(code: str, message: str) -> dict:
    return {"status": "error", "code": code, "message": message}


def _record(row: sqlite3.Row) -> dict:
    result = dict(row)
    for key in _BOOL_FIELDS:
        result[key] = None if row[key] is None else bool(row[key])
    # 旧値は保存するが、意味が未確認の累計を当年末の計算値として公開しない。
    legacy = row["accumulated_depreciation"]
    result["legacy_values"] = {} if legacy is None else {"accumulated_depreciation": legacy}
    result["accumulated_depreciation"] = None
    result["state"] = "draft" if legacy is None else "legacy_unverified"
    # コマンドの提供を示す。各行の計算可否はfa-depreciationの診断で判定する。
    result["calculation_available"] = True
    result["missing_fields"] = [key for key in _REQUIRED_FACTS if result[key] is None]
    return result


def _validate_references(
    conn: sqlite3.Connection, fiscal_year: int, asset: FixedAssetInput
) -> None:
    acquisition_year = int(asset.acquisition_date[:4])
    if acquisition_year > fiscal_year:
        raise ValueError("取得年が対象年度より後の資産は登録できません")
    if asset.origin == "acquired_this_year" and acquisition_year != fiscal_year:
        raise ValueError("acquired_this_yearでは取得年と対象年度が一致する必要があります")
    if asset.asset_account_code is not None:
        row = conn.execute(
            "SELECT category FROM accounts WHERE code = ?", (asset.asset_account_code,)
        ).fetchone()
        if row is None or row[0] != "asset" or not asset.asset_account_code.startswith("11"):
            raise ValueError("asset_account_codeには登録済みの固定資産科目を指定してください")


def _columns_to_save(data: dict) -> dict:
    values = {key: value for key, value in data.items() if key not in _CONFIRMATIONS}
    for flag, column in _CONFIRMATIONS.items():
        if flag in data:
            values[column] = datetime.now(timezone.utc).isoformat() if data[flag] is True else None
    return values


def ledger_add_fixed_asset(*, db_path: str, fiscal_year: int, asset: FixedAssetInput) -> dict:
    with _asset_db(db_path, fiscal_year) as conn:
        _validate_references(conn, fiscal_year, asset)
        values = _columns_to_save(asset.model_dump())
        values.update(asset_uid=str(uuid4()), fiscal_year=fiscal_year)
        with conn:
            cursor = conn.execute(
                f"INSERT INTO fixed_assets ({', '.join(values)}) "
                f"VALUES ({', '.join('?' for _ in values)})",
                tuple(values.values()),
            )
            row = conn.execute(
                "SELECT * FROM fixed_assets WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return {"status": "ok", "asset": _record(row)}


def ledger_list_fixed_assets(
    *, db_path: str, fiscal_year: int, filters: FixedAssetListInput
) -> dict:
    with _asset_db(db_path, fiscal_year) as conn:
        where = ["fiscal_year = ?"]
        args: list[object] = [fiscal_year]
        if filters.asset_id is not None:
            where.append("id = ?")
            args.append(filters.asset_id)
        if filters.asset_uid is not None:
            where.append("asset_uid = ?")
            args.append(filters.asset_uid)
        rows = conn.execute(
            f"SELECT * FROM fixed_assets WHERE {' AND '.join(where)} ORDER BY id",
            args,
        ).fetchall()
        return {
            "status": "ok",
            "fiscal_year": fiscal_year,
            "assets": [_record(row) for row in rows],
            "count": len(rows),
        }


def ledger_update_fixed_asset(
    *,
    db_path: str,
    fiscal_year: int,
    asset_id: int,
    update: FixedAssetUpdateInput,
) -> dict:
    with _asset_db(db_path, fiscal_year) as conn, conn:
        row = conn.execute(
            "SELECT * FROM fixed_assets WHERE id = ? AND fiscal_year = ?",
            (asset_id, fiscal_year),
        ).fetchone()
        if row is None:
            return _error("FA_NOT_FOUND", f"年度{fiscal_year}に固定資産ID {asset_id}はありません")
        # 後続年度の行がある台帳は、後続の整理を先に要求する。
        if conn.execute(
            "SELECT 1 FROM fixed_assets WHERE previous_asset_id = ?", (asset_id,)
        ).fetchone():
            return _error("FA_HAS_SUCCESSOR", "先に後続年度の台帳を整理してください")
        patch = update.model_dump(exclude_unset=True)
        current = {key: row[key] for key in _FACT_FIELDS}
        for key in _BOOL_FIELDS:
            current[key] = None if current[key] is None else bool(current[key])
        merged = FixedAssetInput(**{**current, **patch})
        _validate_references(conn, fiscal_year, merged)
        values = _columns_to_save(patch)
        # 事実の変更後に以前の確認だけが残らないよう、明示的に再確認されない日時を消す。
        facts_changed = any(
            key not in {"memo", "evidence_ref"} and current[key] != value
            for key, value in patch.items()
            if key in current
        )
        if facts_changed:
            for flag, column in _CONFIRMATIONS.items():
                if patch.get(flag) is not True:
                    values[column] = None
        if row["asset_uid"] is None:
            values["asset_uid"] = str(uuid4())
        conn.execute(
            f"UPDATE fixed_assets SET {', '.join(key + ' = ?' for key in values)} "
            "WHERE id = ? AND fiscal_year = ?",
            (*values.values(), asset_id, fiscal_year),
        )
        saved = conn.execute("SELECT * FROM fixed_assets WHERE id = ?", (asset_id,)).fetchone()
        return {"status": "ok", "asset": _record(saved)}


def ledger_delete_fixed_asset(*, db_path: str, fiscal_year: int, asset_id: int) -> dict:
    with _asset_db(db_path, fiscal_year) as conn, conn:
        if (
            conn.execute(
                "SELECT 1 FROM fixed_assets WHERE id = ? AND fiscal_year = ?",
                (asset_id, fiscal_year),
            ).fetchone()
            is None
        ):
            return _error("FA_NOT_FOUND", f"年度{fiscal_year}に固定資産ID {asset_id}はありません")
        if conn.execute(
            "SELECT 1 FROM fixed_assets WHERE previous_asset_id = ?", (asset_id,)
        ).fetchone():
            return _error("FA_HAS_SUCCESSOR", "先に後続年度の台帳を整理してください")
        conn.execute(
            "DELETE FROM fixed_assets WHERE id = ? AND fiscal_year = ?", (asset_id, fiscal_year)
        )
        return {"status": "ok", "deleted_id": asset_id}


def ledger_calculate_fixed_asset_depreciation(
    *,
    db_path: str,
    fiscal_year: int,
    asset_id: int,
    _connection: sqlite3.Connection | None = None,
) -> DepreciationDetailResult:
    """台帳の確認済み事実を共通計算へ渡す。段階2の内部関数で、DBは変更しない。"""
    connection_scope = (
        _asset_db(db_path, fiscal_year) if _connection is None else nullcontext(_connection)
    )
    with connection_scope as conn:
        row = conn.execute(
            "SELECT * FROM fixed_assets WHERE id = ? AND fiscal_year = ?",
            (asset_id, fiscal_year),
        ).fetchone()
        if row is None:
            raise ValueError(f"年度{fiscal_year}に固定資産ID {asset_id}はありません")
        record = _record(row)
    if record["missing_fields"]:
        raise ValueError("台帳に未確認の項目があります: " + ", ".join(record["missing_fields"]))
    if record["treatment"] != "normal_depreciation":
        raise ValueError("年次計算は通常償却だけに対応しています")
    # 通常の有形資産科目に限定する。土地・無形・一括償却等を同じ終端へ通さない。
    if record["asset_account_code"] not in {"1100", "1101", "1110", "1120", "1130"}:
        raise ValueError("この固定資産科目の年次計算は未対応です")
    context = DepreciationAnnualContext(
        fiscal_year=fiscal_year,
        acquisition_date=record["acquisition_date"],
        placed_in_service_date=record["placed_in_service_date"],
        opening_accumulated_depreciation=record["opening_accumulated_depreciation"],
        asset_class=record["asset_class"],
        book_basis=record["book_basis"],
        prior_private_use=record["prior_private_use"],
        additional_depreciation_applicable=record["additional_depreciation_applicable"],
        basis_confirmed=record["basis_confirmed_at"] is not None,
        annual_facts_confirmed=record["annual_facts_confirmed_at"] is not None,
    )
    return depreciation_details_from_input(
        DepreciationCalculationInput(
            method=record["method"],
            acquisition_cost=record["acquisition_cost"],
            useful_life=record["useful_life"],
            business_use_ratio=record["business_use_ratio"],
            annual_context=context,
        )
    )


def _statement_fields(record: dict, detail: DepreciationDetailResult) -> FixedAssetStatementFields:
    """段階2の検証済み結果を転記する。率・丸め・終端はここでは計算しない。"""
    assert detail.closing_book_value is not None
    return FixedAssetStatementFields(
        name=record["name"],
        quantity=record["quantity"],
        quantity_unit=record["quantity_unit"],
        acquisition_date=record["acquisition_date"],
        placed_in_service_date=record["placed_in_service_date"],
        acquisition_cost=record["acquisition_cost"],
        treatment=record["treatment"],
        method=detail.method,
        useful_life=record["useful_life"],
        depreciation_basis=detail.depreciation_basis,
        rate_numerator=detail.rate_numerator,
        rate_denominator=detail.rate_denominator,
        months=detail.months,
        ordinary_amount=detail.ordinary_amount,
        # 段階2の内部関数が追加償却の不適用を検証した行だけに到達する。
        additional_depreciation_amount=0,
        total_depreciation_amount=detail.ordinary_amount,
        business_use_ratio=detail.business_use_ratio,
        expense_amount=detail.expense_amount,
        closing_book_value=detail.closing_book_value,
        memo=record["memo"],
    )


def ledger_preview_fixed_asset_depreciation(
    *,
    db_path: str,
    fiscal_year: int,
    selection: FixedAssetCalculationInput,
) -> dict:
    """同じ読取りスナップショットから診断と候補を返す。DBへ保存しない。"""
    results: list[FixedAssetDepreciationRowResult] = []
    with _asset_db(db_path, fiscal_year) as conn:
        conn.execute("PRAGMA query_only = ON")
        conn.execute("BEGIN")
        rows = conn.execute(
            "SELECT * FROM fixed_assets WHERE fiscal_year = ? ORDER BY id",
            (fiscal_year,),
        ).fetchall()
        by_id = {row["id"]: row for row in rows}
        asset_ids = list(by_id) if selection.asset_ids is None else selection.asset_ids
        for asset_id in asset_ids:
            row = by_id.get(asset_id)
            if row is None:
                results.append(
                    FixedAssetDepreciationRowResult(
                        asset_id=asset_id,
                        calculation_status="blocked",
                        error_code="FA_NOT_FOUND",
                        blocking_reason=f"年度{fiscal_year}に固定資産ID {asset_id}はありません",
                    )
                )
                continue
            record = _record(row)
            try:
                detail = ledger_calculate_fixed_asset_depreciation(
                    db_path=db_path,
                    fiscal_year=fiscal_year,
                    asset_id=asset_id,
                    _connection=conn,
                )
            except ValueError as exc:
                results.append(
                    FixedAssetDepreciationRowResult(
                        asset_id=asset_id,
                        asset_uid=record["asset_uid"],
                        name=record["name"],
                        calculation_status="blocked",
                        missing_fields=record["missing_fields"],
                        error_code="FA_INPUT_UNCONFIRMED"
                        if record["missing_fields"]
                        else "FA_CALCULATION_BLOCKED",
                        blocking_reason=str(exc),
                    )
                )
                continue
            candidate = None
            if detail.expense_amount > 0:
                candidate = JournalEntry(
                    date=f"{fiscal_year}-12-31",
                    description=f"{record['name']}の減価償却費",
                    source="adjustment",
                    is_adjustment=True,
                    lines=[
                        JournalLine(
                            side="debit",
                            account_code="5200",
                            amount=detail.expense_amount,
                            tax_category="out_of_scope",
                            tax_amount=0,
                        ),
                        JournalLine(
                            side="credit",
                            account_code=record["asset_account_code"],
                            amount=detail.expense_amount,
                            tax_category="out_of_scope",
                            tax_amount=0,
                        ),
                    ],
                )
            results.append(
                FixedAssetDepreciationRowResult(
                    asset_id=asset_id,
                    asset_uid=record["asset_uid"],
                    name=record["name"],
                    calculation_status="ready" if candidate is not None else "no_depreciation",
                    ordinary_amount=detail.ordinary_amount,
                    expense_amount=detail.expense_amount,
                    closing_book_value=detail.closing_book_value,
                    calculation=detail,
                    statement_fields=_statement_fields(record, detail),
                    journal_candidate=candidate,
                )
            )
    complete = all(row.calculation_status != "blocked" for row in results)
    subtotal = sum(row.expense_amount for row in results if row.expense_amount is not None)
    return FixedAssetDepreciationResult(
        fiscal_year=fiscal_year,
        assets=results,
        count=len(results),
        complete=complete,
        total_expense=subtotal if complete else None,
        calculable_subtotal=subtotal,
    ).model_dump(mode="json")
