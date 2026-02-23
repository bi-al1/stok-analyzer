import json
import os
import yfinance as yf
from datetime import datetime

WATCHLIST_PATH = "watchlist/data/watchlist.json"

def main():
    if not os.path.exists(WATCHLIST_PATH):
        print(f"Error: {WATCHLIST_PATH} not found.")
        return

    with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    updated_count = 0

    for entry in data.get("watchlist", []):
        if entry.get("status") == "archived":
            continue

        code = entry["code"]
        try:
            # GitHub Actionsのサーバーからはそのままアクセスで大体OK
            ticker = yf.Ticker(f"{code}.T")
            info = ticker.info
            per = info.get("forwardPE") or info.get("trailingPE")
            
            if per is not None:
                per = round(float(per), 1)
                entry["per"] = per

                history = entry.get("per_history", [])
                same_day = [h for h in history if h["date"] == today]
                if same_day:
                    same_day[0]["per"] = per
                    same_day[0]["source"] = "yfinance"
                else:
                    history.append({"date": today, "per": per, "source": "yfinance"})
                entry["per_history"] = history

                updated_count += 1
                print(f"Updated PER for {code}: {per}")
        except Exception as e:
            print(f"Failed to update {code}: {e}")

    if updated_count > 0:
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        print(f"Successfully updated {updated_count} items.")
    else:
        print("No items to update.")

if __name__ == "__main__":
    main()
