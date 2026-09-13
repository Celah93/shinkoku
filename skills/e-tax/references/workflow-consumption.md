# e-tax: 消費税申告が必要で該当方式を入力するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ4: 消費税の申告書入力（該当者のみ）

> ⚠️ **ネイティブダイアログ注意**: 「次へ」クリック後に画面が遷移しない場合、ネイティブダイアログ（alert/confirm）が表示されている可能性がある。技術的な知見の「ネイティブダイアログの検知と対処」を参照。

所得税申告書の完了後、「他の申告書等を作成する」→ `doSubmitCSW0900(3,'25')` で消費税コーナーに遷移。

### ac0100: 条件判定等

URL: `https://www.keisan.nta.go.jp/syouhi/ac0100/submit.htmj#bsctrl`

| フィールド | name | 備考 |
|-----------|------|------|
| 基準期間の課税売上高 | `kijunKazeiUriage` | R5年分 |
| インボイス発行事業者 | `invoice` | true/false |
| 簡易課税制度選択 | `kani` | true/false |
| 経理方式 | `zeikomi` | 税込/税抜 |

#### インボイス=はい の場合に追加表示

| フィールド | name | 備考 |
|-----------|------|------|
| 新たに課税事業者か | `newKazeiJigyosya` | true/false |
| 2割特例を適用するか | `niwariTokurei` | true/false |

#### 一般課税の場合に追加表示

| フィールド | name | 備考 |
|-----------|------|------|
| 仕入税額の計算方法 | `siireKeisanHouhou` | warimodosi/tumiage |

#### 条件判定画面の表示ロジック（基準期間による分岐）

`kijunKazeiUriage`（基準期間の課税売上高）の値によって表示される選択肢が変化する:

| 条件 | 新規課税事業者? | 2割特例? | 簡易課税? |
|------|---------------|---------|---------|
| 基準期間=0, invoice=はい | 表示 | 表示 | 非表示 |
| 基準期間=3,000,000, invoice=はい | 表示 | 表示 | 表示 |
| 基準期間=60,000,000, invoice=はい | 非表示 | 非表示 | 表示 |

**一般課税のみ**: 「税額の計算方法として積上げ計算を選択する方」ボタン（折りたたみセクション内）

#### 分岐ロジック

| 条件 | 遷移先ルート |
|------|-------------|
| インボイス=はい & 2割特例=はい | **2割特例** |
| 簡易課税=はい | **簡易課税** |
| 上記以外 | **一般課税** |

### ac0250: 所得区分の選択

URL: `https://www.keisan.nta.go.jp/syouhi/ac0250/submit.htmj#bsctrl`

該当する所得区分を全て選択する。ヘッダに課税方式（一般課税/簡易課税）と経理方式（税込/税抜）が表示される。

| ラベル | name | 備考 |
|--------|------|------|
| 事業所得（営業等） | `jigyoSyotokuEigyo` | メインターゲット |
| 事業所得（農業） | `jigyoSyotokuNogyo` | |
| 不動産所得 | `fudosanSyotoku` | |
| 雑所得（原稿料等） | `zatuSyotoku` | |
| 業務用固定資産等の譲渡所得 | `jotoSyotoku` | 一般課税のみ表示 |

#### 簡易課税のみ: 事業区分の選択

簡易課税の場合、各所得区分に対して事業区分（第1種〜第6種）のサブ選択がある:

| フィールド | name | 備考 |
|-----------|------|------|
| 事業区分（第1種） | `jigyoSyotokuEigyoJigyoKubun1` | 卸売業 |
| 事業区分（第2種） | `jigyoSyotokuEigyoJigyoKubun2` | 小売業 |
| 事業区分（第3種） | `jigyoSyotokuEigyoJigyoKubun3` | 製造業等 |
| 事業区分（第4種） | `jigyoSyotokuEigyoJigyoKubun4` | その他 |
| 事業区分（第5種） | `jigyoSyotokuEigyoJigyoKubun5` | サービス業等 |
| 事業区分（第6種） | `jigyoSyotokuEigyoJigyoKubun6` | 不動産業 |

#### 一般課税のみ: 業務用固定資産等

| フィールド | name | 備考 |
|-----------|------|------|
| 業務用固定資産等の購入がある | `gyomuyosisanKonyu` | checkbox |

### 売上入力（全ルート共通フォーム）

URL パターン:
- 2割特例: `/syouhi/at3600/inputEigyo.htmj`
- 簡易課税: `/syouhi/ak3600/inputEigyo.htmj`
- 一般課税: `/syouhi/ai3600/inputEigyo.htmj`

