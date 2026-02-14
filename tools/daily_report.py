#!/usr/bin/env python3
import argparse
import os
import sqlite3
from datetime import datetime, timedelta, timezone


def get_db_connection(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_drawdown(trades):
    # Simple drawdown calculation based on cumulative profit
    # This is an approximation as it doesn't account for open trade equity
    cum_profit = 0
    peak = 0
    drawdown = 0

    # Sort by close date
    sorted_trades = sorted(trades, key=lambda x: x["close_date"])

    for t in sorted_trades:
        profit = t["close_profit_abs"] if t["close_profit_abs"] is not None else 0
        cum_profit += profit
        if cum_profit > peak:
            peak = cum_profit
        dd = peak - cum_profit
        if dd > drawdown:
            drawdown = dd

    return drawdown


def main():
    parser = argparse.ArgumentParser(description="Generate Daily Trading Report")
    parser.add_argument("--db", default="user_data/tradesv3.sqlite", help="Path to sqlite DB")
    parser.add_argument("--date", help="Date to report (YYYY-MM-DD), default is yesterday")
    parser.add_argument("--out", help="Output directory", default="user_data/reports")

    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        # Default to yesterday
        target_date = datetime.now(timezone.utc) - timedelta(days=1)
        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    end_date = target_date + timedelta(days=1)

    print(f"Generating report for {target_date.date()}...")

    if not os.path.exists(args.db):
        print(f"Database not found: {args.db}")
        return

    conn = get_db_connection(args.db)

    # Query trades closed on target_date
    # Note: DB dates are usually stored as timestamps or ISO strings depending on version.
    # Freqtrade stores as datetime strings usually.
    # We'll use SQLite date functions if possible or fetch and filter.
    # Assuming standard Freqtrade schema where close_date is datetime string.

    query = """
    SELECT * FROM trades
    WHERE is_open = 0
    AND close_date >= ?
    AND close_date < ?
    """

    params = (
        target_date.strftime("%Y-%m-%d %H:%M:%S"),
        end_date.strftime("%Y-%m-%d %H:%M:%S"),
    )

    try:
        cursor = conn.execute(query, params)
        trades = [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"Error querying DB: {e}")
        return
    finally:
        conn.close()

    total_trades = len(trades)
    if total_trades == 0:
        print("No trades found for this date.")
        # Generate empty report?
        report_content = f"# Daily Summary: {target_date.date()}\n\nNo trades recorded."
    else:
        wins = [t for t in trades if (t["close_profit"] or 0) > 0]
        losses = [t for t in trades if (t["close_profit"] or 0) <= 0]

        win_rate = len(wins) / total_trades if total_trades > 0 else 0

        total_profit_abs = sum((t["close_profit_abs"] or 0) for t in trades)
        avg_profit_pct = (
            sum((t["close_profit"] or 0) for t in trades) / total_trades if total_trades > 0 else 0
        )

        drawdown = calculate_drawdown(trades)

        # Top pairs
        pair_stats = {}
        for t in trades:
            pair = t["pair"]
            profit = t["close_profit_abs"] or 0
            if pair not in pair_stats:
                pair_stats[pair] = {"count": 0, "profit": 0}
            pair_stats[pair]["count"] += 1
            pair_stats[pair]["profit"] += profit

        top_pairs = sorted(pair_stats.items(), key=lambda x: x[1]["profit"], reverse=True)[:5]

        # Exit reasons
        reasons = {}
        for t in trades:
            reason = t["exit_reason"] or t.get("sell_reason", "unknown")
            reasons[reason] = reasons.get(reason, 0) + 1

        report_content = f"""# Daily Summary: {target_date.date()}

## Overview
- **Date**: {target_date.date()}
- **Total Trades**: {total_trades}
- **Win Rate**: {win_rate:.2%} ({len(wins)}W / {len(losses)}L)
- **Total PnL (Abs)**: {total_profit_abs:.2f}
- **Avg Return**: {avg_profit_pct:.2%}
- **Max Drawdown (Daily)**: {drawdown:.2f}

## Top Pairs (by PnL)
| Pair | Trades | PnL |
| :--- | :--- | :--- |
"""
        for pair, stats in top_pairs:
            report_content += f"| {pair} | {stats['count']} | {stats['profit']:.2f} |\n"

        report_content += "\n## Exit Reasons\n"
        for reason, count in reasons.items():
            report_content += f"- **{reason}**: {count}\n"

    # Write report
    outfile = os.path.join(
        args.out, f"daily_summary_{target_date.strftime('%Y%m%d')}.md"
    )
    os.makedirs(args.out, exist_ok=True)
    with open(outfile, "w") as f:
        f.write(report_content)

    print(f"Report written to {outfile}")


if __name__ == "__main__":
    main()
