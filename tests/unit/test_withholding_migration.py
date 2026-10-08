"""既存の源泉徴収票の値と採番を保持する移行。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import shinkoku.db as database
from shinkoku.db import get_connection, init_db

AMOUNTS = (
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
)
OLD_COLUMNS = ("id", "fiscal_year", "payer_name", *AMOUNTS, "source_file", "created_at")


def make_legacy_withholding_db(path: Path) -> list[tuple]:
    conn = init_db(str(path))
    conn.execute("DROP TABLE withholding_slips")
    columns = ", ".join(f"{name} INTEGER NOT NULL DEFAULT 0" for name in AMOUNTS)
    conn.execute(
        f"CREATE TABLE withholding_slips (id INTEGER PRIMARY KEY AUTOINCREMENT, fiscal_year INTEGER NOT NULL REFERENCES fiscal_years(year), payer_name TEXT, {columns}, source_file TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025),(2026)")
    conn.execute(
        "INSERT INTO withholding_slips (id,fiscal_year,payer_name,payment_amount,created_at) VALUES (7,2025,'架空勤務先',5000000,'2025-12-31'),(42,2026,'架空勤務先',6000000,'2026-12-31'),(900,2026,'削除済み架空票',1,'2026-12-31')"
    )
    conn.execute("DELETE FROM withholding_slips WHERE id=900")
    conn.execute("CREATE INDEX idx_withholding_slips_fiscal_year ON withholding_slips(fiscal_year)")
    conn.execute("CREATE INDEX extra_ws_index ON withholding_slips(payment_amount)")
    conn.execute(
        "CREATE TRIGGER extra_ws_trigger AFTER UPDATE ON withholding_slips BEGIN SELECT 1; END"
    )
    conn.commit()
    rows = old_rows(conn)
    conn.close()
    return rows


def old_rows(conn: sqlite3.Connection) -> list[tuple]:
    return [
        tuple(row)
        for row in conn.execute(
            f"SELECT {','.join(OLD_COLUMNS)} FROM withholding_slips ORDER BY id"
        )
    ]


def test_nonempty_withholding_migration_preserves_values_and_sequence(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    original = make_legacy_withholding_db(path)
    conn = init_db(str(path))
    try:
        assert old_rows(conn) == original
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert (
            conn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='withholding_slips'"
            ).fetchone()[0]
            == 900
        )
        extra = {r[1] for r in conn.execute("PRAGMA table_info(withholding_slips)")} - set(
            OLD_COLUMNS
        )
        assert "document_fiscal_year" in extra
        for row in conn.execute("SELECT * FROM withholding_slips"):
            assert all(row[name] is None for name in extra)
        conn.execute("INSERT INTO withholding_slips(fiscal_year) VALUES(2026)")
        row = conn.execute("SELECT * FROM withholding_slips WHERE id=901").fetchone()
        assert row is not None and row["payment_amount"] is None
        conn.commit()
        snapshot = list(conn.iterdump())
    finally:
        conn.close()
    conn = init_db(str(path))
    try:
        assert list(conn.iterdump()) == snapshot
    finally:
        conn.close()


@pytest.mark.parametrize("failure", ["copy", "drop", "rename", "index", "trigger"])
def test_interrupted_withholding_migration_rolls_back(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "interrupted.db"
    original = make_legacy_withholding_db(path)
    conn = get_connection(str(path))
    before = list(conn.iterdump())
    interrupted = False

    def authorizer(action, first, second, *_):
        nonlocal interrupted
        targets = {
            "copy": action == sqlite3.SQLITE_INSERT and first == "withholding_slips_migration",
            "drop": action == sqlite3.SQLITE_DROP_TABLE and first == "withholding_slips",
            "rename": action == sqlite3.SQLITE_ALTER_TABLE
            and second == "withholding_slips_migration",
            "index": action == sqlite3.SQLITE_CREATE_INDEX and first == "extra_ws_index",
            "trigger": action == sqlite3.SQLITE_CREATE_TRIGGER and first == "extra_ws_trigger",
        }
        if targets[failure] and not interrupted:
            interrupted = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        conn.set_authorizer(authorizer)
        with pytest.raises(sqlite3.DatabaseError):
            database._migrate_withholding_slips(conn)
        conn.set_authorizer(None)
        assert interrupted
        assert list(conn.iterdump()) == before and old_rows(conn) == original
        assert not conn.in_transaction
        database._migrate_withholding_slips(conn)
        assert old_rows(conn) == original
    finally:
        conn.close()


@pytest.mark.parametrize("value", [-1, 1.5, "not-an-integer"])
def test_invalid_legacy_amount_is_not_repaired(tmp_path: Path, value: object) -> None:
    path = tmp_path / "invalid.db"
    make_legacy_withholding_db(path)
    conn = get_connection(str(path))
    try:
        conn.execute("UPDATE withholding_slips SET payment_amount=? WHERE id=7", (value,))
        conn.commit()
        before = list(conn.iterdump())
        with pytest.raises(sqlite3.IntegrityError):
            database._migrate_withholding_slips(conn)
        assert list(conn.iterdump()) == before
    finally:
        conn.close()


def test_empty_legacy_withholding_keeps_sequence(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    make_legacy_withholding_db(path)
    conn = get_connection(str(path))
    conn.execute("DELETE FROM withholding_slips")
    conn.commit()
    conn.close()
    conn = init_db(str(path))
    try:
        conn.execute("INSERT INTO withholding_slips (fiscal_year) VALUES (2026)")
        assert conn.execute("SELECT id FROM withholding_slips").fetchone()[0] == 901
    finally:
        conn.close()


@pytest.mark.parametrize(
    "condition", ["unknown_column", "existing_temp", "later_failure", "interrupt"]
)
def test_withholding_migration_retains_state_on_failure(
    tmp_path: Path, monkeypatch, condition: str
) -> None:
    path = tmp_path / "retained.db"
    make_legacy_withholding_db(path)
    conn = get_connection(str(path))
    if condition == "unknown_column":
        conn.execute("ALTER TABLE withholding_slips ADD COLUMN unknown TEXT")
    elif condition == "existing_temp":
        conn.execute("CREATE TABLE withholding_slips_migration(note TEXT)")
        conn.execute("INSERT INTO withholding_slips_migration VALUES('架空の残存値')")
    conn.commit()
    before = list(conn.iterdump())
    conn.close()
    if condition in {"later_failure", "interrupt"}:

        def fail(conn):
            database._migrate_withholding_slips(conn)
            if condition == "interrupt":
                raise KeyboardInterrupt("架空の移行中断")
            raise ValueError("架空の後続移行失敗")

        monkeypatch.setattr(database, "_migrate", fail)
    with pytest.raises((ValueError, sqlite3.DatabaseError, KeyboardInterrupt)):
        init_db(str(path))
    conn = get_connection(str(path))
    try:
        assert list(conn.iterdump()) == before
    finally:
        conn.close()
