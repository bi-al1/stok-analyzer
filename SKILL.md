---
name: stok-analyzer
description: >
  KabuMartのスクリーンショットから銘柄を分析し、分析JSONを生成するスキル。
  ユーザーがKabuMartのスクショを貼り付けたら、画像解析→yfinanceデータ取得→WebSearch調査→JSON生成を自動で行う。
  「銘柄分析」「KabuMart」「株分析」「企業分析」「スクリーニング結果」「この銘柄どう？」など、
  日本株の個別銘柄を調べたいときに必ず使う。スクリーンショットが添付されていなくても、
  銘柄コード（4桁）や企業名が指定されていればWebSearchのみで分析を実行できる。
---

# KabuMart銘柄分析

KabuMartのスクリーンショットを読み取り、yfinanceで定量データを取得し、
WebSearchで定性情報を補完して、分析結果をJSON形式で出力する。

**このスキルの責務は「正しい形式のJSONを生成してGitHubにpushすること」のみ。**
HTMLの生成・表示には一切関与しない（別リポジトリの `detail.html` がJSONを読み取って描画する）。

## 対象ユーザー

投資初心者の「ふゆさん」。専門用語はすべて噛み砕いて説明する。
「つまりどういうこと？」という問いを常に意識し、具体例や日常の比喩で伝える。

---

## 実行フロー

ユーザーから画像または銘柄情報が提供されたら、以下を順番に実行する。

### Step 1：画像解析（スクショがある場合）

KabuMartのスクリーンショットから以下を正確に読み取る：

- **企業名**・**銘柄コード**（4桁）・**業種**
- **総合スコア**とランク（S, A+, A, B+ など）
- **5軸スコア**：成長性、安定性、収益性、余力、新規性（それぞれ数値とランク）
- **予想PER**（倍率）
- **株価チャート**から直近の株価水準を推定
- **ポジティブ要素**（全件、原文のまま抽出）
- **ネガティブ要素**（全件、原文のまま抽出）

スクショがなく銘柄コードのみの場合はこのStepをスキップし、
KabuMartスコアのセクションは「データなし」として空欄にする。

### Step 2：yfinanceデータ取得（定量データの確保）

銘柄コードが判明したら、`scripts/fetch_yfinance.py` を実行して定量データを取得する。

```bash
python scripts/fetch_yfinance.py {銘柄コード} --full --pretty
```

**取得できるデータ：**
- **株価情報**：現在値、52週高値/安値、出来高
- **バリュエーション**：PER（実績/予想）、PBR、PSR、EV/EBITDA
- **ファンダメンタルズ**：ROE、ROA、利益率、売上成長率、自己資本比率
- **配当**：利回り、配当額、配当性向
- **アナリスト情報**：目標株価（高/平均/低）、推奨、アナリスト数
- **テクニカル指標**（`--full`時）：RSI、ボリンジャーバンド位置、SMA50/200ステータス、リターン
- **変化スコア**（`--full`時）：アクルーアルズ、売上加速度、FCFマージン変化、ROE趨勢
- **推定リターン**（`--full`時）：楽観/ベース/悲観の3シナリオ

**yfinanceが使えない場合：** `pip install yfinance` が未実行の場合はエラーJSONが返る。
その場合はStep 2をスキップし、従来通りWebSearchのみで分析を続行する（Graceful degradation）。

**データの役割分担：**
- yfinance → **定量データ**（数字）：PER、PBR、ROE、配当利回り、株価、アナリスト目標株価
- WebSearch → **定性データ**（文脈）：ビジネスモデル、成長戦略、競合状況、リスク要因

### Step 3：WebSearch調査（定性情報の補完）

yfinanceで取得済みの数字系（PER、株価など）は検索不要。
定性的な情報に集中してWebSearchを実行する。

**必須（常に実行）：**
```
"[企業名] ビジネスモデル 収益構造 セグメント"
"[企業名] 決算 業績 最新 2026"
"[企業名] 競合 市場シェア"
```

