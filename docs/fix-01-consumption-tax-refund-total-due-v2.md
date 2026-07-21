# 修正指示書 #01 (v2): 消費税還付時に `total_due` へ国税還付分が反映されない

| 項目 | 内容 |
|------|------|
| 優先度 | **高**（申告サマリー・引継書の還付額が誤る） |
| 対象ファイル | `src/shinkoku/tools/tax_calc.py`（`calc_consumption_tax`, L1461〜1486付近） |
| 付随修正 | `src/shinkoku/models.py`、`skills/consumption-tax/SKILL.md`、`skills/e-tax/SKILL.md`、`pyproject.toml`、`.claude-plugin/plugin.json` |
| テスト追加先 | `tests/unit/test_consumption_tax_rounding.py`（`TestRefundCase` クラス） |
| スコープ外 | 地方消費税の中間納付（中間納付譲渡割額）対応 → §6 の別課題として起票 |

## 改訂履歴

| 版 | 日付 | 内容 |
|----|------|------|
| v1 | 2026-07-13 | 初版 |
| v2 | 2026-07-13 | 調査報告書（fix-01-consumption-tax-refund-investigation-report-2026-07-13）の指摘5点を反映: ① `tax_due` とAAJ00120の直接対応の記述を削除し符号付き集計値として再定義 ② 地方中間納付を別課題に分離し中間納付テストを除外 ③ テストコードを実行可能な完全形に差し替え ④ バージョン更新（0.6.5→0.6.6）を必須化 ⑤ ドキュメント同期範囲を拡大。指摘はすべてリポジトリ・CI定義で裏取り済み |

---

## 1. 背景（なぜ直すか）

本則課税で仕入税額が売上税額を上回る場合（設備投資が大きい年など）、国税の還付分は `refund_shortfall` に格納される。しかし合計額の計算が

```python
tax_due = net_tax - interim_payment      # 還付時は net_tax = 0
total_due = tax_due + local_tax
```

となっており、**`refund_shortfall` がどこにも加算されない**。その結果、「合計納付税額（負 = 還付）」と定義されている `total_due` が地方消費税の還付分だけになり、国税分の還付額が丸ごと欠落する。consumption-tax スキルはこの値を計算結果サマリーと引継書（`.shinkoku/progress/08-consumption-tax.md`）に転記するため、ユーザーに提示する還付額が大幅に過少になる。

あわせて、還付時の地方消費税に納付時と同じ100円未満切捨てを適用している問題も同時に直す。国税庁の令和7年分手引きでも、**100円未満切捨ての対象は地方消費税の「納税額」のみで、「還付額」には適用しない**。現行実装では還付額が最大99円過少になる。

### 再現（検証済み）

```
入力: method=standard, taxable_sales_10=1,100,000, taxable_purchases_10=5,500,000
現状: refund_shortfall=312,000 / local_tax_due=-88,000 / total_due=-88,000
期待: total_due=-400,000（国税還付 312,000 + 地方消費税還付 88,000）
```

---

## 2. 修正内容

### 2-1. `total_due` に `refund_shortfall` を反映する

```python
total_due = tax_due - refund_shortfall + local_tax
```

**`tax_due` の計算式は変更しない**（`net_tax - interim_payment` のまま）。ただしその位置づけは v1 の「申告書の納付税額欄（AAJ00120）に直接対応」ではなく、次のとおり**後方互換の符号付き集計値**として説明する:

- 正の場合: 申告書第一表「納付税額⑪」に相当（この場合のみ AAJ00120 へ転記可能）
- 負の場合: 絶対値が「中間納付還付税額⑫」に相当（申告書上、⑪に負値は記載しない）
- 申告書欄（⑪/⑫）への振り分けは表示側・e-tax側の責務であり、本関数は符号付きで返す

この判断を Why not コメントとしてコードに残すこと:

```python
# NOTE: tax_due は後方互換の符号付き集計値（正=納付税額⑪相当、
# 負=中間納付還付税額⑫相当の絶対値）。申告書欄への振り分けは
# 表示側の責務のため、還付時でも控除不足還付税額（refund_shortfall）は
# ここに含めない。納付/還付の合計は total_due が持つ。
tax_due = net_tax - interim_payment
```

