# 源泉徴収票の読取り・保存・検証の実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking. この会話で指定された実装担当が順番に実行し、追加のサブエージェントは起動しない。

**Goal:** 未読・空欄・明示的な0を区別した源泉徴収票を、共通検算と原本確認を経て保存・訂正し、選択した証憑と申告入力を照合できるようにする。

**Architecture:** 共通フィールドと結果モデルを`models.py`へ、DBに依存しない検算と社会保険料部分の取得を`tools/withholding.py`へ置く。保存・一覧・sanity-checkが同じ検算を呼び、税額計算は既存の関数を使用する。旧テーブルは`schema.sql`を正本として既存の移行トランザクション内で再構築する。

**Tech Stack:** Python 3.11+、既存のPydantic 2、argparse、SQLite、pytest、Ruff、mypy。

**Spec:** [withholding-slip-validation-design.md](withholding-slip-validation-design.md)。設計書と[development-contracts.md](development-contracts.md)を実装時にも参照する。

## Global Constraints

- 起点は`3d08ae7fbc0b2f464880e4138c39fd34eb9ef3d1`、作業ブランチは`codex/fix-withholding-slip-validation`である。設計書を含む既存の変更を保持する。
- 金額は円単位の非負の厳密な`int | None`とし、省略時は`None`にする。税額計算の式・税率・端数処理・対象年度は変更しない。
- 新しい外部依存や補助テーブルは追加しない。OCRエンジン・人数の自動換算・画像認識モデルの固定は追加しない。
- 2025年分・2026年分の改正後の受給者交付用を画像評価の対象とし、原本の年分と帳票の版を別々に確認する。2026年分の通常の年末調整のfixtureは12月以後を前提とする。
- 未払・未徴収の内書き、対象外の様式、年途中の適用関係が未解決なら原本確認を完了扱いにしない。原本の記載額を現在の控除表で上書きしない。
- DBのWALと外部キーを維持し、`get_connection()`と`init_db()`を使用する。旧値・ID・`created_at`・索引・トリガー・採番上限を保持し、中断時はロールバックする。
- 実DB・既存の`shinkoku.config.yaml`・`.data`・`output/`は読まず、変更しない。新しい使い捨てDB・設定・実行記録は`playground/withholding-validation/`と専用のpytest一時ディレクトリへ置く。
- 源泉徴収票は証憑の下書きとして保存できるが、`ready_for_calculation=false`の票から申告入力を組み立てない。原本確認は実帳簿への登録や申告送信の承認を意味しない。
- 各段階で修正前の失敗と修正後の成功、実行コマンド、終了コード、所要時間を記録する。期待値は公的資料と独立した計算で固定し、製品関数の結果から生成しない。
- コミット・push・PRは行わない。コードとSkillの変更を揃え、互換性変更としてバージョン・CHANGELOG・CLI契約を更新する。

### 実行環境と基準検査

親が既存のCLI/Skill契約・DB・sanity-checkの83件を確認し、`83 passed in 9.35s`を得た。この基準範囲を計画作成のために再実行しない。既存の`.venv`はPython 3.14.4であり、標準uvキャッシュの権限エラーを避けるため、実装時には次を最初に設定する。既存環境で足りる検査には`uv run --no-sync`を使用し、同期・新しいソフトの導入を暗黙に行わない。

```powershell
$env:UV_CACHE_DIR = Join-Path (Get-Location) 'playground/uv-cache-withholding'
uv run --no-sync pytest tests/unit/test_skill_cli_contract.py tests/unit/test_db.py tests/unit/test_sanity_check.py -q --basetemp playground/pytest-withholding-baseline
```

下記の各Taskでは検査対象と正規のコマンドを記す。現在のサンドボックスでは同じ検査を`uv run --no-sync`で実行する。時間は`System.Diagnostics.Stopwatch`等で各コマンドを個別に測定し、終了コードとともに記録する。

## Review Focus