**推奨（できるだけ実行）：**
```
"[企業名] 成長戦略 中期経営計画"
"[企業名] リスク 課題"
```

**条件付き（yfinanceでデータが取れなかった項目のみ）：**
```
"[企業名] ROE 自己資本比率 財務 配当"
"[銘柄コード] PER 株価"
"[企業名] アナリスト 目標株価"
```

クエリの詳細パターンは `references/search_queries.md` を参照。

### Step 4：データ構造化

調査結果を以下の構造で整理する（内部処理用、ユーザーには見せない）：

```
company:       企業名、コード、業種、市場
scores:        KabuMartの5軸スコア + 総合スコア
financials:    PER、PBR、ROE、自己資本比率、配当利回り（yfinance優先、なければWebSearch）
price:         現在株価、52週高値/安値（yfinance）
business:      ビジネスモデル概要、主力事業、収益構造（WebSearch）
segments:      セグメント名、売上比率、利益率（WebSearch）
positives:     ポジティブ要素（KabuMart原文 + WebSearch追加分）
negatives:     ネガティブ要素（KabuMart原文 + WebSearch追加分）
change_score:  変化スコア（yfinance、取得できた場合のみ）
technical:     テクニカル指標（yfinance、取得できた場合のみ）
analyst:       アナリスト情報・推定リターン（yfinance、取得できた場合のみ）
verdict:       強み3つ、懸念3つ、初心者向けまとめ
```

### Step 5：分析JSONの生成・保存・push

**** 分析結果は `webapp/data/stocks/{コード}.json` に保存する。

**保存先：** `webapp/data/stocks/{銘柄コード}.json`（例：`402A.json`）

生成後に以下を必ず実行する：
1. **manifest.jsonを更新**（`scripts/update_manifest.py` を実行）
2. **git add + commit + push**（Claude が自動実行）

```bash
# manifest更新（--file と --url は省略可能・自動補完される）
python scripts/update_manifest.py \
  --code {銘柄コード} \
  --name "{企業名}" \
  --date {YYYY-MM-DD} \
  --rank {ランク}

# git push（必須）
git add webapp/data/stocks/{コード}.json webapp/manifest.json
git commit -m "feat: {企業名}（{コード}）分析データを追加"
git push
```

pushが完了したら、URLを案内する：
`https://stock-dashboard-pi-navy.vercel.app/stocks/detail.html?code={コード}`

### Step 6（JSON push後）：ウォッチリスト追加の提案

分析JSONをpushしてURLを案内した後、Claudeはユーザーに対して以下のように提案する：
「ウォッチリストに追加しますか？ダッシュボードの『👀 ウォッチリストに追加』ボタンから直接登録できます。または『追加して』と伝えてください」
- ダッシュボードのボタンから直接 Render API 経由で登録可能（GitHub に自動コミット）
- ユーザーが「追加して」「入れといて」等と口頭で伝えた場合 → watchlistスキルが処理
- analyzerは提案するだけで、保存処理には関与しない（役割分離）

---

## JSONスキーマ定義

以下は `detail.html` のJavaScriptが参照する全フィールドを網羅したスキーマ。
このスキーマに従ったJSONを出力すること。

### トップレベル

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `generated_at` | string | ✅ | 生成日時 ISO形式（例: `"2026-02-20T10:00:00"`） |
| `has_yfinance` | boolean | ✅ | yfinanceデータ取得成否 |
| `has_websearch` | boolean | ✅ | WebSearch実行成否 |
| `has_kabumart` | boolean | ✅ | KabuMartスクショからの読み取り成否 |
| `ipo_date` | string\|null | | IPO日 `"YYYY-MM-DD"`（該当する場合のみ。株価チャート上にIPOラインが描画される） |

