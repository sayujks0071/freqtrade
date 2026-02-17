from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from freqtrade.rpc.api_server.api_auth import create_token, get_user_from_token
from freqtrade.rpc.api_server.webserver import ApiServer


def test_jwt_secret_generation(default_conf, mocker):
    # Ensure api_server key exists
    if "api_server" not in default_conf:
        default_conf["api_server"] = {}

    # Ensure no jwt_secret_key
    if "jwt_secret_key" in default_conf["api_server"]:
        del default_conf["api_server"]["jwt_secret_key"]

    # Mock necessary parts
    mocker.patch("freqtrade.rpc.telegram.Telegram._init")
    mocker.patch("freqtrade.rpc.api_server.webserver.ApiServer.start_api", MagicMock())

    # Initialize ApiServer
    ApiServer.shutdown()
    ApiServer(default_conf)

    # Check that a key was generated
    secret = default_conf["api_server"].get("jwt_secret_key")

    print(f"DEBUG: Secret is {secret}")

    # Assertions for the FIX:
    assert secret is not None, "Secret should have been generated"
    assert secret != "super-secret", "Secret should not be default"
    assert len(secret) >= 32, "Secret should be long enough"

    # Verify that a token signed with "super-secret" fails validation with the new secret
    token_forged = create_token({"identity": {"u": "FreqTrader"}}, "super-secret")

    # The function raises HTTPException on invalid token
    with pytest.raises(HTTPException) as excinfo:
        get_user_from_token(token_forged, secret)

    assert excinfo.value.status_code == 401

    ApiServer.shutdown()
