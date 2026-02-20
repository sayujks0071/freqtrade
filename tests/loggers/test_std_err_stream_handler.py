
import logging
import sys
from unittest.mock import MagicMock

import pytest

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_FTStdErrStreamHandler_emit(mocker):
    handler = FTStdErrStreamHandler()
    record = logging.makeLogRecord({"msg": "test message"})

    # Mock sys.stderr
    mock_stderr = mocker.patch("sys.stderr")

    handler.emit(record)

    mock_stderr.write.assert_called_with("test message\n")
    mock_stderr.flush.assert_called_once()


def test_FTStdErrStreamHandler_flush(mocker):
    handler = FTStdErrStreamHandler()
    mock_stderr = mocker.patch("sys.stderr")

    handler.flush()

    mock_stderr.flush.assert_called_once()


def test_FTStdErrStreamHandler_emit_exception(mocker):
    handler = FTStdErrStreamHandler()
    record = logging.makeLogRecord({"msg": "test message"})

    # Mock sys.stderr to raise an exception
    mock_stderr = mocker.patch("sys.stderr")
    mock_stderr.write.side_effect = Exception("Test Error")

    # Mock handleError to verify it's called
    mock_handle_error = mocker.patch.object(handler, "handleError")

    handler.emit(record)

    mock_handle_error.assert_called_once_with(record)


def test_FTStdErrStreamHandler_emit_recursion_error(mocker):
    handler = FTStdErrStreamHandler()
    record = logging.makeLogRecord({"msg": "test message"})

    # Mock sys.stderr to raise RecursionError
    mock_stderr = mocker.patch("sys.stderr")
    mock_stderr.write.side_effect = RecursionError("Recursion Error")

    with pytest.raises(RecursionError):
        handler.emit(record)
