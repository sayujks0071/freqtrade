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

    # Test case 1: Default 'super-secret' should warn about default
    apiserver = ApiServer(default_conf)
    apiserver.add_rpc_handler(RPC(get_patched_freqtradebot(mocker, default_conf)))
    apiserver.start_api()
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    caplog.clear()
    ApiServer.shutdown()

    # Test case 2: 'somethingrandom' should warn about default (known default)
    default_conf["api_server"]["jwt_secret_key"] = "somethingrandom"
    apiserver = ApiServer(default_conf)
    apiserver.add_rpc_handler(RPC(get_patched_freqtradebot(mocker, default_conf)))
    apiserver.start_api()
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    caplog.clear()
    ApiServer.shutdown()

    # Test case 3: 'super' (substring of default, short) should NOT warn about default,
    # but about length
    default_conf["api_server"]["jwt_secret_key"] = "super"
    apiserver = ApiServer(default_conf)
    apiserver.add_rpc_handler(RPC(get_patched_freqtradebot(mocker, default_conf)))
    apiserver.start_api()

    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    assert log_has_re("SECURITY WARNING - `jwt_secret_key` is too short.*", caplog)
    caplog.clear()
    ApiServer.shutdown()

    # Test case 4: Strong secret should NOT warn
    default_conf["api_server"]["jwt_secret_key"] = "a-very-strong-secret-key-that-is-long-enough"
    apiserver = ApiServer(default_conf)
    apiserver.add_rpc_handler(RPC(get_patched_freqtradebot(mocker, default_conf)))
    apiserver.start_api()
    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` seems to be default.*", caplog)
    assert not log_has_re("SECURITY WARNING - `jwt_secret_key` is too short.*", caplog)
    caplog.clear()
    ApiServer.shutdown()
