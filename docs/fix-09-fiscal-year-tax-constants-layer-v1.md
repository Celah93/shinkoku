# fix-09: 年分別税制定数レイヤーの新設（令和8年度税制改正 対応の基盤）

- 作成日: 2026-07-15
- 優先度: P0（令和8年分の計算に必須。以後の #10以降すべての前提）
- 対象: `src/shinkoku/tax_constants.py`、`src/shinkoku/tools/tax_calc.py`
- 根拠資料: `_handoff_claude/fix-09-reiwa8-tax-reform-impact-investigation-report-2026-07-15.md`（Codex調査）、国税庁「令和８年度税制改正による所得税の基礎控除の引上げ等について」（https://www.nta.go.jp/users/gensen/2026kiso/index.htm）、国税庁「令和８年５月　所得税の基礎控除の引上げ等Ｑ＆Ａ」（https://www.nta.go.jp/users/gensen/2026kiso/pdf/0026005-024.pdf）で数値・適用日を一次資料照合済み

## 1. 背景

### 1.1 現状の問題

`IncomeTaxInput` と `ConsumptionTaxInput` は `fiscal_year` を受け取るが、`tax_constants.py` の税制定数（基礎控除表、給与所得控除の最低保障額、扶養親族等の所得要件など）は令和7年分の一組しか存在しない。`calc_income_tax()` などの計算関数は `fiscal_year` を検証やラベリングに使うのみで、定数選択には使っていない。

このため、令和8年分の申告データを計算しても、実際には令和7年分の税制（基礎控除58万円ベースの表、給与所得控除最低65万円、扶養親族等所得要件58万円）で計算されてしまい、**控除不足による過大申告**が発生する。

### 1.2 令和8年度改正の該当箇所（一次資料照合済み）

| 制度 | 令和7年分（現行コード） | 令和8・9年分 | 適用開始 |
|---|---|---|---|
| 基礎控除（合計所得132万円以下） | 95万円 | 104万円 | 令和8年分から |
| 基礎控除（132万円超336万円以下） | 88万円 | 104万円 | 同上 |
| 基礎控除（336万円超489万円以下） | 68万円 | 104万円 | 同上 |
| 基礎控除（489万円超655万円以下） | 63万円 | 67万円 | 同上 |
| 基礎控除（655万円超2,350万円以下） | 58万円 | 62万円 | 同上 |
| 基礎控除（2,350万円超2,400万円以下） | 48万円 | 48万円（変更なし） | - |
| 基礎控除（2,400万円超2,450万円以下） | 32万円 | 32万円（変更なし） | - |
| 基礎控除（2,450万円超2,500万円以下） | 16万円 | 16万円（変更なし） | - |
| 基礎控除（2,500万円超） | 0円 | 0円（変更なし） | - |
| 給与所得控除 最低保障額 | 65万円 | 69万円（本則）、**令和8・9年分だけ74万円**（特例上乗せ） | 令和8年分から |
| 扶養親族・同一生計配偶者の所得要件 | 58万円以下 | 62万円以下 | 令和8年分から |
| 特定親族特別控除の下限 | 58万円超 | 62万円超（上限123万円・各段階の控除額は据置き） | 令和8年分から |
| 配偶者特別控除の下限 | 58万円超 | 62万円超（上限133万円・段階は据置き） | 令和8年分から |
| 勤労学生の所得要件 | 85万円以下 | 89万円以下 | 令和8年分から |
| 家内労働者等の必要経費最低保障 | 65万円 | 69万円 | 令和8年分から（**現行未実装の制度**、本指示書の対象外） |

給与収入220万円以下かつ69.1万円以上219.6万円未満のレンジには、国税庁が公表する特別な段差表（「収入－74万円」等）が存在するが、これは #10（給与所得控除の実装）で扱う。本指示書ではレイヤーの受け皿のみを用意する。

### 1.3 なぜ今すぐ全部を実装しないか

このリポジトリは令和7年分の確定申告（2026年提出）に加え、これから令和8年分のデータ入力も並行して扱う可能性がある。定数を令和8年表に**上書き**すると令和7年分の再計算（去年のデータの検算・修正）が壊れる。そのため、まず「年分をキーに定数一式を選択する」レイヤーを作り、令和7年分の値をそのまま最初のエントリとして温存したうえで、令和8年分のテーブルを追加する、という2段階構成にする。

