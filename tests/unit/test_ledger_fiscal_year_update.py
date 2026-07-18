"""仕訳更新時の年度変更と重複ハッシュ整合テスト。"""

from __future__ import annotations

from pathlib import Path

from shinkoku.db import get_connection
from shinkoku.hashing import compute_journal_hash
from shinkoku.models import JournalEntry, JournalLine
from shinkoku.tools.ledger import ledger_add_journal, ledger_init, ledger_update_journal


def _entry(*, amount: int = 10_000, description: str = "年度更新") -> JournalEntry:
    return JournalEntry(
        date="2025-12-31",
        description=description,
        lines=[
            JournalLine(side="debit", account_code="5200", amount=amount),
            JournalLine(side="credit", account_code="1100", amount=amount),
        ],
    )


def _init_db(tmp_path: Path, *, include_2026: bool = True) -> str:
    db_path = str(tmp_path / "fiscal-year-update.db")
    ledger_init(fiscal_year=2025, db_path=db_path)
    if include_2026:
        ledger_init(fiscal_year=2026, db_path=db_path)
    return db_path


def _stored_header(db_path: str, journal_id: int) -> tuple[int, str | None]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT fiscal_year, content_hash FROM journals WHERE id = ?",
            (journal_id,),
        ).fetchone()
        assert row is not None
        return row["fiscal_year"], row["content_hash"]
    finally:
        conn.close()


def _stored_amount(db_path: str, journal_id: int) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT amount FROM journal_lines WHERE journal_id = ? AND side = 'debit'",
            (journal_id,),
        ).fetchone()
        assert row is not None
        return row["amount"]
    finally:
        conn.close()


def test_update_journal_moves_entry_to_another_fiscal_year(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    entry = _entry()
    added = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=entry)

    result = ledger_update_journal(
        db_path=db_path,
        journal_id=added["journal_id"],
        fiscal_year=2026,
        entry=entry,
    )

    assert result["status"] == "ok"
    assert _stored_header(db_path, added["journal_id"])[0] == 2026


def test_update_journal_changes_fiscal_year_and_amount_together(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    added = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=_entry())

    result = ledger_update_journal(
        db_path=db_path,
        journal_id=added["journal_id"],
        fiscal_year=2026,
        entry=_entry(amount=25_000),
    )

    assert result["status"] == "ok"
    assert _stored_header(db_path, added["journal_id"])[0] == 2026
    assert _stored_amount(db_path, added["journal_id"]) == 25_000


def test_update_journal_keeps_fiscal_year_when_it_is_unchanged(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    added = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=_entry())

    result = ledger_update_journal(
        db_path=db_path,
        journal_id=added["journal_id"],
        fiscal_year=2025,
        entry=_entry(amount=30_000),
    )

    assert result["status"] == "ok"
    assert _stored_header(db_path, added["journal_id"])[0] == 2025
    assert _stored_amount(db_path, added["journal_id"]) == 30_000


def test_update_journal_checks_hash_collision_in_destination_year(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    entry = _entry()
    source = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=entry)
    destination = ledger_add_journal(db_path=db_path, fiscal_year=2026, entry=entry)

    blocked = ledger_update_journal(
        db_path=db_path,
        journal_id=source["journal_id"],
        fiscal_year=2026,
        entry=entry,
    )

    assert blocked["status"] == "error"
    assert str(destination["journal_id"]) in blocked["message"]
    assert _stored_header(db_path, source["journal_id"])[0] == 2025

    forced = ledger_update_journal(
        db_path=db_path,
        journal_id=source["journal_id"],
        fiscal_year=2026,
        entry=entry,
        force=True,
    )

    assert forced["status"] == "ok"
    assert _stored_header(db_path, source["journal_id"]) == (2026, None)


def test_moving_forced_twin_to_empty_year_restores_content_hash(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path)
    entry = _entry()
    anchor = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=entry)
    twin = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=entry, force=True)
    assert _stored_header(db_path, twin["journal_id"])[1] is None

    moved = ledger_update_journal(
        db_path=db_path,
        journal_id=twin["journal_id"],
        fiscal_year=2026,
        entry=entry,
    )

    assert anchor["status"] == "ok"
    assert moved["status"] == "ok"
    assert _stored_header(db_path, twin["journal_id"]) == (
        2026,
        compute_journal_hash(entry.date, entry.lines),
    )
    duplicate = ledger_add_journal(db_path=db_path, fiscal_year=2026, entry=entry)
    assert duplicate["status"] == "error"
    assert duplicate["duplicate"]["existing_journal_id"] == twin["journal_id"]


def test_update_journal_rejects_unknown_destination_year(tmp_path: Path) -> None:
    db_path = _init_db(tmp_path, include_2026=False)
    entry = _entry()
    added = ledger_add_journal(db_path=db_path, fiscal_year=2025, entry=entry)

    result = ledger_update_journal(
        db_path=db_path,
        journal_id=added["journal_id"],
        fiscal_year=2026,
        entry=entry,
    )

    assert result == {"status": "error", "message": "Fiscal year 2026 not found"}
    assert _stored_header(db_path, added["journal_id"])[0] == 2025