1. 確認済み空欄の社会保険料等・内書きはDB上のNULLを保ち、照合時だけ0にできる。未読NULLは0にできない（Task 2・5）。
2. 年末調整未済と、調整済み票でのみ記載する金額との矛盾は保存を拒否する。未済の適切な空欄は`not_applicable`になる（Task 2・4）。
3. 二つの隣接欄を交換すると合計は一致し得る。原本未照合なら計算用には採用できない（Task 2・6）。
4. 空の旧テーブルにも削除済みIDの採番上限が残り得る。非整数の旧値や移行中断は旧状態を保持する（Task 3）。
5. 前職分を通算した票など、DBにある全票を自動で合算しない。選択を確認したIDだけを照合する（Task 5）。

## 変更するファイルと役割

| ファイル | 役割 |
|---|---|
| `src/shinkoku/models.py` | 共通のnullable入力、読取り・DBモデル、検算結果、`SalaryEvidenceInput`を定義する |
| `src/shinkoku/tools/withholding.py`（新規） | 共通検算と、確認済み空欄を考慮した社会保険料部分の取得を行う |
| `src/shinkoku/schema.sql`、`src/shinkoku/db.py` | nullableスキーマと、旧テーブルを保持できる移行を実装する |
| `src/shinkoku/tools/ledger.py`、`src/shinkoku/cli/ledger.py` | `ws-check`、保存前検算、任意IDによる全項目訂正、読戻し時の再検算を実装する |
| `src/shinkoku/tools/import_data.py` | `WithholdingSlipData`を使用して未読のNULLテンプレートを返す |
| `src/shinkoku/tools/tax_calc.py`、`src/shinkoku/cli/tax_calc.py` | 任意の`salary_evidence`を受け取り、DBを変更せず給与証憑と照合する |
| `tests/unit/test_withholding.py`、`tests/unit/test_withholding_migration.py`（新規） | モデル・純粋検算・旧DB移行の負例を固定する |
| `tests/scripts/test_ledger.py`、`test_import_data.py`、`test_tax_calc.py`、`tests/unit/test_sanity_check.py` | 既存のヘルパーとテスト構造でCLI往復・DB照合を検証する |
| `tests/integration/test_withholding_validation.py`（新規）、`test_frozen_filing_scenarios.py` | 新経路と、太郎49項目・二郎45項目・R6・R7を検証する |
| `tests/fixtures/withholding/`（新規） | 架空PDF・PNG、期待JSON、根拠README、二郎の補助fixtureを置く |
| `tests/helpers/cli_contract.py`、`tests/fixtures/cli_contract.json`、`tests/unit/test_skill_cli_contract.py` | 110コマンドの契約と、源泉徴収票のJSON例の厳密な検査を行う |
| 設計7節の7つのSkill文書 | 読取り・確認・保存・入力組立て・転記の手順とJSONを揃える |
| `pyproject.toml`、`.claude-plugin/plugin.json`、`CHANGELOG.md` | 互換性変更と新しい機能を記録する |

## Task 1: 独立期待値と現行の負例を固定する

**Files:** Create `tests/fixtures/withholding/README.md`、各ケース名のサブディレクトリのPDF・PNG・`input.json`・`expected-validation.json`、`jiro-confirmation.json`。Modify `tests/scripts/test_import_data.py`、`tests/scripts/test_ledger.py`。記録は`playground/withholding-validation/`へ置く。

**Interfaces:** fixtureは平坦な源泉徴収票入力JSONと、検算結果の独立期待値を提供する。二郎の補助fixtureには金額の変更ではなく、`persona.md`と`salary_slip_extra`から確認できる新項目・確認情報・派生額の根拠を入れる。

