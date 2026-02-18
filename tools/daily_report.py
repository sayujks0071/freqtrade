#!/usr/bin/env python3
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
import sys
import os

def main():
    db_path = "user_data/tradesv3.sqlite"
    if not os.path.exists(db_path):
        print("No database found.")
        sys.exit(0)

    conn = sqlite3.connect(db_path)

    # Query trades
    # Ensure columns exist. 'is_short' might be present.
    try:
        # Just check connection and basic select
        pd.read_sql_query("SELECT 1", conn)
    except:
        print("Error checking DB connection.")
        sys.exit(1)

    query = "SELECT * FROM trades"

    try:
        df = pd.read_sql_query(query, conn)
    except Exception as e:
        print(f"Error reading database: {e}")
        sys.exit(1)
    finally:
        conn.close()

    if df.empty:
        print("No trades found.")
        sys.exit(0)

    # Convert dates
    df['open_date'] = pd.to_datetime(df['open_date'])
    df['close_date'] = pd.to_datetime(df['close_date'])

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Filter closed trades today
    if 'is_open' in df.columns:
        daily_trades = df[(df['close_date'] >= today_start) & (df['is_open'] == 0)].copy()
    else:
        # Fallback if is_open missing (unlikely)
        daily_trades = df[(df['close_date'] >= today_start)].copy()

    if daily_trades.empty:
        print("No closed trades today.")
        sys.exit(0)

    timestamp = now.strftime("%Y%m%d")
    report_file = f"user_data/reports/daily_summary_{timestamp}.md"

    total_trades = len(daily_trades)
    wins = len(daily_trades[daily_trades['close_profit'] > 0])
    winrate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl_abs = daily_trades['close_profit_abs'].sum()
    avg_profit_pct = daily_trades['close_profit'].mean() * 100 if total_trades > 0 else 0

    daily_trades = daily_trades.sort_values('close_date')
    daily_trades['cum_pnl'] = daily_trades['close_profit_abs'].cumsum()
    peak = daily_trades['cum_pnl'].cummax()
    drawdown = daily_trades['cum_pnl'] - peak
    max_dd = drawdown.min() if not drawdown.empty else 0

    top_pairs = daily_trades.groupby('pair')['close_profit_abs'].sum().sort_values(ascending=False).head(5)
    top_reasons = daily_trades['exit_reason'].value_counts().head(5) if 'exit_reason' in daily_trades.columns else pd.Series()

    with open(report_file, 'w') as f:
        f.write(f"# Daily Trading Summary: {timestamp}\n\n")
        f.write(f"- **Total Trades:** {total_trades}\n")
        f.write(f"- **Win Rate:** {winrate:.2f}%\n")
        f.write(f"- **Total PnL:** {total_pnl_abs:.2f} USD\n")
        f.write(f"- **Avg Profit:** {avg_profit_pct:.2f}%\n")
        f.write(f"- **Max Drawdown (Intraday Realized):** {max_dd:.2f} USD\n\n")

        f.write("## Top Pairs (PnL)\n")
        for pair, pnl in top_pairs.items():
            f.write(f"- {pair}: {pnl:.2f}\n")

        if not top_reasons.empty:
            f.write("\n## Exit Reasons\n")
            for reason, count in top_reasons.items():
                f.write(f"- {reason}: {count}\n")

        f.write("\n## Recent Trades\n")
        f.write("| Pair | Side | Reason | Profit % | PnL |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for _, row in daily_trades.tail(10).iterrows():
            side = "Short" if row.get('is_short') else "Long"
            reason = row.get('exit_reason', 'N/A')
            f.write(f"| {row['pair']} | {side} | {reason} | {row['close_profit']*100:.2f}% | {row['close_profit_abs']:.2f} |\n")

    print(f"Report generated: {report_file}")

if __name__ == "__main__":
    main()