### `company` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `name` | string | ✅ | 企業名 |
| `code` | string | ✅ | 銘柄コード（4桁） |
| `industry` | string | ✅ | 業種（具体的に。例: `"宇宙・航空"`, `"精密機器"` ） |
| `market` | string | ✅ | 市場（例: `"東証プライム"`, `"東証グロース"`） |
| `analyzed_date` | string | ✅ | 調査日 `"YYYY-MM-DD"` |
| `extra_badge` | string\|null | | 追加バッジテキスト（例: `"IPO 2025.8"`）。該当する場合のみ |
| `kabumart_score` | number\|null | | KabuMart総合スコア（0〜10）。ウォッチリスト追加時にも使用される |
| `kabumart_rank` | string\|null | | KabuMartランク（`"SSS"` 〜 `"F"`）。ウォッチリスト追加時にも使用される |

### `scores` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `total_score` | number | ✅ | 総合スコア（0〜10）。円グラフで表示される |
| `total_rank` | string | ✅ | 総合ランク。有効値: `"SSS"`,`"SS"`,`"S"`,`"A+"`,`"A"`,`"B+"`,`"B"`,`"C"`,`"D"`,`"E"`,`"F"` |
| `note` | string | | スコアの補足説明（例: 赤字フェーズの場合の注釈など） |
| `interpretation` | string | | スコアの読み方・解釈（初心者向け。ボックス内に表示される） |
| `axes` | object | ✅ | 5軸スコア（下記参照） |

**`axes` の各軸**（キー: `growth`, `stability`, `profitability`, `capacity`, `innovation`）：

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `score` | number | ✅ | スコア値（0〜10）。バーとレーダーチャートの両方で使用 |
| `rank` | string | ✅ | ランク（`"SSS"` 〜 `"F"`） |

### `financials` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `per` | number\|null | ✅ | 予想PER。赤字の場合 `null`（ゲージが「赤字」表示になる） |
| `per_note` | string | | PERの初心者向け解説（ゲージ下のツールチップに表示） |
| `roe` | number\|null | ✅ | ROE %値。赤字の場合 `null` |
| `roe_note` | string | | ROEの初心者向け解説 |
| `equity_ratio` | number\|null | ✅ | 自己資本比率 %値（0〜100） |
| `equity_ratio_note` | string | | 自己資本比率の初心者向け解説 |
| `valuation_table` | array | | バリュエーション詳細テーブル（下記参照）。yfinanceデータがある場合に出力 |

**`valuation_table` の各行：**

| フィールド | 型 | 説明 |
|---|---|---|
| `label` | string | 指標名（例: `"PBR（株価純資産倍率）"`, `"配当利回り"`, `"売上成長率（前年比）"`） |
| `value` | string | 値（表示用文字列。例: `"4.24倍"`, `"なし"`, `"-44.4%"`） |
| `benchmark` | string | 一般的な目安（例: `"目安: 1倍以下は割安"`, `"プラスが望ましい"`） |
| `status` | string | 評価ステータス: `"good"` / `"warn"` / `"bad"` |
| `badge` | string | 評価バッジテキスト（例: `"割安"`, `"割高"`, `"高水準"`, `"無配"`） |
| `badge_color` | string | バッジ色: `"green"` / `"orange"` / `"red"` / `"gray"` |
| `note` | string | 初心者向け補足説明（「つまり」を含む） |

### `price` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `current` | number | ✅ | 現在株価（円） |
| `week52_high` | number | | 52週高値（円） |
| `week52_low` | number | | 52週安値（円） |
| `from_high_pct` | string | | 高値からの変動率（例: `"-51.1%"`, `"+12.3%"`） |

### `price_history` 配列

yfinanceで取得した過去1年間の日次終値データ。株価チャートとして描画される。

各要素: `{ "date": "YYYY-MM-DD", "close": 数値 }`

### `earnings_dates` 配列（任意）

決算発表日のリスト。チャート上にマーカーとして表示可能。

