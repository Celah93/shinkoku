# settlement: 固定資産台帳の登録と確認

固定資産の基本情報、供用開始日、期首累計、確認状態を年度ごとに保存し、読取り専用の年次計算で転記項目と仕訳候補を確認する。償却仕訳の確定・取消、翌期繰越は未実装である。台帳の保存や候補の取得だけでは、取得仕訳・償却仕訳・PL・BSは変わらない。

既存DBの移行は `shinkoku ledger init --db-path DB_PATH --fiscal-year YEAR` の既存の初期化経路で行う。既存の帳簿を消したり、空のDBへ置き換えたりしない。旧台帳の値とIDを保ち、追加項目はNULLのままにする。登録や一覧コマンドはDBを勝手に新規作成・移行しない。

## 登録

同じ資産が登録済みかを一覧で確かめ、証憑と確認できた事実だけを登録する。取得日と供用開始日を同じ日と推測しない。未確認の割合や期首累計に100や0を入れない。以下は確認済みの架空PCの例であり、実データの既定値ではない。

```bash
shinkoku ledger fa-add --db-path DB_PATH --fiscal-year YEAR --input asset.json
```

```json
{
  "name": "検証用PC",
  "acquisition_date": "2026-04-01",
  "acquisition_cost": 250000,
  "placed_in_service_date": "2026-04-01",
  "useful_life": 4,
  "method": "straight_line",
  "business_use_ratio": 100,
  "quantity": "1",
  "quantity_unit": "台",
  "origin": "acquired_this_year",
  "asset_class": "tangible",
  "asset_account_code": "1130",
  "treatment": "normal_depreciation",
  "opening_accumulated_depreciation": 0,
  "book_basis": "full_cost_direct",
  "prior_private_use": false,
  "additional_depreciation_applicable": false,
  "basis_confirmed": true,
  "annual_facts_confirmed": true,
  "evidence_ref": "tests/fixtures/scenarios/taro/evidence.json#pc"
}
```

年分はフラグで指定し、JSONへ`fiscal_year`や`detail`のラッパーを加えない。`name`、`acquisition_date`、`acquisition_cost`は必須で、その他の入力事実は省略すると未確認のNULLになる。確認用のtrueは、該当する事実をユーザーと確認できた場合だけ渡す。

成功時の`asset.id`は年度行のID、`asset.asset_uid`は同じ現物を識別するIDである。登録するたびに新しいUIDを発行するため、再試行の前にも一覧を確認する。同名・同額だけで別資産を統合しない。

## 一覧と読戻し

次の例は登録結果の年度行IDが1の場合である。実際には返されたIDを使う。`--input`を省略すると、その年度の全件を返す。

```bash
shinkoku ledger fa-list --db-path DB_PATH --fiscal-year YEAR --input asset-filter.json
```

```json
{
  "asset_id": 1
}
```

返り値の`assets`、`count`、各資産の`missing_fields`と確認日時を確かめる。`state=legacy_unverified`の旧累計は`legacy_values.accumulated_depreciation`へ表示され、計算用の`accumulated_depreciation`はNULLになる。旧値を確認済みの当年末や期首額として流用しない。`calculation_available=true`は計算コマンドの提供を示す能力フラグであり、この行を計算できるかは下記の`calculation_status`で確認する。

## 年次の診断・転記項目・仕訳候補

登録済みの年度行IDを指定して、計算結果と候補を取得する。`--input`を省略するか空のオブジェクトを渡すと、その年度の全資産を診断する。次の例は登録結果のIDが1の場合である。

```bash
shinkoku ledger fa-depreciation --db-path DB_PATH --fiscal-year YEAR --input depreciation-assets.json
```

```json
{
  "asset_ids": [1]
}
```

`asset_ids`の空配列、null、重複、数値文字列は受け付けない。対象年度にないIDも行を省略せず、`blocked`として返す。年度自体が未作成、DBがない・未移行、入力形式が不正な場合はエラーとなる。

各行について次を確認する。

| calculation_status | 意味と確認事項 |
|---|---|
| `ready` | 段階2の共通関数で計算できた。`calculation`の内訳、`statement_fields`の転記項目、`journal_candidate`の候補を確認する |
| `no_depreciation` | 供用前や償却済み等で当年額が確認済み0となる。転記項目は返すが、0円の仕訳候補は作らない |
| `blocked` | 不足情報や対応範囲外等で計算できない。`missing_fields`、`error_code`、`blocking_reason`を確認する。計算額、転記項目、候補はNULLであり、0円とは異なる |

全件計算できた場合だけ`complete=true`と`total_expense`を返す。1行でもblockedなら`complete=false`・`total_expense=null`となり、計算できた行だけの小計を`calculable_subtotal`に返す。この小計を年度の経費合計として転記しない。対象0件ではcount=0・合計0となるので、台帳の漏れがないかも確かめる。明示したIDだけを選んだ場合の合計は、年度の全資産の合計ではない。

当面の計算範囲は、定額法・100％事業用・直接法の通常の有形資産である。確認日時・供用日・期首累計等が未確認、または転用・追加償却・対象外の方式等がある場合は止める。率・丸め・備忘価額は単発CLIと同じ共通関数で扱い、Skillで再計算しない。

候補は年末日付の借方5200／貸方の資産科目で、sourceはadjustment、税区分はout_of_scopeである。候補取得はDBへ書き込まない。`ready`は未計上の保証ではなく、既存の償却仕訳との照合が必要である。実帳簿への登録は別操作としてユーザー確認を経る。同じ候補を取得し直しても登録済みを示す状態にはならない。

## 更新

更新は省略した項目を維持し、明示したNULLだけを未確認へ戻す。名前・取得日・取得価額をNULLにすることはできない。UID、年度、前年行の参照、当年末累計は更新JSONで書き換えない。

```bash
shinkoku ledger fa-update --db-path DB_PATH --fiscal-year YEAR --asset-id 1 --input asset-update.json
```

```json
{
  "memo": "架空の証憑を再確認する",
  "annual_facts_confirmed": null
}
```

取得情報や割合等の事実を変更すると、明示的に再確認した場合を除き、以前の確認日時を消す。備考や証憑参照だけの更新では確認を維持する。旧行の初回更新時にはUIDを採番するが、そのことを税務上の確認と扱わない。

## 誤登録の削除

削除する年度行を一覧で特定し、ユーザーが依頼した誤登録を削除する。処分した資産を消すためのコマンドではない。後続年度の行から参照されている場合は、先に後続を整理する必要がある。

```bash
shinkoku ledger fa-delete --db-path DB_PATH --fiscal-year YEAR --input asset-delete.json
```

```json
{
  "asset_id": 1
}
```

## 償却と帳簿への引継ぎ

台帳がある場合は上記の候補取得を使う。単発計算で確認する場合は、読戻した確認済みの諸元を[決算整理の手順](workflow-adjustments.md)へ渡す。台帳の保存や候補取得を、仕訳登録への承認と扱わない。実帳簿への償却仕訳は対象内容のユーザー確認を経て別途登録する。同じ内容が承認済みなら再承認を求めない。

単発計算の結果は台帳へ自動保存されず、翌年の累計・残高も自動では引き継がれない。計算結果、登録した仕訳、期末残高を照合して引継ぎ資料に残し、未実装の繰越まで完了したとは記録しない。
