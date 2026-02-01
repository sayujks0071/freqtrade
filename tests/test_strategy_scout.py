import shutil
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Import the class to test
from tools.strategy_scout import StrategyScout


class TestStrategyScoutSecurity(unittest.TestCase):
    def setUp(self):
        # Setup directories
        vendor_dir = Path("user_data/strategies_vendor")
        if vendor_dir.exists():
            shutil.rmtree(vendor_dir)
        vendor_dir.mkdir(parents=True, exist_ok=True)

        # Create a dummy exploit file in the wrong place if it exists
        exploit_file = Path("user_data/exploit.py")
        if exploit_file.exists():
            exploit_file.unlink()

    def tearDown(self):
        vendor_dir = Path("user_data/strategies_vendor")
        if vendor_dir.exists():
            shutil.rmtree(vendor_dir)
        exploit_file = Path("user_data/exploit.py")
        if exploit_file.exists():
            exploit_file.unlink()

    @patch('tools.strategy_scout.requests.get')
    @patch('tools.strategy_scout.requests.Session')
    def test_path_traversal_prevention(self, mock_session_cls, mock_requests_get):
        # Mock the session and its methods
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        # Mock repo contents response
        mock_contents_response = MagicMock()
        mock_contents_response.status_code = 200
        # The malicious filename
        mock_contents_response.json.return_value = [
            {
                "name": "../../exploit.py",
                "download_url": "http://example.com/exploit.py"
            }
        ]

        # Mock file download response
        mock_file_response = MagicMock()
        mock_file_response.status_code = 200
        mock_file_response.text = "print('Pwned')"

        # Configure side_effect for session.get (API calls)
        mock_session.get.return_value = mock_contents_response

        # Configure return value for requests.get (File download)
        mock_requests_get.return_value = mock_file_response

        # Initialize scout
        scout = StrategyScout()

        # Manually set up a candidate
        candidate = {
            "full_name": "malicious/repo",
            "name": "repo",
            "strategy_path": "strategies",
            "html_url": "http://github.com/malicious/repo"
        }

        # Run vendor_strategies
        scout.vendor_strategies([candidate])

        # Check if the file ended up in the right place (sanitized)
        expected_path = Path("user_data/strategies_vendor/malicious_repo/exploit.py")
        exploit_path = Path("user_data/exploit.py")

        # It should NOT be at exploit_path
        self.assertFalse(
            exploit_path.exists(),
            "Vulnerability reproduced! File written to user_data/exploit.py"
        )

        # It SHOULD be at expected_path (because of basename/sanitize)
        self.assertTrue(
            expected_path.exists(),
            f"File not found at expected path: {expected_path}"
        )

        print("Security Fix Verified: Path traversal prevented.")

if __name__ == '__main__':
    unittest.main()