## 2. 実装方針

### 2.1 データ構造

`tax_constants.py` に年分別定数を束ねる仕組みを導入する。既存のモジュールレベル定数（`BASIC_DEDUCTION_TABLE` 等）はそのまま令和7年分のデフォルトとして残し、後方互換を壊さない。

```python
# tax_constants.py に追加

from typing import Final

# 各年分の基礎控除テーブルを保持する辞書。
# キーは fiscal_year（int）。値は既存の BASIC_DEDUCTION_TABLE と同じ形式。
BASIC_DEDUCTION_TABLE_BY_YEAR: Final[dict[int, list[tuple[int, int]]]] = {
    2025: BASIC_DEDUCTION_TABLE,  # 既存の令和7年分をそのまま参照
    2026: [
        (1_320_000, 1_040_000),
        (3_360_000, 1_040_000),
        (4_890_000, 1_040_000),
        (6_550_000, 670_000),
        (23_500_000, 620_000),
        (24_000_000, 480_000),
        (24_500_000, 320_000),
        (25_000_000, 160_000),
    ],
}
# 2027年分も2026年と同額（令和8・9年分は同じ表）。
BASIC_DEDUCTION_TABLE_BY_YEAR[2027] = BASIC_DEDUCTION_TABLE_BY_YEAR[2026]

SALARY_DEDUCTION_MIN_BY_YEAR: Final[dict[int, int]] = {
    2025: SALARY_DEDUCTION_MIN,  # 65万円
    2026: 740_000,  # 本則69万円 + 令和8・9年分特例5万円
    2027: 740_000,
}

DEPENDENT_INCOME_LIMIT_BY_YEAR: Final[dict[int, int]] = {
    2025: DEPENDENT_INCOME_LIMIT,  # 58万円
    2026: 620_000,
    2027: 620_000,
}

WORKING_STUDENT_INCOME_LIMIT_BY_YEAR: Final[dict[int, int]] = {
    2025: WORKING_STUDENT_INCOME_LIMIT,  # 85万円
    2026: 890_000,
    2027: 890_000,
}


def get_basic_deduction_table(fiscal_year: int) -> list[tuple[int, int]]:
    """年分に対応する基礎控除テーブルを返す。

    未対応の年分（テーブルに存在しない年）は ValueError を送出する。
    将来の年分を安易にフォールバックさせない。
    """
    if fiscal_year not in BASIC_DEDUCTION_TABLE_BY_YEAR:
        raise ValueError(
            f"fiscal_year={fiscal_year} の基礎控除テーブルが未定義です。"
            f"対応年分: {sorted(BASIC_DEDUCTION_TABLE_BY_YEAR.keys())}"
        )
    return BASIC_DEDUCTION_TABLE_BY_YEAR[fiscal_year]


def get_salary_deduction_min(fiscal_year: int) -> int:
    if fiscal_year not in SALARY_DEDUCTION_MIN_BY_YEAR:
        raise ValueError(
            f"fiscal_year={fiscal_year} の給与所得控除最低保障額が未定義です。"
            f"対応年分: {sorted(SALARY_DEDUCTION_MIN_BY_YEAR.keys())}"
        )
    return SALARY_DEDUCTION_MIN_BY_YEAR[fiscal_year]


def get_dependent_income_limit(fiscal_year: int) -> int:
    if fiscal_year not in DEPENDENT_INCOME_LIMIT_BY_YEAR:
        raise ValueError(
            f"fiscal_year={fiscal_year} の扶養親族所得要件が未定義です。"
            f"対応年分: {sorted(DEPENDENT_INCOME_LIMIT_BY_YEAR.keys())}"
        )
    return DEPENDENT_INCOME_LIMIT_BY_YEAR[fiscal_year]


def get_working_student_income_limit(fiscal_year: int) -> int:
    if fiscal_year not in WORKING_STUDENT_INCOME_LIMIT_BY_YEAR:
        raise ValueError(
            f"fiscal_year={fiscal_year} の勤労学生所得要件が未定義です。"
            f"対応年分: {sorted(WORKING_STUDENT_INCOME_LIMIT_BY_YEAR.keys())}"
        )
    return WORKING_STUDENT_INCOME_LIMIT_BY_YEAR[fiscal_year]
```

