import logging
import pytest
from unittest.mock import patch
from freqtrade.rpc.api_server.webserver import ApiServer
from tests.conftest import log_has

@pytest.fixture(autouse=True)
def cleanup_api_server():
    ApiServer.shutdown()
    yield
    ApiServer.shutdown()

def test_jwt_default_key_warning(default_conf, caplog):
    caplog.set_level(logging.WARNING)

    # Initialize api_server config
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "test",
        "password": "test",
        "jwt_secret_key": "super-secret"
    }

    with patch("freqtrade.rpc.api_server.webserver.UvicornServer"):
        ApiServer(default_conf, standalone=True)

    assert log_has("SECURITY WARNING - `jwt_secret_key` seems to be default.Others may be able to log into your bot.", caplog)

def test_jwt_substring_false_positive(default_conf, caplog):
    caplog.set_level(logging.WARNING)

    # Initialize api_server config
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "test",
        "password": "test",
        "jwt_secret_key": "om" # "om" is a substring of "somethingrandom", but also short
    }

    with patch("freqtrade.rpc.api_server.webserver.UvicornServer"):
        ApiServer(default_conf, standalone=True)

    # Should NOT trigger the "default key" warning
    assert not log_has("SECURITY WARNING - `jwt_secret_key` seems to be default.Others may be able to log into your bot.", caplog)
    # Should trigger the "short key" warning
    assert log_has("SECURITY WARNING - `jwt_secret_key` is too short, please use at least 16 characters.", caplog)

def test_jwt_short_key_warning(default_conf, caplog):
    caplog.set_level(logging.WARNING)

    # Initialize api_server config
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "test",
        "password": "test",
        "jwt_secret_key": "shortkey123" # 11 chars
    }

    with patch("freqtrade.rpc.api_server.webserver.UvicornServer"):
        ApiServer(default_conf, standalone=True)

    # Should trigger the "short key" warning
    assert log_has("SECURITY WARNING - `jwt_secret_key` is too short, please use at least 16 characters.", caplog)

def test_jwt_secure_key_no_warning(default_conf, caplog):
    caplog.set_level(logging.WARNING)

    # Initialize api_server config
    default_conf["api_server"] = {
        "enabled": True,
        "listen_ip_address": "127.0.0.1",
        "listen_port": 8080,
        "username": "test",
        "password": "test",
        "jwt_secret_key": "thisisaverysecureandlongsecretkey12345" # > 16 chars
    }

    with patch("freqtrade.rpc.api_server.webserver.UvicornServer"):
        ApiServer(default_conf, standalone=True)

    # Should NOT trigger any warning
    assert not log_has("SECURITY WARNING - `jwt_secret_key` seems to be default.Others may be able to log into your bot.", caplog)
    assert not log_has("SECURITY WARNING - `jwt_secret_key` is too short, please use at least 16 characters.", caplog)
