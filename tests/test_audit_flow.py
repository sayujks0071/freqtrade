import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import sys
import os

# Add root to path
sys.path.append(os.getcwd())

from user_data.strategies.SampleStrategy import SampleStrategy
from freqtrade.enums import RunMode

class TestAuditFlow(unittest.TestCase):
    def setUp(self):
        self.config = {
            'timeframe': '5m',
            'exchange': {'pair_whitelist': ['BTC/USDT:USDT']},
            'dry_run': True
        }
        self.strategy = SampleStrategy(self.config)

        # Mock DataProvider
        self.dp = MagicMock()
        self.dp.runmode.value = 'dry_run'
        self.strategy.dp = self.dp

    @patch('user_data.strategies._base.AuditedStrategyMixin.logger')
    def test_audit_log_entry(self, mock_logger):
        # Create dummy dataframe
        dates = pd.date_range('2026-01-31', periods=10, freq='5min', tz='UTC')
        df = pd.DataFrame({
            'date': dates,
            'open': 100.0,
            'high': 105.0,
            'low': 95.0,
            'close': 100.0,
            'volume': 1000.0
        })

        # Manually populate indicators to trigger signal
        # Logic: RSI > 30, TEMA <= BB_MID, TEMA > prev TEMA

        # Initialize columns
        df['rsi'] = 20.0
        df['tema'] = 100.0
        df['bb_middleband'] = 102.0
        df['enter_long'] = 0
        df['enter_short'] = 0

        # Set trigger on last row
        # Index 9 (last)
        df.loc[9, 'rsi'] = 40.0 # Crossed above 30
        df.loc[8, 'rsi'] = 25.0

        df.loc[9, 'tema'] = 101.0
        df.loc[8, 'tema'] = 100.0 # Raising

        df.loc[9, 'bb_middleband'] = 102.0 # TEMA (101) <= BB (102)

        metadata = {'pair': 'BTC/USDT:USDT'}

        # We need to ensure populate_indicators doesn't overwrite our manual values
        # SampleStrategy calls ta.RSI etc.
        # So we should probably mock the indicators or just use random data and rely on populate_entry_trend logic.
        # But populate_entry_trend uses the columns in the dataframe.
        # SampleStrategy.populate_entry_trend does NOT call populate_indicators. Freqtrade calls them separately.
        # So passing our prepared DF to populate_entry_trend is correct.

        self.strategy.buy_rsi.value = 30

        # Execute
        self.strategy.populate_entry_trend(df, metadata)

        # Verify signal was set
        self.assertEqual(df.iloc[-1]['enter_long'], 1)

        # Verify log was called
        # We expect one call
        self.assertTrue(mock_logger.info.called)
        args, _ = mock_logger.info.call_args
        log_msg = args[0]

        print(f"Captured Log: {log_msg}")

        self.assertIn("AUDIT_SIGNAL", log_msg)
        self.assertIn("pair=BTC/USDT:USDT", log_msg)
        self.assertIn("side=long", log_msg)
        self.assertIn("reason=", log_msg)

if __name__ == '__main__':
    unittest.main()
