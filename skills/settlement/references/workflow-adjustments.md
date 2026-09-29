# settlement: 減価償却・棚卸・未払等の決算整理候補を作るとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ2: 決算整理仕訳の登録

以下の決算整理項目を順に確認・処理する。各仕訳は `shinkoku ledger journal-add --db-path DB_PATH --fiscal-year YEAR --input journal.json` で登録する。

### 2-1. 減価償却費の計上

固定資産（1100〜1160）に残高がある場合、減価償却費を計上する。

諸元は[固定資産台帳の手順](workflow-fixed-assets.md)で保存・読戻しする。
台帳からは読取り専用の`fa-depreciation`で計算・転記項目・仕訳候補を取得できる。
blockedがあれば年度の合計は未確定であり、小計を合計として扱わない。
以下の単発・詳細計算と、確認後の償却仕訳登録はそれぞれ別操作である。
台帳に登録しただけで当年末累計や翌年の残高が更新されたとは扱わない。

**計算ツールの呼び出し:**

```bash
shinkoku tax calc-depreciation --input depreciation_input.json
```

定額法の場合:
```json
{
  "method": "straight_line",
  "acquisition_cost": 300000,
  "useful_life": 4,
  "business_use_ratio": 100,
  "months": 12
}
```

定率法の場合:
```json
{
  "method": "declining_balance",
  "acquisition_cost": 300000,
  "book_value": 200000,
  "useful_life": 4,
  "declining_rate": 500,
  "business_use_ratio": 100,
  "months": 12
}
```

**詳細と年次の残高を確認する場合:**

```bash
shinkoku tax calc-depreciation --details --input depreciation_annual.json
```

```json
{
  "method": "straight_line",
  "acquisition_cost": 250000,
  "useful_life": 4,
  "business_use_ratio": 100,
  "annual_context": {
    "fiscal_year": 2026,
    "acquisition_date": "2026-04-01",
    "placed_in_service_date": "2026-04-01",
    "opening_accumulated_depreciation": 0,
    "asset_class": "tangible",
    "book_basis": "full_cost_direct",
    "prior_private_use": false,
    "additional_depreciation_applicable": false,
    "basis_confirmed": true,
    "annual_facts_confirmed": true
  }
}
```

これは確認済みの架空PCの例である。確認していない事実をtrue・false・0へ置き換えない。
年次文脈は定額法・100％事業用・直接法の通常の有形資産（坑道を除く）だけを対象とする。
`annual_facts_confirmed`は当年の使用状況と処分がないことの確認も含む。
月数は供用日と年分から求める。`months`を明示した場合は計算した月数との不一致を拒否する。
年次文脈があれば、確認済みの期首簿価に基づいて備忘価額1円を残す終端処理を行う。
`ordinary_amount`と`expense_amount`、期首・期末簿価、制約の適用有無を確認する。

`--details`だけで`annual_context`がない場合、従来の単発算式の内訳を返し、年末簿価はNULLにする。
定率法の単発詳細は既存の一段階の切捨てを維持し、保証・改定を含む年次の計算には対応しない。
少額資産の処理選択で`--details`を指定すると、従来の選択結果と候補ごとの計算内訳を分けて返す。
いずれの計算もDBへ保存せず、仕訳や翌年度の台帳を自動登録しない。

**仕訳の登録:**
```
借方: 減価償却費(5200) / 貸方: 該当の固定資産科目
金額: 計算された償却額
```

- 耐用年数は references/depreciation-rules.md を参照する
- 事業供用開始日が期中の場合は月割り計算を行う
- 一括償却資産（1160）の当年額は`method: "small_asset_treatment"`で取得原価の1/3を計算できる
- 1160の選択保存、翌年以後の残額管理、自動仕訳は未実装のため、結果を確認して手動で記帳する
- 家事按分がある場合は事業使用割合を乗じた金額のみ計上する

### 2-2. 棚卸資産の評価

期末に在庫がある場合、棚卸高を計上する。

#### 在庫データの登録

まず `shinkoku ledger inv-list --db-path DB_PATH --fiscal-year YEAR` で登録済みの棚卸データを確認する。
未登録の場合は `shinkoku ledger inv-set --db-path DB_PATH --fiscal-year YEAR --input inventory.json` で期首・期末の棚卸高を登録する:

