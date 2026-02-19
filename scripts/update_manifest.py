#!/usr/bin/env python3
"""
manifest.json 更新スクリプト

kabumart-analyzerで銘柄分析JSONを生成した後に実行し、
manifest.jsonに新規エントリを追加する。

使い方:
    python scripts/update_manifest.py \
        --code 402A \
        --name "アクセルスペースホールディングス" \
        --date 2026-02-18 \
        --rank C

    # --file は省略可能（省略時は data/stocks/{code}.json を自動設定）
    # --url  は省略可能（省略時は /stocks/detail.html?code={code} を自動設定）
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
BASE_DIR = os.path.dirname(SCRIPT_DIR)
# stok-analyzer の兄弟ディレクトリ stock-dashboard に書き込む
MANIFEST_FILE = os.path.join(BASE_DIR, "..", "stock-dashboard", "manifest.json")


def load_manifest():
    if not os.path.exists(MANIFEST_FILE):
        return {"stocks": []}
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_manifest(data):
    data["updated_at"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(MANIFEST_FILE), exist_ok=True)
    with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update(code, name, date, rank, file_path, url):
    data = load_manifest()

    # 同じcodeが既にあれば更新、なければ追加
    existing = next((s for s in data["stocks"] if s["code"] == code), None)
    entry = {
        "code": code,
        "name": name,
        "analyzed_date": date,
        "kabumart_rank": rank,
        "data_file": file_path,   # data/stocks/{code}.json
        "url": url,               # /stocks/detail.html?code={code}
    }
    if existing:
        existing.update(entry)
        action = "updated"
    else:
        data["stocks"].append(entry)
        action = "added"

    save_manifest(data)
    print(json.dumps({
        "status": action,
        "entry": entry,
        "total": len(data["stocks"]),
    }, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="manifest.json 更新")
    parser.add_argument("--code", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--rank", default="")
    parser.add_argument("--file", default=None, help="省略時: data/stocks/{code}.json")
    parser.add_argument("--url",  default=None, help="省略時: /stocks/detail.html?code={code}")
    args = parser.parse_args()

    file_path = args.file or f"data/stocks/{args.code.upper()}.json"
    url = args.url or f"/stocks/detail.html?code={args.code.upper()}"

    update(args.code, args.name, args.date, args.rank, file_path, url)


if __name__ == "__main__":
    main()
