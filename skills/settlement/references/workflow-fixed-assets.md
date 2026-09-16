# settlement: 固定資産台帳の登録と確認

固定資産の基本情報、供用開始日、期首累計、確認状態を年度ごとに保存する。現在の台帳CLIはCRUDだけに対応し、台帳の年次計算CLI、償却仕訳の確定・取消、翌期繰越は未実装である。確認済みの事実は単発CLIの年次文脈へ渡して詳細計算できる。台帳を保存しても取得仕訳・償却仕訳・PL・BSは変わらない。

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

返り値の`assets`、`count`、各資産の`missing_fields`と確認日時を確かめる。`state=legacy_unverified`の旧累計は`legacy_values.accumulated_depreciation`へ表示され、計算用の`accumulated_depreciation`はNULLになる。旧値を確認済みの当年末や期首額として流用しない。`calculation_available=false`は、現段階では台帳からの計算を提供していないことを示す。

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

現段階では、読戻した確認済みの諸元を[決算整理の手順](workflow-adjustments.md)の単発計算へ渡し、結果を確認する。台帳への登録を、仕訳登録への承認と扱わない。実帳簿への償却仕訳は対象内容のユーザー確認を経て別途登録する。同じ内容が承認済みなら再承認を求めない。

単発計算の結果は台帳へ自動保存されず、翌年の累計・残高も自動では引き継がれない。計算結果、登録した仕訳、期末残高を照合して引継ぎ資料に残し、未実装の繰越まで完了したとは記録しない。
