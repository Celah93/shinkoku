---
name: furusato
description: ふるさと納税の寄附記録を確認・登録し、集計と控除上限を確認する。
---

# ふるさと納税管理（Furusato Nozei Management）

ふるさと納税の寄附金受領証明書を読み取り、寄附データを管理し、控除額を計算するスキル。


個別データを扱う場合だけ [共通の設定・確認境界](../_shared/context.md) を参照します。

## ステップ1: 受領証明書の画像読み取り

### 1-1. ファイルの確認

`shinkoku import furusato-receipt --file-path PATH` でファイルの存在を確認する。

### 1-2. 画像の読み取り

**画像の読み取りは対応する reading-* Skill の形式を使い、通常はメインエージェントが行います。**

#### 単一の受領証明書の場合

画像ファイルの読み取りには `/reading-receipt` スキルを使用する。
   読み取り方・照合・不明箇所の扱いは該当する reading-* Skill に従います。実データへの登録前に確認する内容をまとめます。

読み取り結果の `---FURUSATO_RECEIPT_DATA---` ブロックから以下の情報を取得する:

- **自治体名**: 寄附先の市区町村名
- **都道府県名**: 寄附先の都道府県
- **寄附金額**: 円単位の整数
- **寄附日**: YYYY-MM-DD 形式
- **受領証明書番号**: 記載があれば

#### 複数の受領証明書を一括処理する場合

1. Glob ツールで受領証明書画像の一覧を取得する（例: `furusato_receipts/*.jpg`, `furusato_receipts/*.png`）
2. `shinkoku import furusato-receipt --file-path PATH` で各ファイルの存在を確認する
3. 画像ファイルの読み取りには `/reading-receipt` スキルを使用する。
   読み取り方・照合・不明箇所の扱いは該当する reading-* Skill に従います。実データへの登録前に確認する内容をまとめます。

4. 各証明書の結果をまとめてユーザーに提示する

### 1-3. ユーザーに確認

抽出した情報を一覧表示し、正しいか確認する。修正があればユーザーの入力を反映する。


## ステップ2: 寄附データの登録

確認が完了したら `furusato.py add` で登録する。

```bash
shinkoku furusato add --db-path DB --input FILE
```

入力 JSON ファイルのフォーマット:
```json
{
  "fiscal_year": 2025,
  "municipality_name": "自治体名",
  "amount": 30000,
  "date": "2025-06-15",
  "municipality_prefecture": "都道府県",
  "receipt_number": "受領証明書番号",
  "one_stop_applied": false
}
```

### ワンストップ特例の確認

登録時に「ワンストップ特例を申請しましたか？」と確認する。

**重要な注意**: 副業で確定申告する場合、ワンストップ特例は**無効化**される。
確定申告時に全額を寄附金控除として申告する必要がある。


## ステップ3: 複数の証明書を繰り返し処理

「他に受領証明書はありますか？」と確認し、あればステップ1~2を繰り返す。


## ステップ4: 集計と控除上限チェック

すべての寄附データを登録したら `furusato.py summary` で集計する。

```bash
shinkoku furusato summary --db-path DB --fiscal-year YEAR [--estimated-limit N]
```

表示する情報:
- 寄附先自治体数と合計金額
- 所得控除額（合計 - 2,000円）
- ワンストップ特例申請数
- 控除上限の推定（所得情報がある場合）

### 控除上限の推定

