"""Tests for duplicate detection logic."""

from __future__ import annotations

from pathlib import Path

from shinkoku.db import get_connection
from shinkoku.duplicate_detection import (
    check_duplicate_on_insert,
    check_source_file_imported,
    find_duplicate_pairs,
    record_import_source,
)
from shinkoku.hashing import compute_journal_hash
from shinkoku.models import JournalEntry, JournalLine
from shinkoku.tools.ledger import (
    ledger_add_journal,
    ledger_add_journals_batch,
    ledger_delete_journal,
    ledger_init,
    ledger_update_journal,
)


def _make_entry(
    date: str = "2025-01-15",
    debit_code: str = "1001",
    credit_code: str = "4001",
    amount: int = 10000,
    description: str | None = "test",
) -> JournalEntry:
    return JournalEntry(
        date=date,
        description=description,
        lines=[
            JournalLine(side="debit", account_code=debit_code, amount=amount),
            JournalLine(side="credit", account_code=credit_code, amount=amount),
        ],
    )


def _insert_journal(
    db, entry: JournalEntry, fiscal_year: int = 2025, include_hash: bool = True
) -> int:
    """Insert a journal entry directly into DB (bypassing duplicate check).

    include_hash=False simulates legacy data inserted before duplicate detection.
    """
    content_hash = compute_journal_hash(entry.date, entry.lines) if include_hash else None
    cursor = db.execute(
        "INSERT INTO journals (fiscal_year, date, description, content_hash) VALUES (?, ?, ?, ?)",
        (fiscal_year, entry.date, entry.description, content_hash),
    )
    journal_id = cursor.lastrowid
    for line in entry.lines:
        db.execute(
            "INSERT INTO journal_lines (journal_id, side, account_code, amount) "
            "VALUES (?, ?, ?, ?)",
            (journal_id, line.side, line.account_code, line.amount),
        )
    db.commit()
    return journal_id


def _init_file_db(tmp_path: Path) -> str:
    """Create a file-backed ledger DB for tool-level duplicate tests."""
    db_path = str(tmp_path / "force-duplicate.db")
    ledger_init(fiscal_year=2025, db_path=db_path)
    return db_path


def _trip_entry(description: str) -> JournalEntry:
    """Create one side of a same-day round-trip fare."""
    return _make_entry(
        date="2025-06-01",
        debit_code="5200",
        credit_code="1100",
        amount=220,
        description=description,
    )


def _add_anchor_and_forced_twin(db_path: str) -> tuple[int, int]:
    anchor = ledger_add_journal(
        db_path=db_path,
        fiscal_year=2025,
        entry=_trip_entry("電車賃（行き）"),
    )
    twin = ledger_add_journal(
        db_path=db_path,
        fiscal_year=2025,
        entry=_trip_entry("電車賃（帰り）"),
        force=True,
    )
    assert anchor["status"] == "ok"
    assert twin["status"] == "ok"
    return anchor["journal_id"], twin["journal_id"]


def _content_hash(db_path: str, journal_id: int) -> str | None:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT content_hash FROM journals WHERE id = ?", (journal_id,)
        ).fetchone()
        assert row is not None
        return row[0]
    finally:
        conn.close()


