"""CLI parserとスキル文書のコマンド契約を検査するヘルパー。"""

from __future__ import annotations

import argparse
import json
import re
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


EXPECTED_LEAF_COMMAND_COUNT = 104


@dataclass(frozen=True)
class SkillCommand:
    """Markdownから抽出したコマンド候補。"""

    path: str
    line: int
    text: str


@dataclass(frozen=True)
class ContractViolation:
    """CLI契約に反するコマンド記載。"""

    path: str
    line: int
    command: str
    kind: str
    detail: str


@dataclass(frozen=True)
class CommandExclusion:
    """構文上の理由を明示して検査対象外にしたコマンド記載。"""

    path: str
    line: int
    command: str
    reason: str


@dataclass(frozen=True)
class NonCommandException:
    """コマンドの形に見えるが実行例ではない既知の記載。"""

    path: str
    text: str
    reason: str


@dataclass(frozen=True)
class DeprecatedOccurrence:
    """廃止済みコマンド名または旧ラッパー形式の出現箇所。"""

    name: str
    path: str
    line: int
    matched_text: str


@dataclass(frozen=True)
class SkillContractScan:
    """スキル文書全体の契約検査結果。"""

    commands: tuple[SkillCommand, ...]
    violations: tuple[ContractViolation, ...]
    exclusions: tuple[CommandExclusion, ...]
    exceptions: tuple[NonCommandException, ...]


# fenced block内の案内文2件と、コマンド名だけを示す説明1件。
# 暗黙の抽出規則で除かず、内容が変わったら例外が古くなったと分かるよう完全一致にする。
NON_COMMAND_EXCEPTIONS = (
    NonCommandException(
        path="skills/capabilities/SKILL.md",
        text="shinkoku では {ペルソナ名} の確定申告には対応していません。",
        reason="Out対応ペルソナへ返す案内文であり、CLI実行例ではない",
    ),
    NonCommandException(
        path="skills/e-bookkeeping-compliance/SKILL.md",
        text="shinkoku は優良な電子帳簿の要件（施行規則第5条第5項）を",
        reason="診断結果の文章であり、CLI実行例ではない",
    ),
    NonCommandException(
        path="skills/furusato/references/furusato-consultation-guide.md",
        text="shinkoku furusato summary",
        reason="本文中でコマンド名だけを示す説明であり、実行例ではない",
    ),
)


DEPRECATED_COMMAND_NAMES = (
    "import-deduction-certificate",
    "import-payment-statement",
    "import-withholding",
    "add-business-withholding",
    "add-crypto-income",
    "add-dependent",
    "add-donation",
    "add-housing-loan-detail",
    "add-insurance-policy",
    "add-journal",
    "add-loss-carryforward",
    "add-medical-expense",
    "add-other-income",
    "add-professional-fee",
    "add-rent-detail",
    "add-social-insurance-item",
    "get-spouse",
    "list-business-withholding",
    "list-crypto-income",
    "list-dependents",
    "list-donations",
    "list-insurance-policies",
    "list-inventory",
    "list-loss-carryforward",
    "list-medical-expenses",
    "list-other-income",
    "list-professional-fees",
    "list-social-insurance-items",
    "set-inventory",
    "set-spouse",
    "tax_calc furusato-limit",
)


_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_PATTERN = re.compile(r"(?<!`)`([^`\n]+)`(?!`)")
_OPTIONAL_SYNTAX_PATTERN = re.compile(r"\[[^\]]+\]")
_STRUCTURE_PLACEHOLDER_PATTERN = re.compile(r"^<[^>]+>$")
_LEGACY_WRAPPER_PATTERN = re.compile(r"\b(?:ledger|import_data|tax_calc)\.py\s+[a-z][a-z0-9-]*")


def _stable_type_name(value: object) -> str | None:
    if value is None:
        return None
    module = getattr(value, "__module__", None)
    qualname = getattr(value, "__qualname__", None)
    if module and qualname:
        return f"{module}.{qualname}"
    return value.__class__.__name__


