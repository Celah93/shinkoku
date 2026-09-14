"""Database initialization and connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Create a connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the database: create file, apply schema, return connection."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    _migrate(conn)
    conn.commit()
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """既存DBに新しいカラム・テーブルを追加するマイグレーション。"""
    # fiscal_years: 年度別の消費税プロファイル
    fy_cols = {row[1] for row in conn.execute("PRAGMA table_info(fiscal_years)").fetchall()}
    if "taxpayer_status" not in fy_cols:
        conn.execute("ALTER TABLE fiscal_years ADD COLUMN taxpayer_status TEXT")
    if "consumption_tax_method" not in fy_cols:
        conn.execute("ALTER TABLE fiscal_years ADD COLUMN consumption_tax_method TEXT")
    if "simplified_business_type" not in fy_cols:
        conn.execute("ALTER TABLE fiscal_years ADD COLUMN simplified_business_type INTEGER")

    # journals.counterparty カラム追加（電帳法 検索機能要件: 取引先検索）
    cols = {row[1] for row in conn.execute("PRAGMA table_info(journals)").fetchall()}
    if "counterparty" not in cols:
        conn.execute("ALTER TABLE journals ADD COLUMN counterparty TEXT")

    # housing_loan_details: 重複適用（中古購入＋リフォーム同時）対応カラム追加
    hl_cols = {row[1] for row in conn.execute("PRAGMA table_info(housing_loan_details)").fetchall()}
    if "dual_application_group" not in hl_cols:
        conn.execute("ALTER TABLE housing_loan_details ADD COLUMN dual_application_group TEXT")
    if "cost_for_proration" not in hl_cols:
        conn.execute(
            "ALTER TABLE housing_loan_details "
            "ADD COLUMN cost_for_proration INTEGER NOT NULL DEFAULT 0"
        )
    if "is_special_target_individual" not in hl_cols:
        conn.execute(
            "ALTER TABLE housing_loan_details ADD COLUMN is_special_target_individual INTEGER"
        )
        conn.execute(
            "UPDATE housing_loan_details SET is_special_target_individual = is_childcare_household"
        )

    table_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'housing_loan_details'"
    ).fetchone()
    if table_row is not None and "broker_renovated_resale" not in table_row[0]:
        _rebuild_housing_loan_details(conn)

    # 2028年以後の経過措置・立地の確認情報。旧レコードは未確認のNULLを維持する。
    hl_cols = {row[1] for row in conn.execute("PRAGMA table_info(housing_loan_details)").fetchall()}
    for column, sql_type in (
        ("building_confirmation_date", "TEXT"),
        ("building_completion_date", "TEXT"),
        ("is_disaster_red_zone", "INTEGER"),
        ("is_rebuilding", "INTEGER"),
        ("loan_term_years", "INTEGER"),
    ):
        if column not in hl_cols:
            conn.execute(f"ALTER TABLE housing_loan_details ADD COLUMN {column} {sql_type}")


def _rebuild_housing_loan_details(conn: sqlite3.Connection) -> None:
    """旧CHECK制約を更新し、買取再販区分を保存できるようにする。"""
    conn.execute("ALTER TABLE housing_loan_details RENAME TO housing_loan_details_legacy")
    conn.execute(
        """
        CREATE TABLE housing_loan_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fiscal_year INTEGER NOT NULL REFERENCES fiscal_years(year),
            housing_type TEXT NOT NULL CHECK (housing_type IN (
                'new_custom', 'new_subdivision', 'broker_renovated_resale',
                'resale', 'used', 'renovation'
            )),
            housing_category TEXT NOT NULL CHECK (housing_category IN (
                'general', 'certified', 'zeh', 'energy_efficient'
            )),
            move_in_date TEXT NOT NULL,
            year_end_balance INTEGER NOT NULL CHECK (year_end_balance >= 0),
            is_new_construction INTEGER NOT NULL DEFAULT 1,
            is_childcare_household INTEGER NOT NULL DEFAULT 0,
            is_special_target_individual INTEGER,
            has_pre_r6_building_permit INTEGER NOT NULL DEFAULT 0,
            purchase_date TEXT,
            purchase_price INTEGER NOT NULL DEFAULT 0,
            total_floor_area INTEGER NOT NULL DEFAULT 0,
            residential_floor_area INTEGER NOT NULL DEFAULT 0,
            property_number TEXT,
            application_submitted INTEGER NOT NULL DEFAULT 0,
            dual_application_group TEXT,
            cost_for_proration INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    columns = (
        "id, fiscal_year, housing_type, housing_category, move_in_date, year_end_balance, "
        "is_new_construction, is_childcare_household, is_special_target_individual, "
        "has_pre_r6_building_permit, purchase_date, purchase_price, total_floor_area, "
        "residential_floor_area, property_number, application_submitted, "
        "dual_application_group, cost_for_proration, created_at"
    )
    conn.execute(
        f"INSERT INTO housing_loan_details ({columns}) "
        f"SELECT {columns} FROM housing_loan_details_legacy"
    )
    conn.execute("DROP TABLE housing_loan_details_legacy")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_housing_loan_details_fiscal_year "
        "ON housing_loan_details(fiscal_year)"
    )
