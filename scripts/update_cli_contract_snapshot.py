"""CLI契約スナップショットを明示操作で更新する。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from shinkoku.cli import build_parser  # noqa: E402
from tests.helpers.cli_contract import write_parser_contract_snapshot  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="CLI契約スナップショットを更新します")
    parser.add_argument(
        "--update",
        action="store_true",
        required=True,
        help="契約変更を確認したうえでスナップショットを更新する",
    )
    parser.parse_args()

    destination = REPOSITORY_ROOT / "tests" / "fixtures" / "cli_contract.json"
    write_parser_contract_snapshot(build_parser(), destination)
    print(f"updated: {destination}")


if __name__ == "__main__":
    main()
