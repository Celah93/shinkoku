"""源泉徴収票の独立した架空入力を読み込む。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parents[1] / "fixtures/withholding"


def withholding_input(name: str = "2025-specific", **changes: Any) -> dict:
    data = json.loads((FIXTURES / name / "input.json").read_text(encoding="utf-8"))
    return {**data, **changes}
