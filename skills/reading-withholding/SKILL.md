---
name: reading-withholding
description: 源泉徴収票を読み取り、給与・控除・源泉徴収額を構造化して返す。
---

# reading-withholding

源泉徴収票を読み取り、給与・控除・源泉徴収額を構造化して返す。

[共通の読取・不明値・確認方法](../_shared/ocr.md) に従います。PDFを変換する場合だけ以下を参照します。

## PDF ファイルの場合

ファイルが PDF（`.pdf`）の場合、画像 OCR の前にテキスト抽出を試みる。

1. `shinkoku pdf extract-text --file-path <path>` を実行する
2. 抽出テキストに必要な情報（支払金額・源泉徴収税額等）が含まれていれば、テキストから構造化データを生成する
3. テキストが不十分（スキャン PDF 等）の場合は `shinkoku pdf to-image --file-path <path> --output-dir <dir>` で PNG に変換し、以下の画像読み取りフローに進む


## 基本ルール

- 利用可能な画像読取ツールで原本を確認する
- 金額は必ず int（円単位の整数）で返す。カンマや「円」は除去する
- 日付は YYYY-MM-DD 形式で返す
- 和暦は西暦に変換する（令和7年 → 2025、令和6年 → 2024、平成31年 → 2019）
- 読み取れないフィールドは UNKNOWN（文字列）または 0（金額）とする
- 指定された全ファイルの結果を元ファイルに対応付けて返す


## 出力フォーマット

画像を読み取り、以下の形式で返す:

```
---WITHHOLDING_DATA---
payer_name: 支払者名
payment_amount: 支払金額（int）
withheld_tax: 源泉徴収税額（int）
social_insurance: 社会保険料等の金額（int）
life_insurance_deduction: 生命保険料の控除額（int）
earthquake_insurance_deduction: 地震保険料の控除額（int）
housing_loan_deduction: 住宅借入金等特別控除の額（int）
life_insurance_detail:
  general_new: 一般の新保険料（int）
  general_old: 一般の旧保険料（int）
  medical_care: 介護医療保険料（int）
  annuity_new: 個人年金の新保険料（int）
  annuity_old: 個人年金の旧保険料（int）
---END---
```


## 抽出のポイント

- 「支払金額」欄（給与収入の総額）を最優先で抽出する
- 「源泉徴収税額」欄を正確に読み取る
- 「社会保険料等の金額」欄を読み取る
- 生命保険料控除は新旧制度・3区分（一般/介護医療/個人年金）の内訳を確認する
- 地震保険料控除・住宅ローン控除は記載がある場合のみ抽出する
- 支払者の名称（会社名）を抽出する
- 記載がない項目は 0 とする
