"""非空の旧台帳を、推測による確認やデータ損失なしで移行する。"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

import shinkoku.db as database
from shinkoku.db import _migrate_fixed_assets, get_connection, init_db
from tests.helpers.fixed_assets import LEGACY_COLUMNS, make_legacy_asset_db


def _rows(conn: sqlite3.Connection) -> list[tuple]:
    return [
        tuple(row)
        for row in conn.execute(f"SELECT {', '.join(LEGACY_COLUMNS)} FROM fixed_assets ORDER BY id")
    ]


def test_nonempty_multiple_years_keep_all_values_ids_and_sequence(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    original = make_legacy_asset_db(path)
    conn = init_db(str(path))
    try:
        assert _rows(conn) == original
        # 旧デフォルトの定額法・100％・累計0を確認済みへ昇格させない。
        assert original[0][5:8] == ("straight_line", 100, 0)
        added = {row[1] for row in conn.execute("PRAGMA table_info(fixed_assets)")} - set(
            LEGACY_COLUMNS
        )
        assert added
        for row in conn.execute("SELECT * FROM fixed_assets"):
            assert all(row[key] is None for key in added)
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
        assert (
            conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'fixed_assets'").fetchone()[
                0
            ]
            == 900
        )
        conn.execute(
            "INSERT INTO fixed_assets (name, acquisition_date, acquisition_cost, fiscal_year) "
            "VALUES ('移行後の架空資産', '2026-06-01', 200000, 2026)"
        )
        row = conn.execute("SELECT * FROM fixed_assets WHERE id = 901").fetchone()
        assert row is not None
        for key in ("method", "useful_life", "business_use_ratio", "accumulated_depreciation"):
            assert row[key] is None
        conn.commit()
        before = list(conn.iterdump())
    finally:
        conn.close()
    conn = init_db(str(path))
    try:
        assert list(conn.iterdump()) == before
        tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert not any(name.startswith("fixed_asset_") for name in tables)
    finally:
        conn.close()


@pytest.mark.parametrize("failure", ["copy", "drop", "rename", "index"])
def test_interrupted_migration_rolls_back_schema_values_and_ids(
    tmp_path: Path, failure: str
) -> None:
    path = tmp_path / "interrupted.db"
    original = make_legacy_asset_db(path)
    conn = get_connection(str(path))
    old_schema = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name = 'fixed_assets'"
    ).fetchone()[0]
    interrupted = False

    def authorizer(action: int, first: str | None, second: str | None, *_: object) -> int:
        nonlocal interrupted
        targets = {
            "copy": action == sqlite3.SQLITE_INSERT and first == "fixed_assets_migration",
            "drop": action == sqlite3.SQLITE_DROP_TABLE and first == "fixed_assets",
            "rename": action == sqlite3.SQLITE_ALTER_TABLE and second == "fixed_assets_migration",
            "index": action == sqlite3.SQLITE_CREATE_INDEX
            and first == "idx_fixed_assets_fiscal_year",
        }
        if targets[failure] and not interrupted:
            interrupted = True
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK

    try:
        conn.set_authorizer(authorizer)
        with pytest.raises(sqlite3.DatabaseError):
            _migrate_fixed_assets(conn)
        conn.set_authorizer(None)
        assert interrupted
        assert _rows(conn) == original
        assert (
            conn.execute("SELECT sql FROM sqlite_master WHERE name = 'fixed_assets'").fetchone()[0]
            == old_schema
        )
        assert (
            conn.execute(
                "SELECT name FROM sqlite_master WHERE name = 'fixed_assets_migration'"
            ).fetchone()
            is None
        )
        assert (
            conn.execute("SELECT seq FROM sqlite_sequence WHERE name = 'fixed_assets'").fetchone()[
                0
            ]
            == 900
        )
        assert not conn.in_transaction
        _migrate_fixed_assets(conn)
        assert _rows(conn) == original
    finally:
        conn.close()


def test_failed_init_closes_connection_and_allows_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "failed-init.db"
    original = make_legacy_asset_db(path)
    opened = []

    def fail(conn: sqlite3.Connection) -> None:
        opened.append(conn)
        raise KeyboardInterrupt("架空の移行中断")

    with monkeypatch.context() as patch:
        patch.setattr(database, "_migrate_fixed_assets", fail)
        with pytest.raises(KeyboardInterrupt):
            init_db(str(path))
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].execute("SELECT 1")
    conn = init_db(str(path))
    try:
        assert _rows(conn) == original
    finally:
        conn.close()


def test_invalid_legacy_value_is_not_silently_repaired(tmp_path: Path) -> None:
    path = tmp_path / "invalid.db"
    make_legacy_asset_db(path)
    conn = get_connection(str(path))
    try:
        conn.execute("UPDATE fixed_assets SET acquisition_cost = -1 WHERE id = 7")
        conn.commit()
        original = _rows(conn)
        with pytest.raises(sqlite3.IntegrityError):
            _migrate_fixed_assets(conn)
        assert _rows(conn) == original
        assert "asset_uid" not in {
            row[1] for row in conn.execute("PRAGMA table_info(fixed_assets)")
        }
    finally:
        conn.close()


def test_failure_after_asset_migration_keeps_the_old_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "later-failure.db"
    original = make_legacy_asset_db(path)

    def fail_after_assets(conn: sqlite3.Connection) -> None:
        _migrate_fixed_assets(conn)
        raise KeyboardInterrupt("架空の後続移行中断")

    with monkeypatch.context() as patch:
        patch.setattr(database, "_migrate", fail_after_assets)
        with pytest.raises(KeyboardInterrupt):
            init_db(str(path))
    conn = get_connection(str(path))
    try:
        assert {row[1] for row in conn.execute("PRAGMA table_info(fixed_assets)")} == set(
            LEGACY_COLUMNS
        )
        assert _rows(conn) == original
    finally:
        conn.close()


def test_empty_legacy_table_keeps_deleted_id_high_water_mark(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    make_legacy_asset_db(path)
    conn = get_connection(str(path))
    try:
        conn.execute("DELETE FROM fixed_assets")
        conn.commit()
    finally:
        conn.close()
    conn = init_db(str(path))
    try:
        conn.execute(
            "INSERT INTO fixed_assets (name, acquisition_date, acquisition_cost, fiscal_year) "
            "VALUES ('架空資産', '2026-01-01', 100000, 2026)"
        )
        assert conn.execute("SELECT id FROM fixed_assets").fetchone()[0] == 901
    finally:
        conn.close()


def test_uid_year_uniqueness_and_previous_year_fk(tmp_path: Path) -> None:
    path = tmp_path / "constraints.db"
    make_legacy_asset_db(path)
    conn = init_db(str(path))
    try:
        conn.execute("UPDATE fixed_assets SET asset_uid = 'fictional-pc'")
        conn.execute("UPDATE fixed_assets SET previous_asset_id = 7 WHERE id = 42")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM fixed_assets WHERE id = 7")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE fixed_assets SET fiscal_year = 2025 WHERE id = 42")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE fixed_assets SET asset_account_code = 'missing' WHERE id = 42")
        assert not conn.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        conn.close()


def test_existing_migration_table_is_not_reused_or_discarded(tmp_path: Path) -> None:
    path = tmp_path / "unexpected-table.db"
    original = make_legacy_asset_db(path)
    conn = get_connection(str(path))
    try:
        conn.execute("CREATE TABLE fixed_assets_migration (note TEXT)")
        conn.execute("INSERT INTO fixed_assets_migration VALUES ('架空の残存データ')")
        conn.commit()
        with pytest.raises(sqlite3.OperationalError, match="already exists"):
            _migrate_fixed_assets(conn)
        assert _rows(conn) == original
        assert (
            conn.execute("SELECT note FROM fixed_assets_migration").fetchone()[0]
            == "架空の残存データ"
        )
    finally:
        conn.close()
