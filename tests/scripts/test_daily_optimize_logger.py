import importlib.util
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock


def load_module_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys_modules_backup = {**importlib.sys.modules}
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        print(f"Failed to load module {module_name}: {e}")
        # Restore sys.modules to avoid pollution
        importlib.sys.modules.clear()
        importlib.sys.modules.update(sys_modules_backup)
        raise
    return module


# Load Logger class dynamically to avoid import issues
script_path = Path("scripts/daily_optimize.py").resolve()
daily_optimize = load_module_from_path("daily_optimize", script_path)
Logger = daily_optimize.Logger


class TestLogger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_file = Path(self.test_dir) / "test_log.txt"
        # Ensure parent exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.logger = Logger(self.log_file)
        # Mock terminal to suppress output
        self.logger.terminal = MagicMock()

    def tearDown(self):
        # Close the log file handle explicitly if needed, but Logger keeps it open.
        # We should close it or just let shutil clean up
        self.logger.log.close()
        shutil.rmtree(self.test_dir)

    def test_write_log(self):
        msg = "Test message"
        self.logger.write(msg)

        # Flush to ensure write
        self.logger.flush()

        with self.log_file.open() as f:
            content = f.read()

        self.assertIn(msg, content)
        # Verify timestamp format
        # [YYYY-MM-DD HH:MM:SS] Test message
        self.assertTrue(
            re.match(r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] Test message", content)
        )

    def test_write_newline(self):
        # Logger logic:
        # if message.strip(): add timestamp
        # else: just write

        self.logger.write("Line 1\n")
        self.logger.write("\n")
        self.logger.write("Line 2\n")
        self.logger.flush()

        with self.log_file.open() as f:
            lines = f.readlines()

        # Line 1 should have timestamp
        self.assertTrue(lines[0].startswith("["))
        self.assertIn("Line 1", lines[0])

        # Line 2 (the empty newline) should NOT have timestamp
        # Wait, the logic is:
        # if message.strip(): ... else: self.log.write(message)
        # So "\n" will be written as is.
        self.assertEqual(lines[1], "\n")

        # Line 3 should have timestamp
        self.assertTrue(lines[2].startswith("["))
        self.assertIn("Line 2", lines[2])


if __name__ == "__main__":
    unittest.main()
