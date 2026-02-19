#!/usr/bin/env python3
"""
ウォッチリスト管理スクリプト

watchlist.json のCRUD操作を行う。
kabumart-analyzerで分析した銘柄の追加・一覧・削除・ステータス更新を管理する。

使い方:
    python watchlist_manager.py add --code 7203 --name "トヨタ自動車"
    python watchlist_manager.py add --code 7203 --name "トヨタ自動車" --note "高配当" --rank "A+" --per 12.5
    python watchlist_manager.py list
    python watchlist_manager.py list --format detail
    python watchlist_manager.py remove --code 7203
    python watchlist_manager.py status --code 7203 --status pending
    python watchlist_manager.py update-per --code 7203 --per 13.2
    python watchlist_manager.py count

ステータス一覧:
    watching   👀 要観察（デフォルト）
    interested 💛 積極検討
    pending    ⏳ 見送り中
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Windows環境でのUnicodeEncodeError対策
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# データファイルのパス（スクリプトと同階層の data/ ディレクトリ）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

VALID_STATUSES = ["watching", "interested", "pending"]
STATUS_LABELS = {
    "watching":   "👀 要観察",
    "interested": "💛 積極検討",
    "pending":    "⏳ 見送り中",
}


def load_watchlist() -> dict:
    """ウォッチリストを読み込む。ファイルがなければ空リストを返す。"""
    if not os.path.exists(WATCHLIST_FILE):
        return {"watchlist": [], "updated_at": None}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"watchlist": [], "updated_at": None}


def save_watchlist(data: dict):
    """ウォッチリストを保存する。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_stock(code: str, name: str, note: str = "", rank: str = "",
              change_score: float = None, status: str = "watching", per: float = None):
    """銘柄をウォッチリストに追加する。"""
    data = load_watchlist()

    # 重複チェック
    for item in data["watchlist"]:
        if item["code"] == code:
            print(json.dumps({
                "status": "duplicate",
                "message": f"{name}（{code}）はすでにウォッチリストに登録されています",
                "count": len(data["watchlist"])
            }, ensure_ascii=False))
            return

    entry = {
        "code": code,
        "name": name,
        "added_date": datetime.now().strftime("%Y-%m-%d"),
        "note": note,
        "status": status if status in VALID_STATUSES else "watching",
        "per": per,
    }
    if rank:
        entry["kabumart_rank"] = rank
    if change_score is not None:
        entry["change_score"] = change_score

    data["watchlist"].append(entry)
    save_watchlist(data)

    print(json.dumps({
        "status": "added",
        "message": f"✅ {name}（{code}）をウォッチリストに追加しました",
        "count": len(data["watchlist"]),
        "entry": entry
    }, ensure_ascii=False))


def list_stocks(format_type: str = "simple"):
    """ウォッチリストを表示する。"""
    data = load_watchlist()

    if not data["watchlist"]:
        print(json.dumps({
            "status": "empty",
            "message": "ウォッチリストは空です",
            "count": 0
        }, ensure_ascii=False))
        return

    print(json.dumps({
        "status": "ok",
        "count": len(data["watchlist"]),
        "updated_at": data.get("updated_at"),
        "watchlist": data["watchlist"]
    }, ensure_ascii=False, indent=2 if format_type == "detail" else None))


def remove_stock(code: str):
    """銘柄をウォッチリストから削除する。"""
    data = load_watchlist()
    original_count = len(data["watchlist"])

    data["watchlist"] = [item for item in data["watchlist"] if item["code"] != code]

    if len(data["watchlist"]) == original_count:
        print(json.dumps({
            "status": "not_found",
            "message": f"銘柄コード {code} はウォッチリストに見つかりません",
            "count": len(data["watchlist"])
        }, ensure_ascii=False))
        return

    save_watchlist(data)
    print(json.dumps({
        "status": "removed",
        "message": f"🗑️ {code} をウォッチリストから削除しました",
        "count": len(data["watchlist"])
    }, ensure_ascii=False))