- [x] **Step 1: fixtureを固定する。** ケース名を`2025-specific`、`2026-specific`、`2025-no-specific`、`2025-unadjusted`、`2025-hard-adjacent`とする。氏名は「架空受給者」、勤務先は「架空勤務先」とし、欄外に架空資料と明記する。2025年分は基礎680,000円・特定親族610,000円・社会保険750,000円・合計2,040,000円、2026年分は基礎1,040,000円・特定親族610,000円・社会保険750,000円・合計2,400,000円を別の資料IDとともに固定する。全票の給与・税額・親族設定も該当年の資料で独立に確認する。
- [x] **Step 2: 二郎の補助fixtureを固定する。** 年分2026、調整済み1枚、給与6,000,000円、給与所得控除後4,360,000円、控除合計2,330,000円、基礎670,000円、社会保険900,000円、源泉107,700円を保持する。特定親族0円、生命・地震・内書き0円、その他人的控除0円、派生扶養380,000円の根拠を`tests/fixtures/scenarios/jiro/persona.md`の人物・給与設定へ結び付ける。元の`evidence.json`と期待値は変更しない。
- [x] **Step 3: 失敗テストを書く。** `test_import_withholding_preserves_unread_amounts_as_null`では、既存のファイル受付経路に対して未読NULLを検査する。`test_adjacent_misread_is_rejected_before_save`では、2025年分の社会保険だけを610,000円へ変えた平坦JSONを既存CLIへ渡し、終了コード1・`status=error`・DBの旧内容の保持を要求する。現行の未読0・未知項目の欠落・誤読済みJSONの保存成功により失敗する。

```python
def test_import_withholding_preserves_unread_amounts_as_null(tmp_path: Path) -> None:
    path = tmp_path / "fictional-slip.txt"
    path.write_text("架空資料", encoding="utf-8")
    completed = run_import("withholding", "--file-path", str(path))
    data = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert data["payment_amount"] is None
    assert data["withheld_tax"] is None
    assert data["social_insurance"] is None
```

- [x] **Step 4: 現行の失敗と画像評価を記録する。** 次を実行し、失敗の原因が期待した相違であることを確認する。架空画像を現行の`reading-withholding`手順で読み、PNG/PDFのハッシュ、使用した読取手段、読取り結果を`before/`へ保存する。画像の誤読が起きなければ「未再現」と記録する。

```powershell
uv run pytest tests/scripts/test_import_data.py::test_import_withholding_preserves_unread_amounts_as_null -q --basetemp playground/pytest-withholding-baseline
uv run pytest tests/scripts/test_ledger.py::test_adjacent_misread_is_rejected_before_save -q --basetemp playground/pytest-withholding-baseline-ledger
```

**確認点:** 控除合計の根拠が設計2.3・8.1節の年分別資料に対応する。難読化してもラベルと正解値を消さず、同じ画像を変更後にも使う。画像評価と誤読済みJSONの決定的な負例を区別する。

## Task 2: 共通モデル・検算・ws-checkを実装する

**Files:** Modify `src/shinkoku/models.py`、`src/shinkoku/cli/ledger.py`、CLI契約ヘルパーとスナップショット。Create `src/shinkoku/tools/withholding.py`、`tests/unit/test_withholding.py`。Modify `tests/scripts/test_ledger.py`。

**Interfaces:**

- `WithholdingSlipInput`に金額・確認情報を一度だけ定義し、`WithholdingSlipData`と`WithholdingSlipRecord`が継承する。既存のInput定義を共通モデルの位置へ移し、重複定義を残さない。Dataには`file_path: str`と`extracted_text: str`、Recordには`id: int`と`fiscal_year: int`を加える。
- 共通金額は`payment_amount`、`withheld_tax`、`social_insurance`、`life_insurance_deduction`、`earthquake_insurance_deduction`、`housing_loan_deduction`、`spouse_deduction`、`dependent_deduction`、`basic_deduction`、`life_insurance_general_new`、`life_insurance_general_old`、`life_insurance_medical_care`、`life_insurance_annuity_new`、`life_insurance_annuity_old`、`national_pension_premium`、`old_long_term_insurance_premium`、`specific_relative_special_deduction`、`total_income_deductions`、`salary_income_after_deduction`、`social_insurance_small_business_mutual_aid`、`other_personal_deductions`の21項目である。
- `document_fiscal_year: int | None`はstrictとし、`year_end_adjusted`と`source_confirmed`は`StrictBool | None`、`blank_fields`は21項目名の列挙値リスト、`deduction_derivation_note`・`source_file`・`payer_name`は`str | None`とする。未知キー、空欄名の重複、未知名、金額との同時指定を拒否する。
- `WithholdingSlipValidationIssue`は`severity: Literal["error", "warning", "info"]`・`code: str`・`fields: list[str]`・`message: str`を持つ。`WithholdingSlipValidationResult`は設計5.1節の`status`、3つのnullable金額、`missing_fields`、`issues`、`ready_for_calculation`を持つ。
- `check_withholding_slip(slip: WithholdingSlipInput, *, fiscal_year: int) -> WithholdingSlipValidationResult`と`get_withholding_social_insurance(slip: WithholdingSlipInput) -> int | None`を公開する。後者は総額から内書きを引いた値を返し、社会保険料等と内書きの確認済み空欄だけを有効値0とする。未確認や総額を超える内書きなら`None`を返す。
- `cmd_ws_check(args: argparse.Namespace) -> None`は`_load_json(args.input)`と`WithholdingSlipInput(**data)`を使い、`{status:"ok", fiscal_year, validation}`を返す。DB引数は設けない。

