#!/usr/bin/env python3
import sqlite3
import pandas as pd
from datetime import datetime, timezone, timedelta
import os
import sys

DB_URL = "user_data/tradesv3.sqlite"
REPORT_DIR = "user_data/reports"

def generate_report():
    if not os.path.exists(DB_URL):
        print(f"Database not found at {DB_URL}")
        return

    try:
        conn = sqlite3.connect(DB_URL)

        # Calculate start of day (UTC)
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        query = f"""
        SELECT pair, close_date, close_profit_abs, close_profit, stake_amount, exit_reason
        FROM trades
        WHERE close_date >= '{start_of_day.isoformat()}'
        """

        df = pd.read_sql_query(query, conn)
        conn.close()

        date_str = now.strftime("%Y-%m-%d")
        report_file = os.path.join(REPORT_DIR, f"daily_summary_{date_str}.md")

        os.makedirs(REPORT_DIR, exist_ok=True)

        with open(report_file, "w") as f:
            f.write(f"# Daily Trading Summary - {date_str}\n\n")

            if df.empty:
                f.write("No closed trades today.\n")
                print(f"Report written to {report_file} (Empty)")
                return

            total_trades = len(df)
            total_pnl = df["close_profit_abs"].sum()
            avg_profit_pct = df["close_profit"].mean() * 100

            wins = df[df["close_profit"] > 0]
            win_rate = (len(wins) / total_trades) * 100

            f.write(f"- **Total Trades:** {total_trades}\n")
            f.write(f"- **Total PnL:** {total_pnl:.2f} USDT\n")
            f.write(f"- **Win Rate:** {win_rate:.2f}%\n")
            f.write(f"- **Avg Profit:** {avg_profit_pct:.2f}%\n\n")

            f.write("## Top Pairs\n\n")
            pair_stats = df.groupby("pair")["close_profit_abs"].sum().sort_values(ascending=False).head(5)
            for pair, pnl in pair_stats.items():
                 f.write(f"- **{pair}:** {pnl:.2f} USDT\n")

            f.write("\n## Exit Reasons\n\n")
            reasons = df["exit_reason"].value_counts()
            for reason, count in reasons.items():
                f.write(f"- **{reason}:** {count}\n")

        print(f"Report written to {report_file}")

    except Exception as e:
        print(f"Error generating report: {e}")

if __name__ == "__main__":
    generate_report()
