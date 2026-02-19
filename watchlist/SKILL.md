---
name: watchlist
description: >
  気になる銘柄のウォッチリストを管理するスキル。
  kabumart-analyzerで分析した銘柄の追加、一覧表示、削除、ステータス変更を行う。
  「ウォッチリストに追加」「気になる銘柄一覧」「ウォッチリストから外して」など、
  買う前の銘柄リスト管理に関する操作で使う。
  ダッシュボードからコピーしたテキスト（「ウォッチリストに追加: XXXX 企業名 日付」）を
  受け取った場合もこのスキルが処理する。
---

# ウォッチリスト管理

KabuMartで分析した「気になる銘柄」を管理するシンプルなリストスキル。
買う前の検討段階の銘柄を追加・一覧・削除・ステータス管理する。

## 対象ユーザー

投資初心者の「ふゆさん」。操作は自然言語で行い、コマンドを覚える必要はない。

---

## データ管理

### 保存先
GitHubリポジトリ `bi-al1/kabumart-web` の `data/watchlist.json`

読み書きは全て **Render API（`https://kabumart-analyzer.onrender.com`）経由** で行う。
Claudeが直接JSONを編集したりgit pushしたりする必要はない。

### データ構造
```json
{
  "watchlist": [
    {
      "code": "7203",
      "name": "トヨタ自動車",
      "added_date": "2026-02-17",
      "note": "KabuMartスコアA+、変化スコア72",
      "kabumart_rank": "A+",
      "change_score": 72,
      "status": "watching",
      "per": 12.5,
      "per_history": [
        { "date": "2026-02-17", "per": 15.2, "source": "kabumart" },
        { "date": "2026-03-01", "per": 12.5, "source": "yfinance" }
      ]
    }
  ],
  "updated_at": "2026-02-17T10:30:00"
}
```

### PER矢印表示ルール（Webダッシュボード）

`per_history` の最新2件を比較して矢印を表示する：

| 状況 | 表示例 | 意味 |
|------|--------|------|
| 黒字でPER下落 | `PER 12.5倍 ↓` 🟢 | 割安方向に改善 |
| 黒字でPER上昇 | `PER 20.0倍 ↑` 🔴 | 割高方向に悪化 |
| 赤字で絶対値縮小 | `PER -7.2倍 ↑` 🟡 | 赤字が改善中 |
| 赤字で絶対値拡大 | `PER -12.0倍 ↓` 🔴 | 赤字が悪化中 |
| 横ばい（0.05倍以内） | `PER 15.2倍 →` ⬜ | 変化なし |
| 履歴1件のみ | `PER -9.1倍` | 初回のため矢印なし |
```

### ステータス一覧
| 値 | 表示 | 意味 |
|----|------|------|
| `watching` | 👀 要観察 | デフォルト。気になって観察中 |
| `interested` | 💛 積極検討 | 近く買いたい候補 |
| `pending` | ⏳ 見送り中 | 今は買わないが消したくない |

---

## コマンド

### 追加
**トリガー例：**
- 「ウォッチリストに追加: 7203 トヨタ自動車 2026-02-17」（ダッシュボードからのコピペ）
- 「これウォッチリストに入れて」（直前のkabumart-analyzer分析の文脈から）
- 「7203をウォッチリストに追加」

**処理：**
1. 銘柄コード・企業名を特定
2. Render API `POST /api/watchlist` を呼び出す
3. 「✅ {企業名}（{コード}）をウォッチリストに追加しました（現在 N 銘柄）」と返答

```bash
curl -X POST https://kabumart-analyzer.onrender.com/api/watchlist \
  -H "Content-Type: application/json" \
  -d '{"code":"7203","name":"トヨタ自動車","note":"KabuMartスコアA+","kabumart_rank":"A+"}'
```

**kabumart-analyzerからの引き継ぎ時：**
- 分析データに `financials.per` があれば `note` に含める
- KabuMartランクがあれば `kabumart_rank` に渡す

### ステータス変更
**トリガー例：**
- 「402Aを積極検討に変えて」
- 「アクセルスペースは見送りにして」
- 「7203を要観察に戻して」

**処理：**
1. 銘柄コードを特定
2. Render API `POST /api/watchlist/status` を呼び出す
3. 「✅ {企業名}のステータスを「{ラベル}」に変更しました」と返答

```bash
curl -X POST https://kabumart-analyzer.onrender.com/api/watchlist/status \
  -H "Content-Type: application/json" \
  -d '{"code":"7203","status":"pending"}'
# status値: watching / interested / pending
```

**注意：** ステータスはWebダッシュボード上でも変更可能。どちらで変更しても即時反映される。

### 一覧
**トリガー例：**
- 「ウォッチリストを見せて」
- 「気になる銘柄一覧」
- 「ウォッチリスト」

**処理：**
1. Render API `GET /api/watchlist` を呼び出す
2. 一覧を表示（コード、企業名、ステータス、PER、追加日、メモ）
3. リストが空なら「ウォッチリストは空です。kabumart-analyzerで分析後に追加できます」

```bash
curl https://kabumart-analyzer.onrender.com/api/watchlist
```

### 削除
**トリガー例：**
- 「7203をウォッチリストから外して」
- 「トヨタを削除」

**処理：**
1. Render API `DELETE /api/watchlist/{code}` を呼び出す
2. 「🗑️ {企業名}（{コード}）をウォッチリストから削除しました」と返答

```bash
curl -X DELETE https://kabumart-analyzer.onrender.com/api/watchlist/7203
```

### 購入移行（portfolio-healthとの連携）
**トリガー例：**
- 「7203を買った」「トヨタを100株買った」

**処理：**
1. Render API `DELETE /api/watchlist/{code}` でウォッチリストから削除
2. 「portfolio-healthスキルで売買記録を登録してください」と案内
3. または、購入情報（株数・価格）が提供されていれば、portfolio-healthに引き継ぐ

---

## データ反映フロー（Webアプリ連携）

```
Claude
  ↓ Render API を呼び出す（curl / fetch）
Render FastAPI（https://kabumart-analyzer.onrender.com）
  ↓ GitHub Contents API を呼び出す
GitHub（bi-al1/kabumart-web）の data/watchlist.json を更新・コミット
  ↓
ブラウザで「更新」ボタンを押すと最新データが反映される
```

**Claudeはgit pushを実行しない。** Render APIが自動的にGitHubを更新する。

### ウォッチリストの読み込み先
- ブラウザ → Render `/api/watchlist` → GitHub Contents API → 常に最新を返す
- GitHub Raw CDNのキャッシュ問題を回避するため、Render API経由で取得している

---

## 注意事項

- ウォッチリストは「気になる銘柄」であり、購入推奨ではない旨を表示時に添える
- PERはnullの場合もある（赤字企業はPER計算不能）
- Renderは無料枠のためスリープあり。初回呼び出しは数秒かかる場合がある
- ダッシュボードからの操作（UI）もRender API経由で同じJSONを更新する