- [x] **Step 1: 失敗テストを書く。** `test_amount_contract_and_blank_fields`は省略のNULL・明示的な0・falseとNULLの区別、bool/float/数値文字列/負数/未知キー/空欄矛盾の拒否を検査する。`test_deduction_total_and_adjacent_misread`は正解2,040,000円・差額0、社会保険を610,000円へ誤読した場合は1,900,000円・差額-140,000円・`WS_DEDUCTION_TOTAL_MISMATCH`を検査する。

```python
def test_deduction_total_and_adjacent_misread() -> None:
    raw = json.loads((FIXTURES / "2025-specific/input.json").read_text(encoding="utf-8"))
    good = check_withholding_slip(WithholdingSlipInput(**raw), fiscal_year=2025)
    assert (good.status, good.calculated_total, good.difference) == ("matched", 2040000, 0)
    bad = check_withholding_slip(
        WithholdingSlipInput(**{**raw, "social_insurance": 610000}), fiscal_year=2025
    )
    assert (bad.status, bad.calculated_total, bad.difference) == ("mismatched", 1900000, -140000)
    assert "WS_DEDUCTION_TOTAL_MISMATCH" in {issue.code for issue in bad.issues}
    assert bad.ready_for_calculation is False
```

- [x] **Step 2: 境界の失敗テストを加える。** 特定親族の欠落、内書き・国民年金・住宅ローンの誤加算、内書き超過、年分不一致、正の派生額の根拠不足、調整済みの不明項目、未済の適切な空欄、未済と記載額の矛盾、年途中の額を自動修正しないことを検査する。二欄交換では`matched`でも`source_confirmed=None`ならreadyはfalseとする。確認済み空欄の社会保険と内書きは取得額0、未読は取得額NULLとする。
- [x] **Step 3: 失敗を確認する。** 下記を実行する。新関数がないことによる失敗に加え、既存モデルの未読0・型変換・情報欠落による失敗を記録する。
- [x] **Step 4: 最小実装を行う。** 設計5.1節の8項目の合計だけを照合する。`WS_FIELDS_UNCONFIRMED`、`WS_SOURCE_NOT_CONFIRMED`、`WS_FISCAL_YEAR_MISMATCH`、`WS_INVALID_INNER_AMOUNT`、`WS_YEAR_END_STATUS_CONFLICT`を区別する。空欄の有効値は保存せず検算時にだけ作る。`register()`へ`ws-check`を追加し、JSON不正は終了コード1、有効な不一致・不足は検査結果として0にする。
- [x] **Step 5: 同じテストを再実行する。** `test_ws_check_json_and_exit_codes`を含むws-checkのCLIテストを通す。基準109件を確認して110件へ更新し、既存の`write_parser_contract_snapshot(build_parser(), Path("tests/fixtures/cli_contract.json"))`でスナップショットを再生成する。

```powershell
uv run pytest tests/unit/test_withholding.py tests/scripts/test_ledger.py -k "withholding or ws_check or WithholdingSlip" -q --basetemp playground/pytest-withholding-models
uv run python -c "from pathlib import Path; from shinkoku.cli import build_parser; from tests.helpers.cli_contract import write_parser_contract_snapshot; write_parser_contract_snapshot(build_parser(), Path('tests/fixtures/cli_contract.json'))"
uv run pytest tests/unit/test_cli_contract.py -q --basetemp playground/pytest-withholding-contract
```

