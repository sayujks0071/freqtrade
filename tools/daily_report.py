#!/usr/bin/env python3
"""
Daily Trading Report Generator
Connects to Freqtrade SQLite database and generates a markdown summary.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def setup_args():
    parser = argparse.ArgumentParser(description="Generate Daily Trading Report")
    parser.add_argument("--db-url", default="user_data/tradesv3.sqlite", help="Path to SQLite DB")
    parser.add_argument("--days", type=int, default=1, help="Number of days to look back")
    parser.add_argument("--out", type=Path, help="Output markdown file path")
    return parser.parse_args()


def generate_report(db_path, days, out_path):
    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Calculate time range (UTC)
    now = datetime.now(timezone.utc)  # noqa: UP017
    start_date = now - timedelta(days=days)

    # Query closed trades
    query = """
    SELECT
        pair,
        is_open,
        amount,
        stake_amount,
        open_rate,
        close_rate,
        open_date,
        close_date,
        close_profit,
        close_profit_abs,
        exit_reason,
        strategy
    FROM trades
    WHERE close_date >= ?
    ORDER BY close_date DESC
    """

    cursor.execute(query, (start_date,))
    trades = cursor.fetchall()

    # Analyze
    total_trades = len(trades)
    winning_trades = [t for t in trades if t["close_profit"] > 0]
    losing_trades = [t for t in trades if t["close_profit"] <= 0]

    win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0.0
    total_profit_abs = sum(t["close_profit_abs"] for t in trades if t["close_profit_abs"])
    avg_profit_pct = (
        (sum(t["close_profit"] for t in trades) / total_trades * 100) if total_trades > 0 else 0.0
    )

    # Top Pairs
    pair_stats = {}
    for t in trades:
        pair = t["pair"]
        if pair not in pair_stats:
            pair_stats[pair] = {"count": 0, "profit_abs": 0.0}
        pair_stats[pair]["count"] += 1
        pair_stats[pair]["profit_abs"] += t["close_profit_abs"] or 0.0

    sorted_pairs = sorted(pair_stats.items(), key=lambda x: x[1]["profit_abs"], reverse=True)

    # Top Reasons
    reason_stats = {}
    for t in trades:
        reason = t["exit_reason"]
        reason_stats[reason] = reason_stats.get(reason, 0) + 1

    sorted_reasons = sorted(reason_stats.items(), key=lambda x: x[1], reverse=True)

    # Generate Markdown
    report = []
    report.append(f"# Daily Trading Report ({now.strftime('%Y-%m-%d')})")
    report.append(f"Period: Last {days} days")

    report.append("## Summary")
    report.append(f"- **Total Trades**: {total_trades}")
    report.append(f"- **Win Rate**: {win_rate:.2f}%")
    report.append(f"- **Total Profit**: {total_profit_abs:.2f} USDT")
    report.append(f"- **Avg Return**: {avg_profit_pct:.2f}%")

    report.append("## Top Pairs by Profit")
    report.append("| Pair | Trades | Profit (USDT) |")
    report.append("| --- | --- | --- |")
    for pair, stats in sorted_pairs[:5]:
        report.append(f"| {pair} | {stats['count']} | {stats['profit_abs']:.2f} |")

    report.append("## Exit Reasons")
    for reason, count in sorted_reasons:
        report.append(f"- {reason}: {count}")

    report.append("## Recent Trades")
    report.append("| Date | Pair | Side | Profit % | Profit Abs | Reason |")
    report.append("| --- | --- | --- | --- | --- | --- |")
    for t in trades[:10]:
        p_pct = t["close_profit"] * 100 if t["close_profit"] else 0.0
        p_abs = t["close_profit_abs"] or 0.0
        # Determine side (approximate based on logic or strategy, usually Long for spot/futures unless shorting)
        # Assuming Long for simplicity or generic
        side = "Long/Short"
        date_str = str(t["close_date"]).split(".")[0]
        report.append(
            f"| {date_str} | {t['pair']} | {side} | {p_pct:.2f}% | {p_abs:.2f} | {t['exit_reason']} |"
        )

    content = "\n".join(report)

    if out_path:
        with out_path.open("w") as f:
            f.write(content)
        print(f"Report written to {out_path}")
    else:
        print(content)


if __name__ == "__main__":
    args = setup_args()
    generate_report(args.db_url, args.days, args.out)
