import sqlite3

import pytest

from shinkoku.db import init_db


def test_init_db_creates_file(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    assert (tmp_path / "test.db").exists()
    conn.close()


def test_init_db_creates_all_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    expected = {
        "fiscal_years",
        "accounts",
        "journals",
        "journal_lines",
        "journal_audit_log",
        "fixed_assets",
        "deductions",
        "withholding_slips",
        "opening_balances",
    }
    assert expected.issubset(tables)
    conn.close()


def test_init_db_idempotent(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn1 = init_db(db_path)
    conn1.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn1.commit()
    conn1.close()
    conn2 = init_db(db_path)
    row = conn2.execute("SELECT year FROM fiscal_years").fetchone()
    assert row[0] == 2025
    conn2.close()


def test_migrate_fiscal_year_tax_profile_columns_from_legacy_schema(tmp_path):
    """旧 fiscal_years を自動移行し、既存行を保ったまま3列を追加する。"""
    db_path = str(tmp_path / "legacy.db")
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE fiscal_years ("
        "year INTEGER PRIMARY KEY, "
        "status TEXT NOT NULL DEFAULT 'open', "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    legacy.execute(
        "INSERT INTO fiscal_years (year, status, created_at) VALUES (?, ?, ?)",
        (2024, "closed", "2025-03-01 12:34:56"),
    )
    legacy.commit()
    legacy.close()

    conn = init_db(db_path)
    columns = {row[1]: row for row in conn.execute("PRAGMA table_info(fiscal_years)")}
    row = conn.execute("SELECT * FROM fiscal_years WHERE year = 2024").fetchone()

    assert {"taxpayer_status", "consumption_tax_method", "simplified_business_type"}.issubset(
        columns
    )
    for name in ("taxpayer_status", "consumption_tax_method", "simplified_business_type"):
        assert columns[name][3] == 0  # NOT NULL ではない
        assert columns[name][4] is None
    assert row["year"] == 2024
    assert row["status"] == "closed"
    assert row["created_at"] == "2025-03-01 12:34:56"
    assert row["taxpayer_status"] is None
    assert row["consumption_tax_method"] is None
    assert row["simplified_business_type"] is None
    conn.close()

    # 再実行でも列や既存行が変わらない。
    conn = init_db(db_path)
    columns = [row[1] for row in conn.execute("PRAGMA table_info(fiscal_years)")]
    assert columns.count("taxpayer_status") == 1
    assert columns.count("consumption_tax_method") == 1
    assert columns.count("simplified_business_type") == 1
    assert (
        conn.execute("SELECT status FROM fiscal_years WHERE year = 2024").fetchone()[0] == "closed"
    )
    conn.close()


def test_migrate_fiscal_year_tax_profile_columns_from_interrupted_state(tmp_path):
    """3列中1列だけ追加済みでも、残り2列を個別に追加する。"""
    db_path = str(tmp_path / "interrupted.db")
    legacy = sqlite3.connect(db_path)
    legacy.execute(
        "CREATE TABLE fiscal_years ("
        "year INTEGER PRIMARY KEY, "
        "status TEXT NOT NULL DEFAULT 'open', "
        "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
        "taxpayer_status TEXT)"
    )
    legacy.execute(
        "INSERT INTO fiscal_years (year, taxpayer_status) VALUES (?, ?)",
        (2025, "taxable"),
    )
    legacy.commit()
    legacy.close()

    conn = init_db(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(fiscal_years)")}
    row = conn.execute(
        "SELECT taxpayer_status, consumption_tax_method, simplified_business_type "
        "FROM fiscal_years WHERE year = 2025"
    ).fetchone()
    assert {"taxpayer_status", "consumption_tax_method", "simplified_business_type"}.issubset(
        columns
    )
    assert tuple(row) == ("taxable", None, None)
    conn.close()


def test_foreign_keys_enabled(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1
    conn.close()


def test_wal_mode_enabled(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    result = conn.execute("PRAGMA journal_mode").fetchone()
    assert result[0] == "wal"
    conn.close()


def test_journal_lines_reference_journals(tmp_path):
    """journal_lines の foreign key が journals を参照していることを確認。"""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    # journal_id が存在しない journal_lines は挿入できない
    conn.execute("INSERT INTO accounts (code, name, category) VALUES ('1001', 'cash', 'asset')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO journal_lines (journal_id, side, account_code, amount) "
            "VALUES (999, 'debit', '1001', 1000)"
        )
    conn.close()


def test_additional_tables_exist(tmp_path):
    """社会保険料・保険契約・寄附金テーブルが存在すること。"""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    expected = {"social_insurance_items", "insurance_policies", "donation_records"}
    assert expected.issubset(tables)
    conn.close()


def test_dependents_other_taxpayer_column(tmp_path):
    """dependents テーブルに other_taxpayer_dependent 列が存在すること。"""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cursor = conn.execute("PRAGMA table_info(dependents)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "other_taxpayer_dependent" in columns
    conn.close()


def test_housing_loan_detail_columns(tmp_path):
    """housing_loan_details テーブルに明細列が存在すること。"""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    cursor = conn.execute("PRAGMA table_info(housing_loan_details)")
    columns = {row[1] for row in cursor.fetchall()}
    expected_new = {
        "purchase_date",
        "purchase_price",
        "total_floor_area",
        "residential_floor_area",
        "property_number",
        "application_submitted",
    }
    assert expected_new.issubset(columns)
    conn.close()


def test_opening_balances_table(tmp_path):
    """opening_balances テーブルが存在し、UNIQUE 制約が機能すること。"""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    # テーブル存在確認
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {row[0] for row in cursor.fetchall()}
    assert "opening_balances" in tables
    # UNIQUE 制約の確認
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.execute("INSERT INTO accounts (code, name, category) VALUES ('1001', 'cash', 'asset')")
    conn.execute(
        "INSERT INTO opening_balances (fiscal_year, account_code, amount) VALUES (2025, '1001', 100000)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO opening_balances (fiscal_year, account_code, amount) "
            "VALUES (2025, '1001', 200000)"
        )
    conn.close()