```json
{
  "period": "ending",
  "amount": 200000,
  "method": "cost",
  "details": "品目の明細等"
}
```
年分は `--fiscal-year` で指定する。JSONには `fiscal_year` や `detail` のラッパーを付けない。

#### 棚卸仕訳の登録

`inv-set` は棚卸明細を `inventory_records` へ保存する操作であり、仕訳を自動作成しない。
PLは仕訳を集計するため、期首残高と既存の振替仕訳を確認し、必要な次の仕訳を別途登録して初めて棚卸が反映される。
すでに登録されている振替は重複させず、棚卸額が0円ならその仕訳は作成しない。

```
当期の期首棚卸の振替:
借方: 仕入(5001) / 貸方: 棚卸資産(1030)  金額: 当期の期首棚卸高

期末棚卸仕訳:
借方: 棚卸資産(1030) / 貸方: 仕入(5001)  金額: 期末棚卸高
```

- 期末の在庫数量と単価をユーザーに確認する
- 評価方法（最終仕入原価法等）を確認する
- **売上原価の計算**: 期首棚卸高 + 仕入高 - 期末棚卸高
- 仕訳登録後、`shinkoku ledger pl --db-path DB_PATH --fiscal-year YEAR` の仕入勘定が上の売上原価と一致し、BSの棚卸資産が期末棚卸高と一致することを確認する。例えば期首0円・仕入240,000円・期末100,000円なら、期末仕訳後の売上原価は140,000円になる。
- 現在の `pdf` CLIは既存PDFのテキスト抽出・画像変換だけで、`inventory_records` を読む決算書PDF生成機能はない。棚卸明細からPDFへの自動反映も行われない。作成コーナーで決算書を作る際には、明細と照合済みのPL・BSを入力し、出力した決算書と照合する。

### 2-3. 未払費用の計上

年度末時点で発生しているが未払いの費用を計上する。

```
借方: 該当の費用科目 / 貸方: 未払費用(2031)
```

- 12月分の家賃（翌月払いの場合）
- 12月分の通信費・光熱費
- 社会保険料の未払い分

### 2-4. 前払費用の計上

翌期分を当期に支払い済みの場合、前払費用に振り替える。

```
借方: 前払費用(1041) / 貸方: 該当の費用科目
```

- 年払いの保険料のうち翌期対応分
- 年払いのサブスクリプション料金のうち翌期対応分

### 2-5. 売掛金・買掛金の確認

- 売掛金（1010）残高と未回収の請求書一覧が一致するか確認する
- 買掛金（2001）残高と未払いの仕入先一覧が一致するか確認する
- 回収不能な売掛金がある場合は貸倒金（5260）への振替を検討する

### 2-6. 事業主勘定の確認

- 事業主貸（1200）: 事業資金から個人利用分の合計
- 事業主借（3010）: 個人資金から事業利用分の合計
- これらは決算で相殺しない（翌期首に元入金で繰越処理する）


## ステップ2.7: 地代家賃の内訳登録

事業で地代家賃を計上している場合、内訳を登録する（青色申告決算書の添付資料）。

### `shinkoku ledger rd-add --db-path DB_PATH --fiscal-year YEAR --input rent.json` の呼び出し

```bash
shinkoku ledger rd-add --db-path DB_PATH --fiscal-year YEAR --input rent.json
```
入力 JSON:
```json
{
  "property_type": "自宅兼事務所",
  "usage": "自宅兼事務所",
  "landlord_name": "賃貸先の名称",
  "landlord_address": "賃貸先の住所",
  "monthly_rent": 100000,
  "annual_rent": 1200000,
  "deposit": 0,
  "business_ratio": 50
}
```
年分は `--fiscal-year` で指定する。JSONには `fiscal_year` や `detail` のラッパーを付けない。

**確認項目:**

- 自宅兼事務所の場合、事業割合が適切に設定されているか
- 年間賃料 = 月額賃料 × 支払月数 で正しいか
- 複数の物件がある場合はすべて登録する