### 2-2. 還付時の地方消費税は100円未満切捨てをやめる

```python
elif refund_shortfall > 0:
    # 還付譲渡割額は100円未満切捨ての対象外（切捨ては納税額のみ。
    # 令和7年分手引き: 地方消費税の税額計算）
    local_tax = -(refund_shortfall * LOCAL_TAX_RATIO // NATIONAL_TAX_RATIO)
```

納付側（`net_tax > 0` の分岐）の切捨ては現状のまま維持する。

### 2-3. スコープの明示: 地方消費税の中間納付は本修正に含めない

`ConsumptionTaxInput` には国税の `interim_payment` しか存在しない一方、e-tax の入力では中間納付消費税額（`chukanNofuZei`）と中間納付譲渡割額（`chukanNofuJotoWari`）が別項目になっている（`skills/e-tax/SKILL.md` L882-883）。つまり**地方の中間納付がある場合、`total_due` は本修正後も完全ではない**。これは入力モデルの拡張を伴うため §6 の別課題に分離し、本修正では制約をコードコメントで可視化するに留める:

```python
# NOTE: 地方消費税の中間納付譲渡割額は入力モデルに存在しないため
# total_due に反映されない（Issue: 中間納付譲渡割額の入力対応）。
total_due = tax_due - refund_shortfall + local_tax
```

### 2-4. ドキュメントの同期

| ファイル | 更新内容 |
|---------|---------|
| `src/shinkoku/tools/tax_calc.py` | `calc_consumption_tax` docstring の計算フロー（Step 4/5）に還付時の扱いを追記。Step 5 のコメント「100円未満切捨」に「納税額のみ。還付額は切捨てなし」を明記 |
| `src/shinkoku/models.py` | `ConsumptionTaxResult` クラスdocstringの Step 5 記述を同上に更新。`tax_due` コメントを「符号付き集計値 = net_tax - interim_payment（正=納付税額⑪/AAJ00120、負=中間納付還付税額⑫相当）」に変更。`local_tax_due` を「納付時は100円未満切捨、還付時は切捨てなし」に、`total_due` を「= tax_due − refund_shortfall + local_tax_due（負=還付。地方の中間納付は未考慮）」に更新 |
| `skills/consumption-tax/SKILL.md` | 出力フィールド説明（L128-132）を上記と同期。計算結果サマリー（L250-254付近）と引継書テンプレート（L303-305付近）の「合計納付税額」に「（マイナスの場合は還付額）」の条件付き表記を追加 |
| `skills/e-tax/SKILL.md` | 地方消費税の100円未満切捨てが納税額のみに適用される旨を該当箇所に追記 |
| `CHANGELOG.md` | 任意（0.2.0以降更新が途絶えており、CIでも検証されない。追記する場合は Keep a Changelog 形式の Fixed 節） |

### 2-5. バージョン更新（CI必須）

`src/` と `skills/` を変更するため、CI の Version Check（`.github/workflows/test.yml` の `version-check` ジョブ）がバージョン更新を要求する。バグ修正のため **0.6.5 → 0.6.6** に更新する。CIは両ファイルの一致も検証するため、必ず同時に更新すること:

- `pyproject.toml` の `version`
- `.claude-plugin/plugin.json` の `version`

---

## 3. テスト（追加する仕様）

`tests/unit/test_consumption_tax_rounding.py` の `TestRefundCase` に以下2件を追加する（`calc_consumption_tax` / `ConsumptionTaxInput` は同ファイルでimport済み）。そのまま貼り付けて実行可能な完全形:

```python
def test_refund_total_due_includes_national_refund_shortfall(self) -> None:
    """売上110万・仕入550万(本則): total_due = -(312,000 + 88,000) = -400,000。"""
    r = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2025,
            method="standard",
            taxable_sales_10=1_100_000,
            taxable_purchases_10=5_500_000,
        )
    )
    assert r.refund_shortfall == 312_000
    assert r.local_tax_due == -88_000
    assert r.total_due == -400_000

def test_refund_local_tax_is_not_truncated_to_100yen(self) -> None:
    """還付譲渡割に端数が出るケース: -22,481 のまま返す（-22,400 に切捨てない）。"""
    r = calc_consumption_tax(
        ConsumptionTaxInput(
            fiscal_year=2025,
            method="standard",
            taxable_sales_10=110_000,
            taxable_purchases_10=1_234_100,
        )
    )
    # 売上国税: 課税標準100,000 × 7.8% = 7,800
    # 仕入国税: 1,234,100 × 78 // 1100 = 87,508
    # refund_shortfall = 79,708 → 79,708 × 22 // 78 = 22,481
    assert r.refund_shortfall == 79_708
    assert r.local_tax_due == -22_481
    assert r.total_due == -(79_708 + 22_481)
```

