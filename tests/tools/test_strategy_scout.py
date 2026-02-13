import ast
import os
import sys
import unittest
from unittest.mock import MagicMock, patch


# Add tools to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../tools')))

# Since strategy_scout is a script in tools/, we might need to import it carefully
# But since I added tools to path, I can import strategy_scout if it was a module.
# However, strategy_scout.py is a script. Importing it might run main if not guarded.
# It is guarded with if __name__ == '__main__':.

from strategy_scout import StrategyScout, StrategyVisitor


class TestStrategyVisitor(unittest.TestCase):
    def test_extract_metadata(self):
        code = """
class MyStrategy(IStrategy):
    stoploss = -0.10
    minimal_roi = {"0": 0.2}
    timeframe = '5m'
    process_only_new_candles = True
    can_short = True

    def populate_indicators(self, dataframe, metadata):
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        dataframe['mac'] = talib.MACD(dataframe)
        return dataframe
"""
        visitor = StrategyVisitor()
        visitor.visit(ast.parse(code))

        self.assertEqual(visitor.metadata['stoploss'], -0.10)
        self.assertEqual(visitor.metadata['timeframe'], '5m')
        self.assertTrue(visitor.metadata['can_short'])
        self.assertIn('ta.RSI', visitor.metadata['indicators'])
        self.assertIn('talib.MACD', visitor.metadata['indicators'])

class TestStrategyScout(unittest.TestCase):
    @patch('requests.Session')
    def test_search_github(self, mock_session):
        # Mock responses
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [
                {"full_name": "user/repo1", "stargazers_count": 100},
                {"full_name": "user/repo2", "stargazers_count": 50}
            ]
        }
        # Configure the mock to return the response when get is called
        mock_session_instance = mock_session.return_value
        mock_session_instance.get.return_value = mock_resp

        scout = StrategyScout()
        # Mock check_rate_limit to return True
        scout.check_rate_limit = MagicMock(return_value=True)
        # Mock add_known_sources to avoid extra calls
        scout._add_known_sources = MagicMock()

        # Inject the mock session
        scout.session = mock_session_instance

        scout.search_github()

        # We expect at least these 2, but search_github loops over SEARCH_QUERIES (4 queries).
        # So it will add them multiple times (deduplicated by dict key though).
        self.assertEqual(len(scout.candidates), 2)
        # Check full_name is in candidates
        names = [c['full_name'] for c in scout.candidates]
        self.assertIn('user/repo1', names)

if __name__ == '__main__':
    unittest.main()