**確認点:** `WithholdingSlipRecord`も同じ検算関数へ渡せる。検算の一致をOCRの正しさや税務上の適用要件の証明と表示しない。新しい控除表は作らない。

## Task 3: nullableスキーマと旧DB移行を実装する

**Files:** Modify `src/shinkoku/schema.sql`、`src/shinkoku/db.py`。Create `tests/unit/test_withholding_migration.py`。既存の`test_fixed_asset_migration.py`を回帰検査する。

**Interfaces:** `_migrate_withholding_slips(conn: sqlite3.Connection) -> None`を`_migrate()`から呼ぶ。金額列はnullable・DEFAULT NULLとし、NULL以外はSQLiteの`typeof(...)='integer'`と非負のCHECKを課す。確認フラグはNULL・0・1だけを許す。`blank_fields`はnullable TEXTのJSONで保存し、読取り時のSQL NULLは空リストへ対応付ける。

- [x] **Step 1: 失敗テストを書く。** テスト内の`make_legacy_withholding_db(path: Path) -> list[tuple]`で、2025・2026年、明示値、旧デフォルト0、固定`created_at`、追加索引・トリガー、削除済みIDの採番上限900を持つ旧DBを作る。`test_nonempty_withholding_migration_preserves_values_and_sequence`では全旧列・ID・作成日時の一致、新列NULL、次のID901、再移行の論理内容一致を検査する。
- [x] **Step 2: 中断の失敗テストを書く。** `test_interrupted_withholding_migration_rolls_back`でcopy/drop/rename/index/triggerの失敗を既存のSQLite authorizer方式で注入する。`test_invalid_legacy_amount_is_not_repaired`では負数、REAL、非数値TEXTの旧金額を与え、移行が失敗して全旧値と旧スキーマが残ることを検査する。空テーブルの採番上限、未知の列、残存一時テーブル、後続移行の失敗・KeyboardInterruptでも旧状態が残ることを検査する。
- [x] **Step 3: 失敗を確認する。** 下記を実行し、現行のNOT NULLと移行未実装による失敗を確認する。
- [x] **Step 4: 再構築を実装する。** 固定資産移行の既存パターンを使い、`schema.sql`の同じCREATE文から一時テーブルを作る。既知の旧列を名前でコピーし、件数・全旧値を確認してから置換する。SAVEPOINTを使い、索引・トリガー・採番上限・外部キーを確認する。未知構成や不適合値を修正して続行せず、既存の外側トランザクションまでロールバックする。
- [x] **Step 5: 同じテストを再実行する。** 新規DBのNULLと型CHECK、旧0の保持、新しい確認情報がNULLであること、WAL/FK/integrity、再実行と中断後の再試行を確認する。

```powershell
uv run pytest tests/unit/test_withholding_migration.py tests/unit/test_fixed_asset_migration.py tests/unit/test_db.py -q --basetemp playground/pytest-withholding-migration
```

**確認点:** 移行の完了だけでは旧票はreadyにならない。全票の原本再確認をDB開閉の条件にしない。後続移行が失敗しても源泉徴収票だけを部分確定しない。

## Task 4: 保存・訂正・読戻し・importをつなぐ

**Files:** Modify `src/shinkoku/tools/ledger.py`、`src/shinkoku/cli/ledger.py`、`src/shinkoku/tools/import_data.py`、`tests/scripts/test_ledger.py`、`tests/scripts/test_import_data.py`、CLI契約スナップショット。

**Interfaces:**

- `ledger_save_withholding_slip(*, db_path: str, fiscal_year: int, detail: WithholdingSlipInput, withholding_slip_id: int | None = None) -> dict`。成功時は既存の`status`・`withholding_slip_id`に`validation`を追加する。
- `ledger_list_withholding_slips(*, db_path: str, fiscal_year: int) -> dict`は既存の一覧・IDを維持し、各行へ共通検算の`validation`を追加する。結果はDBへ保存しない。
- `import_withholding(*, file_path: str) -> dict`は既存の`status`・`file_path`・`extracted_text`を保ち、`WithholdingSlipData`から共通フィールドのNULLテンプレートを作る。数値の読取り完了とは表示しない。

