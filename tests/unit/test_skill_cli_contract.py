"""スキル文書に記載したCLIコマンドの契約テスト。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from shinkoku.cli import build_parser
from shinkoku.cli.ledger import cmd_lc_add
from shinkoku.models import JournalEntry, OpeningBalanceInput, LossCarryforwardInput
from tests.helpers.cli_contract import (
    DEPRECATED_COMMAND_NAMES,
    NON_COMMAND_EXCEPTIONS,
    SKILL_JSON_INPUT_MODELS,
    CommandExclusion,
    SkillCommand,
    derive_ledger_json_input_models,
    extract_markdown_commands,
    extract_markdown_json_examples,
    find_deprecated_command_names,
    find_legacy_wrappers,
    format_exclusions,
    format_violations,
    lint_skill_command,
    iter_leaf_parsers,
    scan_skill_cli_contract,
    scan_skill_json_contract,
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


def test_skill_json_examples_match_cli_input_models() -> None:
    scan = scan_skill_json_contract(REPOSITORY_ROOT)

    assert scan.examples, "SkillのJSON例を一つも検査していません"
    assert not scan.violations, format_violations(scan.violations)


def test_all_ledger_input_commands_have_derived_validators() -> None:
    parser = build_parser()
    expected = {
        path
        for path, leaf in iter_leaf_parsers(parser)
        if path[0] == "ledger"
        and any("--input" in action.option_strings for action in leaf._actions)
    }

    assert set(derive_ledger_json_input_models(parser)) == expected
    assert set(SKILL_JSON_INPUT_MODELS) == expected


def _parser_with_input_handler(handler: object) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    ledger = parser.add_subparsers().add_parser("ledger")
    command = ledger.add_subparsers().add_parser("future-command")
    command.add_argument("--input", required=True)
    command.set_defaults(func=handler)
    return parser


def test_new_ledger_command_is_derived_without_a_manual_map_entry() -> None:
    parser = _parser_with_input_handler(cmd_lc_add)

    assert derive_ledger_json_input_models(parser) == {
        ("ledger", "future-command"): LossCarryforwardInput,
    }


def _handler_without_input_model(args: argparse.Namespace) -> dict:
    return json.loads(Path(args.input).read_text(encoding="utf-8"))


def test_unrecognised_handler_fails_instead_of_being_excluded() -> None:
    parser = _parser_with_input_handler(_handler_without_input_model)

    with pytest.raises(ValueError, match="ledger future-command.*導出できません"):
        derive_ledger_json_input_models(parser)


@pytest.mark.parametrize(
    ("command", "item", "item_type"),
    [
        ("ob-set-batch", {"account_code": "1002", "amount": 1000}, OpeningBalanceInput),
        (
            "journal-batch-add",
            {
                "date": "2026-01-01",
                "lines": [
                    {"side": "debit", "account_code": "5190", "amount": 1000},
                    {"side": "credit", "account_code": "1002", "amount": 1000},
                ],
            },
            JournalEntry,
        ),
    ],
)
def test_batch_input_models_are_derived_as_arrays(
    command: str, item: dict, item_type: type
) -> None:
    validator = SKILL_JSON_INPUT_MODELS[("ledger", command)]
    assert isinstance(validator, TypeAdapter)
    assert isinstance(validator.validate_python([item], strict=True)[0], item_type)
    with pytest.raises(ValidationError):
        validator.validate_python(item, strict=True)


@pytest.mark.parametrize(
    ("payload", "valid"),
    [
        ('{"taxpayer_status": "taxable"}', True),
        ('{"fiscal_year": 2026, "detail": {"taxpayer_status": "taxable"}}', False),
    ],
)
def test_optional_patch_model_does_not_silently_drop_wrapper_keys(
    tmp_path: Path, payload: str, valid: bool
) -> None:
    skill = tmp_path / "skills" / "example.md"
    skill.parent.mkdir()
    skill.write_text(
        "`shinkoku ledger fiscal-year-update --db-path DB --fiscal-year 2026 --input patch.json`\n"
        f"```json\n{payload}\n```\n",
        encoding="utf-8",
    )

    scan = scan_skill_json_contract(tmp_path)

    assert len(scan.examples) == 1
    assert (len(scan.violations) == 0) is valid
    if not valid:
        assert "detail" in scan.violations[0].detail
        assert "fiscal_year" in scan.violations[0].detail


@pytest.mark.parametrize("fence", ["```", "~~~"])
@pytest.mark.parametrize("inline", [True, False])
def test_json_examples_bind_to_inline_and_fenced_commands(fence: str, inline: bool) -> None:
    command = "shinkoku ledger si-add --db-path DB --fiscal-year 2026 --input si.json"
    invocation = f"2. `{command}` で登録する。" if inline else f"{fence}bash\n{command}\n{fence}"
    markdown = f"### 社会保険料\n{invocation}\n   {fence}json\n   {{}}\n   {fence}\n"

    examples = extract_markdown_json_examples(markdown, "skills/sample/references/input.md")

    assert len(examples) == 1
    assert examples[0].command_path == ("ledger", "si-add")
    assert examples[0].command.text == command
    assert examples[0].line == (4 if inline else 6)
    assert json.loads(examples[0].text) == {}


@pytest.mark.parametrize(
    "boundary",
    [
        "### 別の節",
        "`shinkoku ledger si-list --db-path DB --fiscal-year 2026`",
        "`shinkoku tax calc-deductions --input deductions.json`",
    ],
)
def test_json_examples_do_not_cross_sections_or_other_commands(boundary: str) -> None:
    markdown = (
        "`shinkoku ledger si-add --db-path DB --fiscal-year 2026 --input si.json`\n"
        f"{boundary}\n```json\n{{}}\n```\n"
    )

    assert extract_markdown_json_examples(markdown, "sample.md") == ()


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ('{"insurance_type": "national_health", "name": "架空", "amount": 300000}', None),
        (
            '{"fiscal_year": 2026, "detail": {"insurance_type": "national_health", '
            '"name": "架空", "amount": 300000}}',
            "invalid_json_input",
        ),
        (
            '{"insurance_type": "national_health", "name": "架空", "amount": "300000"}',
            "invalid_json_input",
        ),
        (
            '{"insurance_type": "national_health", "name": "架空", "amount": true}',
            "invalid_json_input",
        ),
        (
            '{"insurance_type": "national_health", "name": "架空", "amount": -1}',
            "invalid_json_input",
        ),
        ('{"insurance_type": "national_health",}', "invalid_json"),
    ],
)
def test_json_scanner_checks_nested_references_and_strict_inputs(
    tmp_path: Path, payload: str, kind: str | None
) -> None:
    skill = tmp_path / "skills" / "another-skill" / "references" / "example.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "`shinkoku ledger si-add --db-path DB --fiscal-year 2026 --input si.json`\n"
        f"```json\n{payload}\n```\n",
        encoding="utf-8",
    )

    scan = scan_skill_json_contract(tmp_path)

    assert len(scan.examples) == 1
    assert [v.kind for v in scan.violations] == ([] if kind is None else [kind])
    if scan.violations:
        assert scan.violations[0].path == "skills/another-skill/references/example.md"
        assert scan.violations[0].line == 3


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
