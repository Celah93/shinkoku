"""源泉徴収票の保存列と、失敗した訂正の保持を検証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from shinkoku.db import get_connection
from shinkoku.models import WithholdingSlipData, WithholdingSlipInput, WithholdingSlipRecord
from shinkoku.tools.ledger import ledger_init, ledger_save_withholding_slip
from tests.helpers.withholding import withholding_input


@pytest.mark.parametrize(
    "model,extra",
    [
        (WithholdingSlipData, {"file_path": "fictional.pdf", "extracted_text": "架空"}),
        (WithholdingSlipRecord, {"id": 999, "fiscal_year": 2025}),
    ],
)
def test_save_subclass_only_writes_common_input_columns(tmp_path: Path, model, extra) -> None:
    db = str(tmp_path / "subclass.db")
    ledger_init(db_path=db, fiscal_year=2025)
    saved = ledger_save_withholding_slip(
        db_path=db, fiscal_year=2025, detail=model(**withholding_input(), **extra)
    )
    assert saved["status"] == "ok"
    assert saved["withholding_slip_id"] == 1


def test_update_ignored_by_trigger_is_not_success_and_is_rolled_back(tmp_path: Path) -> None:
    db = str(tmp_path / "ignored.db")
    ledger_init(db_path=db, fiscal_year=2025)
    detail = WithholdingSlipInput(**withholding_input())
    saved = ledger_save_withholding_slip(db_path=db, fiscal_year=2025, detail=detail)
    conn = get_connection(db)
    conn.execute(
        "CREATE TRIGGER ignore_ws_update BEFORE UPDATE ON withholding_slips BEGIN DELETE FROM withholding_slips WHERE id=OLD.id; SELECT RAISE(IGNORE); END"
    )
    conn.commit()
    before = list(conn.iterdump())
    conn.close()
    updated = ledger_save_withholding_slip(
        db_path=db,
        fiscal_year=2025,
        detail=detail,
        withholding_slip_id=saved["withholding_slip_id"],
    )
    assert updated["status"] == "error"
    conn = get_connection(db)
    assert list(conn.iterdump()) == before
    conn.close()
