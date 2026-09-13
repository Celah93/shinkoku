# income-tax: 所得控除を集計するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ2: 所得控除の計算

### `shinkoku tax calc-deductions --input deductions_input.json` の呼び出し

```bash
shinkoku tax calc-deductions --input deductions_input.json
```
入力 JSON:
```json
{
  "total_income": 5000000,
  "social_insurance": 700000,
  "life_insurance_premium": 80000,
  "earthquake_insurance_premium": 30000,
  "medical_expenses": 200000,
  "furusato_nozei": 50000,
  "housing_loan_balance": 0,
  "taxpayer_birth_date": null,
  "spouse_income": null,
  "spouse_birth_date": null,
  "ideco_contribution": 276000,
  "dependents": [],
  "fiscal_year": 2025,
  "housing_loan_detail": null,
  "donations": null
}
```
出力 (DeductionsResult):
- `income_deductions`: 所得控除の一覧（basic_deduction, social_insurance_deduction, life_insurance_deduction, earthquake_insurance_deduction, ideco_deduction, medical_deduction, furusato_deduction, donation_deduction, spouse_deduction, dependent_deduction, disability_deduction）
- `tax_credits`: 税額控除の一覧（housing_loan_credit, public_interest_donation, npo_donation, political_donation 等）
- `total_income_deductions`: 所得控除合計
- `total_tax_credits`: 税額控除合計
- `housing_loan_credit_entries`: 入居年、申告年分、適用年数、控除期間、限度額、控除額、状態
- `warnings`: 一般新築の未対応経過措置や残高だけの旧入力経路など、確認が必要な事項

**各控除の確認事項:**

- 基礎控除: 合計所得金額に応じた段階的控除（令和7年分の改正を反映、132万以下=95万）
- 社会保険料控除: 国民年金・国民健康保険・その他の年間支払額
- 生命保険料控除: 新旧制度 × 3区分（一般/介護医療/個人年金）で計算する
  - `life_insurance_detail` パラメータで5区分の保険料を指定:
    - `general_new`: 一般（新制度）、`general_old`: 一般（旧制度）
    - `medical_care`: 介護医療（新制度のみ）
    - `annuity_new`: 個人年金（新制度）、`annuity_old`: 個人年金（旧制度）
  - 通常の各区分上限: 新制度 40,000円 / 旧制度 50,000円 / 合算上限 40,000円
  - 令和8・9年分は、所得要件を満たす23歳未満の扶養親族がいる場合、一般生命保険料の
    新契約だけ次の特例表で計算する

    | 年間の新生命保険料 | 控除額 |
    |---:|---:|
    | 30,000円以下 | 支払額全額 |
    | 30,000円超60,000円以下 | 支払額 × 1/2 + 15,000円 |
    | 60,000円超120,000円以下 | 支払額 × 1/4 + 30,000円 |
    | 120,000円超 | 60,000円 |

  - 特例時の一般生命保険料は、新契約と旧契約を合わせて60,000円が上限
  - 対象親族には16歳未満を含む。他の納税者が扶養控除を取る親族も、
    `other_taxpayer_dependent: true` で登録されていれば特例判定に含める
  - 配偶者と青色・白色事業専従者は対象外。事業専従者は扶養親族リストへ登録しない
  - 介護医療保険料と個人年金保険料の計算表・上限は変わらない
  - 3区分合計の上限: 120,000円
  - 源泉徴収票に生命保険料5区分の記載がある場合はそのまま使用する
- 地震保険料控除: 地震保険（上限5万円）+ 旧長期損害保険（上限1.5万円）、合算上限5万円
  - `old_long_term_insurance_premium` パラメータで旧長期損害保険料を指定可能
- 小規模企業共済等掛金控除: 3サブタイプ個別追跡
  - iDeCo（個人型確定拠出年金）
  - 小規模企業共済
  - 心身障害者扶養共済
  - `small_business_mutual_aid` パラメータで小規模企業共済掛金を指定
- 医療費控除: 支払額から保険金等の補填額を差し引き、10万円（または所得の5%）を超える部分
  - **セルフメディケーション税制との選択適用**: OTC医薬品の購入額 - 12,000円（上限 88,000円）
  - 医療費控除とセルフメディケーションは併用不可。有利な方を選択する
- 配偶者控除/特別控除: 配偶者の所得に応じて段階的に控除額が変動
- 扶養控除: 年齢区分に応じた控除額（一般38万/特定63万/老人48万or58万）
- 障害者控除: 障害の程度に応じた控除額
- **人的控除**（config の納税者情報から自動判定）:
  - 寡婦控除: 27万円（所得500万以下）
  - ひとり親控除: 35万円（所得500万以下）
  - 障害者控除（本人）: 一般 27万円 / 特別 40万円
  - 勤労学生控除: 27万円（所得75万以下）
- ふるさと納税: 寄附金 − 2,000円（確定申告ではワンストップ特例分も含める）
- 住宅ローン控除: 住宅区分別の年末残高上限と控除率0.7%（令和4年以降入居）
