from pathlib import Path

from freqtrade.resolvers import StrategyResolver
from freqtrade.strategy.interface import IStrategy


def test_experimental_sentiment_loading(default_conf):
    # Ensure config doesn't override strategy timeframe
    if "timeframe" in default_conf:
        del default_conf["timeframe"]

    default_conf.update(
        {
            "strategy": "Experimental_Sentiment",
            "strategy_path": str(Path.cwd() / "user_data" / "strategies"),
            "trading_mode": "futures",
            "margin_mode": "isolated",
        }
    )
    strategy = StrategyResolver.load_strategy(default_conf)
    assert isinstance(strategy, IStrategy)
    assert strategy.timeframe == "1h"
    assert strategy.startup_candle_count == 100


def test_experimental_sentiment_indicators(default_conf, dataframe_1m):
    default_conf.update(
        {
            "strategy": "Experimental_Sentiment",
            "strategy_path": str(Path.cwd() / "user_data" / "strategies"),
            "trading_mode": "futures",
            "margin_mode": "isolated",
        }
    )
    strategy = StrategyResolver.load_strategy(default_conf)

    metadata = {"pair": "ETH/BTC"}  # ETH/BTC is in default whitelist
    dataframe = strategy.advise_indicators(dataframe_1m, metadata)

    assert "volume_mean_24" in dataframe.columns
    assert "twitter_volume" in dataframe.columns
    assert "whale_movement" in dataframe.columns
    assert "ema_50" in dataframe.columns


def test_experimental_sentiment_signals(default_conf, dataframe_1m):
    default_conf.update(
        {
            "strategy": "Experimental_Sentiment",
            "strategy_path": str(Path.cwd() / "user_data" / "strategies"),
            "trading_mode": "futures",
            "margin_mode": "isolated",
            "timeframe": "1m",  # Override timeframe to match dataframe_1m
        }
    )
    # Add ETH/USDT to whitelist if we want to use it, or use ETH/BTC
    default_conf["exchange"]["pair_whitelist"].append("ETH/USDT")

    strategy = StrategyResolver.load_strategy(default_conf)
    metadata = {"pair": "ETH/USDT"}

    # Mock data to trigger entry
    # twitter_volume > 2.0 -> volume > 2 * mean
    # whale_movement > 0.02 -> (high-low)/open > 0.02
    # close > ema_50

    # Let's populate indicators first
    dataframe = strategy.advise_indicators(dataframe_1m, metadata)

    # We need to manually set values to trigger the signal because random data might not trigger it
    dataframe["twitter_volume"] = 3.0
    dataframe["whale_movement"] = 0.03
    dataframe["ema_50"] = dataframe["close"] * 0.9  # Close > EMA

    dataframe = strategy.advise_entry(dataframe, metadata)

    assert "enter_long" in dataframe.columns
    assert dataframe["enter_long"].iloc[-1] == 1

    # Test Exit
    # twitter_volume < 1.0 & close < ema_50
    dataframe["twitter_volume"] = 0.5
    dataframe["ema_50"] = dataframe["close"] * 1.1  # Close < EMA

    dataframe = strategy.advise_exit(dataframe, metadata)
    assert "exit_long" in dataframe.columns
    assert dataframe["exit_long"].iloc[-1] == 1