各要素: `{ "date": "YYYY-MM-DD", "label": "1Q決算" }`

### `business` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `catchcopy` | string | ✅ | キャッチコピー。HTML `<span>` タグで副題を囲むことも可能 |
| `paragraphs` | string[] | ✅ | 事業説明（3段落程度の配列）。具体的な製品・サービス名を含めること |
| `tags` | string[] | ✅ | ビジネスタグ（例: `["BtoB", "宇宙インフラ", "グロース株"]`） |
| `segments` | array | ✅ | 事業セグメント情報（下記参照） |

**`segments` の各要素：**

| フィールド | 型 | 説明 |
|---|---|---|
| `icon` | string | 絵文字アイコン（例: `"🌍"`, `"🚀"`） |
| `name` | string | セグメント名 |
| `description` | string | セグメントの説明（初心者向け、具体的に） |
| `highlight` | boolean | 主力セグメントの場合 `true`（視覚的に強調表示される） |

### `change_score` オブジェクト（yfinanceデータがある場合のみ）

| フィールド | 型 | 説明 |
|---|---|---|
| `total` | number | 合計スコア（0〜100） |
| `interpretation` | string | 解釈ラベル。≥75: `"強い改善トレンド 📈"` / 50-74: `"改善傾向あり ↗️"` / 35-49: `"横ばい ➡️"` / <35: `"悪化傾向 📉"` |
| `components` | object | 4指標の詳細（キー: `accruals`, `revenue_accel`, `fcf_margin`, `roe_trend`） |

**`components` の各指標：**

| フィールド | 型 | 説明 |
|---|---|---|
| `score` | number | スコア（0〜25） |
| `max` | number | 常に `25` |
| `detail` | string | 初心者向けの解説文（「つまり」を含む） |

### `technical` オブジェクト（yfinanceデータがある場合のみ）

| フィールド | 型 | 説明 |
|---|---|---|
| `rsi_14` | number\|null | RSI（14日） |
| `bollinger_position` | number\|null | ボリンジャーバンド内の位置（0〜1） |
| `sma_status` | object | `{ "sma50_above_price": boolean|null, "golden_cross": boolean|null, "death_cross": boolean|null }` |
| `return_1m` | number\|null | 1ヶ月リターン（%） |
| `return_3m` | number\|null | 3ヶ月リターン（%） |
| `return_6m` | number\|null | 6ヶ月リターン（%） |
| `return_1y` | number\|null | 1年リターン（%） |
| `volatility_30d` | number\|null | 30日ボラティリティ（%） |

### `analyst` オブジェクト（yfinanceデータがある場合のみ）

| フィールド | 型 | 説明 |
|---|---|---|
| `target_high` | number\|null | アナリスト目標株価（高値） |
| `target_mean` | number\|null | アナリスト目標株価（平均） |
| `target_low` | number\|null | アナリスト目標株価（安値） |
| `recommendation` | string\|null | 推奨: `"buy"` / `"hold"` / `"sell"` / `"none"` |
| `number_of_analysts` | number\|null | アナリスト数 |

### `positives` / `negatives` 配列

各要素：

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `title` | string | ✅ | 要素のタイトル |
| `impact` | string | ✅ | インパクト: `"high"` / `"mid"` / `"low"` |
| `explain` | string | ✅ | 初心者向け解説。必ず「つまり」を含む言い換えを入れること |
| `source` | string | ✅ | 情報源: `"📌 KabuMart"` / `"📝 WebSearch"` / `"📊 yfinance"` またはそれらの組み合わせ |

**yfinanceデータから自動追加するポジネガ要素：**
- PBR < 1.0 → ポジティブに追加「資産価値以下で買える（割安の可能性）」
- 配当利回り > 3% → ポジティブに追加「高配当銘柄」
- 変化スコア > 60 → ポジティブに追加「業績改善トレンド」
- 変化スコア < 30 → ネガティブに追加「業績悪化傾向」
- RSI > 70 → ネガティブに追加「短期的に買われすぎ」
- デッドクロス → ネガティブに追加「テクニカル的に弱い」

