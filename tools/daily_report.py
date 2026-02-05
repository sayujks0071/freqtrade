#!/usr/bin/env python3
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# noqa: C901

DB_PATH = "user_data/tradesv3.sqlite"
REPORT_DIR = "user_data/reports"

def get_db_connection():
    if not Path(DB_PATH).exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(0)
    return sqlite3.connect(DB_PATH)

def generate_daily_report():  # noqa: C901
    conn = get_db_connection()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # UTC Date
    today = datetime.now(timezone.utc).date()

    # Optional: Arg for date
    target_date = today
    if len(sys.argv) > 1:
        try:
            target_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            pass

    start_ts = datetime.combine(target_date, datetime.min.time())
    end_ts = start_ts + timedelta(days=1)

    print(f"Generating report for {target_date}...")

    # Query Trades - handling naive datetime storage in sqlite
    # We fetch broadly and filter in python to be safe with timezone formats

    query = "SELECT * FROM trades WHERE is_open = 0"

    cursor.execute(query)
    trades_raw = cursor.fetchall()

    trades = []
    for t in trades_raw:
        # Parse close_date
        cd_str = t['close_date']
        if not cd_str:
            continue

        try:
            # Freqtrade often stores as "YYYY-MM-DD HH:MM:SS.mmmmmm"
            # It might be naive UTC.
            if isinstance(cd_str, str):
                cd = datetime.fromisoformat(cd_str)
            else:
                cd = cd_str # Already datetime?

            # If naive, assume UTC
            if cd.tzinfo is None:
                cd = cd.replace(tzinfo=timezone.utc) # noqa: UP017

            if start_ts.replace(tzinfo=timezone.utc) <= cd < end_ts.replace(tzinfo=timezone.utc):
                trades.append(t)
        except Exception:
            continue

    total_trades = len(trades)
    wins = 0
    losses = 0
    total_profit_abs = 0.0
    volume = 0.0

    pairs_stats = {}
    exit_reasons = {}

    for t in trades:
        # PnL
        # close_profit_abs might be in DB, or calculate
        profit_ratio = t['close_profit'] if 'close_profit' in t.keys() else 0.0
        stake = t['stake_amount'] if 'stake_amount' in t.keys() else 0.0

        # Try to find abs profit
        if 'close_profit_abs' in t.keys() and t['close_profit_abs'] is not None:
            profit_abs = t['close_profit_abs']
        else:
            profit_abs = profit_ratio * stake

        total_profit_abs += profit_abs
        volume += stake

        if profit_abs > 0:
            wins += 1
        else:
            losses += 1

        pair = t['pair']
        if pair not in pairs_stats:
            pairs_stats[pair] = {'count': 0, 'profit': 0.0}
        pairs_stats[pair]['count'] += 1
        pairs_stats[pair]['profit'] += profit_abs

        reason = t['exit_reason'] if 'exit_reason' in t.keys() else 'unknown'
        exit_reasons[reason] = exit_reasons.get(reason, 0) + 1

    winrate = (wins / total_trades * 100) if total_trades > 0 else 0

    # Generate Markdown
    report = f"""# Daily Trading Report - {target_date}

## Summary
- **Total Trades:** {total_trades}
- **Win Rate:** {winrate:.2f}% ({wins} W / {losses} L)
- **Total Profit:** {total_profit_abs:.4f} USDT
- **Volume:** {volume:.2f} USDT

## Top Pairs
| Pair | Trades | Profit |
|---|---|---|
"""

    # Sort pairs by profit
    sorted_pairs = sorted(pairs_stats.items(), key=lambda x: x[1]['profit'], reverse=True)
    for p, stats in sorted_pairs[:5]:
        report += f"| {p} | {stats['count']} | {stats['profit']:.4f} |\n"

    report += "\n## Exit Reasons\n"
    for r, c in exit_reasons.items():
        report += f"- **{r}:** {c}\n"

    # Save
    Path(REPORT_DIR).mkdir(parents=True, exist_ok=True)
    filename = f"{REPORT_DIR}/daily_summary_{target_date}.md"
    with open(filename, 'w') as f:
        f.write(report)

    print(f"Report saved to {filename}")

if __name__ == "__main__":
    generate_daily_report()