### 2.2 `tax_calc.py` 側の変更

`calc_income_tax()` 等が定数を直接参照している箇所（`BASIC_DEDUCTION_TABLE` を直接読んでいる箇所など）を、`get_basic_deduction_table(fiscal_year)` 呼び出しに置き換える。**この指示書の実装範囲では、基礎控除・給与所得控除・扶養親族等所得要件の「値の選択」のみを年分別にする**。給与所得控除の段差表（69.1万〜220万円未満）や特定親族特別控除・配偶者特別控除の表の年分別化、消費税の経過措置切替は #10以降で扱う。

`fiscal_year` が未対応の年分（例: 2024年分やまだテーブルのない2028年分）の場合、`get_*` 関数が `ValueError` を送出する。この例外は `calc_income_tax()` の呼び出し元（MCPツール層）でキャッチし、ユーザーに分かる形のエラーメッセージ（例: `{"status": "error", "message": "fiscal_year=2024 は未対応です"}`）に変換する。**サイレントに令和7年分へフォールバックしない。** 誤った年分の値で計算されることは、未対応エラーより悪い。

### 2.3 Why not（却下した実装方針）

**却下1: 既存定数を令和8年表で直接上書きする**
理由: 令和7年分の再計算・過去データの検算が即座に壊れる。#02の期首残高バグのように「過去年度のデータを扱うユーザー」が実在する前提を壊す。

**却下2: `fiscal_year` ごとに `tax_constants_2025.py` / `tax_constants_2026.py` とモジュールを分割する**
理由: 現時点では差分が基礎控除・給与所得控除・扶養要件の3項目のみで、モジュール全体を複製すると同期漏れのリスク（一方だけ直して他方を直し忘れる）が上がる。定数点数が増えて破綻したら、その時点でモジュール分割を再検討する。辞書ベースの年分キーであれば差分だけを追加すればよく、令和7年分の定義を変更せずに済む。

**却下3: 未対応年分は最も新しい年分の値にフォールバックする**
理由: 一見親切だが、令和9年分と令和8年分は基礎控除は同額でも給与所得控除の特例（74万円は令和8・9年分限定）のように「同じに見えて実は年数限定」の項目があるため、無条件フォールバックは将来の年分改正時に静かに誤った値を使うリスクを生む。年分ごとに明示的にテーブルへ追加する運用とし、未定義はエラーにする。

**却下4: CPIスライド計算式をコードに実装し、将来年分を自動算出する**
理由: 報告書が指摘するとおり、CPI連動は令和10年分以後の「基本方針」であり、次回の具体的な金額は今後の税制改正で確定する（自動スライド条項ではない）。算定方法の詳細が政令未確定の段階でコード化すると、確定した公式の値と食い違うリスクがある。今回は法律で確定済みの令和8・9年分の金額のみをテーブルに直接記載する。

## 3. テスト仕様

以下は実装前のドラフトであり、Codexが実装後に実際の関数シグネチャに合わせて微調整してよい。ただし期待値（金額）は変更しないこと。

