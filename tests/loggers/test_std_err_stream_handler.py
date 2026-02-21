import logging
from unittest.mock import patch

import pytest

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_std_err_stream_handler():
    handler = FTStdErrStreamHandler()
    logger = logging.getLogger("test_std_err_handler")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    with patch("sys.stderr") as mock_stderr:
        logger.info("Test message")

        # Verify write called
        assert mock_stderr.write.called
        assert mock_stderr.flush.called

        # Verify content - might be multiple calls (msg + newline)
        # Check if any call contains the message
        calls = mock_stderr.write.call_args_list
        messages = [args[0] for args, _ in calls]
        assert any("Test message" in msg for msg in messages)

    logger.removeHandler(handler)


def test_std_err_stream_handler_exception():
    handler = FTStdErrStreamHandler()
    record = logging.LogRecord("name", logging.INFO, "pathname", 1, "msg", (), None)

    # Simulate recursion error
    with patch("sys.stderr.write", side_effect=RecursionError):
        with pytest.raises(RecursionError):
            handler.emit(record)

    # Simulate other exception
    with patch("sys.stderr.write", side_effect=ValueError):
        with patch.object(handler, "handleError") as mock_handle_error:
            handler.emit(record)
            assert mock_handle_error.called
