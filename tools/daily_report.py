#!/usr/bin/env python3
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


# Simple report generator reading directly from sqlite for speed/independence
# usage: python tools/daily_report.py [db_path]


def get_db_path():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return "user_data/tradesv3.sqlite"


def generate_report(db_path):
    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Time range: Last 24h
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(days=1)

    try:
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cursor.fetchone():
            print("No trades table found (fresh db?)")
            return

        cursor.execute("SELECT * FROM trades WHERE is_open=0 ORDER BY close_date DESC")
        trades = cursor.fetchall()
    except Exception as e:
        print(f"Error querying trades: {e}")
        return

    todays_trades = []
    for t in trades:
        # Assuming close_date is text ISO
        c_date_str = t["close_date"]
        if not c_date_str:
            continue

        try:
            # Handle potential variations
            # Freqtrade often stores as '2023-01-01 12:00:00.000000'
            # Simple check if it matches YYYY-MM-DD
            c_date = datetime.fromisoformat(c_date_str)
            if c_date.tzinfo is None:
                c_date = c_date.replace(tzinfo=timezone.utc)

            if c_date >= start_time:
                todays_trades.append(t)
        except ValueError:
            continue

    # Stats
    count = len(todays_trades)
    wins = len([t for t in todays_trades if t["profit_ratio"] > 0])
    winrate = (wins / count * 100) if count > 0 else 0.0
    total_profit_abs = sum([t["profit_abs"] for t in todays_trades])
    avg_profit_ratio = (
        (sum([t["profit_ratio"] for t in todays_trades]) / count) if count > 0 else 0.0
    )

    # Best/Worst
    sorted_trades = sorted(todays_trades, key=lambda x: x["profit_ratio"], reverse=True)
    best = sorted_trades[0] if sorted_trades else None
    worst = sorted_trades[-1] if sorted_trades else None

    # Markdown output
    report = f"""# Daily Trading Report
Date: {now.strftime("%Y-%m-%d")} (Last 24h)

## Summary
- **Trades:** {count}
- **Win Rate:** {winrate:.2f}%
- **Total PnL:** {total_profit_abs:.2f}
- **Avg Return:** {avg_profit_ratio:.2%}

## Top Performers
- **Best:** {best["pair"] if best else "N/A"} ({best["profit_ratio"]:.2%} / {best["profit_abs"]:.2f})
- **Worst:** {worst["pair"] if worst else "N/A"} ({worst["profit_ratio"]:.2%} / {worst["profit_abs"]:.2f})

## Recent Trades
| Pair | Side | Profit % | Profit Abs | Exit Reason | Time |
|---|---|---|---|---|---|
"""

    # Safely get fields (handling potential schema changes/missing fields)
    for t in todays_trades[:20]:  # Show last 20
        pair = t["pair"]
        direction = t["trade_direction"] if "trade_direction" in t.keys() else "long"
        p_ratio = t["profit_ratio"]
        p_abs = t["profit_abs"]
        reason = t["exit_reason"]
        time = t["close_date"]
        report += (
            f"| {pair} | {direction} | {p_ratio:.2%} | {p_abs:.2f} | {reason} | {time} |\n"
        )

    filename = f"user_data/reports/daily_summary_{now.strftime('%Y%m%d')}.md"
    try:
        with Path(filename).open("w") as f:
            f.write(report)
        print(f"Report generated: {filename}")
    except Exception as e:
        print(f"Error writing report: {e}")

    conn.close()


if __name__ == "__main__":
    generate_report(get_db_path())