期待値の根拠（検算済み）:

| ケース | 課税標準額 | 売上国税 | 仕入国税 | refund_shortfall | 還付譲渡割 |
|--------|-----------|---------|---------|-----------------|-----------|
| 110万/550万 | 1,000,000 | 78,000 | 390,000 | 312,000 | 88,000 |
| 11万/1,234,100 | 100,000 | 7,800 | 87,508 | 79,708 | 22,481 |

- v1 にあった中間納付を含む3件目のテストは、地方の中間納付が未対応である前提を焼き込むため本指示書から除外した。§6 の別課題側で、国税・地方の中間納付を組み合わせたケースとして追加する
- 既存の `test_refund_basic` / `test_refund_not_blocked` / `test_refund_local_tax_negative` は緩いアサーション（`total_due < 0` 等）のため修正不要で、そのままパスするはず。納付側の既存テスト（`TestRefundCase` 以外の19件）に影響がないことも確認する

---

## 4. コミットメッセージ案

```
fix: 消費税還付時に total_due へ控除不足還付税額が反映されない問題を解消

本則課税で仕入税額が売上税額を上回る場合、国税の還付分が
refund_shortfall に分離されたまま合計に加算されず、
「合計納付税額（負=還付）」が地方消費税分のみになっていた。
設備投資年の還付額をサマリー・引継書で大幅に過少提示してしまう。

あわせて、還付時の地方消費税に納付時と同じ100円未満切捨てを
適用していた問題も修正する。手引きのとおり切捨ての対象は
納税額のみで、還付額は1円単位（切捨てなし）が正しい。

地方消費税の中間納付譲渡割額は入力モデルに存在せず本修正の
対象外（別Issueに分離）。
```

---

## 5. 完了条件

1. 基本還付ケースで `total_due == -400_000` になる
2. 端数がある還付ケースで `local_tax_due == -22_481` になる
3. 納付側の既存結果が変化しない（既存テスト全件パス）
4. `tax_due` の説明が「符号付き集計値」であり、申告書欄（⑪/⑫）との関係に矛盾がない（AAJ00120への直接対応という記述が残っていない）
5. 地方中間納付が未対応である旨のコメントがコード上に残っている
6. `pyproject.toml` と `.claude-plugin/plugin.json` のバージョンが `0.6.6` で一致している
7. `uv run pytest tests/unit/ tests/scripts/` が成功する
8. `uv run mypy src/shinkoku/ --ignore-missing-imports` が成功する
9. `uv run ruff check src/ tests/` および `uv run ruff format --check src/ tests/` が成功する
10. §2-4 の表に挙げたコメント・スキル文書がすべて実装と一致している

---

## 6. 別課題として起票する内容（Issue草案）

```
タイトル: 消費税: 地方消費税の中間納付（中間納付譲渡割額）に対応する

ConsumptionTaxInput には国税の interim_payment のみが存在するが、
確定申告書等作成コーナー / e-tax では中間納付消費税額（chukanNofuZei）と
中間納付譲渡割額（chukanNofuJotoWari）を別項目で入力する
（skills/e-tax/SKILL.md L882-883）。地方の中間納付がある事業者では
total_due が正しい合計にならない。

対応案:
- ConsumptionTaxInput に interim_local_payment（中間納付譲渡割額）を追加（デフォルト0）
- total_due の計算へ反映し、tax_due と対になる地方側の集計値も検討
- テスト: 国税・地方の中間納付を組み合わせた納付/還付ケース
  （例: 還付312,000+88,000・国税中間納付50,000 → total_due == -450,000 に
   地方中間納付分を加えた期待値）

関連: 修正指示書 #01 v2（total_due への refund_shortfall 反映）のスコープ外事項
```