- [x] **Step 1: 失敗テストを書く。** `test_withholding_roundtrip_preserves_null_blank_and_zero`で下書きのNULL、空欄リスト、明示的0、確認フラグ、全21金額を往復させる。`test_withholding_update_replaces_fields_and_preserves_identity`で同じ年度のID指定訂正を行い、省略された旧値がNULLへ置換され、ID・`created_at`が維持されることを検査する。
- [x] **Step 2: 保存拒否の失敗テストを書く。** `test_invalid_withholding_save_does_not_change_db`で型エラー・年分不一致・内書き超過・控除合計不一致・年末調整状態矛盾を検査する。存在しないID・別年度ID・訂正時のトランザクション失敗では旧行を保持する。検算可能な不一致は下書きとしても保存しない。型不正はDB接続前に拒否し、新しいDBを作らない。
- [x] **Step 3: 失敗を確認する。** 下記とTask 1のimportテストを実行する。
- [x] **Step 4: 実装する。** 検算を接続前に行い、保存を拒否する問題だけをerrorへする。不足は保存可能な下書きとして返す。型不正には`WS_INPUT_INVALID`と`validation:null`、その他の拒否には該当`code`・`validation`・`message`を返し、CLIの既存`_output()`で終了コード1にする。訂正では全共通項目を一つのトランザクションで置換し、`created_at`を更新しない。DBのJSONリストと0/1のフラグをモデルへ復元し、一覧は呼出しのたびに検算する。
- [x] **Step 5: 同じテストを再実行する。** importの受付テストを画像OCRの成功と扱わず、NULLテンプレートの契約として確認する。訂正オプションのスナップショットを再生成する。

```powershell
uv run pytest tests/scripts/test_ledger.py tests/scripts/test_import_data.py -q --basetemp playground/pytest-withholding-storage
uv run python -c "from pathlib import Path; from shinkoku.cli import build_parser; from tests.helpers.cli_contract import write_parser_contract_snapshot; write_parser_contract_snapshot(build_parser(), Path('tests/fixtures/cli_contract.json'))"
uv run pytest tests/unit/test_cli_contract.py -q --basetemp playground/pytest-withholding-storage-contract
```

**確認点:** `ws-delete`の既存契約を維持する。`ws-list`の結果を手動で改変しても、保存時・sanity-check時の再検算を迂回できない。

## Task 5: salary_evidenceによるDB照合と既存回帰をつなぐ

**Files:** Modify `src/shinkoku/models.py`、`src/shinkoku/tools/tax_calc.py`、`src/shinkoku/cli/tax_calc.py`、`tests/unit/test_sanity_check.py`、`tests/scripts/test_tax_calc.py`、`tests/integration/test_frozen_filing_scenarios.py`。Create `tests/integration/test_withholding_validation.py`。

**Interfaces:**

- `SalaryEvidenceInput`はextraを禁止し、`slip_ids: list[int]`を1件以上の重複しない正のstrict整数、`selection_confirmed: StrictBool | None = None`、`additional_social_insurance: int | None = None`を非負のstrict整数にする。
- `sanity_check_income_tax(input_data: IncomeTaxInput, result: IncomeTaxResult, *, db_path: str | None = None, salary_evidence: SalaryEvidenceInput | None = None) -> TaxSanityCheckResult`へ拡張する。
- `_check_salary_against_ledger(input_data: IncomeTaxInput, result: IncomeTaxResult, db_path: str, salary_evidence: SalaryEvidenceInput | None) -> list[TaxSanityCheckItem]`を既存の事業源泉照合と同じ場所から呼ぶ。`_handle_sanity_check()`は既存の`{input, result}`と任意の`salary_evidence`を受け取る。

