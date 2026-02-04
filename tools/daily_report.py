#!/usr/bin/env python3
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd


def generate_daily_report(db_path, date_str, output_file):
    if not os.path.exists(db_path):
        print(f"No database found at {db_path}")
        # Write empty report to avoid workflow errors
        with open(output_file, "w") as f:
            f.write(f"# Daily Report for {date_str}\n\nNo database found.")
        return

    conn = sqlite3.connect(db_path)

    try:
        query = "SELECT * FROM trades"
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading DB: {e}")
        return
    finally:
        conn.close()

    if df.empty:
        print("No trades found in DB.")
        with open(output_file, "w") as f:
            f.write(f"# Daily Report for {date_str}\n\nNo trades found in DB.")
        return

    # Ensure date columns are datetime
    # Freqtrade stores dates as strings usually? Or timestamps?
    # If read_sql_query doesn't parse, we force it.
    if "open_date" in df.columns:
        df["open_date"] = pd.to_datetime(df["open_date"])
    if "close_date" in df.columns:
        df["close_date"] = pd.to_datetime(df["close_date"])

    # Filter by date
    try:
        target_date = pd.to_datetime(date_str).date()
    except ValueError:
        print(f"Invalid date format {date_str}")
        return

    # Trades CLOSED on this date
    daily_closed = (
        df[df["close_date"].dt.date == target_date]
        if "close_date" in df.columns
        else pd.DataFrame()
    )

    # Trades OPENED on this date
    daily_opened = (
        df[df["open_date"].dt.date == target_date] if "open_date" in df.columns else pd.DataFrame()
    )

    # Metrics
    total_trades = len(daily_closed)
    wins = len(daily_closed[daily_closed["close_profit"] > 0]) if not daily_closed.empty else 0
    losses = len(daily_closed[daily_closed["close_profit"] <= 0]) if not daily_closed.empty else 0
    winrate = (wins / total_trades * 100) if total_trades > 0 else 0

    total_profit_abs = (
        daily_closed["close_profit_abs"].sum()
        if not daily_closed.empty and "close_profit_abs" in daily_closed
        else 0
    )
    avg_return = daily_closed["close_profit"].mean() * 100 if total_trades > 0 else 0

    # Max Loss Trade
    max_loss_trade = daily_closed["close_profit"].min() * 100 if not daily_closed.empty else 0

    # Top Pairs
    if not daily_closed.empty and "close_profit_abs" in daily_closed:
        top_pairs = (
            daily_closed.groupby("pair")["close_profit_abs"]
            .sum()
            .sort_values(ascending=False)
            .head(5)
        )
    else:
        top_pairs = pd.Series()

    # Report Content
    lines = []
    lines.append(f"# Daily Report for {date_str} (UTC)")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- **Trades Closed**: {total_trades}")
    lines.append(f"- **Win Rate**: {winrate:.2f}% ({wins} W / {losses} L)")
    lines.append(f"- **Total PnL**: {total_profit_abs:.2f}")
    lines.append(f"- **Avg Return**: {avg_return:.2f}%")
    lines.append(f"- **Max Loss Trade**: {max_loss_trade:.2f}%")
    lines.append("")
    lines.append("## Top Pairs (PnL)")
    if not top_pairs.empty:
        for pair, pnl in top_pairs.items():
            lines.append(f"- {pair}: {pnl:.2f}")
    else:
        lines.append("No trades closed.")

    lines.append("")
    lines.append("## Trades Opened Today")
    lines.append(f"- Count: {len(daily_opened)}")
    if not daily_opened.empty:
        for _, row in daily_opened.iterrows():
            lines.append(f"- {row['pair']} @ {row['open_rate']}")

    with open(output_file, "w") as f:
        f.write("\n".join(lines))

    print(f"Report generated at {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="user_data/tradesv3.sqlite")
    parser.add_argument(
        "--date", help="YYYY-MM-DD", default=datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    parser.add_argument("--output")

    args = parser.parse_args()

    out = args.output if args.output else f"user_data/reports/daily_summary_{args.date}.md"
    generate_daily_report(args.db, args.date, out)