def update_status(code: str, status: str):
    """銘柄のステータスを更新する。"""
    if status not in VALID_STATUSES:
        print(json.dumps({
            "status": "error",
            "message": f"無効なステータス: {status}。有効値: {', '.join(VALID_STATUSES)}"
        }, ensure_ascii=False))
        return

    data = load_watchlist()
    for item in data["watchlist"]:
        if item["code"] == code:
            item["status"] = status
            save_watchlist(data)
            print(json.dumps({
                "status": "updated",
                "message": f"✅ {item['name']}（{code}）のステータスを「{STATUS_LABELS[status]}」に変更しました",
                "entry": item
            }, ensure_ascii=False))
            return

    print(json.dumps({
        "status": "not_found",
        "message": f"銘柄コード {code} はウォッチリストに見つかりません"
    }, ensure_ascii=False))


def update_per(code: str, per: float, source: str = "yfinance"):
    """銘柄の予想PERを更新し、履歴に追記する。"""
    data = load_watchlist()
    today = datetime.now().strftime("%Y-%m-%d")

    for item in data["watchlist"]:
        if item["code"] == code:
            old_per = item.get("per")
            item["per"] = per

            # per_history に今日の値を追記（同日の重複は上書き）
            history = item.get("per_history", [])
            # 同日エントリがあれば上書き、なければ追記
            same_day = [h for h in history if h["date"] == today]
            if same_day:
                same_day[0]["per"] = per
                same_day[0]["source"] = source
            else:
                history.append({"date": today, "per": per, "source": source})
            item["per_history"] = history

            save_watchlist(data)
            print(json.dumps({
                "status": "updated",
                "message": f"✅ {item['name']}（{code}）の予想PERを {old_per} → {per} に更新しました（履歴: {len(history)}件）",
                "entry": item
            }, ensure_ascii=False))
            return

    print(json.dumps({
        "status": "not_found",
        "message": f"銘柄コード {code} はウォッチリストに見つかりません"
    }, ensure_ascii=False))


def count_stocks():
    """ウォッチリストの件数を返す。"""
    data = load_watchlist()
    print(json.dumps({
        "status": "ok",
        "count": len(data["watchlist"])
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="ウォッチリスト管理")
    subparsers = parser.add_subparsers(dest="command", help="操作を選択")

    # add
    add_parser = subparsers.add_parser("add", help="銘柄を追加")
    add_parser.add_argument("--code", required=True, help="銘柄コード（4桁）")
    add_parser.add_argument("--name", required=True, help="企業名")
    add_parser.add_argument("--note", default="", help="メモ")
    add_parser.add_argument("--rank", default="", help="KabuMartランク")
    add_parser.add_argument("--change-score", type=float, default=None, help="変化スコア")
    add_parser.add_argument("--status", default="watching",
                            choices=VALID_STATUSES, help="初期ステータス")
    add_parser.add_argument("--per", type=float, default=None, help="予想PER（倍）")

    # list
    list_parser = subparsers.add_parser("list", help="一覧表示")
    list_parser.add_argument("--format", choices=["simple", "detail"], default="simple")

    # remove
    remove_parser = subparsers.add_parser("remove", help="銘柄を削除")
    remove_parser.add_argument("--code", required=True)

    # status
    status_parser = subparsers.add_parser("status", help="ステータスを変更")
    status_parser.add_argument("--code", required=True)
    status_parser.add_argument("--status", required=True, choices=VALID_STATUSES)

    # update-per
    per_parser = subparsers.add_parser("update-per", help="予想PERを更新（履歴に追記）")
    per_parser.add_argument("--code", required=True)
    per_parser.add_argument("--per", required=True, type=float)
    per_parser.add_argument("--source", default="yfinance",
                            help="データソース（kabumart / yfinance）")

    # count
    subparsers.add_parser("count", help="件数確認")

    args = parser.parse_args()

    if args.command == "add":
        add_stock(args.code, args.name, args.note, args.rank,
                  args.change_score, args.status, args.per)
    elif args.command == "list":
        list_stocks(args.format)
    elif args.command == "remove":
        remove_stock(args.code)
    elif args.command == "status":
        update_status(args.code, args.status)
    elif args.command == "update-per":
        update_per(args.code, args.per, args.source)
    elif args.command == "count":
        count_stocks()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
