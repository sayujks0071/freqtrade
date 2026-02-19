#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Environment..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/strategies
mkdir -p user_data/strategies/_base
mkdir -p user_data/logs
mkdir -p user_data/protections
mkdir -p user_data/strategies_vendor

# Create initial whitelist if missing
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    # Minimal valid whitelist to allow startup before first refresh
    echo '{"exchange": {"pair_whitelist": ["BTC/USDT:USDT"]}}' > user_data/pairlists/whitelist.delta.json
fi

if [ ! -f user_data/pairlists/whitelist.delta.txt ]; then
    echo "BTC/USDT:USDT" > user_data/pairlists/whitelist.delta.txt
fi

# Ensure SampleStrategy exists (to avoid crashes if config references it)
if [ ! -f user_data/strategies/SampleStrategy.py ]; then
    echo "Creating SampleStrategy..."
    cat <<EOF > user_data/strategies/SampleStrategy.py
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class SampleStrategy(IStrategy):
    INTERFACE_VERSION = 3
    minimal_roi = {"0": 0.1}
    stoploss = -0.1
    timeframe = '1h'

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'enter_long'] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[:, 'exit_long'] = 0
        return dataframe
EOF
fi

chmod +x scripts/*.sh

echo "Bootstrap complete."
