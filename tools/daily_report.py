"""
Daily Report Generator
Generates a markdown summary of trading activity for the day.
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from freqtrade.configuration import Configuration
from freqtrade.misc import parse_db_uri_for_logging
from freqtrade.persistence import Trade, init_db


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, required=True, help="Path to config file")
    parser.add_argument("--days", type=int, default=1, help="Number of days to report on")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("user_data/reports"),
        help="Output directory",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default="sqlite:///user_data/tradesv3.sqlite",
        help="Database URL",
    )
    args = parser.parse_args()

    # Load Config
    config = Configuration({"config": [args.config]}).get_config()

    # Override/Set DB URL
    if args.db_url:
        config["db_url"] = args.db_url
    elif "db_url" not in config:
        config["db_url"] = "sqlite:///user_data/tradesv3.sqlite"

    # Init DB
    logger.info(f"Using DB: {parse_db_uri_for_logging(config['db_url'])}")
    init_db(config["db_url"])

    # Date Range (UTC)
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=args.days)

    logger.info(f"Generating report for {start_date} to {end_date}...")

    # Query Trades
    trades = Trade.get_trades(
        [
            Trade.close_date >= start_date,
            Trade.close_date <= end_date,
            Trade.is_open.is_(False),
        ]
    ).all()

    open_trades = Trade.get_trades([Trade.is_open.is_(True)]).all()

    # Calculate Stats
    total_trades = len(trades)
    winning_trades = [t for t in trades if t.close_profit >= 0]
    # losing_trades = [t for t in trades if t.close_profit < 0]

    winrate = (len(winning_trades) / total_trades) if total_trades > 0 else 0.0
    total_profit_abs = sum((t.close_profit_abs or 0.0) for t in trades)
    avg_profit_pct = (
        (sum(t.close_profit for t in trades) / total_trades) if total_trades > 0 else 0.0
    )

    # Top Pairs
    pair_stats = {}
    for t in trades:
        pair = t.pair
        if pair not in pair_stats:
            pair_stats[pair] = {"count": 0, "profit_abs": 0.0}
        pair_stats[pair]["count"] += 1
        pair_stats[pair]["profit_abs"] += t.close_profit_abs or 0.0

    top_pairs = sorted(pair_stats.items(), key=lambda x: x[1]["profit_abs"], reverse=True)[:5]

    # Top Exit Reasons
    reason_stats = {}
    for t in trades:
        reason = t.exit_reason
        if reason not in reason_stats:
            reason_stats[reason] = 0
        reason_stats[reason] += 1

    top_reasons = sorted(reason_stats.items(), key=lambda x: x[1], reverse=True)

    # Generate Markdown
    report_file = args.output_dir / f"daily_summary_{end_date.strftime('%Y%m%d')}.md"

    with report_file.open("w") as f:
        f.write(f"# Daily Trading Summary ({end_date.strftime('%Y-%m-%d')})\n\n")
        f.write(f"**Period**: {start_date.isoformat()} to {end_date.isoformat()} (UTC)\n\n")

        f.write("## Overview\n")
        f.write(f"- **Total Closed Trades**: {total_trades}\n")
        f.write(f"- **Win Rate**: {winrate:.1%}\n")
        f.write(f"- **Total PnL**: {total_profit_abs:.2f} USDT\n")
        f.write(f"- **Avg Return**: {avg_profit_pct:.2%}\n")
        f.write(f"- **Open Trades**: {len(open_trades)}\n\n")

        f.write("## Top Pairs (by PnL)\n")
        f.write("| Pair | Trades | PnL (USDT) |\n")
        f.write("|---|---|---|\n")
        for pair, stats in top_pairs:
            f.write(f"| {pair} | {stats['count']} | {stats['profit_abs']:.2f} |\n")
        f.write("\n")

        f.write("## Exit Reasons\n")
        for reason, count in top_reasons:
            f.write(f"- **{reason}**: {count}\n")

    logger.info(f"Report written to {report_file}")


if __name__ == "__main__":
    main()
