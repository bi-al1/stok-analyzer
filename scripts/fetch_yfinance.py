#!/usr/bin/env python3
"""
yfinance データ取得スクリプト for kabumart-analyzer

日本株の銘柄コード（4桁）を受け取り、yfinance経由で
財務データ・テクニカル指標・アナリスト情報を取得してJSON出力する。

使い方:
    python fetch_yfinance.py 7203        # トヨタ自動車
    python fetch_yfinance.py 7203 --full  # 変化スコア含むフル取得

依存: pip install yfinance
"""

import argparse
import json
import sys
import warnings
from datetime import datetime, timedelta

# Windows環境でのUnicodeEncodeError対策
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

warnings.filterwarnings("ignore")

try:
    import yfinance as yf
except ImportError:
    print(json.dumps({
        "error": "yfinance未インストール。`pip install yfinance` を実行してください。",
        "status": "missing_dependency"
    }))
    sys.exit(1)


def safe_get(info: dict, key: str, default=None):
    """yfinanceのinfoから安全に値を取得（異常値サニタイズ付き）"""
    val = info.get(key, default)
    if val is None:
        return default
    return val


def sanitize_ratio(value, min_val=0, max_val=500):
    """異常値を除外する（PER > 500 や PBR < 0 など）"""
    if value is None:
        return None
    if value < min_val or value > max_val:
        return None
    return round(value, 2)


def calc_rsi(prices, period=14):
    """RSI（相対力指数）を計算"""
    if prices is None or len(prices) < period + 1:
        return None
    deltas = prices.diff().dropna()
    gain = deltas.where(deltas > 0, 0).rolling(window=period).mean()
    loss = (-deltas.where(deltas < 0, 0)).rolling(window=period).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return round(100 - (100 / (1 + rs)), 1)


