"""固定資産の架空入力と、移行元の固定済み旧テーブル定義。"""

from __future__ import annotations

from pathlib import Path
import re
import sqlite3

from shinkoku.db import SCHEMA_PATH


LEGACY_COLUMNS = (
    "id",
    "name",
    "acquisition_date",
    "acquisition_cost",
    "useful_life",
    "method",
    "business_use_ratio",
    "accumulated_depreciation",
    "fiscal_year",
    "memo",
)
LEGACY_FIXED_ASSETS_SQL = """CREATE TABLE IF NOT EXISTS fixed_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    acquisition_date TEXT NOT NULL,
    acquisition_cost INTEGER NOT NULL,
    useful_life INTEGER NOT NULL,
    method TEXT NOT NULL DEFAULT 'straight_line' CHECK (method IN ('straight_line', 'declining_balance')),
    business_use_ratio INTEGER NOT NULL DEFAULT 100 CHECK (business_use_ratio BETWEEN 1 AND 100),
    accumulated_depreciation INTEGER NOT NULL DEFAULT 0,
    fiscal_year INTEGER NOT NULL REFERENCES fiscal_years(year),
    memo TEXT
);"""


def make_legacy_asset_db(path: Path) -> list[tuple]:
    """非空・複数年度・旧デフォルト・削除済みIDを含む使い捨てDBを作る。"""
    schema_sql = re.sub(
        r"CREATE TABLE IF NOT EXISTS fixed_assets \([\s\S]+?\n\);",
        LEGACY_FIXED_ASSETS_SQL,
        SCHEMA_PATH.read_text(encoding="utf-8"),
    )
    conn = sqlite3.connect(path)
    try:
        conn.executescript(schema_sql)
        conn.execute("INSERT INTO fiscal_years (year) VALUES (2025), (2026)")
        conn.execute(
            "INSERT INTO accounts (code, name, category) VALUES ('1130', '架空備品', 'asset')"
        )
        conn.execute(
            "INSERT INTO fixed_assets (id, name, acquisition_date, acquisition_cost, useful_life, fiscal_year) "
            "VALUES (7, '架空PC', '2025-04-01', 250000, 4, 2025)"
        )
        conn.execute(
            "INSERT INTO fixed_assets VALUES "
            "(42, '架空PC', '2025-04-01', 250000, 4, 'declining_balance', 60, 62500, 2026, '架空の旧値')"
        )
        conn.execute(
            "INSERT INTO fixed_assets (id, name, acquisition_date, acquisition_cost, useful_life, fiscal_year) "
            "VALUES (900, '削除済みの架空資産', '2026-01-01', 100000, 3, 2026)"
        )
        conn.execute("DELETE FROM fixed_assets WHERE id = 900")
        conn.commit()
        return [tuple(row) for row in conn.execute("SELECT * FROM fixed_assets ORDER BY id")]
    finally:
        conn.close()


def fictional_asset(**overrides: object) -> dict:
    return {
        "name": "検証用PC",
        "acquisition_date": "2026-04-01",
        "acquisition_cost": 250000,
        "placed_in_service_date": "2026-04-01",
        "useful_life": 4,
        "method": "straight_line",
        "business_use_ratio": 100,
        "quantity": "1",
        "quantity_unit": "台",
        "origin": "acquired_this_year",
        "asset_class": "tangible",
        "asset_account_code": "1130",
        "treatment": "normal_depreciation",
        "opening_accumulated_depreciation": 0,
        "book_basis": "full_cost_direct",
        "prior_private_use": False,
        "additional_depreciation_applicable": False,
        "basis_confirmed": True,
        "annual_facts_confirmed": True,
        **overrides,
    }
