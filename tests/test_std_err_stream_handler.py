import logging
import sys
from unittest.mock import MagicMock

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_FTStdErrStreamHandler(mocker):
    handler = FTStdErrStreamHandler()

    # Mock sys.stderr
    stderr_mock = MagicMock()
    mocker.patch.object(sys, "stderr", stderr_mock)

    # Create a log record
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # Call emit
    handler.emit(record)

    # Verify write called
    stderr_mock.write.assert_called_once_with("Test message\n")
    # Verify flush called
    stderr_mock.flush.assert_called_once()


def test_FTStdErrStreamHandler_flush(mocker):
    handler = FTStdErrStreamHandler()

    # Mock sys.stderr
    stderr_mock = MagicMock()
    mocker.patch.object(sys, "stderr", stderr_mock)

    handler.flush()
    stderr_mock.flush.assert_called_once()


def test_FTStdErrStreamHandler_exception(mocker):
    handler = FTStdErrStreamHandler()

    # Mock sys.stderr to raise an exception
    stderr_mock = MagicMock()
    stderr_mock.write.side_effect = Exception("Test exception")
    mocker.patch.object(sys, "stderr", stderr_mock)

    # Mock handleError to verify it's called
    handle_error_mock = mocker.patch.object(handler, "handleError")

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    handler.emit(record)

    handle_error_mock.assert_called_once_with(record)


def test_FTStdErrStreamHandler_recursion_error(mocker):
    handler = FTStdErrStreamHandler()

    # Mock sys.stderr to raise RecursionError
    stderr_mock = MagicMock()
    stderr_mock.write.side_effect = RecursionError("Test recursion")
    mocker.patch.object(sys, "stderr", stderr_mock)

    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    import pytest

    with pytest.raises(RecursionError):
        handler.emit(record)
