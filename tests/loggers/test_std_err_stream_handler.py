
import logging
import sys
from unittest.mock import MagicMock

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_emit(mocker):
    handler = FTStdErrStreamHandler()
    record = MagicMock()
    record.levelno = logging.INFO
    record.levelname = "INFO"
    record.msg = "Test message"
    record.args = None
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None

    # Mock sys.stderr
    mock_stderr = mocker.patch("sys.stderr")

    handler.emit(record)

    # Check if flush was called on sys.stderr
    assert mock_stderr.flush.call_count == 1
