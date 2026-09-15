# income-tax: 源泉徴収票を読み取り、控除内訳を検算するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ1: 源泉徴収票の取り込み

給与所得がある場合、源泉徴収票からデータを取り込む。

### `shinkoku import withholding --file-path withholding.pdf` の呼び出し

```bash
shinkoku import withholding --file-path withholding.pdf
```
入力 JSON:
```json
{
  "file_path": "path/to/withholding_slip.pdf"
}
```
出力:
```json
{
  "payer_name": "支払者名",
  "payment_amount": 5000000,
  "deduction_amount": 3560000,
  "income_tax_withheld": 100000,
  "social_insurance": 700000,
  "life_insurance": 50000,
  "spouse_deduction": 0
}
```

#### 画像ファイルの場合: OCR 読み取り

`extracted_text` が空の場合（画像ファイルまたはスキャン PDF）、画像の読み取りは `/reading-withholding` スキルを使用する。
   読み取り方・照合・不明箇所の扱いは該当する reading-* Skill に従います。実データへの登録前に確認する内容をまとめます。

**取り込み後の検算（必須）:**

OCR 結果の整合性を検証するため、「所得控除の額の合計額」と各内訳の合計を照合する:

```
検算: 所得控除の額の合計額 ≟ 社会保険料等の金額          ← 小規模企業共済等掛金を含む（内数）
                            + 生命保険料の控除額
                            + 地震保険料の控除額
                            + 配偶者（特別）控除の額
                            + 扶養控除額                ← 人数×単価から算出（特定63万/老人48万or58万/その他38万）
                            + 障害者控除                ← 人数×単価から算出（一般27万/特別40万/同居特別75万）
                            + 寡婦控除（27万）またはひとり親控除（35万） ← 該当時
                            + 勤労学生控除（27万）       ← 該当時
                            + 基礎控除の額              ← 源泉徴収票の記載額を使用。未記載なら所得と年度から算出
```

注意:
- 「（うち小規模企業共済等掛金の額）」は社会保険料等の金額の**内数**。別途加算すると二重計上になる
- 扶養控除・障害者控除は金額欄ではなく人数欄で記載されるため、人数×単価で算出する
- 基礎控除の額は源泉徴収票に記載があればその値を使う。未記載の場合は合計所得と年度に応じて算出する（令和7・8年は特例加算あり、令和9年以降は一律58万）

- **一致の場合:** 各フィールドの OCR 精度が確認できたものとして採用する
- **不一致の場合:** 差額を明示し、どのフィールドが誤読の可能性があるかユーザーに提示する。元画像と突き合わせて修正する

**その他の確認事項:**

1. 複数の勤務先がある場合は各社分を取り込む
2. 年末調整済みの控除を確認し、追加控除の有無を判定する

### 確認済みの源泉徴収票をDBへ保存する

確認した内容を `shinkoku ledger ws-save --db-path DB_PATH --fiscal-year YEAR --input salary.json` で保存し、`ws-list`で読戻す。
以下は2026年分の架空の1枚の例であり、給与収入や控除・源泉税は実際に確認した票の値で置き換える。

```json
{
  "payer_name": "架空勤務先",
  "payment_amount": 6000000,
  "withheld_tax": 107700,
  "social_insurance": 900000,
  "spouse_deduction": 380000,
  "dependent_deduction": 380000,
  "basic_deduction": 670000,
  "housing_loan_deduction": 0
}
```

`payer_name` は給与を支払った勤務先である。`pf-add`の同名フィールドとは対象が異なる。
年分は `--fiscal-year` で指定し、`fiscal_year`・`detail`のラッパーは付けない。
`payment_amount` は `calc-income` の `salary_income`、給与の `withheld_tax` は同じく `withheld_tax` へ渡す。
給与の源泉を事業源泉へ混ぜず、年末調整済みの控除と追加控除を二重に加算しない。