def calc_bollinger_position(prices, period=20):
    """ボリンジャーバンドにおける現在価格の位置（0〜1、0.5が中央）"""
    if prices is None or len(prices) < period:
        return None
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    if upper.iloc[-1] == lower.iloc[-1]:
        return 0.5
    position = (prices.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
    return round(min(max(position, 0), 1), 3)


def calc_sma_status(prices):
    """SMA50 / SMA200 のステータス判定"""
    if prices is None or len(prices) < 200:
        return {"sma50_above_price": None, "golden_cross": None, "death_cross": None}

    sma50 = prices.rolling(50).mean()
    sma200 = prices.rolling(200).mean()
    current = prices.iloc[-1]

    sma50_current = sma50.iloc[-1]
    sma200_current = sma200.iloc[-1]
    sma50_prev = sma50.iloc[-5] if len(sma50) > 5 else sma50_current
    sma200_prev = sma200.iloc[-5] if len(sma200) > 5 else sma200_current

    return {
        "price_vs_sma50": round(((current / sma50_current) - 1) * 100, 2) if sma50_current else None,
        "price_vs_sma200": round(((current / sma200_current) - 1) * 100, 2) if sma200_current else None,
        "sma50_above_sma200": bool(sma50_current > sma200_current),
        "trend": "上昇トレンド" if sma50_current > sma200_current else "下降トレンド",
        "golden_cross_recent": bool(sma50_prev <= sma200_prev and sma50_current > sma200_current),
        "death_cross_recent": bool(sma50_prev >= sma200_prev and sma50_current < sma200_current),
    }


def calc_change_score(ticker: yf.Ticker):
    """
    変化スコア（アルファスコア）: 業績改善の方向性を定量化
    - アクルーアルズ（利益の質）
    - 売上加速度
    - FCFマージン変化
    - ROE趨勢
    各0〜25点、合計100点満点。50以上で「改善傾向」。
    """
    result = {"total": None, "components": {}, "interpretation": None}

    try:
        # 年次財務データ取得
        income = ticker.financials
        balance = ticker.balance_sheet
        cashflow = ticker.cashflow

        if income is None or income.empty or len(income.columns) < 2:
            result["interpretation"] = "財務データ不足（2期分必要）"
            return result

        scores = {}

        # 1. アクルーアルズ（利益の質）: 営業CFと純利益の乖離
        # 営業CF / 純利益 が高いほど利益の質が高い
        try:
            net_income = income.loc["Net Income"].iloc[0] if "Net Income" in income.index else None
            operating_cf = cashflow.loc["Operating Cash Flow"].iloc[0] if cashflow is not None and "Operating Cash Flow" in cashflow.index else None

            if net_income and operating_cf and net_income != 0:
                accrual_ratio = operating_cf / abs(net_income)
                # 1.0以上が良好、1.5以上が非常に良好
                if accrual_ratio >= 1.5:
                    scores["accruals"] = 25
                elif accrual_ratio >= 1.0:
                    scores["accruals"] = 20
                elif accrual_ratio >= 0.7:
                    scores["accruals"] = 15
                elif accrual_ratio >= 0.5:
                    scores["accruals"] = 10
                else:
                    scores["accruals"] = 5
                scores["accruals_detail"] = f"営業CF/純利益 = {accrual_ratio:.2f}"
            else:
                scores["accruals"] = None
                scores["accruals_detail"] = "データ不足"
        except Exception:
            scores["accruals"] = None
            scores["accruals_detail"] = "計算エラー"

        # 2. 売上加速度: 直近の売上成長率 vs 前期の売上成長率
        try:
            revenues = income.loc["Total Revenue"] if "Total Revenue" in income.index else None
            if revenues is not None and len(revenues) >= 3:
                rev_latest = revenues.iloc[0]
                rev_prev = revenues.iloc[1]
                rev_prev2 = revenues.iloc[2]

                if rev_prev and rev_prev2 and rev_prev != 0 and rev_prev2 != 0:
                    growth_latest = (rev_latest - rev_prev) / abs(rev_prev)
                    growth_prev = (rev_prev - rev_prev2) / abs(rev_prev2)
                    acceleration = growth_latest - growth_prev

                    if acceleration > 0.05:
                        scores["revenue_accel"] = 25
                    elif acceleration > 0.02:
                        scores["revenue_accel"] = 20
                    elif acceleration > 0:
                        scores["revenue_accel"] = 15
                    elif acceleration > -0.03:
                        scores["revenue_accel"] = 10
                    else:
                        scores["revenue_accel"] = 5
                    scores["revenue_accel_detail"] = f"売上成長 {growth_latest:.1%} → 加速度 {acceleration:+.1%}"
                else:
                    scores["revenue_accel"] = None
                    scores["revenue_accel_detail"] = "データ不足"
            else:
                scores["revenue_accel"] = None
                scores["revenue_accel_detail"] = "3期分のデータ不足"
        except Exception:
            scores["revenue_accel"] = None
            scores["revenue_accel_detail"] = "計算エラー"

        # 3. FCFマージン変化
        try:
            if cashflow is not None and len(cashflow.columns) >= 2:
                fcf_rows = ["Free Cash Flow"]
                op_cf_rows = ["Operating Cash Flow"]
                capex_rows = ["Capital Expenditure"]

                def get_fcf(col_idx):
                    if "Free Cash Flow" in cashflow.index:
                        return cashflow.loc["Free Cash Flow"].iloc[col_idx]
                    elif "Operating Cash Flow" in cashflow.index and "Capital Expenditure" in cashflow.index:
                        return cashflow.loc["Operating Cash Flow"].iloc[col_idx] + cashflow.loc["Capital Expenditure"].iloc[col_idx]
                    return None

                fcf_latest = get_fcf(0)
                fcf_prev = get_fcf(1)
                rev_latest = income.loc["Total Revenue"].iloc[0] if "Total Revenue" in income.index else None
                rev_prev = income.loc["Total Revenue"].iloc[1] if "Total Revenue" in income.index and len(income.columns) >= 2 else None

                if all(v is not None and v != 0 for v in [fcf_latest, fcf_prev, rev_latest, rev_prev]):
                    margin_latest = fcf_latest / rev_latest
                    margin_prev = fcf_prev / rev_prev
                    margin_change = margin_latest - margin_prev

                    if margin_change > 0.03:
                        scores["fcf_margin"] = 25
                    elif margin_change > 0.01:
                        scores["fcf_margin"] = 20
                    elif margin_change > 0:
                        scores["fcf_margin"] = 15
                    elif margin_change > -0.02:
                        scores["fcf_margin"] = 10
                    else:
                        scores["fcf_margin"] = 5
                    scores["fcf_margin_detail"] = f"FCFマージン変化 {margin_change:+.1%}"
                else:
                    scores["fcf_margin"] = None
                    scores["fcf_margin_detail"] = "データ不足"
            else:
                scores["fcf_margin"] = None
                scores["fcf_margin_detail"] = "キャッシュフロー不足"
        except Exception:
            scores["fcf_margin"] = None
            scores["fcf_margin_detail"] = "計算エラー"

        # 4. ROE趨勢
        try:
            if len(income.columns) >= 2 and balance is not None and len(balance.columns) >= 2:
                ni_latest = income.loc["Net Income"].iloc[0] if "Net Income" in income.index else None
                ni_prev = income.loc["Net Income"].iloc[1] if "Net Income" in income.index else None
                eq_latest = balance.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in balance.index else None
                eq_prev = balance.loc["Stockholders Equity"].iloc[1] if "Stockholders Equity" in balance.index else None

                if all(v is not None and v != 0 for v in [ni_latest, ni_prev, eq_latest, eq_prev]):
                    roe_latest = ni_latest / eq_latest
                    roe_prev = ni_prev / eq_prev
                    roe_change = roe_latest - roe_prev

                    if roe_change > 0.03:
                        scores["roe_trend"] = 25
                    elif roe_change > 0.01:
                        scores["roe_trend"] = 20
                    elif roe_change > 0:
                        scores["roe_trend"] = 15
                    elif roe_change > -0.02:
                        scores["roe_trend"] = 10
                    else:
                        scores["roe_trend"] = 5
                    scores["roe_trend_detail"] = f"ROE変化 {roe_change:+.1%}（{roe_prev:.1%} → {roe_latest:.1%}）"
                else:
                    scores["roe_trend"] = None
                    scores["roe_trend_detail"] = "データ不足"
            else:
                scores["roe_trend"] = None
                scores["roe_trend_detail"] = "データ不足"
        except Exception:
            scores["roe_trend"] = None
            scores["roe_trend_detail"] = "計算エラー"

        # 合計スコア算出
        valid_scores = [v for k, v in scores.items() if not k.endswith("_detail") and v is not None]
        if valid_scores:
            # Noneの指標は平均値で補完
            avg = sum(valid_scores) / len(valid_scores)
            total_components = 4
            total = sum(valid_scores) + avg * (total_components - len(valid_scores))
            result["total"] = round(total, 1)

            if total >= 75:
                result["interpretation"] = "強い改善トレンド 📈"
            elif total >= 50:
                result["interpretation"] = "改善傾向あり ↗️"
            elif total >= 35:
                result["interpretation"] = "横ばい ➡️"
            else:
                result["interpretation"] = "悪化傾向 📉"

        result["components"] = scores

    except Exception as e:
        result["interpretation"] = f"変化スコア計算エラー: {str(e)}"

    return result


def fetch_stock_data(code: str, full: bool = False) -> dict:
    """
    銘柄コードからyfinanceでデータを取得しJSON構造で返す。

    Args:
        code: 4桁の銘柄コード（例: "7203"）
        full: Trueで変化スコア・テクニカル分析を含むフル取得
    """
    ticker_symbol = f"{code}.T"
    ticker = yf.Ticker(ticker_symbol)

    try:
        info = ticker.info
    except Exception as e:
        return {"error": f"銘柄 {code} のデータ取得に失敗: {str(e)}", "status": "fetch_error"}

    if not info or info.get("regularMarketPrice") is None:
        return {"error": f"銘柄 {code} が見つかりません", "status": "not_found"}

    # ===== 基本情報 =====
    data = {
        "status": "success",
        "fetched_at": datetime.now().isoformat(),
        "ticker": ticker_symbol,
        "code": code,
        "company": {
            "name": safe_get(info, "longName") or safe_get(info, "shortName", "不明"),
            "sector": safe_get(info, "sector", "不明"),
            "industry": safe_get(info, "industry", "不明"),
            "market_cap": safe_get(info, "marketCap"),
            "employee_count": safe_get(info, "fullTimeEmployees"),
            "website": safe_get(info, "website"),
            "description": safe_get(info, "longBusinessSummary"),
        },
        "price": {
            "current": safe_get(info, "regularMarketPrice"),
            "previous_close": safe_get(info, "previousClose"),
            "day_high": safe_get(info, "dayHigh"),
            "day_low": safe_get(info, "dayLow"),
            "fifty_two_week_high": safe_get(info, "fiftyTwoWeekHigh"),
            "fifty_two_week_low": safe_get(info, "fiftyTwoWeekLow"),
            "volume": safe_get(info, "volume"),
        },
        "valuation": {
            "per": sanitize_ratio(safe_get(info, "trailingPE"), 0, 500),
            "forward_per": sanitize_ratio(safe_get(info, "forwardPE"), 0, 500),
            "pbr": sanitize_ratio(safe_get(info, "priceToBook"), 0, 100),
            "psr": sanitize_ratio(safe_get(info, "priceToSalesTrailing12Months"), 0, 100),
            "ev_ebitda": sanitize_ratio(safe_get(info, "enterpriseToEbitda"), 0, 200),
        },
        "fundamentals": {
            "roe": None,
            "roa": safe_get(info, "returnOnAssets"),
            "profit_margin": safe_get(info, "profitMargins"),
            "operating_margin": safe_get(info, "operatingMargins"),
            "revenue": safe_get(info, "totalRevenue"),
            "revenue_growth": safe_get(info, "revenueGrowth"),
            "earnings_growth": safe_get(info, "earningsGrowth"),
            "debt_to_equity": safe_get(info, "debtToEquity"),
        },
        "dividend": {
            "yield": safe_get(info, "dividendYield"),
            "rate": safe_get(info, "dividendRate"),
            "payout_ratio": safe_get(info, "payoutRatio"),
        },
        "analyst": {
            "target_high": safe_get(info, "targetHighPrice"),
            "target_mean": safe_get(info, "targetMeanPrice"),
            "target_low": safe_get(info, "targetLowPrice"),
            "target_median": safe_get(info, "targetMedianPrice"),
            "recommendation": safe_get(info, "recommendationKey"),
            "number_of_analysts": safe_get(info, "numberOfAnalystOpinions"),
        },
    }

    # ROE = returnOnEquity（yfinanceで直接取れる場合）
    roe_val = safe_get(info, "returnOnEquity")
    if roe_val is not None:
        data["fundamentals"]["roe"] = round(roe_val, 4)

    # 自己資本比率の概算 (yfinanceに直接のフィールドがないため計算)
    try:
        bs = ticker.balance_sheet
        if bs is not None and not bs.empty:
            total_assets = bs.loc["Total Assets"].iloc[0] if "Total Assets" in bs.index else None
            equity = bs.loc["Stockholders Equity"].iloc[0] if "Stockholders Equity" in bs.index else None
            if total_assets and equity and total_assets != 0:
                data["fundamentals"]["equity_ratio"] = round(equity / total_assets, 4)
    except Exception:
        pass

    # ===== フル取得（テクニカル + 変化スコア） =====
    if full:
        try:
            hist = ticker.history(period="1y")
            if hist is not None and not hist.empty:
                close = hist["Close"]
                data["technical"] = {
                    "rsi_14": calc_rsi(close, 14),
                    "bollinger_position": calc_bollinger_position(close, 20),
                    "sma_status": calc_sma_status(close),
                    "return_1m": round(((close.iloc[-1] / close.iloc[-21]) - 1) * 100, 2) if len(close) > 21 else None,
                    "return_3m": round(((close.iloc[-1] / close.iloc[-63]) - 1) * 100, 2) if len(close) > 63 else None,
                    "return_6m": round(((close.iloc[-1] / close.iloc[-126]) - 1) * 100, 2) if len(close) > 126 else None,
                    "return_1y": round(((close.iloc[-1] / close.iloc[0]) - 1) * 100, 2) if len(close) > 1 else None,
                    "volatility_30d": round(close.pct_change().tail(30).std() * (252 ** 0.5) * 100, 2) if len(close) > 30 else None,
                }
        except Exception as e:
            data["technical"] = {"error": str(e)}

        # 変化スコア
        data["change_score"] = calc_change_score(ticker)

        # アナリスト推奨の3シナリオ推定利回り
        current = data["price"]["current"]
        target_high = data["analyst"]["target_high"]
        target_mean = data["analyst"]["target_mean"]
        target_low = data["analyst"]["target_low"]
        n_analysts = data["analyst"]["number_of_analysts"] or 0

        if current and target_mean:
            # アナリスト少数時のスプレッド拡張
            if n_analysts < 3 and target_high == target_low:
                spread = current * 0.15
                target_high = target_mean + spread
                target_low = target_mean - spread

            data["estimated_return"] = {
                "optimistic": round(((target_high / current) - 1) * 100, 1) if target_high else None,
                "base": round(((target_mean / current) - 1) * 100, 1),
                "pessimistic": round(((target_low / current) - 1) * 100, 1) if target_low else None,
                "analyst_count": n_analysts,
                "note": "アナリスト少数のためスプレッド拡張済み" if n_analysts < 3 else None,
            }

    return data


def main():
    parser = argparse.ArgumentParser(description="yfinanceで日本株データを取得")
    parser.add_argument("code", help="4桁の銘柄コード（例: 7203）")
    parser.add_argument("--full", action="store_true", help="変化スコア・テクニカル含むフル取得")
    parser.add_argument("--pretty", action="store_true", help="整形済みJSON出力")
    args = parser.parse_args()

    # 銘柄コードの正規化（.Tが付いていたら除去）
    code = args.code.replace(".T", "").strip()

    data = fetch_stock_data(code, full=args.full)

    indent = 2 if args.pretty else None
    print(json.dumps(data, ensure_ascii=False, indent=indent, default=str))


if __name__ == "__main__":
    main()
