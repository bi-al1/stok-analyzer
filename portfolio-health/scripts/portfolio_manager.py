#!/usr/bin/env python3
"""
ポートフォリオ管理スクリプト

portfolio.json の売買記録・保有銘柄管理を行う。
ヘルスチェックのデータ取得は fetch_yfinance.py と連携する。

使い方:
    python portfolio_manager.py buy --code 7203 --name "トヨタ自動車" --shares 100 --price 2500
    python portfolio_manager.py sell --code 7203 --shares 50 --price 3000
    python portfolio_manager.py list
    python portfolio_manager.py list --format detail
    python portfolio_manager.py codes
    python portfolio_manager.py history
    python portfolio_manager.py history --code 7203
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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
PORTFOLIO_FILE = os.path.join(DATA_DIR, "portfolio.json")


def load_portfolio() -> dict:
    """ポートフォリオを読み込む。"""
    if not os.path.exists(PORTFOLIO_FILE):
        return {"holdings": [], "trade_history": [], "updated_at": None}
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {"holdings": [], "trade_history": [], "updated_at": None}


def save_portfolio(data: dict):
    """ポートフォリオを保存する。"""
    os.makedirs(DATA_DIR, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def buy_stock(code: str, name: str, shares: int, price: float, note: str = ""):
    """株を購入記録する。"""
    data = load_portfolio()

    # 取引履歴に追加
    trade = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "code": code,
        "name": name,
        "action": "buy",
        "shares": shares,
        "price": price,
    }
    data["trade_history"].append(trade)

    # 保有銘柄を更新
    existing = None
    for h in data["holdings"]:
        if h["code"] == code:
            existing = h
            break

    if existing:
        # 平均取得単価を更新
        total_cost = existing["avg_cost"] * existing["shares"] + price * shares
        total_shares = existing["shares"] + shares
        existing["avg_cost"] = round(total_cost / total_shares, 2)
        existing["shares"] = total_shares
    else:
        # 新規追加
        holding = {
            "code": code,
            "name": name,
            "shares": shares,
            "avg_cost": price,
            "purchase_date": datetime.now().strftime("%Y-%m-%d"),
            "note": note,
        }
        data["holdings"].append(holding)

    save_portfolio(data)

    print(json.dumps({
        "status": "bought",
        "message": f"✅ {name}（{code}）{shares}株を{price}円で購入記録しました",
        "holdings_count": len(data["holdings"]),
        "trade": trade,
    }, ensure_ascii=False))


def sell_stock(code: str, shares: int, price: float):
    """株を売却記録する。"""
    data = load_portfolio()

    # 保有銘柄を検索
    existing = None
    for h in data["holdings"]:
        if h["code"] == code:
            existing = h
            break

    if not existing:
        print(json.dumps({
            "status": "not_found",
            "message": f"銘柄コード {code} はポートフォリオに見つかりません",
        }, ensure_ascii=False))
        return

    if shares > existing["shares"]:
        print(json.dumps({
            "status": "insufficient",
            "message": f"保有株数（{existing['shares']}株）を超える売却はできません",
        }, ensure_ascii=False))
        return

    # 損益計算
    profit_per_share = price - existing["avg_cost"]
    total_profit = profit_per_share * shares

    # 取引履歴に追加
    trade = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "code": code,
        "name": existing["name"],
        "action": "sell",
        "shares": shares,
        "price": price,
        "profit_per_share": round(profit_per_share, 2),
        "total_profit": round(total_profit, 2),
    }
    data["trade_history"].append(trade)

    # 保有銘柄を更新
    existing["shares"] -= shares
    if existing["shares"] == 0:
        data["holdings"] = [h for h in data["holdings"] if h["code"] != code]

    save_portfolio(data)

    profit_str = f"+{total_profit:,.0f}" if total_profit >= 0 else f"{total_profit:,.0f}"
    print(json.dumps({
        "status": "sold",
        "message": f"✅ {existing['name']}（{code}）{shares}株を{price}円で売却記録しました（損益: {profit_str}円）",
        "holdings_count": len(data["holdings"]),
        "trade": trade,
    }, ensure_ascii=False))


def list_holdings(format_type: str = "simple"):
    """保有銘柄一覧を表示する。"""
    data = load_portfolio()

    if not data["holdings"]:
        print(json.dumps({
            "status": "empty",
            "message": "ポートフォリオは空です。「{銘柄}を{株数}株買った」で記録を追加できます",
            "count": 0,
        }, ensure_ascii=False))
        return

    print(json.dumps({
        "status": "ok",
        "count": len(data["holdings"]),
        "updated_at": data.get("updated_at"),
        "holdings": data["holdings"],
    }, ensure_ascii=False, indent=2 if format_type == "detail" else None))


def get_codes():
    """保有銘柄のコード一覧を返す（ヘルスチェック用）。"""
    data = load_portfolio()
    codes = [h["code"] for h in data["holdings"]]
    print(json.dumps({
        "status": "ok",
        "codes": codes,
        "count": len(codes),
    }, ensure_ascii=False))


def show_history(code: str = None):
    """取引履歴を表示する。"""
    data = load_portfolio()
    history = data.get("trade_history", [])

    if code:
        history = [t for t in history if t["code"] == code]

    if not history:
        msg = f"銘柄コード {code} の取引履歴はありません" if code else "取引履歴はありません"
        print(json.dumps({
            "status": "empty",
            "message": msg,
        }, ensure_ascii=False))
        return

    print(json.dumps({
        "status": "ok",
        "count": len(history),
        "history": history,
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="ポートフォリオ管理")
    subparsers = parser.add_subparsers(dest="command", help="操作を選択")

    # buy
    buy_parser = subparsers.add_parser("buy", help="購入記録")
    buy_parser.add_argument("--code", required=True, help="銘柄コード")
    buy_parser.add_argument("--name", required=True, help="企業名")
    buy_parser.add_argument("--shares", required=True, type=int, help="株数")
    buy_parser.add_argument("--price", required=True, type=float, help="購入単価")
    buy_parser.add_argument("--note", default="", help="メモ")

    # sell
    sell_parser = subparsers.add_parser("sell", help="売却記録")
    sell_parser.add_argument("--code", required=True, help="銘柄コード")
    sell_parser.add_argument("--shares", required=True, type=int, help="株数")
    sell_parser.add_argument("--price", required=True, type=float, help="売却単価")

    # list
    list_parser = subparsers.add_parser("list", help="保有一覧")
    list_parser.add_argument("--format", choices=["simple", "detail"], default="simple")

    # codes
    subparsers.add_parser("codes", help="銘柄コード一覧")

    # history
    hist_parser = subparsers.add_parser("history", help="取引履歴")
    hist_parser.add_argument("--code", default=None, help="特定銘柄のみ")

    args = parser.parse_args()

    if args.command == "buy":
        buy_stock(args.code, args.name, args.shares, args.price, args.note)
    elif args.command == "sell":
        sell_stock(args.code, args.shares, args.price)
    elif args.command == "list":
        list_holdings(args.format)
    elif args.command == "codes":
        get_codes()
    elif args.command == "history":
        show_history(args.code)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