def _json_value(value: object) -> Any:
    if value is argparse.SUPPRESS:
        return {"sentinel": "argparse.SUPPRESS"}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple, set, frozenset, range)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in sorted(value.items())}
    raise TypeError(f"スナップショット化できない値です: {_stable_type_name(value)}")


def iter_leaf_parsers(
    parser: argparse.ArgumentParser,
) -> tuple[tuple[tuple[str, ...], argparse.ArgumentParser], ...]:
    """末端コマンドのパスとparserを安定した順序で返す。"""
    leaves: list[tuple[tuple[str, ...], argparse.ArgumentParser]] = []

    def walk(current: argparse.ArgumentParser, path: tuple[str, ...]) -> None:
        subparser_actions = [
            action for action in current._actions if isinstance(action, argparse._SubParsersAction)
        ]
        if not subparser_actions:
            leaves.append((path, current))
            return
        for action in subparser_actions:
            for name, child in sorted(action.choices.items()):
                walk(child, (*path, name))

    walk(parser, ())
    return tuple(sorted(leaves, key=lambda item: item[0]))


def _normalize_action(action: argparse.Action) -> dict[str, object]:
    aliases = list(action.option_strings)
    return {
        "action": action.__class__.__name__,
        "aliases": aliases,
        "choices": _json_value(action.choices),
        "default": _json_value(action.default),
        "destination": action.dest,
        "kind": "optional" if aliases else "positional",
        "nargs": _json_value(action.nargs),
        "required": bool(action.required),
        "type": _stable_type_name(action.type),
    }


def _normalized_arguments(parser: argparse.ArgumentParser) -> list[dict[str, object]]:
    arguments = [
        _normalize_action(action)
        for action in parser._actions
        if action.dest != "help" and not isinstance(action, argparse._SubParsersAction)
    ]
    return sorted(
        arguments,
        key=lambda argument: (
            str(argument["kind"]),
            str(argument["aliases"]),
            str(argument["destination"]),
        ),
    )


def snapshot_parser_contract(parser: argparse.ArgumentParser) -> dict[str, object]:
    """parserからJSONへ保存できるCLI契約を生成する。"""
    commands = {
        " ".join(path): {"arguments": _normalized_arguments(leaf)}
        for path, leaf in iter_leaf_parsers(parser)
    }
    return {
        "commands": commands,
        "global_arguments": _normalized_arguments(parser),
    }


