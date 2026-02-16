#!/usr/bin/env python3
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone


def generate_report(db_path, out_path, date_str=None):
    # Ensure output dir exists
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        # Create empty report
        with open(out_path, "w") as f:
            f.write(f"# Daily Trading Report ({date_str or 'Today'})\n\nNo database found.")
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if not date_str:
        target_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    else:
        target_date = date_str

    print(f"Generating report for {target_date}...")

    # Trades table schema in Freqtrade V3:
    # close_date is DATETIME string.
    # exit_reason (or sell_reason in older versions)

    # Check if exit_reason or sell_reason exists
    try:
        cursor.execute("PRAGMA table_info(trades)")
        columns = [row["name"] for row in cursor.fetchall()]
        reason_col = "exit_reason" if "exit_reason" in columns else "sell_reason"
    except Exception:
        reason_col = "exit_reason"

    query = f"""
    SELECT pair, close_profit, close_date, stake_amount, {reason_col}
    FROM trades
    WHERE date(close_date) == ?
    AND is_open = 0
    """

    try:
        cursor.execute(query, (target_date,))
        rows = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Error querying database: {e}")
        rows = []

    conn.close()

    report_lines = [f"# Daily Trading Report: {target_date}"]

    if not rows:
        report_lines.append("\nNo trades closed today.")
    else:
        total_trades = len(rows)
        wins = [r for r in rows if r["close_profit"] > 0]
        # win_rate calculation
        win_rate = len(wins) / total_trades if total_trades > 0 else 0.0

        # Calculate totals
        # close_profit is ratio. PnL = ratio * stake
        total_profit_ratio = sum(r["close_profit"] for r in rows)
        avg_return = total_profit_ratio / total_trades if total_trades > 0 else 0.0

        total_pnl = sum(r["close_profit"] * r["stake_amount"] for r in rows)

        report_lines.append("\n## Summary")
        report_lines.append(f"- **Total Trades**: {total_trades}")
        report_lines.append(f"- **Win Rate**: {win_rate:.2%}")
        report_lines.append(f"- **Avg Return**: {avg_return:.2%}")
        report_lines.append(f"- **Total PnL**: {total_pnl:.4f} (Quote Currency)")

        # Top Pairs
        pair_pnl = {}
        for r in rows:
            pair = r["pair"]
            pnl = r["close_profit"] * r["stake_amount"]
            pair_pnl[pair] = pair_pnl.get(pair, 0) + pnl

        sorted_pairs = sorted(pair_pnl.items(), key=lambda x: x[1], reverse=True)[:5]

        report_lines.append("\n## Top Pairs (PnL)")
        for pair, pnl in sorted_pairs:
            report_lines.append(f"- {pair}: {pnl:.4f}")

        # Exit Reasons
        reasons = {}
        for r in rows:
            reason = r[reason_col]
            reasons[reason] = reasons.get(reason, 0) + 1

        report_lines.append("\n## Exit Reasons")
        for reason, count in sorted(reasons.items(), key=lambda x: x[1], reverse=True):
            report_lines.append(f"- {reason}: {count}")

    with open(out_path, "w") as f:
        f.write("\n".join(report_lines))

    print(f"Report saved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="user_data/tradesv3.sqlite")
    parser.add_argument("--out", default="user_data/reports/daily_summary.md")
    parser.add_argument("--date", help="YYYY-MM-DD (default: today UTC)", default=None)
    args = parser.parse_args()

    generate_report(args.db, args.out, args.date)