- [x] **Step 1: 失敗テストを書く。** `test_salary_evidence_selection_is_strict`では空リスト・重複ID・0/負数/bool/float/文字列ID・未知キーを拒否する。`test_salary_evidence_required_by_mode`ではDB付きで給与収入または源泉が非0なら未指定を`SALARY_EVIDENCE_UNCONFIRMED`とし、filingではerror、estimateではwarningとする。明示された証憑は給与0でも検査し、DBなしの指定は入力エラーとする。
- [x] **Step 2: 照合の失敗テストを書く。** `test_salary_ledger_mismatches_are_errors_in_both_modes`で給与・入力源泉・結果源泉・社会保険をそれぞれずらし、設計の3つの`SALARY_*_LEDGER_MISMATCH`を検査する。存在しないID・別年分・未確認票・検算不一致・選択未確認・追加社会保険NULLを検査する。別年分と既知金額の不一致は両モードでerrorとする。
- [x] **Step 3: NULLと読取り専用の境界テストを書く。** `test_salary_ledger_uses_confirmed_blank_without_hiding_unread_null`で、社会保険・内書きの確認済み空欄はNULL保存のまま0円照合になり、片方が未読なら集計を完了しないことを検査する。未選択票・前職通算前票は加算しない。不存在DBを作らず、必要な新列のない旧DBを移行せずエラーにする。照合前後の`iterdump()`一致とquery-only接続でも成功することを確認する。
- [x] **Step 4: 失敗を確認して実装する。** DBの存在と必要列を確認して`get_connection()`で読み、`init_db()`・`ws-list`による移行は呼ばない。選択行を取得して共通検算を再実行し、確認済みの額だけをPythonの整数で合計する。社会保険料部分にはTask 2の取得関数を使い、SQLのSUM/COALESCEでNULLを隠さない。既存の事業源泉照合と税額計算は維持する。
- [x] **Step 5: 結合と既存回帰を再実行する。** 新しい実CLI経路は平坦JSON→ws-check→ws-save→ws-list→filingのcalc-income→DB付きsanity-checkを通す。誤読済みJSONは保存前に拒否されることも検査する。二郎の登録にTask 1の補助fixtureをマージし、選択IDをsanity-checkとR6の負例へ渡す。既存のDB付きsanity-checkテストで給与を持つケースにも、当該テスト入力を変えずに確認済みの架空証憑と選択情報を補う。元の49/45項目、R6の20,420円誤合算、R7の棚卸と決算の境界を維持する。

```powershell
uv run pytest tests/unit/test_sanity_check.py tests/scripts/test_tax_calc.py tests/integration/test_withholding_validation.py tests/integration/test_frozen_filing_scenarios.py -q --basetemp playground/pytest-withholding-sanity
uv run pytest tests/unit/test_income_tax_2027.py tests/unit/test_tax_year_support.py tests/scripts/test_tax_year_support.py -q --basetemp playground/pytest-withholding-years
```

**確認点:** 税計算の単発経路やDBなしのsanity-checkは従来どおり使える。estimateでwarningだけならpassedがtrueでも証憑照合済みと表示しない。種類別掛金の配分・資料との重複・親族の適用要件はこの3等式の証明範囲に含めない。

## Task 6: Skill・契約・リリース記録と画像評価を仕上げる

**Files:** Modify `skills/reading-withholding/SKILL.md`、`skills/_shared/ocr.md`、`skills/income-tax/references/workflow-withholding.md`、`workflow-deductions.md`、`workflow-calculation.md`、`workflow-business.md`、`skills/e-tax/references/workflow-income.md`、`tests/unit/test_skill_cli_contract.py`、`pyproject.toml`、`.claude-plugin/plugin.json`、`CHANGELOG.md`。画像評価の結果と検査記録は`playground/withholding-validation/`へ置く。

**Interfaces:** `---WITHHOLDING_DATA---`と`---END---`の既存マーカーの中を、`WithholdingSlipInput`で検証できる平坦なJSONへ変える。importの外側の`file_path`だけは構造化時に明示的に`source_file`へ対応付ける。`ws-check`と`ws-save`の例は既存のAST導出による自動検査へ入れ、読取り出力と`SalaryEvidenceInput`の例には明示的な厳密検査も置く。