def write_parser_contract_snapshot(
    parser: argparse.ArgumentParser,
    destination: Path,
) -> None:
    """明示された出力先へCLI契約を整形済みJSONとして保存する。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(snapshot_parser_contract(parser), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _normalize_invocation(text: str) -> str | None:
    stripped = text.strip()
    if stripped.startswith("$ "):
        stripped = stripped[2:].lstrip()
    if stripped == "uv run shinkoku" or stripped.startswith("uv run shinkoku "):
        return stripped[len("uv run ") :]
    if stripped.startswith("shinkoku "):
        return stripped
    return None


def extract_markdown_commands(markdown: str, path: str) -> tuple[SkillCommand, ...]:
    lines = markdown.splitlines()
    commands: list[SkillCommand] = []
    in_fence = False
    pending: list[str] = []
    pending_line = 0

    for line_number, line in enumerate(lines, 1):
        if _FENCE_PATTERN.match(line):
            in_fence = not in_fence
            pending = []
            pending_line = 0
            continue

        if in_fence:
            stripped = line.strip()
            if pending:
                continued = stripped.endswith("\\")
                pending.append(stripped.removesuffix("\\").rstrip())
                if not continued:
                    commands.append(
                        SkillCommand(path=path, line=pending_line, text=" ".join(pending))
                    )
                    pending = []
                    pending_line = 0
                continue

            invocation = _normalize_invocation(stripped)
            if invocation is not None:
                continued = invocation.endswith("\\")
                if continued:
                    pending = [invocation.removesuffix("\\").rstrip()]
                    pending_line = line_number
                else:
                    commands.append(SkillCommand(path=path, line=line_number, text=invocation))
            continue

        for inline in _INLINE_CODE_PATTERN.findall(line):
            invocation = _normalize_invocation(inline)
            if invocation is not None:
                commands.append(SkillCommand(path=path, line=line_number, text=invocation))

    return tuple(commands)


def _command_contracts(
    parser: argparse.ArgumentParser,
) -> dict[tuple[str, ...], dict[str, object]]:
    snapshot = snapshot_parser_contract(parser)
    commands = snapshot["commands"]
    assert isinstance(commands, dict)
    return {tuple(path.split()): contract for path, contract in commands.items()}


def _exclude_command(command: SkillCommand, tokens: list[str]) -> CommandExclusion | None:
    args = tokens[1:]
    if any(_STRUCTURE_PLACEHOLDER_PATTERN.match(token) for token in args[:2]):
        return CommandExclusion(
            path=command.path,
            line=command.line,
            command=command.text,
            reason="command_structure_placeholder",
        )
    if _OPTIONAL_SYNTAX_PATTERN.search(command.text):
        return CommandExclusion(
            path=command.path,
            line=command.line,
            command=command.text,
            reason="optional_bracket_syntax",
        )
    return None


def lint_skill_command(
    command: SkillCommand,
    parser: argparse.ArgumentParser,
) -> tuple[tuple[ContractViolation, ...], CommandExclusion | None]:
    """一つのMarkdownコマンドをparser契約と照合する。"""
    try:
        tokens = shlex.split(command.text)
    except ValueError as exc:
        violation = ContractViolation(
            path=command.path,
            line=command.line,
            command=command.text,
            kind="tokenize_error",
            detail=str(exc),
        )
        return (violation,), None

    exclusion = _exclude_command(command, tokens)
    if exclusion is not None:
        return (), exclusion

    if tokens == ["shinkoku", "--version"]:
        return (), None
    if not tokens or tokens[0] != "shinkoku":
        violation = ContractViolation(
            path=command.path,
            line=command.line,
            command=command.text,
            kind="invalid_entrypoint",
            detail="先頭がshinkokuではありません",
        )
        return (violation,), None

    args = tokens[1:]
    contracts = _command_contracts(parser)
    matching_paths = [path for path in contracts if args[: len(path)] == list(path)]
    if not matching_paths:
        top_levels = {path[0] for path in contracts}
        kind = "unknown_top_level" if args and args[0] not in top_levels else "unknown_command"
        detail = args[0] if kind == "unknown_top_level" and args else " ".join(args[:2])
        violation = ContractViolation(
            path=command.path,
            line=command.line,
            command=command.text,
            kind=kind,
            detail=detail,
        )
        return (violation,), None

    command_path = max(matching_paths, key=len)
    contract = contracts[command_path]
    arguments = contract["arguments"]
    assert isinstance(arguments, list)
    option_aliases: dict[str, str] = {}
    required_options: set[str] = set()
    for argument in arguments:
        assert isinstance(argument, dict)
        aliases = argument["aliases"]
        assert isinstance(aliases, list)
        if not aliases:
            continue
        canonical = next(
            (alias for alias in aliases if isinstance(alias, str) and alias.startswith("--")),
            str(aliases[0]),
        )
        option_aliases.update({str(alias): canonical for alias in aliases})
        if argument["required"]:
            required_options.add(canonical)

    remaining = args[len(command_path) :]
    provided = {
        token.split("=", 1)[0] for token in remaining if token.startswith("-") and token != "-"
    }
    violations: list[ContractViolation] = []
    for option in sorted(provided - option_aliases.keys()):
        violations.append(
            ContractViolation(
                path=command.path,
                line=command.line,
                command=command.text,
                kind="unknown_option",
                detail=option,
            )
        )

    canonical_provided = {option_aliases[option] for option in provided if option in option_aliases}
    for option in sorted(required_options - canonical_provided):
        violations.append(
            ContractViolation(
                path=command.path,
                line=command.line,
                command=command.text,
                kind="missing_required_option",
                detail=option,
            )
        )
    return tuple(violations), None


def scan_skill_cli_contract(
    repository_root: Path,
    parser: argparse.ArgumentParser,
) -> SkillContractScan:
    """skills配下のMarkdownを走査し、全コマンドをCLI契約と照合する。"""
    commands: list[SkillCommand] = []
    violations: list[ContractViolation] = []
    exclusions: list[CommandExclusion] = []
    matched_exceptions: list[NonCommandException] = []
    exception_map = {(item.path, item.text): item for item in NON_COMMAND_EXCEPTIONS}

    for markdown_path in sorted((repository_root / "skills").rglob("*.md")):
        relative_path = markdown_path.relative_to(repository_root).as_posix()
        extracted = extract_markdown_commands(
            markdown_path.read_text(encoding="utf-8"),
            relative_path,
        )
        for command in extracted:
            commands.append(command)
            exception = exception_map.get((command.path, command.text))
            if exception is not None:
                matched_exceptions.append(exception)
                continue
            command_violations, exclusion = lint_skill_command(command, parser)
            violations.extend(command_violations)
            if exclusion is not None:
                exclusions.append(exclusion)

    return SkillContractScan(
        commands=tuple(commands),
        violations=tuple(violations),
        exclusions=tuple(exclusions),
        exceptions=tuple(matched_exceptions),
    )


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def find_legacy_wrappers(repository_root: Path) -> tuple[DeprecatedOccurrence, ...]:
    """skills文書に残る旧Pythonラッパー形式を列挙する。"""
    occurrences: list[DeprecatedOccurrence] = []
    for markdown_path in sorted((repository_root / "skills").rglob("*.md")):
        relative_path = markdown_path.relative_to(repository_root).as_posix()
        text = markdown_path.read_text(encoding="utf-8")
        for match in _LEGACY_WRAPPER_PATTERN.finditer(text):
            occurrences.append(
                DeprecatedOccurrence(
                    name="legacy_python_wrapper",
                    path=relative_path,
                    line=_line_number(text, match.start()),
                    matched_text=match.group(0),
                )
            )
    return tuple(occurrences)


def find_deprecated_command_names(repository_root: Path) -> tuple[DeprecatedOccurrence, ...]:
    """skills文書に残る31種類の廃止済みコマンド名を列挙する。"""
    occurrences: list[DeprecatedOccurrence] = []
    literal_names = DEPRECATED_COMMAND_NAMES[:-1]
    special_name = DEPRECATED_COMMAND_NAMES[-1]
    special_pattern = re.compile(r"tax_calc(?:\.py)?\s+furusato-limit")

    for markdown_path in sorted((repository_root / "skills").rglob("*.md")):
        relative_path = markdown_path.relative_to(repository_root).as_posix()
        text = markdown_path.read_text(encoding="utf-8")
        for name in literal_names:
            pattern = re.compile(re.escape(name))
            for match in pattern.finditer(text):
                occurrences.append(
                    DeprecatedOccurrence(
                        name=name,
                        path=relative_path,
                        line=_line_number(text, match.start()),
                        matched_text=match.group(0),
                    )
                )
        for match in special_pattern.finditer(text):
            occurrences.append(
                DeprecatedOccurrence(
                    name=special_name,
                    path=relative_path,
                    line=_line_number(text, match.start()),
                    matched_text=match.group(0),
                )
            )
    return tuple(sorted(occurrences, key=lambda item: (item.path, item.line, item.name)))


def format_violations(violations: tuple[ContractViolation, ...]) -> str:
    """pytestの失敗メッセージ向けに違反を安定順で整形する。"""
    return "\n".join(
        f"{item.path}:{item.line}: {item.kind}({item.detail}): {item.command}"
        for item in violations
    )


def format_exclusions(exclusions: tuple[CommandExclusion, ...]) -> str:
    """除外行と理由を作業報告にも転記できる形で整形する。"""
    return "\n".join(
        f"{item.path}:{item.line}: {item.reason}: {item.command}" for item in exclusions
    )
