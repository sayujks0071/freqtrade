import logging
from io import StringIO
from unittest.mock import patch

from freqtrade.loggers.std_err_stream_handler import FTStdErrStreamHandler


def test_ft_std_err_stream_handler_emit(capsys):
    handler = FTStdErrStreamHandler()
    logger = logging.getLogger("test_ft_std_err_stream_handler")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    # Test basic emitting
    with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
        logger.info("Test message")
        assert "Test message" in mock_stderr.getvalue()


def test_ft_std_err_stream_handler_flush():
    handler = FTStdErrStreamHandler()
    with patch("sys.stderr") as mock_stderr:
        handler.flush()
        mock_stderr.flush.assert_called_once()


def test_ft_std_err_stream_handler_emit_exception():
    handler = FTStdErrStreamHandler()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test",
        args=(),
        exc_info=None,
    )

    # Mock sys.stderr.write to raise an exception
    with patch("sys.stderr.write", side_effect=Exception("Test Error")):
        with patch.object(handler, "handleError") as mock_handle_error:
            handler.emit(record)
            mock_handle_error.assert_called_once_with(record)


def test_ft_std_err_stream_handler_recursion_error():
    handler = FTStdErrStreamHandler()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="Test",
        args=(),
        exc_info=None,
    )

    # Mock sys.stderr.write to raise RecursionError
    with patch("sys.stderr.write", side_effect=RecursionError):
        try:
            handler.emit(record)
        except RecursionError:
            pass
        else:
            raise AssertionError("RecursionError should have been raised")
