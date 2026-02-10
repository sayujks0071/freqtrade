from unittest.mock import MagicMock

from freqtrade.rpc.api_server.webserver import ApiServer
from freqtrade.rpc.rpc import RPC
from tests.conftest import get_patched_freqtradebot, log_has_re


def test_jwt_secret_warning_logic(default_conf, mocker, caplog):
    # Add api_server section to config
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "test",
        "password": "test",
        "jwt_secret_key": "super-secret",
    }

    # Setup mocks
    mocker.patch("freqtrade.rpc.telegram.Telegram._init")
    server_mock = MagicMock()
    mocker.patch("freqtrade.rpc.api_server.webserver.UvicornServer", server_mock)

    # We need to cleanup ApiServer instance between tests because it's a Singleton
    ApiServer.shutdown()

    def run_jwt_test(secret_key):
        default_conf["api_server"]["jwt_secret_key"] = secret_key
        apiserver = ApiServer(default_conf)
        apiserver.add_rpc_handler(RPC(get_patched_freqtradebot(mocker, default_conf)))
        # We don't need to start the full API server to test the init logic warning
        # but the warning happens in start_api()
        apiserver.start_api()
        # cleanup
        apiserver.cleanup()
        ApiServer.shutdown()

    # Test case 1: Default 'super-secret' should warn about default
    run_jwt_test("super-secret")
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    caplog.clear()

    # Test case 2: 'somethingrandom' should warn about default (known default)
    run_jwt_test("somethingrandom")
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    caplog.clear()

    # Test case 3: 'super' (substring of default, short) should NOT warn about default,
    # but about length
    run_jwt_test("super")
    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` is too short.*", caplog)
    caplog.clear()

    # Test case 4: Strong secret should NOT warn
    run_jwt_test("a-very-strong-secret-key-that-is-long-enough")
    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` is too short.*", caplog)
    caplog.clear()
