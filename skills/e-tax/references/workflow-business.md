# e-tax: 事業所得があり決算書を入力するとき

この資料は該当する作業でだけ参照します。節番号は元の手順を識別するためのものです。実行コマンドと `docs/`・`skills/`・設定/進捗パスはプロジェクトルート基準、本文中の `references/` はこのSkillの参照フォルダを指します。対象データが既に揃っていれば先行Skillや全手順をやり直しません。

## ステップ2: 青色申告決算書の入力（事業所得がある場合）

> ⚠️ **ネイティブダイアログ注意**: 「次へ」クリック後に画面が遷移しない場合、ネイティブダイアログ（alert/confirm）が表示されている可能性がある。技術的な知見の「ネイティブダイアログの検知と対処」を参照。

### /kessan/ac/pre/ac0300: 決算書の種類選択

ラジオボタン:
- **青色申告決算書** ← 青色申告の場合
- 収支内訳書（白色申告の場合）
- 青色申告決算書（現金主義用）

### /kessan/ac/aa0200: 損益計算書（P/L）の入力

URL: `https://www.keisan.nta.go.jp/kessan/ac/aa0200#bsctrl`

#### 期間の入力

| フィールド | name | デフォルト |
|-----------|------|-----------|
| 開始月 | `sonekiKeisansyoFromMonth` | 1 |
| 開始日 | `sonekiKeisansyoFromDay` | 1 |
| 終了月 | `sonekiKeisansyoToMonth` | 12 |
| 終了日 | `sonekiKeisansyoToDay` | 31 |

#### 売上（収入）金額

「入力」ボタン → `/kessan/ac/aa0201` 売上仕入月別入力サブページに遷移。

aa0201 のフィールド:
- `uriageKingaku1`〜`uriageKingaku12`: 月別売上
- `siireKingaku1`〜`siireKingaku12`: 月別仕入
- `kajisyohi`: 家事消費等
- `zatusyunyu`: 雑収入

合計: `uriageKingakuGokei`, `siireKingakuGokei`

#### 経費（行8〜31）

| 行 | 科目 | name（直接入力） | 備考 |
|----|------|-------------------|------|
| 8 | 租税公課 | `sozeiKoka` | |
| 9 | 荷造運賃 | `nidukuriUntin` | |
| 10 | 水道光熱費 | `suidoKonetuhi` | |
| 11 | 旅費交通費 | `ryohiKotuhi` | |
| 12 | 通信費 | `tusinhi` | |
| 13 | 広告宣伝費 | `kokokuSendenhi` | |
| 14 | 接待交際費 | `settaiKosaihi` | |
| 15 | 損害保険料 | `songaiHokenryo` | |
| 16 | 修繕費 | `syuzenhi` | |
| 17 | 消耗品費 | `syomohinhi` | |
| 18 | 減価償却費 | — | 「入力」→ `/kessan/ac/init/aa0203` |
| 19 | 福利厚生費 | `fukuriKoseihi` | |
| 20 | 給料賃金 | — | 「入力」→ `/kessan/ac/aa0205` |
| 21 | 外注工賃 | `gaichukotin` | |
| 22 | 利子割引料 | — | 「入力」→ `/kessan/ac/aa0206` |
| 23 | 地代家賃 | — | 「入力」→ `/kessan/ac/aa0207` |
| 24 | 貸倒金 | `kasidaorekin` | |
| 25 | 税理士等の報酬 | `keihiNiniKingaku1` | 科目名: `keihiNiniKamoku1` |
| 26 | 震災関連経費 | `keihiNiniKingaku2` | 科目名: `keihiNiniKamoku2` |
| 27-30 | 任意科目 | `keihiNiniKingaku3`〜`6` | 科目名: `keihiNiniKamoku3`〜`6` |
| 31 | 雑費 | `zappi` | |

集計 hidden フィールド: `keihiSannyugakuGokei`, `kyuryoTinginTotalGokei`, `risiWaribikiryoGokei`, `tidaiYatinGokei`

#### 繰戻額等

- `kurimodosiNiniKamoku1`/`kurimodosiNiniKingaku1`
- `kurimodosiNiniKamoku2`/`kurimodosiNiniKingaku2`

