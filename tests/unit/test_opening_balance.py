"""Tests for opening balance CRUD and BS integration."""

from __future__ import annotations

from pathlib import Path

from shinkoku.models import JournalEntry, JournalLine, OpeningBalanceInput
from shinkoku.tools.ledger import (
    ledger_add_journal,
    ledger_bs,
    ledger_delete_opening_balance,
    ledger_general_ledger,
    ledger_list_opening_balances,
    ledger_set_opening_balance,
    ledger_set_opening_balances_batch,
)


def test_set_opening_balance_insert(tmp_path, in_memory_db_with_accounts):
    """新規登録ができること。"""
    db = in_memory_db_with_accounts
    db.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    db.commit()
    db_path = str(tmp_path / "ob_test.db")
    # in_memory_db は使えないので、実ファイルで再現
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    detail = OpeningBalanceInput(account_code="1001", amount=500000)
    result = ledger_set_opening_balance(db_path=db_path, fiscal_year=2025, detail=detail)
    assert result["status"] == "ok"
    assert result["account_code"] == "1001"

    # 確認
    listed = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    assert listed["count"] == 1
    assert listed["records"][0]["amount"] == 500000


def test_set_opening_balance_upsert(tmp_path):
    """同一科目の上書きができること。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_upsert.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    detail1 = OpeningBalanceInput(account_code="1001", amount=100000)
    ledger_set_opening_balance(db_path=db_path, fiscal_year=2025, detail=detail1)

    detail2 = OpeningBalanceInput(account_code="1001", amount=200000)
    result = ledger_set_opening_balance(db_path=db_path, fiscal_year=2025, detail=detail2)
    assert result["status"] == "ok"

    listed = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    assert listed["count"] == 1
    assert listed["records"][0]["amount"] == 200000


def test_list_opening_balances(tmp_path):
    """一覧取得ができること。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_list.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    balances = [
        OpeningBalanceInput(account_code="1001", amount=100000),
        OpeningBalanceInput(account_code="1002", amount=300000),
    ]
    ledger_set_opening_balances_batch(db_path=db_path, fiscal_year=2025, balances=balances)

    result = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    assert result["status"] == "ok"
    assert result["count"] == 2
    assert result["records"][0]["account_code"] == "1001"
    assert result["records"][1]["account_code"] == "1002"


def test_delete_opening_balance(tmp_path):
    """削除ができること。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_delete.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    detail = OpeningBalanceInput(account_code="1001", amount=100000)
    ledger_set_opening_balance(db_path=db_path, fiscal_year=2025, detail=detail)

    listed = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    ob_id = listed["records"][0]["id"]

    result = ledger_delete_opening_balance(db_path=db_path, opening_balance_id=ob_id)
    assert result["status"] == "ok"

    listed2 = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    assert listed2["count"] == 0


def test_delete_opening_balance_not_found(tmp_path):
    """存在しないIDの削除はエラーになること。"""
    from shinkoku.db import init_db

    db_path = str(tmp_path / "ob_notfound.db")
    conn = init_db(db_path)
    conn.close()

    result = ledger_delete_opening_balance(db_path=db_path, opening_balance_id=999)
    assert result["status"] == "error"


def test_set_opening_balances_batch(tmp_path):
    """一括登録ができること。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_batch.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    balances = [
        OpeningBalanceInput(account_code="1001", amount=100000),
        OpeningBalanceInput(account_code="1002", amount=200000),
        OpeningBalanceInput(account_code="2001", amount=50000),
    ]
    result = ledger_set_opening_balances_batch(db_path=db_path, fiscal_year=2025, balances=balances)
    assert result["status"] == "ok"
    assert result["count"] == 3

    listed = ledger_list_opening_balances(db_path=db_path, fiscal_year=2025)
    assert listed["count"] == 3