| フィールド | name | 備考 |
|-----------|------|------|
| 売上（収入）金額 | `uriageWari` | 必須。税込総額 |
| 免税売上 | `menzeiUriageWari` | |
| 非課税売上 | `hikazeiUriageWari` | |
| 不課税取引 | `jigyoFukazeiUriageWari` | |
| 軽減税率（6.24%）適用分 | `kazeiUriage624PercentWari` | |
| 返還等対価（軽減） | `uriageTaikaKeigen.uriageTaika624Percent` | |
| 返還等対価（標準） | `uriageTaikaKeigen.uriageTaika78Percent` | |
| 貸倒れ発生（軽減） | `kasidaoreKeigen.occurredKasidaore624Percent` | 2割特例・簡易課税のみ |
| 貸倒れ発生（標準） | `kasidaoreKeigen.occurredKasidaore78Percent` | 2割特例・簡易課税のみ |
| 貸倒れ回収（軽減） | `kasidaoreKeigen.recoveredKasidaore624Percent` | 2割特例・簡易課税のみ |
| 貸倒れ回収（標準） | `kasidaoreKeigen.recoveredKasidaore78Percent` | 2割特例・簡易課税のみ |
| 貸倒れ発生有無 | `kasidaore.occurredKasidaoreAns` | 2割特例・簡易課税のみ (radio) |

#### 一般課税のみの追加フィールド

| フィールド | name | 備考 |
|-----------|------|------|
| 非課税返還 | `uriageTaikaKeigen.hikazeiHenkan` | |
| 非課税資産の輸出等返還 | `uriageTaikaKeigen.hikazeiSisanHenkan` | |

### 中間納付税額等の入力（全ルート共通）

| name | 備考 |
|------|------|
| `chukanNofuZei` | 中間納付消費税額 |
| `chukanNofuJotoWari` | 中間納付譲渡割額 |

### 一般課税（積上げ計算）専用: 決算額テーブル

URL: `/syouhi/ai3610/submit.htmj`

積上げ計算選択時のみ表示される大規模フォーム（194項目）。
青色申告決算書の各勘定科目に対して、決算額・課税取引金額・軽減税率分・免税事業者等取引分を入力。

フィールド名パターン: `{科目略称}{列略称}Wari` (割戻し) / `{科目略称}{列略称}Tumi` (積上げ)

列略称: `Kessan`(決算額), `KazeiIgai`(課税取引にならないもの), `Keigen624`(軽減税率分), `MenzeiKeigen`(免税事業者等/軽減), `Menzei`(免税事業者等/標準)

| 科目 | プレフィックス |
|------|---------------|
| 仕入金額 | `siire` |
| 租税公課 | `sozeiKoka` |
| 荷造運賃 | `nidukuri` |
| 水道光熱費 | `suido` |
| 旅費交通費 | `ryohi` |
| 通信費 | `tusin` |
| 広告宣伝費 | `kokoku` |
| 接待交際費 | `settai` |
| 損害保険料 | `songai` |
| 修繕費 | `syuzen` |
| 消耗品費 | `syomohin` |
| 減価償却費 | `genkasyokyaku` |
| 福利厚生費 | `fukurikosei` |
| 給料賃金 | `kyuryo` |
| 外注工賃 | `gaichu` |
| 利子割引料 | `risiWaribiki` |
| 地代家賃 | `jidai` |
| 貸倒金 | `kasidaore` |
| 任意科目 | `niniKamoku25`〜`30` |
| 雑費 | `zappi` |

#### テーブル下の Yes/No 質問（一般課税のみ）

| フィールド | name | 内容 |
|-----------|------|------|
| 発生した貸倒金 | `kasidaoreKeigen.occurredKasidaoreAns` | radio |
| 回収した貸倒金 | `kasidaoreKeigen.recoveredKasidaoreAns` | radio |
| 保税地域からの引取貨物 | `hozeiKeigenIppan.hozeiAns` | radio |
| 課税仕入れに係る対価の返還等 | `siireTaikaKeigenIppan.siireTaikaAns` | radio |
| 課税事業者になった方の棚卸高調整 | `tanaorosiKeigenIppan.oldMenzeiJigyoshaAns` | radio |
| 免税事業者になる方の棚卸高調整 | `tanaorosiKeigenIppan.newMenzeiJigyoshaAns` | radio |

### 簡易課税のみ: 仕入税額控除の控除方式の選択

URL: `/syouhi/ak2140/submit.htmj`

2種以上の事業を営む場合に表示される。以下から選択:
- 原則計算
- 特例計算（2種特例/3種特例/75%特例）

