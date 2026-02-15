import logging
import sys

import pytest

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_FTStdErrStreamHandler(mocker):
    handler = FTStdErrStreamHandler()

    # Mock stderr
    mock_stderr = mocker.patch.object(sys, "stderr")

    # Create a log record
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # Test emit
    handler.emit(record)

    # Check if write was called with formatted message
    mock_stderr.write.assert_called()
    assert "Test message" in mock_stderr.write.call_args[0][0]

    # Check if flush was called
    mock_stderr.flush.assert_called()


def test_FTStdErrStreamHandler_exception(mocker):
    handler = FTStdErrStreamHandler()

    # Mock stderr to raise exception
    mock_stderr = mocker.patch.object(sys, "stderr")
    mock_stderr.write.side_effect = Exception("Test Error")

    # Mock handleError
    mock_handle_error = mocker.patch.object(handler, "handleError")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    handler.emit(record)
    mock_handle_error.assert_called_with(record)


def test_FTStdErrStreamHandler_recursion_error(mocker):
    handler = FTStdErrStreamHandler()

    # Mock stderr to raise RecursionError
    mock_stderr = mocker.patch.object(sys, "stderr")
    mock_stderr.write.side_effect = RecursionError("Recursion Error")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    with pytest.raises(RecursionError):
        handler.emit(record)
