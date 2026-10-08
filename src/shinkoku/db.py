"""Database initialization and connection management."""

from __future__ import annotations

import re
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
    try:
        schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        # 後続の移行で中断しても、固定資産だけが確定しないよう通常のトランザクションを張る。
        conn.execute("BEGIN")
        _migrate(conn)
        conn.commit()
        return conn
    except BaseException:
        conn.rollback()
        conn.close()
        raise


def _migrate(conn: sqlite3.Connection) -> None:
    """既存DBに新しいカラム・テーブルを追加するマイグレーション。"""
    _migrate_fixed_assets(conn)
    _migrate_withholding_slips(conn)
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


def _migrate_fixed_assets(conn: sqlite3.Connection) -> None:
    """旧台帳の全値・ID・採番上限を保ち、追加の事実をNULLのまま移行する。"""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(fixed_assets)")}
    if "asset_uid" in columns:
        return
    legacy_columns = (
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
    if columns != set(legacy_columns):
        raise ValueError("固定資産台帳の旧スキーマを識別できません。既存DBは置き換えません")

    # 新規DBと移行後DBの定義を二重に持たず、schema.sqlの同じCREATE文を使う。
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS fixed_assets \([\s\S]+?\n\);",
        SCHEMA_PATH.read_text(encoding="utf-8"),
    )
    if match is None:
        raise ValueError("schema.sqlに固定資産台帳の定義がありません")
    definition = (
        match.group()
        .replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE")
        .replace("fixed_assets", "fixed_assets_migration")
    )
    conn.execute("SAVEPOINT migrate_fixed_assets")
    try:
        schema_objects = conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'fixed_assets' "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL"
        ).fetchall()
        sequence = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name = 'fixed_assets'"
        ).fetchone()
        conn.execute(definition)
        names = ", ".join(legacy_columns)
        conn.execute(
            f"INSERT INTO fixed_assets_migration ({names}) SELECT {names} FROM fixed_assets"
        )
        differences = conn.execute(
            f"SELECT {names} FROM fixed_assets EXCEPT SELECT {names} FROM fixed_assets_migration"
        ).fetchall()
        old_count = conn.execute("SELECT COUNT(*) FROM fixed_assets").fetchone()[0]
        new_count = conn.execute("SELECT COUNT(*) FROM fixed_assets_migration").fetchone()[0]
        if differences or old_count != new_count:
            raise ValueError("固定資産台帳の移行前後で値が一致しません")
        conn.execute("DROP TABLE fixed_assets")
        conn.execute("ALTER TABLE fixed_assets_migration RENAME TO fixed_assets")
        if sequence is not None:
            conn.execute(
                "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'fixed_assets'",
                (sequence[0],),
            )
        for row in schema_objects:
            conn.execute(row[0])
        if conn.execute("PRAGMA foreign_key_check(fixed_assets)").fetchall():
            raise ValueError("固定資産台帳の外部キーに不整合があります")
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT migrate_fixed_assets")
        conn.execute("RELEASE SAVEPOINT migrate_fixed_assets")
        raise
    conn.execute("RELEASE SAVEPOINT migrate_fixed_assets")


def _migrate_withholding_slips(conn: sqlite3.Connection) -> None:
    """全旧値・作成日時・採番を保持し、未確認情報をNULLで追加する。"""
    legacy = (
        "id",
        "fiscal_year",
        "payer_name",
        "payment_amount",
        "withheld_tax",
        "social_insurance",
        "life_insurance_deduction",
        "earthquake_insurance_deduction",
        "housing_loan_deduction",
        "spouse_deduction",
        "dependent_deduction",
        "basic_deduction",
        "life_insurance_general_new",
        "life_insurance_general_old",
        "life_insurance_medical_care",
        "life_insurance_annuity_new",
        "life_insurance_annuity_old",
        "national_pension_premium",
        "old_long_term_insurance_premium",
        "source_file",
        "created_at",
    )
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS withholding_slips \([\s\S]+?\n\);",
        SCHEMA_PATH.read_text(encoding="utf-8"),
    )
    if match is None:
        raise ValueError("schema.sqlに源泉徴収票の定義がありません")
    definition = match.group()
    expected = set(re.findall(r"^\s+(\w+)\s+(?:INTEGER|TEXT)", definition, re.MULTILINE))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(withholding_slips)")}
    if columns == expected:
        return
    if columns != set(legacy):
        raise ValueError("源泉徴収票の旧スキーマを識別できません。既存DBは置き換えません")
    definition = definition.replace("CREATE TABLE IF NOT EXISTS", "CREATE TABLE").replace(
        "withholding_slips", "withholding_slips_migration"
    )
    conn.execute("SAVEPOINT migrate_withholding_slips")
    try:
        objects = conn.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='withholding_slips' AND type IN ('index','trigger') AND sql IS NOT NULL"
        ).fetchall()
        sequence = conn.execute(
            "SELECT seq FROM sqlite_sequence WHERE name='withholding_slips'"
        ).fetchone()
        conn.execute(definition)
        names = ", ".join(legacy)
        conn.execute(
            f"INSERT INTO withholding_slips_migration ({names}) SELECT {names} FROM withholding_slips"
        )
        differences = conn.execute(
            f"SELECT {names} FROM withholding_slips EXCEPT SELECT {names} FROM withholding_slips_migration"
        ).fetchall()
        old_count = conn.execute("SELECT COUNT(*) FROM withholding_slips").fetchone()[0]
        new_count = conn.execute("SELECT COUNT(*) FROM withholding_slips_migration").fetchone()[0]
        if differences or old_count != new_count:
            raise ValueError("源泉徴収票の移行前後で値が一致しません")
        conn.execute("DROP TABLE withholding_slips")
        conn.execute("ALTER TABLE withholding_slips_migration RENAME TO withholding_slips")
        if sequence is not None:
            cursor = conn.execute(
                "UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name='withholding_slips'",
                (sequence[0],),
            )
            if not cursor.rowcount:
                conn.execute(
                    "INSERT INTO sqlite_sequence(name,seq) VALUES('withholding_slips', ?)",
                    (sequence[0],),
                )
        for row in objects:
            conn.execute(row[0])
        if conn.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("源泉徴収票の移行後に外部キーの不整合があります")
    except BaseException:
        conn.execute("ROLLBACK TO SAVEPOINT migrate_withholding_slips")
        conn.execute("RELEASE SAVEPOINT migrate_withholding_slips")
        raise
    conn.execute("RELEASE SAVEPOINT migrate_withholding_slips")


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