```python
# tests/unit/test_tax_constants_fiscal_year.py

import pytest
from shinkoku.tax_constants import (
    get_basic_deduction_table,
    get_salary_deduction_min,
    get_dependent_income_limit,
    get_working_student_income_limit,
)


class TestBasicDeductionTableByYear:
    def test_2025_matches_existing_table(self):
        """令和7年分は既存の値のまま変わらないこと（後方互換の要）。"""
        table = get_basic_deduction_table(2025)
        # 合計所得132万円以下は95万円のまま
        assert table[0] == (1_320_000, 950_000)

    def test_2026_basic_deduction_low_income_is_1040000(self):
        """令和8年分、合計所得132万円以下は104万円。"""
        table = get_basic_deduction_table(2026)
        assert table[0] == (1_320_000, 1_040_000)

    def test_2026_basic_deduction_336_to_489_is_1040000(self):
        """令和8年分、336万円超489万円以下も104万円（令和7年分の68万円から+36万円）。"""
        table = get_basic_deduction_table(2026)
        # 489万円以下の行を探索
        matched = [row for row in table if row[0] == 4_890_000]
        assert matched[0] == (4_890_000, 1_040_000)

    def test_2026_basic_deduction_489_to_655_is_670000(self):
        """令和8年分、489万円超655万円以下は67万円。"""
        table = get_basic_deduction_table(2026)
        matched = [row for row in table if row[0] == 6_550_000]
        assert matched[0] == (6_550_000, 670_000)

    def test_2026_basic_deduction_655_to_2350_is_620000(self):
        """令和8年分、655万円超2,350万円以下は62万円。"""
        table = get_basic_deduction_table(2026)
        matched = [row for row in table if row[0] == 23_500_000]
        assert matched[0] == (23_500_000, 620_000)

    def test_2026_high_income_brackets_unchanged(self):
        """2,350万円超の高所得帯は令和7年分と同額（変更なし）。"""
        table_2025 = get_basic_deduction_table(2025)
        table_2026 = get_basic_deduction_table(2026)
        high_income_2025 = [row for row in table_2025 if row[0] > 23_500_000]
        high_income_2026 = [row for row in table_2026 if row[0] > 23_500_000]
        assert high_income_2025 == high_income_2026

    def test_2027_same_as_2026(self):
        """令和9年分の基礎控除は令和8年分と同額。"""
        assert get_basic_deduction_table(2027) == get_basic_deduction_table(2026)

    def test_unsupported_year_raises_value_error(self):
        """未定義の年分（例: 2028）はサイレントなフォールバックをせずエラー。"""
        with pytest.raises(ValueError, match="2028"):
            get_basic_deduction_table(2028)

    def test_pre_reform_year_raises_value_error(self):
        """テーブルが用意されていない過去年分（例: 2020）もエラー。"""
        with pytest.raises(ValueError):
            get_basic_deduction_table(2020)


class TestSalaryDeductionMinByYear:
    def test_2025_is_650000(self):
        """令和7年分は現行の65万円のまま。"""
        assert get_salary_deduction_min(2025) == 650_000

    def test_2026_is_740000_with_special_addition(self):
        """令和8年分は本則69万円+特例5万円=74万円。"""
        assert get_salary_deduction_min(2026) == 740_000

    def test_2027_is_740000_special_still_active(self):
        """令和9年分も特例が続くため74万円。"""
        assert get_salary_deduction_min(2027) == 740_000

    def test_unsupported_year_raises(self):
        with pytest.raises(ValueError):
            get_salary_deduction_min(2028)


class TestDependentIncomeLimitByYear:
    def test_2025_is_580000(self):
        assert get_dependent_income_limit(2025) == 580_000

    def test_2026_is_620000(self):
        """令和8年分、扶養親族等所得要件は62万円以下に緩和。"""
        assert get_dependent_income_limit(2026) == 620_000


class TestWorkingStudentIncomeLimitByYear:
    def test_2025_is_850000(self):
        assert get_working_student_income_limit(2025) == 850_000

    def test_2026_is_890000(self):
        """令和8年分、勤労学生所得要件は89万円以下に緩和。"""
        assert get_working_student_income_limit(2026) == 890_000


# --- calc_income_tax() 統合テスト（既存テストへの追加分） ---
# tests/unit/test_tax_calc.py または既存の該当ファイルに追加する想定

class TestCalcIncomeTaxFiscalYearSwitch:
    def test_income_tax_2025_unaffected_by_2026_table(self, ...):
        """令和7年分の所得税計算結果が、本改修の前後で変わらないこと（回帰防止）。"""
        # 既存の令和7年分テストケース（合計所得300万円等、既存のfixtureを流用）と
        # 同じ入力・同じ期待値で fiscal_year=2025 を計算し、既存の期待値と一致することを確認する。
        ...

    def test_income_tax_2026_uses_expanded_basic_deduction(self, ...):
        """令和8年分、合計所得300万円のケースで基礎控除104万円が使われること。"""
        # 合計所得3,000,000円、fiscal_year=2026 のケースで
        # 基礎控除が1,040,000円として控除に反映されていることを確認する。
        ...

    def test_income_tax_unsupported_fiscal_year_returns_error(self, ...):
        """未対応年分（2028等）を渡すとMCPツール層でエラーレスポンスになること。"""
        # calc_income_tax(..., fiscal_year=2028) が例外を伝播させず、
        # {"status": "error", ...} 形式のレスポンスになることを確認する。
        ...
```