設定・`profile` の `family` と `housing_loan` を使う場合は [確認状態の意味](../../docs/tax-eligibility.md#設定から引き継ぐ確認状態) に従う。
上限や実負担の判断に必要な項目が `null` なら、不適用や0と仮定せずに確認する。`estimated_tax` は予定納税の確認状態であり、住民税の所得控除として差し引かない。

住民税の計算済み資料がない場合は、総合課税所得・課税区分と各控除の確認済み元データを使い、次のCLIで標準所得割を組み立てる。入力は `docs/resident-tax-estimate.md` を参照する。結果の `furusato_input` を既存の上限CLIに渡せる。課税区分や親族の適格性が不明なときは推測しない。

```bash
shinkoku tax calc-resident-tax-estimate --input FILE
```

所得情報が把握できている場合は `shinkoku tax calc-furusato-limit --input FILE` で上限を推定する。

入力JSONの `fiscal_year` に寄附した年を明示する。対応年分は2025〜2027年。2027年は住民税の所得割額・課税所得・人的控除差・所得税基礎控除を入力し、所得税側の控除で代用しない。193万円は寄附額ではなく特例控除額の上限で、2027年寄附は2028年度住民税へ適用する。詳しい入力と概算の制限は `docs/furusato-and-minimum-tax-2027.md` を参照する。年分を変更・削除して未対応エラーを回避しない。年分省略時2025年は旧入力との互換性のためで、新しい入力では明示する。

```bash
shinkoku tax calc-furusato-limit --input FILE
```

内訳も確認する場合は次を使う。`estimated_limit` と `special_credit_limit` を取り違えず、`warnings` を確認する。

```bash
shinkoku tax calc-furusato-limit-detailed --input FILE
```

上限超過の場合は警告を表示:
「寄附合計額が推定上限を超えています。超過分は自己負担となります。」


## ステップ5: 確定申告との関係

以下を説明する:
- 副業で確定申告する場合、ワンストップ特例は使えない
- 確定申告で寄附金控除（所得控除）として申告する
- 所得税からの控除 = (寄附合計 - 2,000) x 所得税率
- 住民税からの控除は別途計算される（特例分含む）


## リファレンスファイル参照ガイド

| 質問カテゴリ | 参照ファイル |
|-------------|-------------|
| ふるさと納税の税制ルール・計算式 | `references/furusato-tax-rules.md` |
| 上限額・返礼品・タイミング・相談全般 | `references/furusato-consultation-guide.md` |


## 次のステップの案内

- `income-tax` スキルで所得税の計算に進む（寄附金控除が自動反映される）
- 他の控除（医療費控除等）がある場合は先にそちらを処理する


## 引継書の出力

サマリー提示後、以下のファイルを ファイル書込ツールで出力する。
これにより、セッションの中断や Compact が発生しても次のステップで結果を引き継げる。

### ステップ別ファイルの出力

`.shinkoku/progress/05-furusato.md` に以下の形式で出力する:

```
---
step: 5
skill: furusato
status: completed
completed_at: "{当日日付 YYYY-MM-DD}"
fiscal_year: {tax_year}
---

# ふるさと納税管理の結果

## 登録済み寄附一覧

| 自治体名 | 都道府県 | 金額 | 寄附日 | ワンストップ |
|---------|---------|------|--------|------------|
| {自治体名} | {都道府県} | {金額}円 | {日付} | {申請済み/未申請} |

## 集計

- 寄附先自治体数: {件数}
- 寄附合計額: {合計金額}円
- 控除額（合計 - 2,000円）: {控除額}円

## 控除上限との比較

- 推定控除上限: {上限額}円（所得情報がある場合）
- 上限超過: {なし/あり（超過額: {金額}円）}

## 次のステップ

/income-tax で所得税の計算に進む
```

寄附がない場合（スキップ）は status を `skipped` とし、内容は「該当なし」と記載する。

### 進捗サマリーの更新

`.shinkoku/progress/progress-summary.md` を更新する（存在しない場合は新規作成）:

- YAML frontmatter: fiscal_year、last_updated（当日日付）、current_step: furusato
- テーブル: 全ステップの状態を更新（furusato を completed または skipped に）
- 次のステップの案内を記載

### 出力後の案内

ファイルを出力したらユーザーに以下を伝える:
- 「引継書を `.shinkoku/progress/` に保存しました。セッションが中断しても次のスキルで結果を引き継げます。」
- 次のステップの案内