### ac0300: 消費税計算結果の確認

全ルート共通の結果画面。ヘッダ部で「2割特例」「簡易課税」「一般課税」を表示。

表示項目:
- 課税標準額
- 消費税額
- 控除税額小計
- **差引税額**（100円未満切捨て）
- 中間納付税額
- 納付税額
- **地方消費税 譲渡割額**（納税額 = 差引税額 × 22/78、100円未満切捨て）
- **地方消費税 還付譲渡割額**（控除不足還付税額 × 22/78、1円未満切捨て）
  - 還付額には100円未満切捨てを適用しない
- 中間納付譲渡割額
- **合計納付税額**

#### 一般課税のみの追加表示項目

- 「控除過大調整税額」
- 「課税売上割合」セクション（課税資産の譲渡等の対価の額 / 資産の譲渡等の対価の額）

### 消費税 納税地等の入力

URL パターン（ルートごとに異なる）:
- 2割特例: `/syouhi/at1400/submit.htmj`
- 簡易課税: `/syouhi/ak1400/submit.htmj`
- 一般課税: `/syouhi/ai1400/submit.htmj`

画面は全ルートで同一構造（pageId=ac0400）。

| フィールド | name | type | 備考 |
|-----------|------|------|------|
| 納付方法 | `nofuHohoType` | select | |
| 納税地区分 | `nozeitiKubun` | radio | |
| 郵便番号1 | `nozeitiZipCode1` | text | |
| 郵便番号2 | `nozeitiZipCode2` | text | |
| 都道府県 | `nozeitiPrefectureCode` | select | **住所用コード: 13=東京都** |
| 市区町村 | `municipalityCode` | select | |
| 丁目番地等 | `nozeiti1ElaseMunicipal` | text | |
| 税務署都道府県 | `prefectureCode` | select | **税務署用コード: 15=東京都** ← 住所と異なるコード体系! |
| 税務署 | `sinkokuZeimusyoCode` | select | |
| 氏名カナ（姓） | `simeiKanaSei` | text | |
| 氏名カナ（名） | `simeiKanaMei` | text | |
| 氏名漢字（姓） | `simeiKanjiSei` | text | |
| 氏名漢字（名） | `simeiKanjiMei` | text | |
| マイナンバー1 | `myNumber1` | password | |
| マイナンバー2 | `myNumber2` | password | |
| マイナンバー3 | `myNumber3` | password | |
| 電話番号1 | `telNumber1` | text | |
| 電話番号2 | `telNumber2` | text | |
| 電話番号3 | `telNumber3` | text | |

**⚠️ 注意**: 住所の都道府県コード（`nozeitiPrefectureCode`: 13=東京都）と税務署の都道府県コード（`prefectureCode`: 15=東京都）で**異なるコード体系**が使用されている。

### 消費税 計算結果のテストデータ

> 2割特例欄の「×80%」は売上税額からみなし控除する計算であり、免税事業者等からの仕入れに係る経過措置の80%控除とは別制度。

| 項目 | 2割特例 (売上5M) | 簡易課税 第5種 (売上5M) | 一般課税 (売上66M, 仕入0) |
|-----|----------------|----------------------|------------------------|
| 課税標準額 | 4,545,000円 | 4,545,000円 | 60,000,000円 |
| 消費税額 | 354,510円 | 354,510円 | 4,680,000円 |
| 控除税額 | 283,608円 (×80%) | 177,255円 (×50%) | 0円 |
| 差引税額 | 70,900円 | 177,200円 | 4,680,000円 |
| 地方消費税譲渡割額 | 19,900円 | 49,900円 | 1,320,000円 |
| **合計納付** | **90,800円** | **227,100円** | **6,000,000円** |

### 3ルートの計算方式の違い

| 項目 | 2割特例 | 簡易課税 | 一般課税 |
|------|---------|----------|----------|
| 控除税額 | 消費税額×80% | みなし仕入率 | 実額（割戻し or 積上げ） |
| 仕入入力 | 不要 | 不要 | 割戻し: 不要 / 積上げ: 決算額テーブル |
| URL prefix | /at**** | /ak**** | /ai**** |

> ⚠️ **ネイティブダイアログ注意**: 消費税コーナー終了時は **2段階のネイティブダイアログ**が表示される — `#otherTax`（他の申告書等を作成しますか？）と `#end`（終了してもよろしいですか？）。画面が遷移しない場合はダイアログの有無をユーザーに確認し、それぞれ適切にクリックするよう案内すること。

---
