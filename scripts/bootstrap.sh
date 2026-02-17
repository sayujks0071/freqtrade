#!/bin/bash
set -e

echo "Bootstrapping Freqtrade Delta Stack..."

# Create directories
mkdir -p user_data/configs
mkdir -p user_data/pairlists
mkdir -p user_data/reports
mkdir -p user_data/logs
mkdir -p user_data/data
mkdir -p user_data/strategies
mkdir -p user_data/db

# Copy .env if not exists
if [ ! -f .env ]; then
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "Please edit .env with your Delta API keys!"
else
    echo ".env already exists."
fi

# Create a dummy whitelist if it doesn't exist
if [ ! -f user_data/pairlists/whitelist.delta.json ]; then
    echo "Creating dummy whitelist..."
    echo '{"exchange": {"pair_whitelist": []}}' > user_data/pairlists/whitelist.delta.json
fi

# Create SampleStrategy if it doesn't exist
if [ ! -f user_data/strategies/SampleStrategy.py ]; then
    echo "Creating SampleStrategy.py..."
    cat > user_data/strategies/SampleStrategy.py <<EOL
from freqtrade.strategy import IStrategy
from pandas import DataFrame
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib

class SampleStrategy(IStrategy):
    MINIMAL_ROI = {
        "0": 0.1
    }
    STOP_LOSS = -0.10
    timeframe = '5m'

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe['rsi'] = ta.RSI(dataframe)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] < 30)
            ),
            'enter_long'] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe['rsi'] > 70)
            ),
            'exit_long'] = 1
        return dataframe
EOL
fi

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Edit .env with your API credentials."
echo "2. Run 'scripts/run_dryrun.sh' to validate and start the bot in dry-run mode."
