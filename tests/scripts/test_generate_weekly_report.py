import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import os
from datetime import datetime, timezone

# Add scripts directory to path
sys.path.append(os.path.abspath("scripts"))
from generate_weekly_report import parse_git_commits, parse_optimization_log, generate_report_content, OPTIMIZATION_LOG_FILE

class TestWeeklyReport(unittest.TestCase):

    def test_parse_git_commits(self):
        commits = [
            "perf: optimized StrategyA (+1.50% ROI)",
            "chore: update log",
            "perf: optimized StrategyB (+0.50% ROI)",
            "perf: optimized StrategyA (+2.00% ROI)"
        ]

        strategies, roi = parse_git_commits(commits)

        self.assertEqual(strategies, ["StrategyA", "StrategyB", "StrategyA"])
        self.assertAlmostEqual(roi, 4.0)

    @patch("builtins.open")
    @patch("pathlib.Path.exists")
    def test_parse_optimization_log(self, mock_exists, mock_open):
        mock_exists.return_value = True

        # Mock file content
        now = datetime.now(timezone.utc)
        ts_str = now.strftime('%Y-%m-%d %H:%M:%S')

        log_content = f"""
[{ts_str}] Selected Strategy: StrategyStuck
[{ts_str}] ... hyperopt ...
[{ts_str}] Evaluation FAILED. Reverting changes.
[{ts_str}] Selected Strategy: StrategyGood
[{ts_str}] Evaluation PASSED. Committing changes.
[{ts_str}] Selected Strategy: StrategyRecovered
[{ts_str}] Evaluation FAILED.
[{ts_str}] Selected Strategy: StrategyRecovered
[{ts_str}] Evaluation PASSED.
"""
        # mock_open return value needs to be iterable yielding lines
        mock_file = MagicMock()
        mock_file.__enter__.return_value = log_content.strip().splitlines()
        mock_open.return_value = mock_file

        stuck = parse_optimization_log(days=7)

        self.assertIn("StrategyStuck", stuck)
        self.assertNotIn("StrategyGood", stuck)
        self.assertNotIn("StrategyRecovered", stuck)

    def test_generate_report_content(self):
        updated = ["StrategyA", "StrategyB"]
        roi = 2.5
        stuck = ["StrategyC"]

        content = generate_report_content(updated, roi, stuck)

        self.assertIn("# Weekly Strategy Report", content)
        self.assertIn("## 1. Updated Strategies", content)
        self.assertIn("- StrategyA", content)
        self.assertIn("- StrategyB", content)
        self.assertIn("## 2. Portfolio ROI Improvement", content)
        self.assertIn("**Total Estimated Improvement:** +2.50%", content)
        self.assertIn("## 3. Stuck Strategies", content)
        self.assertIn("- StrategyC", content)

if __name__ == "__main__":
    unittest.main()