def test_ledger_bs_includes_opening_balances(tmp_path):
    """ledger_bs() が期首データを返すこと。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_bs.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    # 期首残高を設定
    balances = [
        OpeningBalanceInput(account_code="1001", amount=100000),  # 現金（資産）
        OpeningBalanceInput(account_code="2001", amount=50000),  # 買掛金（負債）
        OpeningBalanceInput(account_code="3001", amount=50000),  # 元入金（純資産）
    ]
    ledger_set_opening_balances_batch(db_path=db_path, fiscal_year=2025, balances=balances)

    result = ledger_bs(db_path=db_path, fiscal_year=2025)
    assert result["status"] == "ok"

    # 期首データが含まれること
    assert len(result["opening_assets"]) == 1
    assert result["opening_assets"][0]["account_code"] == "1001"
    assert result["opening_assets"][0]["amount"] == 100000
    assert result["opening_total_assets"] == 100000

    assert len(result["opening_liabilities"]) == 1
    assert result["opening_liabilities"][0]["amount"] == 50000
    assert result["opening_total_liabilities"] == 50000

    assert len(result["opening_equity"]) == 1
    assert result["opening_equity"][0]["amount"] == 50000
    assert result["opening_total_equity"] == 50000


def test_ledger_bs_no_opening_balances(tmp_path):
    """期首データ未登録時は空リストを返すこと。"""
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / "ob_empty.db")
    conn = init_db(db_path)
    for a in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (a["code"], a["name"], a["category"], a["sub_category"], a["tax_category"]),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()

    result = ledger_bs(db_path=db_path, fiscal_year=2025)
    assert result["status"] == "ok"
    assert result["opening_assets"] == []
    assert result["opening_liabilities"] == []
    assert result["opening_equity"] == []
    assert result["opening_total_assets"] == 0
    assert result["opening_total_liabilities"] == 0
    assert result["opening_total_equity"] == 0


def _create_bs_test_db(tmp_path: Path, name: str) -> str:
    from shinkoku.db import init_db
    from shinkoku.master_accounts import MASTER_ACCOUNTS

    db_path = str(tmp_path / name)
    conn = init_db(db_path)
    for account in MASTER_ACCOUNTS:
        conn.execute(
            "INSERT OR IGNORE INTO accounts (code, name, category, sub_category, tax_category) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                account["code"],
                account["name"],
                account["category"],
                account["sub_category"],
                account["tax_category"],
            ),
        )
    conn.execute("INSERT INTO fiscal_years (year) VALUES (2025)")
    conn.commit()
    conn.close()
    return db_path


def _set_bs_opening_balances(db_path: str, balances: list[tuple[str, int]]) -> None:
    result = ledger_set_opening_balances_batch(
        db_path=db_path,
        fiscal_year=2025,
        balances=[
            OpeningBalanceInput(account_code=account_code, amount=amount)
            for account_code, amount in balances
        ],
    )
    assert result["status"] == "ok"


def _add_bs_journal(db_path: str, *, debit_code: str, credit_code: str, amount: int) -> None:
    result = ledger_add_journal(
        db_path=db_path,
        fiscal_year=2025,
        entry=JournalEntry(
            date="2025-06-30",
            description="BS期末残高テスト",
            lines=[
                JournalLine(side="debit", account_code=debit_code, amount=amount),
                JournalLine(side="credit", account_code=credit_code, amount=amount),
            ],
        ),
    )
    assert result["status"] == "ok"


def _bs_amount(items: list[dict], account_code: str) -> int:
    return next(item["amount"] for item in items if item["account_code"] == account_code)


def _setup_basic_bs_case(tmp_path: Path) -> str:
    db_path = _create_bs_test_db(tmp_path, "bs_basic.db")
    _set_bs_opening_balances(db_path, [("1002", 1_000_000), ("3001", 1_000_000)])
    _add_bs_journal(db_path, debit_code="1002", credit_code="4001", amount=200_000)
    return db_path


class TestBSClosingBalance:
    def test_bs_closing_asset_balance_includes_opening_balance(self, tmp_path: Path) -> None:
        """期首100万円と当期入金20万円から普通預金の期末残高を求める。"""
        db_path = _setup_basic_bs_case(tmp_path)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert _bs_amount(result["assets"], "1002") == 1_200_000
        assert result["total_assets"] == 1_200_000

    def test_bs_closing_equity_includes_opening_capital(self, tmp_path: Path) -> None:
        """元入金の期首残高を純資産の期末残高と合計へ反映する。"""
        db_path = _setup_basic_bs_case(tmp_path)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)
        equity_total = sum(item["amount"] for item in result["equity"])

        assert _bs_amount(result["equity"], "3001") == 1_000_000
        assert equity_total == 1_000_000
        assert result["net_income"] == 200_000
        assert result["total_equity"] == 1_200_000
        assert result["total_equity"] - equity_total == result["net_income"]

    def test_bs_closing_liability_includes_opening_balance(self, tmp_path: Path) -> None:
        """買掛金の期首30万円から当期支払10万円を引いて期末20万円とする。"""
        db_path = _create_bs_test_db(tmp_path, "bs_liability.db")
        _set_bs_opening_balances(db_path, [("1002", 300_000), ("2001", 300_000)])
        _add_bs_journal(db_path, debit_code="2001", credit_code="1002", amount=100_000)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert _bs_amount(result["liabilities"], "2001") == 200_000
        assert result["total_liabilities"] == 200_000
        assert _bs_amount(result["assets"], "1002") == 200_000
        assert result["total_assets"] == 200_000

    def test_bs_account_with_opening_only_appears_on_closing_bs(self, tmp_path: Path) -> None:
        """当期仕訳がない工具器具備品も期首残高を期末BSへ載せる。"""
        db_path = _create_bs_test_db(tmp_path, "bs_opening_only.db")
        _set_bs_opening_balances(db_path, [("1130", 300_000), ("3001", 300_000)])

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert _bs_amount(result["assets"], "1130") == 300_000
        assert result["total_assets"] == 300_000
        assert _bs_amount(result["equity"], "3001") == 300_000
        assert result["total_equity"] == 300_000

    def test_bs_balance_equation_and_absolute_totals(self, tmp_path: Path) -> None:
        """貸借一致に加え、期首を含む絶対額も検証する。"""
        db_path = _setup_basic_bs_case(tmp_path)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert result["total_assets"] == 1_200_000
        assert result["total_liabilities"] == 0
        assert result["total_equity"] == 1_200_000
        assert result["total_assets"] == result["total_liabilities"] + result["total_equity"]

    def test_bs_closing_matches_general_ledger_closing(self, tmp_path: Path) -> None:
        """資産と純資産の期末残高を総勘定元帳と一致させる。"""
        db_path = _setup_basic_bs_case(tmp_path)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)
        asset_ledger = ledger_general_ledger(db_path=db_path, fiscal_year=2025, account_code="1002")
        equity_ledger = ledger_general_ledger(
            db_path=db_path, fiscal_year=2025, account_code="3001"
        )

        assert _bs_amount(result["assets"], "1002") == asset_ledger["closing_balance"]
        assert _bs_amount(result["equity"], "3001") == equity_ledger["closing_balance"]
        assert asset_ledger["closing_balance"] == 1_200_000
        assert equity_ledger["closing_balance"] == 1_000_000

    def test_bs_account_netting_to_zero_excluded_from_closing(self, tmp_path: Path) -> None:
        """期首残高を全額支払って0円になった資産と負債を期末BSから除く。"""
        db_path = _create_bs_test_db(tmp_path, "bs_zero.db")
        _set_bs_opening_balances(db_path, [("1002", 50_000), ("2030", 50_000)])
        _add_bs_journal(db_path, debit_code="2030", credit_code="1002", amount=50_000)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert all(item["account_code"] != "1002" for item in result["assets"])
        assert all(item["account_code"] != "2030" for item in result["liabilities"])
        assert result["total_assets"] == 0
        assert result["total_liabilities"] == 0

    def test_bs_without_opening_balances_behaves_as_before(self, tmp_path: Path) -> None:
        """期首未設定では当期増減を従来どおり返す。"""
        db_path = _create_bs_test_db(tmp_path, "bs_no_opening.db")
        _add_bs_journal(db_path, debit_code="1002", credit_code="4001", amount=200_000)

        result = ledger_bs(db_path=db_path, fiscal_year=2025)

        assert _bs_amount(result["assets"], "1002") == 200_000
        assert result["total_assets"] == 200_000
        assert result["equity"] == []
        assert result["net_income"] == 200_000
        assert result["total_equity"] == 200_000
        assert result["opening_assets"] == []
        assert result["opening_liabilities"] == []
        assert result["opening_equity"] == []