def _journal_count(db_path: str) -> int:
    conn = get_connection(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM journals").fetchone()[0]
    finally:
        conn.close()


class TestCheckDuplicateOnInsert:
    def test_exact_duplicate_detected(self, in_memory_db_with_accounts):
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry = _make_entry()
        _insert_journal(db, entry)

        # Same entry should be detected as exact duplicate
        warning = check_duplicate_on_insert(db, 2025, entry)
        assert warning is not None
        assert warning.match_type == "exact"
        assert warning.score == 100

    def test_similar_detected(self, in_memory_db_with_accounts):
        """Same date + same amount but different accounts -> similar."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry1 = _make_entry(debit_code="1001", credit_code="4001")
        _insert_journal(db, entry1)

        # Same date, same amount, different accounts
        entry2 = _make_entry(debit_code="5190", credit_code="1002")
        warning = check_duplicate_on_insert(db, 2025, entry2)
        assert warning is not None
        assert warning.match_type == "similar"
        assert warning.score == 70

    def test_no_duplicate_clean(self, in_memory_db_with_accounts):
        """Different entry should return None."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry1 = _make_entry(date="2025-01-15", amount=10000)
        _insert_journal(db, entry1)

        # Different date and amount
        entry2 = _make_entry(date="2025-02-15", amount=20000)
        warning = check_duplicate_on_insert(db, 2025, entry2)
        assert warning is None


class TestSourceFileCheck:
    def test_source_file_check(self, in_memory_db_with_accounts):
        """Record and re-check file import."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        file_hash = "abc123def456"

        # Not imported yet
        result = check_source_file_imported(db, 2025, file_hash)
        assert result is None

        # Record import
        source_id = record_import_source(
            db,
            2025,
            file_hash,
            "expenses.csv",
            file_path="/tmp/expenses.csv",
            row_count=10,
        )
        assert source_id > 0

        # Now should be detected
        result = check_source_file_imported(db, 2025, file_hash)
        assert result is not None
        assert result["file_name"] == "expenses.csv"


class TestFindDuplicatePairs:
    def test_find_duplicate_pairs_score90_independent_of_line_insertion_order(
        self, in_memory_db_with_accounts
    ):
        """同じ科目構成なら仕訳行の登録順が逆でもscore 90と判定する。"""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry1 = _make_entry(debit_code="1001", credit_code="4001")
        entry2 = _make_entry(debit_code="1001", credit_code="4001")
        entry2.lines.reverse()
        _insert_journal(db, entry1, include_hash=False)
        _insert_journal(db, entry2, include_hash=False)

        result = find_duplicate_pairs(db, 2025)

        assert len(result.pairs) == 1
        assert result.pairs[0].score == 90

    def test_find_duplicate_pairs_legacy_exact(self, in_memory_db_with_accounts):
        """Legacy entries (NULL hash) with identical content detected via date+amount+accounts."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry = _make_entry()
        # Legacy data: inserted without content_hash (before duplicate detection was added)
        id1 = _insert_journal(db, entry, include_hash=False)
        id2 = _insert_journal(db, entry, include_hash=False)

        result = find_duplicate_pairs(db, 2025)
        # Phase 2 detects same date + same amount + same accounts → score 90
        assert result.suspected_count >= 1
        high_score_pairs = [p for p in result.pairs if p.score >= 90]
        assert len(high_score_pairs) >= 1
        pair_ids = {(p.journal_id_a, p.journal_id_b) for p in high_score_pairs}
        assert (min(id1, id2), max(id1, id2)) in pair_ids

    def test_find_duplicate_pairs_similar(self, in_memory_db_with_accounts):
        """Same date/amount but different accounts -> score 70-90."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        entry1 = _make_entry(debit_code="1001", credit_code="4001")
        entry2 = _make_entry(debit_code="5190", credit_code="1002")
        _insert_journal(db, entry1)
        _insert_journal(db, entry2)

        result = find_duplicate_pairs(db, 2025)
        # Should find suspected pairs (same date + same debit total)
        assert result.suspected_count >= 1
        suspected = [p for p in result.pairs if 70 <= p.score < 100]
        assert len(suspected) >= 1

    def test_find_duplicate_pairs_threshold_filter(self, in_memory_db_with_accounts):
        """Threshold should filter out low-score pairs."""
        db = in_memory_db_with_accounts
        db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
        db.commit()

        # Two entries with same date/amount but different accounts -> score 70
        entry1 = _make_entry(debit_code="1001", credit_code="4001")
        entry2 = _make_entry(debit_code="5190", credit_code="1002")
        _insert_journal(db, entry1)
        _insert_journal(db, entry2)

        # With threshold 80, score 70 pairs should be filtered out
        result_high = find_duplicate_pairs(db, 2025, threshold=80)
        low_score = [p for p in result_high.pairs if p.score < 80]
        assert len(low_score) == 0

        # With threshold 60, score 70 pairs should be included
        result_low = find_duplicate_pairs(db, 2025, threshold=60)
        included = [p for p in result_low.pairs if p.score >= 60]
        assert len(included) >= 1


class TestForceInsertExactDuplicate:
    def test_add_exact_duplicate_without_force_returns_error_with_force_hint(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        first = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（行き）"),
        )

        result = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（帰り）"),
        )

        assert first["status"] == "ok"
        assert result["status"] == "error"
        assert result["duplicate"]["match_type"] == "exact"
        assert "force=True" in result["message"]

    def test_add_exact_duplicate_with_force_inserts_with_null_content_hash(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（行き）"),
        )
        twin = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（帰り）"),
            force=True,
        )

        assert anchor["status"] == "ok"
        assert twin["status"] == "ok"
        assert _content_hash(db_path, anchor["journal_id"]) is not None
        assert _content_hash(db_path, twin["journal_id"]) is None
        assert len(twin["warnings"]) == 1
        assert twin["warnings"][0]["match_type"] == "exact"
        assert twin["warnings"][0]["existing_journal_id"] == anchor["journal_id"]

    def test_third_copy_while_anchor_alive_is_blocked_as_exact(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor_id, _ = _add_anchor_and_forced_twin(db_path)

        result = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（3件目）"),
        )

        assert result["status"] == "error"
        assert result["duplicate"]["match_type"] == "exact"
        assert result["duplicate"]["existing_journal_id"] == anchor_id

    def test_third_copy_after_anchor_deleted_degrades_to_similar_warning(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor_id, _ = _add_anchor_and_forced_twin(db_path)
        deleted = ledger_delete_journal(db_path=db_path, journal_id=anchor_id)

        result = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（3件目）"),
        )

        assert deleted["status"] == "ok"
        assert result["status"] == "warning"
        assert result["duplicate"]["match_type"] == "similar"
        assert _journal_count(db_path) == 1

    def test_forced_twin_appears_as_similar_not_exact_in_check_duplicates(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor_id, twin_id = _add_anchor_and_forced_twin(db_path)
        conn = get_connection(db_path)
        try:
            result = find_duplicate_pairs(conn, 2025)
        finally:
            conn.close()

        assert result.exact_count == 0
        assert result.suspected_count == 1
        assert len(result.pairs) == 1
        assert result.pairs[0].score == 90
        assert {result.pairs[0].journal_id_a, result.pairs[0].journal_id_b} == {
            anchor_id,
            twin_id,
        }

    def test_batch_within_batch_duplicates_with_force_inserts_both_with_resolved_warning(
        self, tmp_path: Path
    ):
        db_path = _init_file_db(tmp_path)

        result = ledger_add_journals_batch(
            db_path=db_path,
            fiscal_year=2025,
            entries=[_trip_entry("電車賃（行き）"), _trip_entry("電車賃（帰り）")],
            force=True,
        )

        assert result["status"] == "ok"
        assert result["count"] == 2
        assert _content_hash(db_path, result["journal_ids"][0]) is not None
        assert _content_hash(db_path, result["journal_ids"][1]) is None
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["entry_index"] == 1
        assert warning["match_type"] == "exact"
        assert warning["existing_journal_id"] == result["journal_ids"][0]

    def test_batch_exact_against_existing_db_row_with_force(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor = ledger_add_journal(
            db_path=db_path,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（行き）"),
        )

        result = ledger_add_journals_batch(
            db_path=db_path,
            fiscal_year=2025,
            entries=[_trip_entry("電車賃（帰り）")],
            force=True,
        )

        assert result["status"] == "ok"
        assert result["count"] == 1
        assert _content_hash(db_path, result["journal_ids"][0]) is None
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["entry_index"] == 0
        assert warning["match_type"] == "exact"
        assert warning["existing_journal_id"] == anchor["journal_id"]

    def test_batch_within_batch_duplicates_without_force_blocked(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)

        result = ledger_add_journals_batch(
            db_path=db_path,
            fiscal_year=2025,
            entries=[_trip_entry("電車賃（行き）"), _trip_entry("電車賃（帰り）")],
        )

        assert result["status"] == "error"
        assert result["failed_index"] == 1
        assert _journal_count(db_path) == 0

    def test_update_collision_with_force_stores_null_hash_and_returns_warning(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        anchor_id, twin_id = _add_anchor_and_forced_twin(db_path)

        result = ledger_update_journal(
            db_path=db_path,
            journal_id=twin_id,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（帰り・摘要修正）"),
            force=True,
        )

        assert result["status"] == "ok"
        assert _content_hash(db_path, twin_id) is None
        assert len(result["warnings"]) == 1
        warning = result["warnings"][0]
        assert warning["match_type"] == "exact"
        assert warning["existing_journal_id"] == anchor_id

    def test_update_collision_without_force_returns_error(self, tmp_path: Path):
        db_path = _init_file_db(tmp_path)
        _, twin_id = _add_anchor_and_forced_twin(db_path)

        result = ledger_update_journal(
            db_path=db_path,
            journal_id=twin_id,
            fiscal_year=2025,
            entry=_trip_entry("電車賃（帰り・摘要修正）"),
        )

        assert result["status"] == "error"
        assert "force=True" in result["message"]
        assert _content_hash(db_path, twin_id) is None
