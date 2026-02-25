import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add scripts directory to path to import the module
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

import generate_weekly_report  # noqa: E402


@pytest.fixture
def mock_git_log():
    return """perf: optimized StrategyA (+10.5% ROI)
fix: minor bug
perf: optimized StrategyB (+5.2% ROI)
docs: update readme
"""


@pytest.fixture
def mock_optimization_log():
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    two_days_ago = now - timedelta(days=2)
    three_days_ago = now - timedelta(days=3)
    four_days_ago = now - timedelta(days=4)
    five_days_ago = now - timedelta(days=5)

    fmt = "%Y-%m-%d %H:%M:%S"

    return f"""
--- Optimization Run Started: {five_days_ago.strftime(fmt)} ---
Selected Strategy: StrategyA
Evaluation PASSED

--- Optimization Run Started: {four_days_ago.strftime(fmt)} ---
Selected Strategy: StrategyB
Evaluation FAILED

--- Optimization Run Started: {three_days_ago.strftime(fmt)} ---
Selected Strategy: StrategyC
Evaluation FAILED

--- Optimization Run Started: {two_days_ago.strftime(fmt)} ---
Selected Strategy: StrategyC
Evaluation FAILED

--- Optimization Run Started: {yesterday.strftime(fmt)} ---
Selected Strategy: StrategyC
Evaluation FAILED

--- Optimization Run Started: {now.strftime(fmt)} ---
Selected Strategy: StrategyC
Evaluation FAILED
"""

def test_generate_report_end_to_end(tmp_path, mock_git_log, mock_optimization_log):
    # Setup temporary report file
    report_file = tmp_path / "WEEKLY_REPORT.md"

    with patch("generate_weekly_report.REPORT_FILE", report_file), \
         patch("generate_weekly_report.OPTIMIZATION_LOG") as mock_opt_log_path, \
         patch("subprocess.run") as mock_run:

        # Mock git log output
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = mock_git_log

        # Mock optimization log content
        mock_opt_log_path.exists.return_value = True
        mock_opt_log_path.read_text.return_value = mock_optimization_log

        # Run report generation
        generate_weekly_report.generate_report()

        # Verify Report Content
        assert report_file.exists()
        content = report_file.read_text()

        # Section 1: Updated Strategies
        assert "StrategyA" in content
        assert "+10.50%" in content
        assert "StrategyB" in content
        assert "+5.20%" in content

        # Section 2: Total ROI
        # 10.5 + 5.2 = 15.7
        assert "+15.70%" in content

        # Section 3: Stuck Strategies
        # StrategyC should be stuck (4 failures)
        assert "Stuck Strategies" in content
        assert "- StrategyC" in content

        # StrategyB failed once, should NOT be stuck
        assert "- StrategyB" not in content