### `verdict` オブジェクト

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| `strengths` | array | ✅ | 強み3つ（下記の要素形式） |
| `risks` | array | ✅ | 懸念3つ（下記の要素形式） |
| `summary` | string | ✅ | 初心者向けまとめ（結論ファースト、200〜400文字）。変化スコアがある場合は「今の方向性」も含める |

**`strengths` / `risks` の各要素：**

| フィールド | 型 | 説明 |
|---|---|---|
| `icon` | string | 絵文字アイコン（例: `"💪"`, `"⚠️"`, `"🛰️"`） |
| `title` | string | 短いタイトル |
| `text` | string | 初心者向けの詳細説明 |

### `links` 配列

各要素: `{ "label": "表示テキスト", "url": "https://..." }`

参考URLリスト（公式IR、ニュース記事、決算資料など）。

---

## ライティングルール

JSON内のテキスト系フィールド（`explain`, `*_note`, `summary`, `paragraphs`, `description`, `catchcopy`, `detail`, `interpretation` 等）は
初心者が「つまりどういうこと？」と迷わないように以下を徹底する。

1. **専門用語は登場するたびに平易な言葉で言い換える**
   - PER 12倍 → 「利益の12倍の価格で買える」
   - ROE 15% → 「株主のお金を15%の効率で増やしている」
   - 自己資本比率 50% → 「企業の資産の50%が自分たちのお金」

2. **「つまり〇〇ってこと」を必ず入れる**
   - `explain` フィールドには必ず「つまり」を含む言い換えを入れる
   - `*_note` フィールドにも平易な解説を添える

3. **抽象的な業種名だけで終わらせない**
   - ❌ 「電子機器製造企業」
   - ✅ 「ロボットの目になる精密なセンサーを世界中の工場に売っている企業」

4. **友人に教えるような口調**
   - 投資判断に必要な情報は漏らさず、でも簡潔に
   - 数字は可能な限り具体的に入れる

5. **データソース間の差異**
   - yfinanceの数字とWebSearchの数字に差がある場合、yfinanceの値を優先
   - 「（yfinance取得値。WebSearchでは〇〇との記載あり）」と注記する

---

## データソースの優先順位

| データ項目 | 第1ソース | 第2ソース（フォールバック） |
|---|---|---|
| PER, PBR, 配当利回り | yfinance | WebSearch |
| ROE, 自己資本比率 | yfinance | WebSearch |
| 株価, 時価総額 | yfinance | WebSearch |
| アナリスト目標株価 | yfinance | WebSearch |
| テクニカル指標 | yfinance | 出力しない |
| 変化スコア | yfinance | 出力しない |
| ビジネスモデル, 事業内容 | WebSearch | ― |
| 競合, 市場シェア | WebSearch | ― |
| 成長戦略, リスク | WebSearch | ― |
| KabuMartスコア | 画像解析 | 出力しない |

---

## 技術仕様

- **出力**：JSONファイル（`webapp/data/stocks/{コード}.json`）のみ。
- **Pythonスクリプト**：`scripts/fetch_yfinance.py`（要 `pip install yfinance`）
- **ダッシュボードURL**：`https://stock-dashboard-pi-navy.vercel.app`
- **バックエンドAPI**：`https://stock-dashboard-rif1.onrender.com`

---

## 注意事項

- このレポートは投資助言ではない（`verdict.summary` の末尾にも含める）
- データの出典（KabuMart、yfinance、WebSearch元）を `source` フィールドに記載する
- 株価や市場データは現在の日付を基準に検索する
- 調査はあくまで公開情報に基づくものであり、正確性を保証するものではない
- yfinanceのデータは無料APIであり、リアルタイムではなく遅延データの可能性がある