- [x] **Step 1: 失敗テストを書く。** `test_withholding_reading_example_matches_input_contract`でマーカー内のJSONを抽出して`WithholdingSlipInput.model_validate(..., strict=True)`へ渡す。`test_ws_check_and_save_examples_are_present`で両コマンドのJSON例が検査対象であることを検査する。`test_salary_evidence_examples_match_strict_contract`で該当JSONの`salary_evidence`を検査する。除外規則を広げて失敗を隠さない。
- [x] **Step 2: 失敗を確認し、7文書を更新する。** 未読0の指示と基礎控除の逆補完を取り除き、ラベルごとの読取り、内書き、空欄、原本年分、派生額の根拠を出力する。ws-check→原本照合と対象内容確認→ws-save→ws-listへ揃える。社会保険は総額から内書きを引き、追加分を確認して加え、掛金は種類と二重計上を確認して既存入力へ渡す。記載控除額を申告時の人的控除へ加算せず、生命保険控除額を保険料へ渡さない。転記一覧は調整済み・未済を分け、未知の画面ラベル・name属性を追加しない。
- [x] **Step 3: 互換性変更を記録する。** 現行0.21.0から、規約のMAJOR変更として`pyproject.toml`と`.claude-plugin/plugin.json`を同じ`1.0.0`へ更新する。CHANGELOGには省略値0→NULL・strict拒否・DB移行・下書き・任意ID訂正・110コマンド・給与証憑選択の要求・税額計算式は変更していないことを記す。部分実装の状態では完了扱いにしない。
- [x] **Step 4: Skill契約と同じ架空画像を再検証する。** 下記のSkill検査を通す。Task 1の同じPDF・PNGを更新後の手順で読み、`after/`へ保存する。各ケースを「正しく読めた」「未読をNULLとして止めた」「誤読した」に分け、実際の読取りJSONへws-checkを実行する。誤読が未再現の場合はその事実を保ち、誤読注入JSONの検出結果とは別に報告する。読取手段が使えなければ無断導入せず、未確認範囲を親へ報告する。
- [x] **Step 5: 最終検査を行う。** 全検査の所要時間と結果を記録する。失敗があれば依頼範囲を修正して該当検査を再実行し、最後に変更範囲・既存設計書の保持・個人情報の非混入を確認する。税計算側の欠陥が見つかった場合は黙って修正せず、根拠と影響を親へ報告する。

```powershell
uv run pytest tests/unit/test_skill_cli_contract.py tests/unit/test_cli_contract.py -q --basetemp playground/pytest-withholding-skills
uv run pytest tests/ --basetemp playground/pytest-withholding
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/shinkoku/ --ignore-missing-imports
git diff --check
git status --short
```

**完了の証拠:** `playground/withholding-validation/report.md`に、各段階の修正前失敗・修正後成功・所要時間、太郎49項目と二郎45項目、R6/R7、DB保持、CLI契約110件、画像評価の実結果と限界を記録する。自動テストの成功だけで画像読取りの修正を検証済みとしない。

## 計画の自己レビュー

- 設計1・2・4節の範囲と型はGlobal Constraints、Task 1・2に対応する。原本値と申告時の控除値を区別する。
- 設計5節の共通検算・CLI・入力組立て・給与証憑照合はTask 2・4・5・6に対応する。確認済み空欄の取得関数を共用し、NULLをそのまま減算しない。
- 設計6節の旧値保持・再移行・中断・互換性変更はTask 3・6に対応する。SQLのINTEGER宣言だけに型検証を依存しない。
- 設計7・8節の7文書・strict契約・架空画像・独立期待値・二人物回帰はTask 1・5・6に対応する。新しい関数とモデルの名前・型は後続Taskと一致する。
- 各Taskは失敗テスト→失敗確認→最小実装→再検証の順であり、Review Focusの5項目を該当Taskのテストで固定した。
- 計画は親が確認し、続行指示に基づいて実装している。全6段階を実装・検証し、全体1650件、Ruff、format、mypy、CLI 1.0.0と110コマンドの契約を確認した。修正前後の記録と画像評価の限界はplayground/withholding-validation/report.mdに残した。