#### 専従者給与

- `senjusyaKyuyoTotalGokei` (hidden、「入力」ボタンで別画面)
- `kasidaoreKuriireGokei` (hidden)

#### 計算結果（自動）

- `disp_aoiroKojomaeSyotokuKingaku` = 売上 - 売上原価 - 経費 + 繰戻額 - 専従者給与等

### /kessan/ac/submit/aa0100: 青色申告特別控除

Q&A形式で控除額を選択:

| 選択肢 | value | 条件 |
|--------|-------|------|
| 10万円 | 2 | |
| 55万円 | 3 | |
| 65万円 | 1 | **e-Tax送信が必須**。書面提出ではエラー KS-E10089 |

フィールド: `aoiroTokubetuKojoSentakugaku`

65万円を選択する場合、電子帳簿保存または e-Tax 送信が条件。

> ⚠️ **ネイティブダイアログ注意**: 65万円を選択して次へ進むと、書面提出の場合は **KS-E10089**（e-Tax送信が必要）のネイティブダイアログが表示される。画面が遷移しない場合はダイアログの有無をユーザーに確認すること。

### 貸借対照表（B/S）の入力

URL: `/kessan/ac/preAoiroCalc`

#### 資産の部

配列形式: `sisannobuTaisyohyoDetailDataList[N].kisyuKingaku` / `.kimatuKingaku`

| index | 勘定科目 |
|-------|----------|
| 0 | 現金 |
| 1 | 当座預金 |
| 2 | 定期預金 |
| 3 | その他の預金 |
| 4 | 受取手形 |
| 5 | 売掛金 |
| 6 | 有価証券 |
| 7 | 棚卸資産 |
| 8 | 前払金 |
| 9 | 貸付金 |
| 10 | 建物 |
| 11 | 建物附属設備 |
| 12 | 機械装置 |
| 13 | 車両運搬具 |
| 14 | 工具器具備品 |
| 15 | 土地 |
| 16-23 | 任意科目 |

#### 負債・資本の部

配列形式: `fusainobuTaisyohyoDetailDataList[N].kisyuKingaku` / `.kimatuKingaku`

| index | 勘定科目 |
|-------|----------|
| 0 | 支払手形 |
| 1 | 買掛金 |
| 2 | 借入金 |
| 3 | 未払金 |
| 4 | 前受金 |
| 5 | 預り金 |
| 6 | 貸倒引当金 |
| 7-15 | 任意科目 |
| 16 | 元入金 |
| 17 | 事業主借 |
| 18 | 事業主貸 |
| 19 | 青色申告特別控除前の所得金額（P/Lから自動） |

**重要**: 資産期末合計 = 負債期末合計 が必須（KS-E40003）

> ⚠️ **ネイティブダイアログ注意**: 資産期末合計と負債期末合計が一致しない状態で「次へ」を押すと、**KS-E40003** のネイティブダイアログが表示される。画面が遷移しない場合はダイアログの有無をユーザーに確認すること。

### /kessan/ac/ac0500: 住所・氏名等の入力

| フィールド | name |
|-----------|------|
| 郵便番号 | `jitakuZip` |
| 都道府県 | `jitakuPrefectureId` |
| 市区町村以下 | `jitakuAddress` |
| 事業所住所（該当者） | `jimusyoAddress` |
| 提出先税務署 | `zeimusyoName` |
| 氏名漢字（姓） | `nameKanjiSei` |
| 氏名漢字（名） | `nameKanjiMei` |
| 業種名 | `gyosyuName` |
| 屋号 | `yago` |
| 提出年月日 | `teisyutuYear`/`teisyutuMonth`/`teisyutuDay` |

### 決算書完了 → 所得税コーナーへ

印刷・データ保存画面（`/kessan/ac/submit/ac0600`）の
「所得税の申告書作成はこちら」ボタンで所得税コーナーに遷移（住所氏名引継ぎ）。

> ⚠️ **ネイティブダイアログ注意**: このボタンをクリックすると **KS-W10035**（印刷を確認したか）のネイティブダイアログが表示される場合がある。画面が遷移しない場合はダイアログの有無をユーザーに確認し、「OK」をクリックするよう案内すること。

---
