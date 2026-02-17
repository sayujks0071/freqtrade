#!/usr/bin/env python3
"""
daily_report.py

Generates a daily trading report from Freqtrade database.
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

def generate_report(db_path, output_file, lookback_days=1):
    if not os.path.exists(db_path):
        logger.error(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Calculate time range (UTC)
    # Freqtrade stores naive UTC datetime strings: "YYYY-MM-DD HH:MM:SS.ssssss"
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=lookback_days)

    start_str = start_time.strftime("%Y-%m-%d %H:%M:%S")

    query = """
    SELECT
        pair,
        close_profit_abs,
        close_profit,
        stake_amount,
        is_open,
        open_date,
        close_date,
        exit_reason,
        strategy
    FROM trades
    WHERE (close_date >= ? OR (is_open = 1 AND open_date >= ?))
    ORDER BY close_date DESC
    """

    try:
        cursor.execute(query, (start_str, start_str))
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        logger.error(f"Database query failed: {e}. Is the schema correct or DB initialized?")
        return

    # Row mapping:
    # 0: pair
    # 1: close_profit_abs
    # 2: close_profit (pct)
    # 3: stake_amount
    # 4: is_open
    # 5: open_date
    # 6: close_date
    # 7: exit_reason
    # 8: strategy

    closed_trades = [r for r in rows if r[4] == 0]
    open_trades = [r for r in rows if r[4] == 1]

    total_trades = len(closed_trades)
    wins = [r for r in closed_trades if (r[2] is not None and r[2] > 0)]
    losses = [r for r in closed_trades if (r[2] is not None and r[2] <= 0)]

    total_pnl = sum((r[1] if r[1] is not None else 0.0) for r in closed_trades)
    win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0

    # Markdown Report
    lines = []
    lines.append(f"# Daily Trading Report ({datetime.now(timezone.utc).date()})")
    lines.append(f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"**Period**: Last {lookback_days} days (Since {start_str} UTC)")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- **Total Closed Trades**: {total_trades}")
    lines.append(f"- **Win Rate**: {win_rate:.2f}% ({len(wins)} W / {len(losses)} L)")
    lines.append(f"- **Total PnL**: {total_pnl:.4f} USDT")
    lines.append(f"- **Open Trades**: {len(open_trades)}")
    lines.append("")

    if closed_trades:
        lines.append("## Closed Trades")
        lines.append("| Pair | PnL (Abs) | PnL (%) | Reason | Time |")
        lines.append("|---|---|---|---|---|")
        for r in closed_trades:
            pair = r[0]
            pnl_abs = r[1] if r[1] is not None else 0.0
            pnl_pct = (r[2] * 100) if r[2] is not None else 0.0
            reason = r[7] if r[7] else "N/A"
            close_date = r[6]
            lines.append(f"| {pair} | {pnl_abs:.4f} | {pnl_pct:.2f}% | {reason} | {close_date} |")
        lines.append("")

    if open_trades:
        lines.append("## Open Trades")
        lines.append("| Pair | Open Time | Stake | Strategy |")
        lines.append("|---|---|---|---|")
        for r in open_trades:
            pair = r[0]
            open_date = r[5]
            stake = r[3]
            strategy = r[8]
            lines.append(f"| {pair} | {open_date} | {stake:.2f} | {strategy} |")
        lines.append("")

    try:
        with open(output_file, "w") as f:
            f.write("\n".join(lines))
        logger.info(f"Report generated at {output_file}")
    except Exception as e:
        logger.error(f"Failed to write report: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Daily Report")
    parser.add_argument("--db", default="user_data/tradesv3.sqlite", help="Path to database")
    parser.add_argument(
        "--out",
        default=f"user_data/reports/daily_report_{datetime.now().date()}.md",
        help="Output file",
    )
    parser.add_argument("--days", type=int, default=1, help="Lookback days")
    args = parser.parse_args()

    generate_report(args.db, args.out, args.days)
