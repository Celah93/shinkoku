---
name: tax-housing-loan-context
description: 入居年別の住宅ローン控除の適用要件・計算と他控除との関係を調べる参照入口。
user-invocable: false
---

# 住宅ローン控除コンテキスト（Housing Loan Tax Credit Context）

このスキルは住宅ローン控除（租税特別措置法第41条）に関する判定・計算コンテキストを提供する。

## 住宅ローン控除の情報提供

住宅ローン控除に関する回答を行う際は、`references/housing-loan.md` を読み込んで以下を実行する:

1. 適用要件（住宅・所得・ローン要件）を確認し、ユーザーへの判定フローに沿って案内する
2. 入居年に一致する借入限度額・控除率・控除期間を提示する。令和9年以降の入居は
   実装範囲外として計算を止める
3. 取得区分は`new_custom`、`new_subdivision`、`broker_renovated_resale`、`used`、
   `renovation`から選ぶ。旧`resale`は通常中古か買取再販かを確認して移行し、推測しない
4. 特例対象個人を判定するため、本人・配偶者・扶養親族の生年月日を入居年末基準で集める。
   計算JSONには`taxpayer_birth_date`、`spouse_birth_date`、`spouse_income`、`dependents`を渡す
5. 確認済みの特例判定を明示するときは`is_special_target_individual`を使う。旧
   `is_childcare_household`は新規入力に使わない。情報不足で判定できないときは止めて確認する
6. ふるさと納税との相互影響を説明する（必要な場合）
7. 重複適用（中古購入＋リフォーム同時）の計算が必要な場合は按分計算を行う
8. `housing_loan_credit_entries`の入居年、申告年分、適用年数、控除期間、状態を確認する。
   `expired`は期間終了、`ineligible`は当該ルールで対象外を表す
9. 一般新築の経過措置警告が出たら、令和6年6月30日までの建築日経路と床面積経路が
   未判定であることを伝え、証拠書類を手作業で確認する。警告を「非該当」と読み替えない

## 参照ファイル

| ファイル | 内容 |
|---------|------|
| `references/housing-loan.md` | 控除額・借入限度額テーブル・適用要件・判定フロー・重複適用の計算例 |