### 3.1 特に確認すべき境界値

- 合計所得489万円ちょうど（`336万円超489万円以下`の上限）→ 令和8年分は104万円
- 合計所得489万円超656万円未満、特に655万円ちょうど（`489万円超655万円以下`の上限）→ 令和8年分は67万円
- 合計所得2,350万円ちょうど（62万円が適用される上限）と2,350万円1円超（48万円へ切替）の境界

これらは #01〜#08 で繰り返し実証されている「境界値でこそバグが出る」というプロジェクトの経験則に沿ったものなので、実装報告書には各境界値の実際の計算結果を明記すること。

## 4. 完了条件

- [ ] `tax_constants.py` に `BASIC_DEDUCTION_TABLE_BY_YEAR`、`SALARY_DEDUCTION_MIN_BY_YEAR`、`DEPENDENT_INCOME_LIMIT_BY_YEAR`、`WORKING_STUDENT_INCOME_LIMIT_BY_YEAR` と対応する `get_*()` 関数を追加
- [ ] 令和7年分（2025）のテーブルは既存定数をそのまま参照し、既存の全テストが無改修でパスすること
- [ ] 令和8年分（2026）・令和9年分（2027）のテーブルを一次資料の値で追加
- [ ] `calc_income_tax()` が基礎控除・給与所得控除最低保障額・扶養親族等所得要件の参照箇所で `get_*(fiscal_year)` を使うよう置き換え
- [ ] 未対応年分は `ValueError` → MCPツール層で `{"status": "error"}` に変換し、サイレントフォールバックしないこと
- [ ] 上記テスト仕様の全ケースが green
- [ ] 既存295+αのテストが全件パス（令和7年分の回帰がないこと）
- [ ] バージョンを `0.6.13` に更新（`pyproject.toml` + `.claude-plugin/plugin.json`）
- [ ] `uv lock` 実行、`uv.lock` を同時コミット
- [ ] `uv run mypy src/shinkoku/ --ignore-missing-imports` / `ruff check` / `ruff format --check` 成功
- [ ] 作業報告書に、境界値（489万円、655万円、2,350万円）の実際の計算結果を明記
- [ ] 給与所得控除の段差表（69.1万〜220万円未満）・特定親族特別控除表・配偶者特別控除表の年分別化は本指示書の範囲外である旨を報告書に明記し、#10として別途指示書化する

## 5. コミットメッセージ案

```
feat: 年分別税制定数レイヤーを新設し、令和8年分の基礎控除等に対応

- tax_constants.py に BASIC_DEDUCTION_TABLE_BY_YEAR 等の年分別辞書と
  get_basic_deduction_table() 等のアクセサ関数を追加
- 令和7年分は既存定数をそのまま参照し後方互換を維持
- 令和8・9年分の基礎控除（最大104万円）、給与所得控除最低保障額
  （令和8・9年分特例により74万円）、扶養親族等所得要件（62万円）を追加
- calc_income_tax() の該当参照箇所を年分別アクセサに置き換え
- 未対応の fiscal_year は ValueError → エラーレスポンスとし、
  誤った年分の値へのサイレントフォールバックを防止

Refs: fix-09-reiwa8-tax-reform-impact-investigation-report-2026-07-15.md
```

## 6. 次の指示書（#10以降）への申し送り

本指示書の完了後、以下を個別の指示書として分割する（一括タスク化しない、との運用方針どおり）:

1. **#10: 給与所得控除の段差表実装**（給与収入69.1万〜220万円未満の特別計算式、令和8・9年分限定）
2. **#11: 特定親族特別控除・配偶者特別控除の年分別所得要件**（58万円超→62万円超、控除額段階は据置き）
3. **#12: 消費税・免税事業者等からの仕入控除の経過措置**（2026-10-01で80%→70%、取引日ベースの判定が必要）
4. **#13: 住宅ローン控除の2026年入居表**
5. **#14: 少額減価償却資産特例（40万円未満、2026-04-01取得分から。現行未実装の新規制度）**

これらはいずれも本指示書で新設する年分別定数レイヤーの上に乗る想定。#10以降の指示書作成時は、本指示書で追加した `get_*()` 関数の実際のシグネチャをCodexの実装報告書で確認してから、それに合わせて書くこと。
