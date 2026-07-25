"""スキル文書に記載したCLIコマンドの契約テスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from shinkoku.cli import build_parser
from tests.helpers.cli_contract import (
    DEPRECATED_COMMAND_NAMES,
    NON_COMMAND_EXCEPTIONS,
    CommandExclusion,
    SkillCommand,
    extract_markdown_commands,
    find_deprecated_command_names,
    find_legacy_wrappers,
    format_exclusions,
    format_violations,
    lint_skill_command,
    scan_skill_cli_contract,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _violation_kinds(command: str) -> set[tuple[str, str]]:
    violations, exclusion = lint_skill_command(
        SkillCommand(path="test.md", line=1, text=command),
        build_parser(),
    )
    assert exclusion is None
    return {(item.kind, item.detail) for item in violations}


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("shinkoku tax calc-furusato-limit --input a.json", set()),
        (
            "shinkoku tax furusato-limit --input a.json",
            {("unknown_command", "tax furusato-limit")},
        ),
        (
            "shinkoku ledger bs --db-path x --input q.json",
            {
                ("unknown_option", "--input"),
                ("missing_required_option", "--fiscal-year"),
            },
        ),
        ("shinkoku ledger bs --db-path x --fiscal-year 2026", set()),
        (
            "shinkoku ledger rd-add --db-path <path> --fiscal-year 2026 --input <file>",
            set(),
        ),
        (
            "shinkoku nosuchgroup foo",
            {("unknown_top_level", "nosuchgroup")},
        ),
        (
            "shinkoku ledger add-rent-detail --db-path x --input rent.json",
            {("unknown_command", "ledger add-rent-detail")},
        ),
    ],
)
def test_linter_contract_cases(command: str, expected: set[tuple[str, str]]) -> None:
    assert _violation_kinds(command) == expected


def test_linter_joins_backslash_continuations() -> None:
    markdown = """```bash
shinkoku import check-imported \\
  --db-path DB --file-path imported.csv
```
"""
    commands = extract_markdown_commands(markdown, "test.md")

    assert len(commands) == 1
    assert _violation_kinds(commands[0].text) == {("missing_required_option", "--fiscal-year")}


def test_linter_excludes_command_structure_placeholder() -> None:
    command = SkillCommand(
        path="test.md",
        line=1,
        text="shinkoku <subcommand> [args]",
    )

    violations, exclusion = lint_skill_command(command, build_parser())

    assert violations == ()
    assert exclusion == CommandExclusion(
        path="test.md",
        line=1,
        command="shinkoku <subcommand> [args]",
        reason="command_structure_placeholder",
    )


def test_deprecated_name_and_unknown_command_are_both_detected(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "sample"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "```bash\nshinkoku ledger add-rent-detail --db-path x --input rent.json\n```\n",
        encoding="utf-8",
    )

    scan = scan_skill_cli_contract(tmp_path, build_parser())
    deprecated = find_deprecated_command_names(tmp_path)

    assert {(item.kind, item.detail) for item in scan.violations} == {
        ("unknown_command", "ledger add-rent-detail")
    }
    assert [(item.name, item.matched_text) for item in deprecated] == [
        ("add-rent-detail", "add-rent-detail")
    ]


def test_skill_cli_commands_match_parser() -> None:
    scan = scan_skill_cli_contract(REPOSITORY_ROOT, build_parser())

    assert not scan.violations, format_violations(scan.violations)


def test_non_command_exceptions_are_explicit_and_current() -> None:
    scan = scan_skill_cli_contract(REPOSITORY_ROOT, build_parser())

    assert set(scan.exceptions) == set(NON_COMMAND_EXCEPTIONS)


def test_skill_cli_exclusions_are_explicit() -> None:
    scan = scan_skill_cli_contract(REPOSITORY_ROOT, build_parser())
    expected = {
        (
            "skills/journal/SKILL.md",
            "command_structure_placeholder",
            "shinkoku ledger <subcommand> [args]",
        ),
        (
            "skills/journal/SKILL.md",
            "command_structure_placeholder",
            "shinkoku import <subcommand> [args]",
        ),
        (
            "skills/furusato/SKILL.md",
            "optional_bracket_syntax",
            "shinkoku furusato summary --db-path DB --fiscal-year YEAR [--estimated-limit N]",
        ),
    }

    actual = {(item.path, item.reason, item.command) for item in scan.exclusions}
    assert actual == expected, format_exclusions(scan.exclusions)


def test_skill_docs_do_not_use_deprecated_command_names() -> None:
    occurrences = find_deprecated_command_names(REPOSITORY_ROOT)
    details = "\n".join(
        f"{item.path}:{item.line}: {item.name}: {item.matched_text}" for item in occurrences
    )

    assert len(DEPRECATED_COMMAND_NAMES) == 31
    assert not occurrences, details


def test_skill_docs_do_not_use_legacy_python_wrappers() -> None:
    occurrences = find_legacy_wrappers(REPOSITORY_ROOT)
    details = "\n".join(f"{item.path}:{item.line}: {item.matched_text}" for item in occurrences)

    assert not occurrences, details
